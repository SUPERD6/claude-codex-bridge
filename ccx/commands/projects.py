"""ccx projects [scan|show] — the person's project catalog (ccx/projects.py), kept in the hub on this machine."""
from __future__ import annotations

from pathlib import Path

from .. import projects
from ..config import load_config, paths
from .common import _out


def cmd_projects(a) -> int:
    p = paths()
    cfg = load_config(p)
    sub = getattr(a, "projects_cmd", None)
    if sub == "scan":
        cat = projects.refresh(p, cfg, roots=a.root or None)
        _out({"catalog": str(projects.store(p)), "roots": cat["roots"], "missing_roots": cat["missing_roots"],
              "projects": len(cat["projects"]), "newest": [projects.brief_row(e) for e in cat["projects"][:10]]})
        return 0
    cat = projects.load(p)
    if not cat:
        _out({"projects": [], "next": 'set the folders your projects live in: `ccx config set projects.roots '
                                      '"DIR;DIR"`, then `ccx projects scan`'})
        return 0
    if sub == "show":
        e = projects.find(cat, a.name)
        if not e:
            raise ValueError(f"no project named {a.name!r} in the catalog; `ccx projects` lists them")
        _out(e)
        return 0
    _out({"scanned_at": cat.get("scanned_at"), "projects": [projects.brief_row(e) for e in cat["projects"]]})
    return 0


def cmd_where(a) -> int:
    p = paths()
    cat = projects.load(p)
    if not cat:
        raise ValueError('no project catalog yet: `ccx config set projects.roots "DIR;DIR"`, then `ccx projects scan`')
    r = projects.where(cat, " ".join(a.words), limit=a.limit)
    if r["pick"]:
        e = projects.find(cat, r["pick"]) or {}
        r["path"] = e.get("path")
        r["read_first"] = e.get("rules", []) + [str(Path(e["path"]) / s) for s in e.get("state", [])
                                                 if s != "topics/"]
        rules = projects.approval_rules(e)
        if rules:
            r["approval_rules"] = rules     # the project's own words on approval; the lead decides
    else:
        r["next"] = ("several projects fit: ask which one (or use the name from the list)" if r["candidates"]
                     else "nothing in the catalog fits; `ccx projects` lists them, `ccx projects scan` refreshes")
    _out(r)
    return 0


def for_run(a) -> tuple[dict | None, dict | None]:
    """`ccx run --project X`: (the project, None) after pointing the run at its folder, or (None, what to tell
    the lead) when the project's rules speak of approval and the lead has not said it read them (--rules-ok)."""
    if a.cwd:
        raise ValueError("give --project or --cwd, not both")
    cat = projects.load(paths())
    if not cat:
        raise ValueError('--project needs the project catalog: `ccx config set projects.roots "DIR;DIR"`, then '
                         "`ccx projects scan`")
    e = projects.resolve(cat, a.project)
    rules = projects.approval_rules(e)
    if rules and not a.rules_ok:
        return None, {"delegated": False, "project": e["name"], "path": e["path"], "approval_rules": rules,
                      "note": "the project's own rules on approval, quoted as written; ccx does not judge whether "
                              "this task is allowed",
                      "next": "read them; if they allow this task (or the person approved it), run again with "
                              "--rules-ok; otherwise ask the person first"}
    a.cwd = e["path"]
    return {"name": e["name"], "path": e["path"], "header": projects.brief_header(e),
            "approval_rules": rules}, None


def register(sub) -> None:
    wh = sub.add_parser("where", help='which project a sentence is about: ccx where "the desk pet" (code only, free)')
    wh.add_argument("words", nargs="+")
    wh.add_argument("--limit", type=int, default=5)
    wh.set_defaults(fn=cmd_where)
    pj = sub.add_parser("projects", help="your projects on this machine (catalog in the hub): list, scan, show")
    pjs = pj.add_subparsers(dest="projects_cmd")
    sc = pjs.add_parser("scan", help="find every project under projects.roots (full rescan)")
    sc.add_argument("--root", action="append", help="scan this folder instead of projects.roots (repeatable)")
    sh = pjs.add_parser("show", help="one project: path, summary, aliases, rule and state files, recent work")
    sh.add_argument("name")
    pj.set_defaults(fn=cmd_projects)
