from google.genai import types

from catalog import LEVEL_ORDER, levels_within
from models import Catalog, CatalogItem, Level, PlanResponse, PlanStep, Track

TRACK_NAMES = [track.value for track in Track]


def filter_candidates(
    catalog: Catalog, goal_text: str, level: Level, completed_item_ids: set[str]
) -> list[CatalogItem]:
    goal_lower = goal_text.lower()
    matched_tracks = [name for name in TRACK_NAMES if name.lower() in goal_lower]
    allowed_levels = levels_within(level, spread=1)

    if matched_tracks:
        candidates = [
            item
            for item in catalog.items
            if item.track.value in matched_tracks and item.level in allowed_levels
        ]
    else:
        candidates = [item for item in catalog.items if item.level in allowed_levels]

    return [item for item in candidates if item.id not in completed_item_ids]


def current_level(starting_level: Level, progress: list[dict], catalog: Catalog) -> Level:
    idx = LEVEL_ORDER.index(starting_level)
    items_by_id = {item.id: item for item in catalog.items}

    for entry in progress:
        item = items_by_id.get(entry["item_id"])
        if item is not None and item.level == LEVEL_ORDER[idx] and entry["quiz_score"] >= 90:
            idx = min(idx + 1, len(LEVEL_ORDER) - 1)

    return LEVEL_ORDER[idx]


def rule_based_plan(candidates: list[CatalogItem], limit: int = 5) -> PlanResponse:
    ordered = sorted(candidates, key=lambda item: (item.level.value, item.duration_minutes))[:limit]
    steps = [
        PlanStep(
            item_id=item.id,
            rationale=(
                f"Fallback rule: {item.level.value} level in {item.track.value}, "
                f"{item.duration_minutes} minutes."
            ),
        )
        for item in ordered
    ]
    return PlanResponse(
        steps=steps,
        summary="Fallback rule-based plan (LLM unavailable): candidates ordered by level then duration.",
    )


PLANNER_MODEL = "gemini-2.5-flash"


def build_prompt(
    goal_text: str, level: Level, progress: list[dict], candidates: list[CatalogItem]
) -> str:
    candidate_lines = "\n".join(
        f"- {item.id}: {item.title} ({item.track.value}, {item.level.value}, {item.duration_minutes}m)"
        for item in candidates
    )
    if progress:
        progress_lines = "\n".join(
            f"- {entry['item_id']}: scored {entry['quiz_score']}%" for entry in progress
        )
    else:
        progress_lines = "None yet."

    return (
        "You are an adaptive learning-path planner for an AI-concepts course catalog.\n\n"
        f"Learner goal: {goal_text}\n"
        f"Learner level: {level.value}\n\n"
        f"Completed items and quiz scores so far:\n{progress_lines}\n\n"
        "Candidate items available to recommend next (choose and order a subset of these; "
        "never invent an id that isn't listed):\n"
        f"{candidate_lines}\n\n"
        "Return an ordered list of item ids to study next, a one-line rationale for each, "
        "and a one-to-two-sentence overall summary of the plan."
    )


def gemini_plan(
    client,
    goal_text: str,
    level: Level,
    progress: list[dict],
    candidates: list[CatalogItem],
    model: str = PLANNER_MODEL,
) -> PlanResponse:
    prompt = build_prompt(goal_text, level, progress, candidates)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PlanResponse,
        ),
    )
    return response.parsed


PASSING_THRESHOLD = 70.0


def plan_or_replan(
    client, catalog: Catalog, learner: dict, progress: list[dict]
) -> tuple[PlanResponse, bool]:
    completed_ids = {entry["item_id"] for entry in progress}
    level = current_level(Level(learner["starting_level"]), progress, catalog)
    candidates = filter_candidates(catalog, learner["goal_text"], level, completed_ids)

    try:
        plan = gemini_plan(client, learner["goal_text"], level, progress, candidates)
        return plan, False
    except Exception:
        return rule_based_plan(candidates), True


def certification_ready_tracks(catalog: Catalog, progress: list[dict]) -> list[str]:
    # Only plain `course` items are counted: `learning_path` bundles have no quiz of
    # their own (item.html renders no submit form when item.quiz is empty), so they
    # can never pick up a real progress row through the UI and must be excluded here.
    scores_by_id = {entry["item_id"]: entry["quiz_score"] for entry in progress}
    ready: list[str] = []

    for track_name in TRACK_NAMES:
        track_items = [
            item
            for item in catalog.items
            if item.track.value == track_name
            and item.type.value == "course"
            and not item.certification_eligible
        ]
        if not track_items:
            continue
        if all(item.id in scores_by_id for item in track_items):
            average = sum(scores_by_id[item.id] for item in track_items) / len(track_items)
            if average >= PASSING_THRESHOLD:
                ready.append(track_name)

    return ready
