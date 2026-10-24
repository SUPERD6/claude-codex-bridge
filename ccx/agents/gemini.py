"""Gemini CLI (Google). checked against the bundled source of Gemini CLI 0.65.0 (packages/cli
nonInteractiveCli), not yet a logged-in run:
  gemini -p P -o stream-json -m M --approval-mode plan|auto_edit --skip-trust --session-id <uuid> | --resume <uuid>
  (prompt on stdin, -p appended); events init{session_id} / message{role,content,delta} / result{status,
  stats{input_tokens,cached,output_tokens}} / error. No schema flag, no effort flag."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import RESULT_SCHEMA
from ..runners import Invocation, Outcome, _json_from_text, bin_argv, classify, usage_dict
from .base import Adapter

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


def gemini_home() -> Path:
    return Path.home() / ".gemini"


ADAPTER = Adapter(
    name="gemini", vendor="google", support="community", tested_version="0.65.0",
    build=gemini_invocation, parse=parse_gemini,
    login_argv=None, home=gemini_home,
    session_files="not read by ccx yet",
    lead_events=None,
    context_file="GEMINI.md", start_hook=None,
    permissions="--approval-mode plan | auto_edit (config [permissions.gemini])",
    can_lead=False, can_work=True, can_resume=True, builtin_subagents=False, quota_readable=False,
    live_cost=False, turn_hook=False,
)
