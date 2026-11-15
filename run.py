"""Run all scenarios and write outputs.

Usage:
    python run.py                       # uses assumptions.yaml, writes to output/
    python run.py --assumptions my.yaml --out results
"""
from __future__ import annotations

import argparse
from pathlib import Path

from bankmodel.model import run_all
from bankmodel.report import write_charts, write_excel, write_markdown
from bankmodel.sensitivity import sensitivity


def main() -> None:
    parser = argparse.ArgumentParser(description="Five-year model for a new digital consumer lender")
    parser.add_argument("--assumptions", default="assumptions.yaml", help="Path to assumptions YAML")
    parser.add_argument("--out", default="output", help="Output folder")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    results = run_all(args.assumptions)
    base = next(r for r in results if r.name == "base")
    sens = sensitivity(base.assumptions, len(base.years))

    write_excel(results, sens, out / "results.xlsx")
    write_charts(results, sens, out)
    write_markdown(results, sens, out / "summary.md")

    print(f"{'Scenario':<12}{'Loans Y5':>10}{'Cum. profit':>13}{'First profit':>14}{'Min cap.':>10}{'Shortfall':>11}")
    for r in results:
        s = r.summary()
        fp = s["first_profitable_year"] or "none"
        print(f"{r.label:<12}{s['loans_end']:>10.1f}{s['cumulative_net_profit']:>13.1f}{fp!s:>14}"
              f"{s['min_capital_ratio']:>10.1%}{s['max_capital_shortfall']:>11.1f}")
    print(f"\nOutputs written to {out.resolve()}")


if __name__ == "__main__":
    main()
