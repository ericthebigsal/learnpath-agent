import pytest
from pydantic import ValidationError

from models import (
    Catalog,
    CatalogItem,
    ItemType,
    Level,
    PlanDiff,
    PlanResponse,
    PlanStep,
    QuizQuestion,
    Track,
)


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
