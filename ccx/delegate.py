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
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import agents, context_share, learn, ledger, recover, subagents
from .config import DELEGATE_AGENTS, Paths, load_config, provider_of
from .runners import BUILDERS, Outcome, execute, usage_dict
# split out by job (J11); re-exported so `from ccx.delegate import ...` keeps working
from .agents.codex import _add_children, _codex_growth, _codex_seen, _codex_total  # noqa: F401
from .ledger import write_record as _write_record  # noqa: F401
from .plan import _fallback_plan, _plan, _provider_envs, _rung_spec, _usable, _within_budget, other  # noqa: F401
from .prompts import (CONTINUE, ESCALATE, FOLLOWUP, NEEDS_WRITE, POLICY_MARKERS, POLICY_RETRY, PROMPT,  # noqa: F401
                      REVIEW_CALLER, REVIEW_FINISH, REVIEW_PERMISSION, SELFCHECK, SELFCHECK_CMD, _policy_rejections)
from .review import review_run as _review  # noqa: F401
from .verdicts import (REASONS, SOFT_AFTER_H, _hard_verdict, _soft_verdict, soft_verdicts, verify,  # noqa: F401
                       verify_builtin)
from .workspace import _git, diffstat, make_worktree, run_check, run_snapshot, undo, undo_snapshot  # noqa: F401

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
    keep_session: bool = False      # ephemeral for ccx, but the tool keeps its session (a discuss turn resumed once)
    check: str | None = None        # acceptance command: the sub-agent runs it, then ccx runs it again
    mode_source: str = "explicit"   # explicit | inferred | default (ccx/modes.py)
    mode_why: str = ""
    allow_subagents: bool = True    # the sub-agent may use its own sub-agents (one level, counted, capped: F9)
    subagents: str = "auto"         # auto | off | N: how many of its own at once (F10; auto = the tool's default)
    budget_usd: float | None = None # this piece's spending cap for its own sub-agents (F11; else [subagents] max_usd)
    parallel: bool | None = None    # say "use sub-agents for the independent parts" (F14; None = when the brief lists parts)
    lead_session: str | None = None # the lead conversation this run belongs to (for auto-continue)
    review: str = "auto"            # independent review by another vendor's cheap model: auto | on | off (F1)
    risk: str | None = None         # low | visible | critical (from the routing rubric): visible+ is reviewed
    review_round: int = 0           # 1 = this run fixes what a review found
    share_context: str | None = None  # auto | on | off: the lead's recent work, from its session file (context_share)


def _busy(p: Paths, prev: dict, scan: int = 300) -> str | None:
    """A run still alive in prev's session (prev itself, or a fix round / resume of it). Round 5: a lead's Bash call
    timed out during ccx's review fix round, the lead resumed the same session meanwhile, and Codex refused."""
    from .runners import pid_alive
    sid, rid = prev.get("session_id"), prev.get("run_id")
    try:
        dirs = sorted((d for d in p.runs.iterdir() if d.is_dir()), reverse=True)[:scan]
    except OSError:
        return None
    for d in dirs:
        try:
            rec = ledger.read_record(d / "run.json") or {}
        except (OSError, ValueError):            # no record yet, or one being replaced
            continue
        if rec.get("state") != "running" or rec.get("ccx_pid") == os.getpid():
            continue
        same = d.name == rid or (sid and rec.get("session_id") == sid) or rec.get("resumed_from") == rid
        if same and pid_alive(rec.get("ccx_pid")):
            return rec.get("run_id") or d.name
    return None


def _start_review(req: Request, p: Paths, cfg: dict, record: dict, cwd: Path, run_dir: Path, result: dict | None) -> dict:
    """Start the independent review in a thread while ccx runs the check. It works on a copy of the record whose
    check is the command as if it passed (what the review is told when its verdict counts at all), so the check's
    own result never races with it."""
    from .workspace import _check_doubt
    shadow = dict(record, result=result)
    shadow["check"] = {"cmd": req.check, "passed": True, **_check_doubt(req.check, cwd)}
    cancel = threading.Event()

    def go() -> None:
        try:
            _review(req, p, cfg, shadow, cwd, run_dir, cancel=cancel)
        except Exception as e:  # noqa: BLE001 — a review that can't run never fails the work itself
            shadow["review"] = {"verdict": "not-run", "error": f"{type(e).__name__}: {e}"[:200]}

    t = threading.Thread(target=go, name=f"ccx-review-{record['run_id']}", daemon=True)
    t.start()
    return {"thread": t, "cancel": cancel, "shadow": shadow, "run_id": record["run_id"]}


def _stop_reviews(p: Paths, run_id: str, scan: int = 50) -> None:
    """Ask the review runs of `run_id` that are still going to stop (the same stop file `ccx stop` writes)."""
    try:
        dirs = sorted((d for d in p.runs.iterdir() if d.is_dir()), reverse=True)[:scan]
    except OSError:
        return
    for d in dirs:
        try:
            rec = ledger.read_record(d / "run.json") or {}
        except (OSError, ValueError):
            continue
        if rec.get("label") == f"review:{run_id}" and rec.get("state") == "running":
            try:
                (d / "stop.request").write_text("ccx: the check failed, this review is not needed",
                                                encoding="utf-8")
            except OSError:
                pass


def _finish_review(bg: dict, record: dict, p: Paths, keep: bool, wait: float = 120.0) -> None:
    """keep: the check passed (or was not run anew), so the review's outcome goes into the record. Otherwise the
    review is stopped and whatever it found is dropped, as when it never ran."""
    t, shadow = bg["thread"], bg["shadow"]
    if keep:
        t.join()
        for k in ("review", "edited_tests"):
            if k in shadow:
                record[k] = shadow[k]
        if shadow.get("kind") in ("review_issues", "review_failed"):
            record["kind"] = shadow["kind"]
        return
    bg["cancel"].set()
    end = time.time() + wait
    while t.is_alive() and time.time() < end:
        _stop_reviews(p, bg["run_id"])
        t.join(0.5)


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


def _brief_notes(p: Paths, cfg: dict, to: str, brief: str, cwd: Path) -> str:
    """I6: every sub-agent's brief carries the few shared notes the task is about. A sub-agent never sees the start
    hook's memory delta (`ccx mem delta` prints nothing under CCX_ROLE=subagent, and the hook moves the lead's
    cursor, not the sub-agent's), so with a hook or without, the brief is the only way hub notes reach it."""
    from . import memory
    try:
        notes = memory.for_brief(p, brief, project=cwd.name)
    except (KeyError, OSError, ValueError):
        return ""
    if not notes:
        return ""
    memory.mark_used(p, [e["seq"] for e in notes], by=to, project=cwd.name, via="brief")   # via brief: a sub-agent
    return "Shared notes that may bear on this task (facts recorded earlier; check before relying on them):\n" + \
        "".join(f"- #{e['seq']} ({e.get('topic')}): {e['text']}\n" for e in notes)


def claude_slim_flags(cfg: dict, mode: str, mcp: bool | None = None, agent_tool: bool = False) -> list[str]:
    """Shrink a headless Claude start: fewer tool definitions, no MCP tool schemas unless wanted, and a
    system prompt that doesn't change per folder (so the prompt cache is reused across runs and projects).
    `agent_tool`: a write run may use Claude's own sub-agents (F12; their spend is read while it runs)."""
    c = cfg.get("claude_subagent") or {}
    out = []
    tools = c.get("tools_read" if mode == "read" else "tools_write")
    if tools and agent_tool and mode != "read" and "Agent" not in tools.split(","):
        tools += ",Agent"
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
             "USE_LOCAL_OAUTH", "USE_STAGING_OAUTH", "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY")


def _spend_watch(p: Paths, cfg: dict, cli: str, spec: dict, record: dict, since: float,
                 budget: float | None = None, cwd: Path | None = None):
    """While a sub-agent runs, what its own sub-agents have spent; a reason to stop once over the cap: this
    piece's budget, else `[subagents] max_usd` (default $2 API-equivalent per attempt). Codex: its child session
    files; Claude: <session>/subagents/*.jsonl (F12)."""
    if cli not in ("codex", "claude"):
        return None
    cap = subagents.cap_usd(budget, cfg)
    where = "--budget" if budget is not None else "[subagents] max_usd"

    def check():
        sid = record.get("session_id")
        if not sid:
            return None
        usd = 0.0
        if cli == "codex":
            from .usage import codex_children
            for tot in codex_children(sid, since - 5).values():
                usd += learn.price_usd(p, "codex", spec["model"], usage_dict(
                    fresh=max(0, tot["input"] - tot["cached"]), cached=tot["cached"], out=tot["output"])) or 0.0
        else:
            for c in subagents.claude_children(sid, cwd or Path.cwd()):
                usd += learn.price_usd(p, "claude", c["model"] or spec["model"], c["usage"]) or 0.0
        if usd > cap:
            # 4 places below a cent: a $0.0001 cap read "spent $0.00 (cap $0.00)" in a real run (PR #30)
            def money(x: float) -> str:
                return f"${x:.4f}" if x < 0.01 else f"${x:.2f}"
            return (f"stopped: its own sub-agents spent {money(usd)} (cap {money(cap)}, {where}); add budget and "
                    f"continue with `ccx resume {record['run_id']} --budget <usd>`, or split it with `ccx q`")
        return None
    return check


def _vendor(name: str, cfg: dict) -> str | None:
    """Who makes the caller's model (deepseek for dsh or a DeepSeek provider); None for the person or ccx itself."""
    from . import agents
    if name in agents.NAMES or name in (cfg.get("providers") or {}):
        return agents.vendor(name, cfg)
    return None


def _provider_url(url: str | None) -> bool:
    """Is this ANTHROPIC_BASE_URL one of the configured providers' endpoints?"""
    if not url:
        return False
    provs = (load_config().get("providers") or {}).values()
    return any(str((pv.get("env") or {}).get("ANTHROPIC_BASE_URL") or "").rstrip("/") == url.rstrip("/")
               for pv in provs)


def _child_env(to: str, run_id: str, extra: dict | None = None, provider: bool = False) -> dict:
    env = dict(os.environ)
    if provider:
        for k in HOST_AUTH:
            env.pop(k, None)
    env.update(extra or {})
    for k in ("CCX_LEAD", "DSH_SESSION_ID"):    # who the lead is must not pass for the sub-agent's identity
        env.pop(k, None)
    if to == "claude" and not provider and _provider_url(env.get("ANTHROPIC_BASE_URL")):
        # the lead is Claude Code on a provider's model (DeepSeek): a Claude sub-agent must reach Anthropic, not
        # inherit the lead's endpoint and key
        for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)
    if to == "claude" and not provider:
        # a `claude --bare` lead (how Claude Code runs on a provider) passes CLAUDE_CODE_SIMPLE on to its commands; a
        # Claude sub-agent started with it is bare too, ignores the person's login and fails "Not logged in"
        # (real run, Claude Code 2.1.309, 2026-10-25)
        env.pop("CLAUDE_CODE_SIMPLE", None)
    agent_home = env.get("CCX_AGENT_HOME", "").strip()
    if agent_home and to in ("codex", "dsh"):
        # opt-in (an evaluation's clean room): a home of their own, so Codex does not load the person's
        # ~/.agents/skills (codex-cli 0.164.0 reads user skills from $HOME/.agents/skills; its login stays in
        # CODEX_HOME, dsh's in DSH_HOME)
        env["HOME"] = env["USERPROFILE"] = agent_home
    env["CCX_DEPTH"] = str(int(env.get("CCX_DEPTH", "0") or 0) + 1)
    env["CCX_ROLE"] = "subagent"
    env["CCX_PARENT_RUN"] = run_id
    if to == "claude":
        # When the caller itself runs inside Claude Code, these would tie the child
        # to the parent's session/effort. The child must be its own session. CLAUDE_CODE_EFFORT_LEVEL overrides
        # --effort (and "ultracode" there turns on dynamic workflows), so the routed effort would not apply.
        # CLAUDE_CODE_ENTRYPOINT would label the child's session file "claude-desktop"; without it a -p run
        # writes "sdk-cli", which is how a reading of real sessions tells a sub-run from a person's conversation.
        for k in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT",
                  "CLAUDE_EFFORT", "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID"):
            env.pop(k, None)
    return env


def run(req: Request, p: Paths) -> dict:
    cfg = load_config(p)
    depth_guard(cfg)
    if req.subagents == "off":
        req.allow_subagents = False
    escalate = cfg["defaults"].get("auto_escalate", True) if req.escalate is None else req.escalate
    max_esc = int(cfg["defaults"].get("max_escalations", 1)) if escalate else 0
    timeout = int(cfg["defaults"].get("timeout_sec", 1800))

    prev = ledger.load_run(p, req.resume_run) if req.resume_run else None
    busy = _busy(p, prev) if prev else None
    if busy:
        raise RuntimeError(
            f"run {busy} is still working in that session (its check, review or fix round included): wait for it "
            f"with `ccx show {busy} --wait`, or stop it with `ccx stop {busy}`, then resume. Starting another run "
            "in the same session now would fail (Codex: 'thread already has an active writer').")
    if prev and prev.get("session_id"):
        try:                               # archived after its run (or by hand): put it back before continuing it
            from . import archive
            archive.bring_back(p, prev["session_id"])
        except Exception:  # noqa: BLE001 — the resume itself then says what is wrong
            pass
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
        # the same task: a lead's `ccx resume` keeps its label (the queue finds a piece's runs by `q:<id>`), its
        # acceptance command (a fix nobody checks is no evidence) and its risk, as ccx's own review fix round does
        req.label = req.label or prev.get("label") or ""
        req.check = req.check or prev.get("check_cmd")
        req.risk = req.risk or prev.get("risk")
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
    if req.caller == REVIEW_CALLER:                   # the reviewer reads only: no builder's "run the tests" text
        mode_text = REVIEW_PERMISSION
    if not req.allow_subagents:
        # codex-cli 0.164 offers its multi_agent v2 tools (spawn_agent ...) even with both features disabled and
        # --ignore-user-config (checked 2026-10-24), so the rule has to be said; the spend watchdog stays as backstop
        mode_text += "; do not start sub-agents of your own (no spawn_agent / Agent tool)"
    selfcheck = (REVIEW_FINISH if req.caller == REVIEW_CALLER
                 else SELFCHECK_CMD.format(check=req.check) if req.check else SELFCHECK)
    brief = req.brief.strip()
    if req.allow_subagents and (req.parallel or (req.parallel is None and subagents.has_parts(brief))):
        brief += "\n\n" + subagents.PARALLEL          # F14: the explicit request Codex's own instructions wait for
    shared, shared_meta = "", None
    if (not prev or cont) and not req.fork_lead and context_share.wanted(req.share_context, cfg, req.mode):
        try:
            shared, shared_meta = context_share.for_run(p, cfg, req.caller, req.lead_session, req.cwd.resolve())
        except Exception as x:  # noqa: BLE001 — background for the sub-agent, never a reason to fail the run
            shared, shared_meta = "", {"source": None, "why": f"error: {x}"}
        if shared:
            (run_dir / "shared-context.md").write_text(shared, encoding="utf-8")
            brief += "\n\n" + shared
    if cont:
        first_prompt = CONTINUE.format(run_id=run_id, caller=req.caller, cwd=cwd, brief=brief,
                                       mode_text=mode_text, selfcheck=selfcheck)
    elif prev:
        first_prompt = FOLLOWUP.format(run_id=run_id, brief=req.brief)
    else:
        first_prompt = PROMPT.format(
            run_id=run_id, caller=req.caller, cwd=cwd, brief=brief,
            mode_text=mode_text, selfcheck=selfcheck,
            context_line=f"Project context (read first): {ctx}\n" if ctx else "",
            memory_line=(f"User background index (open only if the task needs it): {p.memory_index}\n"
                         if p.memory_index.exists() else "") + _brief_notes(p, cfg, req.to, brief, req.cwd.resolve()),
        )
    (run_dir / "prompt.md").write_text(first_prompt, encoding="utf-8")
    if not prev:
        # the person's own brief: `ccx task resume` restarts from it when the run was killed before its session began
        (run_dir / "brief.md").write_text(req.brief, encoding="utf-8")

    if req.provider:
        req.to = req.provider                  # a provider is its own agent: own rungs, prices and learning
    elif provider_of(cfg, req.to):
        req.provider = req.to
    plan = [_usable(p, x) for x in _plan(req, p, cfg, max_esc)]
    pv_env = _provider_envs(cfg, plan)       # missing key for the first rung -> clear error before anything runs
    plan = _within_budget(p, cfg, plan)
    record = {
        "run_id": run_id, "label": req.label, "to": plan[0]["agent"], "caller": req.caller,
        "caller_vendor": _vendor(req.caller, cfg),
        "tier": plan[0].get("tier", "rung"), "start_tier": req.tier if not req.model else "rung",
        "mode": req.mode, "cwd": str(cwd), "session_id": prev.get("session_id") if prev else None,
        "resumed_from": req.resume_run, "attempts": [], "result": None, "ok": False,
        "state": "running", "error": None, "auth_problem": False, "kind": None,
        "route": req.route, "task": req.task, "step": req.step, "learned": None, "ts": time.time(),
        "provider": req.provider, "lead_session": req.lead_session, "continued": cont,
        "first_rung": plan[0]["rung"],
        "continue_depth": (int(prev.get("continue_depth", 0)) + 1) if cont else 0,
        "forked_from_lead": bool(req.fork_lead), "ephemeral": req.ephemeral,
        "mode_source": req.mode_source, "mode_why": req.mode_why, "check_cmd": req.check, "risk": req.risk,
        "shared_context": shared_meta,
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
    oc, early_check, bg_review = None, None, None
    want_review = req.mode == "write" and req.review != "off" and not req.ephemeral
    stop_file = run_dir / "stop.request"         # written by `ccx stop <run_id>`

    def on_start(pid: int) -> None:
        # what `ccx stop` needs: the child's process tree, and whether this ccx process is still there to close it
        record.update(pid=pid, ccx_pid=os.getpid(), host=socket.gethostname(), child=Path(inv.argv[0]).name)
        _write_record(run_dir, record)

    beat = threading.Event()        # heartbeat: where the pid can't be checked (another machine), a stale one tells

    def _beat():
        while True:
            try:
                (run_dir / "beat").write_text(str(time.time()), encoding="utf-8")
            except OSError:
                pass
            if beat.wait(float(os.environ.get("CCX_BEAT_SEC", "60"))):
                return
    threading.Thread(target=_beat, daemon=True).start()

    while i < len(plan):
        if stop_file.exists():                    # stopped between attempts: start nothing more
            oc = Outcome(ok=False, kind="user_stopped", error="stopped by `ccx stop`") if not (oc and oc.ok) else oc
            break
        spec = plan[i]
        to = spec["agent"]
        record["to"] = to
        cli, extra = pv_env.get(to, (to, {}))       # a provider agent runs on another agent's CLI
        perm = list(cfg["permissions"][cli][req.mode])
        perm += [str(x) for x in (provider_of(cfg, to) or {}).get("args") or []]   # e.g. Codex's model provider
        run_env = agents.get(cli).run_env
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
            perm += claude_slim_flags(cfg, req.mode, req.mcp, agent_tool=req.allow_subagents and not extra)
        if req.ephemeral and not req.keep_session:
            perm += {"claude": ["--no-session-persistence"], "codex": ["--ephemeral"]}.get(cli, [])
        if not req.allow_subagents:
            # --no-subagents: no agents of their own. The slim Claude start has no Agent tool anyway.
            if cli == "codex":
                perm += ["--disable", "multi_agent", "--disable", "multi_agent_v2"]   # v2 tools stay in 0.164: see mode_text
            elif forking:
                perm += ["--disallowed-tools", "Agent"]
        elif cli == "codex" and extra:
            # through a provider, Codex's own sub-agents would ask for OpenAI's models on the provider's server; and
            # apps/plugins send every connector's full tool list there: ~210k extra input tokens per request with
            # DeepSeek (codex-cli 0.164, measured 2026-10-24: 219k with them, 10k without)
            perm += ["--disable", "multi_agent", "--disable", "multi_agent_v2", "--disable", "apps",
                     "--disable", "plugins"]
        elif cli == "codex":
            # F10/F13: how many at once and which model stay Codex's own choice; ccx narrows them only when the
            # lead gave a number or quota is tight (config keys from the Codex config reference, read 2026-10-24).
            # Their tokens are added to this attempt and watched against the cap either way.
            from .leadcost import LADDER
            sp = subagents.plan("codex", spec["model"], req.subagents, learn.known_quota(None, p), LADDER)
            record.setdefault("subagent_plan", sp)
            if sp["threads"]:
                perm += ["-c", f"agents.max_concurrent_threads_per_session={sp['threads']}"]
            if sp["model"]:
                perm += ["-c", f'agents.default_subagent_model="{sp["model"]}"']
        if extra and cli == "claude":
            # --bare: auth is strictly ANTHROPIC_API_KEY, OAuth and keychain are never read (claude 2.1.309 --help),
            # so the caller's Claude login can't reach the provider's server
            perm += ["--bare"]
        inv = BUILDERS[cli](model=spec["model"], effort=spec["effort"], perm=perm, cwd=cwd,
                           prompt=prompt, run_dir=run_dir, resume_id=resume_id, lean=spec["lean"])
        t0 = time.time()
        # the attempt in flight: if this process dies, `ccx stop` / the sweep turn it into an attempt (ccx/recover.py)
        record["current"] = {"n": len(record["attempts"]), "agent": to, "cli": cli, "tier": spec.get("tier"),
                             "rung": spec["rung"], "model": spec["model"], "effort": spec["effort"], "t0": t0,
                             "before": seen.get(resume_id) if cli == "codex" else None}
        hb = _Heartbeat(p, cwd, req.task if req.step else None, cli)
        try:
            env = {**extra, **(run_env(req.mode) if run_env else {})}
            oc, so, se = execute(cli, inv, timeout, _child_env(cli, run_id, env, provider=bool(extra)),
                                 on_session=on_session, watch=_spend_watch(p, cfg, cli, spec, record, t0,
                                                                           req.budget_usd, cwd)
                                 if req.allow_subagents else None,
                                 watch_every=float((cfg.get("subagents") or {}).get("watch_every_sec", 20)),
                                 on_start=on_start, stop_file=stop_file)
        except BaseException:
            # Ctrl+C or a crash in ccx itself (execute has killed the tree): count what was spent, keep it resumable
            hb.close()
            beat.set()
            try:
                recover.close_dead(p, run_id, "killed", "interrupted",
                                   f"ccx itself was interrupted; continue with `ccx resume {run_id}`", "run")
            except Exception:  # noqa: BLE001 — never hide the original exception
                pass
            raise
        finally:
            hb.close()
        dt = round(time.time() - t0, 1)
        recovered = None
        if oc.kind in ("timeout", "over_budget", "user_stopped") and not any((oc.usage or {}).values()):
            # killed before its final usage line: read back what it spent (Claude's stream, Codex's session file)
            sid = oc.session_id or session
            recovered = recover.partial_usage(cli, sid, so, cwd, since=t0, before=seen.get(sid))
            oc.usage = recovered[0] or oc.usage
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
        if recovered and cli == "codex":
            codex_total = recovered[1]          # already this attempt's own usage; remember the running total
            if codex_total and oc.session_id:
                seen[oc.session_id] = codex_total
        elif cli == "codex" and oc.usage:
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
            **({"recovered": True} if recovered and oc.usage else {}),
            **({"codex_total": codex_total} if codex_total else {})})
        record["session_id"] = session
        record["tier"] = spec.get("tier", "rung")
        _write_record(run_dir, record)
        if oc.kind == "quota":
            try:                       # H2: what made this a quota stop, kept to check the call later
                from . import quota
                quota.log_stop(p, run_id, record["attempts"][-1], quota.stop_evidence(cli, so, se, oc.error))
            except Exception:  # noqa: BLE001 — evidence is best effort
                pass
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
        if (req.check and oc.ok and status in ("done", "partial") and i + 1 < len(plan) and not oc.auth_problem):
            # "done" but ccx's own run of the check fails: that is a failure too, so climb while a rung is left.
            # Before, only blocked/failed escalated, and a cheap model that wrongly said done stopped there
            # (needed once tradeoff = save picks cheap models first, 2026-10-25)
            if want_review:                    # reviewed while the check runs; dropped if the check fails
                bg_review = _start_review(req, p, cfg, record, cwd, run_dir, oc.result)
            chk = run_check(req.check, cwd, int(cfg["defaults"].get("check_timeout_sec", 900)))
            early_check = (len(record["attempts"]), chk)
            if not chk["passed"] and not chk.get("broken"):   # a broken check is no reason to climb
                if bg_review is not None:
                    _finish_review(bg_review, record, p, keep=False)
                    bg_review = None
                record["attempts"][-1]["kind"] = "check_failed"
                _write_record(run_dir, record)
                summary = f"you said done, but `{chk['cmd']}` failed (exit {chk['exit']}):\n{chk['tail'][-400:]}"
                if plan[i + 1]["agent"] == to and session:
                    prompt = ESCALATE.format(run_id=run_id, status="check_failed", summary=summary)
                else:
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
                  auth_problem=oc.auth_problem, kind=oc.kind,
                  state="stopped" if oc.kind == "user_stopped" else "finished")
    if stop_file.exists():
        record["stop_requested"] = True
    check_passed = None
    want_review = want_review and oc.ok and status in ("done", "partial")
    if bg_review is not None and not (want_review and early_check and early_check[0] == len(record["attempts"])):
        _finish_review(bg_review, record, p, keep=False)         # not this attempt's (cannot happen; be safe)
        bg_review = None
    if req.check and oc.ok and status in ("done", "partial"):
        reuse = early_check and early_check[0] == len(record["attempts"])    # already run on this very attempt
        if not reuse and want_review and bg_review is None:
            # the review runs while ccx runs the check (it needs only the command, not its result); it counts
            # only if the check passes, and is stopped otherwise
            bg_review = _start_review(req, p, cfg, record, cwd, run_dir, oc.result)
        record["check"] = early_check[1] if reuse else run_check(req.check, cwd,
                                                                 int(cfg["defaults"].get("check_timeout_sec", 900)))
        check_passed = record["check"]["passed"]
        if record["check"].get("broken"):
            # the command tested nothing (pytest exit 4/5): no verdict on the work, the lead fixes the check
            record["kind"], check_passed = "check_broken", None
        elif not check_passed:
            # the sub-agent said it was done; the check says otherwise: that's a failure, and it is learned as one
            record["kind"] = "check_failed"
    if bg_review is not None:
        _finish_review(bg_review, record, p, keep=record.get("kind") not in ("check_failed", "check_broken"))
    elif want_review and record.get("kind") not in ("check_failed", "check_broken"):
        try:
            _review(req, p, cfg, record, cwd, run_dir)
        except Exception as e:  # noqa: BLE001 — a review that can't run never fails the work itself
            record["review"] = {"verdict": "not-run", "error": f"{type(e).__name__}: {e}"[:200]}
    if req.task and req.step:
        if oc.kind in ("quota", "timeout", "user_stopped"):
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
    if oc.kind not in ("quota", "auth", "timeout", "model", "needs_write", "split", "over_budget", "user_stopped",
                       "review_issues", "review_failed") and record.get("kind") != "check_broken" and (status in ("blocked", "failed") or not oc.ok
                                                        or (status == "done" and verified)):
        try:
            learn.record_outcomes(p, record, final_ok=oc.ok and status == "done" and check_passed is not False)
            record["learned"] = "auto" if (record.get("route") or {}).get("b") is not None else None
        except Exception:  # noqa: BLE001 — learning is best effort
            pass
    if req.mode == "write":
        try:                               # what changed, so the lead needs no `git diff --stat` of its own
            ds = diffstat(run_snapshot(p, record))
        except Exception:  # noqa: BLE001 — a missing git never fails the run
            ds = None
        if ds:
            record["diffstat"] = ds
    beat.set()
    record.pop("current", None)
    if not ledger.claim_final(run_dir, "run"):
        # `ccx stop` found this process gone and closed the run already: its record and ledger row stand
        closed = ledger.load_run(p, run_id)
        if closed.get("state") == "running":
            # nobody wrote a final state although the lock is taken: say so instead of an empty "not ok"
            closed.update(ok=False, error=closed.get("error") or "final.lock was already taken by "
                          + ((run_dir / "final.lock").read_text(encoding="utf-8", errors="replace")[:200]))
        return closed
    _write_record(run_dir, record)
    ledger.append(p, record)
    try:                                   # sessions.archive = after_run: a final result's session leaves the apps' lists
        from . import archive
        record["archived"] = bool(archive.after_run(p, record))
    except Exception:  # noqa: BLE001 — housekeeping never fails the work
        pass
    if record.get("kind") == "review_issues" and record.get("session_id"):
        # hand the problems back to the same sub-session once; its fix is reviewed again, against the same task
        issues = "\n".join(f"- {x}" for x in record["review"]["issues"]) or record["review"]["summary"]
        fix = run(Request(to=req.to, brief=f"An independent review of your change found problems:\n{issues}\n"
                          "Fix the real ones (say which you think are wrong and why), then re-run only the tests touching "
                          "your fix (-k NAME / one test id)"
                          + ("; not the whole check, ccx runs that itself. " if req.check else ". ") +
                          "Change only what the task needs; do not add checks or hardening it did not ask for.",
                          resume_run=run_id, caller=req.caller, cwd=req.cwd, review="on", risk=req.risk,
                          review_round=req.review_round + 1, check=req.check, fallback=False, task=req.task,
                          step=req.step, label=req.label), p)
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
        "ok": bool(record["ok"]) and record.get("kind") not in ("review_failed", "check_broken"),
        "status": r.get("status") or ("running" if record.get("state") == "running" else "error"),
        "summary": r.get("summary") or record.get("error"),
        "files_changed": r.get("files_changed", []),
        "verification": r.get("verification", "not-run"),
        "open_questions": r.get("open_questions", []),
        "next_step": r.get("next_step", ""),
        "tokens": tok,
    }
    if record.get("diffstat"):
        out["diffstat"] = record["diffstat"]          # `git diff --shortstat` since the run's undo snapshot
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
        if record["kind"] == "check_broken":
            out["hint"] = record["check"].get("broken") or "the check tested nothing"
            out["needs_lead"] = "check_broken: " + out["hint"].split(";")[0]
        if record["kind"] == "needs_write":
            out["hint"] = ("read-only run: the sub-agent says it needs to edit files (see summary). If you agree, "
                           f"run it again with --mode write")
        if record["kind"] in ("quota", "timeout", "user_stopped", "interrupted"):
            why = "ccx stop" if record["kind"] == "user_stopped" else record["kind"]
            out["hint"] = f"stopped by {why}; continue later with `ccx resume {record['run_id']}`"
            ra = last.get("retry_after")
            if ra:
                out["retry_after"] = ra
    if record.get("review"):
        rv = record["review"]
        out["review"] = {k: rv[k] for k in ("verdict", "reason", "by", "issues", "notes", "usd", "error",
                                            "edited_tests") if rv.get(k)}
        if rv.get("edited_tests"):                    # a builder that changed existing tests: the lead looks first
            out["edited_tests"] = rv["edited_tests"]
    if record.get("first_review"):
        out.setdefault("review", {})["first_round"] = {k: record["first_review"].get(k) for k in ("verdict", "issues")}
        out["fixed_after_review_of"] = record["review_of"]
    if record.get("kind") == "review_failed":
        out["hint"] = ("an independent review still finds problems after one fix round (review.issues): decide "
                       f"yourself, or `ccx resume {record['run_id']} \"...\"`")
        first = ((record.get("review") or {}).get("issues") or ["(see review)"])[0]
        out["needs_lead"] = f"review_failed: {first}"[:300]
    if record.get("check"):
        c = record["check"]
        out["check"] = {"cmd": c["cmd"], "passed": c["passed"], "exit": c["exit"],
                        **({"weak": c["weak"], "note": c["note"]} if c.get("weak") else {}),
                        **({"status": "check_broken"} if c.get("broken") else {})}
    if record.get("edited_tests") and "edited_tests" not in out:
        out["edited_tests"] = record["edited_tests"]
    if record["cwd"] and "/.ccx-worktrees/" in record["cwd"].replace("\\", "/"):
        out["worktree"] = record["cwd"]
    if record.get("auth_problem"):
        out["hint"] = f"{record['to']} looks logged out: run `{record['to']} login` on this machine."
    return out


def recap(record: dict, res: dict) -> str:
    """One line for the end of `ccx run`'s output (its last key), so a lead that pipes it through `tail` still has
    the run_id: status, check, review, API-equivalent cost and what to run next."""
    c = res.get("check")
    check = "none" if not c else ("passed" if c.get("passed") else
                                  f"{'broken' if record.get('kind') == 'check_broken' else 'failed'} (exit {c.get('exit')})")
    review = (res.get("review") or {}).get("verdict") or "none"
    usd = sum(a.get("ae_usd") or 0 for a in record.get("attempts") or []) + ((res.get("review") or {}).get("usd") or 0)
    ok = res.get("ok", record.get("ok"))
    lead = f" needs_lead={res['needs_lead'].split(':')[0]}" if res.get("needs_lead") else ""
    return (f"ccx run {record['run_id']}: status={res.get('status')} ok={str(bool(ok)).lower()} "
            f"check={check} review={review}{lead} cost=~${usd:.4f}; next: ccx show {record['run_id']}")
