"""ccx say / reply / board — open sessions in one project write to each other (ccx/board.py, docs/board.md)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import board
from ..config import load_config, paths
from .common import _caller, _out, lead_session_id


def _root(a) -> Path:
    from .. import learn, project
    cwd = Path(a.cwd) if getattr(a, "cwd", None) else Path.cwd()
    return project.find_root(cwd) or learn.cp_root(cwd)


def _detected() -> str:
    """Who is really running this command: the agent ccx sees around it (+ its session), else a person at a
    terminal, else nobody we know."""
    who = _caller(None)
    if who != "user":
        sid = lead_session_id(who)
        return f"{who}:{sid}" if sid else who
    if os.environ.get("CCX_BOARD_AS"):
        return board.norm(os.environ["CCX_BOARD_AS"])
    return "user" if sys.stdin.isatty() else "unknown"


def _writer(a) -> tuple[str, str]:
    """(from, via). An agent cannot write as the person; a process with no agent around it and no terminal has
    to say who it is."""
    via = _detected()
    if a.from_:
        frm = board.norm(a.from_)
        if board.vendor_of(frm) == "user" and via != "user":
            raise ValueError(f"only a person at a terminal can write as user (this is {via})")
        if via not in ("user", "unknown") and board.vendor_of(frm) != board.vendor_of(via):
            raise ValueError(f"this command runs inside {via}; it cannot write as {frm}")
        if ":" not in frm and ":" in via and board.vendor_of(via) == frm:
            frm = via
        return frm, via
    if via == "unknown":
        raise ValueError("say who is writing: --from claude|codex|deepseek (or set CCX_BOARD_AS)")
    return via, via


def _max_machine() -> int:
    return int(load_config(paths()).get("board", {}).get("max_machine_turns", board.MAX_MACHINE))


def _text(words: list[str]) -> str:
    if words and words != ["-"]:
        return " ".join(words)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("give the message as text or on stdin")


def cmd_say(a) -> int:
    frm, via = _writer(a)
    e = board.post(_root(a), frm, a.to, _text(a.message), thread=a.thread, via=via, max_machine=_max_machine())
    _out({"ok": True, "posted": e, "next": f"they see it on their next turn; follow the thread: "
                                          f"`ccx board --thread {e['thread']}`"})
    return 0


def cmd_reply(a) -> int:
    root = _root(a)
    parent = next((e for e in board.entries(root) if e["id"] == a.id), None)
    if parent is None:
        raise ValueError(f"no board message #{a.id}")
    frm, via = _writer(a)
    to = parent["from"] if board.vendor_of(parent["from"]) != "user" else "all"
    e = board.post(root, frm, to, _text(a.message), reply_to=a.id, via=via, max_machine=_max_machine())
    _out({"ok": True, "posted": e})
    return 0


def cmd_board(a) -> int:
    root = _root(a)
    if a.thread:
        es = board.thread(root, a.thread)
        print(f"[ccx board, thread {a.thread}: {len(es)} message(s)]")
    elif a.all:
        es = board.entries(root)[-a.limit:]
        print(f"[ccx board: the last {len(es)} message(s)]")
    else:
        reader = board.norm(a.as_) if a.as_ else _detected()
        if reader == "unknown":
            raise ValueError("say who is reading: --as claude|codex|deepseek (or set CCX_BOARD_AS)")
        if reader == "user":
            es = board.entries(root)[-a.limit:]
            print(f"[ccx board: the last {len(es)} message(s)]")
        else:
            es = board.read(root, reader, advance=not a.peek)
            if not es:
                print(f"[ccx board: nothing new for {reader}]")
                return 0
            print(board.HEADER)
    for e in es:                       # whole text here: this is where long messages are read
        re_ = f" re #{e['reply_to']}" if e.get("reply_to") else ""
        print(f"#{e['id']} {e['ts']} {e['from']} -> {e['to']} [{e['thread']}]{re_}:\n{e['text']}\n")
    return 0


def register(sub) -> None:
    targets = [*board.VENDORS, "dsh", "all"]
    sy = sub.add_parser("say", help="write to the other open sessions in this project (the board): they see it on "
                        "their next turn")
    sy.add_argument("message", nargs="*")
    sy.add_argument("--to", required=True, help=f"{' | '.join(targets)}, or one session vendor:SESSION")
    sy.add_argument("--thread", help="a short name (default: a new thread)")
    sy.add_argument("--from", dest="from_", help="who writes, when ccx cannot tell (deepseek); never another agent "
                    "or the person")
    sy.add_argument("--cwd")
    sy.set_defaults(fn=cmd_say)
    rp = sub.add_parser("reply", help="answer one board message (to its sender, in its thread)")
    rp.add_argument("id", type=int)
    rp.add_argument("message", nargs="*")
    rp.add_argument("--from", dest="from_")
    rp.add_argument("--cwd")
    rp.set_defaults(fn=cmd_reply)
    bd = sub.add_parser("board", help="unread board messages for you (moves your cursor), or one thread")
    bd.add_argument("--as", dest="as_", help="claude | codex | deepseek, or vendor:SESSION")
    bd.add_argument("--thread", help="one thread, whole")
    bd.add_argument("--all", action="store_true", help="the last messages, whoever they are for")
    bd.add_argument("--limit", type=int, default=20)
    bd.add_argument("--peek", action="store_true", help="do not move your cursor")
    bd.add_argument("--cwd")
    bd.set_defaults(fn=cmd_board)
