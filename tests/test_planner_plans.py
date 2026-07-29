from types import SimpleNamespace
from unittest.mock import Mock

from catalog import load_catalog
from models import Level, PlanResponse, PlanStep
from planner import filter_candidates, rule_based_plan, build_prompt, gemini_plan, plan_or_replan, certification_ready_tracks


def test_rule_based_plan_orders_by_level_then_duration_and_respects_limit():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    plan = rule_based_plan(candidates, limit=3)

    assert len(plan.steps) <= 3
    assert plan.summary  # non-empty
    chosen_ids = {step.item_id for step in plan.steps}
    candidate_ids = {item.id for item in candidates}
    assert chosen_ids <= candidate_ids

    chosen_items = [item for item in candidates if item.id in chosen_ids]
    levels_seen = [item.level.value for item in chosen_items]
    assert levels_seen == sorted(levels_seen)


def test_build_prompt_includes_goal_progress_and_candidates():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())[:2]
    progress = [{"item_id": "rag-fundamentals", "quiz_score": 85.0}]

    prompt = build_prompt("Learn RAG", Level.BEGINNER, progress, candidates)

    assert "Learn RAG" in prompt
    assert "beginner" in prompt
    assert "rag-fundamentals" in prompt
    assert "85.0" in prompt
    for candidate in candidates:
        assert candidate.id in prompt


def test_gemini_plan_returns_parsed_plan_response():
    client = Mock()
    expected_plan = PlanResponse(
        steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
        summary="Start with RAG fundamentals.",
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=expected_plan)

    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    result = gemini_plan(client, "Learn RAG", Level.BEGINNER, [], candidates)

    assert result == expected_plan
    client.models.generate_content.assert_called_once()
    _, kwargs = client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-2.5-flash"
    assert kwargs["config"].response_schema is PlanResponse
    assert kwargs["config"].response_mime_type == "application/json"
    assert "Learn RAG" in kwargs["contents"]


def test_plan_or_replan_uses_gemini_plan_when_client_succeeds():
    client = Mock()
    expected_plan = PlanResponse(
        steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
        summary="Start with RAG.",
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=expected_plan)

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback = plan_or_replan(client, catalog, learner, [])

    assert plan == expected_plan
    assert used_fallback is False


def test_plan_or_replan_falls_back_when_gemini_call_raises():
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("rate limited")

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback = plan_or_replan(client, catalog, learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0


def test_certification_ready_tracks_empty_with_no_progress():
    catalog = load_catalog()
    assert certification_ready_tracks(catalog, []) == []


def test_certification_ready_tracks_flags_track_after_all_items_pass():
    catalog = load_catalog()
    rag_courses = [
        item for item in catalog.items
        if item.track.value == "RAG" and item.type.value == "course" and not item.certification_eligible
    ]
    progress = [{"item_id": item.id, "quiz_score": 80.0} for item in rag_courses]

    assert "RAG" in certification_ready_tracks(catalog, progress)


def test_certification_ready_tracks_excludes_track_with_low_average():
    catalog = load_catalog()
    rag_courses = [
        item for item in catalog.items
        if item.track.value == "RAG" and item.type.value == "course" and not item.certification_eligible
    ]
    progress = [{"item_id": item.id, "quiz_score": 50.0} for item in rag_courses]

    assert "RAG" not in certification_ready_tracks(catalog, progress)
