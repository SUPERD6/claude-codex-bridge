"""Paths and configuration for ccx.

Everything user-specific lives in the *hub*, a folder both Claude Code and Codex
read. The repo only holds generic code, defaults and templates — no personal
paths. Where the hub is comes from (first match wins):
  1. $CCX_HUB
  2. `hub = "..."` in ~/.ccx/config.toml   (written by `ccx init --hub PATH`)
  3. ~/.ccx-hub
"""
from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    raise SystemExit("ccx needs Python 3.11+ (for tomllib).")

REPO_ROOT = Path(__file__).resolve().parent.parent
# A clone (or editable install) has ccx.py next to the package; an installed wheel carries the same folders
# as package data (pyproject: config/ -> ccx/_config, skills/ -> ccx/_skills, hub-seed/ -> ccx/_hubseed).
FROM_SOURCE = (REPO_ROOT / "ccx.py").exists()
_PACKAGED = {"config": "_config", "skills": "_skills", "hub-seed": "_hubseed"}


def data_dir(name: str) -> Path:
    """config / skills / hub-seed, wherever this copy of ccx keeps them."""
    if FROM_SOURCE:
        return REPO_ROOT / name
    from importlib.resources import files
    return Path(str(files("ccx") / _PACKAGED[name]))


def ccx_argv() -> list[str]:
    """How to start this copy of ccx from another process (hooks, background runs)."""
    return [sys.executable, str(REPO_ROOT / "ccx.py")] if FROM_SOURCE else [sys.executable, "-m", "ccx"]


DEFAULT_TIERS = data_dir("config") / "tiers.toml"
RESULT_SCHEMA = data_dir("config") / "result.schema.json"
TIER_ORDER = ["T0", "T1", "T2", "T3", "T4"]
AGENTS = ("codex", "claude")                 # wired for shared memory / skills / MCP / hooks
DELEGATE_AGENTS = ("codex", "claude", "gemini", "dsh")   # can run headless sub-tasks (adapters in ccx/agents)


def _default_providers() -> tuple[str, ...]:
    try:
        with open(DEFAULT_TIERS, "rb") as f:
            return tuple(tomllib.load(f).get("providers") or ())
    except (OSError, tomllib.TOMLDecodeError):
        return ("deepseek",)


PROVIDER_AGENTS = _default_providers()   # [providers.<name>] in config: an agent CLI pointed at another model API

def user_config_file() -> Path:
    env = os.environ.get("CCX_CONFIG")
    return Path(env).expanduser() if env else Path.home() / ".ccx" / "config.toml"


def hub_dir() -> Path:
    env = os.environ.get("CCX_HUB")
    if env:
        return Path(env).expanduser()
    f = user_config_file()
    if f.exists():
        try:
            hub = tomllib.loads(f.read_text(encoding="utf-8")).get("hub")
            if hub:
                return Path(hub).expanduser()
        except tomllib.TOMLDecodeError:
            pass
    return Path.home() / ".ccx-hub"


def save_hub(path: Path) -> Path:
    """Remember the hub location for this machine (never inside the repo)."""
    f = user_config_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f'# written by `ccx init --hub`\nhub = {json.dumps(str(path))}\n', encoding="utf-8")
    return f


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    return Path(env).expanduser() if env else Path.home() / ".codex"


def claude_home() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


DEFAULT_LAYOUT = {
    # where the shared snapshot ("1") lives, relative to the hub
    "snapshot": "memory/MEMORY.md",
    # managed  = ccx wires the snapshot into each tool (CLAUDE.md import / AGENTS.md block)
    # external = the tools already load it some other way; ccx never writes into their instruction files
    "snapshot_mode": "managed",
    "skills": "skills",
    "mcp": "mcp/servers.json",
    "mcp_format": "auto",          # auto | ccx ({"servers": ...}) | mcpServers ({"mcpServers": ...})
    "external_sync": "",           # a command that already links skills/MCP into both tools; ccx then defers to it
    # every linked skill's description loads at every session start: link only what you use
    "skills_include": [],          # non-empty = link only these skill names
    "skills_exclude": [],          # never link these
}


def load_layout(hub: Path) -> dict:
    """Hub layout = defaults + <hub>/ccx/layout.toml. Lets ccx plug into an existing personal setup
    instead of creating a second one (that file is personal; the code stays generic)."""
    lay = dict(DEFAULT_LAYOUT)
    f = hub / "ccx" / "layout.toml"
    if f.exists():
        try:
            lay.update(tomllib.loads(f.read_text(encoding="utf-8")).get("layout", {}))
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{f} is not valid TOML: {e}") from e
    return lay


@dataclass(frozen=True)
class Paths:
    hub: Path

    @property
    def layout(self) -> dict:
        return load_layout(self.hub)

    @property
    def state(self) -> Path:          # ccx private state inside the hub
        return self.hub / "ccx"

    @property
    def runs(self) -> Path:
        return self.state / "runs"

    @property
    def ledger(self) -> Path:
        return self.state / "ledger.jsonl"

    @property
    def user_tiers(self) -> Path:
        return self.state / "tiers.toml"

    @property
    def settings(self) -> Path:       # written by `ccx config set` (no hand comments to lose)
        return self.state / "settings.toml"

    @property
    def memory(self) -> Path:
        return self.hub / "memory"

    @property
    def memory_index(self) -> Path:          # the shared snapshot ("1")
        return self.hub / self.layout["snapshot"]

    @property
    def snapshot_external(self) -> bool:
        return self.layout["snapshot_mode"] == "external"

    @property
    def skills(self) -> Path:
        return self.hub / self.layout["skills"]

    @property
    def mcp_registry(self) -> Path:
        return self.hub / self.layout["mcp"]


def paths() -> Paths:
    return Paths(hub_dir())


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(p: Paths | None = None) -> dict:
    p = p or paths()
    with open(DEFAULT_TIERS, "rb") as f:
        cfg = tomllib.load(f)
    for f in (p.user_tiers, p.settings):          # hand-edited overrides, then `ccx config set`
        if f.exists():
            with open(f, "rb") as fh:
                cfg = _deep_merge(cfg, tomllib.load(fh))
    return cfg


def path_list(raw: str) -> list[str]:
    """`ccx config set` value for a list of folders: separated by ';' (a ':' is part of a Windows path)."""
    return [x.strip() for x in raw.replace("\n", ";").split(";") if x.strip()]


SETTINGS = {   # key -> (type, help). Only these can be set with `ccx config set`.
    "defaults.tradeoff": (str, "save | balanced | fast, or a knob 0..1 (0 = cheapest, 1 = fastest)"),
    "defaults.ab_self_rate": (float, "share of routed tasks the lead does itself to measure savings (0 = off)"),
    "defaults.max_escalations": (int, "stronger rungs to try after a verified failure"),
    "defaults.max_parallel": (int, "parallel sub-agents in ccx batch"),
    "defaults.timeout_sec": (int, "per-attempt timeout"),
    "lead.claude": (str, "model the Claude lead runs on (for savings estimates), e.g. opus"),
    "lead.codex": (str, "model the Codex lead runs on, e.g. gpt-6.1-sol"),
    "sessions.archive": (str, "after_run | hours | off: archive a sub-agent session as soon as its result is "
                              "final (default), only after auto_archive_hours, or never by itself"),
    "sessions.auto_archive_hours": (float, "archive finished sub-agent sessions after N hours (0 = off)"),
    "report.publish_dir": (str, "local clone of your private usage repo; `ccx report --publish` commits there"),
    "board.github": (str, "owner/repo of a PRIVATE repository of yours: the board's fallback between computers "
                          "(empty = off, no network)"),
    "board.max_machine_turns": (int, "machine messages in a row in one board thread before a person must speak"),
    "projects.roots": (path_list, "folders `ccx projects scan` looks for your projects in, separated by ';' "
                                  "(the catalog stays in the hub, on this machine)"),
    "autonomy.level": (str, "L0 | L1 | L2: how much the project manager does without asking (default L1; "
                            "per project: `ccx autonomy set`)"),
    "hooks.timeout_s": (float, "seconds a session hook (ccx mem delta / turn) may run before it prints nothing and "
                               "exits 0; logged, shown by `ccx doctor` (0 = no limit)"),
    "ui.lang": (str, "zh | en: language of `ccx ui` and of the lines ccx writes into conversations (unset: the "
                     "page follows the browser, the lines stay English)"),
}


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def set_setting(p: Paths, key: str, raw: str) -> dict:
    if key not in SETTINGS:
        raise ValueError(f"unknown setting {key!r}; known: {', '.join(SETTINGS)}")
    typ = SETTINGS[key][0]
    if key == "defaults.tradeoff" and raw not in ("save", "balanced", "fast"):
        k = float(raw)
        if not 0 <= k <= 1:
            raise ValueError("tradeoff knob must be between 0 and 1")
    if key == "sessions.archive" and raw not in ("after_run", "hours", "off"):
        raise ValueError("sessions.archive must be after_run, hours or off")
    if key == "autonomy.level" and raw not in ("L0", "L1", "L2"):
        raise ValueError("autonomy.level must be L0, L1 or L2")
    if key == "ui.lang" and raw not in ("zh", "en"):
        raise ValueError("ui.lang must be zh or en")
    try:
        val = typ(raw)
    except ValueError as e:
        raise ValueError(f"{key} needs a {typ.__name__}: {e}") from e
    cur = {}
    if p.settings.exists():
        cur = tomllib.loads(p.settings.read_text(encoding="utf-8"))
    sec, name = key.split(".", 1)
    cur.setdefault(sec, {})[name] = val
    lines = ["# written by `ccx config set`; edit with that command"]
    for s, vals in cur.items():
        lines.append(f"\n[{s}]")
        lines += [f"{k} = {_toml_value(v)}" for k, v in vals.items()]
    p.settings.parent.mkdir(parents=True, exist_ok=True)
    p.settings.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {key: val}


def provider_of(cfg: dict, agent: str) -> dict | None:
    """The [providers.<agent>] entry when this agent name is a provider (e.g. deepseek), else None."""
    return (cfg.get("providers") or {}).get(agent)


def daily_cap(cfg: dict, agent: str) -> float | None:
    """USD a pay-per-token agent may spend per day: [providers.<name>] daily_usd, or [pay_per_token.<agent>]
    daily_usd for an agent billed per token by itself (dsh). None = no cap (subscription agents)."""
    pv = provider_of(cfg, agent) or ((cfg.get("pay_per_token") or {}).get(agent)) or {}
    cap = pv.get("daily_usd")
    return None if cap is None else float(cap)


def provider_env(cfg: dict, name: str) -> tuple[str, dict]:
    """A provider = an agent CLI pointed at another model API (e.g. DeepSeek through Claude Code).
    Values like "$DEEPSEEK_API_KEY" are read from the environment at run time; keys are never stored."""
    pv = (cfg.get("providers") or {}).get(name)
    if not pv:
        raise ValueError(f"unknown provider {name!r}; configured: {', '.join(cfg.get('providers') or {}) or 'none'}")
    env = {}
    for k, v in (pv.get("env") or {}).items():
        v = str(v)
        if v.startswith("$"):
            val = os.environ.get(v[1:])
            if not val:
                raise ValueError(f"provider {name} needs the environment variable {v[1:]} (your API key)")
            v = val
        env[k] = v
    return pv.get("agent", "claude"), env


def tier_spec(cfg: dict, tier: str, agent: str) -> dict:
    t = cfg["tiers"].get(tier)
    if t is None:
        raise ValueError(f"unknown tier {tier!r}; use one of {TIER_ORDER}")
    if t.get("delegate") is False:
        raise ValueError(f"{tier} ({t.get('label')}) means: do it yourself, don't delegate.")
    spec = t.get(agent)
    if not spec:
        raise ValueError(f"tier {tier} has no model configured for {agent}")
    return spec


def next_tier(tier: str) -> str | None:
    i = TIER_ORDER.index(tier)
    return TIER_ORDER[i + 1] if i + 1 < len(TIER_ORDER) else None
