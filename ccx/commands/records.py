"""Looking at what happened: show, stats, report, config, repair, archive, undo."""
from __future__ import annotations

from pathlib import Path

from .. import ledger, report
from ..config import SETTINGS, load_config, paths, set_setting
from ..delegate import compact, undo
from .common import _out, lead_session_id


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


def cmd_lead(a) -> int:
    """How much the lead's own conversations re-read every turn (H10); --hint: one line for the next turn, from a
    hook, or nothing."""
    import json
    import sys
    from .. import context
    p = paths()
    if a.breakdown or a.cache or a.suggest:
        from .. import leadcost, ledger
        from ..transcript import find_session
        agent = a.as_ or ("codex" if lead_session_id("codex") and not lead_session_id("claude") else "claude")
        exclude = {s for r in ledger.rows(p) if not r.get("type") for s in r.get("sessions", [])}
        f = find_session(agent, Path.cwd(), exclude, a.session)
        if not f:
            _out({"error": f"no {agent} lead session found for {Path.cwd()} (give --session ID or --as)"})
            return 3
        _out(leadcost.breakdown(p, agent, f) if a.breakdown else leadcost.cache_breaks(p, agent, f) if a.cache
             else leadcost.suggest(p, agent, f))
        return 0
    if a.hint:
        try:
            data = json.loads(sys.stdin.read() or "{}") if not sys.stdin.isatty() else {}
        except ValueError:
            data = {}
        try:
            text = context.hint(p, a.as_ or "claude", data, a.threshold)
        except Exception:  # noqa: BLE001 — a hook must never break the lead's turn
            text = ""
        if text:
            print(text)
        return 0
    rows = context.sessions(p, a.hours)
    for r in rows:
        r["advice"] = context.advice(r, a.threshold) or None
    _out({"sessions": rows[: a.limit], "threshold_tokens": a.threshold,
          "note": "each turn re-reads the whole conversation; a shorter lead conversation is the biggest saving"})
    return 0


def cmd_trial(a) -> int:
    """A week-long formal comparison (H11): half the delegable tasks done by the lead itself, half delegated."""
    from .. import trial
    p = paths()
    if a.trial_cmd == "start":
        t = trial.start(p, a.days, a.rate, a.note or "")
        _out({**t, "how": "nothing else to do: `ccx run`/`ccx route` now tell you which tasks to do yourself "
                          "(close each with `ccx ab done ID --ok 1|0`), and judge delegated work with `ccx verify` "
                          "as usual; `ccx trial report` any time"})
    elif a.trial_cmd == "stop":
        _out(trial.stop(p))
    elif a.markdown:
        print(trial.markdown(trial.summarize(p)) or "no trial yet")
    else:
        _out(trial.summarize(p))
    return 0


def cmd_sum(a) -> int:
    """Run a command and print only what matters of its output (J3); the full output stays in .ccx/sum/."""
    import subprocess
    from .. import summarize
    from ..config import ccx_argv
    argv = [x for x in a.argv if x != "--"]
    if not argv:
        raise ValueError("usage: ccx sum [options] -- <command> [args...]")
    res = summarize.run(argv, Path.cwd(), a.kind, a.max_chars, a.shell)
    print(summarize.header(res, argv))
    print(res["text"])
    if a.ask:
        brief = (f"Read the file {res['log']} (output of `{' '.join(argv)}`, exit {res['exit']}). Answer: {a.ask}\n"
                 "Quote only the few lines that matter. Do not run the command again and do not edit anything.")
        r = subprocess.run([*ccx_argv(), "run", "--mode", "read", "--kind", "read", "--b", "2", "--no-ab", brief],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            import json
            got = json.loads(r.stdout)
            print(f"\n[ccx sum --ask → {got.get('agent')} {got.get('model')}, run {got.get('run_id')}]\n"
                  f"{got.get('summary') or got.get('advice') or r.stdout[-1500:]}")
        except ValueError:
            print("\n[ccx sum --ask failed]\n" + (r.stdout + r.stderr)[-1500:])
    return res["exit"]


def register(sub) -> None:
    sm = sub.add_parser("sum", help="run a command and show only what matters of its output (tests: failures; "
                        "diffs: per file; logs: errors); the full output is kept in .ccx/sum/")
    sm.add_argument("--kind", choices=["auto", "test", "diff", "log"], default="auto")
    sm.add_argument("--max-chars", type=int, default=2000)
    sm.add_argument("--shell", action="store_true", help="run through the shell (pipes, globs)")
    sm.add_argument("--ask", help="too long still: a cheap routed model answers this from the saved output")
    sm.add_argument("argv", nargs="+", help="-- then the command")
    sm.set_defaults(fn=cmd_sum)
    tr = sub.add_parser("trial", help="a formal comparison over a week: half the delegable tasks done by the lead "
                        "itself, half delegated, measured the same way")
    trs = tr.add_subparsers(dest="trial_cmd", required=True)
    ts = trs.add_parser("start")
    ts.add_argument("--days", type=float, default=7.0)
    ts.add_argument("--rate", type=float, default=0.5, help="share of tasks the lead does itself (default 0.5)")
    ts.add_argument("--note", help="what this trial is about")
    trs.add_parser("stop")
    trp = trs.add_parser("report", help="the comparison so far (the last trial when none is running)")
    trp.add_argument("--markdown", action="store_true", help="the table for the README")
    tr.set_defaults(fn=cmd_trial)
    ld = sub.add_parser("lead", help="how many tokens each turn of your lead conversations re-reads, and when a "
                        "fresh conversation would be cheaper")
    ld.add_argument("--hours", type=float, default=24.0)
    ld.add_argument("--limit", type=int, default=10)
    ld.add_argument("--threshold", type=int, default=150_000, help="tokens a turn reads before advising")
    ld.add_argument("--hint", action="store_true", help="for a per-turn hook: read the hook's JSON on stdin and "
                    "print one line only when this conversation is long (at most once every 20 turns)")
    ld.add_argument("--as", dest="as_", choices=["claude", "codex"])
    ld.add_argument("--breakdown", action="store_true", help="what every turn re-reads, part by part (system "
                    "prompt, tools, each MCP server, instruction files, skill list, hook output), with advice")
    ld.add_argument("--cache", action="store_true", help="turns where the prompt cache broke, the likely cause "
                    "and what it cost")
    ld.add_argument("--suggest", action="store_true", help="a model for the lead itself from what the recent "
                    "turns did, with the saving per 100 turns and how soon a switch pays back")
    ld.add_argument("--session", help="with --breakdown/--cache/--suggest: a session id (default: the newest here)")
    ld.set_defaults(fn=cmd_lead)
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
