"""A clean room for evaluation units, and the check that refuses to start without one (E1-E5).

What it guarantees, by mechanism (command-line flags, environment, settings files), not by what the prompt says:

  E1 every unit from zero   a fresh repo copy and hub (the caller), plus a per-unit folder x-<key>/ holding the
                            unit's TMP/TEMP, a git config with a neutral identity, CCX_CONFIG, a fresh DSH_HOME, a
                            home for Codex / dsh (CCX_AGENT_HOME: their HOME / USERPROFILE, so Codex does not load the
                            person's ~/.agents/skills) and the Claude settings below. The environment is built from an
                            allow-list, so host and session variables (CLAUDE_CODE_*, TASK_ROUTING_HOME, ...) do not
                            pass. Claude, lead and ccx sub-agents alike: `--setting-sources project,local` (no user
                            settings.json, so none of its hooks, `language` or `env`), a settings file with
                            disableAllHooks, auto-memory off, claudeMdExcludes for the user-level CLAUDE.md and rules,
                            and permission deny rules (written the way Claude Code matches Windows paths, //c/...) for
                            the real ~/.codex, ~/.ccx, ~/.agents, the real hub, this checkout and the private parts of
                            ~/.claude (CLAUDE.md, rules, settings and their backups, skills, plugins, every project's
                            memory and transcripts, file history, sessions, ...). ccx sub-agents get the same through
                            CCX_CLAUDE_SETTING_SOURCES / CCX_CLAUDE_SETTINGS / CCX_CLAUDE_NO_SKILLS (opt-in knobs in
                            ccx/agents/claude.py). `--claude-isolation config-dir` goes further: CLAUDE_CONFIG_DIR is
                            a fresh folder per unit (needs CLAUDE_CODE_OAUTH_TOKEN, which the person exports; it is
                            passed through by name and never read). Codex: a dedicated eval CODEX_HOME the person
                            logged in to once (`--codex-home`), and CCX_CODEX_ISOLATE=1 (--ignore-user-config,
                            --ignore-rules, memories off on every Codex run).
  E2 no leftovers           every process a unit starts runs in a Windows Job Object (started suspended, so nothing
                            escapes before it is in the job; POSIX: its own session, plus a marker variable
                            CCX_EVAL_UNIT); after the unit the job's survivors (killed by closing the job, never by a
                            pid that may have been reused), and any new process whose command line names the unit's
                            repo, hub or label, are listed (with listening ports), killed and logged in one line. The
                            unit's x- folder, its ccx worktrees and (in flags mode) the Claude session folders named
                            after its paths or its session ids are removed. A process that cannot be killed stops the
                            run.
  E3 same inputs            the fingerprint: eval checkout commit (refused when tracked files are modified or untracked
                            files sit in ccx/, scripts/, config/, skills/), sha256 of the task file and of
                            config/tiers.toml, `claude --version` / `codex --version` / `dsh --version`, the models
                            (lead, effort, worker; the lead's model from its own stream), python / pytest / OS; the
                            commit, task file and CLI versions are checked again after every unit (a change stops the
                            run); the eval CODEX_HOME's file names and the hash of its model list; an empty shared
                            memory in the fresh hub.
  E4 no interference        refuses to start while another eval, pytest, `ccx run/discuss/resume`, `codex exec` or
                            `claude -p` runs outside this process tree, or another process names the work dir; the
                            concurrency (--jobs) is recorded; a watcher samples the machine every minute while the run
                            goes on, and between units.
  E5 this script            `run_checks()` collects every problem; any problem blocks the run unless --force-unclean,
                            which is recorded in every row. Checking alone (`preflight.py`, no `--start`) changes
                            nothing on disk. Each row gets `fingerprint()`, an `audit` of its own streams (init event:
                            no hooks, MCP servers, skills, slash commands, non-builtin plugins or agents, memory paths
                            inside the unit; no tool call naming a real home, hub or this checkout, also spelled with
                            ~, $HOME, %USERPROFILE% or /c/...) and its `leftovers`; `env_clean` is false when any of
                            them found something, when processes could not be listed, or when the machine changed
                            between units.

What it cannot block by mechanism (recorded instead): a Bash command (Claude) or a shell command (Codex, dsh) can
still read any file the user can, since neither sandbox confines reads on Windows; the audit scans every tool call
afterwards, which a determined spelling can still evade. In flags mode Claude keeps the real ~/.claude for login, so
it still writes ~/.claude.json project entries (a tool's own config file: not edited here) and shell snapshots.

  python scripts/eval/preflight.py --arms ccx,ccx2 --workdir <dir> --codex-home <dir>     # check only, no changes
  python scripts/eval/preflight.py ... --canary                                          # + one tiny real lead
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402  (puts ROOT on sys.path)

from ccx.agents.codex import CODEX_KEEP  # noqa: E402
from ccx.runners import find_bin  # noqa: E402

TASKS_FILE = Path(__file__).resolve().parent / "tasks_r5.py"
TIERS_FILE = ROOT / "config" / "tiers.toml"
SETTING_SOURCES = "project,local"
CODEX_ARMS = ("ccx", "ccx2", "direct")          # arms whose units start Codex (ccx routes to it)
# Names a dedicated eval CODEX_HOME must not have: each would bring the person's rules, memory or tools back.
# (skills/ is checked separately: Codex installs its own system skills in skills/.system by itself.)
CODEX_FORBIDDEN = ("AGENTS.md", "AGENTS.override.md", "memories", "rules", "plugins", "hooks")
CODEX_FORBIDDEN_TABLES = ("mcp_servers", "plugins", "hooks", "profiles", "marketplaces")
# Allow-list of inherited variables. Everything else (session ids, host auth helpers, TASK_ROUTING_HOME, ...) is
# dropped; what a unit needs is set explicitly in prepare().
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
         re.compile(r"\bccx(\.py|\.exe|\.cmd)?[\"']?\s+(run|discuss|resume)\b", re.I),
         re.compile(r"\bcodex(\.exe|\.cmd)?[\"']?(\s+-c\s+(\"[^\"]*\"|\S+))*\s+exec(\s|$)", re.I),
         re.compile(r"\bclaude(\.exe|\.cmd)?[\"']?\s(.*\s)?(-p|--print)(\s|$)", re.I))
WORK_ENTRY = re.compile(r"^(\d+-[\w.-]+|h-\d+-[\w.-]+|x-[\w.-]+|r5iso-\w+|\.ccx-worktrees|canary|"
                        r"[\w.-]+\.stream\.jsonl|preflight[\w.-]*\.json|\.ccx-eval-work|ext-cache)$")
# Shells and wrappers: the command they carry runs in a child of theirs, which is what busy() and naming() look at
# (Git Bash on Windows also breaks the parent chain, so this run's own launching shell is not seen as its ancestor)
SHELLS = re.compile(r"^(bash|sh|dash|zsh|fish|cmd|powershell|pwsh|timeout|conhost|wsl|env|nohup|start|mintty)"
                    r"(\.exe)?$", re.I)
CANARY_WORD, CANARY_SECRET = "KIWI-7", "PLUM-3"
# The agents a plain headless Claude Code 2.1.309 lists in its init event (seen in every round-5 stream)
BUILTIN_AGENTS = {"claude", "Explore", "general-purpose", "Plan", "statusline-setup", "output-style-setup"}
# Private parts of a Claude home: (path relative to it, kind) - d: a folder, f: a file, g: a glob
CLAUDE_PRIVATE = (("CLAUDE.md", "f"), ("rules", "d"), ("settings.json", "f"), ("settings.local.json", "f"),
                  ("settings.json.*", "g"), ("agents", "d"), ("commands", "d"), ("skills", "d"), ("plugins", "d"),
                  ("ccx-archive", "d"), ("history.jsonl", "f"), ("todos", "d"), ("output-styles", "d"),
                  ("file-history", "d"), ("sessions", "d"), ("session-env", "d"), ("shell-snapshots", "d"),
                  ("backups", "d"), ("plans", "d"), (".credentials.json", "f"), ("projects/*/memory", "d"),
                  ("projects/*/*.jsonl", "g"), ("projects/*/*/subagents", "d"))


def sha256_file(f: Path) -> str | None:
    try:
        return hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        return None


def slug(path: Path | str) -> str:
    """Claude Code's folder name for a working directory (every non-alphanumeric character becomes '-')."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _norm(s) -> str:
    s = str(s).replace("\\\\", "/").replace("\\", "/")
    return s.lower() if os.name == "nt" else s


def _has(marker: str, text: str) -> bool:
    """`marker` in `text` as a whole path or label: /w/1-t-ccx matches /w/1-t-ccx/x but not /w/1-t-ccx2."""
    if not marker:
        return False
    tail = "" if marker[-1] in "/:" else r"(?![A-Za-z0-9_.-])"     # "eval-r5:<tag>:" is a prefix on purpose
    return re.search(re.escape(marker) + tail, text) is not None


def _under(path: str, roots: list[str]) -> bool:
    """Normalized `path` is one of `roots` or inside one (a whole path component: /w/a is not under /w/ab)."""
    p = _norm(path).rstrip("/")
    for r in roots:
        r = r.rstrip("/")
        if r and (p == r or p.startswith(r + "/")):
            return True
    return False


# ------------------------------------------------------------------ the person's real homes

def other_worktrees(root: Path) -> list[Path]:
    """The checkout's other git worktrees (the main one or siblings): they hold today's code and its history, the
    answers to every task taken from this repository's past."""
    try:
        r = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    here = Path(root).resolve()
    out = []
    for ln in r.stdout.splitlines():
        if ln.startswith("worktree "):
            p = Path(ln[9:].strip())
            if p.resolve() != here:
                out.append(p)
    return out


def real_paths(env=None) -> dict[str, Path]:
    """Where the person's own state lives, from the environment this eval was started in."""
    env = os.environ if env is None else env
    home = Path.home()
    out = {"home": home, "claude_home": Path(env.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser(),
           "claude_json": home / ".claude.json", "home_claude": home / ".claude", "home_codex": home / ".codex",
           "codex_home": Path(env.get("CODEX_HOME") or home / ".codex").expanduser(), "ccx_home": home / ".ccx",
           "ccx_config": Path(env.get("CCX_CONFIG") or home / ".ccx" / "config.toml").expanduser(),
           "dsh_home": Path(env.get("DSH_HOME") or home / ".dsh").expanduser(), "agents_home": home / ".agents",
           "root": ROOT, "root_worktrees": other_worktrees(ROOT)}
    hub = env.get("CCX_HUB")
    if not hub:
        try:
            hub = tomllib.loads(out["ccx_config"].read_text(encoding="utf-8")).get("hub")
        except (OSError, tomllib.TOMLDecodeError):
            hub = None
    out["hub"] = Path(hub).expanduser() if hub else home / ".ccx-hub"       # ccx/config.py hub_dir()'s default
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
    agents: tuple = ()                    # agents the eval itself defines (--agents), allowed in the init event
    hidden: tuple = ()                    # more folders its agents must not open (the other repositories' cache)
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
    def agent_home(self) -> Path:
        return self.x / "agent-home"

    @property
    def claude_dir(self) -> Path:
        return self.x / "claude-config" if self.claude == "config-dir" else self.real["claude_home"]

    def markers(self) -> list[str]:
        """Strings that name this unit in a process's command line."""
        out = [_norm(self.repo), _norm(self.hub), _norm(self.x), _norm(self.worktrees)]
        return out + ([_norm(self.label)] if self.label else [])

    def session_prefixes(self) -> list[str]:
        """Claude's folder names (in <claude home>/projects) for this unit's own working directories (the second is
        a prefix: one folder per ccx worktree)."""
        return [slug(self.repo), slug(self.worktrees) + "-"]

    def own_project_dirs(self) -> list[str]:
        """The same as normalized full paths under the Claude home in use."""
        proj = _norm(Path(self.claude_dir) / "projects")
        return [f"{proj}/{_norm(s)}" for s in self.session_prefixes()]


def _rule_path(p) -> str:
    """A path as a permission rule writes it: //<absolute posix path>. Windows: Claude Code matches C:\\Users\\a as
    /c/Users/a (permissions docs, "use //c/**/.env to match .env files anywhere on that drive")."""
    s = Path(p).as_posix() if not isinstance(p, str) else p.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/*(.*)$", s)
    if m:
        rest = m.group(2).rstrip("/")
        return f"//{m.group(1).lower()}" + (f"/{rest}" if rest else "")
    return "//" + s.lstrip("/")


def forbidden(u: Unit) -> list[Path]:
    """Folders a unit's agents must not open: the person's homes, hub, config, skills and this checkout. A
    dedicated eval CODEX_HOME that overlaps one of them is refused by check_codex_home, never un-denied here."""
    r = u.real
    out = [r["home_codex"], r["codex_home"], r["ccx_home"], r["hub"], r["dsh_home"], r["agents_home"]]
    if u.claude == "config-dir":
        out += [r["home_claude"], r["claude_home"]]
    if not _inside(u.work, r["root"]):
        out.append(r["root"])
    out += [p for p in r.get("root_worktrees") or [] if not _inside(u.work, p)]
    out += [Path(p) for p in u.hidden]
    if u.dsh == "real":
        out = [p for p in out if p != r["dsh_home"]]
    uniq: list[Path] = []
    for p in out:
        if p not in uniq and not _inside(u.work, p):
            uniq.append(p)
    return uniq


def _claude_private(u: Unit) -> list[tuple[str, str]]:
    """(posix path or glob, kind) of the private parts of the real Claude home(s)."""
    out = set()
    for base in {u.real["home_claude"], u.real["claude_home"]}:
        for rel, kind in CLAUDE_PRIVATE:
            out.add((Path(base).as_posix().rstrip("/") + "/" + rel, kind))
    return sorted(out)


def claude_files(u: Unit) -> list[str]:
    """Rule patterns for the private parts of the real Claude home in flags mode (the folder itself stays reachable:
    it holds the login, and the lead reads its own tool-result files under projects/<its folder>/)."""
    return sorted({_rule_path(p) + ("/**" if kind == "d" else "") for p, kind in _claude_private(u)})


def claude_settings(u: Unit, extra_deny: list[str] = ()) -> dict:
    deny = list(extra_deny)
    for p in forbidden(u):
        deny += [f"Read({_rule_path(p)}/**)", f"Edit({_rule_path(p)}/**)"]
    deny += [f"Read({_rule_path(u.real['claude_json'])})", f"Edit({_rule_path(u.real['claude_json'])})"]
    if u.claude == "flags":
        deny += [f"{t}({p})" for p in claude_files(u) for t in ("Read", "Edit")]
    excludes = []
    home = Path(u.real["home"])
    for base in {u.real["home_claude"], u.real["claude_home"]}:
        for p in (Path(base) / "CLAUDE.md", Path(base) / "rules" / "**"):
            excludes += [p.as_posix(), _rule_path(p)[1:]]
    # whatever spelling Claude matches the absolute path in: the user-level files by their tail
    excludes += [f"**/{home.name}/.claude/CLAUDE.md", f"**/{home.name}/.claude/rules/**"]
    return {"disableAllHooks": True, "hooks": {}, "autoMemoryEnabled": False,
            "claudeMdExcludes": sorted(set(excludes)), "permissions": {"deny": sorted(set(deny))}}


def lead_flags(u: Unit) -> list[str]:
    """Extra flags for a headless Claude lead (ccx sub-agents get the same through prepare's environment)."""
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


def prepare(u: Unit, extra_deny: list[str] = ()) -> dict:
    """Make the unit's x- folder and return its environment. Stale Claude session folders named after the unit's
    paths (an earlier run with the same work dir) are removed first, so its auto-memory folder starts empty."""
    rmtree(u.x)
    for d in claude_session_dirs(u):
        rmtree(d)
    for sub in ("tmp", "dsh-home", "agent-home") + (("claude-config",) if u.claude == "config-dir" else ()):
        (u.x / sub).mkdir(parents=True, exist_ok=True)
    (u.x / "gitconfig").write_text("[user]\n\tname = eval\n\temail = eval@example.invalid\n"
                                   "[init]\n\tdefaultBranch = master\n", encoding="utf-8")
    u.settings_file.write_text(json.dumps(claude_settings(u, extra_deny), indent=1), encoding="utf-8")
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
        "CCX_CLAUDE_NO_SKILLS": "1", "CCX_AGENT_HOME": str(u.agent_home),
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "DISABLE_AUTOUPDATER": "1",
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
        # -ww: procps cuts every line at 80 columns when its output is a pipe, which hid the unit's path (the
        # marker) at the end of a long command line. stat= lets parse_ps drop zombies: nothing left to kill.
        r = subprocess.run(["ps", "-A", "-ww", "-o", "pid=", "-o", "ppid=", "-o", "stat=", "-o", "args="],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0 and not r.stdout.strip():
            return None  # e.g. a ps without these options: "cannot list", not "nothing running"
        return parse_ps(r.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def parse_ps(text: str) -> list[dict]:
    """Rows of `ps -o pid= -o ppid= -o stat= -o args=`; zombies (dead, not yet reaped) are left out."""
    out = []
    for line in text.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            if parts[2].startswith("Z"):
                continue
            cmd = parts[3] if len(parts) > 3 else ""
            out.append({"pid": int(parts[0]), "ppid": int(parts[1]),
                        "name": Path(cmd.split(" ")[0]).name if cmd else "", "cmd": cmd})
    return out


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


def busy(procs: list[dict] | None, me: int | None = None, ours: list[str] | None = None,
         exclude: set[int] | None = None) -> list[str]:
    """Heavy work running outside this process tree: another eval, a pytest, a `ccx run`, a headless `claude -p` or
    `codex exec`. `ours`: markers (the work dir, the run's label prefix) of processes this run started that left the
    tree (a detached `ccx run --bg` whose starter exited); they, the processes in this run's jobs (`exclude`) and
    their descendants are not counted."""
    if procs is None:
        return ["cannot list processes"]
    me = os.getpid() if me is None else me
    anc, desc = family(procs, me)
    marks = [m for m in (ours or []) if m]
    for p in procs:
        if (marks and any(_has(m, _norm(p["cmd"] or "")) for m in marks)) or p["pid"] in (exclude or ()):
            desc |= {p["pid"]} | family(procs, p["pid"])[1]
    out = []
    for p in procs:
        if p["pid"] in anc or p["pid"] in desc:
            continue
        if not SHELLS.match(p["name"] or "") and any(h.search(p["cmd"] or "") for h in HEAVY):
            out.append(f"pid {p['pid']} {p['name']}: {(p['cmd'] or '')[:160]}")
    return out


def naming(procs: list[dict] | None, path: Path, me: int | None = None) -> list[str]:
    """Processes outside this tree whose command line names `path` (another eval using the same work dir)."""
    if not procs:
        return []
    me = os.getpid() if me is None else me
    anc, desc = family(procs, me)
    m = _norm(path)
    return [f"pid {p['pid']} {p['name']}: {(p['cmd'] or '')[:160]}" for p in procs
            if p["pid"] not in anc | desc and not SHELLS.match(p["name"] or "") and _has(m, _norm(p["cmd"] or ""))]


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
                try:                       # a detached leftover leads its own process group: take the group too
                    if os.getpgid(pid) == pid and pid != os.getpgid(0):
                        os.killpg(pid, signal.SIGKILL)
                except OSError:
                    pass
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
    # a zombie (killed, not yet reaped by its parent) counts as gone; macOS has no /proc, so ask ps there
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        pass
    try:
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return True
    st = r.stdout.strip()
    return bool(st) and not st.startswith("Z")


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


_JOBS: set = set()                        # live jobs of this run (their processes are this run's, see busy())
_JOBS_LOCK = threading.Lock()


def job_pids_all() -> set[int]:
    with _JOBS_LOCK:
        jobs = list(_JOBS)
    return {x for j in jobs for x in j.pids()}


class Job:
    """Windows: a Job Object with kill-on-close; a child is started suspended, put in the job, then resumed, so
    everything it starts stays in it (ccx's detached `--bg` processes do not ask to break away). POSIX: the child
    leads its own session; ccx's own detached children leave it, which the command-line / CCX_EVAL_UNIT sweep in
    after_unit catches."""

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
            nt = ctypes.WinDLL("ntdll")
            nt.NtResumeProcess.argtypes = (wintypes.HANDLE,)

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
            self.k, self.nt, self.ctypes, self.h = k, nt, ctypes, h
            with _JOBS_LOCK:
                _JOBS.add(self)
        except (OSError, AttributeError):
            self.h = None

    def popen_kw(self) -> dict:
        if os.name == "nt":
            # CREATE_SUSPENDED (0x4) when there is a job: nothing runs before start() has put it in the job
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | (0x4 if self.h else 0)}
        return {"start_new_session": True}

    def start(self, proc: subprocess.Popen) -> bool:
        """Put a child started with popen_kw() in the job, then let it run."""
        if not self.h:
            return False
        ok = bool(self.k.AssignProcessToJobObject(self.h, int(proc._handle)))
        self.nt.NtResumeProcess(int(proc._handle))
        return ok

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

    def terminate(self) -> None:
        """Kill everything in the job; the job stays usable."""
        if self.h:
            self.k.TerminateJobObject(self.h, 1)

    def close(self) -> None:
        if self.h:
            self.k.TerminateJobObject(self.h, 1)
            self.k.CloseHandle(self.h)
            self.h = None
            with _JOBS_LOCK:
                _JOBS.discard(self)


def run(argv: list[str], *, cwd: Path, env: dict, timeout: float, input: str | None = None,
        job: Job | None = None) -> tuple[str, str, int, list[int]]:
    """subprocess.run, but the child and everything it starts live in `job`; on a timeout the whole job is
    killed, not only the direct child. Returns (stdout, stderr, rc, pids still in the job when it finished)."""
    own = job is None
    job = job or Job()
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", **job.popen_kw())
    job.start(p)
    try:
        out, err = p.communicate(input, timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        timed_out = [x for x in job.pids() if x != p.pid]
        if job.h:
            job.terminate()
        elif os.name != "nt":
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
        p.kill()
        out, err = p.communicate()
        if own:
            job.close()
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


def _builtin_plugin(p) -> bool:
    if not isinstance(p, dict):
        return False
    return str(p.get("source") or "").endswith("@builtin") or p.get("path") == "builtin"


def check_init(text: str, allowed: list[Path], prefixes: list[str] = (), agents: set[str] = frozenset()
               ) -> tuple[list[str], dict]:
    """Problems in a Claude stream's start: hooks that ran, MCP servers, skills, slash commands, an output style,
    non-builtin plugins or agents, memory paths outside the unit (`allowed` folders; `prefixes`: folder-name prefixes
    paths of the unit's own <claude home>/projects/<folder>, one ending in "-" a prefix). Also returns the init
    fields worth recording."""
    probs, info = [], {}
    roots = [_norm(p) for p in allowed]
    ok_agents = BUILTIN_AGENTS | set(agents)
    for ev in _events(text):
        if ev.get("type") == "system" and str(ev.get("subtype", "")).startswith("hook_"):
            probs.append(f"hook ran: {ev.get('hook_name') or ev.get('subtype')}")
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            info = {k: ev.get(k) for k in ("model", "claude_code_version", "apiKeySource", "session_id") if k in ev}
            if ev.get("mcp_servers"):
                probs.append(f"mcp servers loaded: {len(ev['mcp_servers'])}")
            if ev.get("skills"):
                probs.append(f"skills loaded: {len(ev['skills'])}")
            if ev.get("slash_commands"):
                probs.append(f"slash commands loaded: {len(ev['slash_commands'])}")
            if ev.get("output_style") not in (None, "", "default"):
                probs.append(f"output style: {ev.get('output_style')}")
            plugins = ev.get("plugins") or []
            info["plugins"] = len(plugins)
            if any(not _builtin_plugin(p) for p in plugins):
                probs.append("non-builtin plugin loaded")
            extra = sorted(str(a) for a in (ev.get("agents") or []) if str(a) not in ok_agents)
            if extra:
                probs.append(f"agents loaded: {extra[:5]}")
            mem = ev.get("memory_paths") or {}
            for v in (mem.values() if isinstance(mem, dict) else mem):
                if not v or _under(str(v), roots):
                    continue
                folder = _norm(v).rstrip("/")
                folder = folder.rsplit("/", 1)[0] if folder.endswith("/memory") else folder
                own = any(folder == pf or (pf.endswith("-") and folder.startswith(pf) and "/" not in folder[len(pf):])
                          for pf in (_norm(x) for x in prefixes))
                if not own:
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


def session_ids(text: str) -> list[str]:
    return sorted({str(ev["session_id"]) for ev in _events(text)
                   if ev.get("type") == "system" and ev.get("subtype") == "init" and ev.get("session_id")})


_B = r"(^|[\s\"'=(:;,|&<>`])"            # what may stand before a path in a command


def canon(text: str, home: Path) -> str:
    """A tool call's text with every spelling of a path made comparable: backslashes and doubled slashes, ~, $HOME,
    ${HOME}, $env:USERPROFILE, %USERPROFILE% and (Windows) Git Bash's /c/... drive form; lower case on Windows."""
    h = Path(home).as_posix()
    t = str(text).replace("\\\\", "/").replace("\\", "/")
    t = re.sub(r"(?i)\$\{?env:userprofile\}?|%userprofile%|%homedrive%%homepath%|\$\{home\}|\$home\b|"
               r"\$\{userprofile\}|\$userprofile\b", lambda _m: h, t)
    t = re.sub(_B + r"~(?=/|$|[\s\"'`;)])", lambda m: m.group(1) + h, t)
    t = re.sub(r"/{2,}", "/", t)
    if os.name == "nt":
        t = re.sub(_B + r"/([A-Za-z])(?=/|$|[\s\"'`;)])", lambda m: f"{m.group(1)}{m.group(2)}:", t)
    return t.lower() if os.name == "nt" else t


def _pattern(p: str) -> re.Pattern:
    """A canonical path or glob (*, **) as a regex that matches it as a whole path component."""
    rx = re.escape(p.rstrip("/")).replace(r"\*\*", ".*").replace(r"\*", r"[^/\s\"']*")
    return re.compile(rx + r"(?![A-Za-z0-9_.-])")


def path_hits(inputs: list[str], u: Unit) -> list[str]:
    """Tool calls that name a real home, hub, skills or this checkout (shell commands are not confined: this is the
    check), in any of the spellings canon() understands."""
    home = u.real["home"]
    c = lambda p: canon(Path(p).as_posix() if not isinstance(p, str) else p, home)      # noqa: E731
    bad = [_pattern(c(p)) for p in forbidden(u)] + [_pattern(c(u.real["claude_json"]))]
    if u.claude == "flags":
        bad += [_pattern(c(p)) for p, _k in _claude_private(u)]
        bad += [_pattern(c(Path(u.real["claude_home"]) / "projects"))]
    proj = c(Path(u.real["claude_home"]) / "projects") + "/"
    allowed = [re.compile(re.escape(c(ROOT / "ccx.py")) + r"(?![A-Za-z0-9_.-])")]
    for s in u.session_prefixes():
        tail = "" if s.endswith("-") else r"(?![A-Za-z0-9_.-])"
        allowed.append(re.compile(re.escape(proj + canon(s, home)) + (r"[^/\s\"']*" if not tail else "") + tail))
    hits = []
    for s in inputs:
        t = canon(s, home)
        for a in allowed:
            t = a.sub("<unit>", t)
        if any(b.search(t) for b in bad):
            hits.append(s[:200])
    return hits


def audit(u: Unit, stream: str) -> dict:
    """The unit's lead stream and every ccx sub-agent log in its hub."""
    allowed = [u.x, u.repo, u.hub, u.worktrees] + ([u.claude_dir] if u.claude == "config-dir" else [])
    pre = u.own_project_dirs()
    probs, info = check_init(stream, allowed, pre, set(u.agents)) if stream else ([], {})
    inputs = tool_inputs(stream)
    sids = session_ids(stream)
    runs = u.hub / "ccx" / "runs"
    for f in sorted(runs.glob("*/events*")) if runs.exists() else []:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        p2, _ = check_init(text, allowed, pre)
        probs += [f"sub-agent {f.parent.name}: {p}" for p in p2]
        inputs += tool_inputs(text)
        sids += session_ids(text)
    hits = path_hits(inputs, u)
    return {"init": info, "problems": sorted(set(probs)), "path_hits": hits[:20], "n_path_hits": len(hits),
            "session_ids": sorted(set(sids)), "clean": not probs and not hits}


# ------------------------------------------------------------------ after a unit (E2)

def claude_session_dirs(u: Unit, sids: list[str] = ()) -> list[Path]:
    """In flags mode: what Claude made in the real ~/.claude for this unit: project folders named after its paths
    (projects/, ccx-archive/) and, for its session ids, file-history/<id> and session-env/<id>."""
    if u.claude != "flags":
        return []
    out = []
    nt = os.name == "nt"
    exact, prefix = slug(u.repo), slug(u.worktrees) + "-"
    if nt:
        exact, prefix = exact.lower(), prefix.lower()
    home = Path(u.real["claude_home"])
    for base in (home / "projects", home / "ccx-archive"):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            n = d.name.lower() if nt else d.name
            if n == exact or n.startswith(prefix):
                out.append(d)
    for sid in sids:
        if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", sid):
            continue
        for sub in ("file-history", "session-env"):
            d = home / sub / sid
            if d.exists():
                out.append(d)
    return out


def after_unit(u: Unit, before: list[dict] | None, job: Job | None = None, sids: list[str] = (),
               keep_repo: bool = True) -> dict:
    """List, kill and log what the unit left: processes (+ ports), worktrees, lock files, its x- folder, Claude
    session folders (flags mode). Only things this unit created are removed. The job's processes are killed by
    closing the job (never by pid, which Windows may have given to someone else by then); the others (they name
    the unit in their command line) only after a fresh look confirms the same pid still runs the same command."""
    after = snapshot()
    procs = leftovers(before, after, u.markers(), u.key)
    in_job = [x for x in (job.pids() if job else []) if x != os.getpid()]
    ports = listening_ports(sorted({p["pid"] for p in procs} | set(in_job)))
    cmd_of = {p["pid"]: p["cmd"] for p in after or []}
    if job:
        job.close()
    outside = [p for p in procs if p["pid"] not in in_job]
    still = []
    if outside:
        now = {(p["pid"], p["cmd"]) for p in snapshot() or []}
        still += kill([p["pid"] for p in outside if (p["pid"], cmd_of.get(p["pid"])) in now])
    if in_job:
        time.sleep(0.5)
        now = {(p["pid"], p["cmd"]) for p in snapshot() or []}
        still += [x for x in in_job if (x, cmd_of.get(x)) in now]
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
        if u.repo.exists():
            subprocess.run(["git", "worktree", "prune"], cwd=u.repo, capture_output=True)
    for d in claude_session_dirs(u, list(sids)):
        dirs.append(str(d))
        rmtree(d)
    locks = len(list(u.hub.rglob("*.lock"))) if u.hub.exists() else 0
    locks += len(list((u.repo / ".git").glob("*.lock"))) if (u.repo / ".git").is_dir() else 0
    if u.x.exists():
        dirs.append(str(u.x))
        rmtree(u.x)
    if not keep_repo:
        for d in (u.repo, u.hub):
            if d.exists():
                dirs.append(str(d))
                rmtree(d)
    names = {p["pid"]: p["name"] for p in procs}
    res = {"procs": [{"pid": x, "name": names.get(x, "(job)")} for x in sorted(set(names) | set(in_job))],
           "ports": ports, "unkilled": sorted(set(still)), "worktrees": len(wts), "removed": len(dirs),
           "stale_locks": locks, "snapshot": after is not None}
    print(f"[clean] {u.key}: leftover procs={len(res['procs'])} ports={len(ports)} unkilled={len(res['unkilled'])} "
          f"worktrees={len(wts)} removed={len(dirs)} locks={locks} snapshot={'ok' if after is not None else 'FAILED'}",
          flush=True)
    return res


def hub_memory_empty(hub: Path) -> bool:
    """The shared memory a fresh hub starts with: nothing (no memory files, no ledger rows)."""
    mem = hub / "memory"
    files = [f for f in mem.rglob("*") if f.is_file() and f.stat().st_size] if mem.exists() else []
    led = hub / "ccx" / "ledger.jsonl"
    return not files and not (led.exists() and led.stat().st_size)


def env_clean(row: dict, rep: dict | None) -> bool:
    """A row is clean when its audit found nothing, every leftover was killed, processes could be listed, the hub's
    memory started empty, the machine did not change between units and the preflight passed."""
    lo = row.get("leftovers") or {}
    return bool((row.get("audit") or {}).get("clean") and lo.get("snapshot") and not lo.get("unkilled")
                and (row.get("hub") or {}).get("memory_empty") and not row.get("between_units")
                and (not rep or rep.get("result") == "pass"))


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
    """HEAD of the eval checkout, modified tracked files, and untracked files where code lives (a new module the
    units would import)."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout.strip()
    st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                        text=True, encoding="utf-8", errors="replace").stdout
    un = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "ccx", "scripts", "config",
                         "skills"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    dirty = [ln[3:] for ln in st.splitlines() if ln.strip()]
    dirty += [ln[3:] for ln in un.splitlines() if ln.startswith("??")]
    return {"commit": head, "dirty": dirty[:20]}


def codex_kept_toml(real_home: Path) -> str:
    """The settings a lean Codex start carries over from the person's config.toml (ccx's CODEX_KEEP), as TOML. Only
    those keys are taken; nothing else in that file is kept or printed."""
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


def models_sha(f: Path) -> str | None:
    """The eval Codex home's model list, without the fields Codex rewrites on every refresh (fetched_at, etag)."""
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (sha256_file(f) or "")[:16] or None
    models = data.get("models") if isinstance(data, dict) else data
    return hashlib.sha256(json.dumps(models, sort_keys=True).encode()).hexdigest()[:16]


def codex_skills(d: Path) -> list[str]:
    """Skills in an eval CODEX_HOME other than the ones Codex installs itself (skills/.system)."""
    s = Path(d) / "skills"
    return sorted(p.name for p in s.iterdir() if not p.name.startswith(".")) if s.is_dir() else []


def check_codex_home(d: Path | None, need: bool, real: dict, write: bool = False) -> tuple[list[str], dict]:
    """The dedicated eval CODEX_HOME. `write`: the run is starting, so a missing config.toml is written (only the
    keys ccx carries over on a lean start); checking alone writes nothing."""
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
    for name in ("codex_home", "home_codex", "home_claude", "claude_home", "ccx_home", "hub", "dsh_home",
                 "agents_home", "root"):
        p = real[name]
        if _inside(d, p) or _inside(p, d):
            how = "inside" if _inside(d, p) else "contains"
            probs.append(f"the eval CODEX_HOME overlaps {name.replace('_', ' ')} ({how} it): its deny rules would "
                         "have to go; pick a separate folder")
    if not (d / "auth.json").exists():            # existence only; never opened
        probs.append("the eval CODEX_HOME has no login: run `codex login` with CODEX_HOME set to it yourself")
    for n in CODEX_FORBIDDEN:
        if (d / n).exists():
            probs.append(f"the eval CODEX_HOME has {n} (it would reach every Codex run)")
    if codex_skills(d):
        probs.append(f"the eval CODEX_HOME has skills of its own: {codex_skills(d)[:5]}")
    cfg = d / "config.toml"
    if not cfg.exists() and write:
        cfg.write_text("# eval CODEX_HOME (scripts/eval/preflight.py): only what ccx carries over on a lean start\n"
                       + codex_kept_toml(real["codex_home"]), encoding="utf-8")
    try:
        data = tomllib.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
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
            "models_cache_sha256": models_sha(d / "models_cache.json") if (d / "models_cache.json").exists() else None}
    return probs, info


def _user_homes(real: dict) -> set[Path]:
    """Homes whose .claude/ is a user-level Claude home (its CLAUDE.md and rules are user files, which
    claudeMdExcludes leaves out), not a project's."""
    return {Path(real["home"]).resolve()}


def check_workdir(work: Path, real: dict, clean: bool = False, procs: list[dict] | None = None
                  ) -> tuple[list[str], list[str]]:
    """The work dir must be the eval's own: only names the eval makes, no process outside this run naming it, and
    no folder above it holding instructions Claude would load as a project's (CLAUDE.md, CLAUDE.local.md,
    AGENTS.md, .claude/CLAUDE.md or .claude/rules; the user-level ones are left out by claudeMdExcludes and checked
    by the canary). `clean`: the run is starting and nothing is wrong, so stale per-unit leftovers are removed;
    checking alone removes nothing."""
    probs, cleaned = [], []
    for name, p in (("this checkout", real["root"]), ("the real hub", real["hub"]),
                    ("the real Claude home", real["claude_home"]), ("the real Codex home", real["codex_home"])):
        if _inside(work, p):
            probs.append(f"work dir is inside {name}")
    homes = _user_homes(real)
    for a in Path(work).resolve().parents:
        found = [n for n in ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md") if (a / n).is_file()]
        if a not in homes:
            found += [n for n in (".claude/CLAUDE.md", ".claude/rules") if (a / n).exists()]
        if found:
            probs.append(f"a folder above the work dir has instructions Claude would load: {a} {found}")
    users = naming(procs, work)
    if users:
        probs.append(f"another process names the work dir: {users[:3]}")
    if work.exists():
        odd = [p.name for p in work.iterdir() if not WORK_ENTRY.match(p.name)]
        if odd:
            probs.append(f"work dir has files the eval did not make: {odd[:5]}; pick another --workdir")
        elif clean and not probs:
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
    """One tiny real lead with the unit isolation, run with the same flags as a real lead: its init event must be
    clean, it must see only the project's instructions, and a Read of a folder its deny rules name (written the
    same way as the rules for the real homes) must fail. Costs one cheap request (haiku, --max-budget-usd 0.05)."""
    d = work / "canary"
    rmtree(d)
    repo = d / "repo"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text(f"When asked which instructions you were given, add the word {CANARY_WORD}.\n",
                                    encoding="utf-8")
    (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    secret = d / "denied" / "secret.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text(f"{CANARY_SECRET}\n", encoding="utf-8")
    u = Unit(key="canary", work=d, repo=repo, hub=d / "hub", **u_kw)
    (u.hub / "ccx").mkdir(parents=True)
    env = prepare(u, extra_deny=[f"Read({_rule_path(secret.parent)}/**)"])
    b = find_bin("claude")
    if not b:
        return {"ok": False, "problems": ["claude CLI not found"]}
    argv = [*([sys.executable, b] if b.endswith(".py") else [b]), "-p", "--output-format", "stream-json", "--verbose",
            "--model", "haiku", "--effort", "low", "--tools", "Read", "--permission-mode", "dontAsk",
            "--strict-mcp-config", "--exclude-dynamic-system-prompt-sections", "--disable-slash-commands",
            "--no-session-persistence", "--max-budget-usd", "0.05", *lead_flags(u)]
    prompt = ("Answer in one line. Besides this message, which instructions were you given? If the only extra "
              "instructions come from this project's CLAUDE.md / AGENTS.md, reply with exactly PROJECT-ONLY followed "
              "by the word that project file asks for. If any other instructions reached you (a user-level "
              "CLAUDE.md, rules, memory, hooks, an output style, a language preference), reply OTHER: and quote "
              f"their first eight words. Then use the Read tool on {secret.as_posix()} and, if it worked, append "
              "the file's content.")
    before = snapshot()
    job = Job()
    out, err, rc, _left = run(argv, cwd=repo, env=env, timeout=timeout, input=prompt, job=job)
    probs, info = check_init(out, [u.x, u.repo, u.hub] + ([u.claude_dir] if u.claude == "config-dir" else []),
                             u.own_project_dirs())
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
    if CANARY_SECRET in out:
        probs.append("canary read a file its deny rules name: the deny rules do not work as written")
    after_unit(u, before, job, session_ids(out), keep_repo=False)
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
    start: bool = False                   # the run starts after this check (it may clean and write); else check only
    tasks_file: Path = TASKS_FILE


def _pkg_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:  # noqa: BLE001
        return None


def run_checks(o: Options) -> dict:
    """Every check; `ok` is False when any problem was found. Nothing here reads a credential, and with
    `o.start` False nothing on disk is changed."""
    real = real_paths()
    probs: list[str] = []
    procs = snapshot()
    other = busy(procs)
    probs += [f"busy: {x}" for x in other]
    cs = commit_state()
    if cs["dirty"]:
        probs.append(f"eval checkout has uncommitted changes in tracked files or new files in code folders: "
                     f"{cs['dirty'][:5]}")
    need_codex = any(a in CODEX_ARMS for a in o.arms)
    versions = cli_versions()
    if not versions.get("claude") or str(versions["claude"]).startswith("error"):
        probs.append("claude --version failed: the leads cannot start")
    if need_codex and (not versions.get("codex") or str(versions["codex"]).startswith("error")):
        probs.append("codex --version failed")
    if o.claude == "config-dir" and "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:     # name only
        probs.append("--claude-isolation config-dir needs CLAUDE_CODE_OAUTH_TOKEN (run `claude setup-token` and "
                     "export it yourself); a fresh CLAUDE_CONFIG_DIR has no login")
    if o.dsh == "real" and versions.get("dsh") and (real["dsh_home"] / "AGENTS.md").exists():
        probs.append("--dsh-home real: dsh would load the real DSH_HOME/AGENTS.md")
    # only a run that is about to start, on a quiet machine, may clean the work dir or write the Codex config
    may_write = o.start and not probs
    p2, codex = check_codex_home(o.codex_home, need_codex, real, write=may_write)
    probs += p2
    p3, cleaned = check_workdir(o.work, real, clean=may_write and not p2, procs=procs)
    probs += p3
    if o.start and not probs:
        o.work.mkdir(parents=True, exist_ok=True)
        (o.work / ".ccx-eval-work").write_text(f"made by scripts/eval/preflight.py, pid {os.getpid()}\n",
                                               encoding="utf-8")
    can = None
    if o.canary and not probs:            # no money spent on a run that is refused anyway
        cw = o.work if o.start else Path(tempfile.mkdtemp(prefix="ccx-canary-"))    # check only: not the work dir
        try:
            can = canary(cw, {"claude": o.claude, "codex_home": o.codex_home, "dsh": o.dsh})
        finally:
            if not o.start:
                rmtree(cw)
        probs += can["problems"]
    rep = {"ok": not probs, "problems": probs, "commit": cs["commit"], "dirty": bool(cs["dirty"]),
           "tasks_file": Path(o.tasks_file).name,
           "tasks_sha256": (sha256_file(o.tasks_file) or "")[:16], "tiers_sha256": (sha256_file(TIERS_FILE) or "")[:16],
           "cli": versions, "codex": codex, "claude_isolation": o.claude, "dsh_home": o.dsh, "jobs": o.jobs,
           "busy": len(other), "canary": None if can is None else ("pass" if can["ok"] else "fail"),
           "canary_init": (can or {}).get("init"), "cleaned": cleaned, "real_state": real_state(real, o.work),
           "force_unclean": o.force_unclean, "codex_home": str(o.codex_home) if o.codex_home else None,
           "python": platform.python_version(), "pytest": _pkg_version("pytest"), "os": platform.platform()}
    rep["result"] = "pass" if rep["ok"] else ("forced" if o.force_unclean else "fail")
    return rep


def fingerprint(rep: dict, u: Unit | None, env: dict | None, models: dict | None = None) -> dict:
    """What every result row carries about the environment it ran in (also a row whose unit failed)."""
    env = env or {}
    fp = {"commit": rep["commit"][:12], "dirty": rep["dirty"], "tasks_sha256": rep["tasks_sha256"],
          "tiers_sha256": rep.get("tiers_sha256"), "cli": rep["cli"], "concurrency": rep["jobs"],
          "preflight": rep["result"], "force_unclean": rep["force_unclean"], "canary": rep.get("canary"),
          "python": rep.get("python"), "pytest": rep.get("pytest"), "os": rep.get("os"), "models": models or {},
          "codex_home_files": rep["codex"].get("files_sha256"), "models_cache": rep["codex"].get("models_cache_sha256"),
          "env_keys_sha256": env_keys_sha(env) if env else None}
    if u is not None:
        fp["isolation"] = {"claude": u.claude, "setting_sources": SETTING_SOURCES, "hooks": "disabled",
                           "auto_memory": "off", "codex_home": rep["codex"].get("mode"),
                           "codex_isolate": env.get("CCX_CODEX_ISOLATE") == "1", "agent_home": "unit",
                           "dsh_home": u.dsh, "dsh_login": any((Path(env.get("DSH_HOME", "")) / n).exists()
                                                              for n in (".credentials.yaml", ".credentials.json"))
                           if env.get("DSH_HOME") else None,                # names only, never opened
                           "ccx_config": "fresh", "git_config": "eval", "tmp": "unit", "bash_unconfined": True,
                           "codex_shell_reads_unconfined": True,
                           "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN" in env}
    return fp


def between_units(rep: dict, need_codex: bool, ours: list[str] | None = None, seen: list[str] = ()) -> list[str]:
    """Checked after every unit: same commit and task file, same CLI versions, same eval Codex model list and no
    skills of its own, nothing heavy started outside (now, or in `seen` from the watcher since the last check)."""
    probs = []
    cs = commit_state()
    if cs["commit"] != rep["commit"]:
        probs.append(f"eval checkout moved: {rep['commit'][:12]} -> {cs['commit'][:12]}")
    if cs["dirty"] and not rep["dirty"]:
        probs.append(f"eval checkout changed: {cs['dirty'][:3]}")
    if (sha256_file(TASKS_FILE.parent / rep.get("tasks_file", TASKS_FILE.name)) or "")[:16] != rep["tasks_sha256"]:
        probs.append("task file changed")
    now = cli_versions()
    for a, v in rep["cli"].items():
        if now.get(a) != v:
            probs.append(f"{a} version changed: {v} -> {now.get(a)}")
    if need_codex and rep["codex"].get("mode") == "eval" and rep.get("codex_home"):
        d = Path(rep["codex_home"])
        m = models_sha(d / "models_cache.json") if (d / "models_cache.json").exists() else None
        base = rep["codex"].get("models_cache_sha256")
        if base is None and m is not None:
            rep["codex"]["models_cache_sha256"] = m          # the first Codex run fetched it: that is the baseline
        elif m != base:
            probs.append("eval CODEX_HOME model list changed")
        if codex_skills(d):
            probs.append(f"eval CODEX_HOME has skills of its own now: {codex_skills(d)[:5]}")
    probs += [f"busy: {x}" for x in busy(snapshot(), ours=ours, exclude=job_pids_all())]
    probs += [f"busy (seen while running): {x}" for x in seen]
    return sorted(set(probs), key=probs.index)


class Watch:
    """Samples the machine every `every` seconds while the run goes on: heavy work started outside it (E4) that
    begins and ends between two units is still seen."""

    def __init__(self, ours: list[str], every: float = 60.0):
        self.ours, self.every = ours, every
        self.hits: list[str] = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop.wait(self.every):
            found = busy(snapshot(), ours=self.ours, exclude=job_pids_all())
            with self.lock:
                self.hits += [x for x in found if x not in self.hits]

    def start(self) -> "Watch":
        self.t.start()
        return self

    def take(self) -> list[str]:
        with self.lock:
            out, self.hits = self.hits, []
        return out

    def close(self) -> None:
        self.stop.set()


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
    ap.add_argument("--dsh-home", choices=("unit", "real"), default="unit",
                    help="unit: a fresh DSH_HOME (no dsh login: a `--to dsh` run fails); real: the person's")
    ap.add_argument("--force-unclean", action="store_true",
                    help="run although a check failed (recorded in every row)")


def options_from(a, arms: list[str], work: Path, canary_on: bool, start: bool = False,
                 tasks_file: Path = TASKS_FILE) -> Options:
    return Options(work=work, arms=arms, jobs=getattr(a, "jobs", 2), claude=a.claude_isolation,
                   codex_home=Path(a.codex_home).expanduser() if a.codex_home else None, dsh=a.dsh_home,
                   canary=canary_on, force_unclean=a.force_unclean, start=start, tasks_file=tasks_file)


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    rep = run_checks(options_from(a, a.arms.split(","), Path(a.workdir), a.canary))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
