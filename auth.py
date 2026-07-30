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
    if not truncated:
        truncated = goal_text[:max_length]
    return truncated + "…"
