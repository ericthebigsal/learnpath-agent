# tests/test_db.py
import pytest

import db


def test_init_db_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise on a second call


def test_create_and_get_user(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)

    user = db.create_user("eric@example.com", "hashed-password", db_path)

    assert user["email"] == "eric@example.com"
    assert user["password_hash"] == "hashed-password"
    assert user["default_starting_level"] == "beginner"
    assert isinstance(user["id"], int)

    fetched = db.get_user(user["id"], db_path)
    assert fetched == user

    assert db.get_user(9999, db_path) is None


def test_get_user_by_email_finds_and_misses(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.create_user("eric@example.com", "hashed-password", db_path)

    found = db.get_user_by_email("eric@example.com", db_path)
    assert found is not None
    assert found["email"] == "eric@example.com"

    assert db.get_user_by_email("nobody@example.com", db_path) is None


def test_create_user_rejects_duplicate_email(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.create_user("eric@example.com", "hash-one", db_path)

    with pytest.raises(db.DuplicateEmailError):
        db.create_user("eric@example.com", "hash-two", db_path)


def test_create_user_normalizes_email_case_for_duplicate_detection(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.create_user("A@Example.com", "hash-one", db_path)

    with pytest.raises(db.DuplicateEmailError):
        db.create_user("a@example.com", "hash-two", db_path)


def test_get_user_by_email_is_case_and_whitespace_insensitive(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.create_user("Eric@Example.com", "hashed-password", db_path)

    found = db.get_user_by_email("eric@example.com", db_path)
    assert found is not None
    assert found["email"] == "eric@example.com"

    found_with_whitespace = db.get_user_by_email("  eric@example.com  ", db_path)
    assert found_with_whitespace is not None
    assert found_with_whitespace["email"] == "eric@example.com"


def test_update_default_starting_level(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)

    db.update_default_starting_level(user["id"], "advanced", db_path)

    updated = db.get_user(user["id"], db_path)
    assert updated["default_starting_level"] == "advanced"


def test_create_and_get_session_with_user(tmp_path):
    from datetime import datetime, timedelta, timezone

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    db.create_session("a-token", user["id"], expires_at, db_path)

    result = db.get_session_with_user("a-token", db_path)
    assert result is not None
    assert result["email"] == "eric@example.com"

    assert db.get_session_with_user("no-such-token", db_path) is None


def test_delete_session_removes_it(tmp_path):
    from datetime import datetime, timedelta, timezone

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    db.create_session("a-token", user["id"], expires_at, db_path)

    db.delete_session("a-token", db_path)

    assert db.get_session_with_user("a-token", db_path) is None


def test_create_and_get_track(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)

    track = db.create_track(user["id"], "Learn RAG", "Learn RAG basics", "beginner", db_path)

    assert track["user_id"] == user["id"]
    assert track["name"] == "Learn RAG"
    assert track["goal_text"] == "Learn RAG basics"
    assert track["starting_level"] == "beginner"

    fetched = db.get_track(track["id"], db_path)
    assert fetched == track
    assert db.get_track(9999, db_path) is None


def test_get_tracks_for_user_returns_only_that_users_tracks(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user_a = db.create_user("a@example.com", "hash-a", db_path)
    user_b = db.create_user("b@example.com", "hash-b", db_path)

    db.create_track(user_a["id"], "A's track", "Learn RAG", "beginner", db_path)
    db.create_track(user_b["id"], "B's track", "Learn agents", "beginner", db_path)

    a_tracks = db.get_tracks_for_user(user_a["id"], db_path)
    assert len(a_tracks) == 1
    assert a_tracks[0]["name"] == "A's track"


def test_record_and_get_progress_keyed_by_track(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG basics", "beginner", db_path)

    db.record_progress(track["id"], "rag-fundamentals", 85.0, db_path)
    db.record_progress(track["id"], "rag-chunking-strategies", 60.0, db_path)

    progress = db.get_progress(track["id"], db_path)

    assert len(progress) == 2
    assert progress[0]["item_id"] == "rag-fundamentals"
    assert progress[0]["quiz_score"] == 85.0


def test_log_plan_and_get_latest_plan_keyed_by_track(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG basics", "beginner", db_path)

    plan = {
        "steps": [{"item_id": "rag-fundamentals", "rationale": "Matches your goal."}],
        "summary": "Start with RAG fundamentals.",
        "candidate_ids": ["rag-fundamentals"],
    }
    logged = db.log_plan(track["id"], plan, "initial", db_path)

    assert logged["trigger"] == "initial"
    assert logged["steps"] == plan["steps"]
    assert logged["summary"] == plan["summary"]

    latest = db.get_latest_plan(track["id"], db_path)
    assert latest["steps"] == plan["steps"]


def test_get_latest_plan_returns_none_for_a_track_with_no_logged_plan(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG basics", "beginner", db_path)

    assert db.get_latest_plan(track["id"], db_path) is None


def test_get_plan_log_returns_all_plans_in_order(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG basics", "beginner", db_path)

    db.log_plan(track["id"], {"steps": [], "summary": "first", "candidate_ids": []}, "initial", db_path)
    db.log_plan(track["id"], {"steps": [], "summary": "second", "candidate_ids": []}, "quiz_result", db_path)

    log = db.get_plan_log(track["id"], db_path)

    assert [entry["summary"] for entry in log] == ["first", "second"]


def test_insert_badge_returns_true_when_newly_earned(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)

    inserted = db.insert_badge(
        user["id"], "first_beginner_course", "2026-08-01T00:00:00+00:00", db_path=db_path
    )

    assert inserted is True
    rows = db.get_badges_for_user(user["id"], db_path)
    assert len(rows) == 1
    assert rows[0]["badge_type"] == "first_beginner_course"
    assert rows[0]["track_id"] == 0
    assert rows[0]["earned_at"] == "2026-08-01T00:00:00+00:00"


def test_insert_badge_is_idempotent_for_same_user_type_and_track(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)

    first = db.insert_badge(
        user["id"], "perfectionist", "2026-08-01T00:00:00+00:00", db_path=db_path
    )
    second = db.insert_badge(
        user["id"], "perfectionist", "2026-08-02T00:00:00+00:00", db_path=db_path
    )

    assert first is True
    assert second is False
    rows = db.get_badges_for_user(user["id"], db_path)
    assert len(rows) == 1
    assert rows[0]["earned_at"] == "2026-08-01T00:00:00+00:00"  # never overwritten


def test_insert_badge_allows_same_type_for_different_tracks(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)

    db.insert_badge(
        user["id"], "track_master", "2026-08-01T00:00:00+00:00", track_id=1, db_path=db_path
    )
    db.insert_badge(
        user["id"], "track_master", "2026-08-02T00:00:00+00:00", track_id=2, db_path=db_path
    )

    rows = db.get_badges_for_user(user["id"], db_path)
    assert len(rows) == 2


def test_get_badges_for_user_returns_only_that_users_badges(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user_a = db.create_user("a@example.com", "hash-a", db_path)
    user_b = db.create_user("b@example.com", "hash-b", db_path)

    db.insert_badge(user_a["id"], "first_beginner_course", "2026-08-01T00:00:00+00:00", db_path=db_path)
    db.insert_badge(user_b["id"], "first_beginner_course", "2026-08-01T00:00:00+00:00", db_path=db_path)

    a_rows = db.get_badges_for_user(user_a["id"], db_path)
    assert len(a_rows) == 1
