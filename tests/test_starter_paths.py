import pytest

from catalog import get_item, load_catalog
from starter_paths import STARTER_PATHS, get_starter_path


def test_there_are_exactly_three_starter_paths():
    assert len(STARTER_PATHS) == 3


def test_starter_path_ids_are_unique():
    ids = [path.id for path in STARTER_PATHS]
    assert len(ids) == len(set(ids))


def test_every_starter_path_has_at_least_one_step():
    for path in STARTER_PATHS:
        assert len(path.steps) > 0


def test_every_starter_path_step_references_a_real_catalog_item():
    catalog = load_catalog()
    for path in STARTER_PATHS:
        for step in path.steps:
            get_item(catalog, step.item_id)  # raises KeyError if missing


def test_get_starter_path_returns_the_matching_path():
    path = get_starter_path("engineer")
    assert path.title == "Engineer"


def test_get_starter_path_raises_key_error_for_unknown_id():
    with pytest.raises(KeyError):
        get_starter_path("does-not-exist")
