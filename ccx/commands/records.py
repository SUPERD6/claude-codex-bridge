"""Looking at what happened: show, stats, report, config, repair, archive, undo."""
from __future__ import annotations

import time
from pathlib import Path

from .. import ledger, recover, report
from ..config import SETTINGS, daily_cap, load_config, paths, set_setting
from ..agents import leads
from ..delegate import compact, recap, undo
from .common import _out, lead_session_id, provider_agents


def cmd_report(a) -> int:
    p = paths()
    res = report.write(p, days=a.days, out=Path(a.out) if a.out else None, include_lead=not a.no_lead,
                       include_evals=a.include_evals)
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
    _out(undo(paths(), a.run_id, a.apply, wrong=a.wrong))
    return 0


POLL_SEC = 2.0                          # `ccx show --wait` reads run.json this often
FIX_ROUND_GRACE = 30.0                  # a review fix round's run.json appears within this after its parent ends


def _fix_round(p, rec: dict) -> dict | None:
    """The review fix round a finished run started (delegate.run resumes the same sub-session once when the
    independent review finds problems), or None. The fix run's record points back with resumed_from/review_of."""
    if rec.get("kind") != "review_issues" or not rec.get("session_id") or not p.runs.exists():
        return None
    rid = rec["run_id"]
    for d in sorted(x for x in p.runs.iterdir() if x.name > rid):       # run ids sort by start time
        f = d / "run.json"
        if not f.exists():
            continue
        try:
            r = ledger.read_record(f)
        except (OSError, ValueError):
            continue
        if r.get("review_of") == rid or r.get("resumed_from") == rid:
            return r
    return None


def wait_run(p, run_id: str, seconds: float) -> tuple[dict | None, str]:
    """Block until run_id, and any review fix round it started, is finished. Returns (last record of the chain or
    None on timeout, the id being waited on)."""
    start = time.time()
    deadline = start + max(0.0, seconds)
    rid, ended_at, swept = run_id, None, 0.0
    if not (p.runs / rid).exists():
        raise FileNotFoundError(f"no ccx run {rid!r} under {p.runs}")
    while True:
        if time.time() - swept >= 20:                # a run whose ccx process died: interrupted, not running forever
            recover.sweep(p)
            swept = time.time()
        f = p.runs / rid / "run.json"
        rec = None
        if f.exists():                               # a --bg run writes it a moment after it was started
            try:
                rec = ledger.read_record(f)
            except (OSError, ValueError):
                rec = None
        if rec and rec.get("state") != "running":
            nxt = _fix_round(p, rec)
            if nxt:
                rid, ended_at = nxt["run_id"], None
                continue
            fix_due = rec.get("kind") == "review_issues" and bool(rec.get("session_id"))   # one is about to start
            tag_due = rid != run_id and not rec.get("review_of")     # its parent writes review_of right after
            if not (fix_due or tag_due):
                return rec, rid
            ended_at = ended_at or time.time()
            if time.time() - ended_at > (FIX_ROUND_GRACE if fix_due else 5 * POLL_SEC):
                return rec, rid                      # nothing more came (a fix round that failed to start)
        if time.time() >= deadline:
            return None, rid
        time.sleep(min(POLL_SEC, max(0.0, deadline - time.time())))


def cmd_show(a) -> int:
    p = paths()
    if a.wait is not None:
        t0 = time.time()
        rec, rid = wait_run(p, a.run_id, a.wait)
        if rec is None:
            _out({"run_id": rid, "status": "running", "waited_s": round(time.time() - t0, 1),
                  "next": f"ccx show {rid} --wait"})
            return 0
        if a.full:
            _out(rec)
            return 0
        res = compact(rec)
        if rid != a.run_id:
            res["chain"] = f"{a.run_id} -> {rid}"      # the review fix round's result is the final one
        res["recap"] = recap(rec, res)
        _out(res)
        return 0
    recover.sweep(p)                    # a run whose ccx process is gone shows as interrupted, not running
    rec = ledger.load_run(p, a.run_id)
    if a.full:
        _out(rec)
        d = p.runs / a.run_id
        print(f"\nlogs: {d}")
    else:
        _out(compact(rec))
    return 0


def cmd_stats(a) -> int:
    recover.sweep(paths())              # count runs whose ccx process died, with what they spent
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
        _out(trial.stop(p, a.void))
    elif a.trial_cmd == "tag":
        from ..usage import _ts
        def when(s):
            if s is None:
                return None
            t = _ts(s)
            if t is None:
                raise ValueError(f"not an ISO time: {s!r} (e.g. 2026-10-26T14:30)")
            return t
        _out(trial.tag(p, a.session, a.arm, a.kind, a.b, None if a.ok is None else bool(a.ok),
                       when(a.since), when(a.until), a.note or ""))
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


def cmd_agents(a) -> int:
    """What each agent CLI can do, which vendor it is, and whether ccx tests it on a real machine (I2, I8)."""
    from .. import agents
    from ..runners import find_bin
    cfg = load_config(paths())
    rows = [{"agent": ad.name, "vendor": ad.vendor, "support": ad.support, "tested_version": ad.tested_version,
             "installed": bool(find_bin(ad.name)), **ad.capabilities(), "context_file": ad.context_file,
             "start_hook": ad.start_hook, "session_files": ad.session_files,
             **({"daily_usd": daily_cap(cfg, ad.name)} if ad.pay_per_token else {})} for ad in agents.all_adapters()]
    ready = set(provider_agents(cfg))
    for name, pv in (cfg.get("providers") or {}).items():
        rows.append({"agent": name, "vendor": agents.vendor(name, cfg), "support": "community",
                     "provider_of": pv.get("agent", "claude"), "can_work": True, "can_lead": False,
                     "pay_per_token": True, "ready": name in ready, "models": pv.get("models") or [],
                     "needs_env": sorted(str(v)[1:] for v in (pv.get("env") or {}).values() if str(v).startswith("$")),
                     "daily_usd": pv.get("daily_usd")})
    _out({"agents": rows})
    return 0


def register(sub) -> None:
    sm = sub.add_parser("sum", help="run a command and show only what matters of its output (tests: failures; "
                        "diffs: per file; logs: errors); the full output is kept in .ccx/sum/")
    sm.add_argument("--kind", choices=["auto", "test", "diff", "log"], default="auto")
    sm.add_argument("--max-chars", type=int, default=2000)
    sm.add_argument("--shell", action="store_true", help="run through the shell (pipes, globs)")
    sm.add_argument("--ask", help="too long still: a cheap routed model answers this from the saved output")
    sm.add_argument("argv", nargs="+", help="-- then the command")
    sm.set_defaults(fn=cmd_sum)
    ag = sub.add_parser("agents", help="each agent CLI: vendor, what it can do, tested version, official or community")
    ag.set_defaults(fn=cmd_agents)
    tr = sub.add_parser("trial", help="a formal comparison over a week: half the delegable tasks done by the lead "
                        "itself, half delegated, measured the same way")
    trs = tr.add_subparsers(dest="trial_cmd", required=True)
    ts = trs.add_parser("start")
    ts.add_argument("--days", type=float, default=7.0)
    ts.add_argument("--rate", type=float, default=0.5, help="share of tasks the lead does itself (default 0.5)")
    ts.add_argument("--note", help="what this trial is about")
    tsp = trs.add_parser("stop")
    tsp.add_argument("--void", metavar="REASON", help="record the trial as void with this reason (the last one when "
                     "it has already ended): its report then claims no result")
    tt = trs.add_parser("tag", help="count a Claude conversation that did a task with its own helpers or a "
                        "workflow (native) into the trial; its spend, helpers included, is read from its files")
    tt.add_argument("--arm", choices=["native", "self"], default="native")
    tt.add_argument("--session", required=True, help="the Claude conversation's session id")
    tt.add_argument("--kind", help="kind of work, as `ccx route` names it (code, test, docs, read, ...)")
    tt.add_argument("--b", type=float, help="difficulty, as `ccx route` estimates it")
    tt.add_argument("--ok", type=int, choices=[0, 1], help="did the work hold up (omit when not judged yet)")
    tt.add_argument("--since", help="only turns from this time (ISO), when the conversation did more than the task")
    tt.add_argument("--until", help="only turns up to this time (ISO)")
    tt.add_argument("--note")
    trp =trs.add_parser("report", help="the comparison so far (the last trial when none is running)")
    trp.add_argument("--markdown", action="store_true", help="the table for the README")
    tr.set_defaults(fn=cmd_trial)
    ld = sub.add_parser("lead", help="how many tokens each turn of your lead conversations re-reads, and when a "
                        "fresh conversation would be cheaper")
    ld.add_argument("--hours", type=float, default=24.0)
    ld.add_argument("--limit", type=int, default=10)
    ld.add_argument("--threshold", type=int, default=150_000, help="tokens a turn reads before advising")
    ld.add_argument("--hint", action="store_true", help="for a per-turn hook: read the hook's JSON on stdin and "
                    "print one line only when this conversation is long (at most once every 20 turns)")
    ld.add_argument("--as", dest="as_", choices=leads())
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
    ud.add_argument("--wrong", action="store_true", help="with --apply: also record the run as wrong (teaches "
                    "routing). Without it undoing records no verdict")
    ud.set_defaults(fn=cmd_undo)
    sh = sub.add_parser("show", help="show a run (compact by default); --wait blocks until it is finished")
    sh.add_argument("run_id")
    sh.add_argument("--full", action="store_true")
    sh.add_argument("--wait", nargs="?", type=float, const=540.0, default=None, metavar="SECONDS",
                    help="block until the run (and a review fix round it started) is finished, then print the "
                         "same compact result as `ccx run`; default 540 s, under a 10-minute tool-call limit. "
                         "Still running then: status=running and the command to call again")
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
    rp.add_argument("--include-evals", action="store_true", help="'where it was wrong' also counts evaluation runs")
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
