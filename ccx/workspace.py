"""The workspace around a write run: a worktree, the acceptance check ccx runs again, the snapshot taken
before the run and `ccx undo` (from delegate.py)."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from . import ledger
from .config import Paths
from .verdicts import _hard_verdict, verify

def make_worktree(cwd: Path, run_id: str) -> Path:
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if top.returncode != 0:
        raise RuntimeError("--worktree needs a git repository")
    root = Path(top.stdout.strip())
    wt = root.parent / f".ccx-worktrees" / root.name / run_id
    wt.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "worktree", "add", "-b", f"ccx/{run_id}", str(wt)], cwd=root,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git worktree add failed: " + r.stderr.strip())
    return wt


def run_check(cmd: str, cwd: Path, timeout: int = 900) -> dict:
    """The lead's acceptance command, run by ccx after the sub-agent says it is done (not trusting its report)."""
    t0 = time.time()
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        code, tail = r.returncode, (r.stdout + r.stderr)[-800:]
    except subprocess.TimeoutExpired:
        code, tail = -1, f"timed out after {timeout}s"
    out = {"cmd": cmd, "exit": code, "passed": code == 0, "seconds": round(time.time() - t0, 1), "tail": tail}
    if out["passed"]:
        out.update(_check_doubt(cmd, cwd))
    return out


def _check_doubt(cmd: str, cwd: Path) -> dict:
    """J7: when this command (here) passed work later judged wrong too often, say so with the result."""
    try:
        from .config import hub_dir
        p = Paths(hub_dir())
        g = ledger.check_trust(ledger.rows(p), p).get(ledger.check_key(cmd, str(cwd))[0])
    except Exception:  # noqa: BLE001 — a note, never a reason for the run to fail
        return {}
    if not g or not g["weak"]:
        return {}
    return {"weak": f"{g['wrong']}/{g['judged']} passed but judged wrong", "note": ledger.WEAK_CHECK_NOTE}


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout.strip()


def undo_snapshot(cwd: Path) -> dict | None:
    """Before a write run: remember the exact working tree (incl. uncommitted edits) without touching it."""
    rc, top = _git(cwd, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None
    _, stash = _git(cwd, "stash", "create")          # a commit object of the dirty tree; "" if clean
    _, head = _git(cwd, "rev-parse", "HEAD")
    base = stash or head
    if not base:
        return None
    _, untracked = _git(Path(top), "ls-files", "--others", "--exclude-standard")
    return {"repo": top, "base": base, "untracked": untracked.splitlines()}


def undo(p: Paths, run_id: str, apply: bool = False, wrong: bool = False) -> dict:
    """Put back the files a write run changed. Dry run unless apply. New files are moved aside, not deleted.
    Undoing is not a verdict by itself (people undo to try again, or to split the work); `wrong` says it was."""
    f = p.runs / run_id / "undo.json"
    if not f.exists():
        raise FileNotFoundError(f"run {run_id} has no undo snapshot (read-only run, worktree run, or not a git repo)")
    snap = json.loads(f.read_text(encoding="utf-8"))
    repo, base = Path(snap["repo"]), snap["base"]
    _, changed = _git(repo, "diff", "--name-only", base)
    _, untracked = _git(repo, "ls-files", "--others", "--exclude-standard")
    new_files = sorted(set(untracked.splitlines()) - set(snap["untracked"]))
    restore = [x for x in changed.splitlines() if x]
    out = {"run_id": run_id, "restore": restore, "move_aside": new_files, "applied": False,
           "warning": "also reverts any edits you made to these files after the run"}
    if apply:
        if restore:
            rc, msg = _git(repo, "checkout", base, "--", *restore)
            if rc != 0:
                raise RuntimeError("git checkout failed: " + msg)
        trash = repo / ".ccx" / "undo" / run_id
        for rel in new_files:
            src = repo / rel
            dst = trash / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
        out.update(applied=True, moved_to=str(trash) if new_files else None)
        (p.runs / run_id / "undone.json").write_text(json.dumps({"ts": time.time(), "wrong": wrong}),
                                                     encoding="utf-8")
        ledger.append_event(p, {"type": "undo", "run_id": run_id, "reason": "undone", "wrong": wrong,
                                "ts": time.time()})
        if wrong and not _hard_verdict(ledger.load_run(p, run_id)):
            verify(p, run_id, False, note="undone with ccx undo --wrong", reason="wrong")
            out["verdict"] = "recorded as wrong (undo --wrong)"
        elif not wrong:
            out["verdict"] = "none: waits for yours (`ccx verify` or `ccx undo --wrong`)"
    return out
