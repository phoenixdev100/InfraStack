#!/usr/bin/env python3
"""Regenerate tools.lock.json from tools.yaml using vendor checksum files.

Run after bumping any version in tools.yaml, review the diff, commit both.
"""

import sys

from toolchain import main_update

if __name__ == "__main__":
    sys.exit(main_update(sys.argv[1:]))
