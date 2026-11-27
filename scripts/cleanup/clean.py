#!/usr/bin/env python3
"""Remove caches and generated output. Only touches git-ignored, regenerable paths.

python scripts/cleanup/clean.py          # caches + reports/generated + .terraform
python scripts/cleanup/clean.py --all    # also .venv, .tools, node_modules
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".terraform", ".terragrunt-cache"}
TOP_LEVEL = ["reports/generated"]
HEAVY = [".venv", ".tools", "node_modules"]
SKIP = {".git", ".venv", ".tools", "node_modules"}


def main(argv: list[str]) -> int:
    targets = [ROOT / t for t in TOP_LEVEL + (HEAVY if "--all" in argv else [])]
    stack = [ROOT]
    while stack:
        current = stack.pop()
        for child in current.iterdir():
            if child.is_dir() and child.name not in SKIP:
                (targets.append(child) if child.name in CACHE_DIRS else stack.append(child))
    for t in targets:
        if t.exists():
            shutil.rmtree(t)
            print(f"removed {t.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
