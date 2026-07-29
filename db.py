import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "learnpath.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_text TEXT NOT NULL,
    starting_level TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    quiz_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    trigger TEXT NOT NULL
);
"""


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


def create_learner(goal_text: str, starting_level: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO learners (goal_text, starting_level, created_at) VALUES (?, ?, ?)",
            (goal_text, starting_level, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM learners WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_learner(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM learners WHERE id = ?", (learner_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_progress(
    learner_id: int, item_id: str, quiz_score: float, db_path: str = DEFAULT_DB_PATH
) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO progress (learner_id, item_id, completed_at, quiz_score) "
            "VALUES (?, ?, ?, ?)",
            (learner_id, item_id, now, quiz_score),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM progress WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_progress(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM progress WHERE learner_id = ? ORDER BY id ASC", (learner_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _plan_row_to_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    plan = json.loads(result.pop("plan_json"))
    result["steps"] = plan["steps"]
    result["summary"] = plan["summary"]
    result["candidate_ids"] = plan.get("candidate_ids", [])
    return result


def log_plan(learner_id: int, plan: dict, trigger: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO plan_log (learner_id, created_at, plan_json, trigger) "
            "VALUES (?, ?, ?, ?)",
            (learner_id, now, json.dumps(plan), trigger),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM plan_log WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _plan_row_to_dict(row)
    finally:
        conn.close()


def get_plan_log(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM plan_log WHERE learner_id = ? ORDER BY id ASC", (learner_id,)
        ).fetchall()
        return [_plan_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_plan(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM plan_log WHERE learner_id = ? ORDER BY id DESC LIMIT 1",
            (learner_id,),
        ).fetchone()
        return _plan_row_to_dict(row) if row else None
    finally:
        conn.close()
