from pathlib import Path

import pytest
from pydantic import ValidationError

from catalog import category_name, get_item, levels_within, load_catalog
from models import Level

DIAGRAMS_DIR = Path(__file__).resolve().parent.parent / "static" / "diagrams"


def test_catalog_loads_with_unique_ids_and_minimum_size():
    catalog = load_catalog()
    ids = [item.id for item in catalog.items]

    assert len(catalog.items) >= 50
    assert len(ids) == len(set(ids)), "catalog item ids must be unique"


def test_catalog_loads_categories():
    catalog = load_catalog()
    assert len(catalog.categories) == 9
    category_ids = {c.id for c in catalog.categories}
    assert "rag" in category_ids


def test_every_category_level_cell_has_at_least_two_course_items():
    catalog = load_catalog()
    for category in catalog.categories:
        for level in Level:
            count = sum(
                1
                for item in catalog.items
                if item.category == category.id and item.level == level and item.type.value == "course"
            )
            assert count >= 2, f"expected >=2 course items for {category.id}/{level.value}, got {count}"


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
            if item.sections:
                assert len(item.sections) >= 3, f"{item.id} has fewer than 3 sections"
                for section in item.sections:
                    assert section.heading, f"{item.id} has a section with no heading"
                    assert len(section.body) >= 150, (
                        f"{item.id} section {section.heading!r} is too short"
                    )
            else:
                assert len(item.content) >= 200, f"{item.id} content is too short"
            assert 3 <= len(item.quiz) <= 5, f"{item.id} quiz must have 3-5 questions"
            for question in item.quiz:
                assert 0 <= question.correct_index < len(question.options)


def test_section_diagram_references_point_to_real_svg_files():
    catalog = load_catalog()
    for item in catalog.items:
        for section in item.sections:
            if section.diagram:
                svg_path = DIAGRAMS_DIR / f"{section.diagram}.svg"
                assert svg_path.is_file(), (
                    f"{item.id} section {section.heading!r} references missing diagram "
                    f"{section.diagram!r} (expected {svg_path})"
                )


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


def test_load_catalog_raises_on_item_referencing_unknown_category(tmp_path):
    import json

    bad_catalog = {
        "categories": [{"id": "rag", "name": "RAG", "keywords": []}],
        "items": [
            {
                "id": "x", "title": "X", "type": "course", "level": "beginner",
                "category": "not-a-real-category", "duration_minutes": 5,
            }
        ],
    }
    bad_path = tmp_path / "bad_catalog.json"
    bad_path.write_text(json.dumps(bad_catalog))

    with pytest.raises(ValueError, match="not-a-real-category"):
        load_catalog(bad_path)


def test_load_catalog_accepts_item_referencing_known_category(tmp_path):
    import json

    good_catalog = {
        "categories": [{"id": "rag", "name": "RAG", "keywords": []}],
        "items": [
            {
                "id": "x", "title": "X", "type": "course", "level": "beginner",
                "category": "rag", "duration_minutes": 5,
            }
        ],
    }
    good_path = tmp_path / "good_catalog.json"
    good_path.write_text(json.dumps(good_catalog))

    catalog = load_catalog(good_path)
    assert catalog.items[0].category == "rag"


def test_category_name_returns_display_name_for_known_id():
    catalog = load_catalog()
    assert category_name(catalog, "rag") == "RAG"


def test_category_name_falls_back_to_id_for_unknown_id():
    catalog = load_catalog()
    assert category_name(catalog, "not-a-real-category") == "not-a-real-category"
