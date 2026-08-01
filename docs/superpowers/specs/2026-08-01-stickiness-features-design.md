# Stickiness Features (Badges + Review Widget) Design

**Goal:** Add non-coercive engagement features that encourage users to come back to learnpath-agent: a persisted badge/achievement system, and a passive spaced-repetition "due for review" widget. Explicitly excludes streaks (loss-aversion mechanic, ruled out as manipulative).

**Architecture:** Two independent additions on top of existing data, no new completion-tracking mechanism needed. Badges are computed once at well-defined trigger points and persisted (so "earned on X date" is a durable fact). The review widget is computed live on every dashboard/achievements load from existing `progress` rows — nothing new to persist there.

**Tech Stack:** Same as the rest of the app — FastAPI routes, Jinja2 templates, raw `sqlite3` via `db.py`, Pydantic models where relevant. No new dependencies.

## Global Constraints

- No streaks, no daily-login mechanics, no loss-aversion design (explicit user requirement).
- No outbound notifications (email/push) exist in this app and none are added — the review widget is passive, visible only when the user opens the dashboard on their own.
- `quiz_score` is stored on a 0-100 scale (`quiz.py:grade_quiz`, `round(100 * correct / len(quiz), 2)`), not 0-1. All thresholds in this spec use that scale.
- Follow existing code conventions: raw `sqlite3` access through `db.py` functions (never inline SQL in `app.py`), Jinja2 templates matching the visual language of `dashboard.html`/`history.html`, plain double-hyphens (` -- `) not em-dashes in any user-facing copy.

---

## Data Model

New table, added to `db.py`'s `SCHEMA` string:

```sql
CREATE TABLE IF NOT EXISTS badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge_type TEXT NOT NULL,
    track_id INTEGER NOT NULL DEFAULT 0,
    earned_at TEXT NOT NULL,
    UNIQUE(user_id, badge_type, track_id)
);
```

- `track_id` is `0` (sentinel, not `NULL`) for user-level badges (7 of the 8 types) and set to the relevant `tracks.id` for `track_master`, the one track-scoped badge. **Deliberately not `NULL`**: SQLite's `UNIQUE` constraint treats every `NULL` as distinct from every other `NULL`, so a `NULL` `track_id` would silently defeat the uniqueness check and let `INSERT OR IGNORE` insert duplicate rows for user-level badges. `0` is safe as a sentinel because `tracks.id` is an `AUTOINCREMENT` primary key starting at 1, so it can never collide with a real track.
- The `UNIQUE` constraint makes badge evaluation idempotent: re-running the check after every completion is safe, an `INSERT OR IGNORE` simply no-ops if already earned.
- No `db.py` function should ever `UPDATE` a badge row — badges are write-once facts.

## Badge Catalog

Eight badge types, each with an exact, mechanically-checkable trigger:

| `badge_type` | Trigger condition |
|---|---|
| `first_beginner_course` | The user's first-ever `progress` row (across all their tracks) where the completed item's `level == "beginner"` |
| `first_intermediate_course` | Same, `level == "intermediate"` |
| `first_advanced_course` | Same, `level == "advanced"` |
| `first_custom_path` | The user's first `progress` row recorded under a track whose `name == "Ad Hoc"` (the existing `AD_HOC_TRACK_NAME` constant in `app.py`) |
| `track_master` | For a given `track_id`: every `item_id` present in that track's `db.get_latest_plan(track_id)["steps"]` has at least one `progress` row for that `track_id`. Earned once per track (hence `track_id` set on the row). |
| `perfectionist` | The user's first `progress` row with `quiz_score == 100.0` |
| `explorer` | The user's first `plan_log` row with `trigger == "explore_open"`, across any of their tracks |
| `welcome_back` | Any `progress` row whose `completed_at` is at least 14 days after the user's chronologically preceding `progress` row (any track) — i.e. the user returned after a 14+ day gap and completed something |

"The user's" progress/plan_log rows means: joined through `tracks.user_id`, since `progress` and `plan_log` key off `track_id`, not `user_id` directly.

## Evaluation Points

A single function, `badges.evaluate_badges(user_id: int, db_path: str) -> list[str]`, re-checks all 8 conditions for a user and inserts (via `INSERT OR IGNORE`) any newly-satisfied ones, returning the `badge_type`s newly earned this call (empty list if none — used later for an optional "you earned a badge" flash, out of scope for this build but the return value costs nothing to include now).

Called from two places:
1. `app.py`'s `submit_quiz` (currently around line 503), immediately after `db.record_progress(...)`. Covers `first_beginner_course`, `first_intermediate_course`, `first_advanced_course`, `first_custom_path`, `track_master`, `perfectionist`, `welcome_back`.
2. `app.py`'s `explore_open_item` (currently around line 296), after the existing `plan_log` write with `trigger="explore_open"`. Covers `explorer`.

Re-checking all 8 conditions on both call sites is fine (cheap, idempotent) — the function does not need to know which subset is "relevant" to the caller.

## Review Scheduling Algorithm

Function `review.get_due_items(user_id: int, db_path: str) -> list[dict]`, computed live (no caching, no persisted schedule):

For each distinct `item_id` the user has completed at least once (across all their tracks):
- `n` = count of `progress` rows for that `(user, item_id)` pair, capped at 3
- `latest_score`, `latest_completed_at` = the values from the most recent such row (highest `id`)
- if `latest_score < 70`: `next_due = latest_completed_at + 1 day` (weak override — ignores the mastered ladder entirely)
- else: `next_due = latest_completed_at + [7, 30, 90][n - 1] days` (mastered ladder; once `n >= 3` it stays on the 90-day cadence)
- Include the item if `next_due <= now`

Sort results by how overdue they are (most overdue first). No "mark reviewed" action exists in the UI — retaking an item's quiz creates a new `progress` row via the existing `submit_quiz` flow, which naturally recomputes `n`/`latest_completed_at` and reschedules it. This is what keeps the feature fully passive: it requires no new user-facing verb, just the existing "take the quiz again" action.

## Display

**`dashboard.html`** (route in `app.py`, currently ~line 164): add two small sections above or alongside the existing track list —
- A badges strip: earned badge icons/labels (a fixed small icon or single-letter glyph per type is enough — no image assets required) plus a "View all →" link to `/achievements`.
- A "Due for review" list: up to 5 most-overdue items from `review.get_due_items()`, each a link to that item's existing page (`/item/{track_id}/{item_id}`) using whichever `track_id` the completion happened under.

**New route `/achievements`** (`achievements.html`): lists all 8 badge types. Earned ones show their `earned_at` date (formatted like the existing date formatting in `history.html`); locked ones show a short human-readable description of how to earn them, visually dimmed. `track_master` may show multiple earned rows (one per completed track) or a locked state per incomplete track — simplest correct behavior is to list it once per track the user has, each showing earned/locked independently.

## Testing

New test file `tests/test_badges.py` mirroring the structure of `tests/test_db.py`/`tests/test_app.py`:
- One test per badge trigger condition, seeding the minimum `progress`/`tracks`/`plan_log` rows needed to satisfy (and separately, to just barely *not* satisfy) each condition.
- A test confirming `evaluate_badges` is idempotent (calling it twice doesn't create duplicate rows or raise on the `UNIQUE` constraint).
- A test confirming `track_master` is scoped per-track (completing all items in track A doesn't award it for track B).

New test file `tests/test_review.py`:
- Weak-score override (score < 70 always due at +1 day regardless of `n`).
- Ladder progression at `n=1,2,3` (7/30/90 day boundaries), and confirms `n=4+` stays at 90.
- An item with no completions never appears; an item completed but not yet due doesn't appear.

Extend `tests/test_app.py` (or a new `tests/test_achievements_route.py`, matching whichever pattern the existing route tests use) with integration tests: `/achievements` renders 200 with expected badge names present, and the dashboard route includes the new badges/review sections without breaking existing dashboard assertions.
