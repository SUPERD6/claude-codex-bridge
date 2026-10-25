"""DeepSeek Harness (`dsh`, DeepSeek's own agent; github.com/deepseek-ai/deepseek-harness). Checked against the
source of dsh-v0.2.1-rc.3 (apps/cli README, packages/bundle/headless README + src, packages/bundle/base
cordis.patch.yml; read 2026-10-24), not yet a real run:
  dsh --profile headless --patch F --json [--session-id <id>] -   (task on stdin; launcher flags first)
  events session{sessionId} / status{phase: step_end, usage{inputTokens, outputTokens, cacheReadTokens,
  cacheWriteTokens}} / status{phase: turn_end, reason} / text / thinking / tool_call / tool_result / final{text} /
  error{message}. Token counts are disjoint (inputTokens is the uncached part). Exit 0 = the turn completed.
  No model or permission flag in rc.3: the model goes in a patch overlay (agent-default-model row), the sandbox
  mode in DSH_PERMISSION_MODE (read-only | workspace-write). Pay per token with DEEPSEEK_API_KEY."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import RESULT_SCHEMA
from ..runners import Invocation, Outcome, _json_from_text, bin_argv, classify, usage_dict
from .base import Adapter


def _patch(model: str, effort: str) -> str:
    """The run's overlay: which model, and no session-log upload (base dsh sends the session log along with
    DeepSeek requests by default; a sub-agent's run is the user's code, so ccx turns that off)."""
    sel = {"provider": "deepseek-official", "model": model}
    if effort and effort != "default":
        sel["reasoningEffort"] = effort
    rows = [{"id": "agent-default-model", "config": sel}, {"id": "session-log-deepseek", "disabled": True}]
    return json.dumps(rows, indent=1) + "\n"     # JSON is YAML: no YAML writer needed


def dsh_invocation(*, model: str, effort: str, perm: list[str], cwd: Path, prompt: str,
                   run_dir: Path, resume_id: str | None = None, lean: bool = False) -> Invocation:
    schema = RESULT_SCHEMA.read_text(encoding="utf-8")
    body = (prompt + "\n\nYour final message must be only the JSON result object described above. JSON schema "
            "of the final message:\n" + schema)
    patch = run_dir / "dsh.patch.yml"
    patch.write_text(_patch(model, effort), encoding="utf-8")
    argv = [*bin_argv("dsh"), "--profile", "headless", "--patch", str(patch), *perm, "--json"]
    if resume_id:
        argv += ["--session-id", resume_id]
    return Invocation(argv + ["-"], body, cwd, None)


def dsh_env(mode: str) -> dict:
    """Read-only or write goes through the environment (rc.3 has no flag for it); no OTel upload either."""
    return {"DSH_PERMISSION_MODE": "workspace-write" if mode == "write" else "read-only",
            "DSH_TELEMETRY_MODE": "DISABLED"}


def parse_dsh(stdout: str, stderr: str, rc: int, _last: Path | None = None) -> Outcome:
    out = Outcome(ok=False)
    fresh = cached = write = output = 0
    final, texts, errors, reason = None, [], [], None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "session":
            out.session_id = ev.get("sessionId") or out.session_id
        elif t == "status" and ev.get("phase") == "step_end":
            u = ev.get("usage") or {}
            fresh += int(u.get("inputTokens", 0) or 0)
            cached += int(u.get("cacheReadTokens", 0) or 0)
            write += int(u.get("cacheWriteTokens", 0) or 0)
            output += int(u.get("outputTokens", 0) or 0)
        elif t == "status" and ev.get("phase") == "turn_end":
            reason = ev.get("reason")
        elif t == "text":
            texts.append(str(ev.get("text", "")))
        elif t == "final":
            final = str(ev.get("text", ""))
        elif t == "error":
            errors.append(str(ev.get("message", "")))
    out.usage = usage_dict(fresh=fresh, write=write, cached=cached, out=output)
    out.raw_text = final if final else (texts[-1] if texts else "")
    out.result = _json_from_text(out.raw_text)
    out.ok = rc == 0 and out.result is not None
    if not out.ok:
        tail = [x for x in stderr.splitlines() if x.startswith("dsh:") and not x.startswith("dsh: reasoning")]
        out.error = (errors[-1] if errors else (tail[-1] if tail else "")) or \
            (f"turn ended: {reason}" if reason and reason != "completed" else f"exit code {rc}")
        out.kind = classify(" ".join(errors + tail))
        out.auth_problem = out.kind == "auth"
    return out


DESKTOP_NAME = "DeepSeek Harness"
DESKTOP_CLI = ("resources", "runtime", "cli", "bin", "dsh.cmd")     # in the desktop app 0.2.1-rc.3 (Windows)


def _uninstall_locations() -> list[str]:
    """InstallLocation of every "DeepSeek Harness ..." entry in Windows' uninstall registry (user, then machine)."""
    import winreg
    out = []
    for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            root = winreg.OpenKey(hive, sub)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                        name = str(winreg.QueryValueEx(k, "DisplayName")[0])
                        if name.startswith(DESKTOP_NAME):
                            out.append(str(winreg.QueryValueEx(k, "InstallLocation")[0]))
                except OSError:
                    continue
    return out


def desktop_cli(locations: list[str]) -> str | None:
    """The first install folder that has the desktop app's bundled CLI in it."""
    return next((str(Path(loc, *DESKTOP_CLI)) for loc in locations if loc and Path(loc, *DESKTOP_CLI).is_file()), None)


_located: dict = {}


def locate_desktop() -> str | None:
    """The `dsh` that ships inside the DeepSeek Harness desktop app, found from where Windows says the app is
    installed (never a path written into ccx). None elsewhere or when the app is not installed. Once per process."""
    import os
    if "path" not in _located:
        try:
            _located["path"] = desktop_cli(_uninstall_locations()) if os.name == "nt" else None
        except Exception:  # noqa: BLE001
            _located["path"] = None
    return _located["path"]


def dsh_home() -> Path:
    import os
    return Path(os.environ.get("DSH_HOME") or Path.home() / ".dsh")


ADAPTER = Adapter(
    name="dsh", vendor="deepseek", support="community", tested_version="0.2.1-rc.3",
    build=dsh_invocation, parse=parse_dsh,
    login_argv=None, home=dsh_home,
    session_files="<DSH_HOME>/... (not read by ccx yet)",
    lead_events=None,
    context_file="AGENTS.md", start_hook=None,      # no command hooks in 0.2.1-rc.3: it reads $DSH_HOME/AGENTS.md
    permissions="DSH_PERMISSION_MODE=read-only | workspace-write (set by ccx per run)",
    can_lead=True, can_work=True, can_resume=True, builtin_subagents=False, quota_readable=False,
    live_cost=False, turn_hook=False, pay_per_token=True, run_env=dsh_env, locate=locate_desktop,
)
