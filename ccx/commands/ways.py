"""ccx way — do a piece of work the way its risk calls for (H8), with builders ordered by their record (H9)."""
from __future__ import annotations

from pathlib import Path

from .. import ways
from ..config import load_config, paths
from .common import _caller, _out


def _candidates(cfg: dict, caller: str, wanted: str | None) -> list[str]:
    from .. import agents
    if wanted:
        return [w.strip() for w in wanted.split(",") if w.strip()]
    inst = agents.installed()
    # another vendor than the lead first: the lead already has its own view of the work
    return [a for a in inst if not agents.same_vendor(a, caller, cfg)] + \
        [a for a in inst if agents.same_vendor(a, caller, cfg)]


def cmd_way(a) -> int:
    p = paths()
    if a.stats:
        _out({"by_kind": ways.track(p, a.days, include_evals=a.include_evals), "min_judged": ways.MIN_JUDGED,
              "evals": "included" if a.include_evals else "left out (--include-evals to count them)",
              "note": "rates over judged pieces only; below min_judged a rate does not steer anything"})
        return 0
    brief = " ".join(a.brief).strip()
    if a.brief_file:
        brief = Path(a.brief_file).read_text(encoding="utf-8").strip()
    if not brief:
        raise ValueError("give the task: ccx way \"...\" (or --brief-file)")
    from ..learn import task_kind
    cfg = load_config(p)
    caller = _caller(a.caller)
    kind = task_kind("write", a.kind)
    choice = ways.choose(a.risk, kind, ways.track(p), _candidates(cfg, caller, a.with_), cfg)
    if a.dry_run:
        _out({**choice, "kind": kind, "next": "two_versions: ask the person, then run with --yes" if choice["needs_yes"]
              else "run the same command without --dry-run"})
        return 0
    out = ways.run(p, brief, choice, cwd=Path(a.cwd).resolve() if a.cwd else Path.cwd().resolve(), check=a.check,
                   caller=caller, risk=a.risk, kind=kind, yes=a.yes)
    _out(out)
    return 0 if out.get("state") == "done" else 1


def register(sub) -> None:
    w = sub.add_parser("way", help="do a piece of work the way its risk calls for: low = one agent (+ review when "
                       "worth it), visible = one plans / another builds / the planner accepts, critical = two "
                       "versions compared (needs --yes); builders ordered by first-time-right rate per kind")
    w.add_argument("brief", nargs="*")
    w.add_argument("--brief-file")
    w.add_argument("--risk", choices=["low", "visible", "critical"], default="low")
    w.add_argument("--kind", choices=["code", "read", "research", "write"])
    w.add_argument("--with", dest="with_", metavar="A,B[,C]", help="who may take part, preferred first")
    w.add_argument("--check", help="acceptance command, run by the builder and again by ccx")
    w.add_argument("--cwd")
    w.add_argument("--from", dest="caller")
    w.add_argument("--yes", action="store_true", help="the person agreed to two_versions (about twice the cost)")
    w.add_argument("--dry-run", action="store_true", help="which way and who, without running")
    w.add_argument("--stats", action="store_true", help="first-time-right and rework rates per kind and agent (H9)")
    w.add_argument("--days", type=float, default=90)
    w.add_argument("--include-evals", action="store_true", help="with --stats: also count evaluation runs (label "
                   "eval-..., --no-ab, ccx's own probes), left out by default")
    w.set_defaults(fn=cmd_way)
