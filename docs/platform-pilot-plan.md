# Platform Pivot — Pilot Validation Plan

**Status:** pilot run 2026-08-06 against docs.amperity.com, scored below,
itemized human review completed 2026-08-09 across all 14 pilot courses.
Decision gate: **Pass** (see Pilot Log / Decision gate). Read this top to
bottom before starting further pilots or scoping the next-phase build.

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
| 1 — Getting Started (`amp-start-first-data-source`, `amp-start-primary-keys-exclusions`, `amp-start-semantics-pii`, `amp-start-profile-generation`) | 0 logged | — | Quiz guessability self-corrected 8/12 → 0/12 flagged during generation, before human review even started; position spread 3/3/3/3. Grounded specifics pulled from real docs (5-step "add courier" dialog shared by S3/Azure/SFTP, Snowflake Secure Data Sharing constraints, exact output-table column names). **Itemized review, 2026-08-09** (`amp-start-first-data-source` + `amp-start-primary-keys-exclusions`; 2 of 4 courses not yet done): re-fetched the 4 actual S3/Snowflake/SFTP source pages, plus the primary-keys and exclusions guides. Zero corrections across both — several matched source near-verbatim (500MB PGP-Parquet preview limit, Snowflake field-case rule, the exact uniqueness/stability framing for primary keys, the ampersand-escaping quirk for exclusions). Every single quiz answer in `amp-start-primary-keys-exclusions` was independently confirmed. **Itemized review, 2026-08-09 continued — Track 1 now fully reviewed, 4 of 4**: re-fetched the semantics/PII-discovery guide and the profile-generation guide (workflow + merge policy + standard output tables). Zero corrections across both remaining courses — every quiz answer in both independently confirmed, several verbatim (the "patented algorithms... identity graph with accurate and actionable customer profiles" quote, the four-stage generation workflow in the same order, the exact data-quality-validation checklist, the merge-policy cascade behavior, all 3 Identity Graph columns). Track 1 finishes with 0 corrections across all 4 courses, the cleanest track in the pilot. | ~14 min (parallel with the other 3 tracks) | not measured |
| 3 — Customer 360 Data Model (`amp-c360-databases-domain-tables-feeds`, `amp-c360-tour-standard-output-tables`, `amp-c360-semantic-tags-data-types`) | **1 logged** | `factual` | Guessability self-corrected 4/9 → 0/9 during generation. Real specifics: feed→domain-table→database pipeline, PII table's actual normalization rules, array/map/struct must-pass-through-a-custom-domain-table constraint. **Itemized review, 2026-08-09** (`amp-c360-databases-domain-tables-feeds` + `amp-c360-tour-standard-output-tables`; `amp-c360-semantic-tags-data-types` not yet done): re-fetched feeds/domain_tables/databases pages plus 3 standard-table reference pages (Unified Coalesced, PII, Unified Transactions). Zero hard corrections — near-verbatim matches on several specific, easy-to-fabricate claims (`_uuid_pk`'s exact purpose, "a custom domain table should be designed to be as static as possible," the SQL-validation-alert-doesn't-block-activation behavior, the exact "identity score of 3.0 or greater" figure for Rep DS/Rep PK, the PII table's phone/state/gender standardization rules, the mandatory Itemized→Transactions→Attributes-Extended build order). One soft nuance flag: 3 identity-resolution-mechanics columns (Component ID, Is Supersized/Supersized ID, CK) get specific functional explanations in the course that the reference table's own column-list documentation, per what I fetched, doesn't actually spell out — plausible given the column names and general Stitch mechanics, but embellished beyond confirmed source; not logged as a correction, just noted. One ambiguous, unlogged item from round 1: the last-updated-file tie-break hierarchy came back 4-tiered in that fetch vs. 3-tiered in the course — not confident enough to call it a real gap vs. extraction noise. **Itemized review, 2026-08-09 continued — Track 3 now fully reviewed, 3 of 3**: re-fetched the semantic-tag-categories reference page and the data-types reference page. Found 1 real issue: the course names a system tag `update-dt`, described generically as tracking "when a record was most recently updated" — the actual reference page documents a differently-named, differently-scoped system tag instead, `system-updated`, whose real function is narrow and specific (retaining compliance-request-table records that arrive after domain transactions close, not a general last-modified timestamp). This doesn't fit the realtime-Journeys pattern from Tracks 4/6 — it looks like a distinct failure mode, a plausible-sounding but seemingly invented tag name/function rather than a stale-relative-to-a-launch fact. Flagged with a normal, not high, confidence level, since it rests on one fetch of one reference page. Everything else in this course checked out — all 7 simple data types, both composite-type rules, and the unsupported-type list (BigQuery RANGE, Snowflake FILE/VARIANT/VECTOR) all matched source closely or verbatim. | ~14 min (parallel) | not measured |
| 4 — Segments, Campaigns & Journeys (`amp-sc-building-segments`, `amp-sc-running-campaigns`, `amp-sc-designing-journeys`, `amp-sc-use-case-to-audience`) | **1 logged** | `factual` | Notable discipline, not a defect: the agent hit `send_results.md` returning content unrelated to its filename and used what was actually there rather than inventing plausible send-metrics. AmpAI mentioned only on the 2 courses where a real product feature (Customer Data Assistant) grounds it. **Itemized review, 2026-08-09** (`amp-sc-building-segments` + `amp-sc-designing-journeys`; other 2 courses not yet done): re-fetched 4 segment/AmpAI source pages plus journeys.md/journeys_reference.md. `amp-sc-building-segments` — zero contradictions; the AmpAI Customer Data Assistant quote and the Chicago/Illinois + Madison AND/OR examples matched source near word-for-word. `amp-sc-designing-journeys` — mostly clean and strongly grounded (verbatim journey-vs-campaign definition, exact 10-exit-segment limit, exact schedule-cadence list, exact 10% control-group default, exact Milestones windows), but states twice ("real-time segments aren't supported" for goal conditions and for percent-split testing) — reviewer confirmed this is wrong, the same realtime-Journeys staleness pattern as the Track 6 finding below, now confirmed in a *second, unrelated* course. **Itemized review, 2026-08-09 continued** (`amp-sc-running-campaigns` added; `amp-sc-use-case-to-audience` still not done): re-fetched campaigns.md. Zero *contradictions*, but this course has meaningfully weaker verification coverage than the other 9 reviewed so far — several specific, quiz-load-bearing claims (the <10%-control-group-risks-zero-members mechanic behind quiz Q1, the destination-timing tiers behind quiz Q3) simply weren't present in the one page fetched, so they're unconfirmed rather than clean. One claim resembles the earlier taxonomy-attribution issue: the course presents "three documented campaign shapes" (one-time, recurring, multichannel), but the fetched page only described two scheduling options (one-time, recurring) — "multichannel" may be a real Amperity concept documented elsewhere, or may be the course's own elevation of a real technique (channel-partitioned sub-audiences) into a named category the docs don't actually use that way. Not logged as a correction without more evidence, but flagged. **Itemized review, 2026-08-09 continued — Track 4 now fully reviewed, 4 of 4**: re-fetched the 4 documented worked-example use-case pages (dormant customers, top-20%-by-revenue, win-back, early repeat purchasers). Zero hard corrections — the strongest single-course grounding found yet, with the exact 730-day dormancy definition, the exact L12M-Monetary/RFM-decile 9-and-10 logic, and the exact 84-day early-repeat-purchaser window all matching source near word-for-word, and all 3 quiz answers independently confirmed. One very minor, unlogged framing nuance: the course presents the win-back segment's 3 conditions (contactable, opted-in, inactive 730+ days) as equally weighted sequential steps, where the source frames the opt-in check specifically as a "tip"/enhancement on top of a 2-condition primary method — the resulting segment logic is identical either way, so this doesn't change what a learner would actually build. | ~14 min (parallel) | not measured |
| 6 — Connecting & Activating Data (`amp-connect-how-sources-work`, `amp-connect-campaigns-destinations`, `amp-connect-choosing-integration`) | **3 logged** | `factual` ×3 | Tests the pilot's core curation thesis: ~250 near-duplicate per-integration pages collapsed into 3 conceptual courses. Guessability clean, 2/2/2/3 spread. Real specifics: **courier** as the pull-mechanism term (defined at first use), cross-account role vs. shared credentials, Bridge's zero-copy sharing quoted directly, Klaviyo email-as-identity-key / Braze one-identifier-per-request gotchas. **Itemized review, 2026-08-09** (`amp-connect-choosing-integration` only; other 2 courses not yet done) found 3 real issues, confirmed by a reviewer with actual Amperity work history: (1) the course states Klaviyo *and* Braze both auto-map incoming columns into named objects — actually Braze requires manual column-to-field-name aliasing by a documented naming convention, it doesn't auto-categorize like Klaviyo; (2) the course opens by claiming "Amperity groups its connector documentation into" 5 named categories (CRM & Marketing Automation / Email & SMS / Advertising Platforms / Data Platforms & Cloud Storage / Analytics & BI) — reviewer confirmed it's a *plausible, logical* grouping but couldn't confirm it's actually Amperity's own stated structure (not in the docs site's own top-level index either); (3) quiz Q1's answer key says a cart-abandonment triggered send maps to a **campaign** — reviewer confirmed this is now wrong: Amperity recently shipped realtime capability in **Journeys**, so a genuine triggered send belongs there. This one isn't a hallucination from nothing — it's the fetched docs (and/or the agent's synthesis of them) lagging a real, recent product change. **Itemized review, 2026-08-09** (`amp-connect-how-sources-work` added): re-fetched source_amazon_s3.md and bridge.md. Zero corrections, and it resolves last round's open item — "cross-account role assumption" for S3 auth is now confirmed verbatim ("Amperity requires using cross-account role assumption to manage access to Amazon S3..."). **Itemized review, 2026-08-09 continued** (`amp-connect-campaigns-destinations` added — Track 6 now fully reviewed, 3 of 3): re-fetched Klaviyo/Braze/Meta Ads Manager pages. Zero corrections — the strongest-grounded course reviewed yet, with all 3 of its quiz answers independently confirmed near word-for-word (Braze's exactly-one-identifier-per-request rejection behavior, Meta's small-sample-first validation step, the 24-hour availability window). See Decision gate note. | ~14 min (parallel) | not measured |
| **Merged total (all 14, 42 quiz questions)** | — | — | Zero structural problems. 7% uniquely-longest (below the 25% chance baseline, and better than this app's own catalog). Flat 10/10/10/12 position spread. | ~20 min (dispatch → merged + published) | not measured |
| Human review — holistic pass (all 14) | not itemized | — | Reviewer is a former Amperity employee (real domain knowledge, not a naive read). Response: "quite nice actually," with no corrections raised against 3 targeted spot-check questions. Fully superseded by the itemized pass below. | ~4 min (read + reply) | n/a |
| **Human review — itemized pass (14 of 14, complete)** | **5 total** (Track 1: 0, Track 3: 1, Track 4: 1, Track 6: 3) | `factual` ×5 | See per-track rows above for the full breakdown. **Final tally: 11 of 14 courses (79%) came back completely clean against re-fetched source; 3 of 14 had real, logged issues, all `factual`, none of them the "systematic hallucination" the Fail criteria describe.** The 5 issues resolve into 4 distinct root causes: (1) an overstated Klaviyo/Braze mapping-symmetry simplification, (2) an unsourced-but-plausible 5-category integration taxonomy presented as Amperity's own structure, (3) realtime-Journeys staleness — a real, recent product launch the fetched docs hadn't caught up to, found independently in **2 separate courses** (a quiz answer and a repeated body claim), (4) one plausible-sounding but apparently invented semantic-tag name/function (`update-dt` vs. the actual `system-updated`). Only (3) recurred across courses; the other 3 were each isolated to one course. Every quiz-load-bearing claim that got checked was either confirmed or (in `amp-connect-choosing-integration` and `amp-sc-designing-journeys`) is the specific thing now logged as wrong — no quiz question was found to rest on an unconfirmed, unflagged claim by the end of the full pass. | ~100 min total (re-fetch 30+ pages across 4 rounds + compare + write up) | not measured |

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

### Verdict: Pass — itemized review complete, 14 of 14 courses

The mechanical bar (structure, guessability, grounded specifics over
paraphrase) held up on a domain with zero AI/technical content — real
evidence `writing-catalog-courses` generalizes rather than being overfit
to this repo's own subject matter. The human holistic read was positive
and came from someone with genuine Amperity domain knowledge, not a cold
reviewer.

**Update, 2026-08-09 — the full itemized pass is done.** Every one of the
14 pilot courses got a real per-section review: source pages re-fetched
fresh (30+ pages across 4 rounds), every specific claim checked against
them, every ambiguous call confirmed by a reviewer with actual Amperity
work history rather than guessed at. **11 of 14 courses (79%) came back
completely clean, many with claims that matched source near word-for-word
or verbatim.** 3 of 14 had real, logged issues — full detail in the Pilot
Log's per-track rows and the "itemized pass" summary row above — and none
of them were the "systematic hallucination" the Fail criteria describe.
They resolve into 4 distinct root causes:

1. An overstated Klaviyo/Braze mapping-symmetry simplification (`amp-connect-choosing-integration`).
2. A plausible-but-unsourced 5-category integration taxonomy presented as if it were Amperity's own documented structure (`amp-connect-choosing-integration`).
3. **Realtime-Journeys staleness** — Amperity recently shipped a real product capability the fetched docs hadn't caught up to yet, found independently in **2 separate courses** written by 2 different subagents (`amp-connect-choosing-integration`, `amp-sc-designing-journeys`).
4. One plausible-sounding but apparently invented semantic-tag name/function (`update-dt`, vs. the actual documented `system-updated`) in `amp-c360-semantic-tags-data-types`.

Only #3 recurred across courses; #1, #2, and #4 were each isolated
one-offs. That recurrence is what makes #3 the sharpest finding of the
whole pilot, not just the most interesting one: **grounding generation in
fetched doc text stops the model from inventing specifics that aren't
anywhere in the source, but it does nothing about specifics that are true
of the live product yet absent or outdated in the docs it fetched — and
that failure mode isn't confined to one course, it can ride along with
whatever the docs happened to be missing at fetch time, wherever that
topic gets discussed.** No amount of retrieval-grounding closes that gap;
only a reviewer who actually uses the current product catches it. That's
a sharper, harder version of the backlog item below about storing raw
source text per course for provenance: provenance tells you which
lessons cite which pages so a *later doc edit* can flag staleness, but it
can't flag a lesson that was already stale *the moment it was fetched*
because the docs themselves hadn't caught up to the product yet. A real
product implication: an ingestion pipeline should probably ask a customer
directly about recent/upcoming feature launches not yet reflected in
their own docs, rather than trusting doc freshness implicitly.

**This verdict is now backed by a complete pass, not a sample** — 14 of
14 courses, not a suggestive subset. A 3/14 (21%) real-issue rate, with
one identifiable, explainable, non-recurring-except-once root cause per
issue and zero fabrication-from-nothing, is a genuine **Pass** by this
document's own criteria, and is now strong enough evidence to greenlight
the next-phase build order below — with the explicit understanding that
issue #3's lesson (docs can lag the live product) needs to become a real
step in whatever ingestion pipeline gets built next, not just a note in
this file.

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
