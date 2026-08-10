# Catalog Category Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `Track` enum with a data-driven `Category`
record embedded in `catalog.json`, validated at load time instead of by
the Python type system.

**Architecture:** `CatalogItem.category` becomes a plain, validated
string (a `Category.id`) instead of an enum-typed field. `catalog.json`
gains a top-level `"categories"` array (id, display name, keywords)
alongside its existing `"items"` array. Every place that used to iterate
the `Track` enum (goal-keyword matching, the Explore filter dropdown,
certification-readiness) now iterates `catalog.categories` instead —
same behavior, data-driven source of truth.

**Tech Stack:** No new dependencies. Same Pydantic v2 models, same
`catalog.json`-as-source-of-truth pattern already in use.

## Global Constraints

- **Naming:** the catalog taxonomy concept is called `Category`
  everywhere (code, JSON, templates, query params). The existing,
  *unrelated* `track` concept — the `tracks` DB table, `create_track`,
  `get_tracks_for_user`, `/tracks`, `/path/{track_id}`, the
  `track_master` badge — is a user's personal learning journey and is
  **never touched** by this plan. If a task below doesn't explicitly
  mention a file, assume it's untouched.
- No admin UI, no DB table for categories in this pass — deferred to the
  multi-tenancy build-order step.
- `validate_catalog.py`'s external (`--file`) mode must keep validating
  already-existing external content (`docs/pilot-amperity/amperity-pilot-catalog.json`,
  and the Stripe taxonomy test artifact from a prior session, if still
  present) with zero changes to those files — they have no `"categories"`
  key and don't need one.
- Category ids are lowercase, hyphenated, ASCII (`"rag"`,
  `"llm-billing-cost-models"`) — stable and URL-safe. Category names are
  the exact current `Track` enum display values (`"RAG"`,
  `"LLM Billing & Cost Models"`) — unchanged, still what's shown to users.
- No em-dashes in any new copy/comments (existing repo convention);
  double-hyphens (` -- `) instead.

---

### Task 1: Data model — `Category` replaces `Track`

**Files:**
- Modify: `models.py:18-27` (delete `Track` enum), `models.py:42-53`
  (`CatalogItem`), `models.py:56-57` (`Catalog`)
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Category(BaseModel)` with fields `id: str`, `name: str`,
  `keywords: list[str] = []`. `CatalogItem.category: str`.
  `Catalog.categories: list[Category]`, `Catalog.items: list[CatalogItem]`.
  These exact names (`Category`, `.id`, `.name`, `.keywords`,
  `CatalogItem.category`, `Catalog.categories`) are what every later task
  imports and uses — do not rename them mid-plan.

- [ ] **Step 1: Write the failing tests**

Replace every `Track` reference in `tests/test_models.py` with the new
shape. Full replacement file:

```python
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
```

Note: `Category` isn't imported yet in that file's `from models import (...)` block above -- add it there too (alphabetically, between `Catalog` and `CatalogItem`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Category' from 'models'` (and `Track` no longer imported, so no failures from that side).

- [ ] **Step 3: Update `models.py`**

Delete the `Track` enum (current lines 18-27):

```python
class Track(str, Enum):
    LLM_FUNDAMENTALS = "LLM Fundamentals"
    RAG = "RAG"
    MULTI_AGENT_SYSTEMS = "Multi-Agent Systems"
    LLM_EVALUATION = "LLM Evaluation & Testing"
    AGENT_TOOLS_SKILLS = "Agent Tools & Skills"
    CONTEXT_ENGINEERING = "Context Engineering"
    LLM_BILLING = "LLM Billing & Cost Models"
    RESPONSIBLE_AI = "Responsible AI"
    AI_SECURITY = "AI Security & Risk"
```

Replace it with:

```python
class Category(BaseModel):
    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)
```

Update `CatalogItem` (current lines 42-53) — change the `track: Track`
field to `category: str`:

```python
class CatalogItem(BaseModel):
    id: str
    title: str
    type: ItemType
    level: Level
    category: str
    duration_minutes: int
    content: str = ""
    sections: list[CourseSection] = Field(default_factory=list)
    quiz: list[QuizQuestion] = Field(default_factory=list)
    certification_eligible: bool = False
    related_item_ids: list[str] = Field(default_factory=list)
```

Update `Catalog` (current lines 56-57) to add `categories`:

```python
class Catalog(BaseModel):
    categories: list[Category]
    items: list[CatalogItem]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_models.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: replace Track enum with data-driven Category model"
```

---

### Task 2: Migrate `data/catalog.json` to the new shape

This is a one-time, throwaway script — write it, run it once, verify its
output, then delete the script itself (not the data it produced).

**Files:**
- Create (temporarily): `scripts/migrate_categories.py`
- Modify: `data/catalog.json`

**Interfaces:**
- Consumes: nothing from Task 1 (operates on raw JSON via the stdlib
  `json` module, not through `models.py`).
- Produces: `data/catalog.json` in the shape
  `{"categories": [...], "items": [...]}`, where every item's old
  `"track"` key is replaced by a `"category"` key holding a category id.
  Later tasks (3+) depend on this file already being in this shape.

- [ ] **Step 1: Confirm the starting shape** (sanity check before writing the script)

Run:
```bash
source venv/bin/activate
python3 -c "
import json
data = json.loads(open('data/catalog.json').read())
print(type(data), len(data))
print(sorted(set(item['track'] for item in data)))
"
```
Expected output: `<class 'list'> 67` and exactly these 9 values:
`['AI Security & Risk', 'Agent Tools & Skills', 'Context Engineering', 'LLM Billing & Cost Models', 'LLM Evaluation & Testing', 'LLM Fundamentals', 'Multi-Agent Systems', 'RAG', 'Responsible AI']`

If the counts or values differ from this, stop and investigate before
proceeding — the hardcoded keyword seed data in Step 2 assumes exactly
these 9 category names.

- [ ] **Step 2: Write the migration script**

Create `scripts/migrate_categories.py`:

```python
"""One-time migration: data/catalog.json from a bare item list to
{"categories": [...], "items": [...]}. Run once, then delete this file.
"""
import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"

# Keyword lists copied verbatim from planner.py's TRACK_KEYWORDS (pre-migration)
# so goal-matching behavior is unchanged after this migration.
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "LLM Fundamentals": [
        "fundamentals", "basics", "how llms work", "transformer", "tokenization",
        "autoregressive", "scaling law", "model card", "open-weight", "open weight",
    ],
    "RAG": [
        "rag", "retrieval", "retrieval-augmented", "vector database", "vector db",
        "embeddings", "chunking", "reranking", "hybrid search",
    ],
    "Multi-Agent Systems": [
        "multi-agent", "multi agent", "agentic", "swarm", "orchestrator",
        "orchestration", "task decomposition",
    ],
    "LLM Evaluation & Testing": [
        "eval", "evaluation", "evaluating", "testing", "test set", "benchmark",
        "llm-as-judge", "llm as judge", "regression test", "red-team", "red team",
    ],
    "Agent Tools & Skills": [
        "tool calling", "function calling", "tool schema", "plugin", "agent tools",
        "agent skills",
    ],
    "Context Engineering": [
        "context window", "context engineering", "context budget", "memory",
        "lost in the middle", "context drift",
    ],
    "LLM Billing & Cost Models": [
        "cost", "billing", "pricing", "budget", "spend", "token cost",
        "prompt caching",
    ],
    "Responsible AI": [
        "ethics", "ethical", "bias", "fairness", "fair", "responsible ai", "privacy",
        "hallucination", "governance", "compliance", "regulation",
    ],
    "AI Security & Risk": [
        "security", "threat", "prompt injection", "injection", "vulnerability",
        "attack", "adversarial", "supply chain", "atlas", "owasp",
    ],
}

EXPECTED_NAMES = set(CATEGORY_KEYWORDS)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    data = json.loads(CATALOG_PATH.read_text())
    assert isinstance(data, list), "expected the pre-migration bare-list shape"

    names_present = {item["track"] for item in data}
    assert names_present == EXPECTED_NAMES, (
        f"track values don't match expected set; diff: "
        f"{names_present ^ EXPECTED_NAMES}"
    )

    categories = [
        {"id": slugify(name), "name": name, "keywords": CATEGORY_KEYWORDS[name]}
        for name in sorted(EXPECTED_NAMES)
    ]
    id_by_name = {c["name"]: c["id"] for c in categories}

    items = []
    for item in data:
        new_item = dict(item)
        track_name = new_item.pop("track")
        new_item["category"] = id_by_name[track_name]
        items.append(new_item)

    output = {"categories": categories, "items": items}
    CATALOG_PATH.write_text(json.dumps(output, indent=2) + "\n")

    print(f"Migrated {len(items)} items across {len(categories)} categories.")
    for c in categories:
        print(f"  {c['id']!r} <- {c['name']!r} ({len(c['keywords'])} keywords)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the migration script**

Run: `source venv/bin/activate && python3 scripts/migrate_categories.py`
Expected: prints `Migrated 67 items across 9 categories.` followed by one
line per category (e.g. `'ai-security-risk' <- 'AI Security & Risk' (10 keywords)'`).

- [ ] **Step 4: Verify the output shape**

Run:
```bash
python3 -c "
import json
data = json.loads(open('data/catalog.json').read())
assert isinstance(data, dict)
assert set(data.keys()) == {'categories', 'items'}
assert len(data['categories']) == 9
assert len(data['items']) == 67
ids = {c['id'] for c in data['categories']}
assert ids == {
    'llm-fundamentals', 'rag', 'multi-agent-systems',
    'llm-evaluation-testing', 'agent-tools-skills', 'context-engineering',
    'llm-billing-cost-models', 'responsible-ai', 'ai-security-risk',
}
assert all('category' in item and 'track' not in item for item in data['items'])
assert all(item['category'] in ids for item in data['items'])
print('OK')
"
```
Expected: `OK`

- [ ] **Step 5: Delete the migration script and commit the migrated data**

```bash
rm scripts/migrate_categories.py
rmdir scripts 2>/dev/null || true
git add data/catalog.json
git commit -m "data: migrate catalog.json from a Track list to a Category-aware shape"
```

(This commit intentionally leaves the rest of the codebase red — `catalog.py`
still expects the old bare-list shape and `CatalogItem` no longer has a
`track` field. Task 3 fixes that immediately next.)

---

### Task 3: Catalog loader — `catalog.py`

**Files:**
- Modify: `catalog.py` (all of it — currently 28 lines)
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Category`, `Catalog`, `CatalogItem` from `models.py` (Task 1);
  `data/catalog.json` in the new shape (Task 2).
- Produces: `load_catalog(path=DEFAULT_CATALOG_PATH) -> Catalog` (same
  signature as before). New: `category_name(catalog: Catalog, category_id: str) -> str`
  — later tasks (5, 6) depend on this exact name and signature for
  resolving a category id to its display name in templates.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_catalog.py` in full:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && pytest tests/test_catalog.py -v`
Expected: FAIL — `ImportError: cannot import name 'category_name' from 'catalog'`
(and, once that's fixed by Step 3 below, `load_catalog()` would still
fail against the new JSON shape until the loader itself is rewritten —
both failures are addressed together in Step 3).

- [ ] **Step 3: Rewrite `catalog.py`**

Full replacement:

```python
import json
from pathlib import Path

from models import Catalog, CatalogItem, Category, Level

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"

LEVEL_ORDER = [Level.BEGINNER, Level.INTERMEDIATE, Level.ADVANCED]


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    data = json.loads(Path(path).read_text())
    categories = [Category.model_validate(c) for c in data["categories"]]
    items = [CatalogItem.model_validate(item) for item in data["items"]]

    known_ids = {c.id for c in categories}
    for item in items:
        if item.category not in known_ids:
            raise ValueError(
                f"catalog item {item.id!r} references unknown category {item.category!r}"
            )

    return Catalog(categories=categories, items=items)


def get_item(catalog: Catalog, item_id: str) -> CatalogItem:
    for item in catalog.items:
        if item.id == item_id:
            return item
    raise KeyError(f"No catalog item with id {item_id!r}")


def category_name(catalog: Catalog, category_id: str) -> str:
    for category in catalog.categories:
        if category.id == category_id:
            return category.name
    return category_id


def levels_within(level: Level, spread: int = 1) -> list[Level]:
    idx = LEVEL_ORDER.index(level)
    lo = max(0, idx - spread)
    hi = min(len(LEVEL_ORDER) - 1, idx + spread)
    return LEVEL_ORDER[lo : hi + 1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_catalog.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add catalog.py tests/test_catalog.py
git commit -m "feat: load categories from catalog.json with referential-integrity check"
```

---

### Task 4: Planner — `planner.py`

**Files:**
- Modify: `planner.py:1-11` (imports, module constants), `planner.py:57-88`
  (`match_tracks`, `filter_candidates`), `planner.py:103-139`
  (`rule_based_plan`), `planner.py:211-258` (`build_prompt`),
  `planner.py:322-344` (`certification_ready_tracks`)
- Test: `tests/test_planner_candidates.py`, `tests/test_planner_plans.py`

**Interfaces:**
- Consumes: `Category`, `Catalog`, `CatalogItem` from `models.py` (Task 1);
  `catalog.category_name` is NOT used here (that's template-facing, Task 5/6) —
  planner.py works entirely in category ids and, for certification, names.
- Produces: `match_categories(goal_text: str, categories: list[Category]) -> list[str]`
  (renamed from `match_tracks`, now takes `categories` explicitly instead
  of reading a module constant, returns category **ids**).
  `certification_ready_categories(catalog: Catalog, progress: list[dict]) -> list[str]`
  (renamed from `certification_ready_tracks`, returns category **names**
  — unchanged from before, since this is display text). Both new names
  are what `app.py` (Task 5) imports.

- [ ] **Step 1: Write the failing tests**

In `tests/test_planner_candidates.py`, replace all 6 tests:

```python
from catalog import load_catalog
from models import Level
from planner import current_level, filter_candidates


def test_filter_candidates_matches_category_named_in_goal_text():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "I want to learn about RAG", Level.BEGINNER, set())

    assert candidates, "expected at least one candidate"
    assert all(item.category == "rag" for item in candidates)
    assert all(item.level in (Level.BEGINNER, Level.INTERMEDIATE) for item in candidates)


def test_filter_candidates_falls_back_to_all_categories_when_goal_names_none():
    catalog = load_catalog()
    candidates = filter_candidates(
        catalog, "I just want to get better at my job", Level.BEGINNER, set()
    )

    categories_present = {item.category for item in candidates}
    assert len(categories_present) > 1, "expected multiple categories when goal names none"


def test_filter_candidates_excludes_completed_items():
    catalog = load_catalog()
    all_rag_beginner_ids = {
        item.id
        for item in catalog.items
        if item.category == "rag" and item.level == Level.BEGINNER
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
        if item.category == "rag" and item.level == Level.BEGINNER and item.type.value == "course"
    )
    progress = [{"item_id": beginner_rag_item.id, "quiz_score": 95.0}]

    assert current_level(Level.BEGINNER, progress, catalog) == Level.INTERMEDIATE


def test_current_level_does_not_bump_on_a_low_score():
    catalog = load_catalog()
    beginner_rag_item = next(
        item for item in catalog.items
        if item.category == "rag" and item.level == Level.BEGINNER and item.type.value == "course"
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
```

In `tests/test_planner_plans.py`, apply these targeted changes (the file
is long — only the parts touching `Track`/`.track`/`certification_ready_tracks`
change; everything else stays exactly as-is):

- Import block (lines 1-15): remove `Track` from the `models` import, and
  rename `certification_ready_tracks` to `certification_ready_categories`
  in the `planner` import:
```python
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from catalog import LEVEL_ORDER, load_catalog
from models import CatalogItem, DroppedItem, Level, PlanResponse, PlanStep
from planner import (
    PASSING_THRESHOLD,
    build_prompt,
    certification_ready_categories,
    filter_candidates,
    gemini_plan,
    plan_or_replan,
    rule_based_plan,
)
```
- `test_rule_based_plan_puts_beginner_items_before_advanced_items` (lines
  40-64 in the old file): replace every `track=Track.RAG` with
  `category="rag"` (3 occurrences, one per `CatalogItem(...)`).
- `test_certification_ready_tracks_empty_with_no_progress` → rename to
  `test_certification_ready_categories_empty_with_no_progress`, body
  changes `certification_ready_tracks(catalog, [])` to
  `certification_ready_categories(catalog, [])`.
- `test_certification_ready_tracks_flags_track_after_all_items_pass` →
  rename to `test_certification_ready_categories_flags_category_after_all_items_pass`:
```python
def test_certification_ready_categories_flags_category_after_all_items_pass():
    catalog = load_catalog()
    rag_courses = [
        item for item in catalog.items
        if item.category == "rag" and item.type.value == "course" and not item.certification_eligible
    ]
    progress = [{"item_id": item.id, "quiz_score": 80.0} for item in rag_courses]

    assert "RAG" in certification_ready_categories(catalog, progress)
```
- `test_certification_ready_tracks_excludes_track_with_low_average` →
  rename to `test_certification_ready_categories_excludes_category_with_low_average`:
```python
def test_certification_ready_categories_excludes_category_with_low_average():
    catalog = load_catalog()
    rag_courses = [
        item for item in catalog.items
        if item.category == "rag" and item.type.value == "course" and not item.certification_eligible
    ]
    progress = [{"item_id": item.id, "quiz_score": 50.0} for item in rag_courses]

    assert "RAG" not in certification_ready_categories(catalog, progress)
```

Every other test in `test_planner_plans.py` (the `gemini_plan`,
`plan_or_replan`, `build_prompt` tests) references `"rag-fundamentals"`
by item id and never touches `Track`/`.track` directly — leave those
untouched.

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && pytest tests/test_planner_candidates.py tests/test_planner_plans.py -v`
Expected: FAIL — `ImportError` (`certification_ready_categories` doesn't
exist yet) and/or `AttributeError`/`ValidationError` on `.track` /
`track=Track.RAG`.

- [ ] **Step 3: Update `planner.py`**

Replace the imports and module constants (current lines 1-11):

```python
import logging
import time

from google.genai import types

from catalog import LEVEL_ORDER, levels_within
from models import Catalog, CatalogItem, Category, DroppedItem, Level, PlanDiff, PlanResponse, PlanStep

logger = logging.getLogger(__name__)
```

(The `TRACK_NAMES` and `TRACK_KEYWORDS` module-level constants, and the
comment above them, are deleted outright — that data now lives in
`catalog.json`, seeded by Task 2's migration.)

Replace `match_tracks` and `filter_candidates` (current lines 57-88):

```python
def match_categories(goal_text: str, categories: list[Category]) -> list[str]:
    """Return catalog category ids whose name or keywords appear in free-text goal.

    Checked in `categories` order so results are stable. Returns [] when
    nothing -- not even a keyword -- matches, which callers should treat
    as "don't guess, ask the learner to pick."
    """
    goal_lower = goal_text.lower()
    matched = []
    for category in categories:
        keywords = [category.name.lower()] + category.keywords
        if any(keyword in goal_lower for keyword in keywords):
            matched.append(category.id)
    return matched


def filter_candidates(
    catalog: Catalog, goal_text: str, level: Level, completed_item_ids: set[str]
) -> list[CatalogItem]:
    matched_categories = match_categories(goal_text, catalog.categories)
    allowed_levels = levels_within(level, spread=1)

    if matched_categories:
        candidates = [
            item
            for item in catalog.items
            if item.category in matched_categories and item.level in allowed_levels
        ]
    else:
        candidates = [item for item in catalog.items if item.level in allowed_levels]

    return [item for item in candidates if item.id not in completed_item_ids]
```

`current_level` (current lines 91-100) is unchanged — it never touched
`Track`.

In `rule_based_plan` (current lines 103-139), update the rationale
f-string (current line 115):

```python
            rationale=(
                f"Fallback rule: {item.level.value} level in {item.category}, "
                f"{item.duration_minutes} minutes."
            ),
```

(`item.category` is a plain string now, no `.value`.)

In `build_prompt` (current lines 211-258), update the candidate-line
f-string (current line 219):

```python
    candidate_lines = "\n".join(
        f"- {item.id}: {item.title} ({item.category}, {item.level.value}, {item.duration_minutes}m)"
        for item in candidates
    )
```

Replace `certification_ready_tracks` (current lines 322-344):

```python
def certification_ready_categories(catalog: Catalog, progress: list[dict]) -> list[str]:
    # Only plain `course` items are counted: `learning_path` bundles have no quiz of
    # their own (item.html renders no submit form when item.quiz is empty), so they
    # can never pick up a real progress row through the UI and must be excluded here.
    scores_by_id = {entry["item_id"]: entry["quiz_score"] for entry in progress}
    ready: list[str] = []

    for category in catalog.categories:
        category_items = [
            item
            for item in catalog.items
            if item.category == category.id
            and item.type.value == "course"
            and not item.certification_eligible
        ]
        if not category_items:
            continue
        if all(item.id in scores_by_id for item in category_items):
            average = sum(scores_by_id[item.id] for item in category_items) / len(category_items)
            if average >= PASSING_THRESHOLD:
                ready.append(category.name)

    return ready
```

(Returns `category.name`, not `category.id` — this is display text shown
directly in `path.html`'s "Certification-ready: ..." banner, and must
keep showing `"RAG"` / `"LLM Billing & Cost Models"`, not the lowercase
ids, to match today's behavior exactly.)

`plan_diff` (current lines 347-356) is unchanged — it never touched
`Track`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_planner_candidates.py tests/test_planner_plans.py -v`
Expected: PASS (6 + 21 tests)

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_candidates.py tests/test_planner_plans.py
git commit -m "feat: match/certify by data-driven categories instead of the Track enum"
```

---

### Task 5: App routes — `app.py`

**Files:**
- Modify: `app.py:14-24` (imports, `CATEGORY_NAMES` lookup + Jinja filter
  registration), `app.py:233-268` (`current_path`), `app.py:345-385` (`explore`)
- Test: `tests/test_explore.py:106-111`

**Interfaces:**
- Consumes: `catalog.category_name` (Task 3), `planner.certification_ready_categories`
  (Task 4).
- Produces: a registered Jinja filter `category_name` (usable in any
  template as `{{ item.category | category_name }}`) — Task 6 depends on
  this filter existing under exactly that name.

- [ ] **Step 1: Write the failing test**

In `tests/test_explore.py`, update `test_explore_filters_by_track`
(current lines 106-111):

```python
def test_explore_filters_by_category(client):
    response = client.get("/explore", params={"category": "rag"})

    assert response.status_code == 200
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    assert "What Is an LLM, Really?" not in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/test_explore.py::test_explore_filters_by_category -v`
Expected: FAIL — the `/explore` route doesn't accept a `category` query
param yet, so it's ignored and no filtering happens (both assertions
about presence/absence of course titles fail).

- [ ] **Step 3: Update `app.py`**

Update the import block (current lines 14-20) — remove `Track`, add
`category_name`:

```python
import auth
import db
import planner
import quiz as quiz_module
import badges
import review
from catalog import category_name, get_item, load_catalog
from models import Level, PlanResponse
from starter_paths import STARTER_PATHS, get_starter_path
```

Immediately after `CATALOG = load_catalog()` (current line 24), register
the Jinja filter:

```python
CATALOG = load_catalog()

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["css_version"] = int((BASE_DIR / "static" / "style.css").stat().st_mtime)
templates.env.filters["category_name"] = lambda category_id: category_name(CATALOG, category_id)
```

In `current_path` (current lines 233-268), update the
`certification_ready_tracks` call (current line 247):

```python
    ready_tracks = planner.certification_ready_categories(CATALOG, progress)
```

(The template context key stays `"ready_tracks"` — `path.html` already
reads that key and expects a list of display names, which is exactly
what `certification_ready_categories` returns. No template change needed
here.)

Replace the `explore` route in full (current lines 345-385):

```python
@app.get("/explore", response_class=HTMLResponse)
def explore(
    request: Request,
    category: str | None = None,
    level: str | None = None,
    active_track_id: int | None = None,
    no_match: bool = False,
    current_user: dict = Depends(get_current_user),
):
    items = CATALOG.items
    if category:
        items = [item for item in items if item.category == category]
    if level:
        items = [item for item in items if item.level.value == level]

    user_tracks = db.get_tracks_for_user(current_user["id"], DB_PATH)
    user_track_ids = {t["id"] for t in user_tracks}
    if active_track_id in user_track_ids:
        selected_track_id = active_track_id
    elif user_tracks:
        selected_track_id = user_tracks[0]["id"]
    else:
        selected_track_id = None

    return templates.TemplateResponse(
        request,
        "explore.html",
        {
            "request": request,
            "current_user": current_user,
            "items": items,
            "categories": CATALOG.categories,
            "levels": [lvl.value for lvl in Level],
            "selected_category": category or "",
            "selected_level": level or "",
            "user_tracks": user_tracks,
            "selected_track_id": selected_track_id,
            "starter_paths": STARTER_PATHS,
            "no_match": no_match,
        },
    )
```

(`active_track_id`, `user_tracks`, `selected_track_id` are the unrelated
user-journey concept and are untouched — only the catalog-filtering
parameter is renamed, from `track` to `category`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && pytest tests/test_explore.py -v`
Expected: PASS (all tests in the file, not just the one changed — this
confirms nothing else in `test_explore.py` broke)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_explore.py
git commit -m "feat: filter Explore by data-driven category instead of Track"
```

---

### Task 6: Templates

**Files:**
- Modify: `templates/explore.html`, `templates/explore_starter_preview.html`,
  `templates/item.html`, `templates/item_section.html`,
  `templates/item_quiz.html`, `templates/path.html`

**Interfaces:**
- Consumes: the `category_name` Jinja filter (Task 5); `categories`
  (a `list[Category]`) and `selected_category` in `explore.html`'s
  template context (Task 5).

No new automated tests for this task — `test_explore.py` (Task 5) and
`test_app.py` already exercise these templates by asserting on rendered
HTML strings, and the full-suite run in Task 8 is the safety net. Each
step below is a plain text substitution; do them exactly as shown.

- [ ] **Step 1: `templates/item.html`**

Line 5, `{{ item.track.value }}` becomes `{{ item.category | category_name }}`:

```html
  <p class="eyebrow">{{ item.category | category_name }} &middot; {{ item.level.value }}</p>
```

- [ ] **Step 2: `templates/item_section.html`**

Line 5, same substitution:

```html
<p class="eyebrow">{{ item.category | category_name }} &middot; {{ item.level.value }}</p>
```

- [ ] **Step 3: `templates/item_quiz.html`**

Line 4, same substitution:

```html
<p class="eyebrow">{{ item.category | category_name }} &middot; {{ item.level.value }}</p>
```

- [ ] **Step 4: `templates/path.html`**

Line 29 (inside the `steps` loop) and line 49 (inside the `candidates`
loop), same substitution in both places:

```html
        <span class="badge">{{ step.item.category | category_name }}</span>
```
```html
          <span class="badge badge-ghost">{{ candidate.category | category_name }}</span>
```

(Line 13's `{{ ready_tracks | join(", ") }}` is untouched — `ready_tracks`
already holds display names, per Task 5.)

- [ ] **Step 5: `templates/explore_starter_preview.html`**

Line 15, same substitution:

```html
        <span class="badge">{{ step.item.category | category_name }}</span>
```

- [ ] **Step 6: `templates/explore.html`**

Line 5 heading is unrelated copy ("Find your next track" refers to the
user-journey concept, not the catalog filter) — leave it as-is.

Replace the filter dropdown (current lines 26-33):

```html
  <div>
    <label for="category">Category</label>
    <select id="category" name="category">
      <option value="">All categories</option>
      {% for c in categories %}
      <option value="{{ c.id }}" {% if c.id == selected_category %}selected{% endif %}>{{ c.name }}</option>
      {% endfor %}
    </select>
  </div>
```

Line 68 (inside the `items` loop), same substitution as the other
templates:

```html
      <span class="badge">{{ item.category | category_name }}</span>
```

- [ ] **Step 7: Commit**

```bash
git add templates/explore.html templates/explore_starter_preview.html \
        templates/item.html templates/item_section.html \
        templates/item_quiz.html templates/path.html
git commit -m "feat: render category display names via the new category_name filter"
```

---

### Task 7: Validator — `validate_catalog.py`

**Files:**
- Modify: `.claude/skills/writing-catalog-courses/validate_catalog.py`
  (docstring at top, `main()`; add one new function)

**Interfaces:**
- Consumes: nothing from earlier tasks directly (this script reads raw
  JSON, not through `models.py`), but its default-mode behavior now
  depends on `data/catalog.json` being in the new shape (Task 2).
- Produces: no new importable interface — this is a CLI script, verified
  by manual invocation (Step 3below), matching how it's verified today
  (there's no `test_validate_catalog.py`).

- [ ] **Step 1: Update the module docstring**

Current lines 9-11 say the default mode expects "this app's pydantic
schema" without describing the shape. Replace lines 1-26 (the full
docstring) with:

```python
#!/usr/bin/env python3
"""Validation checks for course-catalog JSON files.

Run from the repo root (with venv activated):
    python .claude/skills/writing-catalog-courses/validate_catalog.py [item_id ...]
    python .claude/skills/writing-catalog-courses/validate_catalog.py --file path/to/other-catalog.json
    python .claude/skills/writing-catalog-courses/validate_catalog.py --file other.json --diagrams-dir some/svgs/

With no --file, checks this repo's own data/catalog.json and runs the FULL suite,
including this app's pydantic schema and a real render through its Jinja templates
-- that mode is specific to this app's Category/Level model and template conventions.
This repo's own catalog.json is an object shaped {"categories": [...], "items": [...]};
every item's "category" must reference a "categories" entry's "id".

With --file pointing anywhere else (a different tenant's course content, a pilot
file that was never merged into this repo), the schema/render checks that depend
on this app's own code are skipped automatically -- there's no Category model or
CatalogItem model to import for content that was never written against them.
External files may be EITHER shape: a bare list of items (no categories, "category"
treated as an unconstrained free-text label), or the {"categories": [...], "items": [...]}
object (in which case referential integrity -- every item's category exists in
categories -- is checked, the same way it is for this repo's own catalog).
What still runs, on ANY catalog-shaped JSON, is everything that doesn't require
this app's code: duplicate ids/headings, dangling related_item_ids, quiz option
count/bounds/duplicates, and the quiz guessability audit. Pass --diagrams-dir to
also check referenced diagram files exist for external content with its own
diagram set.

With no arguments (default mode only), trailing positional args narrow the
quiz-guessability report to just those item ids; structural checks still run
against the whole file, since a bad id elsewhere breaks everyone.
"""
```

- [ ] **Step 2: Add category extraction + referential check, update `main()`**

Add a new function right after `portable_structural_checks` (after
current line 72):

```python
def extract_items_and_categories(raw: dict | list) -> tuple[list[dict], list[dict] | None]:
    """Normalize either catalog shape to (items, categories).

    A bare list (legacy / category-less external content) has no
    categories -- returns None for that slot, meaning "don't check
    referential integrity." The {"categories": [...], "items": [...]}
    object shape always has a categories list, even if it's empty.
    """
    if isinstance(raw, list):
        return raw, None
    return raw["items"], raw["categories"]


def category_reference_checks(items: list[dict], categories: list[dict]) -> list[str]:
    problems = []
    known_ids = {c.get("id") for c in categories}
    for item in items:
        label = item.get("id", "<no id>")
        category = item.get("category")
        if category not in known_ids:
            problems.append(f"{label}: category {category!r} not in declared categories")
    return problems
```

In `main()`, the current body (lines 159-198) reads
`data = json.loads(target_file.read_text())` and passes `data` directly
(assumed to be a bare list) to `portable_structural_checks`,
`diagram_check`, and `quiz_guessability_report`. Replace the body from
`problems = []` (current line 172) through the end of the function:

```python
    problems = []
    raw = json.loads(target_file.read_text())
    items, categories = extract_items_and_categories(raw)

    if is_own_catalog:
        problems.extend(full_app_checks(target_ids))
        diagrams_dir = args.diagrams_dir or (REPO_ROOT / "static" / "diagrams")
    else:
        print(f"[external file: {target_file}] skipping this app's pydantic schema and template "
              f"render -- running portable checks only.")
        diagrams_dir = args.diagrams_dir

    problems.extend(portable_structural_checks(items))

    if categories is not None:
        problems.extend(category_reference_checks(items, categories))
        print(f"Categories: {len(categories)} declared, referential integrity checked.")
    else:
        print("Categories: none declared in this file, skipping referential-integrity check.")

    if diagrams_dir:
        problems.extend(diagram_check(items, diagrams_dir))
    else:
        print("Diagram files: skipped (no --diagrams-dir given)")

    quiz_guessability_report(items, target_ids)

    print()
    if problems:
        print(f"{len(problems)} structural problem(s):")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("No structural problems found.")
```

(`portable_structural_checks`, `diagram_check`, and
`quiz_guessability_report` themselves are unchanged -- they already take
a plain `list[dict]` of items, which is exactly what `items` now is
regardless of which shape the source file used.)

- [ ] **Step 3: Verify manually against all three known catalogs**

Run all three (this script has no pytest coverage, so this manual pass
is the actual verification):

```bash
source venv/bin/activate

# This repo's own catalog (new shape, default mode)
python .claude/skills/writing-catalog-courses/validate_catalog.py

# External, category-less catalog (bare list -- must still work unmodified)
python .claude/skills/writing-catalog-courses/validate_catalog.py --file docs/pilot-amperity/amperity-pilot-catalog.json
```

Expected for the first: ends with `No structural problems found.` and
prints `Categories: 9 declared, referential integrity checked.`

Expected for the second: ends with `No structural problems found.` (or
whatever pre-existing quiz-guessability numbers were already true for
that file) and prints `Categories: none declared in this file, skipping
referential-integrity check.` -- confirming the external file needed zero
changes.

If a Stripe taxonomy test artifact from a prior session still exists on
disk (check `ls /private/tmp/claude-501/*/scratchpad/stripe*` or similar
under this session's scratchpad path), run the same `--file` command
against it too as a second external-content spot check. If it's gone
(temp dirs are ephemeral), skip this -- the Amperity file is sufficient
coverage for "external, category-less content still validates."

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/writing-catalog-courses/validate_catalog.py
git commit -m "feat: validate category referential integrity in both validator modes"
```

---

### Task 8: Final verification

**Files:** none modified -- this task only runs things.

- [ ] **Step 1: Full automated test suite**

Run: `source venv/bin/activate && pytest -v`
Expected: all tests pass, zero failures, zero errors. (This is the first
point in the plan where the *entire* suite -- including `test_app.py`,
`test_badges.py`, `test_db.py`, etc., which were never directly touched
but import `app`/`CATALOG` at collection time -- is guaranteed green
together.)

- [ ] **Step 2: Validator, both modes** (repeat of Task 7 Step 3, as a
  final confirmation after all other tasks have landed)

```bash
python .claude/skills/writing-catalog-courses/validate_catalog.py
python .claude/skills/writing-catalog-courses/validate_catalog.py --file docs/pilot-amperity/amperity-pilot-catalog.json
```
Expected: both end with `No structural problems found.`

- [ ] **Step 3: Manual smoke test in a real browser**

```bash
source venv/bin/activate
uvicorn app:app --reload
```

Then, in a browser: register or log in, open `/explore`, confirm the
"Category" dropdown lists all 9 categories by their display names (e.g.
"RAG", "LLM Billing & Cost Models" -- not lowercase ids), pick one and
confirm the results filter correctly, and open any item's lesson page to
confirm its category badge shows the display name, not a raw id like
`rag` or `llm-billing-cost-models`. Also open `/path/{track_id}` for an
account with a certification-ready category and confirm the
"Certification-ready: ..." banner still shows proper display names.

Stop the server (Ctrl-C) once confirmed.

- [ ] **Step 4: Grep for any remaining `Track` references**

```bash
grep -rn "\bTrack\b" --include="*.py" . | grep -v venv | grep -v __pycache__
```

Expected: no output. (If anything shows up outside files this plan
already covered, stop and investigate before considering the plan done —
it means Task 1's blast-radius survey missed a usage.)
