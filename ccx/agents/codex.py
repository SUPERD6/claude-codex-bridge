"""Codex CLI (OpenAI). checked against codex-cli 0.164.0 --help (2026-10-22/23):
  codex exec --json -m M -c model_reasoning_effort=".." --output-schema F -o F [-]
  codex exec resume <id> ... (no -s/-C, so sandbox goes through -c)"""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

from ..config import RESULT_SCHEMA, codex_home
from ..runners import AUTH_HINTS, Invocation, Outcome, _json_from_text, bin_argv, classify, usage_dict
from .base import Adapter

# Settings a lean start (--ignore-user-config) must still carry over from the user's config.toml.
# windows.sandbox: without the user's "elevated" sandbox, codex-cli 0.164 rejects every shell command
# in read-only mode ("blocked by policy"; tested 2026-10-23).
CODEX_KEEP = (("windows", "sandbox"),)


# What CCX_CODEX_ISOLATE=1 turns off besides the user's config.toml (belt and braces: config.toml is not loaded)
ISOLATE_SETTINGS = ("-c", "features.memories=false", "-c", "memories.use_memories=false",
                    "-c", "memories.generate_memories=false")


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
    isolate = os.environ.get("CCX_CODEX_ISOLATE") == "1"
    if lean or isolate:
        common += ["--ignore-user-config", *_codex_kept_settings()]
    if isolate:
        # opt-in (an evaluation's clean room): no execpolicy .rules files and no Codex memories, whatever the
        # effort (codex-cli 0.164.0 exec --help: --ignore-rules, -c key=value; also on `exec resume`)
        common += ["--ignore-rules", *ISOLATE_SETTINGS]
    if resume_id:
        argv = [*bin_argv("codex"), "exec", "resume", resume_id, *common, "-"]
    else:
        argv = [*bin_argv("codex"), "exec", *common, "-C", str(cwd), "-"]
        if os.name == "nt":
            prompt = WINDOWS_SHELL + prompt
    return Invocation(argv, prompt, cwd, last)


# Codex runs its commands in Windows PowerShell 5.1 (checked on codex-cli 0.164). Round 5: `Get-Content` without
# -Encoding read a UTF-8 file as the ANSI code page, its Chinese turned to mojibake, the patch context never matched,
# a bash heredoc then failed in PowerShell, and the run gave up after 42 s.
WINDOWS_SHELL = ("[ccx note: Windows] Your shell is Windows PowerShell 5.1. Files are UTF-8: read them with "
                 "`Get-Content -Encoding UTF8 <file>` (plain Get-Content shows non-ASCII text garbled although the file "
                 "is fine) or with Python. Bash syntax such as heredocs (<<'EOF') does not work here: write a .py file "
                 "or use `python -c` instead.\n\n")


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


# ---- accounting for sub-runs (from delegate.py)
# `codex exec resume` reports the session's running total in turn.completed, not the turn's own usage
# (codex-cli 0.164, checked against the rollout's last_token_usage 2026-10-23). Count only the growth.
def _codex_total(u: dict) -> dict:
    return {"input": u.get("input_tokens", 0) + u.get("cached_input_tokens", 0),
            "cached": u.get("cached_input_tokens", 0), "output": u.get("output_tokens", 0)}


def _codex_growth(total: dict, before: dict) -> dict:
    d = {k: max(0, total[k] - before.get(k, 0)) for k in total}
    return usage_dict(fresh=max(0, d["input"] - d["cached"]), cached=d["cached"], out=d["output"])


def _add_children(usage: dict, session: str, since: float, kids: dict) -> dict:
    """Add what the session's own multi_agent children used since `since`: their tokens are not in its
    turn.completed. `kids` keeps each child's counted total, so a resumed session counts only the growth."""
    from ..usage import codex_children
    try:
        found = codex_children(session, since - 5)
    except Exception:  # noqa: BLE001 — accounting must never break a run
        return usage
    out = dict(usage)
    for child, tot in found.items():
        g = _codex_growth(tot, kids.get(child, {}))
        for k in ("input_tokens", "cached_input_tokens", "output_tokens"):
            out[k] = out.get(k, 0) + g.get(k, 0)
        kids[child] = tot
    return out


def _codex_seen(prev: dict | None) -> dict:
    """Running totals of the Codex sessions an earlier run used (older records stored the total as usage)."""
    seen = {}
    for a in (prev or {}).get("attempts", []):
        if a.get("agent") == "codex" and a.get("session_id") and a.get("usage"):
            if a.get("recovered") and not a.get("codex_total"):
                continue            # read back after a kill: its own usage, not a running total of the session
            seen[a["session_id"]] = a.get("codex_total") or _codex_total(a["usage"])
    return seen


ADAPTER = Adapter(
    name="codex", vendor="openai", support="official", tested_version="0.164.0",
    build=codex_invocation, parse=parse_codex,
    login_argv=("login", "status"), home=codex_home,
    session_files="<CODEX_HOME>/sessions/YYYY/MM/DD/rollout-*.jsonl (session_meta has cwd and, for its own "
                  "sub-agents, the parent thread)",
    lead_events="ccx.usage:codex_events",
    context_file="AGENTS.md", start_hook="config.toml [hooks] SessionStart (trust once in /hooks)",
    permissions='-c sandbox_mode="read-only" | --sandbox workspace-write (config [permissions.codex])',
    can_lead=True, can_work=True, can_resume=True, builtin_subagents=True, quota_readable=True,
    live_cost=True, turn_hook=False,
)
