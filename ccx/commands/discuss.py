"""ccx discuss — models from different vendors talk a costly decision through (ccx/discuss.py)."""
from __future__ import annotations

from pathlib import Path

from .. import discuss
from ..config import load_config, paths
from .common import _caller, _out


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
    names = discuss.participants(load_config(p), a.with_.split(",") if a.with_ else None)
    est = discuss.estimate(p, names, a.rounds)
    if a.dry_run:
        _out({"would_run": True, **est, "rounds_max": a.rounds,
              "next": "ask the person; on their yes run the same command without --dry-run"})
        return 0
    context = Path(a.context_file).read_text(encoding="utf-8") if a.context_file else ""
    d = discuss.run(p, question, names, rounds=a.rounds, caller=_caller(a.caller), context=context,
                    cwd=Path(a.cwd) if a.cwd else None, tier=a.tier)
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
    d.add_argument("--tier", default="T2", help="model tier for every turn (default T2)")
    d.add_argument("--cwd")
    d.add_argument("--from", dest="caller")
    d.add_argument("--dry-run", action="store_true", help="who would take part and what it may cost; runs nothing")
    d.add_argument("--show", metavar="ID", help="print a past discussion")
    d.add_argument("--list", action="store_true", help="recent discussions")
    d.set_defaults(fn=cmd_discuss)
