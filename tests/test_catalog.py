import pytest

from catalog import get_item, levels_within, load_catalog
from models import Level, Track


def test_catalog_loads_with_unique_ids_and_minimum_size():
    catalog = load_catalog()
    ids = [item.id for item in catalog.items]

    assert len(catalog.items) >= 50
    assert len(ids) == len(set(ids)), "catalog item ids must be unique"


def test_every_track_level_cell_has_at_least_two_course_items():
    catalog = load_catalog()
    for track in Track:
        for level in Level:
            count = sum(
                1
                for item in catalog.items
                if item.track == track and item.level == level and item.type.value == "course"
            )
            assert count >= 2, f"expected >=2 course items for {track.value}/{level.value}, got {count}"


def test_catalog_has_bundled_learning_paths_and_capstones():
    catalog = load_catalog()
    learning_paths = [item for item in catalog.items if item.type.value == "learning_path"]
    capstones = [item for item in catalog.items if item.certification_eligible]

    assert len(learning_paths) >= 3
    assert all(len(lp.related_item_ids) >= 2 for lp in learning_paths)
    assert len(capstones) >= 4


def test_learning_path_related_ids_reference_real_catalog_items():
    catalog = load_catalog()
    all_ids = {item.id for item in catalog.items}
    for item in catalog.items:
        if item.type.value == "learning_path":
            for related_id in item.related_item_ids:
                assert related_id in all_ids, f"{item.id} references unknown item {related_id}"


def test_course_items_have_substantive_content_and_valid_quizzes():
    catalog = load_catalog()
    for item in catalog.items:
        if item.type.value == "course":
            assert len(item.content) >= 200, f"{item.id} content is too short"
            assert 3 <= len(item.quiz) <= 5, f"{item.id} quiz must have 3-5 questions"
            for question in item.quiz:
                assert 0 <= question.correct_index < len(question.options)


def test_get_item_returns_expected_item_and_raises_for_unknown_id():
    catalog = load_catalog()
    first = catalog.items[0]

    assert get_item(catalog, first.id) == first
    with pytest.raises(KeyError):
        get_item(catalog, "does-not-exist")


def test_levels_within_clamps_at_the_edges():
    assert levels_within(Level.BEGINNER, spread=1) == [Level.BEGINNER, Level.INTERMEDIATE]
    assert levels_within(Level.ADVANCED, spread=1) == [Level.INTERMEDIATE, Level.ADVANCED]
    assert levels_within(Level.INTERMEDIATE, spread=1) == [
        Level.BEGINNER,
        Level.INTERMEDIATE,
        Level.ADVANCED,
    ]
