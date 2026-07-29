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

    def fake_compute_plan(learner, progress):
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
        yield test_client


def test_compute_plan_falls_back_when_genai_client_construction_raises(monkeypatch):
    # Exercises the real app_module.compute_plan (unlike every other test in this file,
    # which monkeypatches compute_plan itself). This is the seam where a missing
    # GEMINI_API_KEY used to crash with an unhandled ValueError from genai.Client(),
    # instead of falling back to the rule-based planner like every other Gemini failure.
    def raise_missing_api_key():
        raise ValueError("Missing key inputs argument!")

    monkeypatch.setattr(app_module.genai, "Client", raise_missing_api_key)

    learner = {"goal_text": "I want to learn about RAG", "starting_level": "beginner"}
    plan, used_fallback, candidate_ids = app_module.compute_plan(learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0
    assert len(candidate_ids) > 0


def test_start_page_renders_goal_form(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "goal_text" in response.text
    assert "starting_level" in response.text


def test_submitting_start_form_creates_learner_and_redirects_to_path(client):
    response = client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/path/")


def test_submitting_start_form_logs_the_initial_plan(client, tmp_path):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest is not None
    assert latest["trigger"] == "initial"
    assert latest["steps"][0]["item_id"] == "rag-fundamentals"


def test_current_path_screen_shows_recommended_items_and_rationale(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    assert "RAG Fundamentals" in response.text
    assert "Matches your goal." in response.text
    assert "Start with RAG fundamentals." in response.text


def test_current_path_screen_shows_candidates_considered(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    assert "Candidates considered (2)" in response.text
    assert "Chunking Strategies: Splitting Documents Without Losing Meaning" in response.text


def test_current_path_screen_returns_404_for_nonexistent_learner(client):
    response = client.get("/path/99999")

    assert response.status_code == 404


def test_item_view_shows_content_and_quiz_form(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals")

    assert response.status_code == 200
    assert "Retrieval-Augmented Generation" in response.text
    assert 'action="/item/1/rag-fundamentals/submit"' in response.text


def test_submitting_quiz_grades_it_and_shows_diff(client, monkeypatch):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    def fake_compute_plan_after_quiz(learner, progress):
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
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/does-not-exist")

    assert response.status_code == 404


def test_submit_quiz_returns_404_for_nonexistent_learner(client):
    response = client.post(
        "/item/99999/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )

    assert response.status_code == 404


def test_history_screen_shows_plan_log_and_catalog_table(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/history/1")

    assert response.status_code == 200
    assert "Start with RAG fundamentals." in response.text  # from plan_log
    assert "RAG Fundamentals" in response.text  # from the catalog table


def test_history_screen_returns_404_for_nonexistent_learner(client):
    response = client.get("/history/99999")

    assert response.status_code == 404
