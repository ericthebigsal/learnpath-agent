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


def test_due_items_uses_latest_by_id_across_merged_tracks(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track_a = db.create_track(user["id"], "Track A", "Learn RAG", "beginner", db_path)
    track_b = db.create_track(user["id"], "Track B", "Learn RAG", "beginner", db_path)

    # Same item_id completed under two different tracks: track A first, then track B --
    # so track B's progress row has a higher id (it was created later) even though the two
    # rows live in different tracks. db.get_progress only guarantees id-order *within* a
    # single track; get_due_items has to merge rows for this item_id across both tracks, so
    # picking the "latest" row correctly depends on sorting the merged list by id.
    db.record_progress(track_a["id"], "rag-fundamentals", 90.0, db_path)
    db.record_progress(track_b["id"], "rag-fundamentals", 90.0, db_path)

    # Leave track A's row's completed_at as "now" (fresh), and backdate track B's (the
    # later/higher-id) row far enough in the past that the 2nd-completion interval (n=2 ->
    # 30-day rung) has clearly elapsed. This is deliberately the opposite of what a
    # completed_at-based (rather than id-based) "latest" pick would assume.
    _backdate(db_path, "rag-fundamentals", datetime.now(timezone.utc) - timedelta(days=35))

    due = review.get_due_items(user["id"], db_path)
    matches = [entry for entry in due if entry["item_id"] == "rag-fundamentals"]

    # If the merge incorrectly picked track A's row as "latest" (e.g. by using the row with
    # the most recent completed_at, or by track creation/iteration order instead of id),
    # next_due would be computed from track A's "now" timestamp and land ~30 days in the
    # future -- so the item would wrongly NOT be due yet.
    assert len(matches) == 1
    # And if the wrong row were picked, this would report track A's id instead of track B's --
    # proving the merge correctly identifies the truly-latest row (track B's, by id) across
    # all of the user's tracks, not just the first/last track iterated.
    assert matches[0]["track_id"] == track_b["id"]


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
