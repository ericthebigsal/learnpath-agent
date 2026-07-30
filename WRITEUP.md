# Building an Adaptive Learning-Path Agent

*How `learnpath-agent` went from an interview-prep side project to a tool I actually use — and the real bugs, false alarms, and design calls that happened along the way.*

## Why this exists

I was deep in interview prep for a Senior TPM role owning Amazon Ads Academy — Amazon's real e-learning platform for advertisers. The recruiter was direct about one gap in my background: no hands-on experience with an LMS platform (Intellum, SCORM, that whole world). Rather than paper over it, I decided to build a small one myself — not to fake equivalent experience, but to actually understand the shape of the problem: a course catalog with levels and tracks, a certification model, and — the part that actually interested me — a personalization layer that adapts to how a learner is doing.

I modeled the taxonomy directly on the real Amazon Ads Academy site (I browsed the live catalog to get this right): content types (`course`, `learning_path`, `video`), three levels, tagged tracks, and a dual recognition model — certification badges for assessments, completion awards for learning paths. But instead of advertising content, I filled it with material about the exact techniques the project itself uses: RAG, multi-agent systems, LLM evaluation, context engineering, agent tooling, LLM billing. It's a small, honest joke — an LMS about AI, built by an AI, teaching you how the thing that built it works.

Then, partway through, the goalposts moved on purpose: I stopped treating it as a portfolio demo and started asking to actually use it — real accounts, real persistence, multiple tracks in parallel. That shift is most of what makes this writeup interesting.

## The core idea: an agent that shows its work

The centerpiece isn't the catalog — it's the planner. Every learner gets an **adaptive path**: instead of routing them through one of the catalog's fixed `learning_path` bundles, an agent plans a personalized sequence from their stated goal and level, then **re-plans it after every quiz** — inserting remedial material on a weak score, skipping ahead on a strong one.

The part I actually cared about getting right wasn't "can an LLM pick some courses" — that's easy. It was making the agent's reasoning something a learner (or a reviewer) can actually inspect and trust, rather than a black box that occasionally does something inexplicable. Four decisions do that work:

- **The candidate set is filtered before the LLM ever sees it.** A deterministic rule (substring-match the goal against track names, then level ± 1) narrows the whole catalog down to a visible shortlist first. The LLM ranks and explains *within* that shortlist — it never gets to search the entire catalog freely, so every item it could have picked is inspectable before the call even happens, and that same shortlist is rendered on the path screen as "candidates considered."
- **Structured output, not hand-parsed text.** The planner asks Gemini for a schema-validated `PlanResponse` (via `response_schema` on `GenerateContentConfig`) and reads `response.parsed` directly — never `json.loads`-ing a raw string and hoping.
- **A deterministic fallback for when the LLM isn't available.** If the API call fails, rate-limits, or returns something unusable, `plan_or_replan` catches it and falls back to a rule-based planner (sort candidates by level, then duration) — the app never has a single point of failure hanging off an external API's uptime.
- **Hallucination guards on both sides.** Even a *successful* LLM response gets its item ids checked against the real candidate set before being trusted — any id the model invents gets silently dropped, and if nothing survives, the whole response is treated as a failure and routed through the same fallback.

## How it was actually built

I used three different levels of process rigor, matched to how structurally risky each piece of work was:

**The two big, structural features** — the initial build (catalog, planner, five screens) and later, adding real accounts (email+password, sessions, renaming the whole "learner" concept into user-owned "tracks" so one account can run several goals in parallel) — went through the full cycle: a brainstormed design spec, a detailed TDD implementation plan, then execution where a *fresh subagent* implements each task, a separate *independent reviewer* subagent checks it against the spec before I ever look at it, a capped fix-loop for anything it finds, and a final whole-branch review — on the accounts feature, specifically a security-focused one — before anything ships.

**The smaller, well-scoped changes** — a full visual redesign, splitting quiz questions onto their own page so you can't just scroll up to cheat, and the explainable-diff feature below — I implemented directly in the same session, still spec-first and still fully tested, just without the separate-reviewer machinery. Matching the process to the actual risk, rather than running every change through the heaviest possible gate, kept the smaller stuff fast without skipping rigor on the parts that could actually break something.

Some real numbers, because a case study without them is just vibes: **43 commits**, 24 feature commits and 7 explicit bug fixes, **113 tests** (all of them run fully offline — the Gemini client is mocked everywhere, so the whole suite runs with no API key and no network access), a **54-item seed catalog** across the 7 tracks, and just over a thousand lines across the core modules (`models.py`, `catalog.py`, `db.py`, `quiz.py`, `planner.py`, `auth.py`, `app.py`).

## Real moments from the build

These aren't hypotheticals — every one of these is a genuine bug or false alarm found during this exact build, in the order they actually happened.

**The fallback that made things worse.**
The rule-based fallback planner sorted candidates by `item.level.value` — a plain string. `"advanced" < "beginner" < "intermediate"` alphabetically. That meant any time the real LLM call failed or rate-limited — the exact scenario the fallback exists to protect against — the app would confidently recommend *advanced* material first, to a *beginner*. It shipped, passed its own task's tests, and was caught by an independent reviewer who actually traced the sort order by hand instead of trusting that "sorted by level" meant what it said. Fixed by sorting on the level's position in an explicit ordered list instead of the string itself, with a regression test that pins the correct order.

**The bug the test suite could never catch.**
`google-genai`'s `Client()` only auto-detects a `GOOGLE_API_KEY` environment variable — not `GEMINI_API_KEY`, the name this project's own README told you to set. With no explicit key, every real API attempt raised, and the broad `except Exception` around it — there specifically so a flaky API never crashes the app — silently routed everything into the deterministic fallback with no visible error. The automated suite mocks the client everywhere, so it structurally could never catch this; it was only found by refusing to trust "the tests pass" and actually running the app with a real key, which is exactly the point of a manual smoke test that a plan explicitly calls for as a separate step from the test suite.

**The false alarm that was almost a real bug.**
Mid-way through the accounts feature, a live smoke test hit a genuine `500`: `no column named track_id`. The instinct is to panic and start migrating schemas. Instead: check whether a truly fresh install could ever hit this. It couldn't — the failure came from a stale, gitignored local database file left over from testing the *pre-accounts* version of the app, which `CREATE TABLE IF NOT EXISTS` correctly left untouched rather than silently corrupting. The fix was deleting one local file, not writing migration code the design had already explicitly decided wasn't needed. Diagnosing *why* something isn't a bug is as real a skill as fixing the ones that are.

**When the data was right and the UI wasn't.**
"I logged back in and it's like I never used the site" sounds like a data-loss bug. It wasn't — direct database inspection showed the account, the track, and the quiz progress were all exactly where they should be, and hitting the real endpoint with the user's actual session token rendered the track correctly. The actual problem: the track's title link had no underline and used ordinary body-text color, so it looked exactly like a plain heading instead of something clickable. "The data is correct" and "the product visibly works" are different claims, and it's worth actually checking which one a bug report is really about before reaching for either a data-recovery story or a UI fix.

**Teaching the agent to explain what it dropped.**
A user request that sounded like a small UI tweak — "show me why a course was added or removed, and let me add a removed one back" — turned out to need a real change to the planner's contract, not just its rendering. The agent could already explain what it *picked* (every step ships with a rationale); it had never been asked to explain what it *dropped*. That meant extending the prompt to tell the model what was previously planned and asking for a one-line reason per dropped item, adding a matching hallucination guard on that new field (never trust a dropped-item id that wasn't actually in the previous plan), and giving the deterministic fallback an equivalent — if more mechanical — answer, so the feature works identically whether or not the LLM is actually available that day.

**A real security review, on a real auth feature.**
Adding accounts meant a final review specifically scoped to auth risk: session tokens, password hashing, ownership checks, the works. It found two things worth naming. First, a reproducible bug: submitting an invalid starting level committed a track row *before* validating it, then 500'd on every future visit — a permanently broken, unremovable entry on the user's own dashboard. Second, a real product risk with no clean recovery: email wasn't normalized, so `Eric@Example.com` and `eric@example.com` could register as two different accounts, and this app deliberately has no password-reset flow — meaning a case-mismatch typo could lock someone out with no way back in. Both were verified by actually reproducing them live, not just reasoning about the code.

## What it's built on

FastAPI + Jinja2, no frontend framework. SQLite (five tables: users, sessions, tracks, progress, plan history), all raw `sqlite3` with explicit connection handling — no ORM. Gemini 2.5 Flash for the planning agent, called through Google's free tier, with structured-output schema validation on every call. `bcrypt` for password hashing, hand-rolled sessions (a `secrets.token_urlsafe` token in an httponly, `samesite=lax` cookie) rather than a session-management library, matching the rest of the project's "minimal dependencies, understand every layer" style. A from-scratch visual identity — a literal "trail" motif (solid for the path you're on, dashed for candidates the agent considered but didn't choose) reused consistently across the path, diff, and history screens, deliberately steering away from Duolingo's game-board look toward something closer to a transit map or a course bulletin.

## Where this could go next

Building this surfaced a real list of what would separate a portfolio demo from something that actually models improving a production Academy: a KPI/analytics view over the completion-rate and certification-attainment data the app already tracks but never surfaces in aggregate; a real content-authoring pipeline (the catalog is currently 54 hand-authored items, not an ingested content API); and an actual accessibility audit, since WCAG compliance is explicitly called out as a real requirement for the role that inspired this project in the first place. None of that changes what's here — it's the honest list of what "production" would still cost.

---

Source: [github.com/ericthebigsal/learnpath-agent](https://github.com/ericthebigsal/learnpath-agent)
