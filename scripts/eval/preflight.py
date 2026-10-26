"""A clean room for evaluation units, and the check that refuses to start without one (E1-E5).

What it guarantees, by mechanism (command-line flags, environment, settings files), not by what the prompt says:

  E1 every unit from zero   a fresh repo copy and hub (the caller), plus a per-unit folder x-<key>/ holding the
                            unit's TMP/TEMP, a git config with a neutral identity, CCX_CONFIG, a fresh DSH_HOME and
                            the Claude settings below. The environment is built from an allow-list, so host and
                            session variables (CLAUDE_CODE_*, TASK_ROUTING_HOME, ...) do not pass. Claude, lead and
                            ccx sub-agents alike: `--setting-sources project,local` (no user settings.json, so none
                            of its hooks, `language` or `env`), a settings file with disableAllHooks, auto-memory off,
                            claudeMdExcludes for the user-level CLAUDE.md and rules, and permission deny rules for the
                            real ~/.claude, ~/.codex, ~/.ccx, the real hub and this checkout. ccx sub-agents get the
                            same through CCX_CLAUDE_SETTING_SOURCES / CCX_CLAUDE_SETTINGS (opt-in knobs in
                            ccx/agents/claude.py). `--claude-isolation config-dir` goes further: CLAUDE_CONFIG_DIR is
                            a fresh folder per unit (needs CLAUDE_CODE_OAUTH_TOKEN, which the person exports; it is
                            passed through by name and never read). Codex: a dedicated eval CODEX_HOME the person
                            logged in to once (`--codex-home`), and CCX_CODEX_ISOLATE=1 (--ignore-user-config,
                            --ignore-rules, memories off on every Codex run).
  E2 no leftovers           every process a unit starts runs in a Windows Job Object (POSIX: its own session, plus a
                            marker variable CCX_EVAL_UNIT); after the unit the job's survivors, and any new process
                            whose command line names the unit's repo, hub or label, are listed (with listening
                            ports), killed and logged in one line. The unit's x- folder, its ccx worktrees and (in
                            flags mode) the Claude session folders named after its paths are removed.
  E3 same inputs            the fingerprint: eval checkout commit (refused when tracked files are modified), sha256
                            of the task file, `claude --version` / `codex --version` / `dsh --version` (checked again
                            after every unit: a change stops the run), the eval CODEX_HOME's file names and
                            models_cache.json hash, an empty shared memory in the fresh hub.
  E4 no interference        refuses to start while another eval, pytest or `ccx run/discuss/resume` runs outside this
                            process tree; the concurrency (--jobs) is recorded; checked again between units.
  E5 this script            `run()` collects every problem; any problem blocks the run unless --force-unclean,
                            which is recorded in every row. Each row gets `fingerprint()`, an `audit` of its own
                            streams (init event: no hooks, no MCP servers, no skills, builtin plugins only, memory
                            paths inside the unit; no tool call naming a real home, hub or this checkout) and its
                            `leftovers`; `env_clean` is false when either found something.

What it cannot block by mechanism (recorded instead): a Bash command can still read any file the user can (Claude's
sandbox is not available on Windows); the audit scans every tool call afterwards. In flags mode Claude keeps the real
~/.claude for login, so it still writes ~/.claude.json project entries and (for leads that keep a session) a session
folder, which is removed after the unit.

  python scripts/eval/preflight.py --arms ccx,ccx2 --workdir %TEMP%/r6 --codex-home <dir>     # check only
  python scripts/eval/preflight.py ... --canary                                               # + one tiny real lead
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402  (puts ROOT on sys.path)

from ccx.agents.codex import CODEX_KEEP  # noqa: E402
from ccx.runners import find_bin  # noqa: E402

TASKS_FILE = Path(__file__).resolve().parent / "tasks_r5.py"
SETTING_SOURCES = "project,local"
CODEX_ARMS = ("ccx", "ccx2", "direct")          # arms whose units start Codex (ccx routes to it)
# Names a dedicated eval CODEX_HOME must not have: each would bring the person's rules, memory or tools back.
CODEX_FORBIDDEN = ("AGENTS.md", "AGENTS.override.md", "memories", "rules", "skills", "plugins", "hooks")
CODEX_FORBIDDEN_TABLES = ("mcp_servers", "plugins", "hooks", "profiles", "marketplaces")
# Allow-list of inherited variables. Everything else (session ids, host auth helpers, TASK_ROUTING_HOME, ...) is
# dropped; what a unit needs is set explicitly in unit_env().
ENV_KEEP = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "OS", "USERPROFILE", "HOME", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ALLUSERSPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "PROGRAMW6432", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "PUBLIC", "USERNAME",
    "USERDOMAIN", "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "TZ", "XDG_RUNTIME_DIR",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "HTTP_PROXY", "HTTPS_PROXY",
    "NO_PROXY", "ALL_PROXY", "VIRTUAL_ENV", "PYTHONUTF8", "CLAUDE_CODE_GIT_BASH_PATH", "CCX_NODE", "CCX_NO_LOCATE",
}
# passed through by name, never read or logged: provider runs need their keys (e.g. DEEPSEEK_API_KEY), and
# CLAUDE_CODE_OAUTH_TOKEN is how a lead logs in with a fresh CLAUDE_CONFIG_DIR
ENV_KEEP_SUFFIX = ("_API_KEY", "_AUTH_TOKEN", "_OAUTH_TOKEN")
HEAVY = (re.compile(r"scripts[/\\]+eval[/\\]+\w+\.py[\"']?\s+(run|rescore)\b", re.I),
         re.compile(r"(-m\s+pytest\b|[/\\]pytest(\.exe)?[\"']?(\s|$)|\bpy\.test\b)", re.I),
         re.compile(r"ccx\.py[\"']?\s+(run|discuss|resume)\b", re.I))
WORK_ENTRY = re.compile(r"^(\d+-[\w.-]+|h-\d+-[\w.-]+|x-[\w.-]+|r5iso-\w+|\.ccx-worktrees|canary|"
                        r"[\w.-]+\.stream\.jsonl|preflight[\w.-]*\.json|\.ccx-eval-work)$")
CANARY_WORD = "KIWI-7"


def sha256_file(f: Path) -> str | None:
    try:
        return hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        return None


def slug(path: Path | str) -> str:
    """Claude Code's folder name for a working directory (every non-alphanumeric character becomes '-')."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _norm(s: str) -> str:
    s = str(s).replace("\\\\", "/").replace("\\", "/")
    return s.lower() if os.name == "nt" else s


def _has(marker: str, text: str) -> bool:
    """`marker` in `text` as a whole path or label: /w/1-t-ccx matches /w/1-t-ccx/x but not /w/1-t-ccx2."""
    if not marker:
        return False
    tail = "" if marker[-1] in "/:" else r"(?![A-Za-z0-9_.-])"     # "eval-r5:<tag>:" is a prefix on purpose
    return re.search(re.escape(marker) + tail, text) is not None


# ------------------------------------------------------------------ the person's real homes

def real_paths(env=None) -> dict[str, Path]:
    """Where the person's own state lives, from the environment this eval was started in."""
    env = os.environ if env is None else env
    home = Path.home()
    out = {"home": home, "claude_home": Path(env.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser(),
           "claude_json": home / ".claude.json", "home_claude": home / ".claude", "home_codex": home / ".codex",
           "codex_home": Path(env.get("CODEX_HOME") or home / ".codex").expanduser(), "ccx_home": home / ".ccx",
           "ccx_config": Path(env.get("CCX_CONFIG") or home / ".ccx" / "config.toml").expanduser(),
           "dsh_home": Path(env.get("DSH_HOME") or home / ".dsh").expanduser(), "root": ROOT}
    hub = env.get("CCX_HUB")
    if not hub:
        try:
            hub = tomllib.loads(out["ccx_config"].read_text(encoding="utf-8")).get("hub")
        except (OSError, tomllib.TOMLDecodeError):
            hub = None
    out["hub"] = Path(hub).expanduser() if hub else home / ".ccx"
    return out


def _inside(p: Path, root: Path) -> bool:
    try:
        Path(p).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


# ------------------------------------------------------------------ one unit's clean room

@dataclass
class Unit:
    key: str
    work: Path
    repo: Path
    hub: Path
    label: str = ""
    claude: str = "flags"                 # flags | config-dir
    codex_home: Path | None = None        # the dedicated eval CODEX_HOME (None: the real one, recorded as such)
    dsh: str = "unit"                     # unit (fresh DSH_HOME per unit) | real
    real: dict = field(default_factory=real_paths)

    @property
    def x(self) -> Path:
        return self.work / f"x-{self.key}"

    @property
    def worktrees(self) -> Path:
        return self.work / ".ccx-worktrees" / self.repo.name

    @property
    def settings_file(self) -> Path:
        return self.x / "claude-settings.json"

    @property
    def claude_dir(self) -> Path:
        return self.x / "claude-config" if self.claude == "config-dir" else self.real["claude_home"]

    def markers(self) -> list[str]:
        """Strings that name this unit in a process's command line."""
        out = [_norm(self.repo), _norm(self.hub), _norm(self.x), _norm(self.worktrees)]
        return out + ([_norm(self.label)] if self.label else [])


def _rule_path(p: Path) -> str:
    return "//" + p.as_posix().lstrip("/")


def forbidden(u: Unit) -> list[Path]:
    """Folders a unit's agents must not open: the person's homes, hub, config and this checkout."""
    r = u.real
    out = [r["home_codex"], r["codex_home"], r["ccx_home"], r["hub"], r["dsh_home"]]
    if u.claude == "config-dir":
        out += [r["home_claude"], r["claude_home"]]
    if not _inside(u.work, r["root"]):
        out.append(r["root"])
    if u.codex_home:
        out = [p for p in out if not (_inside(u.codex_home, p) or _inside(p, u.codex_home))]
    if u.dsh == "real":
        out = [p for p in out if p != r["dsh_home"]]
    uniq: list[Path] = []
    for p in out:
        if p not in uniq and not _inside(u.work, p):
            uniq.append(p)
    return uniq


def claude_files(u: Unit) -> list[str]:
    """Files under the real Claude home a unit must not see in flags mode (the folder stays: it holds the login)."""
    out = []
    for base in {u.real["home_claude"], u.real["claude_home"]}:
        out += [base / "CLAUDE.md", base / "rules", base / "settings.json", base / "settings.local.json",
                base / "agents", base / "commands", base / "skills", base / "plugins", base / "ccx-archive",
                base / "history.jsonl", base / "todos", base / "output-styles"]
    return sorted({_rule_path(p) + ("/**" if not p.suffix else "") for p in out})


def claude_settings(u: Unit) -> dict:
    deny = []
    for p in forbidden(u):
        deny += [f"Read({_rule_path(p)}/**)", f"Edit({_rule_path(p)}/**)"]
    deny += [f"Read({_rule_path(u.real['claude_json'])})", f"Edit({_rule_path(u.real['claude_json'])})"]
    if u.claude == "flags":
        deny += [f"{t}({p})" for p in claude_files(u) for t in ("Read", "Edit")]
    excludes = []
    for base in {u.real["home_claude"], u.real["claude_home"]}:
        for p in (base / "CLAUDE.md", base / "rules" / "**"):
            excludes += [str(p), p.as_posix()]
    return {"disableAllHooks": True, "hooks": {}, "autoMemoryEnabled": False,
            "claudeMdExcludes": sorted(set(excludes)), "permissions": {"deny": sorted(set(deny))}}


def lead_flags(u: Unit) -> list[str]:
    """Extra flags for a headless Claude lead (ccx sub-agents get the same through unit_env)."""
    return ["--setting-sources", SETTING_SOURCES, "--settings", str(u.settings_file)]


def _git_bash() -> str | None:
    if os.name != "nt":
        return None
    g = shutil.which("git")
    if not g:
        return None
    for cand in (Path(g).resolve().parents[1] / "bin" / "bash.exe", Path(g).resolve().parent / "bash.exe"):
        if cand.exists():
            return str(cand)
    return None


def base_env(src=None) -> dict:
    """The inherited part of a unit's environment: the allow-list only."""
    src = os.environ if src is None else src
    return {k: v for k, v in src.items()
            if k.upper() in ENV_KEEP or k.upper().startswith("LC_") or k.upper().endswith(ENV_KEEP_SUFFIX)
            or (k.upper().startswith("CCX_") and k.upper().endswith("_BIN"))}


def prepare(u: Unit) -> dict:
    """Make the unit's x- folder and return its environment."""
    rmtree(u.x)
    for sub in ("tmp", "dsh-home") + (("claude-config",) if u.claude == "config-dir" else ()):
        (u.x / sub).mkdir(parents=True, exist_ok=True)
    (u.x / "gitconfig").write_text("[user]\n\tname = eval\n\temail = eval@example.invalid\n"
                                   "[init]\n\tdefaultBranch = master\n", encoding="utf-8")
    u.settings_file.write_text(json.dumps(claude_settings(u), indent=1), encoding="utf-8")
    env = base_env()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if "CLAUDE_CODE_GIT_BASH_PATH" not in env and _git_bash():
        env["CLAUDE_CODE_GIT_BASH_PATH"] = _git_bash()     # the user settings that usually set it are not loaded
    tmp = str(u.x / "tmp")
    env.update({
        "PYTHONIOENCODING": "utf-8", "TMP": tmp, "TEMP": tmp, "TMPDIR": tmp,
        "GIT_CONFIG_GLOBAL": str(u.x / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
        "CCX_HUB": str(u.hub), "CCX_CONFIG": str(u.x / "user-config.toml"), "CCX_NO_QUOTA_PROBE": "1",
        "CCX_NO_BENCH_REFRESH": "1", "CCX_EVAL_UNIT": u.key, "CCX_CODEX_ISOLATE": "1",
        "CCX_CLAUDE_SETTING_SOURCES": SETTING_SOURCES, "CCX_CLAUDE_SETTINGS": str(u.settings_file),
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CODEX_HOME": str(u.codex_home or u.real["codex_home"]),
        "CODEX_SQLITE_HOME": str(u.codex_home or u.real["codex_home"]),
        "DSH_HOME": str(u.x / "dsh-home" if u.dsh == "unit" else u.real["dsh_home"]),
    })
    if u.claude == "config-dir":
        env["CLAUDE_CONFIG_DIR"] = str(u.x / "claude-config")
    return env


def env_keys_sha(env: dict) -> str:
    return hashlib.sha256("\n".join(sorted(env)).encode()).hexdigest()[:16]


def rmtree(d: Path) -> bool:
    def onerror(fn, path, _exc):
        try:
            os.chmod(path, 0o700)
            fn(path)
        except OSError:
            pass
    if Path(d).exists():
        shutil.rmtree(d, onerror=onerror)
        return not Path(d).exists()
    return False


# ------------------------------------------------------------------ processes (E2, E4)

def _ps_json(script: str, timeout: int = 60):
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       stdin=subprocess.DEVNULL)
    out = r.stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def snapshot() -> list[dict] | None:
    """Every process: pid, ppid, name, command line (None when it cannot be listed)."""
    try:
        if os.name == "nt":
            rows = _ps_json("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,"
                            "CommandLine | ConvertTo-Json -Compress")
            return [{"pid": int(r.get("ProcessId") or 0), "ppid": int(r.get("ParentProcessId") or 0),
                     "name": str(r.get("Name") or ""), "cmd": str(r.get("CommandLine") or "")} for r in rows]
        r = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "args="], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        out = []
        for line in r.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) >= 2 and parts[0].isdigit():
                cmd = parts[2] if len(parts) > 2 else ""
                out.append({"pid": int(parts[0]), "ppid": int(parts[1]),
                            "name": Path(cmd.split(" ")[0]).name if cmd else "", "cmd": cmd})
        return out
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _env_marker(pid: int, key: str) -> bool:
    """Linux only: does the process carry CCX_EVAL_UNIT=<key> (only that variable is looked for, nothing kept)."""
    try:
        data = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return False
    return f"CCX_EVAL_UNIT={key}".encode() in data.split(b"\0")


def family(procs: list[dict], pid: int) -> tuple[set[int], set[int]]:
    """(ancestors, descendants) of pid in a snapshot."""
    parent = {p["pid"]: p["ppid"] for p in procs}
    anc, cur = set(), pid
    while cur in parent and cur not in anc and len(anc) < 64:
        anc.add(cur)
        cur = parent[cur]
    anc.add(cur)
    kids: dict[int, list[int]] = {}
    for p in procs:
        kids.setdefault(p["ppid"], []).append(p["pid"])
    desc, todo = set(), [pid]
    while todo:
        for k in kids.get(todo.pop(), []):
            if k not in desc and k != pid:
                desc.add(k)
                todo.append(k)
    return anc, desc


def busy(procs: list[dict] | None, me: int | None = None, ours: list[str] | None = None) -> list[str]:
    """Heavy work running outside this process tree: another eval, a pytest, a `ccx run`. `ours`: markers (the work
    dir, the run's label prefix) of processes this run started that left the tree (a detached `ccx run --bg` whose
    starter exited); they and their descendants are not counted."""
    if procs is None:
        return ["cannot list processes"]
    me = os.getpid() if me is None else me
    anc, desc = family(procs, me)
    marks = [m for m in (ours or []) if m]
    for p in procs:
        if marks and any(_has(m, _norm(p["cmd"] or "")) for m in marks):
            desc |= {p["pid"]} | family(procs, p["pid"])[1]
    out = []
    for p in procs:
        if p["pid"] in anc or p["pid"] in desc:
            continue
        if any(h.search(p["cmd"] or "") for h in HEAVY):
            out.append(f"pid {p['pid']} {p['name']}: {(p['cmd'] or '')[:160]}")
    return out


def leftovers(before: list[dict] | None, after: list[dict] | None, markers: list[str], key: str = "",
              me: int | None = None) -> list[dict]:
    """Processes new since `before` that belong to the unit: their command line names its repo, hub, x- folder,
    worktrees or label (Linux: or they carry its CCX_EVAL_UNIT)."""
    if after is None:
        return []
    me = os.getpid() if me is None else me
    anc, _ = family(after, me)
    seen = {(p["pid"], p["cmd"]) for p in before or []}
    out = []
    for p in after:
        if p["pid"] in anc or (p["pid"], p["cmd"]) in seen:
            continue
        cmd = _norm(p["cmd"] or "")
        if any(_has(m, cmd) for m in markers) or (key and sys.platform.startswith("linux")
                                                     and _env_marker(p["pid"], key)):
            out.append({"pid": p["pid"], "name": p["name"], "cmd": (p["cmd"] or "")[:200]})
    return out


def kill(pids: list[int]) -> list[int]:
    """Kill these processes and their trees; returns the ones still alive afterwards."""
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=30)
            else:
                os.kill(pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            pass
    time.sleep(0.5 if pids else 0)
    return [pid for pid in pids if alive(pid)]


def alive(pid: int) -> bool:
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return f'"{pid}"' in r.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                   # a zombie (killed, not yet reaped by its parent) counts as gone
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except (OSError, IndexError):
        return True


def listening_ports(pids: list[int]) -> list[dict]:
    if not pids:
        return []
    try:
        if os.name == "nt":
            rows = _ps_json("Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object "
                            f"{{ @({','.join(map(str, pids))}) -contains $_.OwningProcess }} | Select-Object "
                            "LocalPort,OwningProcess | ConvertTo-Json -Compress")
            return [{"pid": int(r["OwningProcess"]), "port": int(r["LocalPort"])} for r in rows]
        r = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", ",".join(map(str, pids)), "-Fpn"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        out, pid = [], 0
        for line in r.stdout.splitlines():
            if line.startswith("p"):
                pid = int(line[1:])
            elif line.startswith("n") and ":" in line:
                out.append({"pid": pid, "port": int(line.rsplit(":", 1)[1])})
        return out
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return []


class Job:
    """Windows: a Job Object with kill-on-close; everything a child starts stays in it (ccx's detached `--bg`
    processes do not ask to break away). POSIX: the child leads its own session; ccx's own detached children leave
    it, which the command-line / CCX_EVAL_UNIT sweep in after_unit catches."""

    def __init__(self):
        self.h = None
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateJobObjectW.restype = wintypes.HANDLE
            k.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
            k.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
            k.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            k.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
            k.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                    ctypes.c_void_p)
            k.CloseHandle.argtypes = (wintypes.HANDLE,)

            class Basic(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class Io(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

            class Ext(ctypes.Structure):
                _fields_ = [("Basic", Basic), ("Io", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            h = k.CreateJobObjectW(None, None)
            if not h:
                return
            info = Ext()
            info.Basic.LimitFlags = 0x2000              # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
                k.CloseHandle(h)
                return
            self.k, self.ctypes, self.h = k, ctypes, h
        except (OSError, AttributeError):
            self.h = None

    def popen_kw(self) -> dict:
        if os.name == "nt":
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    def add(self, proc: subprocess.Popen) -> bool:
        if not self.h:
            return False
        return bool(self.k.AssignProcessToJobObject(self.h, int(proc._handle)))

    def pids(self) -> list[int]:
        if not self.h:
            return []
        ct = self.ctypes
        n = 4096
        buf = (ct.c_size_t * (n + 2))()
        if not self.k.QueryInformationJobObject(self.h, 3, ct.byref(buf), ct.sizeof(buf), None):
            return []
        listed = buf[0] >> 32 if ct.sizeof(ct.c_size_t) == 8 else buf[1]
        start = 1 if ct.sizeof(ct.c_size_t) == 8 else 2
        return [int(buf[start + i]) for i in range(min(int(listed), n))]

    def close(self) -> None:
        if self.h:
            self.k.TerminateJobObject(self.h, 1)
            self.k.CloseHandle(self.h)
            self.h = None


def run(argv: list[str], *, cwd: Path, env: dict, timeout: float, input: str | None = None,
        job: Job | None = None) -> tuple[str, str, int, list[int]]:
    """subprocess.run, but the child and everything it starts live in `job`; on a timeout the whole job is
    killed, not only the direct child. Returns (stdout, stderr, rc, pids still in the job when it finished)."""
    own = job is None
    job = job or Job()
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", **job.popen_kw())
    job.add(p)
    try:
        out, err = p.communicate(input, timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = [x for x in job.pids() if x != p.pid]
        if job.h:
            job.close()
        elif os.name != "nt":
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
        p.kill()
        out, err = p.communicate()
        return out or "", err or "", -9, timed_out
    left = [x for x in job.pids() if x != p.pid]
    if own:
        job.close()
    return out or "", err or "", rc, left


# ------------------------------------------------------------------ streams: what the agents saw and did

def _events(text: str):
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict):
                yield ev


def check_init(text: str, allowed: list[Path]) -> tuple[list[str], dict]:
    """Problems in a Claude stream's start: hooks that ran, MCP servers, skills, non-builtin plugins, memory paths
    outside the unit. Also returns the init fields worth recording."""
    probs, info = [], {}
    roots = [_norm(p) for p in allowed]
    for ev in _events(text):
        if ev.get("type") == "system" and str(ev.get("subtype", "")).startswith("hook_"):
            probs.append(f"hook ran: {ev.get('hook_name') or ev.get('subtype')}")
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            info = {k: ev.get(k) for k in ("model", "claude_code_version", "apiKeySource") if k in ev}
            if ev.get("mcp_servers"):
                probs.append(f"mcp servers loaded: {len(ev['mcp_servers'])}")
            if ev.get("skills"):
                probs.append(f"skills loaded: {len(ev['skills'])}")
            plugins = ev.get("plugins") or []
            info["plugins"] = len(plugins)
            if any("builtin" not in json.dumps(p) for p in plugins):
                probs.append("non-builtin plugin loaded")
            mem = ev.get("memory_paths") or {}
            for v in (mem.values() if isinstance(mem, dict) else mem):
                if v and not any(_norm(v).startswith(r) for r in roots):
                    probs.append("memory path outside the unit")
    return sorted(set(probs)), info


def tool_inputs(text: str) -> list[str]:
    """Every tool call's input in a Claude stream-json or Codex --json log (inputs, not outputs)."""
    out = []
    for ev in _events(text):
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else None
        for c in (msg or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                out.append(json.dumps(c.get("input"), ensure_ascii=False))
        item = ev.get("item") if isinstance(ev.get("item"), dict) else None
        if item:
            for k in ("command", "changes", "path", "arguments"):
                if item.get(k):
                    out.append(json.dumps(item[k], ensure_ascii=False))
    return out


def path_hits(inputs: list[str], u: Unit) -> list[str]:
    """Tool calls that name a real home, hub or this checkout (Bash is not confined: this is the check)."""
    bad = [_norm(p) for p in forbidden(u)]
    if u.claude == "flags":
        bad += [_norm(p) for p in claude_files(u)]
        bad += [_norm(u.real["claude_home"] / "projects")]
    allowed = [_norm(ROOT / "ccx.py")] + [_norm(u.real["claude_home"] / "projects" / s) for s in unit_slugs(u)]
    hits = []
    for s in inputs:
        t = _norm(s).replace("//", "/")
        for a in allowed:
            t = t.replace(a.replace("//", "/"), "<unit>")
        for b in bad:
            b = b.replace("//", "/").rstrip("/*")
            if b and b in t:
                hits.append(s[:200])
                break
    return hits


def audit(u: Unit, stream: str) -> dict:
    """The unit's lead stream and every ccx sub-agent log in its hub."""
    allowed = [u.x, u.repo, u.hub, u.worktrees] + ([u.claude_dir] if u.claude == "config-dir" else [])
    probs, info = check_init(stream, allowed) if stream else ([], {})
    inputs = tool_inputs(stream)
    for f in sorted((u.hub / "ccx" / "runs").glob("*/events*")) if (u.hub / "ccx" / "runs").exists() else []:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        p2, _ = check_init(text, allowed)
        probs += [f"sub-agent {f.parent.name}: {p}" for p in p2]
        inputs += tool_inputs(text)
    hits = path_hits(inputs, u)
    return {"init": info, "problems": sorted(set(probs)), "path_hits": hits[:20], "n_path_hits": len(hits),
            "clean": not probs and not hits}


# ------------------------------------------------------------------ after a unit (E2)

def unit_slugs(u: Unit) -> list[str]:
    return [slug(u.repo)]


def claude_session_dirs(u: Unit) -> list[Path]:
    """In flags mode: the session folders Claude made in the real ~/.claude for this unit's paths."""
    if u.claude != "flags":
        return []
    out = []
    exact, prefix = slug(u.repo), slug(u.worktrees) + "-"
    for base in (u.real["claude_home"] / "projects", u.real["claude_home"] / "ccx-archive"):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            n = d.name.lower() if os.name == "nt" else d.name
            if n == (exact.lower() if os.name == "nt" else exact) or \
                    n.startswith(prefix.lower() if os.name == "nt" else prefix):
                out.append(d)
    return out


def after_unit(u: Unit, before: list[dict] | None, job_pids: list[int] | None = None,
               keep_repo: bool = True) -> dict:
    """List, kill and log what the unit left: processes (+ ports), worktrees, its x- folder, Claude session folders
    (flags mode). Only things this unit created are removed."""
    after = snapshot()
    procs = leftovers(before, after, u.markers(), u.key)
    pids = sorted({p["pid"] for p in procs} | set(job_pids or []))
    ports = listening_ports(pids)
    still = kill(pids)
    wts = []
    if (u.repo / ".git").exists():
        r = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=u.repo, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        wts = [ln[9:].strip() for ln in r.stdout.splitlines() if ln.startswith("worktree ")][1:]
        if wts:
            subprocess.run(["git", "worktree", "prune"], cwd=u.repo, capture_output=True)
    dirs = []
    if u.worktrees.exists():
        dirs.append(str(u.worktrees))
        rmtree(u.worktrees)
        subprocess.run(["git", "worktree", "prune"], cwd=u.repo, capture_output=True) if u.repo.exists() else None
    for d in claude_session_dirs(u):
        dirs.append(str(d))
        rmtree(d)
    locks = len(list(u.hub.rglob("*.lock"))) if u.hub.exists() else 0
    if u.x.exists():
        dirs.append(str(u.x))
        rmtree(u.x)
    if not keep_repo:
        for d in (u.repo, u.hub):
            if d.exists():
                dirs.append(str(d))
                rmtree(d)
    res = {"procs": [{"pid": p["pid"], "name": p["name"]} for p in procs] +
                    [{"pid": x, "name": "(job)"} for x in job_pids or [] if x not in {p["pid"] for p in procs}],
           "ports": ports, "unkilled": still, "worktrees": len(wts), "removed": len(dirs), "stale_locks": locks,
           "snapshot": after is not None}
    print(f"[clean] {u.key}: leftover procs={len(pids)} ports={len(ports)} unkilled={len(still)} "
          f"worktrees={len(wts)} removed={len(dirs)} locks={locks}", flush=True)
    return res


def hub_memory_empty(hub: Path) -> bool:
    """The shared memory a fresh hub starts with: nothing (no memory files, no ledger rows)."""
    mem = hub / "memory"
    files = [f for f in mem.rglob("*") if f.is_file() and f.stat().st_size] if mem.exists() else []
    led = hub / "ccx" / "ledger.jsonl"
    return not files and not (led.exists() and led.stat().st_size)


# ------------------------------------------------------------------ the check (E3, E4, E5)

def cli_versions(agents=("claude", "codex", "dsh")) -> dict:
    """`<cli> --version` (first line), None when the CLI is not installed."""
    out = {}
    for a in agents:
        b = find_bin(a)
        if not b:
            out[a] = None
            continue
        argv = [sys.executable, b] if b.endswith(".py") else [b]
        try:
            r = subprocess.run([*argv, "--version"], capture_output=True, text=True, timeout=60, encoding="utf-8",
                               errors="replace", stdin=subprocess.DEVNULL)
            out[a] = (r.stdout.strip().splitlines() or [""])[0] if r.returncode == 0 else f"error rc={r.returncode}"
        except (OSError, subprocess.SubprocessError):
            out[a] = "error"
    return out


def commit_state() -> dict:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout.strip()
    st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                        text=True, encoding="utf-8", errors="replace").stdout
    return {"commit": head, "dirty": [ln[3:] for ln in st.splitlines() if ln.strip()][:20]}


def codex_kept_toml(real_home: Path) -> str:
    """The settings a lean Codex start carries over from the person's config.toml (ccx's CODEX_KEEP), as TOML."""
    try:
        cfg = tomllib.loads((real_home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    out = []
    for table, key in CODEX_KEEP:
        v = (cfg.get(table) or {}).get(key)
        if isinstance(v, str):
            out.append(f'[{table}]\n{key} = "{v}"\n')
    return "".join(out)


def check_codex_home(d: Path | None, need: bool, real: dict) -> tuple[list[str], dict]:
    if not need:
        return [], {"mode": "not-used"}
    if not d:
        return [("no eval CODEX_HOME: these arms start Codex, which would load the real CODEX_HOME (its AGENTS.md, "
                 "config, rules, memories). Make an empty folder, log in there yourself once (`CODEX_HOME=<dir> "
                 "codex login`), then pass --codex-home <dir> (or set CCX_EVAL_CODEX_HOME)")], {"mode": "real"}
    probs = []
    d = Path(d).expanduser()
    if not d.is_dir():
        return [f"eval CODEX_HOME {d} does not exist"], {"mode": "eval"}
    if _inside(d, real["codex_home"]) and _inside(real["codex_home"], d):
        probs.append("the eval CODEX_HOME is the real CODEX_HOME")
    if not (d / "auth.json").exists():            # existence only; never opened
        probs.append("the eval CODEX_HOME has no login: run `codex login` with CODEX_HOME set to it yourself")
    for n in CODEX_FORBIDDEN:
        if (d / n).exists():
            probs.append(f"the eval CODEX_HOME has {n} (it would reach every Codex run)")
    cfg = d / "config.toml"
    if not cfg.exists():
        cfg.write_text("# eval CODEX_HOME (scripts/eval/preflight.py): only what ccx carries over on a lean start\n"
                       + codex_kept_toml(real["codex_home"]), encoding="utf-8")
    try:
        data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        data = {}
        probs.append(f"eval CODEX_HOME config.toml unreadable: {e}")
    for t in CODEX_FORBIDDEN_TABLES:
        if data.get(t):
            probs.append(f"eval CODEX_HOME config.toml has [{t}]")
    if (data.get("features") or {}).get("memories") or any((data.get("memories") or {}).values()):
        probs.append("eval CODEX_HOME config.toml turns Codex memories on")
    names = sorted(p.name for p in d.iterdir() if p.name not in ("sessions", "archived_sessions", "log", "tmp"))
    info = {"mode": "eval", "files_sha256": hashlib.sha256("\n".join(names).encode()).hexdigest()[:16],
            "models_cache_sha256": (sha256_file(d / "models_cache.json") or "")[:16] or None}
    return probs, info


def check_workdir(work: Path, real: dict) -> tuple[list[str], list[str]]:
    """The work dir must be the eval's own: only names the eval makes. Stale per-unit leftovers are removed."""
    probs, cleaned = [], []
    for name, p in (("this checkout", real["root"]), ("the real hub", real["hub"]),
                    ("the real Claude home", real["claude_home"]), ("the real Codex home", real["codex_home"])):
        if _inside(work, p):
            probs.append(f"work dir is inside {name}")
    if work.exists():
        odd = [p.name for p in work.iterdir() if not WORK_ENTRY.match(p.name)]
        if odd:
            probs.append(f"work dir has files the eval did not make: {odd[:5]}; pick another --workdir")
        elif not probs:
            for p in work.iterdir():
                if p.name.startswith(("x-", "r5iso-")) or p.name in (".ccx-worktrees", "canary"):
                    cleaned.append(p.name)
                    rmtree(p)
    return probs, cleaned


def real_state(real: dict, work: Path) -> dict:
    """What the run may change in the person's own state, by size and count only (compared before/after)."""
    led = real["hub"] / "ccx" / "ledger.jsonl"
    proj = real["claude_home"] / "projects"
    pre = slug(work).lower() + "-"
    n = sum(1 for d in proj.iterdir() if d.name.lower().startswith(pre)) if proj.is_dir() else 0
    return {"hub_ledger_bytes": led.stat().st_size if led.exists() else 0, "claude_project_dirs_for_work": n}


def canary(work: Path, u_kw: dict, timeout: int = 300) -> dict:
    """One tiny real lead with the unit isolation: its init event must be clean and it must see only the project's
    instructions. Costs one cheap request (haiku, --max-budget-usd 0.05)."""
    d = work / "canary"
    rmtree(d)
    repo = d / "repo"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text(f"When asked which instructions you were given, add the word {CANARY_WORD}.\n",
                                    encoding="utf-8")
    (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    u = Unit(key="canary", work=d, repo=repo, hub=d / "hub", **u_kw)
    (u.hub / "ccx").mkdir(parents=True)
    env = prepare(u)
    b = find_bin("claude")
    if not b:
        return {"ok": False, "problems": ["claude CLI not found"]}
    argv = [*([sys.executable, b] if b.endswith(".py") else [b]), "-p", "--output-format", "stream-json", "--verbose",
            "--model", "haiku", "--effort", "low", "--tools", "Read", "--permission-mode", "dontAsk",
            "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence", "--max-budget-usd", "0.05",
            *lead_flags(u)]
    prompt = ("Answer in one line. Besides this message, which instructions were you given? If the only extra "
              "instructions come from this project's CLAUDE.md / AGENTS.md, reply with exactly PROJECT-ONLY followed "
              "by the word that project file asks for. If any other instructions reached you (a user-level "
              "CLAUDE.md, rules, memory, hooks, an output style, a language preference), reply OTHER: and quote "
              "their first eight words.")
    before = snapshot()
    out, err, rc, left = run(argv, cwd=repo, env=env, timeout=timeout, input=prompt)
    probs, info = check_init(out, [u.x, u.repo, u.hub] + ([u.claude_dir] if u.claude == "config-dir" else []))
    answer = ""
    for ev in _events(out):
        if ev.get("type") == "result":
            answer = str(ev.get("result") or "")
    if rc:
        probs.append(f"canary lead failed rc={rc}: {(answer or err)[-160:]}")
    if "PROJECT-ONLY" not in answer or "OTHER:" in answer:
        probs.append(f"canary saw instructions other than the project's: {answer[:160]!r}")
    if CANARY_WORD not in answer:
        probs.append("canary did not see the project's CLAUDE.md -> AGENTS.md (isolation dropped it)")
    after_unit(u, before, left, keep_repo=False)
    rmtree(d)
    return {"ok": not probs, "problems": probs, "init": info}


@dataclass
class Options:
    work: Path
    arms: list[str]
    jobs: int = 2
    claude: str = "flags"
    codex_home: Path | None = None
    dsh: str = "unit"
    canary: bool = False
    force_unclean: bool = False
    tasks_file: Path = TASKS_FILE


def run_checks(o: Options) -> dict:
    """Every check; `ok` is False when any problem was found. Nothing here reads a credential."""
    real = real_paths()
    probs: list[str] = []
    procs = snapshot()
    other = busy(procs)
    probs += [f"busy: {x}" for x in other]
    cs = commit_state()
    if cs["dirty"]:
        probs.append(f"eval checkout has uncommitted changes to tracked files: {cs['dirty'][:5]}")
    need_codex = any(a in CODEX_ARMS for a in o.arms)
    versions = cli_versions()
    if not versions.get("claude") or str(versions["claude"]).startswith("error"):
        probs.append("claude --version failed: the leads cannot start")
    if need_codex and (not versions.get("codex") or str(versions["codex"]).startswith("error")):
        probs.append("codex --version failed")
    p2, codex = check_codex_home(o.codex_home, need_codex, real)
    probs += p2
    if o.claude == "config-dir" and "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:     # name only
        probs.append("--claude-isolation config-dir needs CLAUDE_CODE_OAUTH_TOKEN (run `claude setup-token` and "
                     "export it yourself); a fresh CLAUDE_CONFIG_DIR has no login")
    if o.dsh == "real" and versions.get("dsh") and (real["dsh_home"] / "AGENTS.md").exists():
        probs.append("--dsh-home real: dsh would load the real DSH_HOME/AGENTS.md")
    p3, cleaned = check_workdir(o.work, real)
    probs += p3
    if not p3:
        o.work.mkdir(parents=True, exist_ok=True)
        (o.work / ".ccx-eval-work").write_text("made by scripts/eval/preflight.py\n", encoding="utf-8")
    can = None
    if o.canary and not p3:
        can = canary(o.work, {"claude": o.claude, "codex_home": o.codex_home, "dsh": o.dsh})
        probs += can["problems"]
    rep = {"ok": not probs, "problems": probs, "commit": cs["commit"], "dirty": bool(cs["dirty"]),
           "tasks_sha256": (sha256_file(o.tasks_file) or "")[:16], "cli": versions, "codex": codex,
           "claude_isolation": o.claude, "dsh_home": o.dsh, "jobs": o.jobs, "busy": len(other),
           "canary": None if can is None else ("pass" if can["ok"] else "fail"),
           "canary_init": (can or {}).get("init"), "cleaned": cleaned, "real_state": real_state(real, o.work),
           "force_unclean": o.force_unclean, "codex_home": str(o.codex_home) if o.codex_home else None}
    rep["result"] = "pass" if rep["ok"] else ("forced" if o.force_unclean else "fail")
    return rep


def fingerprint(rep: dict, u: Unit, env: dict) -> dict:
    """What every result row carries about the environment it ran in."""
    return {"commit": rep["commit"][:12], "dirty": rep["dirty"], "tasks_sha256": rep["tasks_sha256"],
            "cli": rep["cli"], "concurrency": rep["jobs"], "preflight": rep["result"],
            "force_unclean": rep["force_unclean"], "canary": rep.get("canary"),
            "isolation": {"claude": u.claude, "setting_sources": SETTING_SOURCES, "hooks": "disabled",
                          "auto_memory": "off", "codex_home": rep["codex"].get("mode"),
                          "codex_isolate": env.get("CCX_CODEX_ISOLATE") == "1", "dsh_home": u.dsh,
                          "git_config": "eval", "tmp": "unit", "bash_unconfined": True,
                          "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN" in env},
            "codex_home_files": rep["codex"].get("files_sha256"),
            "models_cache": rep["codex"].get("models_cache_sha256"),
            "env_keys_sha256": env_keys_sha(env)}


def between_units(rep: dict, need_codex: bool, ours: list[str] | None = None) -> list[str]:
    """Checked after every unit: same CLI versions, same eval Codex model list, nothing heavy started outside."""
    probs = []
    now = cli_versions()
    for a, v in rep["cli"].items():
        if now.get(a) != v:
            probs.append(f"{a} version changed: {v} -> {now.get(a)}")
    if need_codex and rep["codex"].get("mode") == "eval" and rep.get("codex_home"):
        m = (sha256_file(Path(rep["codex_home"]) / "models_cache.json") or "")[:16] or None
        if m != rep["codex"].get("models_cache_sha256"):
            probs.append("eval CODEX_HOME models_cache.json changed")
    probs += [f"busy: {x}" for x in busy(snapshot(), ours=ours)]
    return probs


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_options(ap)
    ap.add_argument("--arms", default="self,builtin,ccx,direct")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--canary", action="store_true", help="also run one tiny real lead (one cheap request)")
    return ap


def add_options(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--claude-isolation", choices=("flags", "config-dir"), default="flags",
                    help="flags: setting sources, settings and deny rules (login stays in the real ~/.claude); "
                         "config-dir: a fresh CLAUDE_CONFIG_DIR per unit (needs CLAUDE_CODE_OAUTH_TOKEN)")
    ap.add_argument("--codex-home", default=os.environ.get("CCX_EVAL_CODEX_HOME", ""),
                    help="a dedicated CODEX_HOME you logged in to once (default: $CCX_EVAL_CODEX_HOME)")
    ap.add_argument("--dsh-home", choices=("unit", "real"), default="unit")
    ap.add_argument("--force-unclean", action="store_true",
                    help="run although a check failed (recorded in every row)")


def options_from(a, arms: list[str], work: Path, canary_on: bool) -> Options:
    return Options(work=work, arms=arms, jobs=getattr(a, "jobs", 2), claude=a.claude_isolation,
                   codex_home=Path(a.codex_home).expanduser() if a.codex_home else None, dsh=a.dsh_home,
                   canary=canary_on, force_unclean=a.force_unclean)


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    rep = run_checks(options_from(a, a.arms.split(","), Path(a.workdir), a.canary))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
