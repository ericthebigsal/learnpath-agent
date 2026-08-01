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
