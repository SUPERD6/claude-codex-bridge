"""Run an agent CLI headless and read what comes back: the parts every agent shares. What differs per tool (its
command line, its output, where its files are, what it can do) lives in ccx/agents/<name>.py."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


AUTH_HINTS = ("401", "unauthorized", "not logged in", "login", "authenticate", "api key")
QUOTA_HINTS = ("429", "rate limit", "rate_limit", "usage limit", "quota", "resource_exhausted", "too many requests",
               "limit reached", "credits", "exhausted your capacity")


MODEL_HINTS = ("model is not supported", "is not supported when using", "model_not_found", "model not found",
               "does not exist or you do not have access", "unsupported model", "not available for your",
               "invalid model", "unknown model")


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


# per-agent builders and parsers, from the adapters (imported last: they use the shared pieces above)
from .agents import all_adapters as _adapters  # noqa: E402
from .agents.claude import claude_invocation, parse_claude  # noqa: E402,F401
from .agents.codex import CODEX_KEEP, _codex_kept_settings, codex_invocation, parse_codex  # noqa: E402,F401
from .agents.gemini import GEMINI_P, gemini_invocation, parse_gemini  # noqa: E402,F401

BUILDERS = {a.name: a.build for a in _adapters()}
PARSERS = {a.name: a.parse for a in _adapters()}
TESTED_VERSIONS = {a.name: a.tested_version for a in _adapters()}
