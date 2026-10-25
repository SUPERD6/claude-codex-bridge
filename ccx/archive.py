"""Archive sub-agent sessions so they don't clutter Claude's / Codex's session history.

  Codex   official command: `codex archive <thread>` (and `codex unarchive`), reversible.
  Claude  no archive command: the session transcript (<claude home>/projects/<folder>/<id>.jsonl) is moved to
          <claude home>/ccx-archive/<folder>/ — nothing is deleted, `ccx archive --restore <run>` moves it back.
  Gemini  no archive command yet: left alone (reported).

One-shot runs (`ccx ask`, `ccx selftest`) are never saved in the first place (--ephemeral /
--no-session-persistence). Runs are archived only after the auto-continue window, so a session that may still
take the next task is never archived. `sessions.auto_archive_hours` (default 2, 0 = off) does this quietly at
session start; `ccx archive` does it on demand.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from . import ledger
from .config import Paths, claude_home, load_config
from .runners import bin_argv, find_bin


def _log(p: Paths) -> Path:
    return p.state / "archived.jsonl"


def archived_ids(p: Paths) -> set[str]:
    f = _log(p)
    if not f.exists():
        return set()
    out = set()
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        (out.discard if e.get("restored") else out.add)(e["run_id"])
    return out


def finished_runs(p: Paths, older_than_h: float = 0) -> list[str]:
    done = archived_ids(p)
    cutoff = time.time() - older_than_h * 3600
    return [r["run_id"] for r in ledger.rows(p)
            if not r.get("type") and r["run_id"] not in done
            and (not r.get("ephemeral") or str(r.get("label") or "").startswith("discuss:"))  # those keep a session
            and not str(r.get("label") or "").startswith("seat:")     # named seats keep their session
            and (r.get("ts") or 0) <= cutoff and (r.get("sessions") or r.get("session_id"))]


def _sessions(p: Paths, run_id: str) -> list[tuple[str, str]]:
    rec = ledger.load_run(p, run_id)
    seen, out = set(), []
    for a in rec.get("attempts", []):
        sid = a.get("session_id")
        if sid and sid not in seen:
            seen.add(sid)
            out.append((a.get("agent") or rec["to"], sid))
    return out


def _claude_transcript(sid: str) -> Path | None:
    hits = list((claude_home() / "projects").glob(f"*/{sid}.jsonl"))
    return hits[0] if hits else None


def _run(argv: list[str]) -> tuple[int, str]:
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL)
    return r.returncode, (r.stdout or r.stderr).strip()[-300:]


def archive(p: Paths, run_ids: list[str], apply: bool = False) -> dict:
    rows, handled = [], {}            # (agent, session) -> first run that archived it in this call
    for run_id in run_ids:
        try:
            sessions = _sessions(p, run_id)
        except FileNotFoundError:
            continue
        done = []
        for agent, sid in sessions:
            if (agent, sid) in handled:       # auto-continued runs share a session: archive it once
                first, original = handled[(agent, sid)]
                if apply and original is not False:
                    done.append([agent, sid, original])
                rows.append({"run_id": run_id, "agent": agent, "session": sid,
                             "action": f"same session as {first}: handled there"})
                continue
            handled[(agent, sid)] = (run_id, False)
            if agent == "codex":
                action = f"codex archive {sid}"
                if apply:
                    if not find_bin("codex"):
                        action += " (skipped: codex CLI not found)"
                        rows.append({"run_id": run_id, "agent": agent, "session": sid, "action": action})
                        continue
                    rc, msg = _run([*bin_argv("codex"), "archive", sid])
                    action += " -> ok" if rc == 0 else f" -> failed: {msg}"
                    if rc == 0:
                        done.append([agent, sid, None])
                        handled[(agent, sid)] = (run_id, None)
            elif agent == "claude":
                src = _claude_transcript(sid)
                if not src:
                    rows.append({"run_id": run_id, "agent": agent, "session": sid, "action": "no transcript (not saved)"})
                    continue
                dst = claude_home() / "ccx-archive" / src.parent.name / src.name
                action = f"move {src} -> {dst}"
                if apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    done.append([agent, sid, str(src)])
                    handled[(agent, sid)] = (run_id, str(src))
            else:
                action = f"{agent}: no archive command, left alone"
            rows.append({"run_id": run_id, "agent": agent, "session": sid, "action": action})
        if apply:
            _log(p).parent.mkdir(parents=True, exist_ok=True)
            with open(_log(p), "a", encoding="utf-8") as f:
                f.write(json.dumps({"run_id": run_id, "sessions": done, "ts": time.time()}) + "\n")
    return {"applied": apply, "runs": len(run_ids), "sessions": rows,
            "note": "" if apply else "dry run: add --apply"}


def restore(p: Paths, run_id: str) -> dict:
    entries = [json.loads(line) for line in _log(p).read_text(encoding="utf-8").splitlines()] if _log(p).exists() else []
    last = next((e for e in reversed(entries) if e["run_id"] == run_id and not e.get("restored")), None)
    if not last:
        raise FileNotFoundError(f"run {run_id} is not archived")
    out = []
    for agent, sid, original in last["sessions"]:
        if agent == "codex":
            rc, msg = _run([*bin_argv("codex"), "unarchive", sid])
            out.append({"session": sid, "action": "codex unarchive -> " + ("ok" if rc == 0 else msg)})
        elif agent == "claude" and original:
            src = claude_home() / "ccx-archive" / Path(original).parent.name / Path(original).name
            if src.exists():
                Path(original).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), original)
            out.append({"session": sid, "action": f"moved back to {original}"})
    with open(_log(p), "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": run_id, "restored": True, "ts": time.time()}) + "\n")
    return {"run_id": run_id, "restored": out}


def auto(p: Paths) -> int:
    """Quiet housekeeping at session start: archive finished runs older than sessions.auto_archive_hours."""
    hours = float((load_config(p).get("sessions") or {}).get("auto_archive_hours", 2) or 0)
    if hours <= 0:
        return 0
    ids = finished_runs(p, older_than_h=hours)
    if ids:
        archive(p, ids, apply=True)
    return len(ids)
