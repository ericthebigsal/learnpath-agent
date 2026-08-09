# Catalog Category Generalization Design

**Goal:** Replace the hardcoded `Track` enum (`models.py`) with a data-driven
taxonomy, so `data/catalog.json` defines its own categories instead of the
Python source code defining them. This is step 1 of the next-phase build
order in `docs/platform-pilot-plan.md`, unblocked now that the Amperity
pilot closed with a Pass verdict — every later step (multi-tenancy,
per-org catalogs, an ingestion UI) is blocked on this one.

**Architecture:** No new subsystem, no DB table, no admin UI. `Track`
becomes `Category`, a plain data record embedded in `catalog.json` itself
(id, display name, keywords) instead of a closed enum baked into the
codebase. `CatalogItem.category` becomes a validated string instead of an
enum-typed field. All matching/filtering logic that used to iterate the
`Track` enum now iterates `catalog.categories` instead — same behavior,
different source of truth.

**Tech Stack:** No new dependencies. Same Pydantic v2 models, same
`catalog.json`-as-source-of-truth pattern already in use.

## Naming Decision (read this first)

This app already has an unrelated concept called "track": a **user's
personal learning journey** — the `tracks` DB table, `create_track`,
`get_tracks_for_user`, `/path/{track_id}`, the `track_master` badge. None
of that is the catalog taxonomy (`RAG`, `LLM Fundamentals`, etc.) — the
two concepts share a word by coincidence.

The catalog taxonomy is renamed **`Category`** throughout (code, JSON
schema, templates, query params). The user-journey `track` concept is
**untouched** — `db.py`, `app.py`'s `/tracks`/`/path/{track_id}` routes,
`badges.py`, and every `*.html` reference to "your tracks" stay exactly
as they are. Anywhere this doc says "track" it means the pre-existing,
unrelated, unchanged concept; everywhere else it says "category."

## Global Constraints

- No admin UI and no DB table for categories in this pass — that's a
  natural extension once multi-tenancy (build-order step 2) adds real
  admin roles and per-org scoping. Building admin CRUD now risks
  rebuilding it once tenancy exists.
- `validate_catalog.py`'s external (`--file`) mode must keep validating
  already-existing external content (the Amperity pilot catalog, the
  Stripe taxonomy test) without modification — those files have no
  `categories` key and shouldn't need one.
- Follow existing conventions: Pydantic v2 models in `models.py`, raw
  `sqlite3` untouched (this doesn't touch the DB at all), double-hyphens
  not em-dashes in any new copy.

---

## Data Model

`models.py`:

```python
class Category(BaseModel):
    id: str                                    # e.g. "rag" -- stable, referenced by items
    name: str                                   # e.g. "RAG" -- display label
    keywords: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    categories: list[Category]
    items: list[CatalogItem]
```

`CatalogItem.track: Track` becomes `CatalogItem.category: str` (stores a
`Category.id`). The `Track` enum (`models.py:18-27`) is deleted entirely.

`data/catalog.json` changes shape from a bare list to an object:

```json
{
  "categories": [
    {"id": "rag", "name": "RAG", "keywords": ["rag", "retrieval", "retrieval-augmented", "vector database", "vector db", "embeddings", "chunking", "reranking", "hybrid search"]},
    ...
  ],
  "items": [
    {"id": "...", "category": "rag", ...},
    ...
  ]
}
```

The 9 categories are seeded 1:1 from the current `Track` enum's values;
each one's `keywords` is seeded verbatim from `planner.py`'s existing
`TRACK_KEYWORDS` dict (see Migration below) — matching *behavior* doesn't
change, only where the data lives.

`catalog.py`'s `load_catalog()` adds a referential-integrity check after
parsing: every item's `category` must match a known `Category.id`, or it
raises. This replaces the safety the enum gave you at the type level with
an equivalent check at load time.

## Application Logic

`planner.py`:

- `TRACK_NAMES` / `TRACK_KEYWORDS` module-level constants are deleted —
  they were the hardcoded stand-in for what's now `catalog.categories`.
- `match_tracks(goal_text)` becomes `match_categories(goal_text, categories: list[Category]) -> list[str]`:
  identical substring-matching logic, reading `category.name` +
  `category.keywords` from the passed-in list instead of the module-level
  dict. Returns matched `Category.id`s instead of enum display names.
- `filter_candidates()` passes `catalog.categories` into
  `match_categories()` and filters on `item.category in matched_ids`
  instead of `item.track.value in matched_tracks`.
- `certification_ready_tracks()` becomes `certification_ready_categories()`:
  same logic, iterates `catalog.categories` instead of the `Track` enum.
- `rule_based_plan()`'s rationale string interpolates `item.category`
  directly (plain string now, no `.value`).
- `build_prompt()`'s candidate-line formatting (`item.track.value`) becomes
  `item.category`.

`app.py`:

- `/explore` route: query param `track: str | None` becomes
  `category: str | None`; local vars `track`/`selected_track` become
  `category`/`selected_category`; the filter
  `item.track.value == track` becomes `item.category == category`.
- Template context key `"tracks": [t.value for t in Track]` becomes
  `"categories": [c for c in CATALOG.categories]` — the filter dropdown
  uses `Category.id` as the option value (stable, URL-safe) and
  `Category.name` as the displayed label, matching how `item_id` vs. item
  title already work elsewhere in this app.
- The `Track` import is dropped from `app.py` and `planner.py`.
- **Untouched:** `active_track_id`, `user_tracks`, `get_owned_track`,
  `/tracks`, `/path/{track_id}` — the unrelated user-journey concept.

Templates (`explore.html`, `explore_starter_preview.html`, `item.html`,
`item_section.html`, `item_quiz.html`, `path.html`):

- `item.track.value` becomes `item.category` everywhere (plain string,
  no `.value`).
- `explore.html`'s filter dropdown: `name="track"` becomes
  `name="category"`; loop iterates `Category` objects, using `.id` as
  option `value` and `.name` as the visible label; `selected_track`
  becomes `selected_category`.

## Validation (`validate_catalog.py`)

- **This-repo mode** (default, no `--file`): expects the new
  `{categories, items}` shape. Adds one check to the existing suite
  (schema load, duplicate ids/headings, dangling `related_item_ids`,
  missing diagrams, quiz guessability): every item's `category` id exists
  in `categories`.
- **External `--file` mode**: `categories` is optional. If present, run
  the same referential-integrity check. If absent, `category` is treated
  as an unconstrained free-text field, exactly as it's treated implicitly
  today. This keeps `docs/pilot-amperity/amperity-pilot-catalog.json` and
  the Stripe taxonomy test file valid with zero changes to them.

## Migration

A one-time script (written, run once, then deleted — not permanent
tooling):

1. Read the current `data/catalog.json` (bare list).
2. Derive the 9 distinct `track` values present; build a `categories`
   array — `id` = slugified name (e.g. `"LLM Billing & Cost Models"` →
   `"llm-billing-cost-models"`), `name` = the original display value,
   `keywords` = copied from `planner.TRACK_KEYWORDS[name]`.
3. Rewrite every item's `"track"` field to `"category"`, holding the
   matching id (not the display name).
4. Write the new `{categories, items}` object back to `data/catalog.json`.
5. Run `validate_catalog.py` and the full test suite immediately after,
   as the correctness check on the migration itself.

## Testing

9 existing references across `test_planner_candidates.py`,
`test_catalog.py`, `test_models.py`, `test_planner_plans.py` update from
`Track.RAG` / `item.track` to plain category-id strings — mechanical
rename, no behavior change expected.

Two new tests in `test_catalog.py` for the referential-integrity check:
loading a catalog with a valid category passes; loading one with an
unknown category id raises.

## Out of Scope

- Any admin UI or DB-backed category CRUD (deferred to the multi-tenancy
  build-order step).
- Per-org / multi-tenant catalog scoping.
- Changing anything about the unrelated user-journey `track` concept
  (DB table, routes, badges).
