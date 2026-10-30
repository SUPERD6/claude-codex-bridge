"""The daily-config Codex home of one evaluation unit (B3 item 2: scripts/eval/r5.py arms ccx2daily*).

Every other arm runs its Codex sub-agents in the dedicated eval CODEX_HOME with --ignore-user-config, --ignore-rules
and memories off (CCX_CODEX_ISOLATE=1), so the setup a person really uses, with their Codex memories, AGENTS.md and
skills, was never measured. A daily arm gets, per unit, a fresh Codex home and HOME of its own inside the unit's x-
folder (removed with it after the unit):

  daily-codex-home/   auth.json        copied from the eval CODEX_HOME (its own login; never the person's)
                      config.toml      written here: the settings ccx carries over on a lean start (CODEX_KEEP), the
                                       eval's features off (apps, plugins, remote_plugin: no account connectors) and
                                       only the person's own memory settings ([features] memories, [memories] values)
                      memories/ AGENTS.md skills/   copied from the person's Codex home (DAILY_COPY), nothing else
  daily-agent-home/   .agents/skills/  copied from the person's ~/.agents/skills (codex-cli 0.164 reads user skills
                                       from $HOME/.agents/skills): the sub-agent's HOME through CCX_AGENT_HOME

Never copied, at any depth: the person's auth or credential files, config.toml (its hooks, trust state, profiles,
MCP servers), sessions, logs, history, databases, rules, hooks and plugins (NEVER); links are not followed. After
the copy the two folders are walked again and any such name other than the eval login stops the unit.

The eval CODEX_HOME itself is never written to, so the preflight and between-unit checks of every other arm (which
refuse memories, AGENTS.md or skills there) stay exactly as strict: the daily arms' exception is this per-unit home.
"""
from __future__ import annotations

import fnmatch
import shutil
import tomllib
from pathlib import Path

DAILY_COPY = ("memories", "AGENTS.md", "skills")        # from the person's Codex home
AGENTS_COPY = ("skills",)                               # from the person's ~/.agents
# names never copied from the person's homes (lower case, fnmatch patterns)
NEVER = ("auth.json", "*credential*", "*.pem", "*.key", "token", "token.json", "*.token", ".env", "config.toml", "sessions",
         "archived_sessions", "log", "logs", "*.log", "history.jsonl", "*.sqlite", "*.sqlite-*", "*.db", "*.db-*",
         "rules", "hooks", "plugins", "tmp", "cache")
# the Claude sub-agents of a daily arm load the user settings layer too (scripts/eval/preflight.py SETTING_SOURCES
# is project,local for every other arm)
DAILY_CLAUDE_SOURCES = "user,project,local"
CODEX_DIR, AGENT_DIR = "daily-codex-home", "daily-agent-home"


def never(name: str) -> bool:
    n = name.lower()
    return any(fnmatch.fnmatch(n, p) for p in NEVER)


def _ignore(_dir, names):
    return [n for n in names if never(n)]


def _copy(src: Path, dst: Path) -> bool:
    """A file or a folder, links not followed (a link itself is left out), NEVER names left out."""
    if src.is_symlink() or not src.exists() or never(src.name):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True, ignore=_ignore)
        for p in sorted(dst.rglob("*"), reverse=True):        # links inside the tree: copied as links, so drop them
            if p.is_symlink():
                p.unlink()
    else:
        shutil.copyfile(src, dst)
    return True


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


def config_toml(kept: str, features_off: tuple, mem: dict) -> str:
    feats = "".join(f"{f} = false\n" for f in features_off)
    if "features.memories" in mem:
        feats += f"memories = {_toml(mem['features.memories'])}\n"
    rest = "".join(f"{k.split('.', 1)[1]} = {_toml(v)}\n" for k, v in mem.items() if k.startswith("memories."))
    return ("# daily-config Codex home of one eval unit (scripts/eval/daily_home.py)\n" + kept + "[features]\n" + feats
            + ("[memories]\n" + rest if rest else ""))


def found_never(root: Path, allow: tuple = ()) -> list[str]:
    """NEVER names (and links) under root, except the relative paths in `allow`."""
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if rel in allow:
            continue
        if p.is_symlink() or never(p.name):
            out.append(rel)
    return sorted(out)


def build(dest: Path, eval_codex_home: Path, codex_src: Path, agents_src: Path | None, kept: str = "",
          features_off: tuple = ("apps", "plugins", "remote_plugin")) -> dict:
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
    copied = [f"codex:{n}" for n in DAILY_COPY if _copy(Path(codex_src) / n, codex / n)]
    if agents_src:
        copied += [f"agents:{n}" for n in AGENTS_COPY if _copy(Path(agents_src) / n, home / ".agents" / n)]
    mem = memory_settings(Path(codex_src))
    (codex / "config.toml").write_text(config_toml(kept, tuple(features_off), mem), encoding="utf-8")
    bad = found_never(codex, allow=("auth.json", "config.toml")) + [f".agents/{x}" for x in found_never(home)]
    if bad:
        raise RuntimeError(f"the daily home holds what must never be copied: {bad[:5]}")
    files = sum(1 for d in (codex, home) for p in d.rglob("*") if p.is_file())
    return {"codex_home": str(codex), "agent_home": str(home), "copied": copied, "files": files,
            "auth": "eval-codex-home", "memory_settings": mem, "features_off": list(features_off),
            "claude_setting_sources": DAILY_CLAUDE_SOURCES}


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
