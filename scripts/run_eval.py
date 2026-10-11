"""Run the reliability batch (docs/PLAN.md §9b) and write a report.

Each variant gets a fresh copy of the seed, the agents work its event, and
the plan is scored against the oracle. Predictions use the baseline, so the
ground truth is stable. Reports go to data/eval/ (git-ignored).

Usage:
    python scripts/run_eval.py                    # all 20 variants, agents on the live model
    python scripts/run_eval.py --variants A1,F2   # a subset
    python scripts/run_eval.py --scripted         # plumbing check without AWS (variants A1 and E1)
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from clear_agents import runner
from clear_agents.testing import ScriptedDirector
from clear_app import settings
from clear_eval import harness, variants

OUT_DIR = settings.REPO_ROOT / "data" / "eval"
SCRIPTED_VARIANTS = ("A1", "E1")  # The scripted model only knows the base S1 and S2 numbers.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variants", help="comma-separated variant IDs, default all")
    parser.add_argument("--scripted", action="store_true", help="scripted model instead of the live model")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252.

    settings.load_env()
    os.environ["CLEAR_PREDICTION_BACKEND"] = "baseline"
    specs = [variants.variant(v) for v in args.variants.split(",")] if args.variants else variants.VARIANTS
    if args.scripted:
        specs = [s for s in specs if s["id"] in SCRIPTED_VARIANTS]
        model_for = ScriptedDirector
    else:
        model_for = lambda store: runner.live_model  # noqa: E731
    with tempfile.TemporaryDirectory() as tmp:
        report = harness.run_batch(specs, model_for, Path(tmp))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-scripted" if args.scripted else "")
    (OUT_DIR / f"eval-{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = markdown(report)
    (OUT_DIR / f"eval-{stamp}.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"Wrote data/eval/eval-{stamp}.json and .md")


def markdown(report: dict) -> str:
    checks = list(report["results"][0]["scores"]) if report["results"] else []
    lines = ["| Variant | Family | Expected | Agents | " + " | ".join(checks) + " | Latency (s) |",
             "|---" * (5 + len(checks)) + "|"]
    for r in report["results"]:
        expected = f"{r['expected']['decision']} ({r['expected']['priority_level']})"
        got = f"{r['outcome']['decision']} ({r['outcome']['priority_level']})"
        marks = " | ".join("✓" if r["scores"][c] else "✗" for c in checks)
        lines.append(f"| {r['variant']} | {r['family']} | {expected} | {got} | {marks} | {r['latency_s']} |")
    summary = report["summary"]
    lines += ["", f"Variants: {summary['variants']}"]
    lines += [f"- {check}: {rate:.0%}" for check, rate in summary["pass_rate"].items()]
    gap = summary["uncovered_gap_t"]
    lines += [
        f"- Uncovered supply gap: {gap['before']:g} t before, {gap['after']:g} t after the recommended plans",
        f"- Human interventions: {summary['human_interventions']['approvals']} approvals, "
        f"{summary['human_interventions']['escalations']} escalations",
        f"- Infeasible transfers proposed and blocked by the validator: "
        f"{summary['infeasible_transfers_proposed_and_blocked']}",
        f"- Median plan latency: {summary['median_latency_s']} s",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
