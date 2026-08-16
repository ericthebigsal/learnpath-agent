---
name: writing-catalog-courses
description: Use when writing or expanding course content -- sections, quizzes, or diagrams -- in data/catalog.json for the learnpath-agent LMS, or when auditing existing catalog items for quality.
---

# Writing Catalog Courses

## Overview

Course content that merely compiles isn't done. This repo's catalog has repeatedly shipped content with the same three defects: quizzes gradeable without reading the lesson, key terms used to explain something without ever being explained themselves, and diagrams that render fine in isolation but break inside the site's actual container. A fresh agent given no guidance reproduces all three on the first try (verified: baseline test scored 2/3 quiz questions with the correct answer as the uniquely-longest option, clustered 2/3 at the same position). This skill is the checklist that prevents that.

## Catalog Schema

`data/catalog.json` is an object shaped `{"categories": [...], "items": [...]}`, not a bare list. A new category needs its own entry in the top-level `categories` array (with `id`, `name`, `keywords`) before any item can reference it via that item's `category` field -- an item referencing an undeclared category id makes `load_catalog()` raise at import time, so this has to happen first, not as cleanup afterward.

## When to Use

- Adding a new course item to an existing category
- Creating a new category from scratch
- Deepening or auditing an existing item for quality
- Reviewing someone else's (or an agent's) catalog PR

## The Four Checks

### 1. Every load-bearing term gets defined where it's first used

If a sentence explains X by naming Y, and Y itself is never explained, that's a gap — even if Y "sounds" like it should be obvious. Test: could a reader at this item's stated `level` follow the argument without already knowing Y? If not, add a clause defining Y right there, or a new section if Y is substantial enough to carry its own weight (e.g. temperature, RLHF, training loss each earned a full section elsewhere in this catalog because the lesson's argument depended entirely on them).

Not every term needs this — decorative examples and terms with enough surrounding context don't count. The bar is "the argument depends on it," not "every technical word."

### 2. Quiz options: recipe, not a warning

Write all 4 options to within ~20-30% of each other in character length, and vary which index (0-3) holds the correct answer across the questions in an item — don't default to writing the correct answer as option B every time. Distractors should be plausible, specific, wrong claims about the same topic (a real misconception, an inverted relationship, a mixed-up adjacent concept) — never a generic dismissal ("None of the above," "Nothing").

Run the validator (`python .claude/skills/writing-catalog-courses/validate_catalog.py <item-id>`) before calling a quiz done. It flags every question where the correct answer is uniquely the longest option and reports the position distribution. Target: at or below the 25% chance baseline for "longest," no more than roughly a third of questions sharing one index.

### 3. Diagrams: reuse or build safely, or skip

Check `static/diagrams/` for an existing unused SVG on the same topic before building a new one (`grep` catalog.json for which diagram names are actually referenced — several good diagrams have sat unused because nobody checked). If building new:

- Never declare `:root { ... }` inside the SVG's own `<style>` — diagrams render inlined directly into the page DOM, so `:root` there means the site's real `<html>` root and silently overrides the actual theme colors for the whole page. Only reference the site's existing custom properties (`var(--ink)`, `var(--ink-muted)`, `var(--surface)`, `var(--border)`, `var(--taken)`/`-tint`/`-border`, `var(--considered)`/`-tint`/`-border`, `var(--signal)`/`-tint`, `var(--font-display)`/`-body`/`-mono`) — never invent or hardcode new ones.
- SVG `<text>` does not wrap. Any string longer than roughly 40-45 characters that has to fit inside a fixed-width box needs manual `<tspan x="..." dy="...">` line breaks, or it will overflow into whatever's rendered on top of it (which reads as "cut off," not "overflowing," because the sibling element painted later hides the rest — this is the exact bug a user caught in production). Check any text positioned near another shape for the same collision (a caption crossing an arrow, a label sharing a title's vertical position).
- The site renders every diagram inside `.lesson-diagram { max-width: 640px }` with `svg { width: 100%; height: auto }` — proportional scaling doesn't fix an overflow, it just shrinks it. Verify by actually rendering the SVG inside that container (see Verifying Diagrams below), not by estimating character widths.
- No diagram is safer than a broken one. Most sections in this catalog have an empty `diagram` field — that's the norm, not a gap.

### 4. Validate before calling it done

```bash
source venv/bin/activate
python .claude/skills/writing-catalog-courses/validate_catalog.py [item-id ...]
python -m pytest -q
```

Against this repo's own `data/catalog.json` (the default, no `--file` needed), the validator checks: pydantic schema load, duplicate ids/headings, dangling `related_item_ids`, missing diagram files, quiz guessability (see #2), and renders every section and quiz page through the actual Jinja templates used in production (`item_section.html`, `item_quiz.html`) — this is what catches the diagram overflow/collision bugs, not eyeballing the SVG source.

The validator also works against course content that was never written for this app — `--file path/to/other-catalog.json` (optionally `--diagrams-dir path/to/svgs`) runs the portable checks (duplicate ids/headings, dangling related ids, quiz option/index validity, quiz guessability, diagram existence) without importing this app's own `Category`/`Level` enums or templates, since external content was never written against them. Use this for pilot content, a different tenant's catalog, or anything not destined for this repo's `data/catalog.json`.

If you changed an existing item's quiz and its `correct_index` values shifted, grep the test suite for hardcoded answer submissions against that item's id (`grep -rn "answer_0" tests/`) — a prior pass broke 6 tests this way by rebalancing a quiz without checking who depended on the old indices.

## Verifying Diagrams Visually

Character-width math is unreliable in both directions (produces false positives and misses real collisions). To actually check, render the SVG inside the real container CSS and screenshot it:

```python
# wrap target SVG(s) in the site's actual .lesson-diagram container + CSS custom
# properties (copy the :root block from static/style.css), serve over local
# http.server (browser tools block file:// URLs), navigate with a headless
# browser, screenshot, and read the image directly.
```

Do this for any new or edited diagram before considering it done, not just the ones you suspect.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing the correct quiz answer with more detail/nuance than distractors "because it's true and true things need more explanation" | Give distractors equal specificity — a wrong claim can be just as detailed as a right one |
| Defaulting to option B for the correct answer across most questions in an item | Deliberately rotate correct_index across 0-3 |
| Naming a mechanism to explain something else, e.g. "...via gradient descent" or "...using server-sent events" without ever explaining gradient descent or SSE | Define it inline where first used, or give it its own section if it's load-bearing enough |
| Judging an SVG fixed by reading its source and estimating widths | Actually render it in the site's container and look |
| Copying a `:root {...}` block into a new diagram's `<style>` for convenience | Reference the site's existing `var(--...)` properties instead; never redeclare `:root` |
| Calling a quiz rewrite done without running the validator | Always run `validate_catalog.py` before considering quiz or diagram work finished |
