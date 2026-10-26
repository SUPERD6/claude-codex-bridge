"""Claude Code (Anthropic). checked against Claude Code 2.1.309 --help (2026-10-22/23):
  claude -p --output-format stream-json --verbose --model M --effort E --json-schema S --resume <id>;
  the first event (system/init) has session_id, the final type=result event has usage, total_cost_usd,
  structured_output."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import RESULT_SCHEMA, claude_home
from ..runners import AUTH_HINTS, Invocation, Outcome, _json_from_text, bin_argv, classify, usage_dict
from .base import Adapter

def claude_schema() -> dict:
    """The result schema with only status and summary required. Claude Code rejects a structured output that misses a
    required key and the model sends it again: in rounds 4-5, 10 of 181 Claude runs re-sent it 51 times in all, mostly
    for `open_questions` (haiku dropped it four times running). ccx reads the other keys with defaults; Codex keeps the
    strict schema, which its --output-schema needs."""
    s = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    s["required"] = [k for k in s.get("required", []) if k in ("status", "summary")]
    return s


def claude_invocation(*, model: str, effort: str, perm: list[str], cwd: Path, prompt: str,
                      run_dir: Path, resume_id: str | None = None, lean: bool = False) -> Invocation:
    schema = json.dumps(claude_schema())
    # stream-json (+ --verbose, required with -p): the session id arrives in the first event, so a crash
    # mid-run still leaves a resumable session on record
    argv = [*bin_argv("claude"), "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--effort", effort, "--json-schema", schema, *perm]
    if lean and "--strict-mcp-config" not in argv:
        argv += ["--strict-mcp-config"]
    if lean and "--disable-slash-commands" not in argv:
        argv += ["--disable-slash-commands"]
    if "--settings" not in argv:
        # ultracode (standing dynamic workflows) is session-scoped, set by the desktop app or --settings; a
        # sub-run must not inherit it or opt in through the keyword in a brief (checked against 2.1.309)
        argv += ["--settings", json.dumps({"ultracode": False, "workflowKeywordTriggerEnabled": False})]
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
        fresh, write = u.get("input_tokens", 0) or 0, u.get("cache_creation_input_tokens", 0) or 0
        cached, outp = u.get("cache_read_input_tokens", 0) or 0, u.get("output_tokens", 0) or 0
        w1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
        mu = data.get("modelUsage") or {}
        if mu:
            # `usage` is the last request of the main conversation only; `modelUsage` is the whole session, its
            # own sub-agents (Agent tool) included (checked 2026-10-24, Claude Code 2.1.309: usage 11.6k cache
            # writes, modelUsage 19.9k with one sub-agent; total_cost_usd matches modelUsage)
            tot = lambda k: sum(int((v or {}).get(k, 0) or 0) for v in mu.values())  # noqa: E731
            if tot("cacheCreationInputTokens") + tot("cacheReadInputTokens") + tot("inputTokens") \
                    >= fresh + write + cached:
                extra_w = max(0, tot("cacheCreationInputTokens") - write)
                fresh, cached, outp = tot("inputTokens"), tot("cacheReadInputTokens"), tot("outputTokens")
                w1h += extra_w if w1h == write else 0       # Claude Code writes the 1-hour cache throughout
                write += extra_w
        out.usage = usage_dict(fresh=fresh, write=write, write_1h=w1h, cached=cached, out=outp)
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


ADAPTER = Adapter(
    name="claude", vendor="anthropic", support="official", tested_version="2.1.309",
    build=claude_invocation, parse=parse_claude,
    login_argv=("auth", "status"), home=claude_home,
    session_files="<CLAUDE_CONFIG_DIR>/projects/<folder slug>/<session>.jsonl; its own sub-agents in "
                  "<session>/subagents/agent-*.jsonl",
    lead_events="ccx.usage:claude_events",
    context_file="CLAUDE.md", start_hook="settings.json hooks SessionStart (+ UserPromptSubmit for `ccx lead --hint`)",
    permissions="--permission-mode / --allowedTools (config [permissions.claude])",
    can_lead=True, can_work=True, can_resume=True, builtin_subagents=True, quota_readable=True,
    live_cost=True, turn_hook=True,          # its sub-agents' spend: <session>/subagents/*.jsonl, live (F12)
)
