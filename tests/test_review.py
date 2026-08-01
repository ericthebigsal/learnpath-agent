from datetime import datetime, timedelta, timezone

import db
import review


def _backdate(db_path, item_id, when):
    conn = db._connect(db_path)
    conn.execute(
        "UPDATE progress SET completed_at = ? "
        "WHERE item_id = ? AND id = (SELECT MAX(id) FROM progress WHERE item_id = ?)",
        (when.isoformat(), item_id, item_id),
    )
    conn.commit()
    conn.close()


def test_weak_score_is_due_after_one_day(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 50.0, db_path)
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=2))

    due = review.get_due_items(user["id"], db_path)

    assert any(entry["item_id"] == "rag-fundamentals" for entry in due)


def test_weak_score_not_yet_due_before_one_day(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 50.0, db_path)

    assert review.get_due_items(user["id"], db_path) == []


def test_mastered_item_due_after_seven_days(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=8))

    due = review.get_due_items(user["id"], db_path)

    assert any(entry["item_id"] == "rag-fundamentals" for entry in due)


def test_mastered_item_not_due_before_seven_days(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=3))

    assert review.get_due_items(user["id"], db_path) == []


def test_mastered_item_second_completion_uses_thirty_day_interval(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=10))

    # 10 days since the 2nd completion isn't enough for the 30-day interval
    assert review.get_due_items(user["id"], db_path) == []


def test_mastered_item_caps_at_ninety_days_after_third_completion(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    for _ in range(4):
        db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=40))

    # 4th completion caps at n=3 -> 90-day interval; 40 days isn't enough
    assert review.get_due_items(user["id"], db_path) == []


def test_item_never_completed_never_appears(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)

    assert review.get_due_items(user["id"], db_path) == []


def test_due_items_sorted_most_overdue_first(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 50.0, db_path)
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=10))
    db.record_progress(track["id"], "rag-vector-databases", 50.0, db_path)
    _backdate(db_path, "rag-vector-databases", datetime.now(timezone.utc) - timedelta(days=3))

    due = review.get_due_items(user["id"], db_path)

    assert [entry["item_id"] for entry in due] == ["rag-fundamentals", "rag-vector-databases"]
