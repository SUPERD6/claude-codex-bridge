"""ccx command line: the parser is put together from ccx/commands/*; main() runs one command."""
from __future__ import annotations

import argparse
import shutil
import sys
import textwrap

from . import __version__, commands, hooktimeout
from .commands.common import _out

DESCRIPTION = ("A team of AI coding agents: Claude Code, Codex and DeepSeek hand work to each other as lead or "
               "sub-agent (Gemini CLI: sub-agent adapter, not run for real), sharing memory and working "
               "context, and route each piece to the cheapest agent likely to finish it.")

# `ccx -h` lists the person's commands by what they are for; `ccx -h --all` lists every group. Every command stays
# callable either way. Groups in NAMES_ONLY list names only; Developer (measuring ccx itself) comes last. A name not
# registered (e.g. `demo` before it lands) is skipped. "Between agents" are the commands open sessions call to
# talk to each other (the person reads and answers the board in `ccx ui`).
GROUPS = (
    ("Everyday", ("setup", "doctor", "run", "ask", "resume", "stop", "undo", "verify", "show", "q", "ui", "demo")),
    ("Memory and context", ("mem", "ctx", "project", "handoff", "fresh", "inbox", "skills")),
    ("Accounting and reports", ("stats", "report", "quota", "lead")),
    ("Between agents", ("peek", "board", "say", "reply")),
    ("Advanced", ("where", "projects", "intake", "init", "uninstall", "repair", "agents")),
    ("Maintenance", ("task", "send", "plan", "batch", "route", "propose", "way", "discuss", "turn", "sum", "archive",
                     "config", "autonomy", "selftest", "sync")),
    ("Developer", ("trial", "ab", "bench", "improve", "namecheck")),
)
NAMES_ONLY = ("Maintenance", "Developer")
SHORT = ("Everyday", "Memory and context", "Accounting and reports")     # what `ccx -h` shows; --all: every group
UNGROUPED_TO = "Maintenance"        # a new command nobody grouped yet still shows up, here


def _width() -> int:
    return max(60, min(shutil.get_terminal_size((100, 24)).columns, 120)) - 2


def _grouped_help(sub: argparse._SubParsersAction, full: bool = True) -> str:
    helps = {a.dest: a.help or "" for a in sub._choices_actions}
    width = _width()
    placed = {n for _, names in GROUPS for n in names}
    rest = tuple(n for n in sub.choices if n not in placed)
    groups = [(title, tuple(n for n in names if n in sub.choices) + (rest if title == UNGROUPED_TO else ()))
              for title, names in GROUPS]
    lines = []
    hidden = [(title, names) for title, names in groups if not full and title not in SHORT]
    for title, names in groups:
        if not full and title not in SHORT:
            continue
        lines.append(f"{title}:")
        if title in NAMES_ONLY:
            lines += textwrap.wrap(", ".join(names), width, initial_indent="  ", subsequent_indent="  ")
        else:
            for n in names:
                lines += textwrap.wrap(helps.get(n, ""), width, initial_indent=f"  {n:<10} ",
                                       subsequent_indent=" " * 13) or [f"  {n}"]
        lines.append("")
    if hidden:
        n = sum(len(names) for _, names in hidden)
        lines += textwrap.wrap(f"`ccx -h --all` lists {n} more commands: " + "; ".join(
            f"{title.lower()} ({', '.join(names[:4])}{', ...' if len(names) > 4 else ''})" for title, names in hidden)
            + ".", width)
    lines.append("`ccx <command> -h` shows one command in full.")
    return "\n".join(lines)


def build_parser(full: bool = False) -> argparse.ArgumentParser:
    """The parser; its help lists the person's commands, or every group with full (`ccx -h --all`)."""
    ap = argparse.ArgumentParser(prog="ccx", usage="ccx [-h] [--version] <command> ...",
                                 description=textwrap.fill(DESCRIPTION, _width()),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"ccx {__version__}")
    ap.add_argument("--all", action="store_true", dest="help_all", help="with -h: list every command, also the "
                    "ones agents call and the advanced and maintenance ones")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<command>", help=argparse.SUPPRESS, prog="ccx")
    for m in commands.MODULES:
        m.register(sub)
    ap.epilog = _grouped_help(sub, full)
    return ap


def parse(argv: list[str]) -> argparse.Namespace:
    """parse_args, except that words left over after an option join the brief. `ccx resume R --check X "fix"` and
    `ccx run --check pytest --to codex do it` stopped with "unrecognized arguments": argparse fills a `nargs="*"`
    brief only once. A leftover that starts with '-' is still a mistyped option and exits 2, as does any leftover for
    a command without a brief. A bare brief word right after a free-text option's value exits 2 too: in
    `--check make test` or `--label a b` it is the value's second word, and taking it as brief would quietly shorten
    the check."""
    if argv and "--all" in argv and set(argv) <= {"-h", "--help", "--all"} and len(set(argv)) > 1:
        build_parser(full=True).print_help()          # `ccx -h --all` (either order): every group
        raise SystemExit(0)
    ap = build_parser()
    a, rest = ap.parse_known_args(argv)
    if rest and not (isinstance(getattr(a, "brief", None), list) and not any(r.startswith("-") for r in rest)):
        ap.error(f"unrecognized arguments: {' '.join(rest)}")
    if isinstance(getattr(a, "brief", None), list):
        # leftovers: after any free-text option; words argparse itself put in the brief: after --check only (the
        # acceptance gate), so that a one-word brief such as `--provider deepseek x` keeps working
        hit = _split_value(ap, a.cmd, argv, rest) or _split_value(ap, a.cmd, argv, a.brief, only={"--check"})
        a.brief += rest
        if hit:
            opt, word = hit
            ap.error(f"{word!r} right after {opt}'s value: {opt} takes one value. Quote a value of several words "
                     f"({opt} \"make test\"), or put the brief before the options")
    return a


def _split_value(ap: argparse.ArgumentParser, cmd: str, argv: list[str], brief: list[str],
                 only: set[str] | None = None) -> tuple[str, str] | None:
    """(option, word) when a bare brief word comes right after the value of a free-text option (one value, no
    choices, not a number), else None. A brief word or a value with a space was quoted, so neither runs on."""
    sub = next(x for x in ap._actions if isinstance(x, argparse._SubParsersAction)).choices[cmd]
    free = {o for act in sub._actions for o in act.option_strings
            if act.nargs is None and act.choices is None and act.type not in (int, float) and (not only or o in only)}
    words = {w for w in brief if " " not in w.strip()}
    for i, tok in enumerate(argv):
        if tok == "--":
            break
        if tok not in words or tok.startswith("-") or i < 1:
            continue
        prev = argv[i - 1]
        if "=" in prev and prev.split("=", 1)[0] in free and " " not in prev:
            return prev.split("=", 1)[0], tok
        if i >= 2 and argv[i - 2] in free and not prev.startswith("-") and " " not in prev:
            return argv[i - 2], tok
    return None


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv
    a = parse(argv)
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
                           "let it write to the ccx hub and use the network: see `ccx doctor --codex-lead`, row "
                           "'Codex as lead (sandbox)'.")
        _out(out)
        return 3
