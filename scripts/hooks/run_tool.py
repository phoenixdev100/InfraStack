#!/usr/bin/env python3
"""Run a repository-pinned tool (from .tools/bin, .venv or PATH) for git hooks.

Fails loudly when the tool is missing instead of silently passing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pibkit.core import ToolMissing, install_hint, tool, tool_env


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: run_tool.py <tool> [args...]", file=sys.stderr)
        return 2
    try:
        exe = tool(argv[0])
    except ToolMissing:
        print(f"{argv[0]} not installed. Install: {install_hint(argv[0])}", file=sys.stderr)
        return 1
    return subprocess.call([exe, *argv[1:]], env=tool_env())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
