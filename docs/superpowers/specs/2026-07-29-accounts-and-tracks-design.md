# Accounts & Tracks — Design Spec

## Overview

Add real email+password accounts so `learnpath-agent` becomes a persistent, multi-track personal LMS instead of an anonymous single-session demo. Today's "learner" concept (one goal + one progress history, identified only by a raw database id in the URL) becomes a **track** — a user can run several tracks in parallel (one for RAG, one for Multi-Agent Systems, etc.), each keeping its own progress and plan history exactly as today. After logging in, a user lands on a dashboard listing their tracks plus a "start a new track" form, pre-filled with whatever starting level they used last time.

This is a personal-use pivot, not a portfolio-only change: the primary goal is that the app's owner (and potentially a small number of other known users) can actually use it as a real, returning tool, not just demo it once.

## Goals

- Real registration and login, with progress and preferences persisted per account rather than per anonymous browser session.
- Support multiple named tracks per user, each with independent progress and plan history.
- Remember the starting level a user picked last time as the default for their next new track.
- No track is ever visible or reachable by a user who doesn't own it.
- Keep the existing offline-testable philosophy: no real network calls (no email sending, no external OAuth) required to run the test suite.

## Non-goals

- No password reset / forgot-password flow (no email-sending infrastructure) — recovery is a manual database edit for now.
- No email verification.
- No invite codes or registration restrictions — registration is open, acceptable since this isn't deployed publicly yet.
- No rate-limiting on login attempts.
- No change to the planning agent, catalog, or any of the five existing screens' visual design — this spec is purely about identity and ownership around the existing functionality.

## Data model

Two new tables, one renamed and extended:

- **`users`**: `id` (PK), `email` (unique, not null), `password_hash` (not null), `default_starting_level` (not null, defaults to `"beginner"`), `created_at`.
- **`sessions`**: `token` (PK, a random opaque string), `user_id` (FK to `users.id`), `created_at`, `expires_at`. A logged-in browser holds `token` in an httponly, `samesite=lax` cookie. A row is deleted on logout or once past `expires_at`.
- **`learners` → renamed `tracks`**: adds `user_id` (FK to `users.id`, the owner) and `name` (a short display label). Existing columns (`goal_text`, `starting_level`, `created_at`) are unchanged in shape. `progress` and `plan_log` keep the same shape, with their `learner_id` foreign-key column renamed to `track_id` for consistency — nothing external depends on the old column name.

Since there is no live deployment and the SQLite file is local and gitignored, this is a clean schema replacement — no migration path for existing data is needed. `db.init_db` recreating the schema from scratch (dropping and recreating tables, or simply requiring a fresh `learnpath.db`) is acceptable.

`name` (the track's display label) is auto-derived from `goal_text` at creation time: the first 60 characters of the goal text, truncated at the nearest word boundary, with an ellipsis if truncated. No separate "name your track" UI step — keeps track creation exactly as fast as today's "start a new goal" flow.

## Auth & sessions

- Passwords are hashed with `bcrypt` (added as a new dependency) — never stored or logged in plain text.
- Sessions are hand-rolled, matching this app's existing "raw SQLite, no framework magic" style rather than pulling in a session-management library: on successful login, generate a token via `secrets.token_urlsafe(32)`, insert it into `sessions` with a 30-day expiry, and set it as the value of an httponly, `samesite=lax` cookie (not marked `secure`, since local development is plain HTTP — noted as a follow-up for whenever this is deployed behind HTTPS).
- A FastAPI dependency, `get_current_user`, reads the session cookie, looks up the `sessions` row, checks it hasn't expired, and resolves the owning `users` row — used by every track-scoped route. If the cookie is missing, the token doesn't exist, or it's expired, the dependency redirects to `/login` (for HTML page routes) rather than raising a raw 401.
- Every track-scoped route additionally verifies `track.user_id == current_user.id`. A track that doesn't exist and a track that exists but belongs to someone else both produce the same 404 — the app never confirms or denies whether a given track id exists to a user who doesn't own it.
- Registration is open — anyone who reaches `/register` can create an account. No invite code, no admin approval step.
- No password reset, no email verification, no login rate-limiting — all explicitly out of scope per the Non-goals above.

## Routes

- `GET /register` — registration form (email, password, confirm password).
- `POST /register` — creates the account (rejecting a duplicate email with a clear inline error), hashes the password, logs the user in immediately (creates a session, sets the cookie), redirects to `/`.
- `GET /login` — login form (email, password).
- `POST /login` — verifies credentials (a generic "email or password is incorrect" message on failure — never reveals which field was wrong), creates a session, redirects to `/`.
- `POST /logout` — deletes the current session row, clears the cookie, redirects to `/login`.
- `GET /` — the dashboard. Redirects to `/login` if not authenticated. Otherwise lists the current user's tracks (name, goal text, a short progress summary — e.g. "3 items completed") each linking to `/path/{track_id}`, plus the "start a new track" form (the same goal-text + starting-level inputs the old start screen had), with the starting-level select defaulted from `current_user.default_starting_level`.
- `POST /tracks` (replaces `POST /start`) — creates a track owned by the current user, computes its initial plan exactly as `POST /start` did today, and additionally updates `current_user.default_starting_level` to whatever level was just chosen. Redirects to `/path/{track_id}`.
- `GET /path/{track_id}`, `GET /item/{track_id}/{item_id}`, `POST /item/{track_id}/{item_id}/submit`, `GET /history/{track_id}` — same behavior as today, now additionally requiring `get_current_user` and the ownership check described above.

The old `GET /` (anonymous start form) and `POST /start` routes are replaced by the dashboard and `POST /tracks` above, not kept alongside them — there is no anonymous, unauthenticated path to creating a track.

## Testing

- New `tests/test_auth.py`: registration (including duplicate-email rejection), login (correct password succeeds, incorrect password fails with the generic error), session creation, session expiry (an expired session is treated as logged-out), and logout (session row is actually deleted, subsequent requests with the old cookie are treated as logged-out).
- A shared pytest fixture logs a test user in (registers, then extracts the session cookie) so existing track-scoped tests can call it before hitting `/path/{id}`, `/item/...`, etc. — every existing test that currently hits those routes anonymously is updated to log in first.
- A new ownership test: user A creates a track, user B logs in and requests `GET /path/{that_track_id}` — asserts a 404, not a 403 or a 200.
- Everything stays fully offline: `bcrypt` and SQLite both run in-process with no network access required, matching the project's existing "runs the whole suite with no API key or network" property (the Gemini-mocking convention from the planner tests is untouched by this work).

## Repo & tech stack additions

- New dependency: `bcrypt` (pinned in `requirements.txt`, matching the project's existing pinning convention).
- New modules: `auth.py` (password hashing/verification, session creation/lookup/deletion — mirrors `db.py`'s style: explicit `db_path` parameters, no hidden globals) is a natural home for this logic, keeping `app.py` focused on routing rather than growing a second responsibility inside it.
- New templates: `templates/register.html`, `templates/login.html`, `templates/dashboard.html` (replaces `templates/start.html`'s role as the logged-out landing page's content — the goal/level form itself is reused inside `dashboard.html`).

## Open questions

None outstanding — all prior open questions (auth mechanism, single vs. multiple goals per account, preferences scope, password reset scope) were resolved during the design discussion above.
