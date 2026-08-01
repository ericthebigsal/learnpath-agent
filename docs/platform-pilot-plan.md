# Platform Pivot — Pilot Validation Plan

**Status:** waiting on a pilot topic. Read this top to bottom before starting.

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
