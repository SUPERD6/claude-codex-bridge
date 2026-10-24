"""Looking at what happened: show, stats, report, config, repair, archive, undo."""
from __future__ import annotations

from pathlib import Path

from .. import ledger, report
from ..config import SETTINGS, load_config, paths, set_setting
from ..delegate import compact, undo
from .common import _out


def cmd_report(a) -> int:
    p = paths()
    res = report.write(p, days=a.days, out=Path(a.out) if a.out else None, include_lead=not a.no_lead)
    if a.publish:
        res["publish"] = report.publish(p, Path(res["report"]).parent)
    _out(res)
    return 0


def cmd_config(a) -> int:
    p = paths()
    if a.config_cmd == "set":
        _out(set_setting(p, a.key, a.value))
        return 0
    cfg = load_config(p)
    def get(key):
        sec, name = key.split(".", 1)
        return (cfg.get(sec) or {}).get(name)
    if a.config_cmd == "get":
        _out({a.key: get(a.key)})
    else:
        _out({k: {"value": get(k), "help": h} for k, (_, h) in SETTINGS.items()})
    return 0


def cmd_repair(a) -> int:
    _out(ledger.repair(paths(), apply=a.apply))
    return 0


def cmd_archive(a) -> int:
    from .. import archive as arc
    p = paths()
    if a.restore:
        _out(arc.restore(p, a.restore))
        return 0
    ids = a.run_ids or arc.finished_runs(p, older_than_h=a.older_than)
    _out(arc.archive(p, ids, apply=a.apply))
    return 0


def cmd_undo(a) -> int:
    _out(undo(paths(), a.run_id, a.apply))
    return 0


def cmd_show(a) -> int:
    p = paths()
    rec = ledger.load_run(p, a.run_id)
    if a.full:
        _out(rec)
        d = p.runs / a.run_id
        print(f"\nlogs: {d}")
    else:
        _out(compact(rec))
    return 0


def cmd_stats(a) -> int:
    if a.summary:
        p = paths()
        s = report.summarize(p, report.collect(p, a.days))
        _out({"totals": s["totals"], "streams": [{k: v for k, v in x.items() if k not in ("agent", "role")}
                                                 for x in s["streams"] if x["events"]], "ab": s["ab"],
              "quota": s["quota"]})
        return 0
    rows = ledger.stats(paths())
    if not rows:
        print("no runs yet")
        return 0
    cols = ["agent", "tier", "runs", "done_rate", "escalated", "avg_input", "avg_cached",
            "avg_output", "avg_seconds", "cost_usd"]
    w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(w[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w[c]) for c in cols))
    return 0


def register(sub) -> None:
    ar = sub.add_parser("archive", help="archive sub-agent sessions so they don't clutter the apps' history "
                        "(dry run unless --apply)")
    ar.add_argument("run_ids", nargs="*", help="default: every finished run")
    ar.add_argument("--older-than", type=float, default=0, help="only runs finished more than N hours ago")
    ar.add_argument("--apply", action="store_true")
    ar.add_argument("--restore", metavar="RUN_ID", help="bring a run's archived sessions back")
    ar.set_defaults(fn=cmd_archive)
    ud = sub.add_parser("undo", help="put back the files a write run changed (dry run unless --apply)")
    ud.add_argument("run_id"); ud.add_argument("--apply", action="store_true")
    ud.set_defaults(fn=cmd_undo)
    sh = sub.add_parser("show", help="show a run (compact by default)")
    sh.add_argument("run_id")
    sh.add_argument("--full", action="store_true")
    sh.set_defaults(fn=cmd_show)
    st = sub.add_parser("stats", help="token/time per agent and tier; --summary for spend and savings")
    st.add_argument("--summary", action="store_true")
    st.add_argument("--days", type=int, default=30)
    st.set_defaults(fn=cmd_stats)
    rp = sub.add_parser("report", help="static HTML dashboard of tokens, spend, quota and savings")
    rp.add_argument("--days", type=int, default=30)
    rp.add_argument("--out", help="output file (default <hub>/ccx/report/index.html)")
    rp.add_argument("--no-lead", action="store_true", help="skip reading the lead's own session logs")
    rp.add_argument("--publish", action="store_true", help="commit to report.publish_dir (your private repo)")
    rp.set_defaults(fn=cmd_report)
    cf = sub.add_parser("config", help="settings, e.g. the save/fast knob: ccx config set defaults.tradeoff 0.3")
    cfs = cf.add_subparsers(dest="config_cmd", required=True)
    cs = cfs.add_parser("set"); cs.add_argument("key", choices=list(SETTINGS)); cs.add_argument("value")
    cg = cfs.add_parser("get"); cg.add_argument("key", choices=list(SETTINGS))
    cfs.add_parser("list")
    cf.set_defaults(fn=cmd_config)
    rpr = sub.add_parser("repair", help="re-count ledger rows written before a counting fix (dry run unless --apply)")
    rpr.add_argument("--apply", action="store_true")
    rpr.set_defaults(fn=cmd_repair)
