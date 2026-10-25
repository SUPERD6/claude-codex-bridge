"""Template for a new agent CLI (I1/I8). Copy to `ccx/agents/<name>.py`, add <name> to NAMES in __init__.py, and
copy tests/fakes/fake_template.py to tests/fakes/fake_<name>.py. Nothing in the core changes.

Before writing a line, read the CLI's own `--help` and docs and note here what you checked and its version, e.g.
  checked against `mytool --help` of mytool 1.4.0 (2026-10-25), not yet a real run:
  mytool run --json --model M [--resume <id>]   (task on stdin); events session{id} / usage{...} / final{text}
A new adapter starts as support="community": ccx tested it with a stand-in only. It becomes "official" after the
release check (H15) runs real read, write and resume tasks on the version in tested_version; `ccx doctor` warns when
the installed major.minor differs from it.

This file is not registered (its name starts with "_"); tests/test_agent_template.py runs it against the fake so the
template itself keeps working."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import RESULT_SCHEMA
from ..runners import Invocation, Outcome, _json_from_text, bin_argv, classify, usage_dict
from .base import Adapter

NAME = "example"            # the command name, also the agent name in `--to` and in tiers.toml


def invocation(*, model: str, effort: str, perm: list[str], cwd: Path, prompt: str,
               run_dir: Path, resume_id: str | None = None, lean: bool = False) -> Invocation:
    """argv + stdin for one headless run. A CLI without a JSON-schema flag gets the schema in the prompt."""
    schema = RESULT_SCHEMA.read_text(encoding="utf-8")
    body = prompt + "\n\nYour final message must be only the JSON result object. JSON schema:\n" + schema
    argv = [*bin_argv(NAME), "run", "--json", "--model", model, *perm]
    if resume_id:
        argv += ["--resume", resume_id]
    return Invocation(argv, body, cwd, None)       # last arg: a file the CLI writes its last message to, if any


def parse(stdout: str, stderr: str, rc: int, _last: Path | None = None) -> Outcome:
    """Read the CLI's event stream: session id, token usage, the final text (which holds the JSON result)."""
    out = Outcome(ok=False)
    text, errors, usage = [], [], {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "session":
            out.session_id = ev.get("id") or out.session_id
        elif t == "usage":
            usage = ev
        elif t == "final":
            text.append(str(ev.get("text", "")))
        elif t == "error":
            errors.append(str(ev.get("message", "")))
    out.usage = usage_dict(fresh=usage.get("input", 0) or 0, cached=usage.get("cached", 0) or 0,
                           out=usage.get("output", 0) or 0)
    out.raw_text = "".join(text)
    out.result = _json_from_text(out.raw_text)
    out.ok = rc == 0 and out.result is not None
    if not out.ok:
        out.error = (errors[-1] if errors else stderr.strip()[-800:]) or f"exit code {rc}"
        out.kind = classify(" ".join(errors) + " " + stderr)     # quota / auth / ... drive fallback
        out.auth_problem = out.kind == "auth"
    return out


ADAPTER = Adapter(
    name=NAME, vendor="example-vendor", support="community", tested_version="1.4.0",
    build=invocation, parse=parse,
    login_argv=None,                      # e.g. ("auth", "status") if the CLI can say whether it is logged in
    home=lambda: Path.home() / f".{NAME}",
    session_files="not read by ccx yet",
    lead_events=None,                     # "module:function" once ccx can read its lead conversations
    context_file="AGENTS.md", start_hook=None,
    permissions="read-only / write flags (config [permissions.example])",
    can_lead=False, can_work=True, can_resume=True, builtin_subagents=False, quota_readable=False,
    live_cost=False, turn_hook=False,
)
