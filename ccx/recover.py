"""What a killed or abandoned run spent, and closing runs whose ccx process is gone.

A sub-agent stopped mid-run (timeout, spending cap, `ccx stop`, Ctrl+C) prints no final usage line: Codex's comes
with turn.completed, Claude's with the result event. Its tokens were spent all the same, so they are read back from
what is there: Claude's assistant events in the stream (or its transcript), Codex's session file (rollout). A run
whose ccx process died leaves a record that says `running` forever; `sweep` closes it as interrupted, with that
usage, so `ccx stats` counts it and `ccx resume` continues it.
"""
from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path

from . import ledger
from .config import Paths, claude_home, codex_home
from .runners import pid_alive, usage_dict

STALE_SEC = 600            # no heartbeat for this long, and liveness can't be checked: the run is gone
SWEEP_DAYS = 14            # only runs this young are looked at


def _claude_usage(lines) -> dict:
    """Sum of assistant messages' usage, each message once (one message spans several events/lines)."""
    seen, tot = set(), usage_dict()
    for line in lines:
        if '"usage"' not in line or '"assistant"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message") or {}
        u = m.get("usage")
        if e.get("type") != "assistant" or not u or (m.get("id") and m.get("id") in seen):
            continue
        seen.add(m.get("id"))
        cc = u.get("cache_creation") or {}
        for k, v in usage_dict(fresh=u.get("input_tokens", 0) or 0, write=u.get("cache_creation_input_tokens", 0) or 0,
                               write_1h=cc.get("ephemeral_1h_input_tokens", 0) or 0,
                               cached=u.get("cache_read_input_tokens", 0) or 0,
                               out=u.get("output_tokens", 0) or 0).items():
            tot[k] += v
    return tot


def _codex_session_total(sid: str, home: Path | None = None) -> dict | None:
    """The session's running total from its rollout file(s): {input, cached, output} (cached inside input)."""
    root = (home or codex_home()) / "sessions"
    best = None
    for f in root.rglob(f"rollout-*{sid}.jsonl") if root.exists() and sid else []:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"token_count"' not in line:
                continue
            try:
                tot = (((json.loads(line).get("payload") or {}).get("info") or {}).get("total_token_usage"))
            except ValueError:
                continue
            if tot:
                cur = {"input": int(tot.get("input_tokens", 0) or 0), "cached": int(tot.get("cached_input_tokens", 0) or 0),
                       "output": int(tot.get("output_tokens", 0) or 0)}
                if not best or cur["input"] > best["input"]:
                    best = cur
                break
    return best


def partial_usage(cli: str, sid: str | None, stdout: str = "", cwd: Path | None = None) -> dict:
    """Usage of an attempt that ended without its final usage line, in the shape its parser would have given:
    Claude per attempt; Codex the session's running total (delegate counts only its growth, as for a resume)."""
    if cli == "claude":
        u = _claude_usage(stdout.splitlines())
        if not any(u.values()) and sid and cwd:
            slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path(cwd).resolve()))
            f = claude_home() / "projects" / slug / f"{sid}.jsonl"
            try:
                u = _claude_usage(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
        return u if any(u.values()) else {}
    if cli == "codex" and sid:
        t = _codex_session_total(sid)
        if t:
            return usage_dict(fresh=max(0, t["input"] - t["cached"]), cached=t["cached"], out=t["output"])
    return {}


def close_dead(p: Paths, run_id: str, kind: str, state: str, why: str, by: str,
               attempt_kind: str | None = None) -> dict | None:
    """Close a run whose own ccx process is gone: the attempt it was in the middle of becomes one attempt with the
    usage read back (kind=`kind`), then the final state and its one ledger row. None if someone else closed it."""
    from . import learn
    from .agents.codex import _codex_growth, _codex_seen, _codex_total
    run_dir = p.runs / run_id
    if not ledger.claim_final(run_dir, by):
        return None
    rec = ledger.load_run(p, run_id)
    cur = rec.get("current") or {}
    if cur and len(rec.get("attempts") or []) <= int(cur.get("n", 0)):
        cli, sid = cur.get("cli") or cur.get("agent"), rec.get("session_id")
        u = partial_usage(cli, sid, cwd=Path(rec["cwd"]) if rec.get("cwd") else None)
        extra = {}
        if cli == "codex" and u:
            total = _codex_total(u)
            u = _codex_growth(total, cur.get("before") or _codex_seen(rec).get(sid, {}))
            extra["codex_total"] = total
        ae = learn.price_usd(p, cur["agent"], cur["model"], u, ts=cur.get("t0")) if u else None
        rec.setdefault("attempts", []).append({
            "agent": cur["agent"], "tier": cur.get("tier"), "rung": cur.get("rung"), "model": cur.get("model"),
            "effort": cur.get("effort"), "ok": False, "kind": attempt_kind or kind,
            "seconds": round(max(0.0, time.time() - float(cur.get("t0") or time.time())), 1), "usage": u,
            "cost_usd": None, "ae_usd": round(ae, 6) if ae is not None else None, "error": why,
            "auth_problem": False, "retry_after": None, "session_id": sid, "recovered": True, **extra})
    rec.update(state=state, kind=kind, ok=False, error=why)
    ledger.write_record(run_dir, rec)
    ledger.append(p, rec)
    return rec


def _gone(rec: dict, run_dir: Path, now: float) -> bool:
    if rec.get("ccx_pid") and rec.get("host") == socket.gethostname():
        return not pid_alive(rec["ccx_pid"])
    beats = [f.stat().st_mtime for f in (run_dir / "beat", run_dir / "run.json") if f.exists()]
    return bool(beats) and now - max(beats) > STALE_SEC


def sweep(p: Paths, now: float | None = None) -> list[str]:
    """Close every `running` record whose ccx process is gone (dead pid on this machine, or no heartbeat for
    STALE_SEC) as interrupted. Cheap: only run folders with no ledger row are opened. Returns their ids."""
    now = now or time.time()
    if not p.runs.exists():
        return []
    done = {r.get("run_id") for r in ledger.rows(p) if not r.get("type")}
    cutoff = time.strftime("%Y%m%d", time.localtime(now - SWEEP_DAYS * 86400))
    out = []
    for d in p.runs.iterdir():
        if d.name in done or d.name[:8] < cutoff or not (d / "run.json").exists():
            continue
        try:
            rec = json.loads((d / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if rec.get("state") != "running" or not _gone(rec, d, now):
            continue
        try:
            if close_dead(p, d.name, "interrupted", "interrupted",
                          "its ccx process ended before the run finished (closed window, crash or kill); "
                          f"continue with `ccx resume {d.name}`", "sweep", attempt_kind="killed"):
                out.append(d.name)
        except (OSError, ValueError, KeyError):
            continue
    return out
