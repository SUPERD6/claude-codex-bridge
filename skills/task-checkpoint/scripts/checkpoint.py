#!/usr/bin/env python3
"""task-checkpoint: make long agent tasks resumable after a quota cut, crash or close.

Standalone: Python 3.11+ standard library only; git optional.
State lives on disk under <root>/.ccx/tasks/<task_id>/, so any agent (Claude Code,
Codex, Gemini CLI, ...) can pick a task up where it stopped:

  plan.json        steps with status: todo | doing | done | failed
  progress.jsonl   append-only event log (who, when, what)
  checkpoint.md    human/agent-readable resume brief (regenerated on every write)
  lock.json        pid + host + heartbeat of whoever is running it

Code state: at `done` (and `snap`) the working tree is snapshotted with
`git stash create` + `git update-ref refs/checkpoints/<task>/<step>` — a commit object
that does NOT touch your branch, index or files. Resume compares against it.

Commands:
  init   --title T --step "first" --step "second" ...      -> prints task id
  start  TASK STEP [--agent claude --session ID]             mark doing + heartbeat
  beat   TASK                                                heartbeat only
  note   TASK "text" [--step N]
  done   TASK STEP [--note "..."]                            mark done + code snapshot
  fail   TASK STEP --reason quota|crash|closed|error|blocked [--note "..."] [--retry-after ISO]
  snap   TASK [--step N]                                     code snapshot without status change
  status [TASK] [--quiet]                                    unfinished tasks (quiet: nothing if none)
  brief  TASK                                                the resume brief (what to read after a restart)
  finish TASK                                                mark the whole task complete
Root = $CHECKPOINT_ROOT, else the git top-level of the cwd, else the cwd.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STALE_SECONDS = int(os.environ.get("CHECKPOINT_STALE_SECONDS", "600"))


# ------------------------------------------------------------------ paths
def _git(*args, cwd: Path) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=60)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def root() -> Path:
    if os.environ.get("CHECKPOINT_ROOT"):
        return Path(os.environ["CHECKPOINT_ROOT"]).expanduser().resolve()
    # all git worktrees of one repo share the MAIN worktree's task folder
    rc, common = _git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=Path.cwd())
    if rc == 0 and common and Path(common).name == ".git":
        return Path(common).parent
    rc, top = _git("rev-parse", "--show-toplevel", cwd=Path.cwd())
    return Path(top) if rc == 0 and top else Path.cwd().resolve()


def tasks_dir(r: Path | None = None) -> Path:
    return (r or root()) / ".ccx" / "tasks"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(text: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", text.strip().lower(), flags=re.U).strip("-")
    return (s[:40] or "task")


# ------------------------------------------------------------------ io
class Task:
    def __init__(self, tid: str, r: Path | None = None):
        self.r = r or root()
        self.id = tid
        self.dir = tasks_dir(self.r) / tid
        if not (self.dir / "plan.json").exists():
            raise SystemExit(f"no task {tid!r} under {tasks_dir(self.r)}")
        self.plan = json.loads((self.dir / "plan.json").read_text(encoding="utf-8"))

    # writes are atomic (temp + replace) so a crash mid-write never corrupts state
    def _write(self, name: str, text: str) -> None:
        tmp = self.dir / (name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.dir / name)

    def save(self) -> None:
        self._write("plan.json", json.dumps(self.plan, ensure_ascii=False, indent=2))
        self._write("checkpoint.md", render_brief(self))

    def log(self, event: str, **kw) -> None:
        rec = {"ts": now(), "event": event, **kw}
        f_path = self.dir / "progress.jsonl"
        if f_path.exists() and f_path.stat().st_size:
            with open(f_path, "rb") as fb:      # a crash may have left a torn last line:
                fb.seek(-1, os.SEEK_END)        # start ours on a fresh line so it isn't lost
                torn = fb.read(1) != b"\n"
        else:
            torn = False
        with open(f_path, "a", encoding="utf-8") as f:
            if torn:
                f.write("\n")
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def events(self) -> list[dict]:
        f = self.dir / "progress.jsonl"
        out = []
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue   # a torn last line after a crash is skipped, not fatal
        return out

    def step(self, n: int) -> dict:
        for s in self.plan["steps"]:
            if s["n"] == n:
                return s
        raise SystemExit(f"task {self.id} has no step {n}")

    def beat(self, agent: str | None = None) -> None:
        lock = {"pid": os.getpid(), "ppid": os.getppid(), "host": socket.gethostname(),
                "agent": agent or self.plan.get("agent"), "heartbeat": time.time()}
        self._write("lock.json", json.dumps(lock))

    def lock(self) -> dict | None:
        f = self.dir / "lock.json"
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        except json.JSONDecodeError:
            return None

    def snapshot(self, label: str) -> str | None:
        """Snapshot the working tree as a commit object; never touches branch/index/files."""
        rc, _ = _git("rev-parse", "--is-inside-work-tree", cwd=self.r)
        if rc != 0:
            return None
        rc, sha = _git("stash", "create", f"checkpoint {self.id} {label}", cwd=self.r)
        if rc != 0 or not sha:
            rc, sha = _git("rev-parse", "HEAD", cwd=self.r)   # clean tree: HEAD is the state
            if rc != 0:
                return None
        _git("update-ref", f"refs/checkpoints/{self.id}/{label}", sha, cwd=self.r)
        return sha


# ------------------------------------------------------------------ derived state
def state_of(t: Task) -> str:
    if t.plan.get("finished"):
        return "finished"
    doing = [s for s in t.plan["steps"] if s["status"] == "doing"]
    if any(s["status"] == "failed" for s in t.plan["steps"]):
        return "interrupted"
    if doing:
        lk = t.lock()
        if not lk or time.time() - lk.get("heartbeat", 0) > STALE_SECONDS:
            return "interrupted"
        return "running"
    if all(s["status"] == "done" for s in t.plan["steps"]):
        return "ready-to-finish"
    return "paused"


def render_brief(t: Task) -> str:
    st = state_of(t) if (t.dir / "plan.json").exists() else "?"
    steps = t.plan["steps"]
    done = sum(s["status"] == "done" for s in steps)
    lines = [f"# Resume brief: {t.plan['title']}  ({t.id})", "",
             f"State: **{st}** · {done}/{len(steps)} steps done · updated {now()}", "", "## Steps"]
    icon = {"done": "[x]", "doing": "[~]", "failed": "[!]", "todo": "[ ]"}
    for s in steps:
        extra = []
        if s.get("agent"):
            extra.append(s["agent"])
        if s.get("session"):
            extra.append(f"session {s['session']}")
        if s.get("snapshot"):
            extra.append(f"snapshot {s['snapshot'][:10]}")
        if s.get("reason"):
            extra.append(f"stopped: {s['reason']}")
        if s.get("retry_after"):
            extra.append(f"retry after {s['retry_after']}")
        tail = f" — {', '.join(extra)}" if extra else ""
        lines.append(f"- {icon.get(s['status'], '[ ]')} {s['n']}. {s['title']}{tail}")
        if s.get("note"):
            lines.append(f"    note: {s['note']}")
    nxt = next((s for s in steps if s["status"] in ("doing", "failed")), None) or \
        next((s for s in steps if s["status"] == "todo"), None)
    lines += ["", "## How to continue"]
    if nxt is None:
        lines.append("All steps done: verify, then `finish`.")
    else:
        lines.append(f"Next: step {nxt['n']} — {nxt['title']}.")
        if nxt.get("session"):
            lines.append(f"1. Prefer resuming the same session ({nxt.get('agent') or 'agent'} session "
                         f"`{nxt['session']}`): it remembers how far it got.")
            lines.append("2. If that session cannot continue (other agent, quota still out), start fresh "
                         "from this brief plus the code diff below; do not redo steps marked [x].")
        else:
            lines.append("Start this step from this brief; do not redo steps marked [x].")
        last = next((s.get("snapshot") for s in reversed(steps) if s["status"] == "done" and s.get("snapshot")), None)
        if last:
            lines.append(f"Code since the last good step: `git diff {last[:12]}` "
                         f"(uncommitted work at the stop is still in the working tree).")
    notes = [e for e in t.events() if e["event"] == "note"][-5:]
    if notes:
        lines += ["", "## Recent notes"] + [f"- {e['ts']} {e.get('text', '')}" for e in notes]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ commands
def cmd_init(a) -> int:
    r = root()
    tid = time.strftime("%Y%m%d-%H%M-") + slug(a.title)
    d = tasks_dir(r) / tid
    d.mkdir(parents=True, exist_ok=False)
    plan = {"id": tid, "title": a.title, "created": now(), "agent": a.agent,
            "steps": [{"n": i + 1, "title": s, "status": "todo"} for i, s in enumerate(a.step or [])]}
    (d / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    t = Task(tid, r)
    t.log("init", title=a.title, steps=len(plan["steps"]))
    t.save()
    gi = r / ".gitignore"
    try:
        txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
        ignored = subprocess.run(["git", "check-ignore", "-q", ".ccx/tasks/x"], cwd=r, capture_output=True,
                                 stdin=subprocess.DEVNULL).returncode == 0     # e.g. the whole .ccx/ already is
        if ".ccx/tasks/" not in txt and not ignored:
            with open(gi, "a", encoding="utf-8") as f:
                f.write(("" if txt.endswith("\n") or not txt else "\n") + ".ccx/tasks/\n")
    except OSError:
        pass
    print(tid)
    return 0


def cmd_add(a) -> int:
    t = Task(a.task)
    n = max([s["n"] for s in t.plan["steps"]] or [0]) + 1
    t.plan["steps"].append({"n": n, "title": a.title, "status": "todo"})
    t.log("add", step=n, title=a.title)
    t.save()
    print(n)
    return 0


def cmd_start(a) -> int:
    t = Task(a.task)
    s = t.step(a.step)
    s.update(status="doing", started=now(), agent=a.agent or s.get("agent"),
             session=a.session or s.get("session"))
    s.pop("reason", None)
    s.pop("retry_after", None)
    t.beat(a.agent)
    t.log("start", step=a.step, agent=a.agent, session=a.session)
    t.save()
    return 0


def cmd_session(a) -> int:
    t = Task(a.task)
    t.step(a.step)["session"] = a.session
    t.log("session", step=a.step, session=a.session)
    t.save()
    return 0


def cmd_beat(a) -> int:
    Task(a.task).beat()
    return 0


def cmd_note(a) -> int:
    t = Task(a.task)
    text = " ".join(a.text)
    if a.step:
        t.step(a.step)["note"] = text
    t.log("note", step=a.step, text=text)
    t.beat()
    t.save()
    return 0


def cmd_done(a) -> int:
    t = Task(a.task)
    s = t.step(a.step)
    sha = t.snapshot(f"step-{a.step}")
    s.update(status="done", ended=now(), snapshot=sha)
    if a.note:
        s["note"] = a.note
    t.log("done", step=a.step, snapshot=sha, note=a.note)
    t.beat()
    t.save()
    return 0


def cmd_fail(a) -> int:
    t = Task(a.task)
    s = t.step(a.step)
    sha = t.snapshot(f"step-{a.step}-stop")
    s.update(status="failed", reason=a.reason, stopped=now(), stop_snapshot=sha)
    if a.retry_after:
        s["retry_after"] = a.retry_after
    if a.note:
        s["note"] = a.note
    t.log("fail", step=a.step, reason=a.reason, note=a.note, retry_after=a.retry_after, snapshot=sha)
    t.save()
    return 0


def cmd_snap(a) -> int:
    t = Task(a.task)
    sha = t.snapshot(f"snap-{int(time.time())}")
    t.log("snap", step=a.step, snapshot=sha)
    t.save()
    print(sha or "(not a git repo)")
    return 0


def cmd_finish(a) -> int:
    t = Task(a.task)
    t.plan["finished"] = now()
    t.log("finish")
    t.save()
    try:
        (t.dir / "lock.json").unlink()
    except FileNotFoundError:
        pass
    return 0


def cmd_status(a) -> int:
    r = root()
    base = tasks_dir(r)
    ids = [a.task] if a.task else sorted(p.name for p in base.iterdir() if (p / "plan.json").exists()) \
        if base.exists() else []
    rows = []
    for tid in ids:
        t = Task(tid, r)
        st = state_of(t)
        if a.quiet and st in ("finished", "running"):
            continue
        steps = t.plan["steps"]
        done = sum(s["status"] == "done" for s in steps)
        cur = next((s for s in steps if s["status"] in ("doing", "failed")), None)
        why = f", step {cur['n']} {cur.get('reason') or 'stopped'}" if cur and st == "interrupted" else ""
        rows.append(f"[unfinished task] {t.plan['title']} ({tid}): {st}, {done}/{len(steps)} steps done{why}. "
                    f"Resume brief: {t.dir / 'checkpoint.md'}")
    if rows:
        print("\n".join(rows))
    elif not a.quiet:
        print("no tasks")
    return 0


def cmd_brief(a) -> int:
    t = Task(a.task)
    t.save()   # refresh state (e.g. stale heartbeat -> interrupted)
    print((t.dir / "checkpoint.md").read_text(encoding="utf-8"), end="")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="checkpoint")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--title", required=True)
    p.add_argument("--step", action="append"); p.add_argument("--agent"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("add"); p.add_argument("task"); p.add_argument("title"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("start"); p.add_argument("task"); p.add_argument("step", type=int)
    p.add_argument("--agent"); p.add_argument("--session"); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("session"); p.add_argument("task"); p.add_argument("step", type=int)
    p.add_argument("session"); p.set_defaults(fn=cmd_session)
    p = sub.add_parser("beat"); p.add_argument("task"); p.set_defaults(fn=cmd_beat)
    p = sub.add_parser("note"); p.add_argument("task"); p.add_argument("text", nargs="+")
    p.add_argument("--step", type=int); p.set_defaults(fn=cmd_note)
    p = sub.add_parser("done"); p.add_argument("task"); p.add_argument("step", type=int)
    p.add_argument("--note"); p.set_defaults(fn=cmd_done)
    p = sub.add_parser("fail"); p.add_argument("task"); p.add_argument("step", type=int)
    p.add_argument("--reason", required=True, choices=["quota", "crash", "closed", "error", "blocked"])
    p.add_argument("--note"); p.add_argument("--retry-after"); p.set_defaults(fn=cmd_fail)
    p = sub.add_parser("snap"); p.add_argument("task"); p.add_argument("--step", type=int); p.set_defaults(fn=cmd_snap)
    p = sub.add_parser("status"); p.add_argument("task", nargs="?"); p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("brief"); p.add_argument("task"); p.set_defaults(fn=cmd_brief)
    p = sub.add_parser("finish"); p.add_argument("task"); p.set_defaults(fn=cmd_finish)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
