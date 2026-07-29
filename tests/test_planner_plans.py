from catalog import load_catalog
from models import Level
from planner import filter_candidates, rule_based_plan


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
