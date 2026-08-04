import logging
import time

from google.genai import types

from catalog import LEVEL_ORDER, levels_within
from models import Catalog, CatalogItem, DroppedItem, Level, PlanDiff, PlanResponse, PlanStep, Track

logger = logging.getLogger(__name__)

TRACK_NAMES = [track.value for track in Track]

# Free-text goals rarely spell out a track's exact name. These keywords catch
# the common ways learners actually phrase a goal, so the deterministic
# fallback (and the LLM's candidate list) can stay focused on-topic instead
# of falling back to every track in the catalog.
TRACK_KEYWORDS: dict[str, list[str]] = {
    "LLM Fundamentals": [
        "fundamentals", "basics", "how llms work", "transformer", "tokenization",
        "autoregressive", "scaling law", "model card", "open-weight", "open weight",
    ],
    "RAG": [
        "rag", "retrieval", "retrieval-augmented", "vector database", "vector db",
        "embeddings", "chunking", "reranking", "hybrid search",
    ],
    "Multi-Agent Systems": [
        "multi-agent", "multi agent", "agentic", "swarm", "orchestrator",
        "orchestration", "task decomposition",
    ],
    "LLM Evaluation & Testing": [
        "eval", "evaluation", "evaluating", "testing", "test set", "benchmark",
        "llm-as-judge", "llm as judge", "regression test", "red-team", "red team",
    ],
    "Agent Tools & Skills": [
        "tool calling", "function calling", "tool schema", "plugin", "agent tools",
        "agent skills",
    ],
    "Context Engineering": [
        "context window", "context engineering", "context budget", "memory",
        "lost in the middle", "context drift",
    ],
    "LLM Billing & Cost Models": [
        "cost", "billing", "pricing", "budget", "spend", "token cost",
        "prompt caching",
    ],
    "Responsible AI": [
        "ethics", "ethical", "bias", "fairness", "fair", "responsible ai", "privacy",
        "hallucination", "governance", "compliance", "regulation",
    ],
    "AI Security & Risk": [
        "security", "threat", "prompt injection", "injection", "vulnerability",
        "attack", "adversarial", "supply chain", "atlas", "owasp",
    ],
}


def match_tracks(goal_text: str) -> list[str]:
    """Return catalog tracks whose name or known keywords appear in free-text goal.

    Checked in TRACK_NAMES order so results are stable regardless of dict
    iteration order. Returns [] when nothing -- not even a keyword -- matches,
    which callers should treat as "don't guess, ask the learner to pick."
    """
    goal_lower = goal_text.lower()
    matched = []
    for name in TRACK_NAMES:
        keywords = [name.lower()] + TRACK_KEYWORDS.get(name, [])
        if any(keyword in goal_lower for keyword in keywords):
            matched.append(name)
    return matched


def filter_candidates(
    catalog: Catalog, goal_text: str, level: Level, completed_item_ids: set[str]
) -> list[CatalogItem]:
    matched_tracks = match_tracks(goal_text)
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


def rule_based_plan(
    candidates: list[CatalogItem],
    previous_item_ids: list[str] | None = None,
    limit: int = 5,
) -> PlanResponse:
    ordered = sorted(
        candidates, key=lambda item: (LEVEL_ORDER.index(item.level), item.duration_minutes)
    )[:limit]
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

    new_step_ids = {step.item_id for step in steps}
    dropped = [
        DroppedItem(
            item_id=prev_id,
            rationale=(
                "Fallback rule-based plan: no longer prioritized under simple "
                "level/duration ordering."
            ),
        )
        for prev_id in (previous_item_ids or [])
        if prev_id not in new_step_ids
    ]

    return PlanResponse(
        steps=steps,
        summary="Fallback rule-based plan (LLM unavailable): candidates ordered by level then duration.",
        dropped=dropped,
    )


PLANNER_MODEL = "gemini-2.5-flash"

# Ordered by preference (fast/cheap first). A hardcoded model name can 404
# for a given key/tier without warning -- select_model() checks what this
# key actually has access to instead of assuming PLANNER_MODEL works.
PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

_MODEL_CACHE_TTL_SECONDS = 3600
_cached_model: str | None = None
_cached_model_at: float = 0.0


def select_model(client, preferred: list[str] = PREFERRED_MODELS) -> str:
    """Pick the first model in `preferred` this API key actually has access to.

    Cached for the process lifetime (refreshed hourly) since this calls a
    separate list-models API request -- we don't want every plan/replan to
    pay that latency. Falls back to PLANNER_MODEL if listing models fails
    outright or nothing on the preference list is available, so a transient
    list() error doesn't block planning; generate_content will surface its
    own error and trigger the normal rule-based fallback if that default
    isn't available either.
    """
    global _cached_model, _cached_model_at

    now = time.monotonic()
    if _cached_model and now - _cached_model_at < _MODEL_CACHE_TTL_SECONDS:
        return _cached_model

    try:
        available: set[str] = set()
        for model in client.models.list():
            name = (model.name or "").split("/")[-1]
            actions = (
                getattr(model, "supported_actions", None)
                or getattr(model, "supported_generation_methods", None)
                or []
            )
            if name and (not actions or "generateContent" in actions):
                available.add(name)
    except Exception:
        logger.exception("Failed to list Gemini models; using default %r", PLANNER_MODEL)
        return PLANNER_MODEL

    chosen = next((name for name in preferred if name in available), None)
    if chosen is None and available:
        chosen = sorted(available)[0]
        logger.warning(
            "None of the preferred models %r available for this key; using %r instead",
            preferred, chosen,
        )
    elif chosen is None:
        logger.warning("Gemini model list was empty; using default %r", PLANNER_MODEL)
        chosen = PLANNER_MODEL

    _cached_model, _cached_model_at = chosen, now
    return chosen


PASSING_THRESHOLD = 70.0
ADVANCE_THRESHOLD = 90.0


def build_prompt(
    goal_text: str,
    level: Level,
    progress: list[dict],
    candidates: list[CatalogItem],
    previous_item_ids: list[str] | None = None,
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

    previous_section = ""
    if previous_item_ids:
        previous_lines = "\n".join(f"- {item_id}" for item_id in previous_item_ids)
        previous_section = (
            "\n\nPreviously planned items (from before this replan):\n"
            f"{previous_lines}\n\n"
            "For any of these you are NOT including in your new plan, add an entry to the "
            "`dropped` list explaining in one line why you dropped it. Only include ids from "
            "this previously-planned list in `dropped` — never invent a dropped id."
        )

    return (
        "You are an adaptive learning-path planner for an AI-concepts course catalog.\n\n"
        f"Learner goal: {goal_text}\n"
        f"Learner level: {level.value}\n\n"
        f"Completed items and quiz scores so far:\n{progress_lines}\n\n"
        "Scoring policy for deciding what to recommend next:\n"
        f"- Below {PASSING_THRESHOLD}%: the learner is struggling. Recommend a remedial "
        "alternate item from the same track and level before moving forward.\n"
        f"- {PASSING_THRESHOLD}% to {ADVANCE_THRESHOLD - 0.01}%: solid pass. Continue with "
        "the next item as planned.\n"
        f"- {ADVANCE_THRESHOLD}% or above: strong mastery. It's fine to skip ahead to the "
        "next level.\n\n"
        "Candidate items available to recommend next (choose and order a subset of these; "
        "never invent an id that isn't listed):\n"
        f"{candidate_lines}"
        f"{previous_section}\n\n"
        "Return an ordered list of item ids to study next, a one-line rationale for each, "
        "and a one-to-two-sentence overall summary of the plan."
    )


def gemini_plan(
    client,
    goal_text: str,
    level: Level,
    progress: list[dict],
    candidates: list[CatalogItem],
    previous_item_ids: list[str] | None = None,
    model: str = PLANNER_MODEL,
) -> PlanResponse:
    prompt = build_prompt(goal_text, level, progress, candidates, previous_item_ids)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PlanResponse,
        ),
    )
    parsed = response.parsed
    if parsed is None:
        raise ValueError("Gemini returned no parseable plan")
    return parsed


def plan_or_replan(
    client,
    catalog: Catalog,
    learner: dict,
    progress: list[dict],
    previous_item_ids: list[str] | None = None,
) -> tuple[PlanResponse, bool, list[str]]:
    completed_ids = {entry["item_id"] for entry in progress}
    level = current_level(Level(learner["starting_level"]), progress, catalog)
    candidates = filter_candidates(catalog, learner["goal_text"], level, completed_ids)
    candidate_ids = [item.id for item in candidates]

    if client is None:
        return rule_based_plan(candidates, previous_item_ids), True, candidate_ids

    try:
        model = select_model(client)
        plan = gemini_plan(
            client, learner["goal_text"], level, progress, candidates, previous_item_ids,
            model=model,
        )
        candidate_id_set = set(candidate_ids)
        plan.steps = [step for step in plan.steps if step.item_id in candidate_id_set]
        if not plan.steps:
            raise ValueError("LLM returned no usable candidate ids")
        plan.dropped = [
            dropped for dropped in plan.dropped if dropped.item_id in (previous_item_ids or [])
        ]
        return plan, False, candidate_ids
    except Exception:
        logger.exception(
            "Gemini plan generation failed for goal %r; falling back to rule-based plan",
            learner.get("goal_text"),
        )
        return rule_based_plan(candidates, previous_item_ids), True, candidate_ids


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


def plan_diff(old_item_ids: list[str], new_item_ids: list[str]) -> PlanDiff:
    old_set = set(old_item_ids)
    new_set = set(new_item_ids)

    kept = [item_id for item_id in new_item_ids if item_id in old_set]
    added = [item_id for item_id in new_item_ids if item_id not in old_set]
    removed = [item_id for item_id in old_item_ids if item_id not in new_set]
    reordered = kept != [item_id for item_id in old_item_ids if item_id in new_set]

    return PlanDiff(kept=kept, added=added, removed=removed, reordered=reordered)
