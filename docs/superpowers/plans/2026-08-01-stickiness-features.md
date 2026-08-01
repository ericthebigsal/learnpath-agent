# Stickiness Features (Badges + Review Widget) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted badge/achievement system (8 badge types) and a passive spaced-repetition "due for review" dashboard widget, per `docs/superpowers/specs/2026-08-01-stickiness-features-design.md`.

**Architecture:** Two new modules (`badges.py`, `review.py`) built entirely on existing `progress`/`tracks`/`plan_log` data, plus one new table (`badges`). Badge evaluation runs synchronously right after the two existing completion-event routes; review scheduling is computed live on every dashboard load, nothing persisted.

**Tech Stack:** Same as the rest of the app — FastAPI routes, Jinja2 templates, raw `sqlite3` via `db.py`, Pydantic models. No new dependencies.

## Global Constraints

- `quiz_score` is stored on a 0-100 scale (`quiz.py:grade_quiz`), not 0-1. All thresholds use that scale.
- No streaks, no daily-login mechanics, no loss-aversion design.
- No outbound notifications exist or are added — the review widget is passive, visible only on a dashboard load the user initiates themselves.
- `badges.track_id` uses `0` as a sentinel for user-level (non-track-scoped) badges, **never `NULL`** — SQLite's `UNIQUE` constraint treats every `NULL` as distinct from every other `NULL`, which would silently defeat the uniqueness check.
- All DB access goes through `db.py` functions — never inline SQL in `app.py`, `badges.py`, or `review.py`.
- Test command for this project: `pytest -v` (or scoped to one file, e.g. `pytest tests/test_badges.py -v`). No API key needed; nothing in this feature touches the Gemini client.
- Use plain double-hyphens (` -- `) for parenthetical dashes in any new user-facing copy (badge descriptions, template text) — not em-dashes, per this codebase's established convention.
- Reference catalog item IDs used throughout this plan and its tests are real, existing entries in `data/catalog.json`: `rag-fundamentals` (level: beginner, track: RAG), `rag-vector-databases` (level: intermediate, track: RAG), `rag-hybrid-search-reranking` (level: advanced, track: RAG).

---

## File Structure

- **`db.py`** (modify) — add the `badges` table to `SCHEMA`; add `insert_badge()` and `get_badges_for_user()`.
- **`badges.py`** (create) — badge catalog (`BADGE_INFO`), the `AD_HOC_TRACK_NAME` constant, `evaluate_badges()` (checks all 8 conditions, persists newly-earned ones), and `describe_badges()` (builds display rows for the achievements page).
- **`review.py`** (create) — `get_due_items()`, the spaced-repetition scheduling algorithm.
- **`app.py`** (modify) — wire `badges.evaluate_badges()` into `submit_quiz` and `explore_open_item`; extend the dashboard route with badge/review context; add the `/achievements` route.
- **`templates/dashboard.html`** (modify) — badges strip + "due for review" list.
- **`templates/achievements.html`** (create) — full badge grid, earned + locked.
- **`templates/base.html`** (modify) — nav link to `/achievements`.
- **`static/style.css`** (modify) — `.achievement-*` and `.review-widget*` rules.
- **`tests/test_db.py`** (modify) — tests for `insert_badge`/`get_badges_for_user`.
- **`tests/test_badges.py`** (create) — tests for every badge condition, idempotency, and `describe_badges`.
- **`tests/test_review.py`** (create) — tests for the scheduling algorithm.
- **`tests/test_app.py`** (modify) — integration tests for the dashboard additions and `/achievements`.

---

## Task 1: `badges` table + DB functions

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `db.insert_badge(user_id: int, badge_type: str, earned_at: str, track_id: int = 0, db_path: str = DEFAULT_DB_PATH) -> bool` (returns `True` if newly inserted, `False` if it already existed)
- Produces: `db.get_badges_for_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]` (each dict has `id`, `user_id`, `badge_type`, `track_id`, `earned_at`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `AttributeError: module 'db' has no attribute 'insert_badge'`

- [ ] **Step 3: Add the `badges` table to `SCHEMA`**

In `db.py`, add this table to the `SCHEMA` string, immediately after the `plan_log` table definition (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge_type TEXT NOT NULL,
    track_id INTEGER NOT NULL DEFAULT 0,
    earned_at TEXT NOT NULL,
    UNIQUE(user_id, badge_type, track_id)
);
```

- [ ] **Step 4: Implement `insert_badge` and `get_badges_for_user`**

Append to `db.py`, after the `# ---------- plans ----------` section:

```python
# ---------- badges ----------

def insert_badge(
    user_id: int,
    badge_type: str,
    earned_at: str,
    track_id: int = 0,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO badges (user_id, badge_type, track_id, earned_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, badge_type, track_id, earned_at),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def get_badges_for_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM badges WHERE user_id = ? ORDER BY earned_at ASC", (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add badges table and insert/get db functions"
```

---

## Task 2: `badges.py` — evaluation and display logic

**Files:**
- Create: `badges.py`
- Test: `tests/test_badges.py`

**Interfaces:**
- Consumes: `db.get_tracks_for_user`, `db.get_progress`, `db.get_plan_log`, `db.get_latest_plan`, `db.insert_badge`, `db.get_badges_for_user` (Task 1); `catalog.get_item`; `models.Level`
- Produces: `badges.AD_HOC_TRACK_NAME: str`, `badges.BADGE_INFO: dict[str, tuple[str, str]]` (badge_type -> (label, description)), `badges.evaluate_badges(user_id: int, catalog: Catalog, db_path: str) -> list[str]` (returns newly-earned badge_types), `badges.describe_badges(user_id: int, db_path: str) -> list[dict]` (each dict has `label`, `description`, `earned`, `earned_at`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_badges.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_badges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badges'`

- [ ] **Step 3: Implement `badges.py`**

Create `badges.py`:

```python
from datetime import datetime, timedelta

import db
from catalog import get_item
from models import Level

AD_HOC_TRACK_NAME = "Ad Hoc"

WELCOME_BACK_GAP_DAYS = 14

BADGE_INFO = {
    "first_beginner_course": ("First Steps", "Complete your first beginner course."),
    "first_intermediate_course": ("Deeper Dive", "Complete your first intermediate course."),
    "first_advanced_course": ("Expert Track", "Complete your first advanced course."),
    "first_custom_path": ("Own Path", "Complete a course you opened yourself from Explore."),
    "track_master": ("Track Master", "Complete every course in one of your tracks."),
    "perfectionist": ("Perfectionist", "Score 100% on a quiz."),
    "explorer": ("Explorer", "Open a course directly from Explore for the first time."),
    "welcome_back": ("Welcome Back", "Complete a course after being away for 14+ days."),
}


def _progress_with_tracks(user_id: int, db_path: str) -> list[dict]:
    tracks = db.get_tracks_for_user(user_id, db_path)
    rows = []
    for track in tracks:
        for entry in db.get_progress(track["id"], db_path):
            entry = dict(entry)
            entry["track"] = track
            rows.append(entry)
    rows.sort(key=lambda r: r["id"])
    return rows


def _award_first_by_level(user_id, rows, catalog, level, badge_type, db_path):
    for row in rows:
        item = get_item(catalog, row["item_id"])
        if item.level == level:
            if db.insert_badge(user_id, badge_type, row["completed_at"], db_path=db_path):
                return badge_type
            break
    return None


def _award_first_custom_path(user_id, rows, db_path):
    for row in rows:
        if row["track"]["name"] == AD_HOC_TRACK_NAME:
            if db.insert_badge(user_id, "first_custom_path", row["completed_at"], db_path=db_path):
                return "first_custom_path"
            break
    return None


def _award_track_master(user_id, tracks, db_path):
    newly_earned = []
    for track in tracks:
        latest_plan = db.get_latest_plan(track["id"], db_path)
        if not latest_plan or not latest_plan["steps"]:
            continue
        required_ids = {step["item_id"] for step in latest_plan["steps"]}
        completed_by_id = {}
        for entry in db.get_progress(track["id"], db_path):
            completed_by_id.setdefault(entry["item_id"], entry["completed_at"])
        if required_ids.issubset(completed_by_id):
            earned_at = max(completed_by_id[item_id] for item_id in required_ids)
            if db.insert_badge(
                user_id, "track_master", earned_at, track_id=track["id"], db_path=db_path
            ):
                newly_earned.append("track_master")
    return newly_earned


def _award_perfectionist(user_id, rows, db_path):
    for row in rows:
        if row["quiz_score"] == 100.0:
            if db.insert_badge(user_id, "perfectionist", row["completed_at"], db_path=db_path):
                return "perfectionist"
            break
    return None


def _award_explorer(user_id, tracks, db_path):
    explore_opens = []
    for track in tracks:
        for entry in db.get_plan_log(track["id"], db_path):
            if entry["trigger"] == "explore_open":
                explore_opens.append(entry)
    if not explore_opens:
        return None
    explore_opens.sort(key=lambda e: e["id"])
    first = explore_opens[0]
    if db.insert_badge(user_id, "explorer", first["created_at"], db_path=db_path):
        return "explorer"
    return None


def _award_welcome_back(user_id, rows, db_path):
    gap = timedelta(days=WELCOME_BACK_GAP_DAYS)
    for previous, current in zip(rows, rows[1:]):
        previous_time = datetime.fromisoformat(previous["completed_at"])
        current_time = datetime.fromisoformat(current["completed_at"])
        if current_time - previous_time >= gap:
            if db.insert_badge(user_id, "welcome_back", current["completed_at"], db_path=db_path):
                return "welcome_back"
            break
    return None


def evaluate_badges(user_id: int, catalog, db_path: str) -> list[str]:
    tracks = db.get_tracks_for_user(user_id, db_path)
    rows = _progress_with_tracks(user_id, db_path)

    newly_earned = []
    for level, badge_type in (
        (Level.BEGINNER, "first_beginner_course"),
        (Level.INTERMEDIATE, "first_intermediate_course"),
        (Level.ADVANCED, "first_advanced_course"),
    ):
        result = _award_first_by_level(user_id, rows, catalog, level, badge_type, db_path)
        if result:
            newly_earned.append(result)

    result = _award_first_custom_path(user_id, rows, db_path)
    if result:
        newly_earned.append(result)

    newly_earned.extend(_award_track_master(user_id, tracks, db_path))

    result = _award_perfectionist(user_id, rows, db_path)
    if result:
        newly_earned.append(result)

    result = _award_explorer(user_id, tracks, db_path)
    if result:
        newly_earned.append(result)

    result = _award_welcome_back(user_id, rows, db_path)
    if result:
        newly_earned.append(result)

    return newly_earned


def _format_date(iso_string: str) -> str:
    return datetime.fromisoformat(iso_string).strftime("%b %d, %Y")


def describe_badges(user_id: int, db_path: str) -> list[dict]:
    earned = db.get_badges_for_user(user_id, db_path)
    earned_by_type: dict[str, list[dict]] = {}
    for row in earned:
        earned_by_type.setdefault(row["badge_type"], []).append(row)

    tracks = db.get_tracks_for_user(user_id, db_path)
    track_names = {track["id"]: track["name"] for track in tracks}

    rows = []
    for badge_type, (label, description) in BADGE_INFO.items():
        matches = earned_by_type.get(badge_type, [])
        if badge_type == "track_master":
            earned_track_ids = {row["track_id"] for row in matches}
            for row in matches:
                rows.append({
                    "label": f"{label}: {track_names.get(row['track_id'], 'Unknown track')}",
                    "description": description,
                    "earned": True,
                    "earned_at": _format_date(row["earned_at"]),
                })
            for track in tracks:
                if track["id"] not in earned_track_ids:
                    rows.append({
                        "label": f"{label}: {track['name']}",
                        "description": description,
                        "earned": False,
                        "earned_at": None,
                    })
        elif matches:
            rows.append({
                "label": label,
                "description": description,
                "earned": True,
                "earned_at": _format_date(matches[0]["earned_at"]),
            })
        else:
            rows.append({"label": label, "description": description, "earned": False, "earned_at": None})

    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_badges.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add badges.py tests/test_badges.py
git commit -m "feat: add badge evaluation and display logic"
```

---

## Task 3: `review.py` — spaced-repetition scheduling

**Files:**
- Create: `review.py`
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: `db.get_tracks_for_user`, `db.get_progress` (existing)
- Produces: `review.get_due_items(user_id: int, db_path: str) -> list[dict]` — each dict has `item_id`, `track_id`, `next_due` (`datetime`), `days_overdue` (`float`), sorted most-overdue first

- [ ] **Step 1: Write the failing tests**

Create `tests/test_review.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'review'`

- [ ] **Step 3: Implement `review.py`**

Create `review.py`:

```python
from datetime import datetime, timedelta, timezone

import db

WEAK_SCORE_THRESHOLD = 70.0
WEAK_REVIEW_DELAY_DAYS = 1
MASTERED_LADDER_DAYS = [7, 30, 90]


def get_due_items(user_id: int, db_path: str) -> list[dict]:
    tracks = db.get_tracks_for_user(user_id, db_path)

    by_item: dict[str, list[dict]] = {}
    for track in tracks:
        for entry in db.get_progress(track["id"], db_path):
            entry = dict(entry)
            entry["track_id"] = track["id"]
            by_item.setdefault(entry["item_id"], []).append(entry)

    now = datetime.now(timezone.utc)
    due = []
    for item_id, entries in by_item.items():
        entries.sort(key=lambda e: e["id"])
        n = min(len(entries), 3)
        latest = entries[-1]
        latest_completed_at = datetime.fromisoformat(latest["completed_at"])
        if latest["quiz_score"] < WEAK_SCORE_THRESHOLD:
            interval_days = WEAK_REVIEW_DELAY_DAYS
        else:
            interval_days = MASTERED_LADDER_DAYS[n - 1]
        next_due = latest_completed_at + timedelta(days=interval_days)
        if next_due <= now:
            due.append({
                "item_id": item_id,
                "track_id": latest["track_id"],
                "next_due": next_due,
                "days_overdue": (now - next_due).total_seconds() / 86400,
            })

    due.sort(key=lambda d: d["days_overdue"], reverse=True)
    return due
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_review.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add review.py tests/test_review.py
git commit -m "feat: add spaced-repetition review scheduling"
```

---

## Task 4: Wire into `app.py`, templates, and CSS

**Files:**
- Modify: `app.py`
- Modify: `templates/dashboard.html`
- Create: `templates/achievements.html`
- Modify: `templates/base.html`
- Modify: `static/style.css`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `badges.evaluate_badges`, `badges.BADGE_INFO`, `badges.describe_badges` (Task 2); `review.get_due_items` (Task 3)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_dashboard_shows_earned_badges(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )
    client.post(
        "/item/1/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "First Steps" in response.text
    assert "Perfectionist" in response.text


def test_dashboard_shows_due_for_review_item(client):
    from datetime import datetime, timedelta, timezone

    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )
    client.post(
        "/item/1/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )
    backdated = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    conn = db._connect(app_module.DB_PATH)
    conn.execute(
        "UPDATE progress SET completed_at = ? WHERE item_id = 'rag-fundamentals'", (backdated,)
    )
    conn.commit()
    conn.close()

    response = client.get("/")

    assert response.status_code == 200
    assert "Due for review" in response.text
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text


def test_achievements_page_lists_locked_badges_before_any_completion(client):
    response = client.get("/achievements")

    assert response.status_code == 200
    assert "First Steps" in response.text
    assert "Perfectionist" in response.text


def test_achievements_page_shows_earned_date_after_completion(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )
    client.post(
        "/item/1/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )

    response = client.get("/achievements")

    assert response.status_code == 200
    assert "Earned " in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v -k "badges or due_for_review or achievements"`
Expected: FAIL (`/achievements` 404s; dashboard has no badge/review context yet)

- [ ] **Step 3: Wire badge evaluation and dashboard/achievements routes into `app.py`**

Add near the top of `app.py`, with the other project imports (after `import quiz as quiz_module`):

```python
import badges
import review
```

Replace the existing line in `app.py`:

```python
AD_HOC_TRACK_NAME = "Ad Hoc"
```

with:

```python
AD_HOC_TRACK_NAME = badges.AD_HOC_TRACK_NAME
```

In `submit_quiz`, immediately after the existing `db.record_progress(track_id, item_id, score, DB_PATH)` line, add:

```python
    badges.evaluate_badges(current_user["id"], CATALOG, DB_PATH)
```

In `explore_open_item`, immediately after the existing `_add_item_to_plan(track["id"], item_id, "explore_open", "Opened directly from the catalog.")` line, add:

```python
    badges.evaluate_badges(current_user["id"], CATALOG, DB_PATH)
```

Replace the existing `dashboard` route:

```python
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    tracks = db.get_tracks_for_user(current_user["id"], DB_PATH)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "tracks": tracks,
            "levels": [level.value for level in Level],
            "default_level": current_user["default_starting_level"],
        },
    )
```

with:

```python
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    tracks = db.get_tracks_for_user(current_user["id"], DB_PATH)
    earned_badges = db.get_badges_for_user(current_user["id"], DB_PATH)
    earned_labels = sorted({badges.BADGE_INFO[row["badge_type"]][0] for row in earned_badges})
    due_items = review.get_due_items(current_user["id"], DB_PATH)[:5]
    due_for_review = [
        {"item": get_item(CATALOG, entry["item_id"]), "track_id": entry["track_id"]}
        for entry in due_items
    ]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "tracks": tracks,
            "levels": [level.value for level in Level],
            "default_level": current_user["default_starting_level"],
            "earned_labels": earned_labels,
            "due_for_review": due_for_review,
        },
    )
```

Add a new route, placed directly after the `dashboard` route:

```python
@app.get("/achievements", response_class=HTMLResponse)
def achievements(request: Request, current_user: dict = Depends(get_current_user)):
    badge_rows = badges.describe_badges(current_user["id"], DB_PATH)
    return templates.TemplateResponse(
        request,
        "achievements.html",
        {"request": request, "current_user": current_user, "badges": badge_rows},
    )
```

- [ ] **Step 4: Update `templates/dashboard.html`**

Insert this block into `templates/dashboard.html`, immediately after the closing `{% endif %}` of the existing tracks `<ul>` block (i.e. right before `<h2>Start a new track</h2>`):

```html
{% if earned_labels %}
<div class="achievement-strip">
  <p class="achievement-strip-label">Badges earned</p>
  {% for label in earned_labels %}
  <span class="achievement-pill">{{ label }}</span>
  {% endfor %}
  <a class="achievement-strip-link" href="/achievements">View all &rarr;</a>
</div>
{% endif %}

{% if due_for_review %}
<div class="review-widget">
  <p class="review-widget-label">Due for review</p>
  <ul class="review-widget-list">
    {% for entry in due_for_review %}
    <li><a href="/item/{{ entry.track_id }}/{{ entry.item.id }}">{{ entry.item.title }}</a></li>
    {% endfor %}
  </ul>
</div>
{% endif %}
```

- [ ] **Step 5: Create `templates/achievements.html`**

```html
{% extends "base.html" %}
{% block title %}Achievements — learnpath-agent{% endblock %}
{% block content %}
<p class="eyebrow">Registrar</p>
<h1>Achievements</h1>

{% if badges %}
<ul class="achievement-grid">
  {% for badge in badges %}
  <li class="achievement-card {% if badge.earned %}achievement-card-earned{% else %}achievement-card-locked{% endif %}">
    <p class="achievement-card-label">{{ badge.label }}</p>
    <p class="achievement-card-description">{{ badge.description }}</p>
    {% if badge.earned %}
    <p class="achievement-card-date">Earned {{ badge.earned_at }}</p>
    {% endif %}
  </li>
  {% endfor %}
</ul>
{% else %}
<p class="empty-state">No badges yet -- complete a course to start earning them.</p>
{% endif %}

<p class="path-footer">
  <a href="/">Back to your dashboard</a>
</p>
{% endblock %}
```

- [ ] **Step 6: Add the nav link in `templates/base.html`**

In `templates/base.html`, change:

```html
      <a class="nav-link" href="/explore">Explore</a>
```

to:

```html
      <a class="nav-link" href="/explore">Explore</a>
      <a class="nav-link" href="/achievements">Achievements</a>
```

- [ ] **Step 7: Add CSS rules to `static/style.css`**

Append to `static/style.css`:

```css
/* ---------- achievements ---------- */

.achievement-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin: 1.5rem 0;
}

.achievement-strip-label {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--ink-muted);
  margin: 0 0.75rem 0 0;
  flex-basis: 100%;
}

.achievement-pill {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  background: var(--taken-tint);
  border: 1px solid var(--taken-border);
  color: var(--taken);
}

.achievement-strip-link {
  margin-left: auto;
  font-size: 0.9rem;
}

.review-widget {
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin: 1.5rem 0;
}

.review-widget-label {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--ink-muted);
  margin: 0 0 0.5rem;
}

.review-widget-list { margin: 0; padding-left: 1.1rem; }
.review-widget-list li { margin-bottom: 0.3rem; }

.achievement-grid {
  list-style: none;
  margin: 1.5rem 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
}

.achievement-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.25rem;
}

.achievement-card-earned {
  background: var(--taken-tint);
  border-color: var(--taken-border);
}

.achievement-card-locked { opacity: 0.55; }

.achievement-card-label {
  font-family: var(--font-display);
  font-weight: 600;
  margin: 0 0 0.35rem;
}

.achievement-card-description {
  color: var(--ink-muted);
  font-size: 0.92rem;
  margin: 0 0 0.5rem;
}

.achievement-card-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--taken);
  margin: 0;
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v -k "badges or due_for_review or achievements"`
Expected: PASS

- [ ] **Step 9: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tests, including the pre-existing suite)

- [ ] **Step 10: Commit**

```bash
git add app.py templates/dashboard.html templates/achievements.html templates/base.html static/style.css tests/test_app.py
git commit -m "feat: wire badges and review widget into dashboard and new achievements page"
```

---

## Self-Review Notes

- **Spec coverage:** all 8 badge types, the review-scheduling algorithm (weak override + 7/30/90 ladder), dashboard display, and the `/achievements` page are each covered by a task.
- **Placeholder scan:** no TBD/TODO markers; every step has complete, runnable code.
- **Type consistency:** `evaluate_badges(user_id: int, catalog, db_path: str) -> list[str]` and `describe_badges(user_id: int, db_path: str) -> list[dict]` signatures are identical between their definition (Task 2) and every call site (Task 4). `get_due_items(user_id: int, db_path: str) -> list[dict]` likewise matches between Task 3 and Task 4.
- Task 1 must land before Tasks 2 and 3 (both depend on `db.insert_badge`/`get_badges_for_user`); Tasks 2 and 3 are independent of each other; Task 4 depends on both.
