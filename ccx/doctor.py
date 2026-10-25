"""`ccx doctor`: say what works, what doesn't, and what is Unknown. No guessing."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from . import memory
from .config import Paths, claude_home, codex_home, load_config
from .runners import bin_argv, find_bin
from .sync import BEGIN, codex_hook_needs_call_operator


def _run(argv, timeout=20):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


HUB_FORMAT = 2   # bump when the hub's on-disk layout changes; `ccx init` migrates

# what to add to ~/.codex/config.toml so a Codex lead can run `ccx run` (codex-cli 0.164 `exec --help`, 2026-10-24)
CODEX_LEAD_FIX = ('[sandbox_workspace_write]\nwritable_roots = ["{hub}"]\nnetwork_access = true\n'
                  '(or start Codex with --add-dir "{hub}")')
# on Windows that is not enough: workspace-write runs commands as a separate sandbox account (CodexSandboxOnline), and a
# Claude sub-agent started there refused every edit ("sensitive file") and saved no session, even with the hub and
# ~/.claude as writable roots and the network on (real runs, codex-cli 0.164 + Claude Code, 2026-10-24)
CODEX_LEAD_FIX_WIN = ('on Windows, give lead sessions full access, e.g. a profile:\n[profiles.lead]\n'
                      'sandbox_mode = "danger-full-access"\nthen start the lead with `codex -p lead`')


# Safer than full access, not yet checked on a real run: keep workspace-write and let only ccx's hand-out commands run
# outside the sandbox with a Codex rule (learn.chatgpt.com/docs/agent-configuration/rules, read 2026-10-25: "allow" =
# "Run the command outside the sandbox without prompting"; rules are experimental). The pattern is an exact argv prefix,
# so it names this copy of ccx exactly as the lead is told to call it (`codex execpolicy check` agrees, codex-cli 0.164).
LEAD_VERBS = ("run", "ask", "resume", "discuss")
FULL_ACCESS_NOTE = ("safety: in full access every command the lead runs has your rights, unsandboxed (files, network, "
                    "credentials). Safer, not yet checked on a real run: keep workspace-write and let only ccx out of "
                    "the sandbox with the rule `ccx doctor --codex-rule` prints")


def codex_lead_rule(argv: list[str] | None = None) -> str:
    """A ~/.codex/rules/ccx.rules entry that lets this copy of ccx hand work out from a sandboxed Codex lead."""
    from .config import ccx_argv
    pat = ", ".join(json.dumps(x) for x in (argv or ccx_argv())) + ", [" + ", ".join(json.dumps(v) for v in LEAD_VERBS) + "]"
    return ("prefix_rule(\n"
            f"    pattern = [{pat}],\n"
            '    decision = "allow",\n'
            '    justification = "ccx starts the sub-agent CLI as you, so it can edit files and keep its session",\n'
            ")\n")


def codex_rule_allows(rules_dir, argv: list[str] | None = None, check=None) -> bool:
    """Does a rule in ~/.codex/rules let `ccx run` out of the sandbox? Asked of Codex itself (`codex execpolicy
    check`), so the answer follows its own matching. `check(rules_file, argv) -> decision` for tests."""
    from pathlib import Path
    from .config import ccx_argv
    files = sorted(Path(rules_dir).glob("*.rules")) if Path(rules_dir).is_dir() else []
    if not files:
        return False
    cmd = [*(argv or ccx_argv()), "run", "--to", "claude", "x"]
    if check is None:
        def check(f, a):
            rc, out = _run([*bin_argv("codex"), "execpolicy", "check", "--rules", str(f), "--", *a])
            try:
                return json.loads(out).get("decision") if rc == 0 else None
            except ValueError:
                return None
    return any(check(f, cmd) == "allow" for f in files)


def codex_lead_sandbox(config_text: str, hub, windows: bool | None = None, rule: bool = False) -> tuple[str, str]:
    """Can a Codex lead run `ccx run`? ccx writes its run records into the hub, and the sub-agent CLI it starts needs
    the network. In Codex's workspace-write sandbox both are blocked unless configured: a real headless Codex lead
    got `[WinError 5] Access is denied` on the hub's runs folder (seven-cores check, 2026-10-24)."""
    import os
    import tomllib
    from pathlib import Path
    windows = os.name == "nt" if windows is None else windows
    try:
        cfg = tomllib.loads(config_text) if config_text else {}
    except tomllib.TOMLDecodeError as e:
        return "Unknown", f"config.toml does not parse: {e}"
    # not set: Codex picks read-only or workspace-write from the project's trust, so check as workspace-write
    mode = cfg.get("sandbox_mode") or "not set"
    if mode == "danger-full-access":
        return "ok", f"sandbox_mode = danger-full-access; {FULL_ACCESS_NOTE}"
    if rule and mode != "read-only":
        return "Unknown", (f"sandbox_mode = {mode} and a rule lets `ccx run` out of the sandbox: by Codex's docs that "
                           "should work, but it has not been checked on a real run (rules are experimental)")
    if windows:
        return "WARN", (f"sandbox_mode = {mode}: a Codex lead cannot hand work to Claude through `ccx run` in this "
                        f"sandbox on Windows (checked on real runs); {CODEX_LEAD_FIX_WIN}\nor, safer but not yet "
                        "checked on a real run: keep the sandbox and add the rule `ccx doctor --codex-rule` prints")
    fix = CODEX_LEAD_FIX.format(hub=Path(hub).as_posix())
    if mode == "read-only":
        return "WARN", f"sandbox_mode = read-only: a Codex lead cannot run `ccx run`; use workspace-write and add\n{fix}"
    ws = cfg.get("sandbox_workspace_write") or {}

    def norm(x) -> str:
        return str(Path(x).expanduser().resolve()).rstrip("\\/").lower()
    roots = {norm(r) for r in ws.get("writable_roots") or []}
    hub_ok = any(norm(hub) == r or norm(hub).startswith(r + ("\\" if "\\" in r else "/")) for r in roots)
    missing = [w for w, ok in (("the hub is not a writable root", hub_ok),
                               ("network_access is off", ws.get("network_access") is True)) if not ok]
    if not missing:
        return "ok", f"sandbox_mode = {mode}, hub writable, network on (not checked on a real run outside Windows)"
    return "WARN", (f"sandbox_mode = {mode} ({'; '.join(missing)}): a Codex lead's `ccx run` will fail. "
                    f"Add to config.toml (profiles may override it; not checked on a real run outside Windows):\n{fix}")


def version_drift(version_out: str, tested: str, official: bool) -> tuple[str, str] | None:
    """(state, detail) when the installed CLI's major.minor differs from the version the adapter's flags were checked
    against (I8), None when they match. Patch releases are taken as compatible."""
    import re
    got = re.search(r"(\d+)\.(\d+)", version_out or "")
    want = re.search(r"(\d+)\.(\d+)", tested or "")
    if not got or not want:
        return "Unknown", f"could not read a version from {(version_out or '').strip()[:60]!r}"
    if got.groups() == want.groups():
        return None
    have = got.group(0)
    if official:
        return "WARN", (f"installed {have}, flags checked against {tested}: run the release check (H15: a real "
                        "read, write and resume run on this version) before relying on it")
    return "WARN", (f"installed {have}, adapter written for {tested}: not verified on this version (community "
                    "adapter; flags or output may have changed)")


# OpenAI's Claude Code plugin (github.com/openai/codex-plugin-cc v1.0.6, read 2026-10-25): marketplace "openai-codex",
# plugin "codex"; its hooks.json adds SessionStart, SessionEnd and an optional Stop review gate of its own.
CODEX_PLUGIN = "codex@openai-codex"


def codex_plugin(home) -> tuple[str, str] | None:
    """(state, detail) when the official codex-plugin-cc is installed or enabled in Claude Code (J8), else None.
    Its hooks run commands of its own, next to ccx's; what could go wrong is ccx's own hook being there twice."""
    from pathlib import Path
    home = Path(home)

    def js(f: Path) -> dict:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}
    installed = any(str(k).startswith(CODEX_PLUGIN) for k in (js(home / "plugins" / "installed_plugins.json")
                                                               .get("plugins") or {}))
    settings = js(home / "settings.json")
    enabled = (settings.get("enabledPlugins") or {}).get(CODEX_PLUGIN)
    if not installed and not enabled:
        return None
    ours = sum("mem delta" in json.dumps(g) for g in (settings.get("hooks") or {}).get("SessionStart") or [])
    state = "WARN" if ours > 1 else "info"
    return state, (f"OpenAI's codex-plugin-cc is {'enabled' if enabled else 'installed (not enabled)'}: its "
                   "SessionStart/SessionEnd/Stop hooks run beside ccx's, which is there "
                   f"{'once' if ours == 1 else f'{ours} times (run `ccx sync --apply`)' if ours else 'not at all'}. "
                   "Using both together is not tested yet; its Stop review gate, if you turn it on, reviews with "
                   "Codex at every stop on top of ccx's review")


def routing_prior(p: Paths) -> tuple[str, str]:
    """Where routing's starting point comes from: the hand-set priors and, for rungs this hub has not learned yet,
    the built-in A/B head start (task-routing [observed])."""
    try:
        from . import learn
        tr = learn.module(p, "routing")
        pri, st = tr.load_priors(), tr.load_state()
    except Exception as e:  # noqa: BLE001
        return "WARN", f"task-routing not readable: {e}"[:120]
    head = f"priors.toml {pri.get('as_of', '?')}"
    if not hasattr(tr, "observed_offsets"):
        return "ok", head + (" (the hub's task-routing predates the built-in A/B head start: update the checkout "
                             "it links to, or `ccx skills install`)")
    obs, learned = tr.observed_offsets(pri), st.get("offsets") or {}
    if not obs:
        return "ok", head
    parts = [f"{k} {v:+.2f}" + (" (learned here since)" if k in learned else "") for k, v in sorted(obs.items())]
    return "ok", (f"{head} + {pri['observed'].get('source', 'built-in outcomes')} at weight "
                  f"{pri['observed'].get('weight', 0.5)}: " + ", ".join(parts))


def doctor(p: Paths) -> bool:
    rows: list[tuple[str, str, str]] = []

    def add(name, state, detail=""):
        rows.append((name, state, detail))

    add("python", "ok" if sys.version_info >= (3, 11) else "FAIL", sys.version.split()[0])
    try:
        load_config(p)
        add("tiers.toml", "ok")
    except Exception as e:  # noqa: BLE001
        add("tiers.toml", "FAIL", str(e))

    from .agents import all_adapters
    for ad in all_adapters():
        agent, official = ad.name, ad.support == "official"
        if not find_bin(agent):
            if official:                       # the two official agents are expected; the rest are optional
                add(f"{agent} CLI", "FAIL", "not on PATH")
            continue
        rc, out = _run([*bin_argv(agent), "--version"])
        ver = out.splitlines()[0] if out else ""
        can = ", ".join(k for k, v in ad.capabilities().items() if v)
        add(f"{agent} CLI" + ("" if official else " (optional)"), "ok" if rc == 0 else ("FAIL" if official else "WARN"),
            f"{ver} (flags checked against {ad.tested_version}; {ad.support}; {ad.vendor}; {can})")
        if rc == 0 and (drift := version_drift(ver, ad.tested_version, official)):
            add(f"{agent} version", *drift)
        if ad.locate and find_bin(agent) == ad.locate():        # not on PATH: say where ccx found it
            add(f"{agent} location", "ok", f"{find_bin(agent)} (found from the installed app, not on PATH)")
        if not ad.login_argv:
            add(f"{agent} login", "Unknown", "ccx can't check this tool's login; its first run will tell")
            continue
        rc, out = _run([*bin_argv(agent), *ad.login_argv])
        try:                                   # claude auth status prints JSON
            import json as _j
            js = _j.loads(out)
            if isinstance(js, dict) and "loggedIn" in js:
                ok_ = bool(js["loggedIn"])
                add(f"{agent} login", "ok" if ok_ else "FAIL",
                    (js.get("authMethod") or "") if ok_ else f"not logged in: run `{agent}` once and log in")
                continue
        except ValueError:
            pass
        low = out.lower()
        if rc == 0 and "not" not in low:
            state = "ok"
        elif rc != 0 or "not logged" in low or "logged out" in low:
            state = "FAIL"
        else:
            state = "Unknown"
        add(f"{agent} login", state, out.splitlines()[0][:90] if out else "")

    add("hub", "ok" if p.hub.exists() else "FAIL", str(p.hub))
    vf = p.state / "version.json"
    if vf.exists():
        import json as _json
        hv = _json.loads(vf.read_text(encoding="utf-8")).get("hub_format")
        add("hub format", "ok" if hv == HUB_FORMAT else "WARN",
            f"{hv}" + ("" if hv == HUB_FORMAT else f" (this ccx writes {HUB_FORMAT}: run `ccx init` to migrate)"))
    if p.memory_index.exists():
        size = p.memory_index.stat().st_size
        if p.snapshot_external:
            # the user's own shared rules file: its size is theirs to decide; ccx only folds its journal into it
            add("memory snapshot", "ok", f"{size} bytes (external: your own file; ccx only appends its section)")
        else:
            add("memory snapshot", "ok" if size < 6000 else "WARN",
                f"{size} bytes" + (" (big: run `ccx mem compact` and trim)" if size >= 6000 else ""))
        n = len(memory.entries(p))
        add("memory journal", "ok" if n < 40 else "WARN",
            f"{n} entries" + (" (run `ccx mem compact`)" if n >= 40 else ""))
    else:
        add("memory snapshot", "FAIL", "run `ccx init`")

    lay = p.layout
    add("hub layout", "ok", f"snapshot={lay['snapshot']} ({lay['snapshot_mode']})"
        + (f", external sync: {lay['external_sync']}" if lay.get("external_sync") else ""))
    add("routing prior", *routing_prior(p))
    if p.snapshot_external:
        add("snapshot wiring", "ok (external)", "the tools load the snapshot themselves; ccx writes no blocks")
    else:
        cm = claude_home() / "CLAUDE.md"
        am = codex_home() / "AGENTS.md"
        tag = BEGIN.format(id="memory")
        add("Claude memory block", "ok" if cm.exists() and tag in cm.read_text(encoding="utf-8") else "missing", str(cm))
        add("Codex memory block", "ok" if am.exists() and tag in am.read_text(encoding="utf-8") else "missing", str(am))

    sj = claude_home() / "settings.json"
    try:
        has = "mem delta" in json.dumps(json.loads(sj.read_text(encoding="utf-8"))["hooks"]["SessionStart"])
    except Exception:  # noqa: BLE001
        has = False
    add("Claude SessionStart hook", "ok" if has else "missing", str(sj))
    if (cp := codex_plugin(claude_home())):
        add("codex-plugin-cc", *cp)
    ct = codex_home() / "config.toml"
    has = ct.exists() and "ccx:begin hooks" in ct.read_text(encoding="utf-8")
    if has and os.name == "nt" and codex_hook_needs_call_operator(ct.read_text(encoding="utf-8")):
        add("Codex SessionStart hook", "WARN", "written before the Windows fix: Codex runs hooks through PowerShell and "
            "this command starts with a quoted path, so it runs nothing. Run `ccx sync --apply`, then trust the hooks "
            f"again in Codex with /hooks ({ct})")
    else:
        add("Codex SessionStart hook", "ok (trust once via /hooks)" if has else "missing", str(ct))
    if find_bin("codex"):
        add("Codex as lead (sandbox)", *codex_lead_sandbox(ct.read_text(encoding="utf-8") if ct.exists() else "", p.hub,
                                                           rule=codex_rule_allows(codex_home() / "rules")))

    skill = "agent-delegate"
    for tool, d in (("claude", claude_home() / "skills"), ("codex", codex_home() / "skills")):
        add(f"{tool} has {skill}", "ok" if (d / skill / "SKILL.md").exists() else "missing", str(d))

    w = max(len(r[0]) for r in rows)
    for name, state, detail in rows:
        print(f"{name.ljust(w)}  {state:<8} {detail}")
    bad = [r for r in rows if r[1] in ("FAIL",)]
    if any(r[1] == "missing" for r in rows):
        print("\nmissing items: run `ccx sync` (dry run) then `ccx sync --apply`.")
    return not bad
