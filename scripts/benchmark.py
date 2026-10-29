"""Accuracy benchmark: runs every planted-error draft through the real scan pipeline.

Usage:  python scripts/benchmark.py            (offline: exact checks + word lists)
        LLM_API_KEY=... python scripts/benchmark.py --ai   (also uses the AI layer)
Each mode rewrites only its own marked section of BENCHMARK.md, so offline and AI results
sit side by side and the hand-written notes below them are kept.
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.engine import ai  # noqa: E402
from app.engine.scan import scan_text  # noqa: E402
from app.seed import FACTS, RULES  # noqa: E402

RULESET = [{**r, "status": "approved"} for r in RULES]
CATEGORY = {r["code"]: r["category"] for r in RULES}
CATEGORY["CONF"] = "confidentiality"
TODAY = date(2026, 10, 29)


def rule_of(f):
    return "CONF" if f["category"] == "confidentiality" else f["rule_code"]


def matches(f, e):
    if rule_of(f) != e["rule"]:
        return False
    return e["quote"] == "" or e["quote"].lower() in (f.get("quote") or "").lower() or \
        (f.get("quote") or "").lower() in e["quote"].lower() and f.get("quote")


def main():
    use_ai = "--ai" in sys.argv
    data = json.load(open(os.path.join(os.path.dirname(__file__), "..", "tests", "benchmark_set.json")))
    per_cat = defaultdict(lambda: {"expected": 0, "caught": 0})
    tp = fp = fn = 0
    hard_total = hard_caught = 0
    misses, false_alarms = [], []
    ai_ran = 0
    for case in data["cases"]:
        findings, summary = scan_text(case["text"], RULESET, FACTS, case["type"], use_ai=use_ai, today=TODAY)
        ai_ran += summary["mode"] == "exact+ai"
        issues = [f for f in findings if f["severity"] != "info"]
        used = set()
        for e in case["expect"]:
            cat = CATEGORY[e["rule"]]
            hit = next((i for i, f in enumerate(issues) if i not in used and matches(f, e)), None)
            if case.get("hard"):
                hard_total += 1
                hard_caught += hit is not None
                if hit is not None:
                    used.add(hit)
                continue
            per_cat[cat]["expected"] += 1
            if hit is None:
                fn += 1
                misses.append(f'#{case["id"]} {e["rule"]} "{e["quote"]}"')
            else:
                tp += 1
                per_cat[cat]["caught"] += 1
                used.add(hit)
        for i, f in enumerate(issues):
            if i not in used and not case.get("hard"):
                fp += 1
                false_alarms.append(f'#{case["id"]} {rule_of(f)} "{f["quote"]}"')
    recall = tp / max(1, tp + fn)
    precision = tp / max(1, tp + fp)
    mode = "ai" if use_ai else "offline"
    heading = (f"## AI mode (exact checks + Gemini `{ai.config()['model']}`)" if use_ai
               else "## Offline mode (exact checks + word lists)")
    lines = [
        heading, "",
        f"{len(data['cases'])} drafts, {tp + fn} planted errors (standard), {hard_total} hard errors, "
        f"{sum(1 for c in data['cases'] if not c['expect'])} clean drafts. Run on {date.today():%d %b %Y}.",
    ]
    if use_ai:
        lines.append(f"The AI layer actually ran on {ai_ran} of {len(data['cases'])} drafts "
                     "(the rest fell back to offline checks).")
    lines += [
        "",
        "| Measure | Result |", "| --- | --- |",
        f"| Planted errors caught (recall) | {tp}/{tp + fn} = {recall:.0%} |",
        f"| Findings that were real (precision) | {tp}/{tp + fp} = {precision:.0%} |",
        f"| False alarms | {fp} |",
        f"| Hard errors caught (need judgement) | {hard_caught}/{hard_total} |",
        "", "| Category | Caught |", "| --- | --- |",
    ]
    for cat, v in sorted(per_cat.items()):
        lines.append(f"| {cat} | {v['caught']}/{v['expected']} |")
    lines += ["", "Missed: " + (", ".join(misses) or "none"), "", "False alarms: " + (", ".join(false_alarms) or "none")]
    section = f"<!-- {mode}:start -->\n" + "\n".join(lines) + f"\n<!-- {mode}:end -->"
    print(section)

    path = os.path.join(os.path.dirname(__file__), "..", "BENCHMARK.md")
    report = open(path).read() if os.path.exists(path) else ""
    marker = re.compile(rf"<!-- {mode}:start -->.*?<!-- {mode}:end -->", re.DOTALL)
    if marker.search(report):
        report = marker.sub(lambda _: section, report)
    else:  # first run: start a fresh report with both sections and the notes
        other = "ai" if mode == "offline" else "offline"
        blocks = {mode: section, other: f"<!-- {other}:start -->\n_Not run yet._\n<!-- {other}:end -->"}
        report = "# Proofmark accuracy benchmark\n\n" + blocks["offline"] + "\n\n" + blocks["ai"] + "\n\n" + LIMITS
    with open(path, "w") as fh:
        fh.write(report)


LIMITS = ("## Limits of this benchmark\n\n"
          "The planted errors were written by the team alongside the rules, so this mainly proves the checks "
          "work as designed and that clean drafts raise no false alarms. Real drafts will score lower. "
          "The hard cases (pressure without listed words, slang not on the list, numbers written as words) "
          "show what offline mode cannot catch and why the AI layer exists. Next step: test on real club and "
          "agency posts written by people outside the team.\n")


if __name__ == "__main__":
    main()
