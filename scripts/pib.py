#!/usr/bin/env python3
"""production-infrastructure-blueprint repository CLI.

Examples:
  python scripts/pib.py list                        # show the test matrix
  python scripts/pib.py run lint validate           # run stages
  python scripts/pib.py run security --strict       # NOT RUN => failure
  python scripts/pib.py run validate --only k8s-policy
  python scripts/pib.py report                      # regenerate reports/*.md

Stages: lint, validate, security, unit, integration, e2e, performance, docs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from pibkit import report, runner
except ModuleNotFoundError as exc:
    # Expected on a fresh clone before `pip install -r requirements/dev.txt`.
    # Other errors (syntax, runtime) are NOT caught here and propagate normally.
    missing = exc.name or "unknown"
    print(
        f"InfraStack cannot start: missing dependency '{missing}'.\n"
        "Install dependencies using:\n"
        "  python -m venv .venv && .venv/Scripts/activate   # Windows\n"
        "  source .venv/bin/activate                        # Linux/macOS\n"
        "  python -m pip install -r requirements/dev.txt",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

STAGES = ["lint", "validate", "security", "docs", "unit", "integration", "e2e", "performance"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one or more stages")
    r.add_argument("stages", nargs="+", choices=[*STAGES, "all"])
    r.add_argument("--only", nargs="*", help="restrict to these check ids")
    r.add_argument("--strict", action="store_true", help="treat NOT RUN as failure")
    r.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("list", help="print the test matrix with target counts")
    sub.add_parser("report", help="regenerate inventory/coverage/results reports")
    args = parser.parse_args()

    if args.cmd == "list":
        return runner.list_matrix()
    if args.cmd == "report":
        return report.generate()
    stages = STAGES if "all" in args.stages else args.stages
    return runner.execute(stages, args.only, args.strict, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
