#!/usr/bin/env python3
"""Apply repository formatters. Missing formatters are reported, never ignored silently.

Exit code 1 if any formatter is missing or fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pibkit.core import ToolMissing, run, select, tool

FORMATTERS = [
    ("ruff", ["format"], ["**/*.py"]),
    ("ruff", ["check", "--fix", "--select", "I"], ["**/*.py"]),
    ("shfmt", ["-w"], ["**/*.sh", "**/*.bash"]),
    ("terraform", ["fmt", "-recursive", "iac/terraform"], None),
]


def main() -> int:
    failed = 0
    for name, args, globs in FORMATTERS:
        try:
            exe = tool(name)
        except ToolMissing:
            print(f"[NOT RUN] {name}: not installed (python scripts/setup/install_tools.py {name})")
            failed = 1
            continue
        files = select(globs) if globs else []
        if globs and not files:
            continue
        code, out = run([exe, *args, *files])
        print(f"[{'OK' if code == 0 else 'FAIL'}] {name} {' '.join(args)}" + (f"\n{out}" if code else ""))
        failed |= code != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
