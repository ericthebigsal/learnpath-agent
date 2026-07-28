from catalog import load_catalog
from models import Level
from planner import current_level, filter_candidates


def test_filter_candidates_matches_track_named_in_goal_text():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "I want to learn about RAG", Level.BEGINNER, set())

    assert candidates, "expected at least one candidate"
    assert all(item.track.value == "RAG" for item in candidates)
    assert all(item.level in (Level.BEGINNER, Level.INTERMEDIATE) for item in candidates)


def test_filter_candidates_falls_back_to_all_tracks_when_goal_names_none():
    catalog = load_catalog()
    candidates = filter_candidates(
        catalog, "I just want to get better at my job", Level.BEGINNER, set()
    )

    tracks_present = {item.track.value for item in candidates}
    assert len(tracks_present) > 1, "expected multiple tracks when goal names no track"


def test_filter_candidates_excludes_completed_items():
    catalog = load_catalog()
    all_rag_beginner_ids = {
        item.id
        for item in catalog.items
        if item.track.value == "RAG" and item.level == Level.BEGINNER
    }
    one_completed = set(list(all_rag_beginner_ids)[:1])

    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, one_completed)

    assert not (one_completed & {item.id for item in candidates})


def test_current_level_starts_at_starting_level_with_no_progress():
    catalog = load_catalog()
    assert current_level(Level.BEGINNER, [], catalog) == Level.BEGINNER


def test_current_level_bumps_up_after_a_high_score_at_that_level():
    catalog = load_catalog()
    beginner_rag_item = next(
        item for item in catalog.items
        if item.track.value == "RAG" and item.level == Level.BEGINNER and item.type.value == "course"
    )
    progress = [{"item_id": beginner_rag_item.id, "quiz_score": 95.0}]

    assert current_level(Level.BEGINNER, progress, catalog) == Level.INTERMEDIATE


def test_current_level_does_not_bump_on_a_low_score():
    catalog = load_catalog()
    beginner_rag_item = next(
        item for item in catalog.items
        if item.track.value == "RAG" and item.level == Level.BEGINNER and item.type.value == "course"
    )
    progress = [{"item_id": beginner_rag_item.id, "quiz_score": 40.0}]

    assert current_level(Level.BEGINNER, progress, catalog) == Level.BEGINNER


def test_current_level_never_advances_past_advanced():
    catalog = load_catalog()
    advanced_items = [
        item for item in catalog.items
        if item.level == Level.ADVANCED and item.type.value == "course"
    ][:1]
    progress = [{"item_id": advanced_items[0].id, "quiz_score": 100.0}]

    assert current_level(Level.ADVANCED, progress, catalog) == Level.ADVANCED
