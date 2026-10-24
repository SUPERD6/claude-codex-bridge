"""`python -m ccx <command>` (used by hooks and background runs when ccx is installed as a package)."""
import sys

from ccx.cli import main

sys.exit(main())
