# Platform Pivot — Pilot Validation Plan

**Status:** pilot run 2026-08-06 against docs.amperity.com, scored below. Decision
gate: **Pass, with a process caveat** (see Pilot Log / Decision gate). Read this
top to bottom before starting further pilots or scoping the next-phase build.

## The core question

`learnpath-agent` currently teaches one topic (AI/agentic concepts) with content
I authored by hand. The idea on the table: turn it into a topic-agnostic
platform companies pay for, by pointing the same content pipeline at a
company's own internal training material instead of my own prompts.

Before building any platform infrastructure (multi-tenancy, admin UI,
billing, SSO), we need to answer one question cheaply: **does the
content-authoring pipeline actually produce good training material on a
domain that isn't AI/LLM concepts?** Everything else is infrastructure we
already know how to build. This is the one unknown worth derisking first.

This document is the playbook for that pressure test, to run once a pilot
topic exists. It assumes no memory of the conversation that produced it —
follow it as a standalone recipe.

## Picking the pilot topic

Deliberately **do not** pick another AI/technical/procedural topic — that
would just repeat what already worked and prove nothing. Look for something
that's representative of what real companies actually hand over: dense,
somewhat unglamorous, not naturally visual. Good candidates:

- HR onboarding (benefits, policies, tools, who's-who)
- A compliance or safety policy set (the kind with a lot of "must/must not"
  language and few diagrammable processes)
- A customer-support playbook or product-support runbook
- A sales enablement deck set for a moderately technical product

Get **5-15 real source documents** from whatever candidate you land on —
actual SOPs, wiki pages, slide decks, PDFs. Messy and real, not pre-cleaned.
A real customer will upload exactly this kind of material, not a tidy
outline.

## The pilot procedure

Run this as a scaled-down replay of the same process used to build the
existing 47-course catalog in this repo (see `data/catalog.json` and the
commit history for `feat: expand ... courses` for the actual mechanics).

### 1. Derive a taxonomy from the material

Read through the source documents and identify the natural groupings —
this is the pilot's version of this app's `Track` enum. Don't force the
existing 7 AI-topic tracks; let the real material's own structure suggest
its own categories. Note whether a clean grouping emerges easily or feels
forced — that's itself a data point about whether the taxonomy model
generalizes.

### 2. Draft a course-shape spec per topic

For each topic/lesson the material implies, write (by hand, this step
isn't automated yet):
- A short "legacy content" stub — a paragraph summarizing what the source
  material says, the same role `content` plays in `models.py`'s
  `CatalogItem`.
- A 3-question quiz with a stated correct answer per question, grounded in
  facts actually present in the source material.

This mirrors exactly what was fed to each content-authoring subagent in
the real build — see any of the dispatch prompts in the session history
for the literal template (depth-bar calibration excerpt, the
double-hyphen-not-em-dash convention, "must fully support answering the
quiz," 4-5 sections, 150-1700 characters per section body).

### 3. Dispatch content-authoring subagents

One subagent per topic, using the same prompt shape as the real build:
give it the source material's content stub, the quiz, and the depth-bar
calibration text, and ask for 4-5 headed `CourseSection` entries. Reuse the
prompt template verbatim, swapping only the subject matter.

### 4. Run the same structural checks

- 4-5 sections per topic
- Each section body 150-1700 characters
- No em-dashes (or whatever prose convention the pilot adopts)
- Every quiz question answerable from the generated sections

These are cheap, mechanical, and already proven — they should pass
trivially regardless of domain. If they don't, something is wrong with the
dispatch prompt, not the domain.

### 5. Human domain-expert review — the step that actually matters

This is the one step that was implicitly done by me (the AI/LLM domain was
something I could review myself) and can't be skipped or faked for a real
domain. Someone who actually knows the pilot topic must read every
generated section and confirm:
- Factually correct against the source material, not just plausible-sounding
- No hallucinated specifics (numbers, policy details, tool names) not
  actually present in the source docs
- Appropriately deep, not generic filler dressed up in confident prose

Track how many sections needed a correction and what kind (factual error
vs. tone vs. missing nuance). This is the single most important signal
from the whole pilot.

### 6. Diagram-worthiness pass

For each section, apply the same judgment used throughout the real
build: does this depict a **process, comparison, or quantifiable
relationship** that prose struggles to convey? If yes, sketch what the
diagram would show (don't necessarily build the SVG by hand for the
pilot — noting the concept is enough). Count how many of the pilot's
sections are genuinely diagram-worthy vs. how many were in the AI/LLM
catalog (roughly 1 diagram per course achieved there). A much lower hit
rate would suggest diagram generation matters less for this domain, or
that it needs a different visual vocabulary (e.g., decision trees and
comparison tables for policy-heavy content, rather than the graphs/flows
that suited technical material).

### 7. Track time and cost

Log wall-clock time and rough token cost for: drafting the course-shape
specs, running the subagents, and doing the human review pass. This is
the beginning of unit economics for what this would cost to run per
customer, per how-many-pages-of-source-material.

## Pilot Log

As each course moves through steps 2-5, record a row here. This is where
step 5's "single most important signal" and step 7's cost tracking
actually get captured — the Decision gate below is a rollup of this
table, not a separate judgment call made from memory. Append as you go;
don't try to reconstruct it retroactively once the whole slice is done.

**Pilot run: docs.amperity.com, 2026-08-06.** Taxonomy step (step 1) proposed
9 tracks / 27 courses for the full site — [Curriculum Proposal
artifact](https://claude.ai/code/artifact/cea04968-894c-4262-a5d7-71073db5ddc4).
A bounded slice of 4 tracks / 14 courses was chosen for content generation —
[Pilot Content Review artifact](https://claude.ai/code/artifact/f5580b7a-9d33-425a-b77e-1f19e5dc1fdf),
raw JSON persisted at `docs/pilot-amperity/amperity-pilot-catalog.json`.

Recorded per-track, not per-course — one subagent per track fetched real
source pages and wrote all of that track's courses in a single grounded
pass, so steps 2 (hand-write a spec) and 3 (dispatch from it) collapsed
into one step in practice. The subagent's own fetched source pages *were*
the ground truth, which arguably beats a hand-written stub — see the note
under Decision gate.

| Track (Course IDs) | Corrections Needed | Correction Type(s) | Notes | Time | Token Cost |
|---|---|---|---|---|---|
| 1 — Getting Started (`amp-start-first-data-source`, `amp-start-primary-keys-exclusions`, `amp-start-semantics-pii`, `amp-start-profile-generation`) | 0 logged by human review | — | Quiz guessability self-corrected 8/12 → 0/12 flagged during generation, before human review even started; position spread 3/3/3/3. Grounded specifics pulled from real docs (5-step "add courier" dialog shared by S3/Azure/SFTP, Snowflake Secure Data Sharing constraints, exact output-table column names). | ~14 min (parallel with the other 3 tracks) | not measured |
| 3 — Customer 360 Data Model (`amp-c360-databases-domain-tables-feeds`, `amp-c360-tour-standard-output-tables`, `amp-c360-semantic-tags-data-types`) | 0 logged by human review | — | Guessability self-corrected 4/9 → 0/9 during generation. Real specifics: feed→domain-table→database pipeline, PII table's actual normalization rules, array/map/struct must-pass-through-a-custom-domain-table constraint. | ~14 min (parallel) | not measured |
| 4 — Segments, Campaigns & Journeys (`amp-sc-building-segments`, `amp-sc-running-campaigns`, `amp-sc-designing-journeys`, `amp-sc-use-case-to-audience`) | 0 logged by human review | — | Notable discipline, not a defect: the agent hit `send_results.md` returning content unrelated to its filename and used what was actually there rather than inventing plausible send-metrics. AmpAI mentioned only on the 2 courses where a real product feature (Customer Data Assistant) grounds it. | ~14 min (parallel) | not measured |
| 6 — Connecting & Activating Data (`amp-connect-how-sources-work`, `amp-connect-campaigns-destinations`, `amp-connect-choosing-integration`) | 0 logged by human review | — | Tests the pilot's core curation thesis: ~250 near-duplicate per-integration pages collapsed into 3 conceptual courses. Guessability clean, 2/2/2/3 spread. Real specifics: **courier** as the pull-mechanism term (defined at first use), cross-account role vs. shared credentials, Bridge's zero-copy sharing quoted directly, Klaviyo email-as-identity-key / Braze one-identifier-per-request gotchas. | ~14 min (parallel) | not measured |
| **Merged total (all 14, 42 quiz questions)** | — | — | Zero structural problems. 7% uniquely-longest (below the 25% chance baseline, and better than this app's own catalog). Flat 10/10/10/12 position spread. | ~20 min (dispatch → merged + published) | not measured |
| Human review (all 14) | not itemized | — | Reviewer is a former Amperity employee (real domain knowledge, not a naive read). Response: "quite nice actually," with no corrections raised against 3 targeted spot-check questions (S3/Azure/Snowflake contrast realism, whether the AmpAI sections read as grounded vs. generic-AI filler, whether the Track 6 pattern-not-page-count approach actually works). Not itemized against source material per-section the way this table's columns assume — see Decision gate note. | ~4 min (read + reply) | n/a |

- **Correction Type** — `factual` (a claim not actually backed by the
  source material), `tone` (accurate but reads generic / off-voice), or
  `nuance` (accurate but missing something a domain expert would flag as
  important). Tag a row with more than one if a section needed more than
  one kind of fix. None were logged this run because the review wasn't
  itemized — see Decision gate.
- **Notes** — anything that doesn't fit a column: a failure pattern that
  recurred across courses, a dispatch-prompt tweak that fixed something,
  a taxonomy call from step 1 that turned out wrong once the real quiz
  got written.

## Decision gate

**Pass** — human review finds the generated content accurate with only
minor edits (tone, emphasis), across most topics. Green light: move on to
scoping the platform-infrastructure work (see below).

**Partial** — content is directionally right but needs substantial correction
on a meaningful fraction of sections, or the taxonomy didn't map cleanly.
Don't scrap the idea; instead, treat the specific failure as the next
thing to fix (a better dispatch prompt, a taxonomy-detection step, a
retrieval-grounded authoring pass instead of prompt-only) and re-run the
pilot on the same material once fixed.

**Fail** — human review finds systematic hallucination or the content
reads as generic regardless of prompt tuning. Worth knowing before
building anything further; the content-authoring approach itself, not
just the domain, would need rethinking.

### Verdict: Pass, with a process caveat

The mechanical bar (structure, guessability, grounded specifics over
paraphrase) held up on a domain with zero AI/technical content — real
evidence `writing-catalog-courses` generalizes rather than being overfit
to this repo's own subject matter. The human read was positive and came
from someone with genuine Amperity domain knowledge, not a cold reviewer.

The caveat: that review was a holistic "quite nice actually" plus three
targeted spot-check questions, not the itemized per-section fact-check
against source material step 5 actually calls for. Zero corrections
*logged* is not the same claim as zero corrections *needed* — the pilot
never generated the data to tell those apart. Treat "0 corrections" in
the Pilot Log as "not measured," not "measured and clean." **Before
trusting this verdict enough to greenlight the next-phase build below on
factual-accuracy grounds alone, run one real itemized human review pass**
(pick 2-3 courses, read every section against the actual cited doc pages,
log real correction counts) rather than scaling straight from a vibe
check.

Also logged as a process finding, not a defect: steps 2 and 3 collapsed
into one in practice — no one hand-wrote a course-shape spec before
dispatch; each track's subagent fetched real source pages and wrote
grounded lessons directly. That's arguably stronger (the ground truth was
the actual docs, not a human's summary of them), but it means step 2's
"taxonomy sanity check" function — catching a bad course boundary before
generation — didn't get exercised this run, since nothing forced a human
to try summarizing each course first. Worth deciding deliberately next
time, not defaulting into it again by the same shortcut.

Token cost was not captured this run (only wall-clock, reconstructed from
session timestamps after the fact) — instrument this explicitly on the
next pilot slice rather than trying to reconstruct it again.

## If it passes: the next-phase build order

Not a task-by-task implementation plan (too early for that without knowing
the pilot's specifics) — a rough sequencing of the architectural changes
already identified as necessary, roughly in the order they unblock each
other:

1. **Generalize the taxonomy** — replace the hardcoded `Track` enum
   (`models.py`) with an org-defined, admin-creatable taxonomy. Nothing
   else below is buildable without this.
2. **Multi-tenancy** — org-scoped catalog and users instead of one global
   `catalog.json` and flat `users` table. Decide early whether "org" is a
   first-class DB concept or whether a lighter scoping mechanism suffices
   for the first paying customers.
3. **Content ingestion + review UI** — turn the manual pilot procedure
   above (steps 1-6) into an actual product surface: upload source
   material, watch AI-drafted lessons come back, edit inline, approve to
   publish. This is the biggest net-new build.
4. **Diagram-spec generation** — the hardest R&D piece. Move from
   hand-authored SVGs to "LLM proposes a diagram spec (type, nodes,
   labels) → deterministic renderer builds the SVG." Can probably launch
   without this (ship text-only lessons first) and add it once ingestion
   is proven.
5. **Manager reporting** — completion rates, quiz scores, who's behind, by
   team. Table stakes for any B2B buyer.
6. **Resolve exploratory-vs-compliance mode** — decide whether this is a
   self-directed "pick your own goal" tool (today's model) or an
   assign-and-track-for-compliance tool (what a lot of corporate L&D
   budget actually goes to). These are different products with different
   UX; figure out which one the pilot's target buyer actually wants before
   building deadlines/reminders/audit trails.
7. **SSO** — SAML/Okta/Azure AD. Needed before most companies will let
   employees log in at all; can wait until there's a real customer asking
   for it.

Don't start any of this until the pilot has run and step 5 (human review)
has a real verdict. The infrastructure is the easy part; the content
pipeline generalizing is the part actually in question.
