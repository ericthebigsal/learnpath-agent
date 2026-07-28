# learnpath-agent — Design Spec

## Overview

A small local web app that simulates a course catalog in the shape of Amazon Ads Academy's real product (course / learning path / video content types, beginner/intermediate/advanced levels, tagged tracks, a dual certification-badge-vs-completion-award recognition model), but with the content itself about modern AI/agentic concepts — the same territory as Eric's other portfolio projects (RAG, multi-agent systems, LLM evaluation, agent tooling, context engineering, LLM billing/cost models). The centerpiece is an **adaptive learning-path agent**: instead of routing a learner through one of the catalog's fixed static "Learning Path" bundles, an LLM agent builds a personalized sequence from a learner's stated goal and starting level, and re-plans it after every quiz result — inserting remedial content on a weak score, skipping ahead or flagging certification readiness on a strong one.

This is portfolio-first: judged on its own technical merit alongside the other five "built from scratch" projects on ericthebigsal.github.io. It also happens to plug a real gap named in Eric's Amazon Ads Academy Sr. TPM interview loop (no hands-on LMS platform experience) — useful color for a Dive Deep answer, not the design driver.

## Goals

- Demonstrate a genuinely adaptive (not just personalized-once) recommendation loop: plan → learner acts → plan changes visibly.
- Keep every agent decision transparent — candidates it could pick, and the rationale for what it did pick, are both visible to the user at all times.
- Match the existing portfolio's conventions: Python, pytest, offline-testable (no API key required to run the test suite), README with an elevator pitch, own top-level repo.
- Stay small enough to actually finish: no auth, no multi-user accounts, no real video/content hosting, no vector database.

## Non-goals

- Not a general-purpose LMS — no instructor/admin tooling, no content-authoring UI, no payment/enrollment flows.
- Not trying to replicate Amazon Ads Academy's actual content, catalog size, or product-specific tracks — the taxonomy shape is borrowed, the subject matter is not.
- Not building a multi-agent system for this project itself — the planner is a single agent making single stateless calls, not a crew of cooperating agents.

## Catalog & data model

Seed catalog of **~50-55 synthetic items** in `data/catalog.json`, using the real Ads Academy taxonomy shape:

- `type`: `course` | `learning_path` | `video`
- `level`: `beginner` | `intermediate` | `advanced`
- `duration_minutes`
- `track`: one of 7 — **LLM Fundamentals** (tokens, context windows, attention basics), **RAG**, **Multi-Agent Systems**, **LLM Evaluation & Testing** (judge-dread-style: deterministic + LLM-as-judge), **Agent Tools & Skills** (Claude Code, MCP, tool use), **Context Engineering**, **LLM Billing & Cost Models**
- `content`: a few paragraphs of real, written lesson text (not lorem ipsum — needs to be substantive enough for the agent's rationale and the learner's quiz to make sense)
- `quiz`: 3-5 multiple-choice questions with correct answers
- `certification_eligible`: bool

Composition target: 7 tracks × 3 levels × 2 items each (42) — the second item per track/level cell exists specifically so the agent has a real remedial or "skip ahead" alternate to offer, not just one fixed item per cell — plus ~5 foundational cross-track items (e.g. "What is an LLM, really?", "Choosing the right model for the job"), ~3 bundled `learning_path` items that reference multiple courses, and ~4 `certification_eligible` capstone assessments per a subset of tracks.

Learner state lives in SQLite (`learnpath.db`, matching the `docs-dashboard`/`searcher` pattern):

- `learners` (id, goal_text, starting_level, created_at)
- `progress` (learner_id, item_id, completed_at, quiz_score)
- `plan_log` (learner_id, created_at, proposed_item_ids_json, rationale_text, trigger — `initial` | `quiz_result`)

A "learner" is just a browser session tied to a row in this table — no auth, no accounts. Restarting the start flow creates a fresh learner.

## Planning agent

Each planning call is **stateless** — no conversation history to manage, matching the mockable, testable pattern already used in `JudgeDred`'s Gemini integration. Inputs to every call:

1. The learner's goal text and current level.
2. Full completed-item history with quiz scores.
3. A **candidate set** pre-filtered by simple rule-based logic: substring-match the goal text against the 7 track names (case-insensitive); if one or more match, restrict candidates to those tracks at the learner's current level ±1; if none match, use all tracks at the learner's current level. Already-completed items are always excluded. The LLM ranks and sequences *within* this candidate set rather than searching the whole catalog freely, so every item it could have picked is inspectable before the call happens.

The response is a structured, Pydantic-validated object via Gemini's structured-output mode (same approach `JudgeDred` uses for judge scoring): an ordered list of item IDs, a one-line rationale per item, and an overall plan summary string.

Re-planning triggers after every quiz submission, against a fixed passing threshold of **70%**:

- Score below 70% → insert a remedial alternate from the same track/level before continuing.
- Score 70-89% → continue to the next planned item as-is.
- Score 90%+ → optionally skip the paired alternate item at that level, move to the next level or track.
- Once all of a track's completed items average 70%+ → surface certification-capstone readiness for that track.

**Fallback:** if the Gemini call fails or rate-limits, fall back to a deterministic rule-based planner (filter candidates by level/tag match, sort by duration) so the app keeps functioning without the LLM — the agent enhances the plan's quality and rationale, it is not a single point of failure for the demo working at all.

## Web UI flow

A small FastAPI app, Jinja2 templates, no frontend framework — matching `docs-dashboard`'s and `searcher`'s actual convention. Five screens:

1. **Start** — free-text goal + starting-level picker. Submitting creates a learner row and triggers the first planning call.
2. **Current path** — the ordered recommended sequence with track/level/duration badges, plus a "Why this path" panel: per-item rationale and the overall plan summary. This is the screen that actually demonstrates the concept.
3. **Item view** — lesson content, then its quiz (multiple-choice form post). Submitting grades deterministically against the stored answer key and triggers a re-plan.
4. **Path updated** — a diff view after every re-plan: kept / added / removed / reordered, so the change is legible in one glance instead of the whole plan silently changing underneath the learner. This is the key screenshot/GIF screen for the portfolio write-up.
5. **Plan history / catalog browse** — a chronological log of every past plan with its rationale (useful for a demo GIF showing the path evolve over several quizzes), plus a simple filterable table of the whole catalog mirroring the real site's browse UI.

Certification-track readiness shows as a banner once a track's items clear the passing-average threshold.

## Testing

Every test mocks the Gemini client — the full suite runs offline, no API key required, exactly like `JudgeDred`'s "clone this repo and run the tests with no key at all" selling point. Coverage:

- Candidate-filtering logic: given a goal/level/progress state, is the right candidate subset produced?
- Rule-based fallback planner: fully deterministic, testable with no mocking at all.
- Quiz grading.
- Plan-diff computation (kept/added/removed/reordered).
- FastAPI routes via `TestClient`, with the planner mocked or swapped for the rule-based fallback.

## Repo & tech stack

- New top-level directory at `~/Documents/learnpath-agent` (sibling to `JudgeDred`, `RAG-project`, `agentic-example`), its own git repo.
- Python, FastAPI, Jinja2, Pydantic, `google-genai` (Gemini free tier, `gemini-2.5-flash` per `JudgeDred`'s existing pattern), SQLite (stdlib `sqlite3`), pytest.
- README with an elevator pitch in the same voice as the other project READMEs (problem → what it does → why it's built this way → quick start).
- Once built and working: a follow-up (separate, later) step adds a project card to `portfolio.md`/`.html`'s "AI Portfolio Projects" section and the homepage — not part of this build.

## Open questions

None outstanding — all prior open questions (interface, LLM choice, catalog realism/size, track list) were resolved during design discussion above.
