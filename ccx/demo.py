"""`ccx demo` (U6): a populated `ccx ui` in under two minutes, with no Claude or Codex account, offline.

build() writes a throwaway hub under the system's temporary folder, seeded from this file's own small fake data
(deterministic: the same records every time, only the times follow the clock): two projects; runs in each state (done
and accepted, review issues with real before/after snapshots so the decision card shows both columns and a file
mismatch, running, failed on its environment); a three-piece work queue with one piece whose worktree is not merged
yet; a board thread stopped by the machine-message cap and one message that asks the person; a ledger with a month of
costs, so the overview shows spend and the saving estimate; a handoff between leads, so the switch-lead panel has a
history. Then `ccx ui` serves it: the same server and page, which only shows a "demo data" mark (the hub carries the
marker file DEMO_MARK).

Nothing outside that folder is written: the hub, the tool homes (an empty Codex home and a Claude home holding one
fake lead conversation) and the project folders are all inside it, and env() points CCX_HUB, CLAUDE_CONFIG_DIR,
CODEX_HOME and DSH_HOME at them for the demo process only. No CLI is started; git is used, when installed, only inside
the demo projects (with its own name, no signing, no hooks) for the snapshots. In a demo hub the page runs only
commands that record something there (a verdict, a handoff); one that would start an agent is shown, not run."""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .config import Paths

DEMO_MARK = "ccx-demo.json"
DEMO_DIRS = ("hub", "projects", "homes")          # all build() writes under its folder
SEED = 7
LEAD_SESSION = "0d3m0c1a-0000-4000-8000-00000000c1a0"     # the demo's Claude lead conversation (fake)
SHOP, DOCS, QUIET = "shop-api", "docs-site", "mobile-app"


def is_demo(p: Paths) -> bool:
    return (p.hub / DEMO_MARK).is_file()


def env(base: Path) -> dict[str, str]:
    """The environment that keeps a demo process inside `base`: its hub and its own (fake) tool homes."""
    base = Path(base)
    return {"CCX_HUB": str(base / "hub"), "CLAUDE_CONFIG_DIR": str(base / "homes" / "claude"),
            "CODEX_HOME": str(base / "homes" / "codex"), "DSH_HOME": str(base / "homes" / "dsh")}


def new_base() -> Path:
    return Path(tempfile.mkdtemp(prefix="ccx-demo-"))


# ------------------------------------------------------------------ git, inside the demo projects only
def _git(cwd: Path, *args: str) -> bool:
    try:
        r = subprocess.run(["git", "-c", "user.name=ccx demo", "-c", "user.email=demo@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull, "-c", "core.autocrlf=false",
                            *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _write(f: Path, text: str) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------ run records
def _attempt(agent: str, model: str, effort: str, secs: float, tin: int, tout: int, usd: float) -> dict:
    return {"agent": agent, "rung": f"{agent}:{model}:{effort}", "model": model, "effort": effort, "seconds": secs,
            "usage": {"input_tokens": tin, "cached_input_tokens": tin * 3, "output_tokens": tout}, "ae_usd": usd}


def _run(p: Paths, run_id: str, cwd: Path, brief: str, ts: float, *, to: str = "codex", model: str = "gpt-6-luna",
         effort: str = "low", caller: str = "claude", lead: str | None = LEAD_SESSION, secs: float = 140.0,
         usd: float = 0.004, record: bool = True, **kw) -> dict:
    rec = {"run_id": run_id, "label": None, "to": to, "caller": caller, "mode": "write", "cwd": str(cwd), "tier": "T1",
           "session_id": None, "lead_session": lead, "ts": ts, "first_rung": f"{to}:{model}:{effort}",
           "attempts": [_attempt(to, model, effort, secs, 9000, 1400, usd)],
           "result": {"status": "done", "summary": "", "files_changed": [], "verification": ""},
           "ok": True, "state": "finished", "kind": None}
    rec.update(kw)
    d = p.runs / run_id
    d.mkdir(parents=True, exist_ok=True)
    _write(d / "run.json", json.dumps(rec, ensure_ascii=False, indent=1))
    _write(d / "prompt.md", f"[ccx sub-task {run_id}]\n## Task\n{brief}\n\n## Finish\nReturn the result JSON.\n")
    if record and rec["state"] == "finished":
        from . import ledger
        ledger.append(p, rec)
    return rec


def _verdict(p: Paths, run_id: str, ok: bool, ts: float, **kw) -> None:
    from . import ledger
    ledger.append_event(p, {"type": "verify", "run_id": run_id, "ok": ok, "ts": ts, "by": "user", **kw})


# ------------------------------------------------------------------ the two projects
def _shop(p: Paths, root: Path, now: float) -> dict:
    """shop-api: a Claude lead's runs in every state, a board, a handoff Codex -> Claude two days ago."""
    from . import board, project, workspace
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "orders.py", "def total(items):\n    return sum(i['price'] for i in items)\n")
    _write(root / "tests" / "test_orders.py", "from orders import total\n\n\ndef test_total():\n"
           "    assert total([{'price': 2}]) == 2\n")
    _write(root / "README.md", "# shop-api\n\nA small demo service (ccx demo data).\n")
    project.init(root)                         # first: its .gitignore lines go into the first commit
    has_git = _git(root, "init", "-q") and _git(root, "add", "-A") and _git(root, "commit", "-qm", "start")
    out = {}
    out["ok"] = _run(p, "demo-r-ok", root, "Add a /health endpoint that returns the build version", now - 26 * 3600,
                     result={"status": "done", "summary": "Added GET /health returning {status, version}.",
                             "files_changed": ["health.py", "tests/test_health.py"],
                             "verification": "pytest -q tests/test_health.py: 2 passed"},
                     check={"cmd": "pytest -q", "exit": 0, "passed": True, "tail": "6 passed in 0.41s"},
                     review={"verdict": "pass", "issues": [], "by": "claude:haiku:low"}, verdict={"ok": True})
    _verdict(p, "demo-r-ok", True, now - 25 * 3600)

    # review issues, with ccx's own snapshots: the card shows what it says beside what ccx ran, and a mismatch
    rid = "demo-r-review"
    rv = _run(p, rid, root, "Apply a discount code to the order total; codes expire at midnight UTC", now - 3 * 3600,
              kind="review_failed",
              result={"status": "done", "summary": "Discount codes applied in total(); expiry checked against UTC.",
                      "files_changed": ["orders.py", "discounts.py", "tests/test_discounts.py"],
                      "verification": "ran pytest -q: 7 passed; tried code SAVE10 by hand"},
              check={"cmd": "pytest -q", "exit": 0, "passed": True,
                     "tail": "tests/test_orders.py ..\ntests/test_discounts.py ...\n7 passed in 0.52s"},
              review={"verdict": "issues", "by": "claude:sonnet:medium",
                      "issues": ["[must] an expired code is still applied for the last hour (local time used in "
                                 "is_expired)", "[should] a 100% code makes the total negative with shipping"]})
    if has_git:
        run_dir = p.runs / rid
        snap = workspace.undo_snapshot(root)
        if snap:
            _write(run_dir / "undo.json", json.dumps(snap))
            _write(root / "orders.py", "from discounts import apply\n\n\ndef total(items, code=None):\n"
                   "    return apply(sum(i['price'] for i in items), code)\n")
            _write(root / "discounts.py", "import datetime\n\nCODES = {'SAVE10': 0.10}\n\n\ndef is_expired(code):\n"
                   "    return datetime.datetime.now().hour >= 23\n\n\ndef apply(amount, code):\n"
                   "    if not code or is_expired(code):\n        return amount\n"
                   "    return amount * (1 - CODES.get(code, 0))\n")
            _write(root / "checkout.py", "# touched but not reported by the agent\nSHIPPING = 4.5\n")
            workspace.mark_run_end(run_dir, root)
            workspace.write_end_tree(run_dir, root)
    out["review"] = rv

    out["running"] = _run(p, "demo-r-running", root, "Write the OpenAPI description for the orders endpoints",
                          now - 95, to="claude", model="sonnet", effort="medium", state="running", ok=False,
                          result=None, attempts=[], record=False)
    out["env"] = _run(p, "demo-r-env", root, "Profile the slow /orders listing and add an index", now - 5 * 3600,
                      to="deepseek", model="deepseek-flash", effort="high", ok=False, kind="env",
                      error="environment: the database the profiler needs is not running (connection refused on "
                            "localhost:5432); nothing was changed",
                      result={"status": "failed", "summary": "Could not start: Postgres is not running here.",
                              "files_changed": [], "verification": ""})

    # the board: a thread stopped by the machine-message cap, and one message that asks the person
    turns = [("claude", "codex", "Should `<OrderForm>` validate the discount code itself, or leave it to the API?"),
             ("codex", "claude", "The API: the form can't know the expiry. Keep `<OrderForm>` dumb."),
             ("claude", "codex", "Then the API has to answer 422 with a reason the form can show."),
             ("codex", "claude", "Agreed on 422, but the reason should be a code, not English text."),
             ("claude", "codex", "A code means a lookup table in the form, which is what we wanted to avoid."),
             ("codex", "claude", "Both: a code plus a default message `<OrderForm>` can show. Who owns the table?")]
    first = None
    for frm, to, text in turns:
        e = board.post(root, frm, to, text, thread="discount-errors" if first is None else None,
                       reply_to=first, max_machine=board.MAX_MACHINE)
        first = e["id"]
    board.post(root, "codex", "all", "Release notes for 0.4 are drafted in RELEASE.md. @person can we ship on "
               "Friday, or wait for the discount fix?", thread="release-0.4")

    # leads over time: Codex led until two days ago, then handed over to Claude (the current lead)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 50 * 3600))
    doc = (f"<!-- ccx:handoff from=codex to=claude ts={ts} -->\n# Handoff codex -> claude ({ts})\n\n"
           "## Done\n- orders API skeleton, tests green\n## Decisions (and why)\n- money as integer cents (no float "
           "rounding)\n## Open\n- discount codes\n## Next\n- /health, then discounts\n")
    _write(root / ".ccx" / "handoffs" / f"{ts.replace(':', '')}-codex-to-claude.md", doc)
    return out


def _docs(p: Paths, root: Path, now: float) -> dict:
    """docs-site: a Codex lead's work queue of three pieces, one done and merged, one done in a worktree that is not
    merged yet, one waiting on it."""
    from . import project
    from . import queue as wq
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "index.md", "# Docs\n\nDemo pages (ccx demo data).\n")
    project.init(root)
    if _git(root, "init", "-q"):
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "start")
    wq.add(root, "Move the install guide to one page", "Merge install-*.md into install.md, keep the anchors")
    wq.add(root, "Add a search box (client side, no service)", "Static index at build time; no external service")
    wq.add(root, "Link every page from the new search index", "After the search box is merged", deps=["q2"])
    r1 = _run(p, "demo-q1", root, "Move the install guide to one page", now - 7 * 3600, to="claude", model="haiku",
              caller="codex", lead=None, label="q:q1", usd=0.0021,
              result={"status": "done", "summary": "install.md now holds all three guides; old anchors redirect.",
                      "files_changed": ["install.md", "install-linux.md", "install-mac.md"],
                      "verification": "built the site, clicked every old anchor"},
              check={"cmd": "python build.py --check-links", "exit": 0, "passed": True, "tail": "0 broken links"})
    _verdict(p, "demo-q1", True, now - 6.5 * 3600)
    wq.update(root, "q1", status="done", run="demo-q1", agent="claude", cost_usd=0.0021, verdict=True)
    wt = str(root.parent / ".ccx-worktrees" / root.name / "demo-q2")
    _run(p, "demo-q2", root, "Add a search box (client side, no service)", now - 2 * 3600, to="codex",
         model="gpt-6-luna", effort="medium", caller="codex", lead=None, label="q:q2", usd=0.0064,
         result={"status": "done", "summary": "Search box with a prebuilt JSON index (38 KB); no network calls.",
                 "files_changed": ["search.js", "build.py", "index.md"], "verification": "built, searched 'install'"},
         check={"cmd": "python build.py --check-links", "exit": 0, "passed": True, "tail": "0 broken links"},
         worktree=wt)
    wq.update(root, "q2", status="done", run="demo-q2", agent="codex", cost_usd=0.0064, worktree=wt)
    wq.set_budget(root, 0.05)
    return {"q1": r1}


def _ledger_month(p: Paths, now: float, roots: list[Path]) -> None:
    """A month of sub-agent runs in the ledger only (no run folders): the overview's spend and saving estimate."""
    from . import ledger
    from .ui import month_start
    rnd = random.Random(SEED)
    start = month_start(now)
    span = max(3600.0, now - start - 6 * 3600)
    mix = [("codex", "gpt-6-luna", "low", 0.003), ("codex", "gpt-6.1-sol", "medium", 0.02),
           ("claude", "haiku", "low", 0.004), ("claude", "sonnet", "medium", 0.03), ("deepseek", "deepseek-flash", "low", 0.001)]
    for i in range(36):
        agent, model, effort, usd = mix[rnd.randrange(len(mix))]
        ts = start + span * (i + rnd.random()) / 36
        tin, tout = rnd.randint(6000, 40000), rnd.randint(800, 6000)
        ok = rnd.random() > 0.15
        rec = {"run_id": f"demo-m{i:02d}", "label": None, "to": agent, "caller": "claude" if i % 3 else "codex",
               "mode": "write", "ok": ok, "ts": ts, "kind": None if ok else "check_failed", "cwd": str(roots[i % 2]),
               "attempts": [_attempt(agent, model, effort, rnd.uniform(40, 400), tin, tout,
                                     round(usd * rnd.uniform(0.5, 2.0), 5))],
               "result": {"status": "done" if ok else "failed"}, "route": {"b": rnd.choice([2, 3, 4, 5])}}
        ledger.append(p, rec)
        if ok and rnd.random() > 0.3:
            _verdict(p, rec["run_id"], rnd.random() > 0.1, ts + 600)


def _claude_session(home: Path, root: Path, now: float) -> None:
    """One fake Claude Code lead conversation in shop-api: the page shows it as the current lead, and the switch-lead
    button builds its handoff from it (`ccx handoff --from-transcript claude`), as with a real session file."""
    from .transcript import CLAUDE_SLUG_MAX, long_path
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
    if len(slug) > CLAUDE_SLUG_MAX:              # as Claude Code names a long folder: cut, plus a suffix
        slug = slug[:CLAUDE_SLUG_MAX] + "-demo"
    f = long_path(home / "projects", len(slug) + 60) / slug / f"{LEAD_SESSION}.jsonl"   # Windows: past 260 chars
    lines = [
        {"type": "user", "sessionId": LEAD_SESSION, "cwd": str(root),
         "message": {"role": "user", "content": "Discount codes for the shop API: apply them at checkout, expire at "
                                                "midnight UTC, and keep the tests green"}},
        {"type": "assistant", "sessionId": LEAD_SESSION, "cwd": str(root),
         "message": {"id": "msg_demo_1", "role": "assistant", "model": "claude-opus-demo",
                     "content": [{"type": "text", "text": "Plan: /health first, then discounts (sent to Codex), "
                                                         "then the OpenAPI description (sent to Claude)."}],
                     "usage": {"input_tokens": 1200, "output_tokens": 300}}},
        {"type": "user", "sessionId": LEAD_SESSION, "cwd": str(root),
         "message": {"role": "user", "content": "The review found the expiry uses local time. Fix that before Friday."}},
        {"type": "assistant", "sessionId": LEAD_SESSION, "cwd": str(root),
         "message": {"id": "msg_demo_2", "role": "assistant", "model": "claude-opus-demo",
                     "content": [{"type": "text", "text": "Noted: is_expired must compare in UTC; checking the "
                                                         "diff before another round."}],
                     "usage": {"input_tokens": 1800, "output_tokens": 240}}},
    ]
    _write(f, "\n".join(json.dumps(x) for x in lines) + "\n")
    os.utime(f, (now, now))


def build(base: Path | None = None, now: float | None = None) -> Paths:
    """Write the demo under `base` (default: a new folder in the system's temporary folder) and return its hub."""
    base = Path(base) if base else new_base()
    now = now or time.time()
    e = env(base)
    hub = Path(e["CCX_HUB"])
    if hub.exists() and not is_demo(Paths(hub)):
        raise ValueError(f"{hub} exists and is not a ccx demo hub: not touching it")
    if not hub.exists() and base.is_dir() and any(base.iterdir()):
        raise ValueError(f"{base} is not empty and holds no ccx demo: give a new or empty folder, or an earlier demo")
    if hub.exists():                           # an earlier demo here: start again from nothing (same records)
        for sub in DEMO_DIRS:
            if (base / sub).exists():
                _rmtree(base / sub)
    for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "DSH_HOME"):
        Path(e[k]).mkdir(parents=True, exist_ok=True)
    p = Paths(hub)
    p.runs.mkdir(parents=True, exist_ok=True)
    _write(hub / DEMO_MARK, json.dumps({"demo": True, "created": now, "note": "ccx demo data: made up, safe to "
                                        "delete. Written by `ccx demo`; nothing here is real work."}, indent=1))
    _write(hub / "README-DEMO.txt", "DEMO DATA written by `ccx demo`. Made-up projects, runs and costs; delete this "
           "folder whenever you like. Your real hub and your tools' settings were not touched.\n")
    projects = base / "projects"
    shop, docs = projects / SHOP, projects / DOCS
    saved = {k: os.environ.get(k) for k in e}
    os.environ.update(e)                       # project.init / board / queue read nothing else, but be sure
    try:
        _shop(p, shop, now)
        _docs(p, docs, now)
        _ledger_month(p, now, [shop, docs])
        _claude_session(Path(e["CLAUDE_CONFIG_DIR"]), shop, now)
        (projects / QUIET).mkdir(parents=True, exist_ok=True)
        cat = {"projects": [
            {"path": str(shop), "name": SHOP, "last_active": now - 60, "summary": "Orders and discounts API"},
            {"path": str(docs), "name": DOCS, "last_active": now - 2 * 3600, "summary": "Documentation site"},
            {"path": str(projects / QUIET), "name": QUIET, "last_active": now - 9 * 86400,
             "summary": "Paused: waiting for the design"}]}
        _write(p.state / "projects.json", json.dumps(cat, indent=1))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return p


def remove(base: Path, owned: bool = False) -> bool:
    """Delete a demo folder: one build() made (its hub carries the marker), or with `owned` a folder new_base() made
    for this process (a build that failed before the marker). True when the folder is gone."""
    base = Path(base)
    if base.exists() and (owned or is_demo(Paths(base / "hub"))):
        _rmtree(base)
    return not base.exists()


def _rmtree(d: Path) -> None:
    """shutil.rmtree that also removes read-only files (git keeps its objects read-only on Windows) and paths past
    260 characters (the fake session file is written through the Windows long-path prefix; the tree is removed
    through it too)."""
    if os.name == "nt" and not str(d).startswith("\\\\"):
        d = Path("\\\\?\\" + str(Path(d).resolve()))
    def again(fn, path, _exc):
        try:
            os.chmod(path, stat.S_IWRITE)
            fn(path)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(d, onexc=again)
    else:
        shutil.rmtree(d, onerror=again)
