"""Delegating work: run, ask, resume, batch, send, route, verify, A/B, task, plan."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import lanes, learn, ledger, router, usage
from ..config import AGENTS, DELEGATE_AGENTS, PROVIDER_AGENTS, TIER_ORDER, load_config, paths
from ..delegate import Request, compact, recap, run, verify
from ..runners import find_bin
from ..workspace import missing_test_paths
from .common import (_brief, _caller, _out, _routing_args, _spec_from_args, _target, find_continuable,
    apply_mode, find_seat, installed_agents, lead_session_id, parse_quota, provider_agents, resolve)
from .install import tier_spec_safe
from ..subagents import parse_spec as subagents_spec


def cmd_ab(a) -> int:
    """Close an A/B self-run sample: sum the lead's own usage since the sample opened."""
    p = paths()
    f = p.state / "ab" / f"{a.ab_id}.json"
    if not f.exists():
        raise FileNotFoundError(f"no open A/B sample {a.ab_id}")
    s = json.loads(f.read_text(encoding="utf-8"))
    subs = {x for r in ledger.rows(p) if not r.get("type") for x in r.get("sessions", [])}
    w = usage.window_usage(s["caller"], s["ts"], None, subs, s.get("lead_session"))
    model = w["model"] or load_config(p).get("lead", {}).get(s["caller"], "")
    ae = learn.price_usd(p, s["caller"], model, w["usage"])
    row = {"type": "selfrun", "ab_id": s["id"], "agent": s["caller"], "model": model, "b": s["b"],
           "would_route": s["would_route"], "ok": bool(a.ok), "usage4": w["usage"],
           "messages": w["messages"], "ae_usd": None if ae is None else round(ae, 6),
           "seconds": round(time.time() - s["ts"], 1), "ts": time.time(),
           **{k: s[k] for k in ("trial", "bucket", "kind") if s.get(k)}}
    ledger.append_event(p, row)
    f.unlink()
    _out(row)
    return 0


# ---------------------------------------------------------------- commands
def _background(argv: list[str], p) -> dict:
    """Re-run this exact command detached; the run id is fixed up front so the caller can poll it."""
    from .common import detach
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    log = p.runs / run_id / "bg.log"
    detach(argv, log, {"CCX_RUN_ID": run_id})
    return {"run_id": run_id, "state": "started", "check": f"ccx show {run_id}", "log": str(log),
            "next": f"ccx show {run_id} --wait"}     # blocks until done, under a 10-minute tool-call limit


def _check_names_real_tests(check: str | None, cwd: Path) -> str | None:
    """Stop before any sub-agent is paid when --check names test files that are not there (pytest exit 4 later).
    A missing tests/X.py is swapped for the files tests/X_*.py that exist (a guessed short name; listed one by one, not
    a glob, so it works on Windows), else for its one near-identical match (a typo), with a one-line notice on stderr;
    otherwise the error lists the test files that do exist, so the lead can fix the check in one retry."""
    miss = missing_test_paths(check or "", cwd)
    if not miss:
        return check
    if all(m["prefix"] or len(m["sure"]) == 1 for m in miss):
        for m in miss:
            use = " ".join(m["prefix"] or m["sure"])
            check = re.sub(r"(?<![\w./\\-])" + re.escape(m["path"]) + r"(?![\w./\\-])", lambda _: use, check)
            print(f"ccx: --check names {m['path']}, which does not exist; using {use}", file=sys.stderr)
        return check
    tests = cwd / "tests"
    known = sorted(q.relative_to(cwd).as_posix() for q in tests.rglob("test*.py")) if tests.is_dir() else []
    shown = ", ".join(known[:40]) + (f", ... (+{len(known) - 40} more)" if len(known) > 40 else "")
    raise ValueError("--check names test files that do not exist in " + str(cwd) + ": " + "; ".join(
        m["path"] + (" (close: " + ", ".join(m["close"]) + ")" if m["close"] else " (no close match)")
        for m in miss) + ". Existing test files: " + (shown or "none"))


def cmd_run(a) -> int:
    p = paths()
    cfg = load_config(p)
    proj = None
    if a.project:                                # into a project from the catalog (ccx/commands/projects.py)
        from .projects import for_run
        proj, stop = for_run(a)
        if stop:
            _out(stop)
            return 0
    auto = None
    if proj or a.autonomy:                       # a manager's dispatch: its autonomy level decides (K4)
        from .. import autonomy
        auto = autonomy.level_for(proj["name"] if proj else None, p, cfg, flag=a.autonomy)
    if a.check:
        a.check = _check_names_real_tests(a.check, Path(a.cwd or os.getcwd()))
    if a.bg and not a.brief and not a.brief_file:
        raise ValueError("--bg needs the task as text or --brief-file (stdin is not passed on)")
    if a.bg and not auto:
        _out(_background(sys.argv[1:], p))
        return 0
    text = _brief(a)
    caller = _caller(a.caller)
    spec = _spec_from_args(a, text)
    mode = apply_mode(spec)                      # before routing: start-up cost depends on read/write
    kw, route = resolve(spec, caller, p, cfg)
    route["mode"] = mode
    if a.proposal:                               # the person said yes to an offer (H12)
        from .. import proposals
        proposals.answer(p, a.proposal, True)
        route["proposal"] = a.proposal
    if kw is None:
        _out({"delegated": False, "advice": route.get("advice"), "route": route,
              "hint": "add --force to delegate anyway"})
        return 0
    if auto:
        plan = {"to": kw["to"], "model": kw.get("model"), "effort": kw.get("effort"), "mode": mode["mode"],
                **{k: route[k] for k in ("rung", "p", "expected_usd") if route.get(k) is not None},
                **({"check": a.check} if a.check else {}), **({"budget_usd": a.budget} if a.budget else {}),
                **({"project": proj["name"]} if proj else {})}
        stop = autonomy.gate(auto, mode["mode"], bool(a.approved or a.proposal), plan)
        if stop:
            _out(stop)
            return 0
        if a.bg:
            _out(_background(sys.argv[1:], p))
            return 0
    lead = lead_session_id(caller)
    cwd = Path(a.cwd or os.getcwd())
    fork = None
    if a.fork:
        if kw["to"] != "claude" or caller != "claude" or not os.environ.get("CLAUDE_CODE_SESSION_ID"):
            raise ValueError("--fork works only from a Claude Code lead to a Claude sub-agent (a session can "
                             "only be copied within the same tool); other directions get the context via the brief")
        fork = os.environ["CLAUDE_CODE_SESSION_ID"]
    if a.seat:
        prev = None if (a.new or a.fork or a.worktree) else find_seat(p, a.seat, cwd, kw["to"])
    else:
        prev = None if (a.new or a.fork or a.worktree) else find_continuable(p, lead, cwd, kw["to"], mode["mode"])
    if proj:
        text = f"{proj['header']}\n\n{text}"
    req = Request(brief=text, mode=mode["mode"], mode_source=mode["source"], mode_why=mode["why"], cwd=cwd, caller=caller,
                  worktree=a.worktree, escalate=False if a.no_escalate else None,
                  label=f"seat:{a.seat}" if a.seat else (a.label or ""),
                  fallback=not a.no_fallback, task=a.task, step=a.step, mcp=True if a.mcp else None,
                  lead_session=lead, resume_run=prev, continued=bool(prev), fork_lead=fork,
                  allow_subagents=not a.no_subagents, check=a.check, review=a.review, risk=a.risk,
                  namecheck=getattr(a, "namecheck", None),
                  subagents="off" if a.no_subagents else subagents_spec(a.subagents), budget_usd=a.budget,
                  parallel=True if a.parallel else None, share_context=a.context, **kw)
    rec = run(req, p)
    res = compact(rec)
    if prev:
        res["continued_from"] = prev          # same sub-session: it remembers the earlier task(s)
    res["route"] = {k: v for k, v in route.items() if k in ("source", "b", "rung", "p", "chain_p", "tier",
                                                              "stale", "mode", "trial")}
    if proj:
        res["project"] = {k: proj[k] for k in ("name", "path", "approval_rules") if proj.get(k)}
    if auto:
        res["autonomy"] = {k: auto[k] for k in ("level", "source")}
        if auto["level"] == "L2" and rec["ok"] and res.get("worktree"):
            res["autonomy"]["merge"] = autonomy.merge(p, rec["run_id"], auto, cfg,
                                                      rules=(proj or {}).get("approval_rules"),
                                                      apply=auto["auto_merge"])
    if route.get("b") is None:
        # an explicit pick with no size: its verdict reaches the ledger but not routing (seven-cores A/B, PR #30)
        res["route"]["learns"] = "no: give --minutes (or the rubric flags) so this run's verdict can teach routing"
    res["recap"] = recap(rec, res)              # last key: survives `| tail`
    _out(res)
    return 0 if res["ok"] else 2


def cmd_send(a) -> int:
    """Talk to a running *desktop/interactive* Codex session (the Codex app) instead of a headless one."""
    import subprocess
    codex = find_bin("codex")
    if not codex:
        raise FileNotFoundError("codex CLI not found")
    from ..runners import bin_argv
    if a.list or not a.thread:
        from ..usage import codex_threads
        _out({"threads": codex_threads(),
              "next": "ccx send --to codex --thread <thread> \"message\" (pick one whose cwd is your project)"})
        return 0
    text = " ".join(a.message) if a.message else sys.stdin.read()
    if not a.force:
        # don't cut in while the person is working in that conversation (OpenRig's typing guard)
        import time as _t
        from ..usage import thread_activity
        waited, act = 0, thread_activity(a.thread)
        while act["busy"] and waited < a.wait:
            _t.sleep(min(10, a.wait - waited))
            waited += 10
            act = thread_activity(a.thread)
        if act["busy"]:
            _out({"ok": False, "held": True, "thread": a.thread, "why": act["why"],
                  "next": "send again when the conversation is idle, or add --force to send now"})
            return 2
    r = subprocess.run([*bin_argv("codex"), "queue", "--thread", a.thread, "--message", text],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    _out({"ok": r.returncode == 0, "thread": a.thread, "output": (r.stdout or r.stderr).strip()[-800:]})
    return 0 if r.returncode == 0 else 2


def cmd_ask(a) -> int:
    """Quick second opinion from another model: read-only, low effort, no escalation, not learned from."""
    p = paths()
    cfg = load_config(p)
    caller = _caller(a.caller)
    to = _target(a.to, caller)
    spec = tier_spec_safe(cfg, "T2", to)
    if not spec:
        raise ValueError(f"no T2 model configured for {to}")
    effort = "default" if to == "gemini" else "low"
    req = Request(to=to, brief=_brief(a), mode="read", cwd=Path(a.cwd or os.getcwd()), caller=caller,
                  escalate=False, label="ask", model=spec["model"], effort=effort, ephemeral=True)
    rec = run(req, p)
    c = compact(rec)
    _out({k: c.get(k) for k in ("run_id", "agent", "model", "ok", "summary", "open_questions", "tokens")})
    return 0 if rec["ok"] else 2


def _run_records(p):
    for f in p.runs.glob("*/run.json") if p.runs.exists() else []:
        try:
            yield json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue


def _restart_step(p, a, root: Path, step: dict, last: dict, brief: str) -> int:
    f = p.runs / last["run_id"] / "brief.md"
    own = f.read_text(encoding="utf-8") if f.exists() else step["title"]
    text = (f"{own}\n\n(An earlier attempt at this step, run {last['run_id']}, was cut off before its session "
            "started. Look at `git diff` for anything it already changed; do not redo finished work.)\n\n" + brief)
    rung = (last.get("first_rung") or "").split(":")
    model, effort = (rung[1], rung[2]) if len(rung) == 3 and rung[0] == last["to"] else (None, None)
    req = Request(to=last["to"], brief=text, mode=last.get("mode") or "write", cwd=Path(last.get("cwd") or root),
                  caller=_caller(a.caller), task=a.task, step=step["n"], label=f"{a.task}#{step['n']}",
                  model=model, effort=effort, check=last.get("check_cmd"), provider=last.get("provider"))
    rec = run(req, p)
    _out(compact(rec) | {"restarted": last["run_id"], "why": "the earlier run was cut off before its session "
                         "started, so there was nothing to resume"})
    return 0 if rec["ok"] else 2


def cmd_task(a) -> int:
    """Long tasks (task-checkpoint): status, or continue an interrupted one with a single command."""
    p = paths()
    cp = learn.module(p, "checkpoint")
    root = learn.cp_root(Path(a.cwd or os.getcwd()))
    os.environ.setdefault("CHECKPOINT_ROOT", str(root))
    if a.task_cmd == "status":
        return int(cp.main(["status", *([a.task] if a.task else [])]) or 0)
    t = cp.Task(a.task, root)
    t.save()
    steps = t.plan["steps"]
    nxt = next((s for s in steps if s["status"] in ("doing", "failed")), None) or \
        next((s for s in steps if s["status"] == "todo"), None)
    if nxt is None:
        _out({"task": a.task, "state": "all steps done", "next": "verify, then checkpoint finish"})
        return 0
    runs = [r for r in ledger.rows(p) if not r.get("type") and r.get("task") == a.task and r.get("step") == nxt["n"]]
    if not runs:
        # a run killed mid-way (closed window, crash) never reached the ledger; its record and session id are on disk
        runs = sorted((r for r in _run_records(p) if r.get("task") == a.task and r.get("step") == nxt["n"]
                       and r.get("session_id")), key=lambda r: r.get("ts") or 0)
    brief = (t.dir / "checkpoint.md").read_text(encoding="utf-8")
    if not runs:
        started = sorted((r for r in _run_records(p) if r.get("task") == a.task and r.get("step") == nxt["n"]),
                         key=lambda r: r.get("ts") or 0)
        if started:
            # killed before its agent session began (seen in a real run, killed after 12 s): there is no session to
            # resume, so start the step again from the person's brief instead of only printing advice
            return _restart_step(p, a, root, nxt, started[-1], brief)
    if not runs:
        _out({"task": a.task, "step": nxt["n"], "title": nxt["title"], "delegated_before": False,
              "next": f"do step {nxt['n']} yourself, or: ccx run --task {a.task} --step {nxt['n']} \"...\"",
              "brief": brief})
        return 0
    last = runs[-1]
    quota_out = last.get("kind") == "quota" and not a.same
    if quota_out:
        # the old session's agent is (probably) still out of quota: a fresh session on the other agent,
        # handed the checkpoint brief + the diff, instead of waiting
        from ..delegate import other
        to = other(last["to"], load_config(p))
        text = (f"Continue step {nxt['n']} ({nxt['title']}) of a task another agent started and was cut off "
                f"by its quota. Do not redo finished steps. Look at `git diff` for work already done.\n\n{brief}")
        if last.get("session_id") and last["to"] in ("claude", "codex"):
            # what the cut-off session itself had got to, read by code from its session file
            from .memory import transcript_handoff
            got = transcript_handoff(p, root, last["to"], last["session_id"], 3000, use_model=False)
            if got:
                text += "\n\n# Where the cut-off session stood\n" + got[1]
        req = Request(to=to, brief=text, tier="T2" if to != "gemini" else "T2", caller=_caller(a.caller),
                      cwd=root, task=a.task, step=nxt["n"], label=f"{a.task}#{nxt['n']}")
        rec = run(req, p)
        out = compact(rec) | {"handoff": f"{last['to']} -> {to} (quota)"}
    else:
        req = Request(to=last["to"], brief=f"Continue step {nxt['n']} ({nxt['title']}) from where you stopped. "
                      "Do not redo finished work.", resume_run=last["run_id"], caller=_caller(a.caller))
        rec = run(req, p)
        out = compact(rec) | {"resumed": last["run_id"]}
    _out(out)
    return 0 if rec["ok"] else 2


def cmd_verify(a) -> int:
    if a.sweep:
        from ..delegate import soft_verdicts
        done = soft_verdicts(paths(), a.after_h)
        _out({"recorded": done, "note": "probable verdicts from the evidence (soft); `ccx verify RUN --ok 0|1` "
              "overrides any of them"} if done else {"recorded": [], "note": "nothing old enough with clear evidence"})
        return 0
    if a.sample:
        import sys
        from ..verdicts import review_sample, sample_soft
        picks = sample_soft(paths(), a.sample, include_evals=a.include_evals)
        if not picks:
            _out({"sample": [], "note": "no probable verdict this week that nobody judged since"})
        elif sys.stdin.isatty() and not a.list:
            done = review_sample(paths(), picks)
            _out({"judged": done, "overturned": sum(d["overturned"] for d in done)})
        else:
            _out({"sample": picks, "how": "look at each, then `ccx verify RUN_ID --ok 1|0` (run this in a terminal "
                  "to answer one by one)"})
        return 0
    if a.dismiss:
        if not a.run_id or a.ok is not None:
            raise ValueError("--dismiss takes a run id and no --ok: the run counts neither way")
        from ..verdicts import dismiss
        _out(dismiss(paths(), a.run_id, a.note))
        return 0
    if a.ok is None:
        raise ValueError("give --ok 1 or --ok 0 (or --dismiss, --sweep, --sample N)")
    if a.builtin:
        from ..delegate import verify_builtin
        if a.b is None:
            raise ValueError("--builtin needs --b (the difficulty ccx route used)")
        _out(verify_builtin(paths(), a.builtin, a.b, bool(a.ok), a.agent_id, a.note))
        return 0
    if not a.run_id:
        raise ValueError("give a run id, or --builtin <rung> --b <b> for work your own sub-agent did")
    _out(verify(paths(), a.run_id, bool(a.ok), a.note, a.reason or ""))
    return 0


def cmd_plan(a) -> int:
    """Thin wrapper over the task-split skill (size / check / template / record / show)."""
    p = paths()
    sp = learn.module(p, "split")
    return int(sp.main(a.args) or 0)


def cmd_namecheck(a) -> int:
    """The static undefined-name check by hand: a run's changes (what fail mode ran), the working tree's changes
    since --base, or whole files. Exit 1 on a hit."""
    from .. import namecheck as nck
    from ..review import _git
    from ..workspace import run_snapshot
    if a.files:
        res: dict = {"hits": [], "files": 0}
        for f in a.files:
            try:
                data = Path(f).read_bytes()
            except OSError as e:
                res.setdefault("not_checked", []).append(f"{f}: {e.strerror or e}")
                continue
            res["files"] += 1
            hits, why = nck.check_source(data, f)
            res["hits"] += hits
            if why:
                res.setdefault("not_checked", []).append(f"{f}: {why}")
    elif a.run:
        p = paths()
        rec = ledger.load_run(p, a.run)
        res = nck.scan(Path(rec.get("cwd") or os.getcwd()), run_snapshot(p, rec))
    else:
        cwd = Path.cwd()
        top = _git(cwd, "rev-parse", "--show-toplevel").strip()
        if not top:
            print("ccx namecheck: not in a git repo; name the files to check", file=sys.stderr)
            return 2
        res = nck.scan(cwd, {"repo": top, "base": a.base, "untracked": []})
    for h in res["hits"]:
        print(nck.line(h))
    if a.json:
        _out(res)
    elif not res["hits"]:
        print(f"namecheck: no undefined names ({res['files']} file{'s' if res['files'] != 1 else ''})")
    return 1 if res["hits"] else 0


def cmd_resume(a) -> int:
    p = paths()
    from ..recover import sweep
    sweep(p)                            # closes it as interrupted first if its ccx process died mid-run
    req = Request(to="codex", brief=_brief(a), tier=a.tier, resume_run=a.run_id,
                  caller=_caller(a.caller), escalate=False if a.no_escalate else None,
                  model=a.model, effort=a.effort, budget_usd=a.budget, review=a.review, check=a.check,
                  namecheck=getattr(a, "namecheck", None))
    if a.check:                         # replaces the stored check (one that named a missing file, say)
        prev = ledger.load_run(p, a.run_id)
        req.check = _check_names_real_tests(a.check, Path(prev.get("cwd") or os.getcwd()))
    rec = run(req, p)
    res = compact(rec)
    res["recap"] = recap(rec, res)
    _out(res)
    return 0 if res["ok"] else 2


def cmd_stop(a) -> int:
    from ..stop import stop
    out = stop(paths(), a.run_id, wait=a.wait)
    _out(out)
    return 0 if out.get("stopped") or out.get("requested") else 2


def cmd_batch(a) -> int:
    """plan.json: {"tasks":[{"id", "brief", "to"?, "mode"?, "cwd"?, "tier"? | "model"+"effort"? |
    rubric keys ("files","coupling","clarity","risk","novelty")?, "minutes"?, "task"?, "step"?, "check"?,
    "review"? (auto|on|off, as `ccx run --review`)}]}"""
    p = paths()
    cfg = load_config(p)
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    caller = _caller(a.caller)
    tasks = plan["tasks"]
    for t in tasks:
        apply_mode(t)                            # a task without "mode" gets it from its brief
    writers = [t for t in tasks if t["mode"] == "write"]

    def in_git(cwd: str | None) -> bool:
        import subprocess
        return subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd or os.getcwd(),
                              capture_output=True, stdin=subprocess.DEVNULL).returncode == 0
    reqs, skipped = [], []
    for t in tasks:
        kw, route = resolve(t, caller, p, cfg)
        if kw is None:
            skipped.append({"id": t.get("id"), "advice": route.get("advice")})
            continue
        reqs.append(Request(brief=t["brief"], mode=t["mode"], mode_source=t["mode_source"], mode_why=t["mode_why"],
                            check=t.get("check"), review=t.get("review", "auto"), risk=t.get("risk"),
                            cwd=Path(t.get("cwd") or os.getcwd()), caller=caller, label=t.get("id", ""),
                            task=t.get("task"), step=t.get("step"),
                            # parallel writers in one repo must not trample each other
                            # (outside git there is no worktree: they share the folder, so keep pieces disjoint)
                            worktree=t.get("worktree", len(writers) > 1 and t in writers
                                           and in_git(t.get("cwd"))), **kw))
    threads = int(cfg["defaults"].get("max_parallel", 3))
    n = lanes.width(getattr(a, "lanes", None), cfg)
    if n:
        # warm lanes (ccx/lanes.py): same project + agent + mode share at most n sessions, piece after piece
        lane_list = lanes.split(reqs, n, lambda r: (str(r.cwd.resolve()), r.to, r.provider, r.mode))
        for lane in lane_list:                   # a lane works in one folder: its first piece's worktree (if any)
            for r in lane[1:]:
                r.worktree = lane[0].worktree

        def step(r, warm):
            if warm:
                r.resume_run, r.continued = warm, True
            try:
                rec = run(r, p)
            except Exception as e:  # noqa: BLE001 — one piece's error must not stop its lane
                return {"label": r.label, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}, None
            return compact(rec), rec
        results = lanes.run_lanes(lane_list, step, lanes.limits(cfg), threads)
        _out({"results": results, "do_yourself": skipped, "lanes": len(lane_list)})
        return 0 if all(r["ok"] for r in results) else 2
    with ThreadPoolExecutor(max_workers=threads) as ex:
        results = list(ex.map(lambda r: compact(run(r, p)), reqs))
    _out({"results": results, "do_yourself": skipped})
    return 0 if all(r["ok"] for r in results) else 2


def cmd_quota(a) -> int:
    from .. import quota
    p = paths()
    extra = {}
    if a.backfill:
        extra["backfilled"] = quota.backfill(p)
    if a.probe:
        extra["probe_readings"] = quota.probe(p)
    pr = quota.pressure(p)
    lam = {}
    try:
        tr = learn.module(p, "routing")
        lam = {ag: round(tr.shadow_lambda(v), 2) for ag, v in pr["quota"].items()}
    except Exception:  # noqa: BLE001
        pass
    stops = quota.recent_stops(p)
    if stops:
        extra["recent_quota_stops"] = stops       # H2: why each was taken for a quota stop
    _out({"projected_at_reset": pr["quota"], "quota_price_share_of_api": lam, "windows": pr["pace"], **extra})
    return 0


def cmd_bench(a) -> int:
    """Thin wrapper over task_routing.py refresh / sources (the data lives next to the routing state)."""
    tr = learn.module(paths(), "routing")
    if not hasattr(tr, "bench"):
        raise ValueError("the installed task-routing skill is older than benchmark support: update it")
    b = tr.bench()
    if a.what == "refresh":
        _out(b.refresh(tr.bench_path(), plugin_dirs=tr.bench_plugin_dirs() if hasattr(tr, "bench_plugin_dirs") else ()))
    else:
        d = b.load(tr.bench_path())
        _out({"cache": str(tr.bench_path()), "age_days": b.age_days(tr.bench_path()), **b.summary(d)} if d
             else {"cache": str(tr.bench_path()), "empty": "run: ccx bench refresh"})
    return 0


def cmd_route(a) -> int:
    _out(_route(a))
    return 0


def _route(a) -> dict:
    p = paths()
    cfg = load_config(p)
    if a.coupling or a.clarity or a.risk or a.novelty or a.b is not None or a.minutes:
        spec = {"to": a.to, "files": a.files, "b": a.b, "coupling": a.coupling, "clarity": a.clarity,
                "risk": a.risk, "novelty": a.novelty, "tradeoff": a.tradeoff, "force": True,
                "minutes": a.minutes,
                "brief": " ".join(a.text or []), "mode": getattr(a, "mode", None), "kind": a.kind}
        mode = apply_mode(spec)
        kw, route = resolve(spec, _caller(None), p, cfg)
        route["mode"] = mode            # recommended read/write and why; routing priced the start-up with it
        if a.lead and route.get("rung"):
            ctx = a.ctx_tokens
            for f in a.ctx_files or []:        # rough: 4 bytes per token
                try:
                    ctx += Path(f).stat().st_size // 4
                except OSError:
                    pass
            # what each of your own turns re-reads: given, else your conversation's last request (J5/H10)
            lead_agent, lead_ctx, src = a.lead.split(":")[0], a.lead_ctx, "given"
            if lead_ctx is None:
                from .. import context
                from .common import lead_session_id
                lead_ctx = context.lead_now(lead_agent, lead_session_id(lead_agent))
                src = "none" if lead_ctx is None else "lead_session"
            lead_ctx = lead_ctx or 0
            route["self_vs_delegate"] = learn.self_vs_delegate(p, route["b"], a.lead, route["rung"], ctx,
                                                               a.turns_left, route["tradeoff"], lead_ctx)
            route["self_vs_delegate"].update(ctx_tokens=ctx, lead_ctx_tokens=lead_ctx, ctx_source=src)
            others = ((installed_agents() or list(DELEGATE_AGENTS)) + provider_agents(load_config(p))
                      if a.to == "auto" else [a.to])      # three_way holds pay-per-token agents back itself
            quota = parse_quota(a.quota)
            choice = learn.three_way(p, route["b"], a.lead, others, ctx, a.turns_left, route["tradeoff"],
                                     needs=tuple(x for x in (a.needs or "").split(",") if x), quota=quota,
                                     kind=learn.task_kind(mode["mode"], a.kind), risk=a.risk or "low",
                                     lead_ctx=lead_ctx)
            if choice:
                choice.update(lead_ctx_tokens=lead_ctx, ctx_source=src)
                route["choice"] = choice      # self / built-in sub-agent / ccx: see the agent-delegate skill
        return route
    r = router.classify(" ".join(a.text), a.files)
    t = cfg["tiers"][r.tier]
    out = r.as_dict() | {"label": t.get("label"), "when": t.get("when"),
                         "note": "keyword heuristic; give the rubric flags for a calibrated pick",
                         "mode": apply_mode({"brief": " ".join(a.text or []), "mode": getattr(a, "mode", None)})}
    for ag in AGENTS:
        if t.get(ag):
            out[ag] = t[ag]
    return out


def cmd_propose(a) -> int:
    """H12: estimate before offering to delegate, and record the offer and the person's answer."""
    from .. import proposals
    p = paths()
    if a.stats:
        _out(proposals.stats(p, a.days))
        return 0
    if a.no:
        _out(proposals.answer(p, a.no, False))
        return 0
    if not a.lead:
        raise ValueError("ccx propose needs --lead (your own rung, e.g. claude:opus:high) and the rubric or --minutes")
    route = _route(a)
    if "b" not in route:
        raise ValueError("ccx propose needs the rubric flags or --minutes, so the estimate has a difficulty")
    lead_agent = a.lead.split(":")[0]
    row = proposals.new(p, route, " ".join(a.text or []), lead_session_id(lead_agent))
    c = route.get("choice") or route.get("self_vs_delegate") or {}
    worth = (c.get("recommend") == "delegate")
    def usd(x):
        return "?" if x is None else (f"${x:.4f}" if x < 0.01 else f"${x:.2f}")
    odds = "odds unknown" if row["p"] is None else f"about {row['p']:.0%} likely to work"
    _out({"proposal": row["proposal"], "worth_offering": worth, "recommend": c.get("recommend"),
          "why": c.get("why"), "self_usd": row["self_usd"], "delegate_usd": row["delegate_usd"], "p": row["p"],
          "lead_ctx_tokens": row["lead_ctx_tokens"], "ctx_source": c.get("ctx_source"),
          "say": (f"This looks delegable: about {usd(row['delegate_usd'])} delegated vs {usd(row['self_usd'])} "
                  f"if I do it here, {odds}. Delegate it?") if worth else None,
          "next": (f"on yes: ccx run --proposal {row['proposal']} ... (no --no-ab), then ccx verify <run_id>; "
                   f"on no: ccx propose --no {row['proposal']}") if worth else
                  "not worth offering: do it yourself, nothing to ask"})
    return 0


def register(sub) -> None:
    r = sub.add_parser("run", help="delegate one task to the other agent")
    r.add_argument("brief", nargs="*", help="task text (or use --brief-file / stdin)")
    r.add_argument("--brief-file")
    r.add_argument("--to", choices=["auto", *DELEGATE_AGENTS, *PROVIDER_AGENTS], default="auto")
    r.add_argument("--from", dest="caller", choices=[*DELEGATE_AGENTS, *PROVIDER_AGENTS, "user"])
    r.add_argument("--provider", help="model API behind an agent CLI, e.g. deepseek (see [providers] in config)")
    r.add_argument("--bg", action="store_true", help="run detached; wait for it with `ccx show <run_id> --wait`")
    r.add_argument("--tier", choices=["auto", *TIER_ORDER], default="auto")
    r.add_argument("--mode", choices=["read", "write"],
                   help="read: analyse only; write: may edit files. Not given: inferred from the task text "
                        "(analysis verbs -> read, edit verbs -> write, unclear -> write)")
    r.add_argument("--cwd")
    r.add_argument("--project", help="run in a project from the catalog: its name, an alias or a sentence "
                                     "(`ccx where`); several fit -> an error listing them")
    r.add_argument("--rules-ok", action="store_true", help="with --project: you read the project's approval rules "
                                                          "ccx showed and they allow this task")
    r.add_argument("--autonomy", choices=["L0", "L1", "L2"], help="this run's autonomy level (default: the "
                   "project's, `ccx autonomy`): L0 proposes only, L1 stops before edits, L2 may merge a small branch")
    r.add_argument("--approved", action="store_true", help="the person said yes to this dispatch (passes an "
                   "L0/L1 stop; never a spending cap, approval rules or a merge into a protected branch)")
    _routing_args(r)
    r.add_argument("--model", help="explicit model (skips routing), e.g. gpt-6.1-sol or sonnet")
    r.add_argument("--effort", help="explicit reasoning effort: low|medium|high|xhigh|max")
    r.add_argument("--minutes", type=float, help="how long a skilled engineer would need, in minutes: the standard "
                   "difficulty unit (b = log2 minutes, blended 60/40 with the rubric); task-split learns from it too")
    r.add_argument("--task", help="task-checkpoint task id: the session id is saved into it at once")
    r.add_argument("--step", type=int, help="task-checkpoint step number")
    r.add_argument("--force", action="store_true", help="delegate even when routing says do it yourself/split")
    r.add_argument("--no-ab", action="store_true", help="never pick this task as an A/B self-run sample")
    r.add_argument("--proposal", help="the `ccx propose` id the person said yes to (H12)")
    r.add_argument("--mcp", action="store_true", help="Claude sub-agent: also load MCP tools (bigger start-up)")
    r.add_argument("--new", action="store_true", help="always a fresh sub-session (default: continue the last "
                   "one from this conversation, same folder and agent, if under 1 h old)")
    r.add_argument("--fork", action="store_true", help="Claude lead -> Claude sub only: start from a copy of "
                   "your whole conversation (full context, costs more per turn)")
    r.add_argument("--worktree", action="store_true", help="isolate write task in a git worktree")
    r.add_argument("--quota", action="append", metavar="AGENT=USED",
                   help="share of a subscription's quota already used (claude=0.8); from 70%% routing also "
                        "considers pay-per-token providers such as deepseek")
    r.add_argument("--seat", metavar="NAME", help="a named long-lived role (e.g. reviewer): its sub-session is "
                   "kept for a week and reused by the next --seat NAME task here; --new starts it over")
    r.add_argument("--check", metavar="CMD", help="acceptance command (e.g. 'python -m pytest -q tests/test_x.py'): "
                   "the sub-agent runs it before finishing, then ccx runs it again; a failure counts as a failure")
    r.add_argument("--allow-subagents", action="store_true", help="(the default) the sub-agent may use its own "
                   "sub-agents: one level, counted, stopped over the budget")
    r.add_argument("--no-subagents", action="store_true", help="the sub-agent may not start its own sub-agents "
                   "(same as --subagents off)")
    r.add_argument("--subagents", default="auto", metavar="auto|off|N", help="how many of its own at once: auto = "
                   "the tool's default, fewer when quota is tight (default); off; or a number")
    r.add_argument("--budget", type=float, metavar="USD", help="spending cap for its own sub-agents on this piece "
                   "(default [subagents] max_usd, $2); over it the run stops and can go on with ccx resume --budget")
    r.add_argument("--parallel", action="store_true", help="tell it explicitly to use sub-agents for independent "
                   "parts (done by itself when the brief lists 3 or more items)")
    r.add_argument("--review", choices=["auto", "on", "off"], default="auto", help="independent review of the diff "
                   "by another vendor's cheap model: auto = only when --risk is visible/critical, the sub-agent is "
                   "unsure, or its claimed files don't match the diff (default); on = every write run; off")
    r.add_argument("--namecheck", choices=["warn", "fail", "off"], help="static check for names no scope "
                   "defines in the functions the run changed: warn = shown to you and the reviewer (default, "
                   "[defaults] namecheck); fail = a hit fails the work like a failed --check; off")
    r.add_argument("--no-escalate", action="store_true")
    r.add_argument("--no-fallback", action="store_true", help="on quota/rate limit, stop instead of "
                   "retrying on the other agent")
    r.add_argument("--context", choices=["auto", "on", "off"], help="shared work context: attach what your "
                   "conversation has been about lately (the person's recent asks, what was settled, your plan, files "
                   "you changed), read by code from your session file. auto = write tasks only (default, "
                   "[shared_context] run)")
    r.add_argument("--label")
    r.set_defaults(fn=cmd_run)
    ak = sub.add_parser("ask", help="quick read-only second opinion from the other agent (low effort)")
    ak.add_argument("brief", nargs="*"); ak.add_argument("--brief-file")
    ak.add_argument("--to", choices=["auto", *DELEGATE_AGENTS, *PROVIDER_AGENTS], default="auto")
    ak.add_argument("--from", dest="caller", choices=[*DELEGATE_AGENTS, *PROVIDER_AGENTS, "user"]); ak.add_argument("--cwd")
    ak.set_defaults(fn=cmd_ask)
    tk = sub.add_parser("task", help="long tasks: status, or resume an interrupted one (task-checkpoint)")
    tks = tk.add_subparsers(dest="task_cmd", required=True)
    tst = tks.add_parser("status"); tst.add_argument("task", nargs="?")
    trs = tks.add_parser("resume"); trs.add_argument("task")
    trs.add_argument("--same", action="store_true", help="resume the same session even after a quota stop")
    trs.add_argument("--from", dest="caller", choices=[*DELEGATE_AGENTS, *PROVIDER_AGENTS, "user"])
    for x in (tst, trs):
        x.add_argument("--cwd")
    tk.set_defaults(fn=cmd_task)
    se = sub.add_parser("send", help="send a message into a live Codex desktop/interactive session")
    se.add_argument("message", nargs="*")
    # Codex only: `codex queue` is the one way in from outside. A Claude Code session (terminal or desktop app) has no
    # entrance for another program's message; a Claude sub-agent is followed up with `ccx resume <run_id>`
    se.add_argument("--to", choices=["codex"], default="codex",
                    help="codex (the only one: Claude sessions take no message from outside; use ccx resume)")
    se.add_argument("--thread", help="Codex thread id (see --list)")
    se.add_argument("--list", action="store_true", help="list live sessions (codex agents)")
    se.add_argument("--wait", type=int, default=120, help="seconds to wait for the conversation to go idle (120)")
    se.add_argument("--force", action="store_true", help="send even while you are working in that conversation")
    se.set_defaults(fn=cmd_send)
    v = sub.add_parser("verify", help="record your verdict on a run (calibrates routing and splitting)")
    v.add_argument("run_id", nargs="?")
    v.add_argument("--ok", type=int, choices=[0, 1])
    v.add_argument("--note", default="", help="why (kept with the verdict)")
    v.add_argument("--reason", choices=["unfinished", "wrong", "overreach", "other"],
                   help="with --ok 0: what was wrong (not finished / done wrong / changed what it shouldn't / other)")
    v.add_argument("--dismiss", action="store_true", help="a test, probe or leftover, not real work: it leaves "
                   "'waits for you', counts neither right nor wrong and is never learned from (a later --ok undoes it)")
    v.add_argument("--sweep", action="store_true", help="record 'probably right' for finished runs nobody judged "
                   "whose check or self-check passed and review (if any) passed (undone ones wait for you); also "
                   "runs quietly at session start. Your own verdict always overrides these")
    v.add_argument("--after-h", type=float, default=12.0, help="with --sweep: only runs at least this old (hours)")
    v.add_argument("--sample", type=int, metavar="N", help="spot-check N random probable verdicts of this week: shows "
                   "what changed and asks ok / wrong (J7: tells how far probable verdicts can be trusted)")
    v.add_argument("--include-evals", action="store_true", help="with --sample: evaluation runs too")
    v.add_argument("--list", action="store_true", help="with --sample: print the picks as JSON instead of asking")
    v.add_argument("--builtin", metavar="RUNG", help="work your own built-in sub-agent did, e.g. claude-builtin:haiku:low")
    v.add_argument("--b", type=float, help="with --builtin: the difficulty ccx route used")
    v.add_argument("--agent-id", help="with --builtin: the sub-agent's id, so its real cost is read and learned")
    v.set_defaults(fn=cmd_verify)
    pl = sub.add_parser("plan", help="task-split: size / check / template / record / show",
                        add_help=False)
    pl.add_argument("args", nargs=argparse.REMAINDER)
    pl.set_defaults(fn=cmd_plan)
    rs = sub.add_parser("resume", help="follow up in the same sub-session (cheap: keeps its context)")
    rs.add_argument("run_id")
    rs.add_argument("brief", nargs="*")
    rs.add_argument("--brief-file")
    rs.add_argument("--tier", choices=["auto", *TIER_ORDER], default="auto")
    rs.add_argument("--from", dest="caller", choices=[*DELEGATE_AGENTS, *PROVIDER_AGENTS, "user"])
    rs.add_argument("--no-escalate", action="store_true")
    rs.add_argument("--model")
    rs.add_argument("--effort")
    rs.add_argument("--budget", type=float, metavar="USD", help="a new spending cap for its own sub-agents (after "
                    "an over_budget stop)")
    rs.add_argument("--review", choices=["auto", "on", "off"], default="auto", help="independent review of what this "
                    "follow-up changed, as for ccx run (default auto)")
    rs.add_argument("--check", metavar="CMD", help="replace the run's acceptance command from here on (e.g. one "
                    "that named a missing file or ran no tests)")
    rs.add_argument("--namecheck", choices=["warn", "fail", "off"], help="static check for names no scope "
                    "defines in the functions the run changed: warn = shown to you and the reviewer (default, "
                    "[defaults] namecheck); fail = a hit fails the work like a failed --check; off")
    rs.set_defaults(fn=cmd_resume)
    nc = sub.add_parser("namecheck", help="static check for names no scope defines (NameError waiting to happen) "
                        "in changed Python functions; exit 1 on a hit")
    nc.add_argument("files", nargs="*", help="check these whole files instead of changed functions")
    nc.add_argument("--run", metavar="RUN_ID", help="the changes of that ccx run (what its namecheck saw)")
    nc.add_argument("--base", default="HEAD", help="without --run or files: changes since this commit "
                    "(default HEAD; untracked .py files count as new)")
    nc.add_argument("--json", action="store_true")
    nc.set_defaults(fn=cmd_namecheck)
    sp = sub.add_parser("stop", help="stop a running delegation (its whole process tree); `ccx resume` continues it")
    sp.add_argument("run_id")
    sp.add_argument("--wait", type=float, default=15.0, help="seconds to wait for the run to record the stop (15)")
    sp.set_defaults(fn=cmd_stop)
    b = sub.add_parser("batch", help="run independent tasks in parallel from plan.json")
    b.add_argument("plan")
    b.add_argument("--from", dest="caller", choices=[*DELEGATE_AGENTS, *PROVIDER_AGENTS, "user"])
    b.add_argument("--lanes", type=int, metavar="N", help="warm lanes: pieces for the same project and agent share "
                   "at most N sub-sessions, one piece after another (each still its own run, check and ledger row); "
                   "0 = every piece its own session (default: [lanes] default, 0)")
    b.set_defaults(fn=cmd_batch)
    ro = sub.add_parser("route", help="which agent/model/effort for a task (rubric -> task-routing)")
    ro.add_argument("text", nargs="*", help="the task description (used to recommend read or write)")
    ro.add_argument("--mode", choices=["read", "write"], help="explicit read/write (else inferred from the text)")
    ro.add_argument("--minutes", type=float, help="how long a skilled engineer would need (standard difficulty unit)")
    ro.add_argument("--to", choices=["auto", *DELEGATE_AGENTS, *PROVIDER_AGENTS], default="auto")
    _routing_args(ro)
    sv = ro.add_argument_group("self vs delegate (needs --lead)")
    sv.add_argument("--lead", help="your own rung, e.g. claude:opus:high")
    sv.add_argument("--ctx-files", nargs="*", help="files you would have to read yourself")
    sv.add_argument("--ctx-tokens", type=int, default=0, help="or the token count directly")
    sv.add_argument("--lead-ctx", type=int, help="tokens each of your requests re-reads (your conversation's size); "
                    "default: read from your conversation's last request")
    sv.add_argument("--turns-left", type=int, default=10, help="turns this session will still run")
    sv.add_argument("--needs", help="comma list that only a ccx run gives: undo,worktree,other-vendor,resume")
    sv.add_argument("--quota", action="append", metavar="AGENT=USED",
                    help="share of an agent's quota already used, e.g. claude=0.4 (Codex's is read automatically)")
    ro.set_defaults(fn=cmd_route)
    pr = sub.add_parser("propose", help="before offering to delegate a large, checkable task: the estimate, one "
                        "line to say, and a record of the offer (H12)")
    for act in ro._actions:                    # the same flags as `ccx route`
        if act.dest != "help":
            pr._add_action(act)
    pr.add_argument("--no", metavar="PROPOSAL", help="the person said no to this offer")
    pr.add_argument("--stats", action="store_true",
                    help="proposed -> agreed -> delegated -> judged, and the share of real runs with a verdict")
    pr.add_argument("--days", type=float, default=7.0)
    pr.set_defaults(fn=cmd_propose)
    bn = sub.add_parser("bench", help="public benchmark data for routing: refresh (weekly by itself) or show sources")
    bn.add_argument("what", choices=["sources", "refresh"], nargs="?", default="sources")
    bn.set_defaults(fn=cmd_bench)
    qu = sub.add_parser("quota", help="subscription quota by pace: projected use of each window at its reset")
    qu.add_argument("--probe", action="store_true", help="one tiny Claude request now, to read its windows")
    qu.add_argument("--backfill", action="store_true", help="read Claude windows from past run logs (once)")
    qu.set_defaults(fn=cmd_quota)
    ab = sub.add_parser("ab", help="close an A/B self-run sample")
    abs_ = ab.add_subparsers(dest="ab_cmd", required=True)
    abd = abs_.add_parser("done"); abd.add_argument("ab_id"); abd.add_argument("--ok", type=int, choices=[0, 1],
                                                                               required=True)
    ab.set_defaults(fn=cmd_ab)
