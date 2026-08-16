#!/usr/bin/env python3
"""Validation checks for course-catalog JSON files.

Run from the repo root (with venv activated):
    python .claude/skills/writing-catalog-courses/validate_catalog.py [item_id ...]
    python .claude/skills/writing-catalog-courses/validate_catalog.py --file path/to/other-catalog.json
    python .claude/skills/writing-catalog-courses/validate_catalog.py --file other.json --diagrams-dir some/svgs/

With no --file, checks this repo's own data/catalog.json and runs the FULL suite,
including this app's pydantic schema and a real render through its Jinja templates
-- that mode is specific to this app's Category/Level model and template conventions.
This repo's own catalog.json is an object shaped {"categories": [...], "items": [...]};
every item's "category" must reference a "categories" entry's "id".

With --file pointing anywhere else (a different tenant's course content, a pilot
file that was never merged into this repo), the schema/render checks that depend
on this app's own code are skipped automatically -- there's no Category model or
CatalogItem model to import for content that was never written against them.
External files may be EITHER shape: a bare list of items (no categories, "category"
treated as an unconstrained free-text label), or the {"categories": [...], "items": [...]}
object (in which case referential integrity -- every item's category exists in
categories -- is checked, the same way it is for this repo's own catalog).
What still runs, on ANY catalog-shaped JSON, is everything that doesn't require
this app's code: duplicate ids/headings, dangling related_item_ids, quiz option
count/bounds/duplicates, and the quiz guessability audit. Pass --diagrams-dir to
also check referenced diagram files exist for external content with its own
diagram set.

With no arguments (default mode only), trailing positional args narrow the
quiz-guessability report to just those item ids; structural checks still run
against the whole file, since a bad id elsewhere breaks everyone.
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG = REPO_ROOT / "data" / "catalog.json"
sys.path.insert(0, str(REPO_ROOT))

import json  # noqa: E402


def portable_structural_checks(data: list[dict]) -> list[str]:
    """Checks that need nothing beyond the JSON itself -- works for any tenant's content."""
    problems = []
    ids = [item.get("id") for item in data]
    if len(ids) != len(set(ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        problems.append(f"Duplicate item ids: {dupes}")

    id_set = set(ids)
    for item in data:
        label = item.get("id", "<no id>")
        for field in ("id", "title", "level", "content"):
            if field not in item:
                problems.append(f"{label}: missing required field {field!r}")
        # sections/quiz are optional and default to [] -- e.g. learning_path items
        # bundle other items and legitimately have neither of their own.

        for rid in item.get("related_item_ids", []):
            if rid not in id_set:
                problems.append(f"{label}: related_item_id {rid!r} does not exist")

        headings = [s.get("heading") for s in item.get("sections", [])]
        if len(headings) != len(set(headings)):
            problems.append(f"{label}: duplicate section headings")

        for q in item.get("quiz", []):
            opts = q.get("options", [])
            if len(opts) != 4:
                problems.append(f"{label}: quiz question has {len(opts)} options, expected 4")
            ci = q.get("correct_index")
            if not (isinstance(ci, int) and 0 <= ci < len(opts)):
                problems.append(f"{label}: quiz correct_index {ci!r} out of range")
            if len(set(o.strip().lower() for o in opts)) != len(opts):
                problems.append(f"{label}: quiz has duplicate option text")
    return problems


def extract_items_and_categories(raw: dict | list) -> tuple[list[dict], list[dict] | None]:
    """Normalize either catalog shape to (items, categories).

    A bare list (legacy / category-less external content) has no
    categories -- returns None for that slot, meaning "don't check
    referential integrity." The {"categories": [...], "items": [...]}
    object shape always has a categories list, even if it's empty.
    """
    if isinstance(raw, list):
        return raw, None
    return raw["items"], raw["categories"]


def category_reference_checks(items: list[dict], categories: list[dict]) -> list[str]:
    problems = []
    known_ids = {c.get("id") for c in categories}
    for item in items:
        label = item.get("id", "<no id>")
        category = item.get("category")
        if category not in known_ids:
            problems.append(f"{label}: category {category!r} not in declared categories")
    return problems


def quiz_guessability_report(data: list[dict], target_ids: set[str]) -> None:
    print("Quiz guessability (target: correct answer not the longest option, "
          "positions spread across 0-3, not clustered):")
    scope = [item for item in data if not target_ids or item["id"] in target_ids]
    total_q = 0
    longest_hits = 0
    positions = {0: 0, 1: 0, 2: 0, 3: 0}
    for item in scope:
        for q in item.get("quiz", []):
            opts = q.get("options", [])
            ci = q.get("correct_index")
            if len(opts) != 4 or not (isinstance(ci, int) and 0 <= ci < len(opts)):
                continue  # already flagged as a structural problem
            total_q += 1
            lens = [len(o) for o in opts]
            correct_len = lens[ci]
            if correct_len == max(lens) and lens.count(max(lens)) == 1:
                longest_hits += 1
                print(f"  FLAG: {item['id']!r} q={q['question'][:50]!r} "
                      f"correct answer is uniquely longest ({correct_len} vs {sorted(lens)[-2]})")
            positions[ci] += 1
    if total_q:
        print(f"  {longest_hits}/{total_q} ({100*longest_hits/total_q:.0f}%) uniquely-longest "
              f"(baseline chance is 25%)")
        print(f"  position distribution: {positions}")
    else:
        print("  (no quiz questions in scope)")


def diagram_check(data: list[dict], diagrams_dir: Path) -> list[str]:
    referenced = {s.get("diagram") for item in data for s in item.get("sections", []) if s.get("diagram")}
    existing = {p.stem for p in diagrams_dir.glob("*.svg")}
    missing = referenced - existing
    print(f"Diagram files ({diagrams_dir}): {'OK' if not missing else 'MISSING: ' + str(missing)}")
    return [f"Missing diagram files: {missing}"] if missing else []


def full_app_checks(target_ids: set[str]) -> list[str]:
    """Only valid against this repo's own data/catalog.json -- needs its pydantic
    models (Category/Level) and its Jinja templates to mean anything."""
    problems = []
    from catalog import load_catalog

    catalog = load_catalog()
    print(f"[1/4] Pydantic load: OK ({len(catalog.items)} items)")

    from app import templates, BASE_DIR

    sec_tmpl = templates.env.get_template("item_section.html")
    quiz_tmpl = templates.env.get_template("item_quiz.html")
    render_errors = []
    rendered = 0
    for item in catalog.items:
        if target_ids and item.id not in target_ids:
            continue
        for idx, section in enumerate(item.sections, start=1):
            rendered += 1
            diagram_svg = None
            if section.diagram:
                svg_path = BASE_DIR / "static" / "diagrams" / f"{section.diagram}.svg"
                diagram_svg = svg_path.read_text() if svg_path.exists() else None
            try:
                sec_tmpl.render(
                    request=None, current_user={"id": 1, "email": "t@example.com"},
                    track_id=1, item=item, section=section, diagram_svg=diagram_svg,
                    section_number=idx, total_sections=len(item.sections),
                    prev_number=idx - 1 if idx > 1 else None,
                    next_number=idx + 1 if idx < len(item.sections) else None,
                )
            except Exception as e:
                render_errors.append((item.id, idx, str(e)))
        if item.quiz:
            try:
                quiz_tmpl.render(request=None, current_user={"id": 1, "email": "t@example.com"},
                                  track_id=1, item=item)
            except Exception as e:
                render_errors.append((item.id, "quiz", str(e)))
    print(f"[4/4] Template render: {rendered} sections, {len(render_errors)} errors")
    for e in render_errors:
        print("  ERROR:", e)
    problems.extend(f"render error: {e}" for e in render_errors)
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=None,
                         help="Catalog-shaped JSON file to validate. Defaults to this repo's own data/catalog.json.")
    parser.add_argument("--diagrams-dir", type=Path, default=None,
                         help="Directory of .svg files to check diagram references against (external content only).")
    parser.add_argument("item_ids", nargs="*", help="Narrow the quiz-guessability report to these item ids.")
    args = parser.parse_args()

    target_file = args.file.resolve() if args.file else DEFAULT_CATALOG
    is_own_catalog = (args.file is None) or (target_file == DEFAULT_CATALOG.resolve())
    target_ids = set(args.item_ids)

    problems = []
    raw = json.loads(target_file.read_text())
    items, categories = extract_items_and_categories(raw)

    if is_own_catalog:
        problems.extend(full_app_checks(target_ids))
        diagrams_dir = args.diagrams_dir or (REPO_ROOT / "static" / "diagrams")
    else:
        print(f"[external file: {target_file}] skipping this app's pydantic schema and template "
              f"render -- running portable checks only.")
        diagrams_dir = args.diagrams_dir

    problems.extend(portable_structural_checks(items))

    if categories is not None:
        problems.extend(category_reference_checks(items, categories))
        print(f"Categories: {len(categories)} declared, referential integrity checked.")
    else:
        print("Categories: none declared in this file, skipping referential-integrity check.")

    if diagrams_dir:
        problems.extend(diagram_check(items, diagrams_dir))
    else:
        print("Diagram files: skipped (no --diagrams-dir given)")

    quiz_guessability_report(items, target_ids)

    print()
    if problems:
        print(f"{len(problems)} structural problem(s):")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("No structural problems found.")


if __name__ == "__main__":
    main()
