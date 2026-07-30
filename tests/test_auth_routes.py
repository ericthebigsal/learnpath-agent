import pytest
from fastapi.testclient import TestClient

import app as app_module
import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)
    with TestClient(app_module.app) as test_client:
        yield test_client


def test_register_page_renders_form(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert "email" in response.text
    assert "password" in response.text


def test_registering_creates_user_and_logs_in(client):
    response = client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "session_token" in response.cookies

    user = db.get_user_by_email("eric@example.com", app_module.DB_PATH)
    assert user is not None
    assert user["password_hash"] != "hunter2"


def test_registering_with_mismatched_passwords_shows_error(client):
    response = client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "different"},
    )

    assert response.status_code == 200
    assert "match" in response.text.lower()
    assert db.get_user_by_email("eric@example.com", app_module.DB_PATH) is None


def test_registering_duplicate_email_shows_error(client):
    client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
    )

    response = client.post(
        "/register",
        data={"email": "eric@example.com", "password": "different", "confirm_password": "different"},
    )

    assert response.status_code == 200
    assert "already" in response.text.lower()


def test_login_with_correct_password_succeeds(client):
    client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
    )
    client.cookies.clear()

    response = client.post(
        "/login", data={"email": "eric@example.com", "password": "hunter2"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert "session_token" in response.cookies


def test_login_with_wrong_password_shows_generic_error(client):
    client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
    )
    client.cookies.clear()

    response = client.post("/login", data={"email": "eric@example.com", "password": "wrong"})

    assert response.status_code == 200
    assert "incorrect" in response.text.lower()


def test_login_with_unknown_email_shows_the_same_generic_error(client):
    response = client.post("/login", data={"email": "nobody@example.com", "password": "whatever"})

    assert response.status_code == 200
    assert "incorrect" in response.text.lower()


def test_login_sets_a_persistent_session_cookie(client):
    client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
    )
    client.cookies.clear()

    response = client.post(
        "/login", data={"email": "eric@example.com", "password": "hunter2"}, follow_redirects=False
    )

    assert "max-age=" in response.headers["set-cookie"].lower()


def test_logout_deletes_session_and_redirects_to_login(client):
    client.post(
        "/register",
        data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
    )
    token = client.cookies.get("session_token")

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert db.get_session_with_user(token, app_module.DB_PATH) is None
