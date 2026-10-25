"""Subscription quota by pace: how much of each window will be used by the time it resets.

Readings:
  Codex  — every token_count line of its own session logs carries rate_limits.{primary,secondary}: used_percent,
           window_minutes, resets_at (codex-cli 0.164). Whatever windows the plan has (weekly; Plus also 5 hours)
           are read as they come; the plan's name is never needed.
  Claude — its logs carry no quota. A Claude sub-agent's stream-json has rate_limit_event.rate_limit_info
           .unifiedWindows.{five_hour, seven_day}: utilization 0..1, resetsAt (Claude Code 2.1.309). ccx keeps each
           one in <hub>/ccx/quota.jsonl when it runs Claude; `probe` asks a tiny question just to get one.

Pace: within the current window (readings since its reset only — a drop in use or a later reset time means a new
window, e.g. after a plan change), the rate over the last 48 hours is projected to the reset. With less than six
hours of readings it is too early to project and the current share is used as it is."""
from __future__ import annotations

import json
import time
from pathlib import Path

WINDOW_MIN = {"five_hour": 300, "seven_day": 10080}
RATE_HOURS = 48
MIN_SPAN_HOURS = 6
PROBE_AFTER_S = 3600


def _file(p) -> Path:
    return p.state / "quota.jsonl"


def save_claude(p, events: list[dict]) -> int:
    """Keep the Claude windows from a run's stream events (rate_limit_event). Returns how many were kept."""
    out = []
    for ev in events:
        info = (ev.get("rate_limit_info") or {}) if ev.get("type") == "rate_limit_event" else {}
        for win, w in (info.get("unifiedWindows") or {}).items():
            if isinstance(w, dict) and w.get("utilization") is not None:
                out.append({"ts": time.time(), "agent": "claude", "window": win, "used": float(w["utilization"]),
                            "resets_at": w.get("resetsAt"), "window_minutes": WINDOW_MIN.get(win)})
    if out:
        f = _file(p)
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            for r in out:
                fh.write(json.dumps(r) + "\n")
    return len(out)


def claude_readings(p, days: float = 8) -> list[dict]:
    since = time.time() - days * 86400
    try:
        lines = _file(p).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if (r.get("ts") or 0) >= since:
            out.append(r)
    return out


def codex_readings(days: float = 8) -> list[dict]:
    from .usage import codex_events
    try:
        _, samples = codex_events(time.time() - days * 86400, set())
    except Exception:  # noqa: BLE001
        return []
    return [{"ts": s["ts"], "agent": "codex", "window": s["window"], "used": s["used_percent"] / 100,
             "resets_at": s.get("resets_at"), "window_minutes": s.get("window_minutes")} for s in samples]


def pace(readings: list[dict], now: float | None = None) -> dict:
    """window -> {used, projected, resets_at, hours_left, per_day, note}."""
    now = now or time.time()
    out = {}
    for win in sorted({r["window"] for r in readings}):
        rs = sorted((r for r in readings if r["window"] == win), key=lambda r: r["ts"])
        last = rs[-1]
        reset = last.get("resets_at")
        if reset and reset <= now:
            # the window has reset since the last reading: what it says no longer applies
            out[win] = {"used": None, "projected": 0.0, "resets_at": reset, "hours_left": 0.0,
                        "note": "window has reset since the last reading"}
            continue
        # the current window: same reset time as the latest reading, and no drop in use since
        cur = [r for r in rs if r.get("resets_at") is None or reset is None or abs(r["resets_at"] - reset) < 120]
        for i in range(len(cur) - 1, 0, -1):
            if cur[i]["used"] + 0.02 < cur[i - 1]["used"]:
                cur = cur[i:]
                break
        hours_left = max(0.0, (reset - now) / 3600) if reset else None
        recent = [r for r in cur if r["ts"] >= last["ts"] - RATE_HOURS * 3600]
        span = (last["ts"] - recent[0]["ts"]) / 3600 if recent else 0
        row = {"used": round(last["used"], 3), "resets_at": reset,
               "hours_left": round(hours_left, 1) if hours_left is not None else None,
               "reading_age_min": round((now - last["ts"]) / 60)}
        if span >= MIN_SPAN_HOURS and hours_left is not None:
            per_h = max(0.0, (last["used"] - recent[0]["used"]) / span)
            row.update(per_day=round(per_h * 24, 3), projected=round(last["used"] + per_h * hours_left, 3))
        else:
            row.update(projected=round(last["used"], 3), note="too early to project (less than 6 h of readings)")
        out[win] = row
    return out


def pressure(p, given: dict | None = None) -> dict:
    """agent -> projected share of its tightest window by its reset (what the total cost prices quota with).
    Explicit values (--quota claude=0.8) win; else Codex from its logs and Claude from kept readings."""
    q = dict(given or {})
    detail = {}
    for agent, readings in (("codex", codex_readings()), ("claude", claude_readings(p))):
        if agent in q or not readings:
            continue
        pc = pace(readings)
        if pc:
            detail[agent] = pc
            q[agent] = max(w["projected"] for w in pc.values())
            if all(w.get("used") is None for w in pc.values()):
                del q[agent]                     # every window reset since: no current reading
    return {"quota": q, "pace": detail}


def backfill(p) -> int:
    """Read the Claude windows out of past run logs (once, to start with some history)."""
    n = 0
    for f in sorted(p.runs.glob("*/events.*.log")) if p.runs.exists() else []:
        try:
            lines = [x for x in f.read_text(encoding="utf-8", errors="replace").splitlines()
                     if '"rate_limit_event"' in x]
        except OSError:
            continue
        evs = []
        for x in lines:
            try:
                evs.append(json.loads(x))
            except ValueError:
                pass
        if evs:
            ts = f.stat().st_mtime
            for ev in evs:
                for win, w in ((ev.get("rate_limit_info") or {}).get("unifiedWindows") or {}).items():
                    if isinstance(w, dict) and w.get("utilization") is not None:
                        with open(_file(p), "a", encoding="utf-8") as fh:
                            fh.write(json.dumps({"ts": ts, "agent": "claude", "window": win,
                                                 "used": float(w["utilization"]), "resets_at": w.get("resetsAt"),
                                                 "window_minutes": WINDOW_MIN.get(win)}) + "\n")
                        n += 1
    return n


def _stops_file(p) -> Path:
    return p.state / "quota-stops.jsonl"


def stop_evidence(cli: str, stdout: str, stderr: str, error: str | None) -> dict:
    """Why an attempt was taken for a quota stop (H2): Claude's rejected rate_limit_event as it came, else the hint
    in runners.QUOTA_HINTS that matched and the words around it. Kept so a wrong call ("quota" in a task's own
    text, a new wording of a real limit) can be found and the hints corrected, without spending quota to test."""
    from .runners import QUOTA_HINTS
    if cli == "claude":
        for line in stdout.splitlines():
            if '"rate_limit_event"' not in line:
                continue
            try:
                info = json.loads(line).get("rate_limit_info") or {}
            except ValueError:
                continue
            if str(info.get("status", "")).lower() in ("rejected", "exceeded", "blocked"):
                return {"by": "rate_limit_event", "event": {k: info.get(k) for k in (
                    "status", "rateLimitType", "resetsAt", "overageStatus", "isUsingOverage") if k in info}}
    text = " ".join(x for x in (error, stderr[-4000:], stdout[-4000:]) if x)
    low = text.lower()
    for h in QUOTA_HINTS:
        i = low.find(h)
        if i != -1:
            return {"by": "hint", "hint": h, "text": " ".join(text[max(0, i - 160): i + 160].split())}
    return {"by": "unknown"}


def log_stop(p, run_id: str, attempt: dict, evidence: dict) -> None:
    """One line per quota stop in <hub>/ccx/quota-stops.jsonl (shown by `ccx quota`)."""
    row = {"ts": time.time(), "run_id": run_id, "agent": attempt.get("agent"), "model": attempt.get("model"),
           "effort": attempt.get("effort"), "retry_after": attempt.get("retry_after"),
           "seconds": attempt.get("seconds"), **evidence}
    f = _stops_file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def recent_stops(p, n: int = 5) -> list[dict]:
    try:
        lines = _stops_file(p).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def claude_reading_age(p) -> float | None:
    rs = claude_readings(p, days=8)
    return (time.time() - max(r["ts"] for r in rs)) if rs else None


def probe(p) -> int:
    """One tiny, history-free Claude request just to read its quota windows (a few thousand tokens)."""
    from .delegate import Request, run
    rec = run(Request(to="claude", brief="Reply with the single word OK.", mode="read", caller="user",
                      escalate=False, fallback=False, label="quota-probe", model="haiku", effort="low",
                      ephemeral=True, cwd=Path.cwd()), p)
    return len(claude_readings(p, days=0.01)) if rec else 0
