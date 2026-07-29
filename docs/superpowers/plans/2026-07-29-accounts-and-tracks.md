# Accounts & Tracks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn learnpath-agent from an anonymous single-session demo into a persistent, multi-track personal LMS: real email+password accounts, "learners" renamed to user-owned "tracks" (a user can run several in parallel), and a dashboard replacing the old anonymous start screen.

**Architecture:** A new `auth.py` module (password hashing via bcrypt, session tokens, track-name derivation) alongside the existing flat module layout. `db.py`'s schema gains `users`/`sessions` tables and renames `learners`→`tracks` (with `user_id`/`name`) and every `learner_id` FK column to `track_id`. `app.py` gains a `get_current_user` FastAPI dependency (redirects to `/login` via a custom exception + handler, not a raw 401) and an ownership check used by every track-scoped route. `planner.py`, `catalog.py`, `quiz.py`, `models.py` are untouched — a track dict has the same shape the planner already expects (`goal_text`, `starting_level`), so the planning agent doesn't know or care that tracks now have owners.

**Tech Stack:** Adds `bcrypt` to the existing FastAPI/Jinja2/SQLite/pytest stack.

## Global Constraints

- Passwords hashed with `bcrypt`, never logged or stored in plain text.
- Session tokens: `secrets.token_urlsafe(32)`, stored in a `sessions` table, set as an httponly, `samesite=lax` cookie (not `secure`, since local dev is plain HTTP), 30-day expiry.
- `get_current_user` redirects unauthenticated requests to `/login` (a 303 redirect), not a raw 401/403 JSON error — implemented via a custom `NotAuthenticated` exception and an `@app.exception_handler`.
- Every track-scoped route (`/path/{track_id}`, `/item/{track_id}/{item_id}`, `/item/.../submit`, `/history/{track_id}`) 404s identically whether the track doesn't exist or belongs to someone else — never reveals which.
- No password reset, no email verification, no login rate-limiting, no invite codes — registration is open. All explicitly out of scope per the spec.
- No changes to `planner.py`, `catalog.py`, `quiz.py`, `models.py`, `data/catalog.json` — this plan is scoped entirely to identity/ownership around existing functionality.
- Track's `name` is auto-derived from `goal_text`: first 60 characters, truncated at the nearest word boundary, with `…` appended if truncated. No separate "name your track" UI step.
- This is a clean schema replacement (no live deployment, local gitignored SQLite file) — no migration path for old data is needed.

---

## File Structure

```
learnpath-agent/
  auth.py          # NEW: hash_password, verify_password, generate_session_token, derive_track_name, SESSION_DURATION
  db.py            # MODIFIED: users/sessions tables, learners->tracks rename, learner_id->track_id rename
  app.py           # MODIFIED: get_current_user, NotAuthenticated handler, register/login/logout/dashboard routes,
                   #           /tracks replaces /start, ownership checks on all track-scoped routes
  templates/
    base.html      # MODIFIED: header shows logout form when logged in
    register.html  # NEW
    login.html     # NEW
    dashboard.html # NEW: replaces start.html's role as the logged-out landing page
    start.html     # REMOVED (superseded by dashboard.html)
    path.html      # MODIFIED: learner_id->track_id, learner->track
    item.html      # MODIFIED: learner_id->track_id
    path_updated.html  # MODIFIED: learner_id->track_id
    history.html   # MODIFIED: learner_id->track_id
  static/style.css # MODIFIED: small additions for the logout form/link, register/login form pages
  tests/
    test_auth.py       # NEW: password hashing, session tokens, track-name derivation
    test_db.py         # MODIFIED: users/sessions CRUD, tracks (renamed) CRUD
    test_app.py        # MODIFIED: every test logs in first; /start -> /tracks; new register/login/logout/
                        #           dashboard tests; cross-user ownership test
```

---

### Task 1: `auth.py` — password hashing, session tokens, track-name derivation

**Files:**
- Create: `auth.py`
- Create: `tests/test_auth.py`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`, `generate_session_token() -> str`, `SESSION_DURATION` (a `datetime.timedelta`), `derive_track_name(goal_text: str, max_length: int = 60) -> str` — all consumed by `db.py` (Task 2) and `app.py` (Tasks 3-5).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
from datetime import timedelta

from auth import (
    SESSION_DURATION,
    derive_track_name,
    generate_session_token,
    hash_password,
    verify_password,
)


def test_hash_password_produces_a_verifiable_but_different_string():
    password = "correct horse battery staple"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("the-real-password")
    assert verify_password("a-wrong-guess", hashed) is False


def test_hash_password_is_salted_so_two_hashes_of_the_same_password_differ():
    hashed_a = hash_password("same-password")
    hashed_b = hash_password("same-password")
    assert hashed_a != hashed_b
    assert verify_password("same-password", hashed_a) is True
    assert verify_password("same-password", hashed_b) is True


def test_generate_session_token_produces_unique_url_safe_strings():
    tokens = {generate_session_token() for _ in range(20)}
    assert len(tokens) == 20
    for token in tokens:
        assert len(token) >= 32
        assert " " not in token


def test_session_duration_is_thirty_days():
    assert SESSION_DURATION == timedelta(days=30)


def test_derive_track_name_returns_short_goal_text_unchanged():
    assert derive_track_name("Learn RAG") == "Learn RAG"


def test_derive_track_name_truncates_long_goal_text_at_a_word_boundary():
    goal = "I want to understand how RAG differs from just stuffing context into a giant prompt window"
    name = derive_track_name(goal, max_length=30)

    assert len(name) <= 31  # 30 chars + the ellipsis character
    assert name.endswith("…")
    assert not name[:-1].endswith(" ")  # trimmed back to the last full word, no trailing space before the ellipsis
    assert goal.startswith(name[:-1])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 3: Implement `auth.py`**

```python
import secrets
from datetime import timedelta

import bcrypt

SESSION_DURATION = timedelta(days=30)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def derive_track_name(goal_text: str, max_length: int = 60) -> str:
    if len(goal_text) <= max_length:
        return goal_text
    truncated = goal_text[:max_length].rsplit(" ", 1)[0]
    return truncated + "…"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: 7 passed.

- [ ] **Step 5: Add `bcrypt` to `requirements.txt`**

Add this line to `requirements.txt` (after `python-multipart==0.0.12`):

```
bcrypt==4.2.0
```

Then reinstall: `pip install -r requirements.txt`

- [ ] **Step 6: Commit**

```bash
git add auth.py tests/test_auth.py requirements.txt
git commit -m "feat: add password hashing, session tokens, and track-name derivation"
```

---

### Task 2: `db.py` — users, sessions, and the learners→tracks rename

**Files:**
- Modify: `db.py`
- Modify: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing new (still stdlib `sqlite3`).
- Produces: `create_user`, `get_user_by_email`, `get_user`, `update_default_starting_level`, `create_session`, `get_session_with_user`, `delete_session`, `create_track`, `get_track`, `get_tracks_for_user`, `record_progress`/`get_progress` (now `track_id`-keyed), `log_plan`/`get_plan_log`/`get_latest_plan` (now `track_id`-keyed) — all consumed by `app.py` (Tasks 3-5).

This task **replaces** `db.py`'s entire content — every existing function is touched (renamed parameters) or added. Read the full new file below rather than trying to diff it mentally against the old one.

- [ ] **Step 1: Write the failing tests**

Replace the entire content of `tests/test_db.py` with:

```python
# tests/test_db.py
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


def test_get_plan_log_returns_all_plans_in_order(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    user = db.create_user("eric@example.com", "hashed-password", db_path)
    track = db.create_track(user["id"], "Learn RAG", "Learn RAG basics", "beginner", db_path)

    db.log_plan(track["id"], {"steps": [], "summary": "first", "candidate_ids": []}, "initial", db_path)
    db.log_plan(track["id"], {"steps": [], "summary": "second", "candidate_ids": []}, "quiz_result", db_path)

    log = db.get_plan_log(track["id"], db_path)

    assert [entry["summary"] for entry in log] == ["first", "second"]
```

Add `import pytest` at the top of `tests/test_db.py` (needed for the duplicate-email test's `pytest.raises`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'create_user'` (or similar, since none of the new functions exist yet).

- [ ] **Step 3: Replace `db.py` entirely**

```python
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "learnpath.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    default_starting_level TEXT NOT NULL DEFAULT 'beginner',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    goal_text TEXT NOT NULL,
    starting_level TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    quiz_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    trigger TEXT NOT NULL
);
"""


class DuplicateEmailError(Exception):
    pass


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------- users ----------

def create_user(email: str, password_hash: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = _connect(db_path)
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise DuplicateEmailError(f"Email already registered: {email!r}")

        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, default_starting_level, created_at) "
            "VALUES (?, ?, 'beginner', ?)",
            (email, password_hash, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_default_starting_level(
    user_id: int, starting_level: str, db_path: str = DEFAULT_DB_PATH
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE users SET default_starting_level = ? WHERE id = ?",
            (starting_level, user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- sessions ----------

def create_session(
    token: str, user_id: int, expires_at: str, db_path: str = DEFAULT_DB_PATH
) -> None:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_session_with_user(token: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT users.*, sessions.expires_at AS session_expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_session(token: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


# ---------- tracks ----------

def create_track(
    user_id: int,
    name: str,
    goal_text: str,
    starting_level: str,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO tracks (user_id, name, goal_text, starting_level, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, name, goal_text, starting_level, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tracks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_track(track_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_tracks_for_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE user_id = ? ORDER BY id ASC", (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------- progress ----------

def record_progress(
    track_id: int, item_id: str, quiz_score: float, db_path: str = DEFAULT_DB_PATH
) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO progress (track_id, item_id, completed_at, quiz_score) "
            "VALUES (?, ?, ?, ?)",
            (track_id, item_id, now, quiz_score),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM progress WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_progress(track_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM progress WHERE track_id = ? ORDER BY id ASC", (track_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------- plans ----------

def _plan_row_to_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    plan = json.loads(result.pop("plan_json"))
    result["steps"] = plan["steps"]
    result["summary"] = plan["summary"]
    result["candidate_ids"] = plan.get("candidate_ids", [])
    return result


def log_plan(track_id: int, plan: dict, trigger: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO plan_log (track_id, created_at, plan_json, trigger) "
            "VALUES (?, ?, ?, ?)",
            (track_id, now, json.dumps(plan), trigger),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM plan_log WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _plan_row_to_dict(row)
    finally:
        conn.close()


def get_plan_log(track_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM plan_log WHERE track_id = ? ORDER BY id ASC", (track_id,)
        ).fetchall()
        return [_plan_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_plan(track_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM plan_log WHERE track_id = ? ORDER BY id DESC LIMIT 1",
            (track_id,),
        ).fetchone()
        return _plan_row_to_dict(row) if row else None
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add users/sessions tables, rename learners to user-owned tracks"
```

---

### Task 3: Registration, login, and logout routes

**Files:**
- Modify: `app.py`
- Create: `templates/register.html`
- Create: `templates/login.html`
- Create: `tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `auth.hash_password`, `auth.verify_password`, `auth.generate_session_token`, `auth.SESSION_DURATION` (Task 1); `db.create_user`, `db.get_user_by_email`, `db.create_session`, `db.get_session_with_user`, `db.delete_session`, `db.DuplicateEmailError` (Task 2).
- Produces: `SESSION_COOKIE_NAME`, `NotAuthenticated` (exception class), `get_current_user` (FastAPI dependency), `GET/POST /register`, `GET/POST /login`, `POST /logout` — `get_current_user` and `NotAuthenticated` are consumed by every later task's routes.

This task only adds new routes/imports to `app.py` — it does not yet touch `start_page`, `start_learner`, `current_path`, `item_view`, `submit_quiz`, or `history_page` (those are Task 4-5's job). The app is in a transitional state after this task: old anonymous routes still work, new auth routes exist alongside them.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth_routes.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_routes.py -v`
Expected: FAIL — 404s, since `/register`/`/login`/`/logout` don't exist yet.

- [ ] **Step 3: Add auth infrastructure and routes to `app.py`**

Add these imports to the top of `app.py` (alongside the existing ones):

```python
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
```

Add this after the existing `db.init_db(DB_PATH)` line:

```python
SESSION_COOKIE_NAME = "session_token"


class NotAuthenticated(Exception):
    pass


@app.exception_handler(NotAuthenticated)
def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise NotAuthenticated()

    result = db.get_session_with_user(token, DB_PATH)
    if result is None:
        raise NotAuthenticated()

    expires_at = datetime.fromisoformat(result["session_expires_at"])
    if expires_at < datetime.now(timezone.utc):
        db.delete_session(token, DB_PATH)
        raise NotAuthenticated()

    return result
```

Add these routes (anywhere after the above, before the existing `start_page` route):

```python
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"request": request, "error": None})


@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            request, "register.html", {"request": request, "error": "Passwords don't match."}
        )

    try:
        user = db.create_user(email, auth.hash_password(password), DB_PATH)
    except db.DuplicateEmailError:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"request": request, "error": "That email is already registered."},
        )

    token = auth.generate_session_token()
    expires_at = (datetime.now(timezone.utc) + auth.SESSION_DURATION).isoformat()
    db.create_session(token, user["id"], expires_at, DB_PATH)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax")
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    user = db.get_user_by_email(email, DB_PATH)
    if user is None or not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": "That email or password is incorrect."},
        )

    token = auth.generate_session_token()
    expires_at = (datetime.now(timezone.utc) + auth.SESSION_DURATION).isoformat()
    db.create_session(token, user["id"], expires_at, DB_PATH)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout_submit(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is not None:
        db.delete_session(token, DB_PATH)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
```

- [ ] **Step 4: Create `templates/register.html`**

```html
{% extends "base.html" %}
{% block title %}Register — learnpath-agent{% endblock %}
{% block content %}
<h1>Create your account</h1>
{% if error %}<p class="form-error">{{ error }}</p>{% endif %}
<form class="goal-form" method="post" action="/register">
  <label for="email">Email</label>
  <input type="email" id="email" name="email" required>

  <label for="password">Password</label>
  <input type="password" id="password" name="password" required>

  <label for="confirm_password">Confirm password</label>
  <input type="password" id="confirm_password" name="confirm_password" required>

  <button type="submit">Create account</button>
</form>
<p><a href="/login">Already have an account? Log in.</a></p>
{% endblock %}
```

- [ ] **Step 5: Create `templates/login.html`**

```html
{% extends "base.html" %}
{% block title %}Log in — learnpath-agent{% endblock %}
{% block content %}
<h1>Log in</h1>
{% if error %}<p class="form-error">{{ error }}</p>{% endif %}
<form class="goal-form" method="post" action="/login">
  <label for="email">Email</label>
  <input type="email" id="email" name="email" required>

  <label for="password">Password</label>
  <input type="password" id="password" name="password" required>

  <button type="submit">Log in</button>
</form>
<p><a href="/register">Need an account? Register.</a></p>
{% endblock %}
```

- [ ] **Step 6: Add a small style for form-level errors to `static/style.css`**

Append:

```css
.form-error {
  background: var(--signal-tint);
  color: var(--signal);
  border: 1px solid var(--signal);
  border-radius: 8px;
  padding: 0.6rem 0.9rem;
  margin-bottom: 1.25rem;
  font-size: 0.92rem;
}
```

Also add plain `input[type="email"]`/`input[type="password"]` styling matching the existing `textarea`/`select` rule (find the `form textarea, form select {` rule and add `, form input[type="email"], form input[type="password"]` to its selector list).

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_auth_routes.py -v`
Expected: 8 passed. Then run `pytest -v` for the whole suite — the pre-existing `test_app.py` tests should still pass unchanged, since this task didn't touch `start_page`/`start_learner`/etc.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/register.html templates/login.html static/style.css tests/test_auth_routes.py
git commit -m "feat: add registration, login, and logout routes"
```

---

### Task 4: Dashboard and track creation

**Files:**
- Modify: `app.py`
- Create: `templates/dashboard.html`
- Modify: `templates/base.html`
- Remove: `templates/start.html`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `get_current_user`, `NotAuthenticated` (Task 3); `db.get_tracks_for_user`, `db.create_track`, `db.update_default_starting_level`, `auth.derive_track_name` (Tasks 1-2).
- Produces: `GET /` (dashboard, replacing `start_page`), `POST /tracks` (replacing `start_learner`) — consumed by Task 5's tests and every later track-scoped route's "create a track first" test setup.

This task removes the old anonymous `GET /`/`POST /start` routes entirely and replaces them. Track-scoped routes (`/path`, `/item`, `/history`) are NOT yet auth-protected — that's Task 5. This task only changes how tracks get created.

- [ ] **Step 1: Rewrite the top of `tests/test_app.py`**

Replace the `client` fixture and the tests that hit `/` and `/start` with:

```python
# tests/test_app.py  (top of file — fixture and dashboard/track-creation tests)
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

    def fake_compute_plan(track, progress):
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
            data={"email": "eric@example.com", "password": "hunter2", "confirm_password": "hunter2"},
        )
        yield test_client


def test_compute_plan_falls_back_when_genai_client_construction_raises(monkeypatch):
    def raise_missing_api_key():
        raise ValueError("Missing key inputs argument!")

    monkeypatch.setattr(app_module.genai, "Client", raise_missing_api_key)

    track = {"goal_text": "I want to learn about RAG", "starting_level": "beginner"}
    plan, used_fallback, candidate_ids = app_module.compute_plan(track, [])

    assert used_fallback is True
    assert len(plan.steps) > 0
    assert len(candidate_ids) > 0


def test_dashboard_redirects_to_login_when_not_authenticated(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    with TestClient(app_module.app) as anon_client:
        response = anon_client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_shows_goal_form_when_logged_in(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "goal_text" in response.text
    assert "starting_level" in response.text


def test_submitting_track_form_creates_track_and_redirects_to_path(client):
    response = client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/path/")


def test_submitting_track_form_logs_the_initial_plan_and_updates_default_level(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "intermediate"},
    )

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest is not None
    assert latest["trigger"] == "initial"
    assert latest["steps"][0]["item_id"] == "rag-fundamentals"

    user = db.get_user_by_email("eric@example.com", app_module.DB_PATH)
    assert user["default_starting_level"] == "intermediate"


def test_dashboard_lists_existing_tracks(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "I want to learn about RAG" in response.text
```

Leave every other existing test in `tests/test_app.py` (the `/path`, `/item`, `/history` ones) in place for now — Task 5 updates them.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — `/tracks` doesn't exist yet (404s), `test_dashboard_*` tests fail since `/` still serves the old anonymous form.

- [ ] **Step 3: Replace `start_page`/`start_learner` in `app.py`**

Remove the existing `start_page` and `start_learner` functions entirely, replacing them with:

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


@app.post("/tracks")
def create_track(
    goal_text: str = Form(...),
    starting_level: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    name = auth.derive_track_name(goal_text)
    track = db.create_track(current_user["id"], name, goal_text, starting_level, DB_PATH)
    db.update_default_starting_level(current_user["id"], starting_level, DB_PATH)

    plan, _used_fallback, candidate_ids = compute_plan(track, [])
    plan_dict = plan.model_dump()
    plan_dict["candidate_ids"] = candidate_ids
    db.log_plan(track["id"], plan_dict, "initial", DB_PATH)
    return RedirectResponse(url=f"/path/{track['id']}", status_code=303)
```

- [ ] **Step 4: Create `templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Dashboard — learnpath-agent{% endblock %}
{% block content %}
<p class="eyebrow">Your tracks</p>
<h1>Welcome back</h1>

{% if tracks %}
<ul class="track-list">
  {% for track in tracks %}
  <li class="track-list-item">
    <a class="track-list-name" href="/path/{{ track.id }}">{{ track.name }}</a>
    <p class="track-list-goal">{{ track.goal_text }}</p>
  </li>
  {% endfor %}
</ul>
{% endif %}

<h2>Start a new track</h2>
<form class="goal-form" method="post" action="/tracks">
  <label for="goal_text">Your goal</label>
  <textarea id="goal_text" name="goal_text" rows="3" required
    placeholder="e.g. I want to understand how RAG differs from just stuffing context"></textarea>

  <label for="starting_level">Starting level</label>
  <select id="starting_level" name="starting_level">
    {% for level in levels %}
    <option value="{{ level }}" {% if level == default_level %}selected{% endif %}>{{ level | capitalize }}</option>
    {% endfor %}
  </select>

  <button type="submit">Build my learning path</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Update `templates/base.html`'s header to show a logout form when logged in**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}learnpath-agent{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="site-header">
    <a class="site-mark" href="/">learnpath-agent</a>
    {% if current_user %}
    <form method="post" action="/logout" class="logout-form">
      <span class="site-user">{{ current_user.email }}</span>
      <button type="submit" class="logout-button">Log out</button>
    </form>
    {% else %}
    <span class="site-tag">plans your path, then rewrites it as you learn</span>
    {% endif %}
  </header>
  <main class="page">{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 6: Append logout/track-list styling to `static/style.css`**

```css
.logout-form {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.site-user {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-muted);
}

.logout-button {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  font-weight: 500;
  padding: 0.3rem 0.7rem;
  background: transparent;
  color: var(--ink-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.logout-button:hover { background: var(--surface); color: var(--ink); }

.track-list { list-style: none; margin: 1.5rem 0; padding: 0; }

.track-list-item {
  padding: 0.9rem 0;
  border-bottom: 1px solid var(--border);
}

.track-list-name {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 1.05rem;
  text-decoration: none;
  color: var(--ink);
}

.track-list-name:hover { color: var(--taken); }
.track-list-goal { color: var(--ink-muted); margin: 0.25rem 0 0; font-size: 0.92rem; }
```

- [ ] **Step 7: Delete `templates/start.html`**

```bash
rm templates/start.html
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: the fixture-dependent tests from Step 1 pass. Tests further down in the file (still referencing `/start`, `/path/1`, etc. before Task 5 updates them) will fail here — that's expected and resolved in Task 5. Confirm specifically: `pytest tests/test_app.py -v -k "dashboard or track_form or compute_plan_falls_back"` — all pass.

- [ ] **Step 9: Commit**

```bash
git add app.py templates/dashboard.html templates/base.html tests/test_app.py static/style.css
git rm templates/start.html
git commit -m "feat: add dashboard and multi-track creation, replacing anonymous start screen"
```

---

### Task 5: Ownership checks on path/item/history routes, template renames, remaining test updates

**Files:**
- Modify: `app.py`
- Modify: `templates/path.html`
- Modify: `templates/item.html`
- Modify: `templates/path_updated.html`
- Modify: `templates/history.html`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `get_current_user` (Task 3), `db.get_track` (Task 2).
- Produces: an internal `get_owned_track(track_id, current_user, db_path) -> dict` helper — raises 404 if the track doesn't exist or isn't owned by `current_user`. Used by every route in this task.

- [ ] **Step 1: Update the remaining tests in `tests/test_app.py`**

Replace every remaining test below the ones added in Task 4 (i.e. everything from `test_current_path_screen_shows_recommended_items_and_rationale` onward) with:

```python
def test_current_path_screen_shows_recommended_items_and_rationale(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    assert "RAG Fundamentals" in response.text
    assert "Matches your goal." in response.text
    assert "Start with RAG fundamentals." in response.text


def test_current_path_screen_shows_candidates_considered(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    assert "Candidates considered (2)" in response.text
    assert "Chunking Strategies: Splitting Documents Without Losing Meaning" in response.text


def test_current_path_screen_returns_404_for_nonexistent_track(client):
    response = client.get("/path/99999")
    assert response.status_code == 404


def test_current_path_screen_returns_404_for_another_users_track(client, tmp_path):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    with TestClient(app_module.app) as other_client:
        other_client.post(
            "/register",
            data={"email": "someone-else@example.com", "password": "hunter2", "confirm_password": "hunter2"},
        )
        response = other_client.get("/path/1")

    assert response.status_code == 404


def test_item_view_shows_content_and_quiz_form(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals")

    assert response.status_code == 200
    assert "Retrieval-Augmented Generation" in response.text
    assert 'action="/item/1/rag-fundamentals/submit"' in response.text


def test_submitting_quiz_grades_it_and_shows_diff(client, monkeypatch):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    def fake_compute_plan_after_quiz(track, progress):
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
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/does-not-exist")
    assert response.status_code == 404


def test_submit_quiz_returns_404_for_nonexistent_track(client):
    response = client.post(
        "/item/99999/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )
    assert response.status_code == 404


def test_history_screen_shows_plan_log_and_catalog_table(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/history/1")

    assert response.status_code == 200
    assert "Start with RAG fundamentals." in response.text
    assert "RAG Fundamentals" in response.text


def test_history_screen_returns_404_for_nonexistent_track(client):
    response = client.get("/history/99999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — routes still take `learner_id` and aren't auth-protected yet, so ownership/404-for-other-user tests fail and every route call is missing the required login dependency.

- [ ] **Step 3: Update `path`/`item`/`submit`/`history` routes in `app.py`**

Add this helper function (near `get_current_user`):

```python
def get_owned_track(track_id: int, current_user: dict, db_path: str) -> dict:
    track = db.get_track(track_id, db_path)
    if track is None or track["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Track not found")
    return track
```

Replace the four remaining route functions (`current_path`, `item_view`, `submit_quiz`, `history_page`) with:

```python
@app.get("/path/{track_id}", response_class=HTMLResponse)
def current_path(
    request: Request, track_id: int, current_user: dict = Depends(get_current_user)
):
    track = get_owned_track(track_id, current_user, DB_PATH)
    progress = db.get_progress(track_id, DB_PATH)
    latest_plan = db.get_latest_plan(track_id, DB_PATH)

    steps = [
        {"item": get_item(CATALOG, step["item_id"]), "rationale": step["rationale"]}
        for step in latest_plan["steps"]
    ]
    ready_tracks = planner.certification_ready_tracks(CATALOG, progress)
    candidates = [
        get_item(CATALOG, item_id) for item_id in latest_plan.get("candidate_ids", [])
    ]

    return templates.TemplateResponse(
        request,
        "path.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "track": track,
            "steps": steps,
            "summary": latest_plan["summary"],
            "ready_tracks": ready_tracks,
            "candidates": candidates,
        },
    )


@app.get("/item/{track_id}/{item_id}", response_class=HTMLResponse)
def item_view(
    request: Request,
    track_id: int,
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    get_owned_track(track_id, current_user, DB_PATH)
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    return templates.TemplateResponse(
        request,
        "item.html",
        {"request": request, "current_user": current_user, "track_id": track_id, "item": item},
    )


@app.post("/item/{track_id}/{item_id}/submit", response_class=HTMLResponse)
async def submit_quiz(
    request: Request,
    track_id: int,
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    track = get_owned_track(track_id, current_user, DB_PATH)
    form = await request.form()
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    answers = [int(form.get(f"answer_{i}", -1)) for i in range(len(item.quiz))]
    score = quiz_module.grade_quiz(item.quiz, answers)

    db.record_progress(track_id, item_id, score, DB_PATH)

    previous_plan = db.get_latest_plan(track_id, DB_PATH)
    progress = db.get_progress(track_id, DB_PATH)
    new_plan, _used_fallback, candidate_ids = compute_plan(track, progress)
    new_plan_dict = new_plan.model_dump()
    new_plan_dict["candidate_ids"] = candidate_ids
    db.log_plan(track_id, new_plan_dict, "quiz_result", DB_PATH)

    old_item_ids = [step["item_id"] for step in previous_plan["steps"]] if previous_plan else []
    diff = planner.plan_diff(old_item_ids, [step.item_id for step in new_plan.steps])

    return templates.TemplateResponse(
        request,
        "path_updated.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "score": score,
            "diff": diff,
            "summary": new_plan.summary,
        },
    )


@app.get("/history/{track_id}", response_class=HTMLResponse)
def history_page(
    request: Request, track_id: int, current_user: dict = Depends(get_current_user)
):
    get_owned_track(track_id, current_user, DB_PATH)
    plan_log = db.get_plan_log(track_id, DB_PATH)
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "plan_log": plan_log,
            "catalog": CATALOG.items,
        },
    )
```

- [ ] **Step 4: Rename `learner_id`/`learner` to `track_id`/`track` in the four templates**

In `templates/path.html`: replace every `{{ learner_id }}` with `{{ track_id }}`, and `{{ learner.goal_text }}` with `{{ track.goal_text }}`.

In `templates/item.html`: replace every `{{ learner_id }}` with `{{ track_id }}`.

In `templates/path_updated.html`: replace every `{{ learner_id }}` with `{{ track_id }}`.

In `templates/history.html`: replace every `{{ learner_id }}` with `{{ track_id }}`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest -v` for the full suite.
Expected: all tests pass, including the new cross-user ownership test.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/path.html templates/item.html templates/path_updated.html templates/history.html tests/test_app.py
git commit -m "feat: require login and ownership on all track-scoped routes"
```

---

### Task 6: README update and manual smoke test

**Files:**
- Modify: `README.md`

**Interfaces:**
- None — documentation and manual verification only.

- [ ] **Step 1: Update `README.md`'s "How it works" and "Quick start" sections**

Add a bullet to the "How it works" list (after the `app.py` bullet):

```markdown
- `auth.py` / `db.py`'s `users`/`sessions` tables — real email+password accounts. A "learner" from earlier versions of this project is now a user-owned **track**; one account can run several tracks in parallel, each with its own progress and plan history.
```

Update the "Quick start" section's walkthrough paragraph to:

```markdown
Then open http://127.0.0.1:8000/, register an account, and describe a learning goal (e.g. "I want to understand how RAG differs from just stuffing context into a prompt") to start your first track. Complete items and take their quizzes to watch the plan adapt — and start additional tracks for other goals any time from the dashboard.
```

- [ ] **Step 2: Manually smoke-test the full flow**

```bash
source venv/bin/activate
uvicorn app:app --reload
```

Open the app and confirm, in order: registering a new account redirects to an empty dashboard; starting a track redirects to `/path/{id}` with real catalog items; logging out and back in still shows that track on the dashboard; starting a second track with a different goal shows both tracks on the dashboard; opening a track's `/path` while logged in as a *different* account (register a second account in an incognito window) returns a 404, not the first account's track.

- [ ] **Step 3: Run the full test suite one last time**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for accounts and multi-track support"
```

---

## Self-Review Notes

- **Spec coverage:** users/sessions/tracks data model → Task 2. Password hashing/session tokens/track naming → Task 1. Register/login/logout → Task 3. Dashboard + track creation + default-level memory → Task 4. Ownership enforcement on every track-scoped route (identical 404 for nonexistent vs. not-owned) → Task 5. Non-goals (no password reset, no email verification, no rate-limiting, open registration) are honored by omission — no task adds any of them.
- **Placeholder scan:** every step has complete code, including `register_submit`/`login_submit` taking a real `request: Request` parameter for their error-redisplay branches rather than a hand-wavy fallback.
- **Type consistency:** `db.py`'s renamed functions (`create_track`, `get_track`, `get_tracks_for_user`, `record_progress`, `get_progress`, `log_plan`, `get_plan_log`, `get_latest_plan`) are defined once in Task 2 and consumed with matching signatures in Task 4 (`create_track`, `update_default_starting_level`) and Task 5 (`get_track` via `get_owned_track`, `get_progress`, `log_plan`, `get_plan_log`, `get_latest_plan`). `get_current_user`'s return shape (a `users` row plus `session_expires_at`) is defined once in Task 3 and consumed identically everywhere it's injected via `Depends`.
