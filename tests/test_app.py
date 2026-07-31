import pytest
from fastapi.testclient import TestClient

import app as app_module
import db
from models import DroppedItem, PlanResponse, PlanStep


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    def fake_compute_plan(track, progress, previous_item_ids=None):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
                summary="Start with RAG fundamentals.",
            ),
            False,
            ["rag-fundamentals", "rag-vector-databases"],
        )

    monkeypatch.setattr(app_module, "compute_plan", fake_compute_plan)

    with TestClient(app_module.app) as test_client:
        test_client.post(
            "/register",
            data={"email": "eric@example.com", "password": "hunter22", "confirm_password": "hunter22"},
        )
        yield test_client


def test_compute_plan_falls_back_when_genai_client_construction_raises(monkeypatch):
    def raise_missing_api_key():
        raise ValueError("Missing key inputs argument!")

    monkeypatch.setattr(app_module.genai, "Client", raise_missing_api_key)

    track = {"goal_text": "I want to learn about RAG", "starting_level": "beginner"}
    plan, used_fallback, candidate_ids = app_module.compute_plan(track, [])

    assert used_fallback is True
    assert len(plan.steps) > 0
    assert len(candidate_ids) > 0


def test_dashboard_redirects_to_login_when_not_authenticated(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    with TestClient(app_module.app) as anon_client:
        response = anon_client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_shows_goal_form_when_logged_in(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "goal_text" in response.text
    assert "starting_level" in response.text


def test_submitting_track_form_creates_track_and_redirects_to_path(client):
    response = client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/path/")


def test_submitting_track_form_with_invalid_starting_level_returns_422_and_creates_no_track(client):
    response = client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "not-a-level"},
        follow_redirects=False,
    )

    assert response.status_code == 422

    user = db.get_user_by_email("eric@example.com", app_module.DB_PATH)
    assert db.get_tracks_for_user(user["id"], app_module.DB_PATH) == []


def test_submitting_track_form_logs_the_initial_plan_and_updates_default_level(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "intermediate"},
    )

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest is not None
    assert latest["trigger"] == "initial"
    assert latest["steps"][0]["item_id"] == "rag-fundamentals"

    user = db.get_user_by_email("eric@example.com", app_module.DB_PATH)
    assert user["default_starting_level"] == "intermediate"


def test_dashboard_lists_existing_tracks(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "I want to learn about RAG" in response.text


def test_current_path_screen_shows_recommended_items_and_rationale(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    assert "RAG Fundamentals" in response.text
    assert "Matches your goal." in response.text
    assert "Start with RAG fundamentals." in response.text


def test_current_path_screen_shows_candidates_considered(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    # the fixture's candidate_ids is ["rag-fundamentals", "rag-vector-databases"], but
    # rag-fundamentals is also the chosen step — it must not appear as a "candidate"
    # since it wasn't rejected, it's already in the path.
    assert "Candidates considered (1)" in response.text
    assert "Vector Databases: How Similarity Search Actually Works" in response.text


def test_current_path_screen_excludes_chosen_steps_from_candidates(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    # RAG Fundamentals is the chosen step (appears once, in the trail), not a second
    # time inside the candidates-considered panel.
    assert response.text.count("RAG Fundamentals: Retrieval Meets Generation") == 1


def test_current_path_screen_lets_you_add_a_candidate_to_the_path(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert 'action="/path/1/add/rag-vector-databases"' in response.text
    assert "Add to path" in response.text


def test_current_path_screen_returns_404_for_nonexistent_track(client):
    response = client.get("/path/99999")
    assert response.status_code == 404


def test_current_path_screen_returns_404_for_track_with_no_logged_plan(client):
    user = db.get_user_by_email("eric@example.com", app_module.DB_PATH)
    track = db.create_track(
        user["id"], "Learn RAG", "Learn RAG basics", "beginner", app_module.DB_PATH
    )

    response = client.get(f"/path/{track['id']}")

    assert response.status_code == 404


def test_current_path_screen_returns_404_for_another_users_track(client, tmp_path):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    with TestClient(app_module.app) as other_client:
        other_client.post(
            "/register",
            data={"email": "someone-else@example.com", "password": "hunter22", "confirm_password": "hunter22"},
        )
        response = other_client.get("/path/1")

    assert response.status_code == 404


def test_item_view_shows_content_but_not_the_quiz_form(client):
    # rag-vector-databases has legacy flat content (no sections) — this test
    # covers the non-paginated rendering path in item.html.
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-vector-databases")

    assert response.status_code == 200
    assert "Vector databases store embeddings" in response.text
    assert 'action="/item/1/rag-vector-databases/submit"' not in response.text
    assert 'href="/item/1/rag-vector-databases/quiz"' in response.text


def test_item_quiz_page_shows_the_quiz_form_but_not_the_lesson_content(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-vector-databases/quiz")

    assert response.status_code == 200
    assert 'action="/item/1/rag-vector-databases/submit"' in response.text
    assert "Vector databases store embeddings" not in response.text
    assert 'href="/item/1/rag-vector-databases"' in response.text  # link back to re-read the material


def test_item_quiz_page_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/does-not-exist/quiz")

    assert response.status_code == 404


def test_item_view_redirects_to_first_section_when_item_has_sections(client):
    # rag-fundamentals has real, structured sections (unlike most catalog items).
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/item/1/rag-fundamentals/section/1"


def test_item_section_view_shows_only_that_sections_content(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/2")

    assert response.status_code == 200
    assert "<h2>How the pipeline actually works</h2>" in response.text
    assert "Section 2 of 5" in response.text
    assert "<h2>What problem this solves</h2>" not in response.text  # section 1's body isn't rendered, only its TOC entry


def test_item_section_view_shows_the_diagram_on_the_section_that_has_one(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/2")

    assert response.status_code == 200
    assert '<figure class="lesson-diagram">' in response.text
    assert "<svg" in response.text
    assert "rag-pipeline-title" in response.text


def test_item_section_view_shows_no_diagram_on_a_section_without_one(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/1")

    assert response.status_code == 200
    assert '<figure class="lesson-diagram">' not in response.text


def test_item_section_view_shows_table_of_contents_with_all_headings(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/1")

    assert response.status_code == 200
    for heading in [
        "What problem this solves",
        "How the pipeline actually works",
        "Where it breaks",
        "A worked example",
        "What&#39;s next",
    ]:
        assert heading in response.text
    assert 'href="/item/1/rag-fundamentals/quiz"' in response.text


def test_item_section_view_links_to_previous_and_next_sections(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/2")

    assert 'href="/item/1/rag-fundamentals/section/1"' in response.text
    assert 'href="/item/1/rag-fundamentals/section/3"' in response.text


def test_item_section_view_first_section_has_no_previous_link(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/1")

    assert 'href="/item/1/rag-fundamentals/section/0"' not in response.text


def test_item_section_view_last_section_links_to_quiz_instead_of_next(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/5")

    assert 'href="/item/1/rag-fundamentals/section/6"' not in response.text
    assert "Take the quiz" in response.text


def test_item_section_view_returns_404_for_out_of_range_section_number(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/section/6")

    assert response.status_code == 404


def test_item_section_view_redirects_to_flat_view_for_item_without_sections(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-vector-databases/section/1", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/item/1/rag-vector-databases"


def test_submitting_quiz_grades_it_and_shows_diff(client, monkeypatch):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    def fake_compute_plan_after_quiz(track, progress, previous_item_ids=None):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-chunking-strategies", rationale="Next in RAG track.")],
                summary="Move on to chunking strategies.",
                dropped=[
                    DroppedItem(item_id="rag-fundamentals", rationale="You've already mastered this.")
                ],
            ),
            False,
            ["rag-chunking-strategies"],
        )

    monkeypatch.setattr(app_module, "compute_plan", fake_compute_plan_after_quiz)

    response = client.post(
        "/item/1/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )

    assert response.status_code == 200
    assert "Move on to chunking strategies." in response.text
    # resolved titles, not raw ids
    assert "Chunking Strategies: Splitting Documents Without Losing Meaning" in response.text
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    # real rationale for both an added and a removed item
    assert "Next in RAG track." in response.text
    assert "already mastered this" in response.text
    # add-back action present for the removed item
    assert 'action="/path/1/add/rag-fundamentals"' in response.text

    progress = db.get_progress(1, app_module.DB_PATH)
    assert progress[0]["item_id"] == "rag-fundamentals"


def test_item_view_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/does-not-exist")
    assert response.status_code == 404


def test_submit_quiz_returns_404_for_nonexistent_track(client):
    response = client.post(
        "/item/99999/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )
    assert response.status_code == 404


def test_history_screen_shows_no_completed_courses_yet(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/history/1")

    assert response.status_code == 200
    assert "No courses completed yet" in response.text
    assert 'href="/explore"' in response.text


def test_history_screen_shows_completed_courses_with_quiz_results(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )
    client.post(
        "/item/1/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )

    response = client.get("/history/1")

    assert response.status_code == 200
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    assert "100.0%" in response.text
    assert "No courses completed yet" not in response.text


def test_history_screen_returns_404_for_nonexistent_track(client):
    response = client.get("/history/99999")
    assert response.status_code == 404


def test_add_back_route_reinserts_a_dropped_item_and_redirects(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post(
        "/path/1/add/rag-vector-databases", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/path/1"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert any(step["item_id"] == "rag-vector-databases" for step in latest["steps"])
    assert latest["trigger"] == "manual_add"


def test_add_back_route_does_not_duplicate_an_already_present_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    # rag-fundamentals is already in the fixture's fake initial plan
    client.post("/path/1/add/rag-fundamentals")

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    matching = [step for step in latest["steps"] if step["item_id"] == "rag-fundamentals"]
    assert len(matching) == 1


def test_add_back_route_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post("/path/1/add/does-not-exist")
    assert response.status_code == 404


def test_add_back_route_returns_404_for_another_users_track(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    with TestClient(app_module.app) as other_client:
        other_client.post(
            "/register",
            data={
                "email": "someone-else@example.com",
                "password": "hunter22",
                "confirm_password": "hunter22",
            },
        )
        response = other_client.post("/path/1/add/rag-fundamentals")

    assert response.status_code == 404
