# Explainable Diff & Add-Back — Design Spec

## Overview

Extend the path-updated screen so every added, removed, and kept item is an expandable tile showing its resolved title (the diff currently shows raw item ids, a real bug) and a genuine rationale for why the agent made that call. Removed items additionally get an "Add it back" button that immediately reinserts them into the current path. Getting a real "why removed" reason requires extending the planner's contract — today `PlanResponse` explains what it picked, never what it dropped.

## Goals

- Fix the raw-item-id display bug in the diff screen.
- Show a genuine, agent-produced rationale for why each removed item was dropped, not a synthesized/generic one.
- Let a learner immediately reinsert a removed item into their current path with one click.
- Keep both planning paths (real Gemini call and rule-based fallback) producing this data, so the feature works identically regardless of which planner mode is active.

## Non-goals

- No protection against a future replan dropping a manually-added-back item again — it's a one-time insert, not a pinned/protected item. If a later quiz-triggered replan doesn't include it, the learner can add it back again.
- No change to how candidates are chosen or filtered — this only adds an explanation layer on top of decisions already being made.
- No new LLM call for the add-back action itself — it's a direct, mechanical insert.

## Planner changes

- New model `DroppedItem`: `{item_id: str, rationale: str}`.
- `PlanResponse` gains `dropped: list[DroppedItem] = []`.
- `plan_or_replan(client, catalog, track, progress, previous_item_ids=None)` — new optional parameter, the prior plan's step item ids (empty/`None` for the initial plan, where there's nothing to have dropped).
- `build_prompt` includes `previous_item_ids` (when non-empty) and instructs the model: for any of these it is not including in the new plan, explain why in one line as a `dropped` entry.
- `gemini_plan`'s existing hallucination guard (which filters `steps` to ids actually in the candidate set) gets a matching guard on `dropped`: filter to only ids that were actually in `previous_item_ids`, silently dropping anything hallucinated.
- `rule_based_plan(candidates, previous_item_ids=None, limit=5)` computes `dropped` mechanically: any id in `previous_item_ids` not present in the newly-selected `steps`, each with the rationale `"Fallback rule-based plan: no longer prioritized under simple level/duration ordering."`
- `plan_or_replan`'s return type is unchanged (`tuple[PlanResponse, bool, list[str]]`) — `dropped` rides inside the `PlanResponse` itself, not as a new tuple element.

## Add-back route

`POST /path/{track_id}/add/{item_id}`:
- Ownership-checked via the existing `get_owned_track` (identical 404 semantics as every other track-scoped route).
- 404s if `item_id` isn't a real catalog item.
- No LLM call, no candidate-set validation — this is a direct, explicit user override.
- Fetches the track's latest plan, appends a new step `{item_id, rationale: "Added back by you."}` to its existing steps (no-op / skip appending if the item is already present in the current steps, to avoid duplicates).
- Logs this as a new plan entry: `trigger: "manual_add"`, `dropped: []` (nothing was dropped by this action), `candidate_ids` carried forward unchanged from the plan it's amending.
- Redirects to `/path/{track_id}`.

## Path-updated screen

Replaces the three comma-joined lines (added/removed/kept) with one `<details>` tile per item:
- Summary line: the category tag (Added/Removed/Kept) + the item's resolved title (via `catalog.get_item`) — never a raw id.
- Expanding it reveals the rationale: for added/kept items, looked up from `new_plan.steps` (already real, already-computed data); for removed items, looked up from `new_plan.dropped`.
- Removed tiles additionally show an "Add it back" button posting to the new add-back route.
- The existing "Reordered" notice (when `diff.reordered` is true) is unchanged.

## Testing

- Planner: `gemini_plan` test asserting `dropped` entries come through when the mocked response includes them; a hallucination-guard test (a dropped id not in `previous_item_ids` gets filtered); `rule_based_plan` test asserting mechanical dropped-item computation with the fallback's rationale text; `plan_or_replan` tests for both the Gemini-success and fallback paths passing `previous_item_ids` through correctly.
- App: a new test for the add-back route (creates a track, submits a quiz that drops an item, posts to the add-back route, confirms the item reappears in the next `/path` response); a 404 test for a bad item id; a 404 test for another user's track; an updated path-updated test asserting resolved titles (not raw ids) and rationale text appear for both an added and a removed item.

## Open questions

None outstanding — all prior open questions (rationale source, add-back timing, add-back persistence through future replans) were resolved during the design discussion above.
