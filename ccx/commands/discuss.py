"""ccx discuss — models from different vendors talk a costly decision through (ccx/discuss.py)."""
from __future__ import annotations

import os
from pathlib import Path

from .. import discuss
from ..config import load_config, paths
from .common import _caller, _out


def started_by_agent() -> str | None:
    """Who runs this command when it is not the person at a terminal: the lead tool (from its environment, not from
    --from, which a lead may set to anything) or a ccx sub-agent. None = the person typed it."""
    if int(os.environ.get("CCX_DEPTH", "0") or 0) > 0:
        return "a ccx sub-agent"
    who = _caller(None)
    return None if who == "user" else who


def cmd_discuss(a) -> int:
    p = paths()
    if a.show:
        _out(discuss.view(discuss.load(p, a.show)))
        return 0
    if a.list:
        _out({"discussions": [{k: d.get(k) for k in ("id", "state", "question", "ts", "usd")}
                              for d in discuss.recent(p)[:20]]})
        return 0
    question = " ".join(a.question).strip()
    if a.question_file:
        question = Path(a.question_file).read_text(encoding="utf-8").strip()
    if not question:
        raise ValueError("give the question: ccx discuss \"...\" (or --question-file)")
    cfg = load_config(p)
    names = discuss.participants(cfg, a.with_.split(",") if a.with_ else None)
    context = Path(a.context_file).read_text(encoding="utf-8") if a.context_file else ""
    tiers, why = discuss.tiers(p, names, a.tier)
    est = discuss.estimate(p, names, a.rounds, tier=tiers, cfg=cfg, question=question, context=context)
    if why:
        est["tier_why"] = why
    if a.dry_run:
        _out({"would_run": True, **est, "rounds_max": a.rounds,
              "next": "ask the person; on their yes run the same command with --confirmed instead of --dry-run"})
        return 0
    agent = started_by_agent()
    if agent and not a.confirmed:      # H4: several paid model calls only on the person's yes
        _out({"ran": False, "why": f"started by {agent} without --confirmed: a discussion runs only after the "
              "person says yes", **est, "rounds_max": a.rounds,
              "next": "tell the person the question and this estimate; on their yes run the same command with "
                      "--confirmed"})
        return 0
    d = discuss.run(p, question, names, rounds=a.rounds, caller=_caller(a.caller), context=context,
                    cwd=Path(a.cwd) if a.cwd else None, tier=tiers)
    out = discuss.view(d)
    out["next"] = "the turns as a conversation: `ccx ui` (Discussions)"
    _out(out)
    return 0 if d["state"] == "done" else 1


def register(sub) -> None:
    d = sub.add_parser("discuss", help="2-3 models from different vendors talk a costly decision through: one "
                       "proposes, one finds faults, one judges; consensus, disagreements, reasons, recommendation")
    d.add_argument("question", nargs="*")
    d.add_argument("--question-file")
    d.add_argument("--context-file", help="facts the models should start from (cut to 4000 characters)")
    d.add_argument("--with", dest="with_", metavar="A,B[,C]",
                   help="who takes part, in role order (proposer, critic, judge); default: installed, one per vendor")
    d.add_argument("--rounds", type=int, default=discuss.MAX_ROUNDS, choices=range(1, discuss.MAX_ROUNDS + 1))
    d.add_argument("--tier", default="auto", help="model tier for every turn; auto (default): T2, but T1 for an "
                   "agent whose quota would run past 100%% before it resets")
    d.add_argument("--cwd")
    d.add_argument("--from", dest="caller")
    d.add_argument("--dry-run", action="store_true", help="who would take part and what it may cost; runs nothing")
    d.add_argument("--confirmed", action="store_true",
                   help="the person said yes (H4): needed when a lead or a sub-agent starts the discussion; without "
                        "it they only get the estimate")
    d.add_argument("--show", metavar="ID", help="print a past discussion")
    d.add_argument("--list", action="store_true", help="recent discussions")
    d.set_defaults(fn=cmd_discuss)
