"""ccx command line: the parser is put together from ccx/commands/*; main() runs one command."""
from __future__ import annotations

import argparse
import sys

from . import __version__, commands
from .commands.common import _out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ccx", description="Claude Code <-> Codex bridge")
    ap.add_argument("--version", action="version", version=f"ccx {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for m in commands.MODULES:
        m.register(sub)
    return ap


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except (PermissionError, FileNotFoundError, ValueError, RuntimeError) as e:
        _out({"ok": False, "error": str(e)})
        return 3
