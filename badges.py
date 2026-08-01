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
            if not tracks and not matches:
                rows.append({
                    "label": label,
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
