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


from starter_paths import get_starter_path


def test_explore_starter_preview_shows_all_steps_with_rationale(client):
    response = client.get("/explore/starter/product-manager")

    assert response.status_code == 200
    assert "What Is an LLM, Really?" in response.text
    assert "Grounds every later conversation in what the model actually is." in response.text
    assert 'action="/explore/starter/product-manager"' in response.text


def test_explore_starter_preview_returns_404_for_unknown_id(client):
    response = client.get("/explore/starter/does-not-exist")
    assert response.status_code == 404


def test_explore_starter_confirm_creates_track_with_fixed_plan(client):
    response = client.post("/explore/starter/engineer", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/path/1"

    path_response = client.get("/path/1")
    assert path_response.status_code == 200
    assert "How LLMs Generate Text: Autoregression and Sampling" in path_response.text

    track = db.get_track(1, app_module.DB_PATH)
    assert track["name"] == "Engineer"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest["trigger"] == "starter"
    expected = get_starter_path("engineer")
    assert [step["item_id"] for step in latest["steps"]] == [s.item_id for s in expected.steps]


def test_explore_starter_confirm_returns_404_for_unknown_id(client):
    response = client.post("/explore/starter/does-not-exist")
    assert response.status_code == 404


def test_explore_open_creates_an_ad_hoc_track_and_redirects_into_the_lesson(client):
    response = client.post("/explore/open/rag-chunking-strategies", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/item/1/rag-chunking-strategies"

    track = db.get_track(1, app_module.DB_PATH)
    assert track["name"] == "Ad Hoc"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest["trigger"] == "explore_open"
    assert latest["steps"][0]["item_id"] == "rag-chunking-strategies"


def test_explore_open_reuses_the_same_ad_hoc_track_across_calls(client):
    client.post("/explore/open/rag-chunking-strategies")
    response = client.post("/explore/open/rag-vector-databases", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/item/1/rag-vector-databases"

    tracks = db.get_tracks_for_user(1, app_module.DB_PATH)
    ad_hoc_tracks = [t for t in tracks if t["name"] == "Ad Hoc"]
    assert len(ad_hoc_tracks) == 1

    latest = db.get_latest_plan(ad_hoc_tracks[0]["id"], app_module.DB_PATH)
    item_ids = {step["item_id"] for step in latest["steps"]}
    assert item_ids == {"rag-chunking-strategies", "rag-vector-databases"}


def test_explore_open_does_not_duplicate_an_already_present_item(client):
    client.post("/explore/open/rag-chunking-strategies")
    client.post("/explore/open/rag-chunking-strategies")

    track = db.get_track(1, app_module.DB_PATH)
    latest = db.get_latest_plan(track["id"], app_module.DB_PATH)
    matching = [step for step in latest["steps"] if step["item_id"] == "rag-chunking-strategies"]
    assert len(matching) == 1


def test_explore_open_returns_404_for_nonexistent_item(client):
    response = client.post("/explore/open/does-not-exist")
    assert response.status_code == 404


def test_explore_open_redirects_to_login_when_not_authenticated(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    with TestClient(app_module.app) as anon_client:
        response = anon_client.post(
            "/explore/open/rag-fundamentals", follow_redirects=False
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
