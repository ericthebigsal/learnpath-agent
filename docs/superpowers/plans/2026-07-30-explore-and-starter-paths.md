# Explore & Starter Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated `/explore` page where users browse the full catalog (filterable by track/level) and add any item to an existing track, plus 3 hand-curated starter learning paths (Product Manager, Engineer, Product Builder (Forward-Deployed)) that create a real track in one flow.

**Architecture:** One new pure-data module (`starter_paths.py`) holds the 3 fixed curricula. Two new template pages (`explore.html`, `explore_starter_preview.html`) and 4 new routes in `app.py` reuse the existing `get_owned_track`/`get_current_user` auth pattern and the existing `db.create_track`/`db.log_plan` functions — no new database tables, no LLM calls. The catalog table currently duplicated in `history.html` is removed in favor of linking to `/explore`.

**Tech Stack:** FastAPI, Jinja2, raw `sqlite3` via `db.py`, Pydantic v2 models — no new dependencies.

## Global Constraints

- No client-side JavaScript anywhere in this app — every interaction is a plain HTML form or link. Do not introduce `<script>` tags or `onchange`/`onclick` attributes; use explicit submit buttons instead.
- All new routes require authentication via the existing `get_current_user` FastAPI dependency; track ownership is checked via the existing `get_owned_track(track_id, current_user, db_path)` helper in `app.py`. An unauthorized or nonexistent track must return **404, not 403** — matches the app's established ownership-check convention.
- Starter paths are fixed, hand-authored data — never call `compute_plan` or the Gemini client for them. This keeps the test suite fully offline, matching the project's existing "no network calls in tests" property.
- Reuse existing CSS classes (`.badge`, `.trail`, `.trail-stop`, `.trail-title`, `.trail-tags`, `.trail-rationale`, `.catalog-table`, `.path-footer`, `.empty-state`) and design tokens (`--taken`, `--ink-muted`, `--border`, `--surface`, `--font-display`, `--font-mono`) rather than inventing new colors.
- No new dependencies.

---

### Task 1: Starter path data module

**Files:**
- Create: `starter_paths.py`
- Test: `tests/test_starter_paths.py`

**Interfaces:**
- Produces: `StarterPathStep` (dataclass: `item_id: str`, `rationale: str`), `StarterPath` (dataclass: `id: str`, `title: str`, `description: str`, `steps: list[StarterPathStep]`), `STARTER_PATHS: list[StarterPath]`, `get_starter_path(starter_id: str) -> StarterPath` (raises `KeyError` if not found — same contract as `catalog.get_item`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_starter_paths.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_starter_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'starter_paths'`

- [ ] **Step 3: Write the implementation**

Create `starter_paths.py`:

```python
from dataclasses import dataclass, field


@dataclass
class StarterPathStep:
    item_id: str
    rationale: str


@dataclass
class StarterPath:
    id: str
    title: str
    description: str
    steps: list[StarterPathStep] = field(default_factory=list)


STARTER_PATHS: list[StarterPath] = [
    StarterPath(
        id="product-manager",
        title="Product Manager",
        description="A breadth-first tour for PMs who need to speak credibly about AI systems without writing the code.",
        steps=[
            StarterPathStep("llmf-what-is-an-llm-really", "Grounds every later conversation in what the model actually is."),
            StarterPathStep("llmf-tokens-and-context-windows", "The vocabulary you'll need to read a token bill or a context limit."),
            StarterPathStep("llmf-prompting-basics", "The lowest-cost lever product teams reach for first."),
            StarterPathStep("llmf-choosing-the-right-model", "Model choice is a product tradeoff, not just an engineering one."),
            StarterPathStep("rag-fundamentals", "The most common pattern behind 'our AI knows our data.'"),
            StarterPathStep("ctx-what-is-context-engineering", "Explains why the same model behaves differently across products."),
            StarterPathStep("mas-what-is-a-multi-agent-system", "What 'agentic' actually means when a vendor pitches it to you."),
            StarterPathStep("eval-why-eval-llm-apps", "How teams know an AI feature is actually working before shipping it."),
            StarterPathStep("bill-how-token-pricing-works", "The unit economics question you'll get asked about in every review."),
        ],
    ),
    StarterPath(
        id="engineer",
        title="Engineer",
        description="Practical, build-oriented depth for engineers shipping AI features.",
        steps=[
            StarterPathStep("llmf-how-llms-generate-text", "The mechanics behind every downstream architecture decision."),
            StarterPathStep("llmf-embeddings-explained", "The primitive that RAG, search, and clustering all sit on top of."),
            StarterPathStep("rag-fundamentals", "The core pattern you'll implement first."),
            StarterPathStep("rag-chunking-strategies", "The single highest-leverage lever for RAG quality."),
            StarterPathStep("rag-vector-databases", "What's actually happening when you call a similarity search."),
            StarterPathStep("tools-function-calling-basics", "How a model goes from text to real side effects."),
            StarterPathStep("tools-designing-good-tool-schemas", "Bad schemas are the most common source of tool-calling bugs."),
            StarterPathStep("ctx-context-window-budgeting", "You'll hit this limit in production before you hit any other."),
            StarterPathStep("eval-golden-datasets-and-test-sets", "Without this, you can't tell a regression from noise."),
            StarterPathStep("bill-input-vs-output-token-costs", "Cost shows up in your design decisions, not just your invoice."),
        ],
    ),
    StarterPath(
        id="product-builder-fd",
        title="Product Builder (Forward-Deployed)",
        description="Agents, tools, and cost tradeoffs for builders deploying agentic systems directly with clients.",
        steps=[
            StarterPathStep("mas-what-is-a-multi-agent-system", "The architecture you'll be standing up on-site."),
            StarterPathStep("mas-orchestrator-vs-swarm-patterns", "The first design decision for any client deployment."),
            StarterPathStep("tools-what-are-agent-tools", "What actually connects an agent to a client's real systems."),
            StarterPathStep("mas-task-decomposition-and-delegation", "How work actually gets split across agents in practice."),
            StarterPathStep("tools-tool-selection-at-scale", "Client environments rarely have just one or two tools."),
            StarterPathStep("mas-handling-agent-failures-and-loops", "The failure mode that will page you at a client site."),
            StarterPathStep("rag-fundamentals", "How agents ground answers in a client's own data."),
            StarterPathStep("ctx-memory-and-state-management", "What survives between turns in a long-running client session."),
            StarterPathStep("eval-llm-as-judge", "How you'll demonstrate the system is working without a human reviewing every output."),
            StarterPathStep("bill-choosing-models-for-cost-efficiency", "Client budgets make model routing a real design constraint, not an afterthought."),
        ],
    ),
]


def get_starter_path(starter_id: str) -> StarterPath:
    for path in STARTER_PATHS:
        if path.id == starter_id:
            return path
    raise KeyError(f"No starter path with id {starter_id!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_starter_paths.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add starter_paths.py tests/test_starter_paths.py
git commit -m "feat: add hand-curated starter learning path data"
```

---

### Task 2: Shared add-to-track helper and `/explore/add/{item_id}` route

**Files:**
- Modify: `app.py`
- Test: Create `tests/test_explore.py`

**Interfaces:**
- Consumes: `db.get_latest_plan(track_id, db_path)`, `db.log_plan(track_id, plan_dict, trigger, db_path)`, `get_owned_track(track_id, current_user, db_path)`, `get_item(CATALOG, item_id)` — all existing.
- Produces: `_add_item_to_plan(track_id: int, item_id: str, trigger: str, rationale: str) -> None` (module-level helper in `app.py`), used by both `add_back_item` and the new `explore_add_item` route. Later tasks reuse this shared helper for no other purpose — it is not exported outside `app.py`.

The existing `POST /path/{track_id}/add/{item_id}` route inlines its "append item to latest plan if not already present" logic. This task extracts that into a shared helper so `/explore/add/{item_id}` can reuse it with a different trigger and rationale, instead of duplicating the logic.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_explore.py`:

```python
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

    def fake_compute_plan(track, progress, previous_item_ids=None):
        return (
            PlanResponse(
                steps=[PlanStep(item_id="rag-fundamentals", rationale="Matches your goal.")],
                summary="Start with RAG fundamentals.",
            ),
            False,
            ["rag-fundamentals", "rag-chunking-strategies"],
        )

    monkeypatch.setattr(app_module, "compute_plan", fake_compute_plan)

    with TestClient(app_module.app) as test_client:
        test_client.post(
            "/register",
            data={"email": "eric@example.com", "password": "hunter22", "confirm_password": "hunter22"},
        )
        yield test_client


def test_explore_add_inserts_item_and_redirects_to_lesson(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post(
        "/explore/add/rag-chunking-strategies",
        data={"track_id": 1},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/item/1/rag-chunking-strategies"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert any(step["item_id"] == "rag-chunking-strategies" for step in latest["steps"])
    assert latest["trigger"] == "explore_add"


def test_explore_add_does_not_duplicate_an_already_present_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    client.post("/explore/add/rag-fundamentals", data={"track_id": 1})

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    matching = [step for step in latest["steps"] if step["item_id"] == "rag-fundamentals"]
    assert len(matching) == 1


def test_explore_add_returns_404_for_nonexistent_item(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.post("/explore/add/does-not-exist", data={"track_id": 1})
    assert response.status_code == 404


def test_explore_add_returns_404_for_another_users_track(client):
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
        response = other_client.post("/explore/add/rag-fundamentals", data={"track_id": 1})

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_explore.py -v`
Expected: FAIL — `/explore/add/rag-chunking-strategies` returns 404 (route does not exist yet)

- [ ] **Step 3: Extract the shared helper and add the route**

In `app.py`, replace the body of `add_back_item` (currently at line 230) with a new module-level helper placed directly above it, then have `add_back_item` call it and add `explore_add_item` below it:

```python
def _add_item_to_plan(track_id: int, item_id: str, trigger: str, rationale: str) -> None:
    latest_plan = db.get_latest_plan(track_id, DB_PATH)
    existing_ids = {step["item_id"] for step in latest_plan["steps"]} if latest_plan else set()

    if item_id not in existing_ids:
        steps = list(latest_plan["steps"]) if latest_plan else []
        steps.append({"item_id": item_id, "rationale": rationale})
        plan_dict = {
            "steps": steps,
            "summary": latest_plan["summary"] if latest_plan else "",
            "dropped": [],
        }
        if latest_plan and "candidate_ids" in latest_plan:
            plan_dict["candidate_ids"] = latest_plan["candidate_ids"]
        db.log_plan(track_id, plan_dict, trigger, DB_PATH)


@app.post("/path/{track_id}/add/{item_id}")
def add_back_item(track_id: int, item_id: str, current_user: dict = Depends(get_current_user)):
    get_owned_track(track_id, current_user, DB_PATH)
    try:
        get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")

    _add_item_to_plan(track_id, item_id, "manual_add", "Added back by you.")
    return RedirectResponse(url=f"/path/{track_id}", status_code=303)


@app.post("/explore/add/{item_id}")
def explore_add_item(
    item_id: str,
    track_id: int = Form(...),
    current_user: dict = Depends(get_current_user),
):
    get_owned_track(track_id, current_user, DB_PATH)
    try:
        get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")

    _add_item_to_plan(track_id, item_id, "explore_add", "Added from the catalog.")
    return RedirectResponse(url=f"/item/{track_id}/{item_id}", status_code=303)
```

`Form` is already imported in `app.py` (`from fastapi import Depends, FastAPI, Form, HTTPException, Request`), so no import changes are needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_explore.py tests/test_app.py -v`
Expected: PASS — new tests pass, and the existing `test_add_back_route_*` tests in `tests/test_app.py` still pass unchanged (the helper produces identical behavior for `add_back_item`).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_explore.py
git commit -m "feat: add /explore/add route via a shared add-to-track helper"
```

---

### Task 3: `GET /explore` page — catalog browsing, filters, and starter-path cards

**Files:**
- Modify: `app.py`
- Modify: `templates/base.html`
- Create: `templates/explore.html`
- Modify: `static/style.css`
- Modify: `tests/test_explore.py`

**Interfaces:**
- Consumes: `STARTER_PATHS` from `starter_paths.py` (Task 1), `Track`/`Level` enums from `models.py`, `db.get_tracks_for_user` (existing).
- Produces: `GET /explore` route rendering `templates/explore.html`. The starter-path cards link to `/explore/starter/{id}`, which does not exist until Task 4 — this is fine, since this task's tests never click through those links, only assert they render.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explore.py`:

```python
def test_explore_lists_all_catalog_items_with_no_filters(client):
    response = client.get("/explore")

    assert response.status_code == 200
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    assert "What Is an LLM, Really?" in response.text


def test_explore_filters_by_track(client):
    response = client.get("/explore", params={"track": "RAG"})

    assert response.status_code == 200
    assert "RAG Fundamentals: Retrieval Meets Generation" in response.text
    assert "What Is an LLM, Really?" not in response.text


def test_explore_filters_by_level(client):
    response = client.get("/explore", params={"level": "advanced"})

    assert response.status_code == 200
    assert "RAG Practitioner Certification Assessment" in response.text
    assert "What Is an LLM, Really?" not in response.text


def test_explore_redirects_to_login_when_not_authenticated(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    db.init_db(db_path)

    with TestClient(app_module.app) as anon_client:
        response = anon_client.get("/explore", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_explore_shows_add_to_track_control_when_user_has_a_track(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/explore")

    assert 'action="/explore/add/rag-fundamentals"' in response.text


def test_explore_shows_hint_when_user_has_no_tracks(client):
    response = client.get("/explore")

    assert "Start a track first" in response.text


def test_explore_shows_starter_path_cards(client):
    response = client.get("/explore")

    assert 'href="/explore/starter/product-manager"' in response.text
    assert "Product Manager" in response.text
    assert "Engineer" in response.text
    assert "Product Builder (Forward-Deployed)" in response.text


def test_explore_nav_link_appears_on_dashboard(client):
    response = client.get("/")

    assert 'href="/explore"' in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_explore.py -v`
Expected: FAIL — `/explore` returns 404 (no such route), nav link test fails (no such link in `base.html`)

- [ ] **Step 3: Add the route**

In `app.py`, change the models import to include `Track`:

```python
from models import Level, PlanResponse, Track
```

Add near the top-level imports:

```python
from starter_paths import STARTER_PATHS
```

Add the route (near the other `GET` routes, e.g. after `add_back_item`/`explore_add_item` from Task 2):

```python
@app.get("/explore", response_class=HTMLResponse)
def explore(
    request: Request,
    track: str | None = None,
    level: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    items = CATALOG.items
    if track:
        items = [item for item in items if item.track.value == track]
    if level:
        items = [item for item in items if item.level.value == level]

    return templates.TemplateResponse(
        request,
        "explore.html",
        {
            "request": request,
            "current_user": current_user,
            "items": items,
            "tracks": [t.value for t in Track],
            "levels": [lvl.value for lvl in Level],
            "selected_track": track or "",
            "selected_level": level or "",
            "user_tracks": db.get_tracks_for_user(current_user["id"], DB_PATH),
            "starter_paths": STARTER_PATHS,
        },
    )
```

- [ ] **Step 4: Add the nav link in `base.html`**

Replace the header block in `templates/base.html`:

```html
  <header class="site-header">
    <a class="site-mark" href="/">learnpath-agent</a>
    {% if current_user %}
    <form method="post" action="/logout" class="logout-form">
      <span class="site-user">{{ current_user.email }}</span>
      <button type="submit" class="logout-button">Log out</button>
    </form>
    {% else %}
    <span class="site-tag">plans your path, then rewrites it as you learn</span>
    {% endif %}
  </header>
```

with:

```html
  <header class="site-header">
    <a class="site-mark" href="/">learnpath-agent</a>
    {% if current_user %}
    <nav class="site-nav">
      <a class="nav-link" href="/explore">Explore</a>
      <form method="post" action="/logout" class="logout-form">
        <span class="site-user">{{ current_user.email }}</span>
        <button type="submit" class="logout-button">Log out</button>
      </form>
    </nav>
    {% else %}
    <span class="site-tag">plans your path, then rewrites it as you learn</span>
    {% endif %}
  </header>
```

- [ ] **Step 5: Create `templates/explore.html`**

```html
{% extends "base.html" %}
{% block title %}Explore — learnpath-agent{% endblock %}
{% block content %}
<p class="eyebrow">Explore</p>
<h1>Find your next track</h1>

<h2>Starter paths</h2>
<div class="starter-grid">
  {% for starter in starter_paths %}
  <a class="starter-card" href="/explore/starter/{{ starter.id }}">
    <span class="trail-title">{{ starter.title }}</span>
    <p class="starter-description">{{ starter.description }}</p>
  </a>
  {% endfor %}
</div>

<h2>Browse the catalog</h2>
<form class="explore-filters" method="get" action="/explore">
  <div>
    <label for="track">Track</label>
    <select id="track" name="track">
      <option value="">All tracks</option>
      {% for t in tracks %}
      <option value="{{ t }}" {% if t == selected_track %}selected{% endif %}>{{ t }}</option>
      {% endfor %}
    </select>
  </div>
  <div>
    <label for="level">Level</label>
    <select id="level" name="level">
      <option value="">All levels</option>
      {% for lvl in levels %}
      <option value="{{ lvl }}" {% if lvl == selected_level %}selected{% endif %}>{{ lvl | capitalize }}</option>
      {% endfor %}
    </select>
  </div>
  <button type="submit">Filter</button>
</form>

<div class="explore-grid">
  {% for item in items %}
  <div class="explore-card">
    <span class="trail-title">{{ item.title }}</span>
    <div class="trail-tags">
      <span class="badge">{{ item.track.value }}</span>
      <span class="badge">{{ item.level.value }}</span>
      <span class="badge">{{ item.duration_minutes }}m</span>
    </div>
    {% if user_tracks %}
    <form class="explore-add-form" method="post" action="/explore/add/{{ item.id }}">
      <select name="track_id">
        {% for t in user_tracks %}
        <option value="{{ t.id }}">{{ t.name }}</option>
        {% endfor %}
      </select>
      <button type="submit">Add to track</button>
    </form>
    {% else %}
    <p class="explore-empty-hint">Start a track first to add this course to it.</p>
    {% endif %}
  </div>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 6: Add CSS**

Append to `static/style.css`:

```css
/* ---------- explore ---------- */

.site-nav {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.nav-link {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--ink-muted);
  text-decoration: none;
}

.nav-link:hover { color: var(--ink); text-decoration: underline; }

.starter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.starter-card {
  display: block;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  background: var(--surface);
  text-decoration: none;
  color: var(--ink);
  transition: border-color 0.15s ease;
}

.starter-card:hover { border-color: var(--taken-border); }

.starter-description {
  color: var(--ink-muted);
  font-size: 0.9rem;
  margin: 0.4rem 0 0;
}

.explore-filters {
  display: flex;
  gap: 1.5rem;
  align-items: flex-end;
  flex-wrap: wrap;
  margin-bottom: 2rem;
}

.explore-filters select { margin-bottom: 0; min-width: 180px; }

.explore-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.explore-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  background: var(--surface);
}

.explore-add-form { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
.explore-add-form select { width: auto; margin-bottom: 0; flex: 1; }
.explore-add-form button { padding: 0.5rem 0.9rem; font-size: 0.85rem; }

.explore-empty-hint { color: var(--ink-muted); font-size: 0.9rem; margin: 0.75rem 0 0; }
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_explore.py tests/test_app.py -v`
Expected: PASS (all new tests, plus no regressions in existing dashboard/header-dependent tests)

- [ ] **Step 8: Commit**

```bash
git add app.py templates/base.html templates/explore.html static/style.css tests/test_explore.py
git commit -m "feat: add /explore page with catalog filters and starter-path cards"
```

---

### Task 4: Starter path preview and confirm routes

**Files:**
- Modify: `app.py`
- Create: `templates/explore_starter_preview.html`
- Modify: `tests/test_explore.py`

**Interfaces:**
- Consumes: `get_starter_path` from `starter_paths.py` (Task 1), `db.create_track`, `db.log_plan` (existing).
- Produces: `GET /explore/starter/{starter_id}` and `POST /explore/starter/{starter_id}` routes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_explore.py`:

```python
from starter_paths import get_starter_path


def test_explore_starter_preview_shows_all_steps_with_rationale(client):
    response = client.get("/explore/starter/product-manager")

    assert response.status_code == 200
    assert "What Is an LLM, Really?" in response.text
    assert "Grounds every later conversation in what the model actually is." in response.text
    assert 'action="/explore/starter/product-manager"' in response.text


def test_explore_starter_preview_returns_404_for_unknown_id(client):
    response = client.get("/explore/starter/does-not-exist")
    assert response.status_code == 404


def test_explore_starter_confirm_creates_track_with_fixed_plan(client):
    response = client.post("/explore/starter/engineer", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/path/1"

    track = db.get_track(1, app_module.DB_PATH)
    assert track["name"] == "Engineer"

    latest = db.get_latest_plan(1, app_module.DB_PATH)
    assert latest["trigger"] == "starter"
    expected = get_starter_path("engineer")
    assert [step["item_id"] for step in latest["steps"]] == [s.item_id for s in expected.steps]


def test_explore_starter_confirm_returns_404_for_unknown_id(client):
    response = client.post("/explore/starter/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_explore.py -v`
Expected: FAIL — `/explore/starter/product-manager` returns 404 (route does not exist yet)

- [ ] **Step 3: Add the routes**

In `app.py`, change the starter_paths import to:

```python
from starter_paths import STARTER_PATHS, get_starter_path
```

Add the two routes (near the `/explore` route added in Task 3):

```python
@app.get("/explore/starter/{starter_id}", response_class=HTMLResponse)
def explore_starter_preview(
    request: Request, starter_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        starter_path = get_starter_path(starter_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Starter path not found")

    steps = [
        {"item": get_item(CATALOG, step.item_id), "rationale": step.rationale}
        for step in starter_path.steps
    ]

    return templates.TemplateResponse(
        request,
        "explore_starter_preview.html",
        {
            "request": request,
            "current_user": current_user,
            "starter_path": starter_path,
            "steps": steps,
        },
    )


@app.post("/explore/starter/{starter_id}")
def explore_starter_confirm(starter_id: str, current_user: dict = Depends(get_current_user)):
    try:
        starter_path = get_starter_path(starter_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Starter path not found")

    track = db.create_track(
        current_user["id"],
        starter_path.title,
        starter_path.description,
        current_user["default_starting_level"],
        DB_PATH,
    )
    plan_dict = {
        "steps": [
            {"item_id": step.item_id, "rationale": step.rationale}
            for step in starter_path.steps
        ],
        "summary": starter_path.description,
        "dropped": [],
    }
    db.log_plan(track["id"], plan_dict, "starter", DB_PATH)
    return RedirectResponse(url=f"/path/{track['id']}", status_code=303)
```

- [ ] **Step 4: Create `templates/explore_starter_preview.html`**

```html
{% extends "base.html" %}
{% block title %}{{ starter_path.title }} — learnpath-agent{% endblock %}
{% block content %}
<p class="eyebrow">Starter path</p>
<h1>{{ starter_path.title }}</h1>
<p class="goal">{{ starter_path.description }}</p>

<ol class="trail">
  {% for step in steps %}
  <li class="trail-stop">
    <span class="trail-marker">&middot;</span>
    <div class="trail-body">
      <span class="trail-title">{{ step.item.title }}</span>
      <div class="trail-tags">
        <span class="badge">{{ step.item.track.value }}</span>
        <span class="badge">{{ step.item.level.value }}</span>
        <span class="badge">{{ step.item.duration_minutes }}m</span>
      </div>
      <p class="trail-rationale">{{ step.rationale }}</p>
    </div>
  </li>
  {% endfor %}
</ol>

<form method="post" action="/explore/starter/{{ starter_path.id }}">
  <button type="submit">Start this path</button>
</form>

<p class="path-footer"><a href="/explore">Back to Explore</a></p>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_explore.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/explore_starter_preview.html tests/test_explore.py
git commit -m "feat: add starter path preview and confirm routes"
```

---

### Task 5: Consolidate the catalog table out of `history.html`

**Files:**
- Modify: `templates/history.html`
- Modify: `app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- None new — this task removes a now-redundant inline catalog table and points to `/explore` instead.

- [ ] **Step 1: Update the existing test that depends on the old table**

In `tests/test_app.py`, find `test_history_screen_shows_no_completed_courses_yet` (currently asserting `"RAG Fundamentals" in response.text  # still shows in the full catalog table`) and replace its body with:

```python
def test_history_screen_shows_no_completed_courses_yet(client):
    client.post(
        "/tracks",
        data={"goal_text": "I want to learn about RAG", "starting_level": "beginner"},
    )

    response = client.get("/history/1")

    assert response.status_code == 200
    assert "No courses completed yet" in response.text
    assert 'href="/explore"' in response.text
```

- [ ] **Step 2: Run test to verify it fails against current behavior**

Run: `pytest tests/test_app.py::test_history_screen_shows_no_completed_courses_yet -v`
Expected: FAIL — `href="/explore"` is not yet present in `history.html`

- [ ] **Step 3: Update `templates/history.html`**

Replace the full contents of `templates/history.html` with:

```html
{% extends "base.html" %}
{% block title %}History — learnpath-agent{% endblock %}
{% block content %}
<p class="eyebrow">Registrar</p>
<h1>Courses completed</h1>

{% if completed %}
<div class="catalog-table-wrap">
<table class="catalog-table">
  <thead>
    <tr><th>Course</th><th>Result</th><th>Completed</th></tr>
  </thead>
  <tbody>
    {% for entry in completed %}
    <tr>
      <td>{{ entry.item.title }}</td>
      <td>{{ entry.quiz_score }}%</td>
      <td>{{ entry.completed_at }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<p class="empty-state">No courses completed yet — head back to your path to get started.</p>
{% endif %}

<p class="path-footer">
  <a href="/path/{{ track_id }}">Back to your path</a> &middot;
  <a href="/explore">Browse the full catalog</a>
</p>
{% endblock %}
```

- [ ] **Step 4: Remove the now-unused `catalog` context value in `app.py`**

In the `history_page` route, remove the `"catalog": CATALOG.items,` line from the `TemplateResponse` context dict, leaving:

```python
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "completed": completed,
        },
    )
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS — all tests, including the updated history test and every test from Tasks 1-4.

- [ ] **Step 6: Commit**

```bash
git add templates/history.html app.py tests/test_app.py
git commit -m "refactor: link history page to /explore instead of duplicating the catalog table"
```

---

## Final Verification

After all 5 tasks:

```bash
pytest -v
```

Expected: all tests pass, including `tests/test_starter_paths.py`, `tests/test_explore.py`, and the updated `tests/test_app.py`.

Then manually smoke-test: log in, visit `/explore`, filter by a track and a level, click a starter path preview, confirm one, verify it lands on `/path/{track_id}` with the exact curated steps, then go back to `/explore` and add one more catalog item to an existing track from the catalog grid.
