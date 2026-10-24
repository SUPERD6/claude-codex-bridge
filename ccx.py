#!/usr/bin/env python3
"""Entry point: `python ccx.py <command>` (or the ccx / ccx.cmd shims in bin/)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccx.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
