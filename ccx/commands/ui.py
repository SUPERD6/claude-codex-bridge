"""ccx ui — the live page and manager's board on this machine (ccx/ui.py), or a static snapshot of it (--export);
ccx demo (or ccx ui --demo) — the same page on a throwaway hub of made-up data (ccx/demo.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import ui
from ..config import paths
from .common import _out


def _serve(p, project, days: float, a) -> int:
    if a.export:
        _out({"snapshot": str(ui.export(p, Path(a.export), project, days))})
        return 0
    srv = ui.UI(p, project, days, port=a.port)
    print(f"ccx ui: {srv.url}", flush=True)
    print("buttons that change something show their ccx command and run it on a second click; stops on its own "
          "about a minute after the page is closed, up to 5 minutes if it was a background tab (or Ctrl+C)", file=sys.stderr, flush=True)
    if not a.no_open:
        ui.open_browser(srv.url)
    try:
        why = srv.serve()
    except KeyboardInterrupt:
        why = "Ctrl+C"
    print(f"ccx ui: stopped ({why})", file=sys.stderr, flush=True)
    return 0


def cmd_ui(a) -> int:
    if getattr(a, "demo", False):
        return cmd_demo(a)
    p = paths()
    project = Path(a.project).resolve() if a.project else None
    return _serve(p, project, a.days, a)


def cmd_demo(a) -> int:
    """U6: build the demo (made-up data in the temporary folder), point this process at it, serve the page. The
    real hub and the tools' own folders are never read or written; nothing is started but the page's server."""
    from .. import demo
    given = getattr(a, "dir", None)
    base = Path(given).resolve() if given else demo.new_base()
    try:
        p = demo.build(base)
        os.environ.update(demo.env(base))      # this process and the commands its buttons run stay in the demo
        print(f"ccx demo: made-up data in {base} (marked as demo data on the page; your hub and tools are untouched)",
              file=sys.stderr, flush=True)
        return _serve(p, None, 7, a)
    finally:                                   # an export needs no folder afterwards; a failed build leaves none
        if not given and not getattr(a, "keep", False):
            if not demo.remove(base, owned=True):
                print(f"ccx demo: could not delete {base}: delete it by hand", file=sys.stderr, flush=True)
        elif base.exists():
            print(f"ccx demo: kept {base}", file=sys.stderr, flush=True)


def register(sub) -> None:
    u = sub.add_parser("ui", help="a live page on this machine: who works on what across projects, what waits "
                       "for you, quota, this month's saving; buttons run ccx commands after a second click")
    u.add_argument("--project", help="only this project folder (default: every project with recent runs)")
    u.add_argument("--no-open", action="store_true", help="print the address, don't open a browser")
    u.add_argument("--port", type=int, default=0, help="default: a random free port")
    u.add_argument("--days", type=float, default=7, help="runs from the last N days")
    u.add_argument("--export", metavar="FILE", help="write a static snapshot page instead of serving")
    u.add_argument("--demo", action="store_true", help="the page on made-up data (same as `ccx demo`)")
    u.add_argument("--keep", action="store_true", help="with --demo: keep the demo folder after the page closes")
    u.set_defaults(fn=cmd_ui)
    d = sub.add_parser("demo", help="see ccx ui in 30 seconds, no account needed: made-up projects, runs, costs "
                       "and conversations in a temporary folder, shown on the same page; works offline")
    d.add_argument("--no-open", action="store_true", help="print the address, don't open a browser")
    d.add_argument("--port", type=int, default=0, help="default: a random free port")
    d.add_argument("--export", metavar="FILE", help="write a static snapshot of the demo page instead of serving")
    d.add_argument("--dir", help="build the demo in this folder and keep it: a new or empty folder, or an earlier demo folder")
    d.add_argument("--keep", action="store_true", help="keep the temporary demo folder after the page closes")
    d.set_defaults(fn=cmd_demo)
