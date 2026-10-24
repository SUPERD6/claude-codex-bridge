"""Setting up and wiring: init, sync, skills, uninstall, doctor, setup, selftest, improve."""
from __future__ import annotations

import json
import shutil
import time

from pathlib import Path

from .. import __version__, memory
from ..config import DELEGATE_AGENTS, data_dir, load_config, paths
from ..delegate import Request, compact, run
from ..runners import find_bin
from .common import _caller, _out, installed_agents


def cmd_selftest(a) -> int:
    """Smoke test against the REAL installed CLIs: one tiny read-only task per agent on its cheapest
    model. Shows login problems, start-up token cost and whether parsing works on this machine."""
    import tempfile
    p = paths()
    cfg = load_config(p)
    agents = [x.strip() for x in a.agents.split(",")] if a.agents else installed_agents()
    cheapest = {ag: tier_spec_safe(cfg, "T1", ag) for ag in agents}
    jobs = [(ag, cheapest[ag], None) for ag in agents]
    if a.provider:              # every model of that provider, through its agent CLI, instead of the agents' own
        pv = (cfg.get("providers") or {}).get(a.provider) or {}
        ag = pv.get("agent", "claude")
        jobs = [(ag, {"model": m, "effort": "low"}, a.provider) for m in pv.get("models") or []] or             [(ag, None, a.provider)]
    results = []
    with tempfile.TemporaryDirectory() as d:
        Path(d, "hello.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        for ag, spec, provider in jobs:
            if not spec or not find_bin(ag):
                results.append({"agent": ag, "ok": False, "error": "not installed / no T1 model"})
                continue
            req = Request(to=ag, brief="Read hello.py and report in one sentence what add() returns. "
                          "Do not edit anything.", mode="read", cwd=Path(d), caller="user", escalate=False,
                          fallback=False, label=f"selftest-{ag}", model=spec["model"], effort=spec["effort"],
                          ephemeral=True, provider=provider)     # leaves no session in the tools' history
            t0 = time.time()
            try:
                rec = run(req, p)
            except Exception as e:  # noqa: BLE001
                results.append({"agent": ag, "ok": False, "error": str(e)})
                continue
            c = compact(rec)
            results.append({"agent": ag, **({"provider": provider} if provider else {}), "model": c["model"], "ok": rec["ok"], "kind": rec.get("kind"),
                            "session": bool(rec.get("session_id")), "tokens": c["tokens"],
                            "ae_usd": (rec["attempts"][-1] or {}).get("ae_usd"),
                            "seconds": round(time.time() - t0, 1), "summary": (c.get("summary") or "")[:160]})
    _out({"selftest": results, "all_ok": all(r["ok"] for r in results)})
    return 0 if all(r["ok"] for r in results) else 2


def tier_spec_safe(cfg: dict, tier: str, agent: str) -> dict | None:
    try:
        from ..config import tier_spec
        return tier_spec(cfg, tier, agent)
    except ValueError:
        return None


def cmd_sync(a) -> int:
    from ..sync import sync_all
    parts = a.only.split(",") if a.only else ["skills", "memory", "hooks", "mcp"]
    plan = sync_all(paths(), apply=a.apply, parts=parts)
    for x in plan.actions:
        print(x)
    for w in plan.warnings:
        print("WARN", w)
    if not plan.actions:
        print("nothing to do")
    if not a.apply and plan.actions:
        print("\n(dry run — re-run with --apply to make these changes)")
    return 0


def _migrate_hub(p) -> list[str]:
    """Bring an older hub up to HUB_FORMAT. Each step is idempotent and only adds/renames ccx's own files."""
    from ..doctor import HUB_FORMAT
    vf = p.state / "version.json"
    cur = json.loads(vf.read_text(encoding="utf-8")).get("hub_format", 1) if vf.exists() else 1
    done = []
    if cur < 2:
        # format 2 (v0.2): ccx-owned settings.toml + learned skill state live under <hub>/ccx/
        p.state.mkdir(parents=True, exist_ok=True)
        done.append("1->2: settings.toml / routing-state.json / split-state.json now live in <hub>/ccx")
    vf.write_text(json.dumps({"hub_format": HUB_FORMAT, "ccx": __version__}), encoding="utf-8")
    return done


def _skills_install(p, replace: bool, apply: bool = False) -> int:
    """Link the repo's bundled skills into the hub's skills folder, so `git pull` upgrades them in place.
    Existing real folders (e.g. older copies) are kept unless --replace, which backs them up first.
    Dry run unless apply, like `ccx sync`."""
    from ..sync import _is_link, _link
    src_root = data_dir("skills")
    if apply:
        p.skills.mkdir(parents=True, exist_ok=True)
    rows = []
    will = "" if apply else "[dry-run] "
    for src in sorted(d for d in src_root.iterdir() if (d / "SKILL.md").exists()):
        dst = p.skills / src.name
        if _is_link(dst):
            ok = dst.resolve() == src.resolve()
            rows.append({"skill": src.name, "action": "already linked" if ok else "linked elsewhere: left alone"})
            continue
        if dst.exists():
            if not replace:
                rows.append({"skill": src.name, "action": "real folder exists: kept (use --replace to back it up and link)"})
                continue
            # outside the skills folder: a hub sync that links every folder with a SKILL.md would
            # otherwise install the backup as a second copy of the skill
            bak = p.state / "skill-backups" / f"{dst.name}-{time.strftime('%Y%m%d%H%M%S')}"
            rows.append({"skill": src.name, "action": f"{will}backed up to {bak}, then linked"})
            if apply:
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(bak))
        else:
            rows.append({"skill": src.name, "action": f"{will}linked"})
        if apply:
            _link(src, dst)
    _out({"hub_skills": str(p.skills), "skills": rows, "applied": apply,
          "note": ("your sync (ccx sync, or your own external sync) links the hub skills into both tools"
                   if apply else "dry run: add --apply")})
    return 0


def cmd_skills(a) -> int:
    """Find a skill in the shared library before writing a new one (names + descriptions only: cheap)."""
    p = paths()
    if a.skills_cmd == "install":
        return _skills_install(p, a.replace, a.apply)
    roots = [p.skills, data_dir("skills")]
    words = [w.lower() for w in a.query]
    seen, hits = set(), []
    for root in roots:
        for f in sorted(root.glob("*/SKILL.md")) if root.exists() else []:
            name = f.parent.name
            if name in seen:
                continue
            seen.add(name)
            head = f.read_text(encoding="utf-8", errors="replace")[:1500]
            desc = next((l.split(":", 1)[1].strip() for l in head.splitlines() if l.startswith("description:")), "")
            hay = (name + " " + desc).lower()
            score = sum(hay.count(w) for w in words) if words else 1
            if score:
                hits.append({"skill": name, "score": score, "description": desc[:200], "path": str(f.parent)})
    _out(sorted(hits, key=lambda h: -h["score"])[:a.limit])
    return 0


def cmd_improve(a) -> int:
    """Log a CONCRETE problem met while working and what would fix it (no speculative reviews)."""
    p = paths()
    f = p.state / "improvements.jsonl"
    if a.improve_cmd == "add":
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": a.by or _caller(None), "target": a.target,
               "problem": a.problem, "fix": a.fix or "", "status": "open"}
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        _out(row)
        return 0
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []
    _out([r for r in rows if a.all or r.get("status") == "open"])
    return 0


def cmd_init(a) -> int:
    _out(init_hub(a.hub, a.snapshot, a.external_sync))
    return 0


def init_hub(hub: str | None = None, snapshot: str | None = None, external_sync: str | None = None) -> dict:
    """Create the hub skeleton (only new files; nothing existing is changed). Used by `init` and `setup`."""
    from ..config import save_hub
    saved = None
    if hub:
        saved = save_hub(Path(hub).expanduser().resolve())
    p = paths()
    lay = p.state / "layout.toml"
    if snapshot or external_sync:
        p.state.mkdir(parents=True, exist_ok=True)
        lines = ["# hub layout for ccx (personal; lives in your hub, not in the repo)", "[layout]"]
        if snapshot:
            lines += [f"snapshot = {json.dumps(snapshot)}", 'snapshot_mode = "external"']
        if external_sync:
            lines.append(f"external_sync = {json.dumps(external_sync)}")
        lay.write_text("\n".join(lines) + "\n", encoding="utf-8")
    memory.ensure(p)
    seed = data_dir("hub-seed")
    reg = p.mcp_registry
    if not reg.exists():
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text((seed / "mcp" / "servers.json").read_text(encoding="utf-8"), encoding="utf-8")
    p.skills.mkdir(parents=True, exist_ok=True)
    p.runs.mkdir(parents=True, exist_ok=True)
    readme = p.state / "README.md"
    if not readme.exists():
        readme.write_text((seed / "ccx-README.md").read_text(encoding="utf-8"), encoding="utf-8")
    migrated = _migrate_hub(p)
    return {"hub": str(p.hub), "hub_saved_in": str(saved) if saved else None,
            "layout": {k: v for k, v in p.layout.items()},
            "memory": str(p.memory_index), "mcp_registry": str(reg), "migrated": migrated,
            "next": "ccx doctor, then ccx sync (dry run), then ccx sync --apply"}


def cmd_uninstall(a) -> int:
    from ..sync import uninstall
    plan = uninstall(paths(), apply=a.apply)
    for x in plan.actions:
        print(x)
    if not a.apply:
        print("\n(dry run — re-run with --apply to remove; your hub data is kept)")
    else:
        print("\nTo put it back: `ccx sync --apply` (hooks, memory, MCP), then `ccx skills install --replace --apply` "
              "(the ccx skills; your own copies restored above are backed up again), then `ccx doctor`.")
    return 0


def cmd_doctor(a) -> int:
    from ..doctor import doctor
    ok = doctor(paths())
    return 0 if ok else 1


def register(sub) -> None:
    sk = sub.add_parser("skills", help="find a skill in the shared library: ccx skills find pdf table")
    sks = sk.add_subparsers(dest="skills_cmd", required=True)
    skf = sks.add_parser("find"); skf.add_argument("query", nargs="*"); skf.add_argument("--limit", type=int, default=8)
    ski = sks.add_parser("install", help="link this repo's skills into the hub (git pull = upgrade)")
    ski.add_argument("--replace", action="store_true", help="back up existing copies and link instead")
    ski.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    sk.set_defaults(fn=cmd_skills)
    im = sub.add_parser("improve", help="log a concrete problem + fix for a skill/tool (ccx improve add ...)")
    ims = im.add_subparsers(dest="improve_cmd", required=True)
    ima = ims.add_parser("add"); ima.add_argument("target", help="skill or component name")
    ima.add_argument("problem"); ima.add_argument("--fix"); ima.add_argument("--by", choices=[*DELEGATE_AGENTS, "user"])
    iml = ims.add_parser("list"); iml.add_argument("--all", action="store_true")
    im.set_defaults(fn=cmd_improve)
    stt = sub.add_parser("selftest", help="tiny real run per installed agent (login, parsing, start-up tokens)")
    stt.add_argument("--agents", help="comma list, default: every installed agent")
    stt.add_argument("--provider", help="test each model of this provider instead (e.g. deepseek; needs its key)")
    stt.set_defaults(fn=cmd_selftest)
    s = sub.add_parser("sync", help="link skills/memory/hooks/MCP into both tools (dry run unless --apply)")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--only", help="comma list of: skills,memory,hooks,mcp")
    s.set_defaults(fn=cmd_sync)
    i = sub.add_parser("init", help="create the shared hub skeleton")
    i.add_argument("--hub", help="where your personal hub lives; remembered in ~/.ccx/config.toml")
    i.add_argument("--snapshot", help="use an existing file (relative to the hub) as the shared snapshot that "
                                      "both tools already load, e.g. AGENTS.md; ccx then never edits their instruction files")
    i.add_argument("--external-sync", help="command that already links skills/MCP into both tools; ccx defers to it")
    i.set_defaults(fn=cmd_init)
    stp = sub.add_parser("setup", help="guided first run: check, hub, init, sync (asks first), doctor, selftest")
    stp.add_argument("--yes", action="store_true", help="accept every step (scripts / CI)")
    stp.add_argument("--hub", help="hub folder (default: the one already set, or ~/.ccx-hub)")
    stp.set_defaults(fn=lambda a: __import__("ccx.setup", fromlist=["run"]).run(yes=a.yes, hub=a.hub))
    sub.add_parser("doctor", help="check installs, logins and wiring").set_defaults(fn=cmd_doctor)
    u = sub.add_parser("uninstall", help="remove ccx hooks/blocks/links from both tools (dry run unless --apply)")
    u.add_argument("--apply", action="store_true")
    u.set_defaults(fn=cmd_uninstall)
