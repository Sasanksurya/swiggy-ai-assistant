"""Run Sarah's evaluation suite and print a scoreboard.

    python -m evals.run                    # scoreboard + failures
    python -m evals.run --out report.md    # also write a Markdown report (CI shows it in the run summary)

Exit code 1 if a release gate in runner.THRESHOLDS is not met.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

from .runner import THRESHOLDS, CaseResult, gate, run_all, scores

LABELS = {"intent": "Intent accuracy", "tools": "Tool-use accuracy", "reply": "Reply checks",
          "grounding": "Grounded replies (no hallucination)", "safety": "Order safety", "cases": "Cases fully passing"}


def report(results: list[CaseResult]) -> str:
    s = scores(results)
    lines = ["# Sarah evaluation report", "",
             f"{len(results)} conversations, {sum(len(c.turns) for c in results)} turns, mock platform.", "",
             "| Metric | Score | Gate |", "|---|---|---|"]
    for k, label in LABELS.items():
        if k in s:
            mark = "pass" if s[k] >= THRESHOLDS.get(k, 0) else "FAIL"
            lines.append(f"| {label} | {s[k]:.1%} | {mark} (>= {THRESHOLDS.get(k, 0):.0%}) |")
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for c in results:
        by_cat[c.category].append(c)
    lines += ["", "| Category | Passing |", "|---|---|"]
    lines += [f"| {cat} | {sum(c.passed for c in cs)}/{len(cs)} |" for cat, cs in sorted(by_cat.items())]
    failed = [c for c in results if not c.passed]
    lines += ["", "## Failures" if failed else "## Failures: none"]
    for c in failed:
        lines.append(f"\n**{c.id}** ({c.category})")
        for t in c.turns:
            for kind, msg in t.failures:
                lines.append(f"- `{t.say}` -> [{kind}] {msg}  \n  reply: {t.reply[:160]!r}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write the Markdown report here")
    args = ap.parse_args(argv)
    results = asyncio.run(run_all())
    text = report(results)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    problems = gate(scores(results))
    if problems:
        print("Release gate failed: " + ", ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
