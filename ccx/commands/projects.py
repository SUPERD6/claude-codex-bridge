"""ccx projects [scan|show] — the person's project catalog (ccx/projects.py), kept in the hub on this machine."""
from __future__ import annotations

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


def register(sub) -> None:
    pj = sub.add_parser("projects", help="your projects on this machine (catalog in the hub): list, scan, show")
    pjs = pj.add_subparsers(dest="projects_cmd")
    sc = pjs.add_parser("scan", help="find every project under projects.roots (full rescan)")
    sc.add_argument("--root", action="append", help="scan this folder instead of projects.roots (repeatable)")
    sh = pjs.add_parser("show", help="one project: path, summary, aliases, rule and state files, recent work")
    sh.add_argument("name")
    pj.set_defaults(fn=cmd_projects)
