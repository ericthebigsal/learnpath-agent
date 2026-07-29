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
        )

    monkeypatch.setattr(app_module, "compute_plan", fake_compute_plan)

    with TestClient(app_module.app) as test_client:
        yield test_client


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


def test_current_path_screen_returns_404_for_nonexistent_learner(client):
    response = client.get("/path/99999")

    assert response.status_code == 404
