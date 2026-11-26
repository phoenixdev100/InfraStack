#!/usr/bin/env python3
"""Install pinned, checksum-verified validator binaries into .tools/bin.

Usage: python scripts/setup/install_tools.py [tool ...] [--force]
"""

import sys

from toolchain import main_install

if __name__ == "__main__":
    sys.exit(main_install(sys.argv[1:]))
