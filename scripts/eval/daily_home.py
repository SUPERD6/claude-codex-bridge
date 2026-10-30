"""The daily-config Codex home of one evaluation unit (B3 item 2: scripts/eval/r5.py arms ccx2daily*).

Every other arm runs its Codex sub-agents in the dedicated eval CODEX_HOME with --ignore-user-config, --ignore-rules
and memories off (CCX_CODEX_ISOLATE=1), so the setup a person really uses, with their Codex memories, AGENTS.md and
skills, was never measured. A daily arm gets, per unit, a fresh Codex home and HOME of its own inside the unit's x-
folder (removed with it after the unit):

  daily-codex-home/   auth.json        copied from the eval CODEX_HOME (its own login; never the person's)
                      config.toml      written here: the settings ccx carries over on a lean start (CODEX_KEEP), the
                                       eval's features off (apps, plugins, remote_plugin: no account connectors),
                                       only the person's own memory settings ([features] memories, [memories] values)
                                       and, on Windows only, [windows] sandbox = "unelevated" (WINDOWS_SANDBOX)
                      memories/ AGENTS.md skills/   copied from the person's Codex home (DAILY_COPY), nothing else
  daily-agent-home/   .agents/skills/  copied from the person's ~/.agents/skills (codex-cli 0.164 reads user skills
                                       from $HOME/.agents/skills): the sub-agent's HOME through CCX_AGENT_HOME

Copied: only files of a known text type (TEXT_SUFFIXES: .md, .txt, scripts, .json, .toml, .yaml ...); everything
else is left out and counted. Never copied, at any depth, whatever the type: the person's auth or credential files,
keys and certificates (id_*, *.pem, *.key, *.p12, *.pfx), secrets, .netrc / .npmrc / .pypirc, .ssh / .aws / .gnupg /
.git folders, config.toml (its hooks, trust state, profiles, MCP servers), sessions, logs, history, databases, rules,
hooks and plugins (NEVER). Links (symbolic links and Windows junctions; skill folders are often one) are followed
into their target, since that is what Codex loads, and every file found there passes the same filters; a folder seen
twice (a loop) is walked once. The copy holds plain files only. After the copy the two folders are walked again and
any NEVER name, link or file of another type (other than the eval login and the written config.toml) stops the
unit. `sha256` (names and bytes of what was copied) lets paired units with different snapshots be told apart.

The eval CODEX_HOME gets nothing of the person's: the preflight and between-unit checks of every other arm (which
refuse memories, AGENTS.md or skills there) stay exactly as strict; the daily arms' exception is this per-unit home.
The one write to it is its own login: a ChatGPT login refreshes and rotates its token inside the unit's copy, so
sync_login puts a refreshed copy back (atomically) before the unit's folder goes, and the daily arms run one unit at a
time (r5 refuses --jobs > 1 for them), so no unit holds a spent token.

Codex reads skills from CODEX_HOME/skills as well as from $HOME/.agents/skills, and AGENTS.md and memories from
CODEX_HOME: `[subagent] clean` changes only HOME, so on the Codex side ccx2daily_clean differs from ccx2daily by the
~/.agents/skills copy alone (`copied` says which sources were there).

Windows: Codex's elevated sandbox runs commands as machine-wide sandbox accounts (CodexSandboxOffline /
CodexSandboxOnline) whose passwords sit in each CODEX_HOME's .sandbox-secrets. A fresh per-unit home has none, so
Codex starts its setup helper, which needs UAC; with nobody at the machine that is cancelled and every shell command
fails (seen live with codex-cli 0.164.0, 2026-10-30). Running setup again from any home rotates the shared accounts
and breaks the other homes. So on Windows every daily arm alike gets [windows] sandbox = "unelevated" (it replaces
the person's own windows.sandbox from CODEX_KEEP): no UAC, no secrets, nothing shared with other homes. The limit:
the person's real setup uses the elevated sandbox; the daily arms compare the switches with each other under the
unelevated one. Elsewhere nothing is added. Rows record it as daily.windows_sandbox.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import stat
import sys
import tomllib
from pathlib import Path

DAILY_COPY = ("memories", "AGENTS.md", "skills")        # from the person's Codex home
AGENTS_COPY = ("skills",)                               # from the person's ~/.agents
# names never copied from the person's homes (lower case, fnmatch patterns)
NEVER = ("auth.json", "*credential*", "*.pem", "*.key", "token", "token.json", "*.token", ".env", ".env.*", "config.toml",
         "sessions", "archived_sessions", "log", "logs", "*.log", "history.jsonl", "*.sqlite", "*.sqlite-*", "*.db",
         "*.db-*", "rules", "hooks", "plugins", "tmp", "cache",
         "id_*", "*.p12", "*.pfx", "*.jks", "*.kdbx", "*secret*", "oauth*", ".netrc", ".npmrc", ".pypirc", ".ssh", ".aws",
         ".gnupg", ".git", ".git-credentials", "node_modules")
# the only file types copied (lower-case suffixes): what memories, AGENTS.md and skills are written in
TEXT_SUFFIXES = (".md", ".markdown", ".txt", ".rst", ".json", ".toml", ".yaml", ".yml", ".py", ".sh", ".ps1", ".bat",
                 ".cmd", ".js", ".mjs", ".cjs", ".ts", ".html", ".css", ".csv", ".xml", ".svg")
MAX_DEPTH = 16
# the Claude sub-agents of a daily arm load the user settings layer too (scripts/eval/preflight.py SETTING_SOURCES
# is project,local for every other arm)
DAILY_CLAUDE_SOURCES = "user,project,local"
CODEX_DIR, AGENT_DIR = "daily-codex-home", "daily-agent-home"
# the Windows sandbox of every daily home (see the module text); None elsewhere
WINDOWS_SANDBOX = "unelevated"


def windows_sandbox(platform: str | None = None) -> str | None:
    """The [windows] sandbox a daily home is given on this platform: WINDOWS_SANDBOX on win32, else None."""
    return WINDOWS_SANDBOX if (platform or sys.platform) == "win32" else None


def never(name: str) -> bool:
    n = name.lower()
    return any(fnmatch.fnmatch(n, p) for p in NEVER)


def text_file(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_SUFFIXES


def is_link(p: Path) -> bool:
    """A symbolic link or a Windows junction (Path.is_symlink() does not see a junction)."""
    try:
        if os.path.islink(p):
            return True
        isj = getattr(os.path, "isjunction", None)            # 3.12+
        if isj and isj(p):
            return True
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        return False


def _copy(src: Path, dst: Path, stats: dict, seen: set | None = None, depth: int = 0) -> bool:
    """A file or a folder as plain files: links followed into their target, NEVER names and other file types left
    out (counted in stats), a folder already walked (a loop through a link) walked once."""
    seen = set() if seen is None else seen
    if never(src.name) or not src.exists():
        return False
    if is_link(src):
        stats["links_followed"] = stats.get("links_followed", 0) + 1
    if src.is_dir():
        real = os.path.realpath(src)
        if real in seen or depth > MAX_DEPTH:
            return False
        seen.add(real)
        dst.mkdir(parents=True, exist_ok=True)
        for child in sorted(src.iterdir(), key=lambda c: c.name):
            _copy(child, dst / child.name, stats, seen, depth + 1)
        return True
    if not src.is_file():
        return False
    if not text_file(src.name):
        stats["skipped_type"] = stats.get("skipped_type", 0) + 1
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)                               # follows a link: the copy is a plain file
    return True


def tree_sha256(roots: list[Path], skip: tuple = ("auth.json",)) -> str:
    """Names and bytes of every file under the roots (the eval login left out): equal for equal snapshots."""
    h = hashlib.sha256()
    for i, root in enumerate(roots):
        for f in sorted(p for p in Path(root).rglob("*") if p.is_file()):
            rel = f.relative_to(root).as_posix()
            if i == 0 and rel in skip:
                continue
            h.update(f"{i}:{rel}\0".encode("utf-8"))
            h.update(f.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def memory_settings(codex_src: Path) -> dict:
    """The person's own memory settings from their config.toml: [features] memories and the scalar values of
    [memories]; nothing else of that file is read out."""
    try:
        cfg = tomllib.loads((codex_src / "config.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out = {}
    feats = cfg.get("features") if isinstance(cfg.get("features"), dict) else {}
    if isinstance(feats.get("memories"), bool):
        out["features.memories"] = feats["memories"]
    mem = cfg.get("memories") if isinstance(cfg.get("memories"), dict) else {}
    for k, v in mem.items():
        if isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) < 200):
            out[f"memories.{k}"] = v
    return out


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def with_windows_sandbox(kept: str, sandbox: str) -> str:
    """The kept settings' TOML (flat tables of scalars, preflight.codex_kept_toml) with [windows] sandbox set to
    `sandbox`, replacing the person's own value: one [windows] table."""
    try:
        cfg = tomllib.loads(kept) if kept else {}
    except tomllib.TOMLDecodeError:
        cfg = {}
    win = cfg.get("windows") if isinstance(cfg.get("windows"), dict) else {}
    cfg["windows"] = {**win, "sandbox": sandbox}
    return "".join(f"[{t}]\n" + "".join(f"{k} = {_toml(v)}\n" for k, v in vals.items())
                   for t, vals in cfg.items() if isinstance(vals, dict))


def config_toml(kept: str, features_off: tuple, mem: dict, platform: str | None = None) -> str:
    """The daily home's config.toml. On win32 (or `platform`) [windows] sandbox is WINDOWS_SANDBOX (module text)."""
    sandbox = windows_sandbox(platform)
    if sandbox:
        kept = with_windows_sandbox(kept, sandbox)
    feats = "".join(f"{f} = false\n" for f in features_off)
    if "features.memories" in mem:
        feats += f"memories = {_toml(mem['features.memories'])}\n"
    rest = "".join(f"{k.split('.', 1)[1]} = {_toml(v)}\n" for k, v in mem.items() if k.startswith("memories."))
    return ("# daily-config Codex home of one eval unit (scripts/eval/daily_home.py)\n" + kept + "[features]\n" + feats
            + ("[memories]\n" + rest if rest else ""))


def found_never(root: Path, allow: tuple = ()) -> list[str]:
    """NEVER names, links (junctions included) and files of a type not copied under root, except the relative paths
    in `allow`. Walked without following links."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for n in dirnames + filenames:
            q = Path(dirpath) / n
            rel = q.relative_to(root).as_posix()
            if rel in allow:
                continue
            if is_link(q) or never(n) or (n in filenames and not text_file(n)):
                out.append(rel)
        dirnames[:] = [d for d in dirnames if not is_link(Path(dirpath) / d)]
    return sorted(out)


def build(dest: Path, eval_codex_home: Path, codex_src: Path, agents_src: Path | None, kept: str = "",
          features_off: tuple = ("apps", "plugins", "remote_plugin"), platform: str | None = None) -> dict:
    """Make dest/daily-codex-home and dest/daily-agent-home (see the module text). `kept`: the TOML of the settings
    ccx carries over on a lean start (preflight.codex_kept_toml). Raises when the eval home has no login or when a
    name that must never be copied ended up in either folder. Returns what was made, by name only."""
    codex, home = Path(dest) / CODEX_DIR, Path(dest) / AGENT_DIR
    for d in (codex, home):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    auth = Path(eval_codex_home) / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"the eval CODEX_HOME {eval_codex_home} has no login (auth.json): the daily home's login "
                           "comes from there, never from the person's own Codex home")
    shutil.copyfile(auth, codex / "auth.json")         # copied, never opened
    stats: dict = {}
    copied = [f"codex:{n}" for n in DAILY_COPY if _copy(Path(codex_src) / n, codex / n, stats)]
    if agents_src:
        copied += [f"agents:{n}" for n in AGENTS_COPY if _copy(Path(agents_src) / n, home / ".agents" / n, stats)]
    mem = memory_settings(Path(codex_src))
    (codex / "config.toml").write_text(config_toml(kept, tuple(features_off), mem, platform), encoding="utf-8")
    bad = found_never(codex, allow=("auth.json", "config.toml")) + [f".agents/{x}" for x in found_never(home)]
    if bad:
        raise RuntimeError(f"the daily home holds what must never be copied: {bad[:5]}")
    files = sum(1 for d in (codex, home) for p in d.rglob("*") if p.is_file())
    out = {"codex_home": str(codex), "agent_home": str(home), "copied": copied, "files": files,
           "links_followed": stats.get("links_followed", 0), "skipped_type": stats.get("skipped_type", 0),
           "sha256": tree_sha256([codex, home]), "auth": "eval-codex-home", "auth_sha256": file_sha256(auth),
           "memory_settings": mem, "features_off": list(features_off), "claude_setting_sources": DAILY_CLAUDE_SOURCES}
    sandbox = windows_sandbox(platform)
    if sandbox:                                         # Windows only: the sandbox every daily home runs under
        out["windows_sandbox"] = sandbox
    return out


def file_sha256(f: Path) -> str | None:
    try:
        return hashlib.sha256(Path(f).read_bytes()).hexdigest()
    except OSError:
        return None


def sync_login(info: dict, eval_codex_home: Path) -> dict:
    """After a daily unit: a ChatGPT login refreshes its token and writes the new one into the unit's copy of
    auth.json, and a refresh token works once, so the eval home's own copy may now be spent. The rotated copy is
    written back to the eval home (atomically) when the eval home's file is still the one the unit copied; when both
    changed (another unit refreshed too) nothing is written and the round should stop: `conflict`. Returns what
    happened, for the row (hashes only; the file is never opened as text)."""
    copy, orig = Path(info["codex_home"]) / "auth.json", Path(eval_codex_home) / "auth.json"
    start, now, ours = info.get("auth_sha256"), file_sha256(orig), file_sha256(copy)
    if ours is None or ours == start:
        return {"auth": "unchanged"}
    if now != start:
        return {"auth": "conflict", "note": "the unit's login was refreshed and the eval home's changed too: stop the "
                "round and log in to the eval Codex home again"}
    tmp = orig.with_name(orig.name + ".ccx-daily.tmp")
    shutil.copyfile(copy, tmp)
    os.replace(tmp, orig)
    return {"auth": "refreshed", "written_back": True}


def unit_env(env: dict, info: dict) -> dict:
    """A daily unit's environment from its clean-room one (preflight.prepare): Codex sub-agents in the daily home
    with the person's setup (no CCX_CODEX_ISOLATE: no --ignore-user-config / --ignore-rules / memories off), HOME
    with their ~/.agents skills, Claude sub-agents with the user settings layer and skills on. The settings file
    (hooks off, auto-memory off, deny rules) stays: those keep the person's real homes out of reach."""
    out = dict(env)
    for k in ("CCX_CODEX_ISOLATE", "CCX_CLAUDE_NO_SKILLS"):
        out.pop(k, None)
    out.update({"CODEX_HOME": info["codex_home"], "CODEX_SQLITE_HOME": info["codex_home"],
                "CCX_AGENT_HOME": info["agent_home"], "CCX_CLAUDE_SETTING_SOURCES": DAILY_CLAUDE_SOURCES})
    return out


def overlay_toml(switches: dict) -> str:
    """The [subagent] table a daily variant writes into its unit hub's tiers.toml (empty for the baseline)."""
    if not switches:
        return ""
    return "[subagent]\n" + "".join(f"{k} = {_toml(v)}\n" for k, v in sorted(switches.items()))
