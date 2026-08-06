#!/usr/bin/env python3
"""Validation checks for data/catalog.json used by writing-catalog-courses.

Run from the repo root (with venv activated):
    python .claude/skills/writing-catalog-courses/validate_catalog.py [item_id ...]

With no arguments, checks the whole catalog. With item ids, narrows the
quiz-guessability report to just those items (structural/render checks
still run against the whole file, since a bad id elsewhere breaks everyone).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import json  # noqa: E402


def main():
    target_ids = set(sys.argv[1:])
    problems = []

    # 1. Pydantic schema validation
    from catalog import load_catalog

    catalog = load_catalog()
    print(f"[1/4] Pydantic load: OK ({len(catalog.items)} items)")

    ids = set(i.id for i in catalog.items)
    if len(ids) != len(catalog.items):
        problems.append("Duplicate item ids found in catalog.json")

    for item in catalog.items:
        for rid in item.related_item_ids:
            if rid not in ids:
                problems.append(f"{item.id}: related_item_id {rid!r} does not exist")
        headings = [s.heading for s in item.sections]
        if len(headings) != len(set(headings)):
            problems.append(f"{item.id}: duplicate section headings")
        for q in item.quiz:
            if len(q.options) != 4:
                problems.append(f"{item.id}: quiz question has {len(q.options)} options, expected 4")
            elif not (0 <= q.correct_index < 4):
                problems.append(f"{item.id}: quiz correct_index {q.correct_index} out of range")
            if len(set(o.strip().lower() for o in q.options)) != len(q.options):
                problems.append(f"{item.id}: quiz has duplicate option text")

    # 2. Diagram files exist
    data = json.loads((REPO_ROOT / "data" / "catalog.json").read_text())
    referenced = {s.get("diagram") for item in data for s in item.get("sections", []) if s.get("diagram")}
    existing = {p.stem for p in (REPO_ROOT / "static" / "diagrams").glob("*.svg")}
    missing = referenced - existing
    if missing:
        problems.append(f"Missing diagram files: {missing}")
    print(f"[2/4] Diagram files: {'OK' if not missing else 'MISSING: ' + str(missing)}")

    # 3. Quiz guessability (report only, not a hard failure -- use judgment)
    print("[3/4] Quiz guessability (target: correct answer not the longest option, "
          "positions spread across 0-3, not clustered):")
    scope = [item for item in data if not target_ids or item["id"] in target_ids]
    total_q = 0
    longest_hits = 0
    positions = {0: 0, 1: 0, 2: 0, 3: 0}
    for item in scope:
        for q in item.get("quiz", []):
            total_q += 1
            lens = [len(o) for o in q["options"]]
            correct_len = lens[q["correct_index"]]
            if correct_len == max(lens) and lens.count(max(lens)) == 1:
                longest_hits += 1
                print(f"  FLAG: {item['id']!r} q={q['question'][:50]!r} "
                      f"correct answer is uniquely longest ({correct_len} vs {sorted(lens)[-2]})")
            positions[q["correct_index"]] += 1
    if total_q:
        print(f"  {longest_hits}/{total_q} ({100*longest_hits/total_q:.0f}%) uniquely-longest "
              f"(baseline chance is 25%)")
        print(f"  position distribution: {positions}")
    else:
        print("  (no quiz questions in scope)")

    # 4. Render every section + quiz page through the real templates
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

    print()
    if problems:
        print(f"{len(problems)} structural problem(s):")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("No structural problems found.")


if __name__ == "__main__":
    main()
