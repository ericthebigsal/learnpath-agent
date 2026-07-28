# learnpath-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `learnpath-agent`, a small FastAPI web app that simulates an Amazon-Ads-Academy-shaped course catalog (course/learning-path/video content types, three levels, tagged tracks, dual certification model) whose content teaches modern AI/agentic concepts, and adds an LLM-driven planning agent that builds and continuously re-plans a personalized learning path for a learner based on their stated goal and quiz performance.

**Architecture:** A flat set of single-responsibility modules at the repo root — Pydantic schema (`models.py`), a JSON-backed catalog loader (`catalog.py`), a SQLite persistence layer for learner state (`db.py`), quiz grading (`quiz.py`), and the planning agent (`planner.py`, candidate filtering + a Gemini structured-output call + a deterministic rule-based fallback + plan-diffing) — wired together by a FastAPI app (`app.py`) with Jinja2 templates. Every function that calls the Gemini API takes the client as an explicit parameter, and `genai.Client()` is constructed in exactly one place, so the entire test suite runs offline with a mocked client and no API key, mirroring `JudgeDred`'s dependency-injection pattern.

**Tech Stack:** Python 3.10+, FastAPI, Jinja2, Pydantic v2, `google-genai` (Gemini free tier, `gemini-2.5-flash`), SQLite (stdlib `sqlite3`), pytest.

## Global Constraints

- Passing threshold for quiz scores is a fixed **70%** (spec §Planning agent). Score bands: <70 → insert remedial alternate; 70-89 → continue as planned; 90+ → may skip the paired alternate and advance a level/track.
- Candidate filtering rule (spec §Planning agent, made explicit): substring-match the goal text against the 7 track names (case-insensitive); if any match, restrict to those tracks at the learner's current level ±1; if none match, use all tracks at the learner's current level. Always exclude already-completed items.
- Every function that calls the Gemini API takes `client` as an explicit parameter (dependency injection). `genai.Client()` is constructed in exactly one place in `app.py`. No test may construct a real client or make a network call — every test either mocks the client or exercises the rule-based fallback / a wrapper function that's monkeypatched.
- Structured output from Gemini uses `response_schema=PlanResponse` (a Pydantic model) on `GenerateContentConfig`, reading `response.parsed` — never hand-parse raw text with `json.loads`.
- Model is `gemini-2.5-flash` (free tier) everywhere; every function that calls it accepts a `model: str` override.
- No auth, no multi-user accounts, no vector database, no real video/content hosting (spec §Non-goals).
- Web framework is **FastAPI** with Jinja2Templates — not Flask — matching `docs-dashboard` and `searcher`'s actual convention.
- Catalog composition target (spec §Catalog & data model): 7 tracks × 3 levels × 2 `course` items minimum (42), plus foundational items, bundled `learning_path` items (≥2 related items each), and `certification_eligible` capstones, landing at ~50-55 total items.
- The 7 tracks, exact names: `LLM Fundamentals`, `RAG`, `Multi-Agent Systems`, `LLM Evaluation & Testing`, `Agent Tools & Skills`, `Context Engineering`, `LLM Billing & Cost Models`.

---

## File Structure

```
learnpath-agent/
  requirements.txt
  pytest.ini
  .gitignore
  README.md
  models.py       # Pydantic schema: ItemType, Level, Track, QuizQuestion, CatalogItem, Catalog, PlanStep, PlanResponse, PlanDiff
  catalog.py       # load_catalog, get_item, levels_within, LEVEL_ORDER
  db.py            # SQLite: learners, progress, plan_log tables + CRUD
  quiz.py          # grade_quiz
  planner.py       # filter_candidates, current_level, rule_based_plan, build_prompt, gemini_plan, plan_or_replan, certification_ready_tracks, plan_diff
  app.py           # FastAPI routes + template wiring
  data/
    catalog.json   # ~50-55 seed catalog items
  templates/
    base.html
    start.html
    path.html
    item.html
    path_updated.html
    history.html
  static/
    style.css
  tests/
    test_models.py
    test_catalog.py
    test_db.py
    test_quiz.py
    test_planner_candidates.py
    test_planner_plans.py
    test_planner_diff.py
    test_app.py
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `static/style.css`
- Create: `tests/test_sanity.py`

**Interfaces:**
- Produces: a working pytest setup with `pythonpath = .`, so every later task can `import models`, `import db`, etc. from the repo root without a package/`src` layout.

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
jinja2==3.1.4
httpx==0.27.2
python-multipart==0.0.12
google-genai>=0.3.0
pydantic==2.9.2
pytest==8.3.3
```

(`python-multipart` is required by FastAPI/Starlette to parse HTML form posts — every screen in this app submits a form.)

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
*.egg-info/
.DS_Store
learnpath.db
```

- [ ] **Step 4: Create a minimal `static/style.css`**

```css
:root {
  color-scheme: light dark;
  --border: #d0d0d0;
  --muted: #666;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 860px;
  margin: 0 auto;
  padding: 1.5rem;
  line-height: 1.5;
}

.site-header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.75rem;
  margin-bottom: 1.5rem;
  font-weight: 600;
}

.site-header a {
  text-decoration: none;
  color: inherit;
}

form label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
}

form input, form select, form textarea {
  width: 100%;
  padding: 0.5rem;
  margin-bottom: 1rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  box-sizing: border-box;
}

button {
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: 4px;
  background: #2c5aa0;
  color: white;
  font-weight: 600;
  cursor: pointer;
}
```

- [ ] **Step 5: Write a sanity test to confirm the pytest config works**

```python
# tests/test_sanity.py
def test_pytest_is_configured():
    assert 1 + 1 == 2
```

- [ ] **Step 6: Run the test suite**

Run: `pytest -v`
Expected: `tests/test_sanity.py::test_pytest_is_configured PASSED`, 1 passed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini .gitignore static/style.css tests/test_sanity.py
git commit -m "chore: project scaffolding (requirements, pytest config, base styles)"
```

---

### Task 2: Pydantic schema

**Files:**
- Create: `models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `ItemType`, `Level`, `Track`, `QuizQuestion`, `CatalogItem`, `Catalog`, `PlanStep`, `PlanResponse`, `PlanDiff` — used by every later task.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: Implement `models.py`**

```python
from enum import Enum

from pydantic import BaseModel, Field


class ItemType(str, Enum):
    COURSE = "course"
    LEARNING_PATH = "learning_path"
    VIDEO = "video"


class Level(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Track(str, Enum):
    LLM_FUNDAMENTALS = "LLM Fundamentals"
    RAG = "RAG"
    MULTI_AGENT_SYSTEMS = "Multi-Agent Systems"
    LLM_EVALUATION = "LLM Evaluation & Testing"
    AGENT_TOOLS_SKILLS = "Agent Tools & Skills"
    CONTEXT_ENGINEERING = "Context Engineering"
    LLM_BILLING = "LLM Billing & Cost Models"


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int


class CatalogItem(BaseModel):
    id: str
    title: str
    type: ItemType
    level: Level
    track: Track
    duration_minutes: int
    content: str = ""
    quiz: list[QuizQuestion] = Field(default_factory=list)
    certification_eligible: bool = False
    related_item_ids: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    items: list[CatalogItem]


class PlanStep(BaseModel):
    item_id: str
    rationale: str


class PlanResponse(BaseModel):
    steps: list[PlanStep]
    summary: str


class PlanDiff(BaseModel):
    kept: list[str]
    added: list[str]
    removed: list[str]
    reordered: bool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add Pydantic schema for catalog items, plans, and plan diffs"
```

---

### Task 3: Catalog loader and seed data

**Files:**
- Create: `catalog.py`
- Create: `data/catalog.json`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Catalog`, `CatalogItem`, `Level`, `Track` (Task 2).
- Produces: `load_catalog(path=DEFAULT_CATALOG_PATH) -> Catalog`, `get_item(catalog, item_id) -> CatalogItem`, `levels_within(level, spread=1) -> list[Level]`, `LEVEL_ORDER` — all consumed by `planner.py` (Tasks 6-10) and `app.py` (Tasks 11-14).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_catalog.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog'` (and `data/catalog.json` doesn't exist yet).

- [ ] **Step 3: Implement `catalog.py`**

```python
import json
from pathlib import Path

from models import Catalog, CatalogItem, Level

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog.json"

LEVEL_ORDER = [Level.BEGINNER, Level.INTERMEDIATE, Level.ADVANCED]


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    data = json.loads(Path(path).read_text())
    return Catalog(items=[CatalogItem.model_validate(item) for item in data])


def get_item(catalog: Catalog, item_id: str) -> CatalogItem:
    for item in catalog.items:
        if item.id == item_id:
            return item
    raise KeyError(f"No catalog item with id {item_id!r}")


def levels_within(level: Level, spread: int = 1) -> list[Level]:
    idx = LEVEL_ORDER.index(level)
    lo = max(0, idx - spread)
    hi = min(len(LEVEL_ORDER) - 1, idx + spread)
    return LEVEL_ORDER[lo : hi + 1]
```

- [ ] **Step 4: Author `data/catalog.json`**

This is the real content-authoring step. `data/catalog.json` is a JSON array of objects matching `CatalogItem`'s schema. Two fully-worked examples below set the quality bar — real, substantive lesson text (not filler) and quizzes that test judgment, not just recall:

```json
[
  {
    "id": "rag-fundamentals",
    "title": "RAG Fundamentals: Retrieval Meets Generation",
    "type": "course",
    "level": "beginner",
    "track": "RAG",
    "duration_minutes": 15,
    "content": "Retrieval-Augmented Generation (RAG) pairs a language model with an external knowledge source so it can answer questions using information it was never trained on. Instead of relying only on what the model memorized during training, a RAG system retrieves relevant text chunks from a document store at query time and inserts them into the model's prompt as context. This course walks through the three core stages of a RAG pipeline: indexing (splitting source documents into chunks and storing them so they can be searched later), retrieval (given a user's question, finding the chunks most relevant to it), and generation (handing the retrieved chunks to the model along with the original question so it can produce a grounded answer). You'll learn why chunking strategy matters -- split documents at the wrong boundaries and you separate a question from its answer before the model even sees it -- and why 'stuffing everything into a huge context window' is not the same thing as RAG: a system with no retrieval step, just a large prompt, has no way to prioritize what's actually relevant, and costs far more in tokens. By the end of this course you'll be able to explain, in plain language, what problem RAG solves, what its three stages are, and one concrete failure mode that breaks the pipeline even when the underlying model is capable.",
    "quiz": [
      {
        "question": "What are the three core stages of a RAG pipeline, in order?",
        "options": ["Indexing, retrieval, generation", "Training, fine-tuning, deployment", "Generation, retrieval, indexing", "Chunking, training, inference"],
        "correct_index": 0
      },
      {
        "question": "Why is 'just stuffing everything into a huge context window' not the same as RAG?",
        "options": ["It uses a different programming language", "It has no retrieval step to prioritize what's relevant, and costs more tokens", "It only works with images, not text", "It requires a GPU cluster to run"],
        "correct_index": 1
      },
      {
        "question": "Why does chunking strategy matter in a RAG system?",
        "options": ["It doesn't matter, any chunk size works equally well", "Bad chunk boundaries can separate a question from its answer before the model sees it", "Chunking only affects how fast the UI renders", "Chunking is only relevant for image data"],
        "correct_index": 1
      }
    ],
    "certification_eligible": false,
    "related_item_ids": []
  },
  {
    "id": "rag-bootcamp",
    "title": "RAG Bootcamp: From Fundamentals to Production Patterns",
    "type": "learning_path",
    "level": "beginner",
    "track": "RAG",
    "duration_minutes": 45,
    "content": "A bundled sequence covering RAG from first principles through common production pitfalls: what problem retrieval-augmented generation solves, how chunking and retrieval quality affect answer accuracy, and how teams evaluate whether a RAG system is actually working. Complete the linked courses in order.",
    "quiz": [],
    "certification_eligible": false,
    "related_item_ids": ["rag-fundamentals", "rag-chunking-strategies", "rag-evaluation-basics"]
  },
  {
    "id": "rag-capstone-certification",
    "title": "RAG Practitioner Certification Assessment",
    "type": "course",
    "level": "advanced",
    "track": "RAG",
    "duration_minutes": 30,
    "content": "This capstone assessment validates practical RAG knowledge across indexing, retrieval quality, and evaluation. Before attempting it, you should be comfortable explaining chunking tradeoffs, the difference between recall and precision in a retrieval step, and how to detect when a RAG system is hallucinating despite having the right document retrieved. The questions probe judgment calls, not just definitions: given a scenario where a RAG system retrieves the correct document but still gives a wrong answer, can you identify whether the fault lies in retrieval, prompt assembly, or the generation step itself? Passing this assessment is meant to signal you could debug a real RAG system in production, not just describe one in the abstract.",
    "quiz": [
      {"question": "A RAG system retrieves the correct source document but still answers incorrectly. Where is the fault most likely to be?", "options": ["Always the retriever", "Could be prompt assembly or generation, not necessarily retrieval", "Always the vector database", "Always the chunk size"], "correct_index": 1},
      {"question": "What does 'recall' measure in a retrieval step?", "options": ["How fast the query runs", "The fraction of relevant documents that were actually retrieved", "How many tokens the answer uses", "The model's temperature setting"], "correct_index": 1},
      {"question": "Which of these is a sign a RAG system may be hallucinating despite good retrieval?", "options": ["The answer cites the retrieved document accurately", "The answer includes specific facts not present in any retrieved chunk", "The answer is short", "The answer takes longer to generate"], "correct_index": 1},
      {"question": "What is this capstone primarily assessing?", "options": ["Memorized definitions only", "Practical judgment about where failures occur across the RAG pipeline", "Typing speed", "Knowledge of an unrelated programming language"], "correct_index": 1}
    ],
    "certification_eligible": true,
    "related_item_ids": []
  }
]
```

Author the remaining items to this same bar (200+ characters of real, specific lesson content per course item; quizzes that test judgment/application, not just term recall) until the file satisfies this exact composition:

- **42 `course` items**: for each of the 7 tracks (`LLM Fundamentals`, `RAG`, `Multi-Agent Systems`, `LLM Evaluation & Testing`, `Agent Tools & Skills`, `Context Engineering`, `LLM Billing & Cost Models`) × each of the 3 levels (`beginner`, `intermediate`, `advanced`), write exactly 2 `course` items. `rag-fundamentals` above is one of the two for `RAG`/`beginner` — you still need one more RAG/beginner course (e.g. `rag-chunking-strategies`), plus two each for RAG/intermediate, RAG/advanced (the capstone above does NOT count toward this 2-per-cell minimum, since capstones are counted separately), and two each for every level of the other 6 tracks.
- **5 additional foundational `course` items**, all in the `LLM Fundamentals` track (any level), covering broad concepts that don't fit neatly into one of the other 6 tracks — e.g. "What Is an LLM, Really?", "Tokens, Context Windows, and Why They Matter", "Choosing the Right Model for the Job", "Reading a Model Card", "Open-Weight vs. Closed Models". These are on top of the 6 `LLM Fundamentals` items already counted above.
- **3 `learning_path` items**, each with `related_item_ids` pointing at 2 or more real `course` ids that exist elsewhere in the same file. `rag-bootcamp` above is one; author 2 more for two other tracks.
- **4 `certification_eligible` capstone `course` items** (advanced level, one each for 4 different tracks), each with a 4-question quiz in the style of `rag-capstone-certification` above.

That totals 42 + 5 + 3 + 4 = 54 items, inside the ~50-55 target.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_catalog.py -v`
Expected: 7 passed. If a count assertion fails, it names exactly which track/level cell or category is short — add items there.

- [ ] **Step 6: Commit**

```bash
git add catalog.py data/catalog.json tests/test_catalog.py
git commit -m "feat: add catalog loader and 54-item seed catalog of AI-concept courses"
```

---

### Task 4: SQLite persistence layer

**Files:**
- Create: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `init_db(db_path)`, `create_learner(goal_text, starting_level, db_path) -> dict`, `get_learner(learner_id, db_path) -> dict | None`, `record_progress(learner_id, item_id, quiz_score, db_path) -> dict`, `get_progress(learner_id, db_path) -> list[dict]`, `log_plan(learner_id, plan: dict, trigger, db_path) -> dict`, `get_plan_log(learner_id, db_path) -> list[dict]`, `get_latest_plan(learner_id, db_path) -> dict | None` — all consumed by `app.py` (Tasks 11-14) and by `planner.py`'s tests (which use `dict` shapes matching `get_progress`'s output: `{"item_id": str, "quiz_score": float, ...}`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db.py
import db


def test_init_db_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise on a second call


def test_create_and_get_learner(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)

    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    assert learner["goal_text"] == "Learn RAG basics"
    assert learner["starting_level"] == "beginner"
    assert isinstance(learner["id"], int)

    fetched = db.get_learner(learner["id"], db_path)
    assert fetched == learner

    assert db.get_learner(9999, db_path) is None


def test_record_and_get_progress(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    db.record_progress(learner["id"], "rag-fundamentals", 85.0, db_path)
    db.record_progress(learner["id"], "rag-chunking-strategies", 60.0, db_path)

    progress = db.get_progress(learner["id"], db_path)

    assert len(progress) == 2
    assert progress[0]["item_id"] == "rag-fundamentals"
    assert progress[0]["quiz_score"] == 85.0
    assert progress[1]["item_id"] == "rag-chunking-strategies"


def test_log_plan_and_get_latest_plan(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    plan = {
        "steps": [{"item_id": "rag-fundamentals", "rationale": "Matches your goal."}],
        "summary": "Start with RAG fundamentals.",
    }
    logged = db.log_plan(learner["id"], plan, "initial", db_path)

    assert logged["trigger"] == "initial"
    assert logged["steps"] == plan["steps"]
    assert logged["summary"] == plan["summary"]

    latest = db.get_latest_plan(learner["id"], db_path)
    assert latest["steps"] == plan["steps"]
    assert latest["summary"] == plan["summary"]


def test_get_latest_plan_returns_none_when_no_plans_logged(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    assert db.get_latest_plan(learner["id"], db_path) is None


def test_get_plan_log_returns_all_plans_in_order(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    db.log_plan(learner["id"], {"steps": [], "summary": "first"}, "initial", db_path)
    db.log_plan(learner["id"], {"steps": [], "summary": "second"}, "quiz_result", db_path)

    log = db.get_plan_log(learner["id"], db_path)

    assert [entry["summary"] for entry in log] == ["first", "second"]
    assert [entry["trigger"] for entry in log] == ["initial", "quiz_result"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implement `db.py`**

```python
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "learnpath.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_text TEXT NOT NULL,
    starting_level TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    quiz_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    trigger TEXT NOT NULL
);
"""


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def create_learner(goal_text: str, starting_level: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO learners (goal_text, starting_level, created_at) VALUES (?, ?, ?)",
            (goal_text, starting_level, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM learners WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_learner(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM learners WHERE id = ?", (learner_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def record_progress(
    learner_id: int, item_id: str, quiz_score: float, db_path: str = DEFAULT_DB_PATH
) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO progress (learner_id, item_id, completed_at, quiz_score) "
            "VALUES (?, ?, ?, ?)",
            (learner_id, item_id, now, quiz_score),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM progress WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_progress(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM progress WHERE learner_id = ? ORDER BY id ASC", (learner_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _plan_row_to_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    plan = json.loads(result.pop("plan_json"))
    result["steps"] = plan["steps"]
    result["summary"] = plan["summary"]
    return result


def log_plan(learner_id: int, plan: dict, trigger: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO plan_log (learner_id, created_at, plan_json, trigger) "
            "VALUES (?, ?, ?, ?)",
            (learner_id, now, json.dumps(plan), trigger),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM plan_log WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _plan_row_to_dict(row)
    finally:
        conn.close()


def get_plan_log(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM plan_log WHERE learner_id = ? ORDER BY id ASC", (learner_id,)
        ).fetchall()
        return [_plan_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_plan(learner_id: int, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM plan_log WHERE learner_id = ? ORDER BY id DESC LIMIT 1",
            (learner_id,),
        ).fetchone()
        return _plan_row_to_dict(row) if row else None
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add SQLite persistence for learners, progress, and plan history"
```

---

### Task 5: Quiz grading

**Files:**
- Create: `quiz.py`
- Test: `tests/test_quiz.py`

**Interfaces:**
- Consumes: `QuizQuestion` (Task 2).
- Produces: `grade_quiz(quiz, answers) -> float` — consumed by `app.py` (Task 13).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_quiz.py
from models import QuizQuestion
from quiz import grade_quiz


def make_quiz():
    return [
        QuizQuestion(question="Q1", options=["a", "b"], correct_index=0),
        QuizQuestion(question="Q2", options=["a", "b"], correct_index=1),
        QuizQuestion(question="Q3", options=["a", "b"], correct_index=0),
        QuizQuestion(question="Q4", options=["a", "b"], correct_index=1),
    ]


def test_grade_quiz_all_correct_scores_100():
    assert grade_quiz(make_quiz(), [0, 1, 0, 1]) == 100.0


def test_grade_quiz_all_wrong_scores_0():
    assert grade_quiz(make_quiz(), [1, 0, 1, 0]) == 0.0


def test_grade_quiz_partial_score_rounds_to_two_decimals():
    # 3 out of 4 correct = 75.0
    assert grade_quiz(make_quiz(), [0, 1, 0, 0]) == 75.0


def test_grade_quiz_empty_quiz_scores_100():
    assert grade_quiz([], []) == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_quiz.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quiz'`

- [ ] **Step 3: Implement `quiz.py`**

```python
from models import QuizQuestion


def grade_quiz(quiz: list[QuizQuestion], answers: list[int]) -> float:
    if not quiz:
        return 100.0
    correct = sum(
        1 for question, answer in zip(quiz, answers) if answer == question.correct_index
    )
    return round(100 * correct / len(quiz), 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_quiz.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add quiz.py tests/test_quiz.py
git commit -m "feat: add deterministic quiz grading"
```

---

### Task 6: Candidate filtering and current-level tracking

**Files:**
- Create: `planner.py`
- Test: `tests/test_planner_candidates.py`

**Interfaces:**
- Consumes: `Catalog`, `CatalogItem`, `Level`, `Track` (Task 2), `LEVEL_ORDER`, `levels_within` (Task 3).
- Produces: `TRACK_NAMES`, `filter_candidates(catalog, goal_text, level, completed_item_ids) -> list[CatalogItem]`, `current_level(starting_level, progress, catalog) -> Level` — consumed by `plan_or_replan` (Task 9).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_planner_candidates.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner_candidates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planner'`

- [ ] **Step 3: Implement the first half of `planner.py`**

```python
from catalog import LEVEL_ORDER, levels_within
from models import Catalog, CatalogItem, Level, Track

TRACK_NAMES = [track.value for track in Track]


def filter_candidates(
    catalog: Catalog, goal_text: str, level: Level, completed_item_ids: set[str]
) -> list[CatalogItem]:
    goal_lower = goal_text.lower()
    matched_tracks = [name for name in TRACK_NAMES if name.lower() in goal_lower]
    allowed_levels = levels_within(level, spread=1)

    if matched_tracks:
        candidates = [
            item
            for item in catalog.items
            if item.track.value in matched_tracks and item.level in allowed_levels
        ]
    else:
        candidates = [item for item in catalog.items if item.level in allowed_levels]

    return [item for item in candidates if item.id not in completed_item_ids]


def current_level(starting_level: Level, progress: list[dict], catalog: Catalog) -> Level:
    idx = LEVEL_ORDER.index(starting_level)
    items_by_id = {item.id: item for item in catalog.items}

    for entry in progress:
        item = items_by_id.get(entry["item_id"])
        if item is not None and item.level == LEVEL_ORDER[idx] and entry["quiz_score"] >= 90:
            idx = min(idx + 1, len(LEVEL_ORDER) - 1)

    return LEVEL_ORDER[idx]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner_candidates.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_candidates.py
git commit -m "feat: add candidate filtering and current-level tracking"
```

---

### Task 7: Rule-based fallback planner

**Files:**
- Modify: `planner.py`
- Test: `tests/test_planner_plans.py`

**Interfaces:**
- Consumes: `CatalogItem`, `PlanResponse`, `PlanStep` (Task 2).
- Produces: `rule_based_plan(candidates, limit=5) -> PlanResponse` — consumed by `plan_or_replan` (Task 9) as the fallback path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_planner_plans.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planner_plans.py -v`
Expected: FAIL — `ImportError: cannot import name 'rule_based_plan' from 'planner'`

- [ ] **Step 3: Add `rule_based_plan` to `planner.py`**

Add this import and function to the existing `planner.py` from Task 6:

```python
from models import Catalog, CatalogItem, Level, PlanResponse, PlanStep, Track
```

```python
def rule_based_plan(candidates: list[CatalogItem], limit: int = 5) -> PlanResponse:
    ordered = sorted(candidates, key=lambda item: (item.level.value, item.duration_minutes))[:limit]
    steps = [
        PlanStep(
            item_id=item.id,
            rationale=(
                f"Fallback rule: {item.level.value} level in {item.track.value}, "
                f"{item.duration_minutes} minutes."
            ),
        )
        for item in ordered
    ]
    return PlanResponse(
        steps=steps,
        summary="Fallback rule-based plan (LLM unavailable): candidates ordered by level then duration.",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planner_plans.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_plans.py
git commit -m "feat: add deterministic rule-based fallback planner"
```

---

### Task 8: Gemini structured-output planner

**Files:**
- Modify: `planner.py`
- Modify (append): `tests/test_planner_plans.py`

**Interfaces:**
- Consumes: `PlanResponse` (Task 2), `google.genai.types`.
- Produces: `build_prompt(goal_text, level, progress, candidates) -> str`, `gemini_plan(client, goal_text, level, progress, candidates, model=PLANNER_MODEL) -> PlanResponse` — consumed by `plan_or_replan` (Task 9).

- [ ] **Step 1: Append the failing tests**

```python
# append to tests/test_planner_plans.py
from types import SimpleNamespace
from unittest.mock import Mock

from planner import build_prompt, gemini_plan
from models import PlanResponse, PlanStep


def test_build_prompt_includes_goal_progress_and_candidates():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())[:2]
    progress = [{"item_id": "rag-fundamentals", "quiz_score": 85.0}]

    prompt = build_prompt("Learn RAG", Level.BEGINNER, progress, candidates)

    assert "Learn RAG" in prompt
    assert "beginner" in prompt
    assert "rag-fundamentals" in prompt
    assert "85.0" in prompt
    for candidate in candidates:
        assert candidate.id in prompt


def test_gemini_plan_returns_parsed_plan_response():
    client = Mock()
    expected_plan = PlanResponse(
        steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
        summary="Start with RAG fundamentals.",
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=expected_plan)

    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    result = gemini_plan(client, "Learn RAG", Level.BEGINNER, [], candidates)

    assert result == expected_plan
    client.models.generate_content.assert_called_once()
    _, kwargs = client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-2.5-flash"
    assert kwargs["config"].response_schema is PlanResponse
    assert kwargs["config"].response_mime_type == "application/json"
    assert "Learn RAG" in kwargs["contents"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner_plans.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_prompt' from 'planner'`

- [ ] **Step 3: Add `build_prompt` and `gemini_plan` to `planner.py`**

Add this import and these two functions to `planner.py`:

```python
from google.genai import types
```

```python
PLANNER_MODEL = "gemini-2.5-flash"


def build_prompt(
    goal_text: str, level: Level, progress: list[dict], candidates: list[CatalogItem]
) -> str:
    candidate_lines = "\n".join(
        f"- {item.id}: {item.title} ({item.track.value}, {item.level.value}, {item.duration_minutes}m)"
        for item in candidates
    )
    if progress:
        progress_lines = "\n".join(
            f"- {entry['item_id']}: scored {entry['quiz_score']}%" for entry in progress
        )
    else:
        progress_lines = "None yet."

    return (
        "You are an adaptive learning-path planner for an AI-concepts course catalog.\n\n"
        f"Learner goal: {goal_text}\n"
        f"Learner level: {level.value}\n\n"
        f"Completed items and quiz scores so far:\n{progress_lines}\n\n"
        "Candidate items available to recommend next (choose and order a subset of these; "
        "never invent an id that isn't listed):\n"
        f"{candidate_lines}\n\n"
        "Return an ordered list of item ids to study next, a one-line rationale for each, "
        "and a one-to-two-sentence overall summary of the plan."
    )


def gemini_plan(
    client,
    goal_text: str,
    level: Level,
    progress: list[dict],
    candidates: list[CatalogItem],
    model: str = PLANNER_MODEL,
) -> PlanResponse:
    prompt = build_prompt(goal_text, level, progress, candidates)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PlanResponse,
        ),
    )
    return response.parsed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner_plans.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_plans.py
git commit -m "feat: add Gemini structured-output planner call"
```

---

### Task 9: Plan orchestration and certification readiness

**Files:**
- Modify: `planner.py`
- Modify (append): `tests/test_planner_plans.py`

**Interfaces:**
- Consumes: `filter_candidates`, `current_level`, `rule_based_plan`, `gemini_plan` (Tasks 6-8).
- Produces: `PASSING_THRESHOLD`, `plan_or_replan(client, catalog, learner, progress) -> tuple[PlanResponse, bool]`, `certification_ready_tracks(catalog, progress) -> list[str]` — both consumed by `app.py` (Tasks 11-14).

- [ ] **Step 1: Append the failing tests**

```python
# append to tests/test_planner_plans.py
from planner import certification_ready_tracks, plan_or_replan


def test_plan_or_replan_uses_gemini_plan_when_client_succeeds():
    client = Mock()
    expected_plan = PlanResponse(
        steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
        summary="Start with RAG.",
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=expected_plan)

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback = plan_or_replan(client, catalog, learner, [])

    assert plan == expected_plan
    assert used_fallback is False


def test_plan_or_replan_falls_back_when_gemini_call_raises():
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("rate limited")

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback = plan_or_replan(client, catalog, learner, [])

    assert used_fallback is True
    assert len(plan.steps) > 0


def test_certification_ready_tracks_empty_with_no_progress():
    catalog = load_catalog()
    assert certification_ready_tracks(catalog, []) == []


def test_certification_ready_tracks_flags_track_after_all_items_pass():
    catalog = load_catalog()
    rag_courses = [
        item for item in catalog.items
        if item.track.value == "RAG" and item.type.value == "course" and not item.certification_eligible
    ]
    progress = [{"item_id": item.id, "quiz_score": 80.0} for item in rag_courses]

    assert "RAG" in certification_ready_tracks(catalog, progress)


def test_certification_ready_tracks_excludes_track_with_low_average():
    catalog = load_catalog()
    rag_courses = [
        item for item in catalog.items
        if item.track.value == "RAG" and item.type.value == "course" and not item.certification_eligible
    ]
    progress = [{"item_id": item.id, "quiz_score": 50.0} for item in rag_courses]

    assert "RAG" not in certification_ready_tracks(catalog, progress)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner_plans.py -v`
Expected: FAIL — `ImportError: cannot import name 'plan_or_replan' from 'planner'`

- [ ] **Step 3: Add `plan_or_replan` and `certification_ready_tracks` to `planner.py`**

```python
PASSING_THRESHOLD = 70.0


def plan_or_replan(
    client, catalog: Catalog, learner: dict, progress: list[dict]
) -> tuple[PlanResponse, bool]:
    completed_ids = {entry["item_id"] for entry in progress}
    level = current_level(Level(learner["starting_level"]), progress, catalog)
    candidates = filter_candidates(catalog, learner["goal_text"], level, completed_ids)

    try:
        plan = gemini_plan(client, learner["goal_text"], level, progress, candidates)
        return plan, False
    except Exception:
        return rule_based_plan(candidates), True


def certification_ready_tracks(catalog: Catalog, progress: list[dict]) -> list[str]:
    # Only plain `course` items are counted: `learning_path` bundles have no quiz of
    # their own (item.html renders no submit form when item.quiz is empty), so they
    # can never pick up a real progress row through the UI and must be excluded here.
    scores_by_id = {entry["item_id"]: entry["quiz_score"] for entry in progress}
    ready: list[str] = []

    for track_name in TRACK_NAMES:
        track_items = [
            item
            for item in catalog.items
            if item.track.value == track_name
            and item.type.value == "course"
            and not item.certification_eligible
        ]
        if not track_items:
            continue
        if all(item.id in scores_by_id for item in track_items):
            average = sum(scores_by_id[item.id] for item in track_items) / len(track_items)
            if average >= PASSING_THRESHOLD:
                ready.append(track_name)

    return ready
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner_plans.py -v`
Expected: 8 passed (3 from Task 8 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_plans.py
git commit -m "feat: add plan orchestration with fallback and certification readiness"
```

---

### Task 10: Plan diffing

**Files:**
- Modify: `planner.py`
- Create: `tests/test_planner_diff.py`

**Interfaces:**
- Consumes: `PlanDiff` (Task 2).
- Produces: `plan_diff(old_item_ids, new_item_ids) -> PlanDiff` — consumed by `app.py` (Task 13) for the "path updated" diff screen.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_planner_diff.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner_diff.py -v`
Expected: FAIL — `ImportError: cannot import name 'plan_diff' from 'planner'`

- [ ] **Step 3: Add `plan_diff` to `planner.py`**

Add this import to `planner.py`:

```python
from models import Catalog, CatalogItem, Level, PlanDiff, PlanResponse, PlanStep, Track
```

```python
def plan_diff(old_item_ids: list[str], new_item_ids: list[str]) -> PlanDiff:
    old_set = set(old_item_ids)
    new_set = set(new_item_ids)

    kept = [item_id for item_id in new_item_ids if item_id in old_set]
    added = [item_id for item_id in new_item_ids if item_id not in old_set]
    removed = [item_id for item_id in old_item_ids if item_id not in new_set]
    reordered = kept != [item_id for item_id in old_item_ids if item_id in new_set]

    return PlanDiff(kept=kept, added=added, removed=removed, reordered=reordered)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner_diff.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_diff.py
git commit -m "feat: add plan-diff computation for the path-updated screen"
```

---

### Task 11: FastAPI scaffolding and Start screen

**Files:**
- Create: `app.py`
- Create: `templates/base.html`
- Create: `templates/start.html`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `load_catalog` (Task 3), `init_db`, `create_learner`, `log_plan` (Task 4), `plan_or_replan` (Task 9).
- Produces: `app` (the FastAPI instance), `CATALOG`, `DB_PATH`, `compute_plan(learner, progress) -> tuple[PlanResponse, bool]` — `compute_plan` is the seam later tasks' tests monkeypatch to avoid touching the real Gemini client.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app.py
import pytest
from fastapi.testclient import TestClient

import app as app_module
import db
from models import PlanResponse, PlanStep


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    def fake_compute_plan(learner, progress):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
                summary="Start with RAG fundamentals.",
            ),
            False,
        )

    monkeypatch.setattr(app_module, "compute_plan", fake_compute_plan)

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_start_page_renders_goal_form(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "goal_text" in response.text
    assert "starting_level" in response.text


def test_submitting_start_form_creates_learner_and_redirects_to_path(client):
    response = client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/path/")


def test_submitting_start_form_logs_the_initial_plan(client, tmp_path):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest is not None
    assert latest["trigger"] == "initial"
    assert latest["steps"][0]["item_id"] == "rag-fundamentals"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Implement `app.py`**

```python
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai

import db
import planner
from catalog import load_catalog
from models import Level, PlanResponse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "learnpath.db")
CATALOG = load_catalog()

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db(DB_PATH)


def compute_plan(learner: dict, progress: list[dict]) -> tuple[PlanResponse, bool]:
    client = genai.Client()
    return planner.plan_or_replan(client, CATALOG, learner, progress)


@app.get("/", response_class=HTMLResponse)
def start_page(request: Request):
    return templates.TemplateResponse(
        request,
        "start.html",
        {"request": request, "levels": [level.value for level in Level]},
    )


@app.post("/start")
def start_learner(goal_text: str = Form(...), starting_level: str = Form(...)):
    learner = db.create_learner(goal_text, starting_level, DB_PATH)
    plan, _used_fallback = compute_plan(learner, [])
    db.log_plan(learner["id"], plan.model_dump(), "initial", DB_PATH)
    return RedirectResponse(url=f"/path/{learner['id']}", status_code=303)
```

- [ ] **Step 4: Create `templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}learnpath-agent{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="site-header"><a href="/">learnpath-agent</a></header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 5: Create `templates/start.html`**

```html
{% extends "base.html" %}
{% block title %}Start — learnpath-agent{% endblock %}
{% block content %}
<h1>What do you want to learn?</h1>
<form method="post" action="/start">
  <label for="goal_text">Your goal</label>
  <textarea id="goal_text" name="goal_text" rows="3" required
    placeholder="e.g. I want to understand how RAG differs from just stuffing context"></textarea>

  <label for="starting_level">Starting level</label>
  <select id="starting_level" name="starting_level">
    {% for level in levels %}
    <option value="{{ level }}">{{ level | capitalize }}</option>
    {% endfor %}
  </select>

  <button type="submit">Build my learning path</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 3 passed. (`/path/{id}` doesn't exist yet — that's fine, this task only asserts on the redirect's `location` header, not on following it.)

- [ ] **Step 7: Commit**

```bash
git add app.py templates/base.html templates/start.html tests/test_app.py
git commit -m "feat: add FastAPI app scaffolding and the start screen"
```

---

### Task 12: Current path screen

**Files:**
- Modify: `app.py`
- Create: `templates/path.html`
- Modify (append): `tests/test_app.py`

**Interfaces:**
- Consumes: `get_item` (Task 3), `get_learner`, `get_progress`, `get_latest_plan` (Task 4), `certification_ready_tracks` (Task 9).
- Produces: `GET /path/{learner_id}` route.

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_app.py
def test_current_path_screen_shows_recommended_items_and_rationale(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/path/1")

    assert response.status_code == 200
    assert "RAG Fundamentals" in response.text
    assert "Matches your goal." in response.text
    assert "Start with RAG fundamentals." in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — 404, no route for `/path/{learner_id}`.

- [ ] **Step 3: Add the `/path/{learner_id}` route to `app.py`**

```python
from catalog import get_item
```

```python
@app.get("/path/{learner_id}", response_class=HTMLResponse)
def current_path(request: Request, learner_id: int):
    learner = db.get_learner(learner_id, DB_PATH)
    progress = db.get_progress(learner_id, DB_PATH)
    latest_plan = db.get_latest_plan(learner_id, DB_PATH)

    steps = [
        {"item": get_item(CATALOG, step["item_id"]), "rationale": step["rationale"]}
        for step in latest_plan["steps"]
    ]
    ready_tracks = planner.certification_ready_tracks(CATALOG, progress)

    return templates.TemplateResponse(
        request,
        "path.html",
        {
            "request": request,
            "learner_id": learner_id,
            "learner": learner,
            "steps": steps,
            "summary": latest_plan["summary"],
            "ready_tracks": ready_tracks,
        },
    )
```

- [ ] **Step 4: Create `templates/path.html`**

```html
{% extends "base.html" %}
{% block title %}Your Path — learnpath-agent{% endblock %}
{% block content %}
<h1>Your learning path</h1>
<p class="goal"><strong>Goal:</strong> {{ learner.goal_text }}</p>

{% if ready_tracks %}
<div class="cert-banner">
  Certification-ready: {{ ready_tracks | join(", ") }}
</div>
{% endif %}

<div class="rationale-panel">
  <strong>Why this path:</strong> {{ summary }}
</div>

<ol class="step-list">
  {% for step in steps %}
  <li class="step-card">
    <a href="/item/{{ learner_id }}/{{ step.item.id }}">{{ step.item.title }}</a>
    <span class="badge">{{ step.item.track.value }}</span>
    <span class="badge">{{ step.item.level.value }}</span>
    <span class="badge">{{ step.item.duration_minutes }}m</span>
    <p class="rationale">{{ step.rationale }}</p>
  </li>
  {% endfor %}
</ol>

<p><a href="/history/{{ learner_id }}">View plan history &amp; browse catalog</a></p>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/path.html tests/test_app.py
git commit -m "feat: add current-path screen with rationale and certification banner"
```

---

### Task 13: Item view, quiz submission, and path-updated diff screen

**Files:**
- Modify: `app.py`
- Create: `templates/item.html`
- Create: `templates/path_updated.html`
- Modify (append): `tests/test_app.py`

**Interfaces:**
- Consumes: `grade_quiz` (Task 5), `record_progress` (Task 4), `plan_diff` (Task 10), `compute_plan` (Task 11).
- Produces: `GET /item/{learner_id}/{item_id}`, `POST /item/{learner_id}/{item_id}/submit` routes.

- [ ] **Step 1: Append the failing tests**

```python
# append to tests/test_app.py
def test_item_view_shows_content_and_quiz_form(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/item/1/rag-fundamentals")

    assert response.status_code == 200
    assert "Retrieval-Augmented Generation" in response.text
    assert 'action="/item/1/rag-fundamentals/submit"' in response.text


def test_submitting_quiz_grades_it_and_shows_diff(client, monkeypatch):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    def fake_compute_plan_after_quiz(learner, progress):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-chunking-strategies", rationale="Next in RAG track.")],
                summary="Move on to chunking strategies.",
            ),
            False,
        )

    monkeypatch.setattr(app_module, "compute_plan", fake_compute_plan_after_quiz)

    response = client.post(
        "/item/1/rag-fundamentals/submit",
        data={"answer_0": "0", "answer_1": "1", "answer_2": "1"},
    )

    assert response.status_code == 200
    assert "Move on to chunking strategies." in response.text
    assert "Added" in response.text or "added" in response.text

    progress = db.get_progress(1, app_module.DB_PATH)
    assert progress[0]["item_id"] == "rag-fundamentals"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — 404, no routes for `/item/{learner_id}/{item_id}` or its `/submit` path.

- [ ] **Step 3: Add both routes to `app.py`**

```python
import quiz as quiz_module
```

```python
@app.get("/item/{learner_id}/{item_id}", response_class=HTMLResponse)
def item_view(request: Request, learner_id: int, item_id: str):
    item = get_item(CATALOG, item_id)
    return templates.TemplateResponse(
        request,
        "item.html",
        {"request": request, "learner_id": learner_id, "item": item},
    )


@app.post("/item/{learner_id}/{item_id}/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request, learner_id: int, item_id: str):
    form = await request.form()
    item = get_item(CATALOG, item_id)
    answers = [int(form.get(f"answer_{i}", -1)) for i in range(len(item.quiz))]
    score = quiz_module.grade_quiz(item.quiz, answers)

    learner = db.get_learner(learner_id, DB_PATH)
    db.record_progress(learner_id, item_id, score, DB_PATH)

    previous_plan = db.get_latest_plan(learner_id, DB_PATH)
    progress = db.get_progress(learner_id, DB_PATH)
    new_plan, _used_fallback = compute_plan(learner, progress)
    db.log_plan(learner_id, new_plan.model_dump(), "quiz_result", DB_PATH)

    old_item_ids = [step["item_id"] for step in previous_plan["steps"]] if previous_plan else []
    diff = planner.plan_diff(old_item_ids, [step.item_id for step in new_plan.steps])

    return templates.TemplateResponse(
        request,
        "path_updated.html",
        {
            "request": request,
            "learner_id": learner_id,
            "score": score,
            "diff": diff,
            "summary": new_plan.summary,
        },
    )
```

- [ ] **Step 4: Create `templates/item.html`**

Jinja2's `loop` variable always refers to the nearest enclosing `{% for %}`, so the question index has to be captured in a named variable (`question_index`) before entering the nested options loop — otherwise every radio button's `name` would incorrectly use the option's loop index instead of the question's.

```html
{% extends "base.html" %}
{% block title %}{{ item.title }} — learnpath-agent{% endblock %}
{% block content %}
<h1>{{ item.title }}</h1>
<p class="content">{{ item.content }}</p>

{% if item.quiz %}
<form method="post" action="/item/{{ learner_id }}/{{ item.id }}/submit">
  {% for question in item.quiz %}
  {% set question_index = loop.index0 %}
  <fieldset>
    <legend>{{ question.question }}</legend>
    {% for option in question.options %}
    <label>
      <input type="radio" name="answer_{{ question_index }}" value="{{ loop.index0 }}" required>
      {{ option }}
    </label>
    {% endfor %}
  </fieldset>
  {% endfor %}
  <button type="submit">Submit quiz</button>
</form>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Create `templates/path_updated.html`**

```html
{% extends "base.html" %}
{% block title %}Path Updated — learnpath-agent{% endblock %}
{% block content %}
<h1>Path updated</h1>
<p>You scored <strong>{{ score }}%</strong> on that quiz.</p>

<div class="rationale-panel">{{ summary }}</div>

<div class="diff">
  {% if diff.added %}<p class="diff-added"><strong>Added:</strong> {{ diff.added | join(", ") }}</p>{% endif %}
  {% if diff.removed %}<p class="diff-removed"><strong>Removed:</strong> {{ diff.removed | join(", ") }}</p>{% endif %}
  {% if diff.kept %}<p class="diff-kept"><strong>Kept:</strong> {{ diff.kept | join(", ") }}</p>{% endif %}
  {% if diff.reordered %}<p class="diff-reordered">The remaining items were also reordered.</p>{% endif %}
</div>

<p><a href="/path/{{ learner_id }}">Back to your path</a></p>
{% endblock %}
```

- [ ] **Step 6: Append diff styling to `static/style.css`**

```css
.cert-banner {
  background: #e6f4ea;
  border: 1px solid #34a853;
  padding: 0.75rem;
  border-radius: 4px;
  margin-bottom: 1rem;
}

.rationale-panel {
  background: #f4f4f4;
  border-left: 4px solid #2c5aa0;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.step-card {
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
}

.badge {
  display: inline-block;
  font-size: 0.8rem;
  background: #eee;
  border-radius: 3px;
  padding: 0.1rem 0.5rem;
  margin-right: 0.3rem;
}

.diff-added { color: #1a7f37; }
.diff-removed { color: #b91c1c; }
.diff-kept { color: var(--muted); }
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 6 passed.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/item.html templates/path_updated.html static/style.css tests/test_app.py
git commit -m "feat: add item view, quiz submission, and path-updated diff screen"
```

---

### Task 14: Plan history and catalog browse screen

**Files:**
- Modify: `app.py`
- Create: `templates/history.html`
- Modify (append): `tests/test_app.py`

**Interfaces:**
- Consumes: `get_plan_log` (Task 4), `CATALOG` (Task 11).
- Produces: `GET /history/{learner_id}` route.

- [ ] **Step 1: Append the failing test**

```python
# append to tests/test_app.py
def test_history_screen_shows_plan_log_and_catalog_table(client):
    client.post(
        "/start",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/history/1")

    assert response.status_code == 200
    assert "Start with RAG fundamentals." in response.text  # from plan_log
    assert "RAG Fundamentals" in response.text  # from the catalog table
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py -v`
Expected: FAIL — 404, no route for `/history/{learner_id}`.

- [ ] **Step 3: Add the route to `app.py`**

```python
@app.get("/history/{learner_id}", response_class=HTMLResponse)
def history_page(request: Request, learner_id: int):
    plan_log = db.get_plan_log(learner_id, DB_PATH)
    return templates.TemplateResponse(
        request,
        "history.html",
        {"request": request, "learner_id": learner_id, "plan_log": plan_log, "catalog": CATALOG.items},
    )
```

- [ ] **Step 4: Create `templates/history.html`**

```html
{% extends "base.html" %}
{% block title %}History — learnpath-agent{% endblock %}
{% block content %}
<h1>Plan history</h1>
<ol>
  {% for entry in plan_log %}
  <li>
    <strong>{{ entry.trigger }}</strong> at {{ entry.created_at }} — {{ entry.summary }}
  </li>
  {% endfor %}
</ol>

<h2>Full catalog</h2>
<table>
  <thead>
    <tr><th>Title</th><th>Type</th><th>Track</th><th>Level</th><th>Duration</th></tr>
  </thead>
  <tbody>
    {% for item in catalog %}
    <tr>
      <td>{{ item.title }}</td>
      <td>{{ item.type.value }}</td>
      <td>{{ item.track.value }}</td>
      <td>{{ item.level.value }}</td>
      <td>{{ item.duration_minutes }}m</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<p><a href="/path/{{ learner_id }}">Back to your path</a></p>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: 7 passed.

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every module pass (Tasks 1-14 combined).

- [ ] **Step 7: Commit**

```bash
git add app.py templates/history.html tests/test_app.py
git commit -m "feat: add plan history and catalog browse screen"
```

---

### Task 15: README and manual smoke test

**Files:**
- Create: `README.md`

**Interfaces:**
- None — this task documents and manually verifies the finished app; it doesn't add new importable code.

- [ ] **Step 1: Write `README.md`**

```markdown
# learnpath-agent

A small FastAPI app that simulates an Amazon-Ads-Academy-shaped course catalog — course/learning-path/video content types, three levels, tagged tracks, a dual certification model — except the content teaches modern AI/agentic concepts (RAG, multi-agent systems, LLM evaluation, agent tooling, context engineering, LLM billing). The centerpiece is an **adaptive learning-path agent**: instead of routing a learner through one of the catalog's fixed "Learning Path" bundles, an LLM plans a personalized sequence from a learner's stated goal and level, and re-plans it after every quiz result.

## Why this exists

Static "personalized learning paths" in most real LMS products are personalized once, at signup, and then static. This project builds the more interesting version: a planner that re-plans after every quiz result — inserting a remedial item on a weak score, skipping ahead on a strong one, and always showing its work (candidates it could have picked, and why it picked what it did).

## How it works

- `catalog.py` / `data/catalog.json` — ~54 seed items across 7 AI-concept tracks and 3 levels.
- `planner.py` — filters the catalog down to a relevant candidate set, then either asks Gemini (structured JSON output validated against a Pydantic schema) to rank/sequence them with rationale, or falls back to a deterministic rule-based planner if the API call fails or rate-limits.
- `db.py` — SQLite-backed learner state: goal, progress, and every past plan with its rationale.
- `app.py` — five FastAPI screens: start → current path → item + quiz → path-updated diff → plan history / catalog browse.

Every function that calls the Gemini API takes the client as an explicit parameter, and `genai.Client()` is constructed in exactly one place (`app.compute_plan`). That's what makes the entire automated test suite run offline, with a mocked client and no API key required.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the test suite (no API key needed — everything's mocked)
pytest -v

# Run the real app (requires a real Gemini key for the planner to actually call the LLM;
# falls back to the rule-based planner automatically if GEMINI_API_KEY is unset or the call fails)
export GEMINI_API_KEY="AIza..."
uvicorn app:app --reload
```

Then open http://127.0.0.1:8000/, describe a learning goal (e.g. "I want to understand how RAG differs from just stuffing context into a prompt"), and follow the generated path — completing items and taking their quizzes to watch the plan adapt.

## Tech stack

Python, FastAPI, Jinja2, Pydantic v2, `google-genai` (Gemini free tier, `gemini-2.5-flash`), SQLite, pytest.
```

- [ ] **Step 2: Manually smoke-test the real app** (not part of `pytest` — this is the one place that touches the real API, same tradeoff `JudgeDred` makes)

```bash
export GEMINI_API_KEY="AIza..."
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/, submit a goal, click through to an item, submit its quiz with a mix of right/wrong answers, and confirm:
1. The start page redirects to `/path/{id}` showing catalog items with rationale.
2. `/item/{id}/{item_id}` shows real lesson content and a quiz form.
3. Submitting the quiz shows the path-updated screen with a non-empty diff.
4. `/history/{id}` shows at least two plan-log entries (`initial` and `quiz_result`) and the full catalog table.

If `GEMINI_API_KEY` is unset, confirm the same flow still works end-to-end via the rule-based fallback (the rationale text on `/path/{id}` will read "Fallback rule-based plan...").

- [ ] **Step 3: Run the full test suite one last time**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with elevator pitch and quick start"
```

---

## Self-Review Notes

- **Spec coverage:** Catalog & data model → Tasks 2-3. Planning agent (candidate filtering, structured output, thresholds, fallback, certification readiness) → Tasks 6-9. Plan diffing → Task 10. Web UI's five screens → Tasks 11-14. Testing (offline, mocked client) → every task's tests plus the dependency-injection constraint stated up front. Repo & tech stack (FastAPI not Flask, own repo, README) → Tasks 1, 11, 15. Portfolio-site integration is explicitly out of scope for this plan per the spec ("a follow-up, later step") — not included as a task here.
- **Placeholder scan:** every step has real, complete code; the one caveat is the Jinja2 nested-loop fix in Task 13, which is spelled out with a corrected final template rather than left ambiguous.
- **Type consistency:** `filter_candidates`, `current_level`, `rule_based_plan`, `gemini_plan`, `plan_or_replan`, `certification_ready_tracks`, and `plan_diff` are defined once (Tasks 6-10) and consumed with matching signatures in `app.py` (Tasks 11-14). `db.py`'s `log_plan`/`get_latest_plan`/`get_plan_log` all agree on the flattened `{"steps": ..., "summary": ..., "trigger": ..., "created_at": ...}` shape used throughout.
