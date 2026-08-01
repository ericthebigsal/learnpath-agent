from datetime import datetime, timedelta, timezone

import badges
import db
from catalog import load_catalog

CATALOG = load_catalog()


def test_first_beginner_course_badge(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)

    earned = badges.evaluate_badges(user["id"], CATALOG, db_path)

    assert "first_beginner_course" in earned


def test_first_intermediate_course_badge(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-vector-databases", 90.0, db_path)

    earned = badges.evaluate_badges(user["id"], CATALOG, db_path)

    assert "first_intermediate_course" in earned


def test_first_advanced_course_badge(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-hybrid-search-reranking", 90.0, db_path)

    earned = badges.evaluate_badges(user["id"], CATALOG, db_path)

    assert "first_advanced_course" in earned


def test_first_custom_path_badge_requires_ad_hoc_track(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    regular_track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(regular_track["id"], "rag-fundamentals", 90.0, db_path)

    assert "first_custom_path" not in badges.evaluate_badges(user["id"], CATALOG, db_path)

    ad_hoc_track = db.create_track(
        user["id"], badges.AD_HOC_TRACK_NAME, "Courses opened directly.", "beginner", db_path
    )
    db.record_progress(ad_hoc_track["id"], "rag-vector-databases", 90.0, db_path)

    assert "first_custom_path" in badges.evaluate_badges(user["id"], CATALOG, db_path)


def test_track_master_badge_requires_every_planned_item_completed(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    plan = {
        "steps": [
            {"item_id": "rag-fundamentals", "rationale": "first"},
            {"item_id": "rag-vector-databases", "rationale": "second"},
        ],
        "summary": "Learn RAG",
        "candidate_ids": [],
    }
    db.log_plan(track["id"], plan, "initial", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)

    assert "track_master" not in badges.evaluate_badges(user["id"], CATALOG, db_path)

    db.record_progress(track["id"], "rag-vector-databases", 90.0, db_path)

    assert "track_master" in badges.evaluate_badges(user["id"], CATALOG, db_path)


def test_track_master_badge_is_scoped_per_track(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track_a = db.create_track(user["id"], "Track A", "Learn RAG", "beginner", db_path)
    track_b = db.create_track(user["id"], "Track B", "Learn agents", "beginner", db_path)

    db.log_plan(
        track_a["id"],
        {"steps": [{"item_id": "rag-fundamentals", "rationale": "x"}], "summary": "s", "candidate_ids": []},
        "initial",
        db_path,
    )
    db.log_plan(
        track_b["id"],
        {"steps": [{"item_id": "rag-vector-databases", "rationale": "x"}], "summary": "s", "candidate_ids": []},
        "initial",
        db_path,
    )
    db.record_progress(track_a["id"], "rag-fundamentals", 90.0, db_path)

    earned = badges.evaluate_badges(user["id"], CATALOG, db_path)

    assert "track_master" in earned
    rows = [row for row in db.get_badges_for_user(user["id"], db_path) if row["badge_type"] == "track_master"]
    assert len(rows) == 1
    assert rows[0]["track_id"] == track_a["id"]


def test_perfectionist_badge_requires_a_perfect_score(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 80.0, db_path)

    assert "perfectionist" not in badges.evaluate_badges(user["id"], CATALOG, db_path)

    db.record_progress(track["id"], "rag-vector-databases", 100.0, db_path)

    assert "perfectionist" in badges.evaluate_badges(user["id"], CATALOG, db_path)


def test_explorer_badge_requires_an_explore_open_plan_log_entry(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)

    assert "explorer" not in badges.evaluate_badges(user["id"], CATALOG, db_path)

    db.log_plan(
        track["id"],
        {"steps": [{"item_id": "rag-fundamentals", "rationale": "x"}], "summary": "s", "candidate_ids": []},
        "explore_open",
        db_path,
    )

    assert "explorer" in badges.evaluate_badges(user["id"], CATALOG, db_path)


def test_welcome_back_badge_requires_a_14_day_gap_between_completions(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)

    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)
    conn = db._connect(db_path)
    conn.execute(
        "UPDATE progress SET completed_at = ? WHERE item_id = ?",
        ((datetime.now(timezone.utc) - timedelta(days=20)).isoformat(), "rag-fundamentals"),
    )
    conn.commit()
    conn.close()

    assert "welcome_back" not in badges.evaluate_badges(user["id"], CATALOG, db_path)

    db.record_progress(track["id"], "rag-vector-databases", 90.0, db_path)

    assert "welcome_back" in badges.evaluate_badges(user["id"], CATALOG, db_path)


def test_evaluate_badges_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 90.0, db_path)

    first_call = badges.evaluate_badges(user["id"], CATALOG, db_path)
    second_call = badges.evaluate_badges(user["id"], CATALOG, db_path)

    assert "first_beginner_course" in first_call
    assert second_call == []
    rows = db.get_badges_for_user(user["id"], db_path)
    assert len(rows) == 1


def test_describe_badges_shows_earned_and_locked_states(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hash", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG", "beginner", db_path)
    db.record_progress(track["id"], "rag-fundamentals", 100.0, db_path)
    badges.evaluate_badges(user["id"], CATALOG, db_path)

    rows = badges.describe_badges(user["id"], db_path)
    by_label = {row["label"]: row for row in rows}

    assert by_label["First Steps"]["earned"] is True
    assert by_label["First Steps"]["earned_at"] is not None
    assert by_label["Deeper Dive"]["earned"] is False
    assert by_label["Deeper Dive"]["earned_at"] is None
