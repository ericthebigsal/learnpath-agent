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

CREATE TABLE IF NOT EXISTS badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge_type TEXT NOT NULL,
    track_id INTEGER NOT NULL DEFAULT 0,
    earned_at TEXT NOT NULL,
    UNIQUE(user_id, badge_type, track_id)
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
    email = email.strip().lower()
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
    email = email.strip().lower()
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
            SELECT users.id, users.email, users.default_starting_level, users.created_at,
                   sessions.expires_at AS session_expires_at
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
