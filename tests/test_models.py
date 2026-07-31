import pytest
from pydantic import ValidationError

from models import (
    Catalog,
    CatalogItem,
    CourseSection,
    DroppedItem,
    ItemType,
    Level,
    PlanDiff,
    PlanResponse,
    PlanStep,
    QuizQuestion,
    Track,
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
        track=Track.RAG, duration_minutes=10,
    )
    assert item.sections == []


def test_catalog_item_holds_sections():
    item = CatalogItem(
        id="x", title="X", type=ItemType.COURSE, level=Level.BEGINNER,
        track=Track.RAG, duration_minutes=10,
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


def test_catalog_item_accepts_valid_enum_values():
    item = CatalogItem(
        id="rag-fundamentals",
        title="RAG Fundamentals",
        type=ItemType.COURSE,
        level=Level.BEGINNER,
        track=Track.RAG,
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
    assert item.track == "RAG"
    assert item.certification_eligible is False
    assert item.related_item_ids == []


def test_catalog_item_rejects_invalid_enum_value():
    with pytest.raises(ValidationError):
        CatalogItem(
            id="bad-1",
            title="Bad",
            type="not-a-real-type",
            level="beginner",
            track="RAG",
            duration_minutes=10,
        )


def test_catalog_holds_a_list_of_items():
    catalog = Catalog(
        items=[
            CatalogItem(
                id="a", title="A", type=ItemType.VIDEO, level=Level.BEGINNER,
                track=Track.RAG, duration_minutes=5,
            )
        ]
    )
    assert len(catalog.items) == 1


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
