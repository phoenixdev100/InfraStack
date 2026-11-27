#!/usr/bin/env python3
"""Print the CHANGELOG.md section for a release tag (Keep a Changelog format).

Usage: python scripts/release/changelog_section.py v1.2.3
Exit code 1 if the section does not exist, so releases without notes fail.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def section(text: str, version: str) -> str | None:
    version = version.removeprefix("v")
    pattern = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", re.M | re.S)
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    body = section(CHANGELOG.read_text(encoding="utf-8"), argv[0])
    if body is None:
        print(f"CHANGELOG.md has no section for {argv[0]}", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
