"""ccx command line: the parser is put together from ccx/commands/*; main() runs one command."""
from __future__ import annotations

import argparse
import shutil
import sys
import textwrap

from . import __version__, commands, hooktimeout
from .commands.common import _out

DESCRIPTION = ("A cost-saving team of AI coding agents: Claude Code, Codex and DeepSeek hand work to each other, "
               "sharing memory and working context.")

# `ccx -h` lists commands by what they are for; every command stays callable, the last group is names only.
GROUPS = (
    ("Everyday", ("setup", "doctor", "run", "ask", "resume", "stop", "verify", "ui", "where", "projects",
                  "peek", "board", "say", "reply")),
    ("Memory and context", ("mem", "ctx", "project", "handoff", "fresh", "inbox", "skills")),
    ("Accounting and reports", ("stats", "report", "show", "quota", "lead", "trial", "ab", "bench")),
    ("Maintenance and advanced", ("task", "send", "plan", "batch", "route", "propose", "way", "discuss", "q",
                                  "turn", "sum", "undo", "archive", "config", "autonomy", "improve", "selftest", "sync",
                                  "init", "uninstall", "agents", "repair")),
)


def _width() -> int:
    return max(60, min(shutil.get_terminal_size((100, 24)).columns, 120)) - 2


def _grouped_help(sub: argparse._SubParsersAction) -> str:
    helps = {a.dest: a.help or "" for a in sub._choices_actions}
    width = _width()
    placed = {n for _, names in GROUPS for n in names}
    groups = list(GROUPS)
    rest = tuple(n for n in sub.choices if n not in placed)  # a new command nobody grouped yet still shows up
    if rest:
        groups[-1] = (groups[-1][0], groups[-1][1] + rest)
    lines = []
    for i, (title, names) in enumerate(groups):
        lines.append(f"{title}:")
        if i == len(groups) - 1:
            lines += textwrap.wrap(", ".join(names), width, initial_indent="  ", subsequent_indent="  ")
        else:
            for n in names:
                lines += textwrap.wrap(helps.get(n, ""), width, initial_indent=f"  {n:<10} ",
                                       subsequent_indent=" " * 13) or [f"  {n}"]
        lines.append("")
    lines.append("`ccx <command> -h` shows one command in full.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ccx", usage="ccx [-h] [--version] <command> ...",
                                 description=textwrap.fill(DESCRIPTION, _width()),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"ccx {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>", help=argparse.SUPPRESS, prog="ccx")
    for m in commands.MODULES:
        m.register(sub)
    ap.epilog = _grouped_help(sub)
    return ap


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv
    a = build_parser().parse_args(argv)
    try:
        if name := hooktimeout.hook_name(argv):          # L4: a slow hook prints nothing instead of holding the turn
            from .config import paths
            return hooktimeout.run(name, lambda: a.fn(a), paths())
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
