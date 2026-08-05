import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "learnpath.db")

SQLITE_SCHEMA = """
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

# Postgres has no AUTOINCREMENT -- SERIAL is the equivalent identity column.
# Otherwise this is the same schema as SQLITE_SCHEMA above.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    goal_text TEXT NOT NULL,
    starting_level TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    quiz_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_log (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    trigger TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS badges (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    badge_type TEXT NOT NULL,
    track_id INTEGER NOT NULL DEFAULT 0,
    earned_at TEXT NOT NULL,
    UNIQUE(user_id, badge_type, track_id)
);
"""


class DuplicateEmailError(Exception):
    pass


def _is_postgres(db_path: str) -> bool:
    return db_path.startswith("postgres://") or db_path.startswith("postgresql://")


def _connect(db_path: str = DEFAULT_DB_PATH):
    if _is_postgres(db_path):
        import psycopg
        from psycopg.rows import dict_row

        # prepare_threshold=None disables psycopg3's automatic server-side statement
        # preparation. A managed Postgres connection string here is typically a
        # PgBouncer pooler in transaction mode (needed since this module opens a
        # fresh connection per call rather than pooling in-process), and prepared
        # statements don't survive across the different backend connections
        # PgBouncer can hand out between transactions.
        return psycopg.connect(db_path, row_factory=dict_row, prepare_threshold=None)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _exec(conn, sql: str, params: tuple = ()):
    """Run `sql` on `conn`, translating SQLite's `?` placeholders to Postgres's
    `%s` when `conn` is a psycopg connection. Query text elsewhere in this
    module is written once, in SQLite style, and works against both backends
    through this indirection.
    """
    if isinstance(conn, sqlite3.Connection):
        return conn.execute(sql, params)
    return conn.execute(sql.replace("?", "%s"), params)


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        if _is_postgres(db_path):
            conn.execute(POSTGRES_SCHEMA)
        else:
            conn.executescript(SQLITE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------- users ----------

def create_user(email: str, password_hash: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    email = email.strip().lower()
    conn = _connect(db_path)
    try:
        existing = _exec(conn, "SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise DuplicateEmailError(f"Email already registered: {email!r}")

        now = datetime.now(timezone.utc).isoformat()
        row = _exec(
            conn,
            "INSERT INTO users (email, password_hash, default_starting_level, created_at) "
            "VALUES (?, ?, 'beginner', ?) RETURNING *",
            (email, password_hash, now),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = _exec(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    email = email.strip().lower()
    conn = _connect(db_path)
    try:
        row = _exec(conn, "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_default_starting_level(
    user_id: int, starting_level: str, db_path: str = DEFAULT_DB_PATH
) -> None:
    conn = _connect(db_path)
    try:
        _exec(
            conn,
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
        _exec(
            conn,
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_session_with_user(token: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = _exec(
            conn,
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
        _exec(conn, "DELETE FROM sessions WHERE token = ?", (token,))
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
        row = _exec(
            conn,
            "INSERT INTO tracks (user_id, name, goal_text, starting_level, created_at) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            (user_id, name, goal_text, starting_level, now),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_track(track_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = _exec(conn, "SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_tracks_for_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = _exec(
            conn, "SELECT * FROM tracks WHERE user_id = ? ORDER BY id ASC", (user_id,)
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
        row = _exec(
            conn,
            "INSERT INTO progress (track_id, item_id, completed_at, quiz_score) "
            "VALUES (?, ?, ?, ?) RETURNING *",
            (track_id, item_id, now, quiz_score),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def get_progress(track_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = _exec(
            conn, "SELECT * FROM progress WHERE track_id = ? ORDER BY id ASC", (track_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------- plans ----------

def _plan_row_to_dict(row) -> dict:
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
        row = _exec(
            conn,
            "INSERT INTO plan_log (track_id, created_at, plan_json, trigger) "
            "VALUES (?, ?, ?, ?) RETURNING *",
            (track_id, now, json.dumps(plan), trigger),
        ).fetchone()
        conn.commit()
        return _plan_row_to_dict(row)
    finally:
        conn.close()


def get_plan_log(track_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = _exec(
            conn, "SELECT * FROM plan_log WHERE track_id = ? ORDER BY id ASC", (track_id,)
        ).fetchall()
        return [_plan_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_plan(track_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = _exec(
            conn,
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
        if _is_postgres(db_path):
            sql = (
                "INSERT INTO badges (user_id, badge_type, track_id, earned_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (user_id, badge_type, track_id) DO NOTHING"
            )
        else:
            sql = (
                "INSERT OR IGNORE INTO badges (user_id, badge_type, track_id, earned_at) "
                "VALUES (?, ?, ?, ?)"
            )
        cursor = _exec(conn, sql, (user_id, badge_type, track_id, earned_at))
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def get_badges_for_user(user_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = _exec(
            conn, "SELECT * FROM badges WHERE user_id = ? ORDER BY earned_at ASC", (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
