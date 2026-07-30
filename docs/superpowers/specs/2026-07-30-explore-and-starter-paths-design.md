# Explore & Starter Paths — Design Spec

## Overview

Today the only way to see what's in the catalog is a static, unfiltered table buried at the bottom of a specific track's history page (`/history/{track_id}`), and the only way to start learning something is to type free-text goal text into the planner. This spec adds a single, dedicated **Explore** page reachable from the home page nav that lets a user (1) browse and filter the full 54-item catalog and add any item straight into an existing track, and (2) pick one of three hand-curated **starter paths** — pre-built curricula for common personas (Product Manager, Engineer, Product Builder (Forward-Deployed)) — as a one-click way to get a real track going without writing a goal.

This consolidates catalog browsing into one place (replacing the old table in `history.html`) and gives new or exploratory users a lower-friction on-ramp than the blank goal-text box.

## Goals

- A user can browse the entire catalog, filtered by track and level, from a page linked off the home page nav.
- A user can add any catalog item directly to one of their existing tracks from that browse view, without writing a goal.
- A user can preview and then adopt one of 3 hand-curated starter paths as a new track in one flow.
- The catalog table currently duplicated in `history.html` is removed in favor of linking to Explore.

## Non-goals

- No free-text search — filtering is by `track` and `level` dropdowns only (matches the existing `starting_level` select pattern already used on the dashboard).
- No LLM involvement in starter paths — they are fixed, hand-authored sequences, not planner output. No variability run to run.
- No standalone/trackless lesson viewing — lessons remain scoped to `/item/{track_id}/{item_id}` exactly as today; Explore's "add to track" flow reuses that existing constraint rather than changing it.
- No new starter-path authoring UI — the 3 curricula are defined once in code, not user-editable.
- No changes to the planner, quiz submission, or certification logic.

## Data model

No new database tables. One new pure-data module, `starter_paths.py`, defining the 3 personas as an in-code constant:

```python
from dataclasses import dataclass

@dataclass
class StarterPathStep:
    item_id: str
    rationale: str

@dataclass
class StarterPath:
    id: str            # e.g. "product-manager"
    title: str          # e.g. "Product Manager"
    description: str    # one-sentence framing shown on the picker card
    steps: list[StarterPathStep]

STARTER_PATHS: list[StarterPath] = [...]
```

Each `StarterPath.steps` list becomes a track's initial plan verbatim — same shape as a `PlanStep` (`item_id` + `rationale`), so it round-trips through the existing `db.log_plan` unchanged.

### The 3 curricula

**`product-manager` — "Product Manager"** (breadth over depth; skip implementation internals)
1. `llmf-what-is-an-llm-really`
2. `llmf-tokens-and-context-windows`
3. `llmf-prompting-basics`
4. `llmf-choosing-the-right-model`
5. `rag-fundamentals`
6. `ctx-what-is-context-engineering`
7. `mas-what-is-a-multi-agent-system`
8. `eval-why-eval-llm-apps`
9. `bill-how-token-pricing-works`

**`engineer` — "Engineer"** (practical build depth)
1. `llmf-how-llms-generate-text`
2. `llmf-embeddings-explained`
3. `rag-fundamentals`
4. `rag-chunking-strategies`
5. `rag-vector-databases`
6. `tools-function-calling-basics`
7. `tools-designing-good-tool-schemas`
8. `ctx-context-window-budgeting`
9. `eval-golden-datasets-and-test-sets`
10. `bill-input-vs-output-token-costs`

**`product-builder-fd` — "Product Builder (Forward-Deployed)"** (agents, tools, failure handling, cost; client-facing)
1. `mas-what-is-a-multi-agent-system`
2. `mas-orchestrator-vs-swarm-patterns`
3. `tools-what-are-agent-tools`
4. `mas-task-decomposition-and-delegation`
5. `tools-tool-selection-at-scale`
6. `mas-handling-agent-failures-and-loops`
7. `rag-fundamentals`
8. `ctx-memory-and-state-management`
9. `eval-llm-as-judge`
10. `bill-choosing-models-for-cost-efficiency`

Every `item_id` above must exist in `data/catalog.json` — enforced by a test (see Testing) in the same spirit as the planner's hallucination guard on LLM-returned ids.

## Routes

- `GET /explore?track=&level=` — the Explore page. Both query params optional; when present, filter `CATALOG.items` by exact match (same `Track`/`Level` enums used elsewhere). Renders:
  - The 3 starter path cards (title + description) up top, each linking to its preview.
  - Below, the filtered catalog as cards (title, track, level, duration, type), each with a control to add it to one of the user's existing tracks.
  - If the user has zero tracks, catalog item cards show a prompt to start one (linking to a starter path or the dashboard's goal form) instead of a track picker.
- `POST /explore/add/{item_id}` — form fields `track_id`. Verifies the user owns `track_id` (reuses `get_owned_track`), then delegates to the same logic `POST /path/{track_id}/add/{item_id}` already uses today. Redirects to `/item/{track_id}/{item_id}`.
- `GET /explore/starter/{starter_id}` — preview page for one starter path: title, description, and the full ordered step list with each rationale, plus a confirm button. 404 if `starter_id` doesn't match a known `StarterPath`.
- `POST /explore/starter/{starter_id}` — creates a new track for the current user (`name` = the starter path's `title`, `goal_text` = its `description`, `starting_level` = the user's `default_starting_level`), then calls `db.log_plan(track_id, {"steps": [...], "summary": ..., "dropped": []}, trigger="starter")` using the fixed steps verbatim (no `compute_plan`, no LLM call, no candidate set — this is a fixed plan, not a computed one). Redirects to `/path/{track_id}`, which renders it exactly like any other track since the plan shape is identical.

Existing route `POST /path/{track_id}/add/{item_id}` is unchanged; `/explore/add/{item_id}` reuses its underlying add-item logic rather than duplicating it (refactor the shared piece into a `db`/helper function both routes call, if it isn't already isolated).

## Template & nav changes

- `templates/base.html`: add an "Explore" link in the header, next to the user email/logout button, visible only when `current_user` is set.
- New `templates/explore.html`: starter path cards + filter dropdowns + catalog item cards, following the existing badge/card visual language already used in `path.html` (`.badge`, `.trail-*` classes) rather than inventing new visual patterns.
- New `templates/explore_starter_preview.html`: ordered step list with rationale, matching the visual treatment of the trail list in `path.html`.
- `templates/history.html`: remove the "Full catalog" table and its heading; replace with `<p class="path-footer"><a href="/explore">Browse the full catalog</a></p>` alongside the existing "back to your path" link.

## Testing

- `tests/test_starter_paths.py`: every `item_id` referenced by every `StarterPath` exists in the real catalog (loaded via the existing `load_catalog()`), each starter path has at least one step, and `id`s are unique across the 3 paths.
- `tests/test_app.py` (or a new `tests/test_explore.py`, matching however route tests are currently split): 
  - `GET /explore` with no filters returns all catalog items; with `track=` and/or `level=` returns only matching items.
  - `GET /explore/starter/{id}` renders the right steps for a known id; 404 for an unknown id.
  - `POST /explore/starter/{id}` creates a track owned by the current user with a plan matching that starter path's steps exactly, and redirects to `/path/{track_id}`.
  - `POST /explore/add/{item_id}` with a `track_id` the user doesn't own is rejected the same way the existing add-item route rejects it (404, not 403 — matching this app's established ownership-check convention).
- `history.html`'s existing tests (if any assert on the catalog table) are updated to assert the "Browse the full catalog" link instead.

## Open questions

None outstanding — placement, click-through behavior, starter-path authoring approach, and the 3 curricula were all resolved during the design discussion above.
