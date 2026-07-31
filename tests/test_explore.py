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

    def fake_compute_plan(track, progress, previous_item_ids=None):
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


def test_explore_add_inserts_item_and_redirects_to_lesson(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post(
        "/explore/add/rag-chunking-strategies",
        data={"track_id": 1},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/item/1/rag-chunking-strategies"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert any(step["item_id"] == "rag-chunking-strategies" for step in latest["steps"])
    assert latest["trigger"] == "explore_add"


def test_explore_add_does_not_duplicate_an_already_present_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    client.post("/explore/add/rag-fundamentals", data={"track_id": 1})

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    matching = [step for step in latest["steps"] if step["item_id"] == "rag-fundamentals"]
    assert len(matching) == 1


def test_explore_add_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post("/explore/add/does-not-exist", data={"track_id": 1})
    assert response.status_code == 404


def test_explore_add_returns_404_for_another_users_track(client):
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
        response = other_client.post("/explore/add/rag-fundamentals", data={"track_id": 1})

    assert response.status_code == 404


def test_explore_lists_all_catalog_items_with_no_filters(client):
    response = client.get("/explore")

    assert response.status_code == 200
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    assert "What Is an LLM, Really?" in response.text


def test_explore_filters_by_track(client):
    response = client.get("/explore", params={"track": "RAG"})

    assert response.status_code == 200
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    assert "What Is an LLM, Really?" not in response.text


def test_explore_filters_by_level(client):
    response = client.get("/explore", params={"level": "advanced"})

    assert response.status_code == 200
    assert "RAG Practitioner Certification Assessment" in response.text
    assert "What Is an LLM, Really?" not in response.text


def test_explore_redirects_to_login_when_not_authenticated(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    with TestClient(app_module.app) as anon_client:
        response = anon_client.get("/explore", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_explore_shows_add_to_track_control_when_user_has_a_track(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/explore")

    assert 'action="/explore/add/rag-fundamentals"' in response.text


def test_explore_shows_hint_when_user_has_no_tracks(client):
    response = client.get("/explore")

    assert "Start a track first" in response.text


def test_explore_shows_starter_path_cards(client):
    response = client.get("/explore")

    assert 'href="/explore/starter/product-manager"' in response.text
    assert "Product Manager" in response.text
    assert "Engineer" in response.text
    assert "Product Builder (Forward-Deployed)" in response.text


def test_explore_nav_link_appears_on_dashboard(client):
    response = client.get("/")

    assert 'href="/explore"' in response.text
