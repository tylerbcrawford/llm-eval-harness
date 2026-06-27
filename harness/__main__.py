"""CLI: ``python -m harness run cases/``.

Runs every case (replay by default), prints a scored table, writes results.json,
and exits non-zero if any case fails its threshold so CI can gate on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .schema import load_cases
from .score import evaluate_case, results_to_dict


def _print_table(report: dict) -> None:
    rows = report["results"]
    width = max((len(r["case_id"]) for r in rows), default=4)
    header = f"{'case'.ljust(width)}  score  thresh  result"
    print(header)
    print("-" * len(header))
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"{r['case_id'].ljust(width)}  "
            f"{r['weighted_score']:.2f}   {r['threshold']:.2f}    {mark}"
        )
    s = report["summary"]
    print("-" * len(header))
    print(f"{s['passed']}/{s['cases']} passed   mean {s['mean_score']:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run cases and score them")
    run_p.add_argument(
        "cases", nargs="?", default="cases", help="cases directory (default: cases/)"
    )
    run_p.add_argument(
        "--live",
        action="store_true",
        help="call the real Anthropic API instead of replaying fixtures (needs a key)",
    )
    run_p.add_argument(
        "--record",
        action="store_true",
        help="live-call and overwrite fixtures with the captured candidate + verdict",
    )
    run_p.add_argument(
        "--fixtures", default="fixtures", help="fixtures directory (default: fixtures/)"
    )
    run_p.add_argument(
        "--json",
        dest="json_path",
        default="results.json",
        help="where to write the JSON report (default: results.json)",
    )
    run_p.add_argument(
        "--no-gate",
        action="store_true",
        help="always exit 0, even if a case fails its threshold",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        cases = load_cases(args.cases)
        live = True if (args.live or args.record) else None
        results = [
            evaluate_case(
                c, live=live, record=args.record, fixtures_dir=args.fixtures
            )
            for c in cases
        ]
        report = results_to_dict(results)
        _print_table(report)

        Path(args.json_path).write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

        if args.no_gate:
            return 0
        return 0 if report["summary"]["failed"] == 0 else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
