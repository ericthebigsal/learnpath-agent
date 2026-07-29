from planner import plan_diff


def test_plan_diff_identifies_kept_added_and_removed():
    diff = plan_diff(old_item_ids=["a", "b", "c"], new_item_ids=["a", "c", "d"])

    assert diff.kept == ["a", "c"]
    assert diff.added == ["d"]
    assert diff.removed == ["b"]


def test_plan_diff_detects_no_reorder_when_relative_order_preserved():
    diff = plan_diff(old_item_ids=["a", "b", "c"], new_item_ids=["a", "b", "c", "d"])
    assert diff.reordered is False


def test_plan_diff_detects_reorder_when_relative_order_changes():
    diff = plan_diff(old_item_ids=["a", "b", "c"], new_item_ids=["c", "a", "b"])
    assert diff.reordered is True


def test_plan_diff_handles_empty_old_plan():
    diff = plan_diff(old_item_ids=[], new_item_ids=["a", "b"])
    assert diff.kept == []
    assert diff.added == ["a", "b"]
    assert diff.removed == []
    assert diff.reordered is False
