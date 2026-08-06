---
name: curriculum-taxonomy-from-docs
description: Use when turning a large external documentation site into a proposed course/track structure, before any lesson content gets written -- especially when the doc site has hundreds or thousands of pages.
---

# Curriculum Taxonomy from Docs

## Overview

Raw documentation is not a curriculum. A doc site with 1,000+ pages might contain 25 genuinely course-worthy topics and 900+ pages of reference material (one page per API endpoint, per third-party integration, per file format) that belong as *citations inside* a handful of lessons, not as lessons of their own. The actual hard problem in "turn these docs into courses" is this curation decision, made once, up front, and reviewed by a human before any content gets written. Get the taxonomy wrong and no amount of good lesson-writing fixes it — you either ship a curriculum that mirrors a sitemap (hundreds of thin, forgettable lessons) or you ship 5 lessons for a product with genuine breadth.

**REQUIRED SUB-SKILL:** once a taxonomy exists and is approved, use `writing-catalog-courses` for the actual lesson authoring. This skill stops at the proposal.

## When to Use

- A company hands you a docs site (or a URL) and asks for a course catalog built from it
- The doc site has enough pages that "one lesson per page" is obviously wrong on its face
- You're evaluating whether a docs-to-course pipeline is even worth building for a given source

Don't use this for a small, curated set of sources someone already picked for you (a handful of RFCs, a couple of PDFs) — go straight to research + `writing-catalog-courses`. This skill earns its keep specifically at scale, where curation is the bottleneck.

## The Process

1. **Find the site's own machine-readable index first.** Check for `llms.txt` / `llms-full.txt` at the site root (an increasingly common convention — a curated, often per-section index a doc site publishes specifically for LLM consumption) before falling back to `sitemap.xml`, and before falling back to crawling the nav yourself. A site's own curated index is higher-signal than raw URL enumeration — it's already grouped by section and usually annotated with a one-line description per page.

2. **Build an index-level inventory across the *whole* site before fetching full page content anywhere.** You need title + one-line description for every page to see the real shape of the site. Fetching full content is expensive and premature before you know which ~10% of pages will actually become lessons — do it later, per-course, once the taxonomy is approved.

3. **Look for structural repetition.** Dozens or hundreds of pages sharing a naming or content template are the single strongest signal of reference-tier material, not lesson material. See the Red Flags table below. Name the cluster and its approximate size explicitly when you find one — don't silently fold it in.

4. **Propose a track/course taxonomy, not a page-by-page plan.** Group by natural workflow or persona — a doc site's own top-level nav sections are often a reasonable starting skeleton. For each proposed course, name the *specific* source pages that ground it. For each repetition cluster from step 3, turn it into a small number of conceptual courses (teach the pattern, cite 2-4 representative pages) rather than one course per page — and say so explicitly in the proposal, so the reviewer sees exactly where you collapsed material and can push back.

5. **Stop and get human review before writing any lesson content.** This is a hard checkpoint, not a suggestion. Present the proposed tracks, courses, source-page counts per course, and the specific curation calls (which clusters got collapsed, into what) as a reviewable artifact. Flag open judgment calls explicitly rather than silently picking one.

6. **Recommend a bounded pilot scope**, not the full map, as the first thing to actually generate. A subset of 2-4 tracks proves whether the content quality holds before committing to the whole site.

## Red Flags: This Is Reference Material, Not a Lesson

| Signal | Example |
|---|---|
| Dozens/hundreds of pages sharing a naming template | `source_*.md`, `destination_*.md`, one page per third-party integration |
| Page is almost entirely a table or parameter list | field dictionaries, syntax references, changelogs |
| Sentence structure repeats near-verbatim across many pages | "Configure X to pull data from Y," swapping only Y |
| The page teaches nothing beyond "how to configure this one specific thing" | most individual connector/endpoint pages |

None of this material disappears — it becomes the specific pages a course's `content`/source list cites, or what a learner is pointed to for hands-on reference after the concept is taught.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Treating every doc page as a lesson candidate | A 1,100-page site does not need 1,100 lessons — most of it is reference material for a much smaller number of concepts |
| Fetching full content for the whole site before doing any curation | Get the index-level inventory first; fetch full page content only for the pages a proposed course actually cites |
| Skipping the human-review checkpoint and generating lesson content straight from the raw inventory | The taxonomy step doesn't parallelize the way lesson-writing does — it needs one pass that sees the whole site, then a review, before any content generation starts |
| Silently collapsing a 200-page cluster into 3 courses with no note | Name the cluster, its size, and the collapse explicitly in the proposal so a reviewer can evaluate the judgment call, not just the output |
| Proposing (or building) the entire taxonomy's content at once | Recommend a bounded pilot slice first, matching how much you can actually get reviewed and validated before scaling |

## Real-World Evidence

Applied to docs.amperity.com: a sitemap of 1,100+ URLs, reduced via its own `llms.txt` index to ~340 curriculum-relevant pages, proposed as 9 tracks / 27 courses. The single largest cluster — roughly 250 near-identical per-integration pages (one per third-party marketing/data tool, across sources/campaigns/destinations) — became 3 conceptual courses in one track, each citing 3-5 representative pages, with the collapse called out explicitly for review rather than silently applied. The reviewer confirmed that specific call before any lesson content was written.
