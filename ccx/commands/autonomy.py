"""ccx autonomy [set|merge] — how much the project manager does without asking (ccx/autonomy.py, K4)."""
from __future__ import annotations

from pathlib import Path

from .. import autonomy, projects
from ..config import load_config, paths
from ..ledger import load_run
from .common import _out


def _onoff(v: str | None) -> bool | None:
    return None if v is None else v == "on"


def cmd_autonomy(a) -> int:
    p = paths()
    cfg = load_config(p)
    sub = getattr(a, "autonomy_cmd", None)
    if sub == "set":
        if not a.level and a.auto_merge is None:
            raise ValueError("give a level (L0, L1, L2) and/or --auto-merge on|off")
        _out({"set": autonomy.set_level(p, a.level, a.project, _onoff(a.auto_merge)),
              "now": autonomy.level_for(a.project, p, load_config(p))})
        return 0
    if sub == "merge":
        e = autonomy._entry(p, a.project) if a.project else None
        if not e:                               # the project whose worktree this run used
            repo = autonomy._repo_of(Path(load_run(p, a.run_id).get("cwd") or "."))
            cat = projects.load(p)
            e = projects.find(cat, str(repo)) if cat and repo else None
        info = autonomy.level_for(e, p, cfg)
        out = autonomy.merge(p, a.run_id, info, cfg, rules=projects.approval_rules(e) if e else None,
                             apply=a.apply)
        _out({"autonomy": {k: info[k] for k in ("level", "source", "project", "auto_merge")}, **out})
        return 0 if out.get("can_merge") or out.get("merged") else 2
    _out(autonomy.overview(p, cfg, a.project))
    return 0


def register(sub) -> None:
    au = sub.add_parser("autonomy", help="how much the project manager does without asking: L0 propose, "
                                         "L1 ask before edits, L2 merge small checked branches")
    au.add_argument("--project", help="a project from the catalog (default: the overall level)")
    aus = au.add_subparsers(dest="autonomy_cmd")
    st = aus.add_parser("set", help="set the default level, or one project's level and merge permission")
    st.add_argument("level", nargs="?", choices=list(autonomy.LEVELS))
    st.add_argument("--project", help="this project only (kept in the hub, on this machine)")
    st.add_argument("--auto-merge", choices=["on", "off"], help="with --project: may L2 merge its small branches")
    mg = aus.add_parser("merge", help="L2: may this worktree run's branch be merged? --apply merges it")
    mg.add_argument("run_id")
    mg.add_argument("--project")
    mg.add_argument("--apply", action="store_true")
    au.set_defaults(fn=cmd_autonomy)
