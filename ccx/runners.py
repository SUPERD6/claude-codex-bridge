"""Build the headless command for each agent and parse what comes back.

Both CLIs were checked against their --help on 2026-10-22:
  codex-cli 0.164.0 : codex exec --json -m M -c model_reasoning_effort=".." --output-schema F -o F [-]
                      codex exec resume <id> ... (no -s/-C, so sandbox goes through -c)
  Claude Code 2.1.309: claude -p --output-format stream-json --verbose --model M --effort E
                      --json-schema S --resume <id>; first event (system/init) has session_id,
                      the final type=result event has usage, total_cost_usd, structured_output.
  Gemini CLI 0.65.0  : gemini -p P -o stream-json -m M --approval-mode plan|auto_edit --skip-trust
                      --session-id <uuid> | --resume <uuid> (prompt on stdin, -p appended); events
                      init{session_id} / message{role,content,delta} / result{status,stats{input_tokens,
                      cached,output_tokens}} / error. No schema flag, no effort flag. Checked against the
                      bundled source (packages/cli nonInteractiveCli), not yet a logged-in run.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import RESULT_SCHEMA, codex_home

AUTH_HINTS = ("401", "unauthorized", "not logged in", "login", "authenticate", "api key")
QUOTA_HINTS = ("429", "rate limit", "rate_limit", "usage limit", "quota", "resource_exhausted", "too many requests",
               "limit reached", "credits", "exhausted your capacity")


MODEL_HINTS = ("model is not supported", "is not supported when using", "model_not_found", "model not found",
               "does not exist or you do not have access", "unsupported model", "not available for your",
               "invalid model", "unknown model")
TESTED_VERSIONS = {"codex": "0.164.0", "claude": "2.1.309", "gemini": "0.65.0"}


def classify(text: str) -> str:
    low = (text or "").lower()
    if any(h in low for h in MODEL_HINTS):
        return "model"          # this account can't use this model: try another model, not a stronger effort
    if any(h in low for h in QUOTA_HINTS):
        return "quota"
    if any(h in low for h in AUTH_HINTS):
        return "auth"
    return "error"


def find_bin(agent: str) -> str | None:
    override = os.environ.get(f"CCX_{agent.upper()}_BIN")
    if override:
        return override
    return shutil.which(agent) or (shutil.which(agent + ".cmd") if os.name == "nt" else None)


def bin_argv(agent: str) -> list[str]:
    """argv prefix for the agent. Overrides may be 'python path/to/fake.py'."""
    b = find_bin(agent)
    if not b:
        raise FileNotFoundError(
            f"{agent} CLI not found on PATH. Install it or set CCX_{agent.upper()}_BIN.")
    if b.endswith(".py"):
        import sys
        return [sys.executable, b]
    return [b]


@lru_cache(maxsize=None)
def cli_version(agent: str) -> str:
    """First line of `<agent> --version`, "" when unknown. Cached per process."""
    try:
        r = subprocess.run([*bin_argv(agent), "--version"], capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ""
    return (r.stdout.strip().splitlines() or [""])[0] if r.returncode == 0 else ""


@dataclass
class Invocation:
    argv: list[str]
    stdin: str
    cwd: Path
    last_message_file: Path | None = None


@dataclass
class Outcome:
    ok: bool
    session_id: str | None = None
    result: dict | None = None
    raw_text: str = ""
    usage: dict = field(default_factory=dict)
    cost_usd: float | None = None
    error: str | None = None
    auth_problem: bool = False
    kind: str = "ok"            # ok | quota | auth | error | timeout
    retry_after: str | None = None


# ---------------------------------------------------------------- codex
# Settings a lean start (--ignore-user-config) must still carry over from the user's config.toml.
# windows.sandbox: without the user's "elevated" sandbox, codex-cli 0.164 rejects every shell command
# in read-only mode ("blocked by policy"; tested 2026-10-23).
CODEX_KEEP = (("windows", "sandbox"),)


def _codex_kept_settings() -> list[str]:
    try:
        cfg = tomllib.loads((codex_home() / "config.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    out = []
    for table, key in CODEX_KEEP:
        value = (cfg.get(table) or {}).get(key)
        if isinstance(value, str):
            out += ["-c", f'{table}.{key}="{value}"']
    return out


def codex_invocation(*, model: str, effort: str, perm: list[str], cwd: Path, prompt: str,
                     run_dir: Path, resume_id: str | None = None, lean: bool = False) -> Invocation:
    last = run_dir / "last_message.json"
    common = ["--json", "-m", model, "-c", f'model_reasoning_effort="{effort}"', *perm,
              "--skip-git-repo-check", "--output-schema", str(RESULT_SCHEMA), "-o", str(last)]
    if lean:
        common += ["--ignore-user-config", *_codex_kept_settings()]
    if resume_id:
        argv = [*bin_argv("codex"), "exec", "resume", resume_id, *common, "-"]
    else:
        argv = [*bin_argv("codex"), "exec", *common, "-C", str(cwd), "-"]
    return Invocation(argv, prompt, cwd, last)


# Usage is normalized to the same four buckets for every agent (billing differs per bucket):
#   input_tokens        fresh, uncached input
#   cache_write_tokens  input written to the prompt cache (Anthropic bills 1.25x input for 5-minute,
#                       2x for 1-hour entries; cache_write_1h_tokens is the 1-hour part)
#   cached_input_tokens input read from the cache (~0.1x input)
#   output_tokens       output incl. reasoning
# OpenAI/Codex reports cached tokens INSIDE input_tokens; Anthropic reports them separately.
def usage_dict(fresh=0, write=0, write_1h=0, cached=0, out=0) -> dict:
    return {"input_tokens": int(fresh), "cache_write_tokens": int(write), "cache_write_1h_tokens": int(write_1h),
            "cached_input_tokens": int(cached), "output_tokens": int(out)}


def parse_codex(stdout: str, stderr: str, rc: int, last_file: Path | None) -> Outcome:
    out = Outcome(ok=False)
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    last_agent_msg, errors = "", []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type", "")
        if t == "thread.started":
            out.session_id = ev.get("thread_id")
        elif t == "turn.completed":
            for k in usage:
                usage[k] += int((ev.get("usage") or {}).get(k, 0) or 0)
        elif t == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") in ("agent_message", "assistant_message"):
                last_agent_msg = item.get("text") or last_agent_msg
        elif t in ("turn.failed", "error"):
            msg = ev.get("message") or (ev.get("error") or {}).get("message") or json.dumps(ev)
            errors.append(str(msg))
    # codex: cached_input_tokens is a subset of input_tokens
    out.usage = usage_dict(fresh=max(0, usage["input_tokens"] - usage["cached_input_tokens"]),
                           cached=usage["cached_input_tokens"], out=usage["output_tokens"])
    text = ""
    if last_file and last_file.exists():
        text = last_file.read_text(encoding="utf-8", errors="replace").strip()
    text = text or last_agent_msg
    out.raw_text = text
    out.result = _json_from_text(text)
    joined = " ".join(errors[-3:] + [stderr[-500:]]).lower()
    out.auth_problem = any(h in joined for h in AUTH_HINTS) and out.result is None
    out.ok = rc == 0 and out.result is not None
    if not out.ok:
        out.error = (errors[-1] if errors else stderr.strip()[-800:]) or f"exit code {rc}"
        out.kind = classify(" ".join(errors) + " " + stderr)
    return out


# ---------------------------------------------------------------- claude
def claude_invocation(*, model: str, effort: str, perm: list[str], cwd: Path, prompt: str,
                      run_dir: Path, resume_id: str | None = None, lean: bool = False) -> Invocation:
    schema = json.dumps(json.loads(RESULT_SCHEMA.read_text(encoding="utf-8")))
    # stream-json (+ --verbose, required with -p): the session id arrives in the first event, so a crash
    # mid-run still leaves a resumable session on record
    argv = [*bin_argv("claude"), "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--effort", effort, "--json-schema", schema, *perm]
    if lean and "--strict-mcp-config" not in argv:
        argv += ["--strict-mcp-config"]
    if lean and "--disable-slash-commands" not in argv:
        argv += ["--disable-slash-commands"]
    if resume_id:
        argv += ["--resume", resume_id]
    return Invocation(argv, prompt, cwd, None)


def parse_claude(stdout: str, stderr: str, rc: int, _last: Path | None = None) -> Outcome:
    out = Outcome(ok=False)
    data = None
    s = stdout.strip()
    events = []
    for line in s.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not events and s:
        try:
            events = [json.loads(s)]
        except json.JSONDecodeError:
            pass
    for ev in events:
        if ev.get("session_id") and not out.session_id:
            out.session_id = ev["session_id"]
        if ev.get("type") == "rate_limit_event":
            info = ev.get("rate_limit_info") or ev
            if str(info.get("status", "")).lower() in ("rejected", "exceeded", "blocked"):
                out.kind = "quota"
            out.retry_after = info.get("resetsAt") or info.get("resets_at") or out.retry_after
    results = [e for e in events if e.get("type") == "result" or "structured_output" in e]
    data = results[-1] if results else (events[-1] if events else None)
    if isinstance(data, dict):
        out.session_id = data.get("session_id")
        u = data.get("usage") or {}
        cc = u.get("cache_creation") or {}
        out.usage = usage_dict(fresh=u.get("input_tokens", 0) or 0,
                               write=u.get("cache_creation_input_tokens", 0) or 0,
                               write_1h=cc.get("ephemeral_1h_input_tokens", 0) or 0,
                               cached=u.get("cache_read_input_tokens", 0) or 0,
                               out=u.get("output_tokens", 0) or 0)
        out.cost_usd = data.get("total_cost_usd")
        out.result = data.get("structured_output") or _json_from_text(str(data.get("result", "")))
        out.raw_text = str(data.get("result", ""))
        if data.get("is_error"):
            out.error = out.raw_text or data.get("subtype")
    joined = (stderr + " " + (out.error or "")).lower()
    out.auth_problem = any(h in joined for h in AUTH_HINTS) and out.result is None
    out.ok = rc == 0 and out.result is not None and not (isinstance(data, dict) and data.get("is_error"))
    if not out.ok and not out.error:
        out.error = stderr.strip()[-800:] or f"exit code {rc}"
    if not out.ok and out.kind == "ok":
        out.kind = classify(joined)
    if out.ok:
        out.kind = "ok"
    return out


# ---------------------------------------------------------------- gemini
GEMINI_P = "Do the task given above. Your final message must be only the JSON result object described there."


def gemini_invocation(*, model: str, effort: str, perm: list[str], cwd: Path, prompt: str,
                      run_dir: Path, resume_id: str | None = None, lean: bool = False) -> Invocation:
    import uuid
    schema = RESULT_SCHEMA.read_text(encoding="utf-8")
    body = prompt + "\n\nJSON schema of the final message:\n" + schema
    argv = [*bin_argv("gemini"), "-p", GEMINI_P, "-o", "stream-json", "-m", model, "--skip-trust", *perm]
    if resume_id:
        argv += ["--resume", resume_id]
    else:
        argv += ["--session-id", str(uuid.uuid4())]   # known before start: resumable even if it dies at once
    return Invocation(argv, body, cwd, None)


def parse_gemini(stdout: str, stderr: str, rc: int, _last: Path | None = None) -> Outcome:
    out = Outcome(ok=False)
    text, errors, status, stats = [], [], None, {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "init":
            out.session_id = ev.get("session_id") or out.session_id
        elif t == "message" and ev.get("role") == "assistant":
            text.append(str(ev.get("content", "")))
        elif t == "error":
            errors.append(str(ev.get("message", "")))
        elif t == "result":
            status, stats = ev.get("status"), ev.get("stats") or {}
            if ev.get("error"):
                errors.append(str((ev["error"] or {}).get("message", "")))
    prompt_tok, cached = int(stats.get("input_tokens", 0) or 0), int(stats.get("cached", 0) or 0)
    out.usage = usage_dict(fresh=max(0, prompt_tok - cached), cached=cached, out=stats.get("output_tokens", 0) or 0)
    out.raw_text = "".join(text)
    out.result = _json_from_text(out.raw_text)
    out.ok = rc == 0 and status != "error" and out.result is not None
    if not out.ok:
        out.error = (errors[-1] if errors else stderr.strip()[-800:]) or f"exit code {rc}"
        out.kind = classify(" ".join(errors) + " " + stderr)
        out.auth_problem = out.kind == "auth"
    return out


def _json_from_text(text: str) -> dict | None:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a != -1 and b > a:
            try:
                v = json.loads(t[a:b + 1])
                return v if isinstance(v, dict) else None
            except json.JSONDecodeError:
                return None
    return None


BUILDERS = {"codex": codex_invocation, "claude": claude_invocation, "gemini": gemini_invocation}
PARSERS = {"codex": parse_codex, "claude": parse_claude, "gemini": parse_gemini}


def _first_session_id(agent: str, line: str) -> str | None:
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return None
    if agent == "codex" and ev.get("type") == "thread.started":
        return ev.get("thread_id")
    if agent != "codex":
        return ev.get("session_id")
    return None


def execute(agent: str, inv: Invocation, timeout: int, env: dict, on_session=None, watch=None,
            watch_every: float = 20.0) -> tuple[Outcome, str, str]:
    """Run the sub-agent, streaming stdout so the session id is persisted the moment it appears. `watch()` is
    asked every `watch_every` seconds while it runs; a reason it returns stops the run (e.g. a spending cap)."""
    import threading
    try:
        proc = subprocess.Popen(inv.argv, cwd=str(inv.cwd), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace")
    except OSError as e:
        oc = Outcome(ok=False, error=f"could not start {agent}: {e}", kind="error")
        return oc, "", ""
    err_chunks: list[str] = []
    t_err = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    t_err.start()
    try:
        proc.stdin.write(inv.stdin)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    out_lines: list[str] = []
    seen = False
    fired: list[bool] = []

    def _kill():
        fired.append(True)
        proc.kill()

    timer = threading.Timer(timeout, _kill)
    timer.start()
    stopped: list[str] = []
    done_ev = threading.Event()

    def _watch():
        while not done_ev.wait(watch_every):
            try:
                why = watch()
            except Exception:  # noqa: BLE001 — a failing check never stops the run
                why = None
            if why:
                stopped.append(why)
                proc.kill()
                return
    if watch:
        threading.Thread(target=_watch, daemon=True).start()
    rc = -1
    try:
        for line in proc.stdout:
            out_lines.append(line)
            if not seen and on_session:
                sid = _first_session_id(agent, line.strip())
                if sid:
                    seen = True
                    try:
                        on_session(sid)
                    except Exception:  # noqa: BLE001 — bookkeeping must never kill the run
                        pass
        rc = proc.wait()
    finally:
        timer.cancel()
        done_ev.set()
    timed_out = bool(fired)
    t_err.join(timeout=5)
    so, se = "".join(out_lines), "".join(err_chunks)
    oc = PARSERS[agent](so, se, rc, inv.last_message_file)
    if timed_out and not oc.ok:
        oc.error, oc.kind = f"timed out after {timeout}s", "timeout"
    if stopped:
        oc.ok, oc.error, oc.kind = False, stopped[0], "over_budget"
    return oc, so, se
