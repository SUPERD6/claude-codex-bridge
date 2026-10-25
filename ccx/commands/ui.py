"""ccx ui — the read-only live page on this machine (ccx/ui.py), or a static snapshot of it (--export)."""
from __future__ import annotations

import sys
from pathlib import Path

from .. import ui
from ..config import paths
from .common import _out


def cmd_ui(a) -> int:
    p = paths()
    project = Path(a.project).resolve() if a.project else None
    if a.export:
        _out({"snapshot": str(ui.export(p, Path(a.export), project, a.days))})
        return 0
    srv = ui.UI(p, project, a.days, port=a.port)
    print(f"ccx ui: {srv.url}", flush=True)
    print("read-only except yes/no on suggested notes; stops on its own about a minute after the page is closed "
          "(or Ctrl+C)", file=sys.stderr, flush=True)
    if not a.no_open:
        ui.open_browser(srv.url)
    try:
        why = srv.serve()
    except KeyboardInterrupt:
        why = "Ctrl+C"
    print(f"ccx ui: stopped ({why})", file=sys.stderr, flush=True)
    return 0


def register(sub) -> None:
    u = sub.add_parser("ui", help="a read-only live page on this machine: who works on what, what waits for you, "
                       "quota (never calls a model)")
    u.add_argument("--project", help="only this project folder (default: every project with recent runs)")
    u.add_argument("--no-open", action="store_true", help="print the address, don't open a browser")
    u.add_argument("--port", type=int, default=0, help="default: a random free port")
    u.add_argument("--days", type=float, default=7, help="runs from the last N days")
    u.add_argument("--export", metavar="FILE", help="write a static snapshot page instead of serving")
    u.set_defaults(fn=cmd_ui)
