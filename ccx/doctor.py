"""`ccx doctor`: say what works, what doesn't, and what is Unknown. No guessing."""
from __future__ import annotations

import json
import subprocess
import sys

from . import memory
from .config import Paths, claude_home, codex_home, load_config
from .runners import bin_argv, find_bin
from .sync import BEGIN


def _run(argv, timeout=20):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


HUB_FORMAT = 2   # bump when the hub's on-disk layout changes; `ccx init` migrates


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
    ct = codex_home() / "config.toml"
    has = ct.exists() and "ccx:begin hooks" in ct.read_text(encoding="utf-8")
    add("Codex SessionStart hook", "ok (trust once via /hooks)" if has else "missing", str(ct))

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
