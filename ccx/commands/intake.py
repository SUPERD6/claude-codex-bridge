"""ccx intake list|pull|ask|done|status — tasks filed as labelled issues in the person's PRIVATE GitHub repository
(ccx/intake.py, docs/intake.md). One-off commands: nothing polls by itself."""
from __future__ import annotations

from .. import intake
from ..config import load_config, paths
from .common import _out


def cmd_intake(a) -> int:
    p = paths()
    sub = a.intake_cmd or "status"
    if sub == "status":
        rows = intake.local(p)
        _out({"open": len(rows), "tasks": rows,
              "next": "`ccx intake list` shows what is on GitHub; `ccx intake pull` takes the new ones"})
        return 0
    repo, label = intake.settings(load_config(p))
    if sub in ("list", "pull"):
        _out(intake.scan(p, repo, label, take=sub == "pull"))
    elif sub == "ask":
        _out(intake.ask(p, repo, a.number, " ".join(a.question)))
    elif sub == "done":
        _out(intake.done(p, repo, a.number, " ".join(a.result), pr=a.pr or "", branch=a.branch or "",
                         cost=a.cost or "", unverified=a.unverified or "", close=a.close))
    return 0


def register(sub) -> None:
    ik = sub.add_parser("intake", help="tasks you file as issues labelled ccx-task in a PRIVATE GitHub repository of "
                        "yours (intake.github): pull them, ask for an approval there, report back there. One-off "
                        "commands, never on a timer by itself")
    ik.set_defaults(fn=cmd_intake, intake_cmd=None)
    s = ik.add_subparsers(dest="intake_cmd", metavar="<what>")
    s.add_parser("status", help="what this computer took and has not reported done (default; no network)")
    s.add_parser("list", help="open labelled issues by you, and replies to ccx's questions (takes nothing)")
    s.add_parser("pull", help="take the new issues and the replies; a pulled issue is never handed out twice")
    ak = s.add_parser("ask", help="comment a question on the issue (an approval the next step needs) and wait for "
                      "your reply there")
    ak.add_argument("number", type=int)
    ak.add_argument("question", nargs="+")
    dn = s.add_parser("done", help="comment the report on the issue: the result in a sentence or two, PR/branch, "
                      "cost, what was not verified")
    dn.add_argument("number", type=int)
    dn.add_argument("result", nargs="+")
    dn.add_argument("--pr")
    dn.add_argument("--branch")
    dn.add_argument("--cost", help="what it cost, e.g. from `ccx show RUN`")
    dn.add_argument("--unverified", help="what was not checked")
    dn.add_argument("--close", action="store_true", help="also close the issue")
