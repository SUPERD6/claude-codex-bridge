"""Run one sub-task on the other agent and hand back a compact result.

Token rules baked in here:
  * the brief is short and points at files; the sub-agent reads them itself
    (those tokens are billed to the *other* account, not the orchestrator);
  * project background lives in <repo>/.ccx/context.md, written once and
    read by every sub-agent, instead of being re-typed into each brief;
  * only a schema-checked JSON summary comes back to the orchestrator; the full
    event log stays on disk (ccx show <id> --full if really needed);
  * follow-ups resume the same sub-session instead of starting cold;
  * escalation resumes the same session with a stronger model;
  * the session id is saved the moment the sub-agent prints it, so a crash, a closed window or a quota
    cut mid-run still leaves something `ccx resume` can continue (and a task-checkpoint step, if given);
  * a quota/rate-limit stop falls back to the other agent once instead of failing the whole task;
  * every attempt is fed back to task-routing / task-split so their estimates calibrate themselves.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import learn, ledger
from .config import DELEGATE_AGENTS, Paths, load_config, provider_of
from .runners import BUILDERS, execute, usage_dict
# split out by job (J11); re-exported so `from ccx.delegate import ...` keeps working
from .agents.codex import _add_children, _codex_growth, _codex_seen, _codex_total  # noqa: F401
from .ledger import write_record as _write_record  # noqa: F401
from .plan import _fallback_plan, _plan, _provider_envs, _rung_spec, _usable, _within_budget, other  # noqa: F401
from .prompts import (CONTINUE, ESCALATE, FOLLOWUP, NEEDS_WRITE, POLICY_MARKERS, POLICY_RETRY, PROMPT,  # noqa: F401
                      SELFCHECK, SELFCHECK_CMD, _policy_rejections)
from .review import review_run as _review  # noqa: F401
from .verdicts import (REASONS, SOFT_AFTER_H, _hard_verdict, _soft_verdict, soft_verdicts, verify,  # noqa: F401
                       verify_builtin)
from .workspace import _git, make_worktree, run_check, undo, undo_snapshot  # noqa: F401

AGENTS = DELEGATE_AGENTS


@dataclass
class Request:
    to: str                   # codex | claude
    brief: str
    tier: str = "T2"
    mode: str = "write"       # write (default: sub-agents may edit) | read
    cwd: Path = Path.cwd()
    caller: str = "unknown"
    resume_run: str | None = None   # earlier ccx run id to continue
    worktree: bool = False
    escalate: bool | None = None
    label: str = ""
    model: str | None = None        # explicit model/effort (from task-routing or --model/--effort);
    effort: str | None = None       # when set, the escalation path comes from the routing ladder
    route: dict | None = None       # {b, rung, ladder, minutes, rubric, ...} — what learning needs
    fallback: bool = True           # on quota/rate limit, retry once on the other agent
    task: str | None = None         # task-checkpoint task id ...
    step: int | None = None         # ... and step this run belongs to
    provider: str | None = None     # e.g. deepseek: same agent CLI, another model API
    mcp: bool | None = None         # Claude sub-agent: load MCP tool definitions (default from config)
    continued: bool = False         # resume_run is a finished earlier task: reuse its session for a NEW task
    fork_lead: str | None = None    # Claude lead session id: the sub-agent starts as a fork of it (same tool only)
    ephemeral: bool = False         # one-shot (ask/selftest): nothing saved to the tools' session history
    check: str | None = None        # acceptance command: the sub-agent runs it, then ccx runs it again
    mode_source: str = "explicit"   # explicit | inferred | default (ccx/modes.py)
    mode_why: str = ""
    allow_subagents: bool = True    # the sub-agent may use its own sub-agents (one level, counted, capped: F9)
    lead_session: str | None = None # the lead conversation this run belongs to (for auto-continue)
    review: str = "auto"            # independent review by another vendor's cheap model: auto | on | off (F1)
    risk: str | None = None         # low | visible | critical (from the routing rubric): visible+ is reviewed
    review_round: int = 0           # 1 = this run fixes what a review found


def depth_guard(cfg: dict) -> None:
    depth = int(os.environ.get("CCX_DEPTH", "0") or 0)
    if depth >= int(cfg["defaults"].get("max_depth", 1)):
        raise PermissionError(
            "ccx: refusing to delegate from inside a sub-agent (CCX_DEPTH="
            f"{depth}). Do the work yourself or report it in open_questions.")


def _project_context(cwd: Path) -> Path | None:
    for d in [cwd, *cwd.parents]:
        f = d / ".ccx" / "context.md"
        if f.exists():
            return f
        if (d / ".git").exists():
            break
    return None


def claude_slim_flags(cfg: dict, mode: str, mcp: bool | None = None) -> list[str]:
    """Shrink a headless Claude start: fewer tool definitions, no MCP tool schemas unless wanted, and a
    system prompt that doesn't change per folder (so the prompt cache is reused across runs and projects)."""
    c = cfg.get("claude_subagent") or {}
    out = []
    tools = c.get("tools_read" if mode == "read" else "tools_write")
    if tools:
        out += ["--tools", tools]
    if c.get("exclude_dynamic", True):
        out.append("--exclude-dynamic-system-prompt-sections")
    if not (c.get("mcp", False) if mcp is None else mcp):
        out.append("--strict-mcp-config")
    if not c.get("skills", True):
        out.append("--disable-slash-commands")
    return out


class _Heartbeat:
    """While a sub-agent works on a task-checkpoint step, keep the task's heartbeat fresh, so a long run is
    not mistaken for an interrupted one (the checkpoint treats >10 min of silence as interrupted)."""
    def __init__(self, p: Paths, cwd: Path, task: str | None, agent: str):
        self.stop = None
        if not task:
            return
        import threading
        self.stop = threading.Event()
        every = float(os.environ.get("CCX_BEAT_SEC", "60"))
        try:
            cp = learn.module(p, "checkpoint")
            t = cp.Task(task, learn.cp_root(cwd))
        except Exception:  # noqa: BLE001
            self.stop = None
            return

        def loop():
            while not self.stop.wait(every):
                try:
                    t.beat(agent)
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=loop, daemon=True).start()

    def close(self):
        if self.stop:
            self.stop.set()


# Credentials the child would otherwise inherit from the caller (a Claude Code / desktop session hands its own
# login down). A provider run must send ONLY the provider's key to the provider's server.
HOST_AUTH = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN",
             "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH", "CLAUDE_CODE_MESSAGING_TOKEN",
             "USE_LOCAL_OAUTH", "USE_STAGING_OAUTH")


def _spend_watch(p: Paths, cfg: dict, cli: str, spec: dict, record: dict, since: float):
    """While a Codex sub-agent runs, what its own sub-agents have spent; a reason to stop once over the cap
    (`[subagents] max_usd`, default $2 API-equivalent per attempt)."""
    if cli != "codex":
        return None
    cap = float((cfg.get("subagents") or {}).get("max_usd", 2.0))

    def check():
        sid = record.get("session_id")
        if not sid:
            return None
        from .usage import codex_children
        usd = 0.0
        for tot in codex_children(sid, since - 5).values():
            usd += learn.price_usd(p, "codex", spec["model"], usage_dict(
                fresh=max(0, tot["input"] - tot["cached"]), cached=tot["cached"], out=tot["output"])) or 0.0
        if usd > cap:
            return (f"stopped: its own sub-agents spent ${usd:.2f} (cap ${cap:.2f}, [subagents] max_usd); "
                    f"split the work with `ccx q` instead")
        return None
    return check


def _child_env(to: str, run_id: str, extra: dict | None = None, provider: bool = False) -> dict:
    env = dict(os.environ)
    if provider:
        for k in HOST_AUTH:
            env.pop(k, None)
    env.update(extra or {})
    env["CCX_DEPTH"] = str(int(env.get("CCX_DEPTH", "0") or 0) + 1)
    env["CCX_ROLE"] = "subagent"
    env["CCX_PARENT_RUN"] = run_id
    if to == "claude":
        # When the caller itself runs inside Claude Code, these would tie the child
        # to the parent's session/effort. The child must be its own session.
        for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
                  "CLAUDE_EFFORT", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID"):
            env.pop(k, None)
    return env


def run(req: Request, p: Paths) -> dict:
    cfg = load_config(p)
    depth_guard(cfg)
    escalate = cfg["defaults"].get("auto_escalate", True) if req.escalate is None else req.escalate
    max_esc = int(cfg["defaults"].get("max_escalations", 1)) if escalate else 0
    timeout = int(cfg["defaults"].get("timeout_sec", 1800))

    prev = ledger.load_run(p, req.resume_run) if req.resume_run else None
    cont = bool(prev and req.continued)      # new task, old session: keep the new task's own settings
    if cont:
        req.to = prev["to"]
        req.cwd = Path(prev["cwd"])
        prev_for_settings = None
    else:
        prev_for_settings = prev
    if prev_for_settings:
        req.to = prev["to"]
        req.cwd = Path(prev["cwd"])
        req.mode = prev["mode"]
        req.route = req.route or prev.get("route")
        req.task, req.step = req.task or prev.get("task"), req.step or prev.get("step")
        req.provider = req.provider or prev.get("provider")
        last = (prev.get("attempts") or [{}])[-1]
        if not req.model and last.get("model"):
            req.model, req.effort = last["model"], last.get("effort")
        elif not req.model and prev.get("first_rung"):     # cut off before its first attempt was recorded
            _, req.model, req.effort = prev["first_rung"].split(":", 2)
        if req.tier == "auto":
            req.tier = prev.get("tier", "T2")

    run_id = os.environ.pop("CCX_RUN_ID", None) or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    run_dir = p.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cwd = req.cwd.resolve()
    if req.worktree and req.mode == "write" and not prev:
        cwd = make_worktree(cwd, run_id)

    ctx = _project_context(cwd)
    # "read-only" alone made gpt-6-luna/low answer once that it had no tool to read files (E8 run, 2026-10-24)
    mode_text = ("read-only: read files and run commands that change nothing (your shell tool works), but do not "
                 "modify files. If finishing really needs edits, do not make them: stop "
                 f"with status blocked and start the summary with {NEEDS_WRITE}: what you would change and why"
                 if req.mode == "read" else "you may edit files in the workspace; keep changes minimal and on-task")
    if not req.allow_subagents:
        # codex-cli 0.164 offers its multi_agent v2 tools (spawn_agent ...) even with both features disabled and
        # --ignore-user-config (checked 2026-10-24), so the rule has to be said; the spend watchdog stays as backstop
        mode_text += "; do not start sub-agents of your own (no spawn_agent / Agent tool)"
    selfcheck = SELFCHECK_CMD.format(check=req.check) if req.check else SELFCHECK
    if cont:
        first_prompt = CONTINUE.format(run_id=run_id, caller=req.caller, cwd=cwd, brief=req.brief.strip(),
                                       mode_text=mode_text, selfcheck=selfcheck)
    elif prev:
        first_prompt = FOLLOWUP.format(run_id=run_id, brief=req.brief)
    else:
        first_prompt = PROMPT.format(
            run_id=run_id, caller=req.caller, cwd=cwd, brief=req.brief.strip(),
            mode_text=mode_text, selfcheck=selfcheck,
            context_line=f"Project context (read first): {ctx}\n" if ctx else "",
            memory_line=(f"User background index (open only if the task needs it): {p.memory_index}\n"
                         if p.memory_index.exists() else ""),
        )
    (run_dir / "prompt.md").write_text(first_prompt, encoding="utf-8")

    if req.provider:
        req.to = req.provider                  # a provider is its own agent: own rungs, prices and learning
    elif provider_of(cfg, req.to):
        req.provider = req.to
    plan = [_usable(p, x) for x in _plan(req, p, cfg, max_esc)]
    pv_env = _provider_envs(cfg, plan)       # missing key for the first rung -> clear error before anything runs
    plan = _within_budget(p, cfg, plan)
    record = {
        "run_id": run_id, "label": req.label, "to": plan[0]["agent"], "caller": req.caller,
        "tier": plan[0].get("tier", "rung"), "start_tier": req.tier if not req.model else "rung",
        "mode": req.mode, "cwd": str(cwd), "session_id": prev.get("session_id") if prev else None,
        "resumed_from": req.resume_run, "attempts": [], "result": None, "ok": False,
        "state": "running", "error": None, "auth_problem": False, "kind": None,
        "route": req.route, "task": req.task, "step": req.step, "learned": None, "ts": time.time(),
        "provider": req.provider, "lead_session": req.lead_session, "continued": cont,
        "first_rung": plan[0]["rung"],
        "continue_depth": (int(prev.get("continue_depth", 0)) + 1) if cont else 0,
        "forked_from_lead": bool(req.fork_lead), "ephemeral": req.ephemeral,
        "mode_source": req.mode_source, "mode_why": req.mode_why,
    }
    _write_record(run_dir, record)          # visible to `ccx show` at once (background runs, crashes)
    if req.mode == "write" and (not prev or cont):
        snap = undo_snapshot(cwd)
        if snap:
            (run_dir / "undo.json").write_text(json.dumps(snap), encoding="utf-8")
    if req.task and req.step:
        learn.checkpoint(p, cwd, "start", req.task, str(req.step), "--agent", plan[0]["agent"])

    def on_session(sid: str) -> None:
        record["session_id"] = sid
        _write_record(run_dir, record)       # crash from here on -> `ccx resume <run_id>` still works
        if req.task and req.step:
            learn.checkpoint(p, cwd, "session", req.task, str(req.step), sid)

    session = record["session_id"]
    seen = _codex_seen(prev)          # Codex session -> running usage total already counted
    kids = dict((prev or {}).get("codex_children") or {})   # child sessions it spawned -> totals counted
    record["codex_children"] = kids
    prompt, i, fell_back, swaps, policy_retried = first_prompt, 0, False, 0, False
    oc = None
    while i < len(plan):
        spec = plan[i]
        to = spec["agent"]
        record["to"] = to
        cli, extra = pv_env.get(to, (to, {}))       # a provider agent runs on another agent's CLI
        perm = list(cfg["permissions"][cli][req.mode])
        if cli == "claude" and req.check and "--allowed-tools" in perm:
            # the acceptance command itself must be runnable, whatever its spelling (a full python.exe path is not
            # covered by Bash(python:*); found in the F1 live trial, 2026-10-24)
            k = perm.index("--allowed-tools") + 1
            perm[k] = f"{perm[k]} Bash({req.check})"
        resume_id = session
        forking = to == "claude" and req.fork_lead and not session and i == 0
        if forking:
            # start from a copy of the lead's own conversation: full context, original lead untouched.
            # No slim flags: the less the prompt differs from the lead's, the more of its cache is reused.
            resume_id = req.fork_lead
            perm += ["--fork-session"]
        elif cli == "claude":
            perm += claude_slim_flags(cfg, req.mode, req.mcp)
        if req.ephemeral:
            perm += {"claude": ["--no-session-persistence"], "codex": ["--ephemeral"]}.get(cli, [])
        if not req.allow_subagents:
            # --no-subagents: no agents of their own. The slim Claude start has no Agent tool anyway.
            if cli == "codex":
                perm += ["--disable", "multi_agent", "--disable", "multi_agent_v2"]   # v2 tools stay in 0.164: see mode_text
            elif forking:
                perm += ["--disallowed-tools", "Agent"]
        elif cli == "codex":
            # its own sub-agents run on the rung routing picked, a few at a time (config keys from the Codex config
            # reference, read 2026-10-24); their tokens are added to this attempt and watched against a cap
            sub = cfg.get("subagents") or {}
            perm += ["-c", f"agents.max_concurrent_threads_per_session={int(sub.get('max_threads', 3))}",
                     "-c", f'agents.default_subagent_model="{spec["model"]}"',
                     "-c", f'agents.default_subagent_reasoning_effort="{spec["effort"]}"']
        if extra and cli == "claude":
            # --bare: auth is strictly ANTHROPIC_API_KEY, OAuth and keychain are never read (claude 2.1.309 --help),
            # so the caller's Claude login can't reach the provider's server
            perm += ["--bare"]
        inv = BUILDERS[cli](model=spec["model"], effort=spec["effort"], perm=perm, cwd=cwd,
                           prompt=prompt, run_dir=run_dir, resume_id=resume_id, lean=spec["lean"])
        t0 = time.time()
        hb = _Heartbeat(p, cwd, req.task if req.step else None, cli)
        try:
            oc, so, se = execute(cli, inv, timeout, _child_env(cli, run_id, extra, provider=bool(extra)),
                                 on_session=on_session, watch=_spend_watch(p, cfg, cli, spec, record, t0)
                                 if req.allow_subagents else None,
                                 watch_every=float((cfg.get("subagents") or {}).get("watch_every_sec", 20)))
        finally:
            hb.close()
        dt = round(time.time() - t0, 1)
        n = len(record["attempts"])
        (run_dir / f"events.{n}.log").write_text(so, encoding="utf-8")
        if cli == "claude" and not extra and "rate_limit_event" in so:
            try:                       # Claude's quota windows only show up here: keep them for pacing
                from . import quota
                quota.save_claude(p, [json.loads(x) for x in so.splitlines() if '"rate_limit_event"' in x])
            except Exception:  # noqa: BLE001
                pass
        if se:
            (run_dir / f"stderr.{n}.log").write_text(se, encoding="utf-8")
        session = oc.session_id or session
        codex_total = None
        if cli == "codex" and oc.usage:
            codex_total = _codex_total(oc.usage)
            if resume_id and resume_id in seen:
                oc.usage = _codex_growth(codex_total, seen[resume_id])
            if oc.session_id:
                seen[oc.session_id] = codex_total
                oc.usage = _add_children(oc.usage, oc.session_id, t0, kids)
        ae = learn.price_usd(p, to, spec["model"], oc.usage, ts=t0) if oc.usage else None
        record["attempts"].append({
            "agent": to, "tier": spec.get("tier"), "rung": spec["rung"], "model": spec["model"],
            "effort": spec["effort"], "ok": oc.ok, "kind": oc.kind, "seconds": dt, "usage": oc.usage,
            # through a provider the CLI still prices with its own vendor's table: only ccx's price is right
            "cost_usd": None if extra else oc.cost_usd, "ae_usd": round(ae, 6) if ae is not None else None,
            "error": oc.error, "auth_problem": oc.auth_problem, "retry_after": oc.retry_after,
            "session_id": oc.session_id, "substituted_for": spec.get("substituted_for"),
            **({"codex_total": codex_total} if codex_total else {})})
        record["session_id"] = session
        record["tier"] = spec.get("tier", "rung")
        _write_record(run_dir, record)
        status = (oc.result or {}).get("status")

        if status == "blocked" and ((oc.result or {}).get("summary") or "").lstrip().upper().startswith("SPLIT"):
            # a proposal to split (ccx queue): the lead's queue takes the parts; no escalation, nothing to learn
            oc.kind = "split"
            record["attempts"][-1]["kind"] = "split"
            break
        if req.mode == "read" and status == "blocked" and                 ((oc.result or {}).get("summary") or "").lstrip().upper().startswith(NEEDS_WRITE):
            # not a lack of ability: a stronger read-only model can't do it either. Back to the lead.
            oc.kind = "needs_write"
            record["attempts"][-1]["kind"] = "needs_write"
            break
        rejected = _policy_rejections(se) if status == "blocked" else []
        if rejected:
            # the sandbox, not the model, stopped it: says nothing about ability, and a stronger model won't help
            record["attempts"][-1]["kind"] = "policy"
            _write_record(run_dir, record)
            if not policy_retried and session:
                policy_retried = True
                prompt = POLICY_RETRY.format(run_id=run_id, rejected="\n".join(rejected))
                continue                          # same rung, same session
        if oc.kind == "quota" and req.fallback and not fell_back and (not prev or cont):
            fb = _fallback_plan(req, p, cfg, spec)
            if fb:
                fell_back = True
                plan = plan[:i + 1] + [fb]
                prompt, session = first_prompt, None      # fresh session on the other agent
                i += 1
                continue
        if oc.kind == "model" and swaps < 2:
            # this account can't use the model: remember it, move to the cheapest usable model at least as able.
            # Fresh session (the failed one holds nothing), and drop later rungs on the same model.
            try:
                learn.mark_unavailable(p, to, spec["model"])
                sub = learn.substitute(p, to, spec["model"], spec["effort"])
            except Exception:  # noqa: BLE001
                sub = None
            if sub:
                swaps += 1
                new = _rung_spec(f"{to}:{sub[0]}:{sub[1]}")
                new["substituted_for"] = spec["rung"]
                plan = plan[:i + 1] + [new] + [x for x in plan[i + 1:] if x["model"] != spec["model"]]
                prompt, session = first_prompt, None
                i += 1
                continue
        stuck = (not oc.ok and oc.kind == "error") or status in ("blocked", "failed")
        if stuck and i + 1 < len(plan) and plan[i + 1]["agent"] == to and session and not oc.auth_problem:
            prompt = ESCALATE.format(run_id=run_id, status=status or "error",
                                     summary=((oc.result or {}).get("summary") or oc.error or "")[:400])
            i += 1
            continue
        if stuck and i + 1 < len(plan) and plan[i + 1]["agent"] != to and not oc.auth_problem:
            # the ladder goes on on another agent (e.g. DeepSeek -> Claude): its own fresh session, the same brief
            prompt, session = first_prompt, None
            i += 1
            continue
        break

    status = (oc.result or {}).get("status")
    record.update(result=oc.result, ok=oc.ok, error=None if oc.ok else oc.error,
                  auth_problem=oc.auth_problem, kind=oc.kind, state="finished")
    check_passed = None
    if req.check and oc.ok and status in ("done", "partial"):
        record["check"] = run_check(req.check, cwd, int(cfg["defaults"].get("check_timeout_sec", 900)))
        check_passed = record["check"]["passed"]
        if not check_passed:
            # the sub-agent said it was done; the check says otherwise: that's a failure, and it is learned as one
            record["kind"] = "check_failed"
    if (req.mode == "write" and req.review != "off" and not req.ephemeral and oc.ok and status in ("done", "partial")
            and record.get("kind") != "check_failed"):
        try:
            _review(req, p, cfg, record, cwd, run_dir)
        except Exception as e:  # noqa: BLE001 — a review that can't run never fails the work itself
            record["review"] = {"verdict": "not-run", "error": f"{type(e).__name__}: {e}"[:200]}
    if req.task and req.step:
        if oc.kind in ("quota", "timeout"):
            args = ["fail", req.task, str(req.step), "--reason", "quota" if oc.kind == "quota" else "error",
                    "--note", f"ccx run {run_id}: {oc.kind}; resume with `ccx resume {run_id}`"]
            if oc.retry_after:
                args += ["--retry-after", str(oc.retry_after)]
            learn.checkpoint(p, cwd, *args)
        elif not oc.ok or status in ("blocked", "failed"):
            learn.checkpoint(p, cwd, "fail", req.task, str(req.step), "--reason",
                             "blocked" if status == "blocked" else "error", "--note", f"ccx run {run_id}")
        else:
            learn.checkpoint(p, cwd, "note", req.task, f"ccx run {run_id} returned {status}; verify, then"
                             f" `ccx verify {run_id} --ok 1|0`", "--step", str(req.step))
    # provisional learning: a definite failure, or a success the sub-agent itself checked.
    # `ccx verify` (the lead's verdict) adds or corrects this later.
    verified = check_passed is not None or (oc.result or {}).get("verification", "not-run") not in ("", "not-run")
    if oc.kind not in ("quota", "auth", "timeout", "model", "needs_write", "split", "over_budget",
                       "review_issues", "review_failed") and (status in ("blocked", "failed") or not oc.ok
                                                        or (status == "done" and verified)):
        try:
            learn.record_outcomes(p, record, final_ok=oc.ok and status == "done" and check_passed is not False)
            record["learned"] = "auto" if (record.get("route") or {}).get("b") is not None else None
        except Exception:  # noqa: BLE001 — learning is best effort
            pass
    _write_record(run_dir, record)
    ledger.append(p, record)
    if record.get("kind") == "review_issues" and record.get("session_id"):
        # hand the problems back to the same sub-session once; its fix is reviewed again (review_round 1)
        issues = "\n".join(f"- {x}" for x in record["review"]["issues"]) or record["review"]["summary"]
        fix = run(Request(to=req.to, brief=f"An independent review of your change found problems:\n{issues}\n"
                          "Fix the real ones (say which you think are wrong and why), run the checks again.",
                          resume_run=run_id, caller=req.caller, cwd=req.cwd, review="on", risk=req.risk,
                          review_round=1, check=req.check, fallback=False, task=req.task, step=req.step,
                          label=req.label), p)
        fix["review_of"], fix["first_review"] = run_id, record["review"]
        _write_record(p.runs / fix["run_id"], fix)
        return fix
    return record


def compact(record: dict) -> dict:
    """What the orchestrator actually reads. Keep it small."""
    r = record.get("result") or {}
    tok = ledger.sum_usage(record["attempts"])
    last = (record.get("attempts") or [{}])[-1]
    out = {
        "run_id": record["run_id"], "agent": record["to"], "tier": record["tier"],
        "model": f"{last.get('model')}/{last.get('effort')}",
        "ok": record["ok"],
        "status": r.get("status") or ("running" if record.get("state") == "running" else "error"),
        "summary": r.get("summary") or record.get("error"),
        "files_changed": r.get("files_changed", []),
        "verification": r.get("verification", "not-run"),
        "open_questions": r.get("open_questions", []),
        "next_step": r.get("next_step", ""),
        "tokens": tok,
    }
    atts = record["attempts"]
    chain = [a.get("tier") or a.get("rung") or "?" for k, a in enumerate(atts)   # a policy retry stays on its rung
             if not (k and atts[k - 1].get("kind") == "policy" and atts[k - 1]["rung"] == a["rung"])]
    if len(chain) > 1:
        out["escalated"] = " -> ".join(chain)
    blocked = sum(a.get("kind") == "policy" for a in record["attempts"])
    if blocked:
        out["policy_blocked"] = blocked
    if record.get("kind") and record["kind"] != "ok":
        out["kind"] = record["kind"]
        if record["kind"] == "over_budget":
            out["hint"] = (record.get("error") or "stopped over the sub-agent spending cap") +                 f"; what it did so far: `ccx show {record['run_id']} --full`"
        if record["kind"] == "check_failed":
            out["hint"] = (f"the sub-agent reported done, but the check failed (exit {record['check']['exit']}); "
                           f"see `ccx show {record['run_id']} --full`, or continue: ccx resume {record['run_id']} "
                           f"\"the check fails: fix it\"")
        if record["kind"] == "needs_write":
            out["hint"] = ("read-only run: the sub-agent says it needs to edit files (see summary). If you agree, "
                           f"run it again with --mode write")
        if record["kind"] in ("quota", "timeout"):
            out["hint"] = f"stopped by {record['kind']}; continue later with `ccx resume {record['run_id']}`"
            ra = last.get("retry_after")
            if ra:
                out["retry_after"] = ra
    if record.get("review"):
        rv = record["review"]
        out["review"] = {k: rv[k] for k in ("verdict", "reason", "by", "issues", "notes", "usd", "error")
                         if rv.get(k)}
    if record.get("first_review"):
        out.setdefault("review", {})["first_round"] = {k: record["first_review"].get(k) for k in ("verdict", "issues")}
        out["fixed_after_review_of"] = record["review_of"]
    if record.get("kind") == "review_failed":
        out["hint"] = ("an independent review still finds problems after one fix round (review.issues): decide "
                       f"yourself, or `ccx resume {record['run_id']} \"...\"`")
    if record.get("check"):
        c = record["check"]
        out["check"] = {"cmd": c["cmd"], "passed": c["passed"], "exit": c["exit"]}
    if record["cwd"] and "/.ccx-worktrees/" in record["cwd"].replace("\\", "/"):
        out["worktree"] = record["cwd"]
    if record.get("auth_problem"):
        out["hint"] = f"{record['to']} looks logged out: run `{record['to']} login` on this machine."
    return out
