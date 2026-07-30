# Explainable Diff & Add-Back Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (direct, same-session execution — no subagent dispatch). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the raw-item-id display bug on the path-updated (diff) screen, add a genuine per-item rationale for why each item was added/removed/kept (including a real, LLM-produced "why removed" reason — a new planner capability), and let a learner immediately reinsert a removed item into their current path with one click.

**Architecture:** `models.py` gains a `DroppedItem` model and `PlanResponse.dropped`. `planner.py`'s `build_prompt`/`gemini_plan`/`rule_based_plan`/`plan_or_replan` all gain a `previous_item_ids` parameter so the planner can be asked (or, for the fallback, mechanically compute) why previously-planned items are no longer in the new plan. `app.py` threads `previous_item_ids` through `compute_plan`/`submit_quiz`, and gains one new route for the add-back action. `path_updated.html` becomes one expandable `<details>` tile per item instead of three comma-joined lines.

**Tech Stack:** No new dependencies — same FastAPI/Jinja2/Pydantic/SQLite/pytest stack.

## Global Constraints

- `dropped` is a new field on `PlanResponse`, defaulting to `[]` — existing stored `plan_log` rows without this field must still deserialize correctly (they already tolerate missing `candidate_ids` the same way, via `.get(..., [])`).
- The hallucination guard already applied to `steps` (filter to real candidate ids) gets a matching guard on `dropped` (filter to ids that were actually in `previous_item_ids`) — never trust the LLM's `dropped` list unfiltered.
- The rule-based fallback must produce equally real (if mechanical) `dropped` data — the feature must work identically regardless of which planner mode is active.
- The add-back route makes no LLM call and does no candidate-set validation — it is a direct, explicit user override, not a planning decision.
- No protection against a future replan dropping a manually-added-back item again (explicit non-goal, already decided).
- `plan_or_replan`'s return type stays `tuple[PlanResponse, bool, list[str]]` — `dropped` rides inside `PlanResponse`, no new tuple element.

---

## File Structure

```
learnpath-agent/
  models.py       # MODIFIED: + DroppedItem, PlanResponse.dropped
  planner.py       # MODIFIED: build_prompt, gemini_plan, rule_based_plan, plan_or_replan all gain previous_item_ids
  app.py           # MODIFIED: compute_plan gains previous_item_ids param; submit_quiz reorders to compute old_item_ids
                    #           first and pass them in; new POST /path/{track_id}/add/{item_id} route
  templates/
    path_updated.html  # MODIFIED: one <details> tile per item instead of three comma-joined lines
  static/style.css # MODIFIED: tile/add-back-button styling
  tests/
    test_models.py            # MODIFIED: DroppedItem, PlanResponse.dropped tests
    test_planner_plans.py      # MODIFIED: previous_item_ids threading, dropped generation, hallucination guard
    test_app.py                 # MODIFIED: add-back route tests, updated path_updated assertions
```

---

### Task 1: `models.py` — `DroppedItem` and `PlanResponse.dropped`

**Files:**
- Modify: `models.py`
- Modify: `tests/test_models.py`

**Interfaces:**
- Produces: `DroppedItem{item_id: str, rationale: str}`, `PlanResponse.dropped: list[DroppedItem] = []` — consumed by `planner.py` (Task 2-3) and `app.py`/`path_updated.html` (Task 4-5).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
from models import DroppedItem


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'DroppedItem' from 'models'`

- [ ] **Step 3: Add `DroppedItem` and `PlanResponse.dropped` to `models.py`**

Add this class near `PlanStep`:

```python
class DroppedItem(BaseModel):
    item_id: str
    rationale: str
```

Modify the existing `PlanResponse` class:

```python
class PlanResponse(BaseModel):
    steps: list[PlanStep]
    summary: str
    dropped: list[DroppedItem] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: all passing (existing tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add DroppedItem model and PlanResponse.dropped field"
```

---

### Task 2: `planner.py` — thread `previous_item_ids` through the Gemini path

**Files:**
- Modify: `planner.py`
- Modify: `tests/test_planner_plans.py`

**Interfaces:**
- Consumes: `DroppedItem` (Task 1).
- Produces: `build_prompt(goal_text, level, progress, candidates, previous_item_ids=None)`, `gemini_plan(client, goal_text, level, progress, candidates, previous_item_ids=None, model=PLANNER_MODEL)` — both now accept and use the new parameter; consumed by `plan_or_replan` (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planner_plans.py`:

```python
from models import DroppedItem


def test_build_prompt_mentions_previously_planned_items_when_given():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())[:2]

    prompt = build_prompt(
        "Learn RAG", Level.BEGINNER, [], candidates, previous_item_ids=["rag-fundamentals"]
    )

    assert "rag-fundamentals" in prompt
    assert "dropped" in prompt.lower() or "no longer" in prompt.lower() or "explain" in prompt.lower()


def test_build_prompt_omits_previous_items_section_when_none_given():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())[:2]

    prompt_without = build_prompt("Learn RAG", Level.BEGINNER, [], candidates)
    prompt_with_empty = build_prompt(
        "Learn RAG", Level.BEGINNER, [], candidates, previous_item_ids=[]
    )

    # Both forms of "nothing previously planned" should produce the same prompt shape
    assert prompt_without == prompt_with_empty


def test_gemini_plan_passes_through_real_dropped_entries():
    client = Mock()
    expected_plan = PlanResponse(
        steps=[PlanStep(item_id="rag-chunking-strategies", rationale="Next step.")],
        summary="Moving on.",
        dropped=[DroppedItem(item_id="rag-fundamentals", rationale="Already mastered.")],
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=expected_plan)

    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    result = gemini_plan(
        client, "Learn RAG", Level.BEGINNER, [], candidates, previous_item_ids=["rag-fundamentals"]
    )

    assert result.dropped[0].item_id == "rag-fundamentals"
    assert result.dropped[0].rationale == "Already mastered."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner_plans.py -v -k "previous_item or dropped"`
Expected: FAIL — `TypeError: build_prompt() got an unexpected keyword argument 'previous_item_ids'`

- [ ] **Step 3: Update `build_prompt` and `gemini_plan` in `planner.py`**

Replace the existing `build_prompt` function:

```python
def build_prompt(
    goal_text: str,
    level: Level,
    progress: list[dict],
    candidates: list[CatalogItem],
    previous_item_ids: list[str] | None = None,
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

    previous_section = ""
    if previous_item_ids:
        previous_lines = "\n".join(f"- {item_id}" for item_id in previous_item_ids)
        previous_section = (
            "\n\nPreviously planned items (from before this replan):\n"
            f"{previous_lines}\n\n"
            "For any of these you are NOT including in your new plan, add an entry to the "
            "`dropped` list explaining in one line why you dropped it. Only include ids from "
            "this previously-planned list in `dropped` — never invent a dropped id."
        )

    return (
        "You are an adaptive learning-path planner for an AI-concepts course catalog.\n\n"
        f"Learner goal: {goal_text}\n"
        f"Learner level: {level.value}\n\n"
        f"Completed items and quiz scores so far:\n{progress_lines}\n\n"
        "Candidate items available to recommend next (choose and order a subset of these; "
        "never invent an id that isn't listed):\n"
        f"{candidate_lines}"
        f"{previous_section}\n\n"
        "Return an ordered list of item ids to study next, a one-line rationale for each, "
        "and a one-to-two-sentence overall summary of the plan."
    )
```

Replace the existing `gemini_plan` function:

```python
def gemini_plan(
    client,
    goal_text: str,
    level: Level,
    progress: list[dict],
    candidates: list[CatalogItem],
    previous_item_ids: list[str] | None = None,
    model: str = PLANNER_MODEL,
) -> PlanResponse:
    prompt = build_prompt(goal_text, level, progress, candidates, previous_item_ids)
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
Expected: all passing, including the 3 new tests plus every pre-existing test in this file (verify none broke — `build_prompt`/`gemini_plan`'s new parameter is optional with a default, so all existing call sites without it still work unchanged).

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_plans.py
git commit -m "feat: ask the planner to explain dropped items via previous_item_ids"
```

---

### Task 3: `planner.py` — `rule_based_plan`'s mechanical dropped computation, `plan_or_replan`'s hallucination guard and threading

**Files:**
- Modify: `planner.py`
- Modify: `tests/test_planner_plans.py`

**Interfaces:**
- Produces: `rule_based_plan(candidates, previous_item_ids=None, limit=5)`, `plan_or_replan(client, catalog, learner, progress, previous_item_ids=None)` — both now accept and correctly handle the new parameter.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planner_plans.py`:

```python
def test_rule_based_plan_computes_dropped_items_mechanically():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    plan = rule_based_plan(candidates, previous_item_ids=["rag-fundamentals", "does-not-exist-anymore"])

    new_step_ids = {step.item_id for step in plan.steps}
    dropped_ids = {d.item_id for d in plan.dropped}

    for prev_id in ["rag-fundamentals", "does-not-exist-anymore"]:
        if prev_id not in new_step_ids:
            assert prev_id in dropped_ids
    for dropped in plan.dropped:
        assert "Fallback rule-based plan" in dropped.rationale


def test_rule_based_plan_with_no_previous_items_drops_nothing():
    catalog = load_catalog()
    candidates = filter_candidates(catalog, "Learn RAG", Level.BEGINNER, set())

    plan = rule_based_plan(candidates)

    assert plan.dropped == []


def test_gemini_plan_filters_hallucinated_dropped_ids():
    client = Mock()
    hallucinated_plan = PlanResponse(
        steps=[PlanStep(item_id="rag-chunking-strategies", rationale="Next step.")],
        summary="Moving on.",
        dropped=[
            DroppedItem(item_id="rag-fundamentals", rationale="Real, was previously planned."),
            DroppedItem(item_id="totally-invented-id", rationale="Hallucinated, never planned."),
        ],
    )
    client.models.generate_content.return_value = SimpleNamespace(parsed=hallucinated_plan)

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback = plan_or_replan(
        client, catalog, learner, [], previous_item_ids=["rag-fundamentals"]
    )

    assert used_fallback is False
    dropped_ids = {d.item_id for d in plan.dropped}
    assert "rag-fundamentals" in dropped_ids
    assert "totally-invented-id" not in dropped_ids


def test_plan_or_replan_passes_previous_item_ids_to_fallback_on_failure():
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("rate limited")

    catalog = load_catalog()
    learner = {"goal_text": "Learn RAG", "starting_level": "beginner"}

    plan, used_fallback = plan_or_replan(
        client, catalog, learner, [], previous_item_ids=["rag-fundamentals"]
    )

    assert used_fallback is True
    # The fallback must have had the chance to compute dropped items too
    assert isinstance(plan.dropped, list)
```

Note: `plan_or_replan` currently returns a 2-tuple `(plan, used_fallback)` per its existing signature in this file — check the actual current return arity in `planner.py` before writing these assertions (an earlier feature added a third `candidate_ids` return value; if that's present, unpack 3 values here, e.g. `plan, used_fallback, _candidate_ids = plan_or_replan(...)`, matching whatever `plan_or_replan`'s current real signature is in this codebase).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner_plans.py -v -k "rule_based_plan_computes or rule_based_plan_with_no or hallucinated_dropped or passes_previous_item_ids"`
Expected: FAIL — `TypeError: rule_based_plan() got an unexpected keyword argument 'previous_item_ids'`

- [ ] **Step 3: Update `rule_based_plan` and `plan_or_replan` in `planner.py`**

Replace the existing `rule_based_plan` function:

```python
def rule_based_plan(
    candidates: list[CatalogItem], previous_item_ids: list[str] | None = None, limit: int = 5
) -> PlanResponse:
    ordered = sorted(candidates, key=lambda item: (LEVEL_ORDER.index(item.level), item.duration_minutes))[:limit]
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

    new_step_ids = {step.item_id for step in steps}
    dropped = [
        DroppedItem(
            item_id=prev_id,
            rationale="Fallback rule-based plan: no longer prioritized under simple level/duration ordering.",
        )
        for prev_id in (previous_item_ids or [])
        if prev_id not in new_step_ids
    ]

    return PlanResponse(
        steps=steps,
        summary="Fallback rule-based plan (LLM unavailable): candidates ordered by level then duration.",
        dropped=dropped,
    )
```

Update `plan_or_replan` — find its current implementation in `planner.py` (it currently calls `gemini_plan(...)` inside a `try`, falls back to `rule_based_plan(candidates)` in the `except`, and validates/filters `plan.steps` against the candidate id set before returning). Modify it to:

```python
def plan_or_replan(
    client,
    catalog: Catalog,
    learner: dict,
    progress: list[dict],
    previous_item_ids: list[str] | None = None,
) -> tuple[PlanResponse, bool]:
    completed_ids = {entry["item_id"] for entry in progress}
    level = current_level(Level(learner["starting_level"]), progress, catalog)
    candidates = filter_candidates(catalog, learner["goal_text"], level, completed_ids)
    candidate_ids = {item.id for item in candidates}

    if client is None:
        return rule_based_plan(candidates, previous_item_ids), True

    try:
        plan = gemini_plan(
            client, learner["goal_text"], level, progress, candidates, previous_item_ids
        )
        plan.steps = [step for step in plan.steps if step.item_id in candidate_ids]
        if not plan.steps:
            raise ValueError("LLM returned no usable candidate ids")
        plan.dropped = [
            dropped for dropped in plan.dropped if dropped.item_id in (previous_item_ids or [])
        ]
        return plan, False
    except Exception:
        return rule_based_plan(candidates, previous_item_ids), True
```

**Important:** read the actual current `plan_or_replan` implementation in `planner.py` before replacing it — the exact existing structure (variable names, whether it currently returns 2 or 3 values, whether `client is None` is already handled as an explicit early branch or falls through the `try`) may differ slightly from this sketch, since it's been modified by prior features. Preserve every existing behavior (explicit `client is None` fast path, candidate-id validation on `steps`, the broad `except Exception` fallback) exactly as it currently works, only *adding* the `previous_item_ids` parameter and the `dropped` filtering — do not remove or alter any existing validated behavior while making this change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner_plans.py -v`
Expected: all tests in this file passing — every test added across Tasks 2-3, plus every pre-existing test (confirming the optional-parameter, backward-compatible nature of this change).

- [ ] **Step 5: Commit**

```bash
git add planner.py tests/test_planner_plans.py
git commit -m "feat: compute mechanical dropped-item rationale in the rule-based fallback"
```

---

### Task 4: `app.py` — thread `previous_item_ids` through, add the add-back route

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `planner.plan_or_replan`'s new `previous_item_ids` parameter (Task 3).
- Produces: `compute_plan(learner, progress, previous_item_ids=None)`, `POST /path/{track_id}/add/{item_id}` — the route consumed only by users clicking the button (Task 5's template).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_add_back_route_reinserts_a_dropped_item_and_redirects(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post(
        "/path/1/add/rag-chunking-strategies", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/path/1"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert any(step["item_id"] == "rag-chunking-strategies" for step in latest["steps"])
    assert latest["trigger"] == "manual_add"


def test_add_back_route_does_not_duplicate_an_already_present_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    # rag-fundamentals is already in the fixture's fake initial plan
    client.post("/path/1/add/rag-fundamentals")

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    matching = [step for step in latest["steps"] if step["item_id"] == "rag-fundamentals"]
    assert len(matching) == 1


def test_add_back_route_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post("/path/1/add/does-not-exist")
    assert response.status_code == 404


def test_add_back_route_returns_404_for_another_users_track(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    with TestClient(app_module.app) as other_client:
        other_client.post(
            "/register",
            data={
                "email": "someone-else@example.com",
                "password": "hunter22",
                "confirm_password": "hunter22",
            },
        )
        response = other_client.post("/path/1/add/rag-fundamentals")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v -k "add_back"`
Expected: FAIL — 404s, since `/path/{track_id}/add/{item_id}` doesn't exist yet.

- [ ] **Step 3: Update `compute_plan` and `submit_quiz`, add the new route in `app.py`**

Update the existing `compute_plan` function:

```python
def compute_plan(
    learner: dict, progress: list[dict], previous_item_ids: list[str] | None = None
) -> tuple[PlanResponse, bool]:
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    except Exception:
        client = None
    return planner.plan_or_replan(client, CATALOG, learner, progress, previous_item_ids)
```

(Check the actual current return type of `compute_plan`/`plan_or_replan` in this codebase before editing — a prior feature may have added a third `candidate_ids` tuple element; preserve whatever the current real arity is, only adding the `previous_item_ids` parameter to the signature and passing it through to `planner.plan_or_replan` unchanged.)

In `submit_quiz`, reorder so `old_item_ids` is computed BEFORE calling `compute_plan`, then pass it in:

```python
@app.post("/item/{track_id}/{item_id}/submit", response_class=HTMLResponse)
async def submit_quiz(
    request: Request,
    track_id: int,
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    track = get_owned_track(track_id, current_user, DB_PATH)
    form = await request.form()
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    answers = [int(form.get(f"answer_{i}", -1)) for i in range(len(item.quiz))]
    score = quiz_module.grade_quiz(item.quiz, answers)

    db.record_progress(track_id, item_id, score, DB_PATH)

    previous_plan = db.get_latest_plan(track_id, DB_PATH)
    old_item_ids = [step["item_id"] for step in previous_plan["steps"]] if previous_plan else []

    progress = db.get_progress(track_id, DB_PATH)
    new_plan, _used_fallback = compute_plan(track, progress, previous_item_ids=old_item_ids)
    new_plan_dict = new_plan.model_dump()
    db.log_plan(track_id, new_plan_dict, "quiz_result", DB_PATH)

    diff = planner.plan_diff(old_item_ids, [step.item_id for step in new_plan.steps])

    return templates.TemplateResponse(
        request,
        "path_updated.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "score": score,
            "diff": diff,
            "summary": new_plan.summary,
            "new_plan": new_plan,
        },
    )
```

**Important:** check the current real body of `submit_quiz` in `app.py` before replacing it — it may already carry a `candidate_ids` variable (from a prior feature) that gets merged into `new_plan_dict["candidate_ids"] = candidate_ids`. If so, preserve that line exactly as it currently exists, in addition to the changes above (don't drop existing `candidate_ids` handling — only add the `old_item_ids`-before-`compute_plan` reordering, the `previous_item_ids=old_item_ids` argument, and passing `new_plan` itself into the template context, which Task 5's template needs to look up per-item rationale).

Add the new route (place it near the other `/path/{track_id}` routes):

```python
@app.post("/path/{track_id}/add/{item_id}")
def add_back_item(track_id: int, item_id: str, current_user: dict = Depends(get_current_user)):
    get_owned_track(track_id, current_user, DB_PATH)
    try:
        get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")

    latest_plan = db.get_latest_plan(track_id, DB_PATH)
    existing_ids = {step["item_id"] for step in latest_plan["steps"]} if latest_plan else set()

    if item_id not in existing_ids:
        steps = list(latest_plan["steps"]) if latest_plan else []
        steps.append({"item_id": item_id, "rationale": "Added back by you."})
        plan_dict = {
            "steps": steps,
            "summary": latest_plan["summary"] if latest_plan else "",
            "dropped": [],
        }
        if latest_plan and "candidate_ids" in latest_plan:
            plan_dict["candidate_ids"] = latest_plan["candidate_ids"]
        db.log_plan(track_id, plan_dict, "manual_add", DB_PATH)

    return RedirectResponse(url=f"/path/{track_id}", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: all tests passing, including the 4 new add-back tests and every pre-existing test in this file.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add manual add-back route, thread previous_item_ids through submit_quiz"
```

---

### Task 5: `path_updated.html` — expandable per-item tiles with rationale and add-back

**Files:**
- Modify: `templates/path_updated.html`
- Modify: `static/style.css`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `new_plan` (the full `PlanResponse`, now in the template context per Task 4), `diff` (unchanged `PlanDiff`), `catalog.get_item`.

- [ ] **Step 1: Write the failing test**

Update the existing `test_submitting_quiz_grades_it_and_shows_diff` test in `tests/test_app.py` (find it and replace its body) to assert on resolved titles and expandable rationale rather than raw ids:

```python
def test_submitting_quiz_grades_it_and_shows_diff(client, monkeypatch):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    def fake_compute_plan_after_quiz(track, progress, previous_item_ids=None):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-chunking-strategies", rationale="Next in RAG track.")],
                summary="Move on to chunking strategies.",
                dropped=[
                    DroppedItem(item_id="rag-fundamentals", rationale="You've already mastered this.")
                ],
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
    # resolved titles, not raw ids
    assert "Chunking Strategies: Splitting Documents Without Losing Meaning" in response.text
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    # real rationale for both an added and a removed item
    assert "Next in RAG track." in response.text
    assert "You&#39;ve already mastered this." in response.text or "You've already mastered this." in response.text
    # add-back action present for the removed item
    assert 'action="/path/1/add/rag-fundamentals"' in response.text

    progress = db.get_progress(1, app_module.DB_PATH)
    assert progress[0]["item_id"] == "rag-fundamentals"
```

Note: this replaces the compute_plan monkeypatch's signature to accept the new `previous_item_ids` keyword — check the fixture's own `fake_compute_plan` (used by other tests in this file) and update its signature the same way (`def fake_compute_plan(track, progress, previous_item_ids=None):`) so every test using that fixture still works with the new `compute_plan` call signature from Task 4.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py -v -k "shows_diff"`
Expected: FAIL — old raw-id-based assertions no longer match, or a `TypeError` if the fixture's `fake_compute_plan` signature wasn't updated to accept `previous_item_ids`.

- [ ] **Step 3: Update the `client` fixture's `fake_compute_plan` signature in `tests/test_app.py`**

Find the fixture (near the top of the file) and update its inner function:

```python
def fake_compute_plan(track, progress, previous_item_ids=None):
    return (
        PlanResponse(
            steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
            summary="Start with RAG fundamentals.",
        ),
        False,
    )
```

(Keep whatever the fixture's actual current return arity is — if it currently returns a 3-tuple including `candidate_ids`, keep that third element; only add the `previous_item_ids=None` parameter to the function signature itself.)

- [ ] **Step 4: Rewrite `templates/path_updated.html`**

```html
{% extends "base.html" %}
{% block title %}Path Updated — learnpath-agent{% endblock %}
{% block content %}
<p class="eyebrow">Replanned</p>
<h1>Path updated</h1>
<p class="score-line">You scored <strong class="score">{{ score }}%</strong> on that quiz.</p>

<div class="rationale-panel">
  <span class="rationale-label">What changed</span>
  <p>{{ summary }}</p>
</div>

<div class="diff-rail">
  {% for item_id in diff.added %}
  {% set item = get_item(item_id) %}
  {% set rationale = added_rationale.get(item_id) %}
  <details class="diff-tile diff-tile-added">
    <summary><span class="diff-tag">Added</span> {{ item.title }}</summary>
    <p class="diff-rationale">{{ rationale or "No rationale available." }}</p>
  </details>
  {% endfor %}

  {% for item_id in diff.removed %}
  {% set item = get_item(item_id) %}
  {% set rationale = removed_rationale.get(item_id) %}
  <details class="diff-tile diff-tile-removed">
    <summary><span class="diff-tag">Removed</span> {{ item.title }}</summary>
    <p class="diff-rationale">{{ rationale or "No rationale available." }}</p>
    <form method="post" action="/path/{{ track_id }}/add/{{ item_id }}">
      <button type="submit" class="add-back-button">Add it back</button>
    </form>
  </details>
  {% endfor %}

  {% for item_id in diff.kept %}
  {% set item = get_item(item_id) %}
  {% set rationale = added_rationale.get(item_id) %}
  <details class="diff-tile diff-tile-kept">
    <summary><span class="diff-tag">Kept</span> {{ item.title }}</summary>
    <p class="diff-rationale">{{ rationale or "No rationale available." }}</p>
  </details>
  {% endfor %}

  {% if diff.reordered %}
  <div class="diff-row diff-row-reordered">
    <span class="diff-tag">Reordered</span>
    <span>The remaining items were also resequenced.</span>
  </div>
  {% endif %}
</div>

<p class="path-footer"><a href="/path/{{ track_id }}">Back to your path</a></p>
{% endblock %}
```

This template calls a `get_item` function and reads `added_rationale`/`removed_rationale` dicts directly in Jinja — Jinja2 can call a plain Python callable passed into the context and call `.get()` on a plain dict, so pass these into the template context from `app.py` (next step) rather than trying to add a custom Jinja filter.

- [ ] **Step 5: Update `submit_quiz` in `app.py` to pass `get_item`, `added_rationale`, and `removed_rationale` into the template context**

Modify the `templates.TemplateResponse(...)` call at the end of `submit_quiz` (from Task 4) to:

```python
    added_rationale = {step.item_id: step.rationale for step in new_plan.steps}
    removed_rationale = {dropped.item_id: dropped.rationale for dropped in new_plan.dropped}

    return templates.TemplateResponse(
        request,
        "path_updated.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "score": score,
            "diff": diff,
            "summary": new_plan.summary,
            "get_item": lambda item_id: get_item(CATALOG, item_id),
            "added_rationale": added_rationale,
            "removed_rationale": removed_rationale,
        },
    )
```

Remove the `"new_plan": new_plan` context key from Task 4's version if present (it's no longer needed now that `added_rationale`/`removed_rationale` are precomputed) — keep everything else in that dict.

- [ ] **Step 6: Append tile/add-back-button styling to `static/style.css`**

```css
.diff-tile {
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  padding: 0.6rem 0.9rem;
  margin-bottom: 0.5rem;
}

.diff-tile summary {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.diff-tile[open] summary { margin-bottom: 0.6rem; }

.diff-tile-added { border-left: 3px solid var(--taken); }
.diff-tile-removed { border-left: 3px solid var(--considered); opacity: 0.9; }
.diff-tile-kept { border-left: 3px solid var(--border); }

.diff-rationale { color: var(--ink-muted); margin: 0 0 0.6rem; font-size: 0.92rem; }

.add-back-button {
  font-size: 0.85rem;
  padding: 0.4rem 0.9rem;
  background: var(--considered);
}

.add-back-button:hover { background: var(--taken); }
```

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: every test in the suite passes — this is the final task, so nothing should be left broken or "expected to fail."

- [ ] **Step 8: Manual smoke test**

Start the app (`uvicorn app:app --host 127.0.0.1 --port 8010`, or any free port), log in, complete a quiz that produces both an addition and a removal, and confirm: the path-updated screen shows real course titles (not raw ids) in each tile's summary line, expanding a tile shows real rationale text, and clicking "Add it back" on a removed tile redirects to `/path/{id}` with that item now appearing in the trail.

- [ ] **Step 9: Commit**

```bash
git add templates/path_updated.html app.py static/style.css tests/test_app.py
git commit -m "feat: show resolved titles and per-item rationale on the path-updated screen"
```

---

## Self-Review Notes

- **Spec coverage:** raw-id fix → Task 5 (titles resolved via `get_item`). Real LLM-generated "why removed" → Tasks 2-3 (prompt extension + hallucination guard + fallback's mechanical equivalent). Add-back action → Task 4 (route) + Task 5 (button). Non-goals (no protection against future drops, no new LLM call for add-back) are honored by omission.
- **Placeholder scan:** every step has complete code. Tasks 3 and 4 explicitly flag where the plan's sketch of existing code (`plan_or_replan`, `submit_quiz`, `compute_plan`) may not match the current real file contents exactly (since prior features modified them) and instruct reading the real file first and preserving its existing validated behavior — this is a deliberate acknowledgment of drift risk, not a vague placeholder, since the instruction is concrete: read first, preserve existing behavior, only add what's specified.
- **Type consistency:** `DroppedItem`/`PlanResponse.dropped` (Task 1) are consumed identically by `planner.py` (Tasks 2-3) and `app.py`/the template (Tasks 4-5). `previous_item_ids: list[str] | None = None` is the consistent parameter name and type across `build_prompt`, `gemini_plan`, `rule_based_plan`, `plan_or_replan`, and `compute_plan`.
