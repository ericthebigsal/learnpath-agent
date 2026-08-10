import pytest
from pydantic import ValidationError

from models import (
    Catalog,
    Category,
    CatalogItem,
    CourseSection,
    DroppedItem,
    ItemType,
    Level,
    PlanDiff,
    PlanResponse,
    PlanStep,
    QuizQuestion,
)


def test_course_section_holds_heading_and_body():
    section = CourseSection(heading="How it works", body="A detailed explanation.")
    assert section.heading == "How it works"
    assert section.body == "A detailed explanation."


def test_course_section_defaults_diagram_to_empty_string():
    section = CourseSection(heading="How it works", body="A detailed explanation.")
    assert section.diagram == ""


def test_course_section_holds_a_diagram_reference():
    section = CourseSection(heading="How it works", body="Text.", diagram="rag-pipeline")
    assert section.diagram == "rag-pipeline"


def test_catalog_item_defaults_sections_to_empty_list():
    item = CatalogItem(
        id="x", title="X", type=ItemType.COURSE, level=Level.BEGINNER,
        category="rag", duration_minutes=10,
    )
    assert item.sections == []


def test_catalog_item_holds_sections():
    item = CatalogItem(
        id="x", title="X", type=ItemType.COURSE, level=Level.BEGINNER,
        category="rag", duration_minutes=10,
        sections=[CourseSection(heading="Intro", body="Some body text.")],
    )
    assert item.sections[0].heading == "Intro"


def test_dropped_item_holds_id_and_rationale():
    dropped = DroppedItem(item_id="rag-fundamentals", rationale="No longer relevant to your goal.")
    assert dropped.item_id == "rag-fundamentals"
    assert dropped.rationale == "No longer relevant to your goal."


def test_plan_response_defaults_dropped_to_empty_list():
    plan = PlanResponse(steps=[], summary="test")
    assert plan.dropped == []


def test_plan_response_holds_dropped_items():
    plan = PlanResponse(
        steps=[],
        summary="test",
        dropped=[DroppedItem(item_id="x", rationale="y")],
    )
    assert plan.dropped[0].item_id == "x"


def test_catalog_item_accepts_valid_field_values():
    item = CatalogItem(
        id="rag-fundamentals",
        title="RAG Fundamentals",
        type=ItemType.COURSE,
        level=Level.BEGINNER,
        category="rag",
        duration_minutes=15,
        content="Retrieval-augmented generation pairs a model with a knowledge source.",
        quiz=[
            QuizQuestion(
                question="What does RAG stand for?",
                options=["Retrieval-Augmented Generation", "Random Access Generator"],
                correct_index=0,
            )
        ],
    )

    assert item.type == "course"
    assert item.level == "beginner"
    assert item.category == "rag"
    assert item.certification_eligible is False
    assert item.related_item_ids == []


def test_catalog_item_rejects_invalid_enum_value():
    with pytest.raises(ValidationError):
        CatalogItem(
            id="bad-1",
            title="Bad",
            type="not-a-real-type",
            level="beginner",
            category="rag",
            duration_minutes=10,
        )


def test_catalog_item_requires_category_field():
    with pytest.raises(ValidationError):
        CatalogItem(
            id="bad-2",
            title="Bad",
            type=ItemType.COURSE,
            level=Level.BEGINNER,
            duration_minutes=10,
        )


def test_category_holds_id_name_and_keywords():
    category = Category(id="rag", name="RAG", keywords=["retrieval", "vector database"])
    assert category.id == "rag"
    assert category.name == "RAG"
    assert category.keywords == ["retrieval", "vector database"]


def test_category_defaults_keywords_to_empty_list():
    category = Category(id="rag", name="RAG")
    assert category.keywords == []


def test_catalog_holds_categories_and_items():
    catalog = Catalog(
        categories=[Category(id="rag", name="RAG")],
        items=[
            CatalogItem(
                id="a", title="A", type=ItemType.VIDEO, level=Level.BEGINNER,
                category="rag", duration_minutes=5,
            )
        ],
    )
    assert len(catalog.items) == 1
    assert catalog.categories[0].id == "rag"


def test_plan_response_holds_ordered_steps_and_summary():
    plan = PlanResponse(
        steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your stated goal.")],
        summary="Start with RAG fundamentals.",
    )
    assert plan.steps[0].item_id == "rag-fundamentals"
    assert plan.summary == "Start with RAG fundamentals."


def test_plan_diff_holds_four_change_lists():
    diff = PlanDiff(kept=["a"], added=["b"], removed=["c"], reordered=True)
    assert diff.kept == ["a"]
    assert diff.added == ["b"]
    assert diff.removed == ["c"]
    assert diff.reordered is True
