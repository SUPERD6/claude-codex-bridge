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
        out = {"ok": False, "error": str(e)}
        if isinstance(e, PermissionError):
            # seen on a real headless Codex lead: its workspace-write sandbox may not write outside the project
            out["hint"] = ("ccx could not write there. If a sandboxed agent (e.g. Codex in workspace-write) ran this, "
                           "let it write to the ccx hub and use the network: see `ccx doctor`, row "
                           "'Codex as lead (sandbox)'.")
        _out(out)
        return 3
