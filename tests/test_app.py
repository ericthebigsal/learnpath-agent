import pytest
from fastapi.testclient import TestClient

import app as app_module
import db
from models import PlanResponse, PlanStep


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    def fake_compute_plan(track, progress):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
                summary="Start with RAG fundamentals.",
            ),
            False,
            ["rag-fundamentals", "rag-chunking-strategies"],
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
    assert "Candidates considered (2)" in response.text
    assert "Chunking Strategies: Splitting Documents Without Losing Meaning" in response.text


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
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals")

    assert response.status_code == 200
    assert "Retrieval-Augmented Generation" in response.text
    assert 'action="/item/1/rag-fundamentals/submit"' not in response.text
    assert 'href="/item/1/rag-fundamentals/quiz"' in response.text


def test_item_quiz_page_shows_the_quiz_form_but_not_the_lesson_content(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals/quiz")

    assert response.status_code == 200
    assert 'action="/item/1/rag-fundamentals/submit"' in response.text
    assert "Retrieval-Augmented Generation" not in response.text
    assert 'href="/item/1/rag-fundamentals"' in response.text  # link back to re-read the material


def test_item_quiz_page_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/does-not-exist/quiz")

    assert response.status_code == 404


def test_submitting_quiz_grades_it_and_shows_diff(client, monkeypatch):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    def fake_compute_plan_after_quiz(track, progress):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-chunking-strategies", rationale="Next in RAG track.")],
                summary="Move on to chunking strategies.",
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
    assert "Added" in response.text or "added" in response.text

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
    assert "RAG Fundamentals" in response.text  # still shows in the full catalog table


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
