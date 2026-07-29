import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from catalog import LEVEL_ORDER, load_catalog
from models import CatalogItem, Level, PlanResponse, PlanStep, Track
from planner import (
    PASSING_THRESHOLD,
    build_prompt,
    certification_ready_tracks,
    filter_candidates,
    gemini_plan,
    plan_or_replan,
    rule_based_plan,
)


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
    level_indices = [LEVEL_ORDER.index(item.level) for item in chosen_items]
    assert level_indices == sorted(level_indices)


def test_rule_based_plan_puts_beginner_items_before_advanced_items():
    # Regression test: sorting by item.level.value (a plain string) puts "advanced"
    # before "beginner" alphabetically, inverting the intended fallback ordering.
    # Build a candidate list spanning all three levels and confirm no advanced item
    # is ever ordered ahead of a beginner item.
    candidates = [
        CatalogItem(
            id="adv-1",
            title="Advanced item",
            type="course",
            level=Level.ADVANCED,
            track=Track.RAG,
            duration_minutes=10,
        ),
        CatalogItem(
            id="int-1",
            title="Intermediate item",
            type="course",
            level=Level.INTERMEDIATE,
            track=Track.RAG,
            duration_minutes=10,
        ),
        CatalogItem(
            id="beg-1",
            title="Beginner item",
            type="course",
            level=Level.BEGINNER,
            track=Track.RAG,
            duration_minutes=10,
        ),
    ]

    plan = rule_based_plan(candidates, limit=3)

    ordered_ids = [step.item_id for step in plan.steps]
    assert ordered_ids == ["beg-1", "int-1", "adv-1"]

    # No advanced-level item should appear before a beginner-level item.
    positions = {item_id: idx for idx, item_id in enumerate(ordered_ids)}
    assert positions["beg-1"] < positions["adv-1"]
    assert positions["int-1"] < positions["adv-1"]


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

    plan, used_fallback, candidate_ids = plan_or_replan(client, catalog, learner, [])

    assert plan == expected_plan
    assert used_fallback is False
    assert "rag-fundamentals" in candidate_ids


def test_plan_or_replan_falls_back_when_gemini_call_raises():
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("rate limited")

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback, candidate_ids = plan_or_replan(client, catalog, learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0
    assert len(candidate_ids) > 0


def test_plan_or_replan_returns_candidate_ids_used():
    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}
    expected_candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    plan, used_fallback, candidate_ids = plan_or_replan(None, catalog, learner, [])

    assert used_fallback is True
    assert set(candidate_ids) == {item.id for item in expected_candidates}


def test_plan_or_replan_is_explicit_fallback_when_client_is_none():
    # Elevated finding: when app.compute_plan fails to construct a genai.Client (e.g. no
    # API key), it passes client=None. This must be an explicit, self-documenting early
    # return rather than relying on the incidental AttributeError from None.models to be
    # caught by the broad except Exception in the try block.
    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback, candidate_ids = plan_or_replan(None, catalog, learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0
    assert len(candidate_ids) > 0


def test_gemini_plan_raises_when_response_parsed_is_none():
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(parsed=None)

    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    with pytest.raises(Exception):
        gemini_plan(client, "Learn RAG", Level.BEGINNER, [], candidates)


def test_plan_or_replan_falls_back_when_gemini_returns_none_parsed():
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(parsed=None)

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback, candidate_ids = plan_or_replan(client, catalog, learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0


def test_plan_or_replan_drops_hallucinated_ids_and_keeps_valid_ones():
    client = Mock()
    llm_plan = PlanResponse(
        steps=[
            PlanStep(item_id="rag-fundamentals", rationale="A real candidate."),
            PlanStep(item_id="totally-made-up-id", rationale="Hallucinated by the model."),
        ],
        summary="Mixed valid and invalid ids.",
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=llm_plan)

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback, candidate_ids = plan_or_replan(client, catalog, learner, [])

    assert used_fallback is False
    assert [step.item_id for step in plan.steps] == ["rag-fundamentals"]
    assert "totally-made-up-id" not in [step.item_id for step in plan.steps]


def test_plan_or_replan_falls_back_when_all_returned_ids_are_invalid():
    client = Mock()
    llm_plan = PlanResponse(
        steps=[PlanStep(item_id="totally-made-up-id", rationale="Hallucinated by the model.")],
        summary="All invalid ids.",
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=llm_plan)

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback, candidate_ids = plan_or_replan(client, catalog, learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0
    assert all(step.item_id in candidate_ids for step in plan.steps)


def test_build_prompt_includes_passing_threshold():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())[:2]

    prompt = build_prompt("Learn RAG", Level.BEGINNER, [], candidates)

    assert str(PASSING_THRESHOLD) in prompt


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
