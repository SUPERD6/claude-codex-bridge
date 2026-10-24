"""Verdicts on finished runs: the lead's (`ccx verify`), on built-in sub-agents, and the probable ones ccx
draws from the evidence (H13) (from delegate.py)."""
from __future__ import annotations

import time
from pathlib import Path

from . import learn, ledger
from .config import Paths
from .ledger import write_record as _write_record

# ---- verdicts without asking (H13) -------------------------------------------------------------------------------
SOFT_AFTER_H = 12.0          # a finished run nobody judged for this long, with good evidence, counts as probably right


REASONS = ("unfinished", "wrong", "overreach", "other")


def _hard_verdict(record: dict) -> bool:
    v = record.get("verdict") or {}
    return bool(v) and not v.get("soft")


def _soft_verdict(p: Paths, record: dict, ok: bool, reason: str, note: str) -> None:
    """A verdict ccx draws from the evidence. Kept apart from the lead's (`soft`), and a later `ccx verify`
    overrides it. It feeds routing only where nothing was learned yet, or to correct the provisional record."""
    record["verdict"] = {"ok": ok, "soft": True, "reason": reason, "note": note, "ts": time.time()}
    how = record.get("learned")
    auto_ok = bool(record.get("ok") and (record.get("result") or {}).get("status") == "done")
    if (record.get("route") or {}).get("b") is not None and (how is None or (how == "auto" and auto_ok != ok)):
        try:
            learn.record_outcomes(p, record, final_ok=ok)
            record["learned"] = "soft"
        except Exception:  # noqa: BLE001 — learning is best effort
            pass
    _write_record(p.runs / record["run_id"], record)
    ledger.append_event(p, {"type": "verify", "run_id": record["run_id"], "ok": ok, "soft": True,
                            "reason": reason, "ts": time.time()})


def soft_verdicts(p: Paths, min_age_h: float = SOFT_AFTER_H, now: float | None = None) -> list[dict]:
    """Finished runs nobody judged within `min_age_h`: 'probably right' when ccx's own check passed or the
    sub-agent's self-check ran, the independent review (if any) passed, and it was neither undone nor sent back.
    Runs without such evidence stay unjudged: they wait for the person (the UI's 'please review' list)."""
    now = now or time.time()
    rows = ledger.rows(p)
    judged = {r.get("run_id") for r in rows if r.get("type") == "verify"}
    out = []
    for r in rows:
        if r.get("type") or r.get("run_id") in judged or not r.get("ok") or r.get("status") != "done":
            continue
        if now - float(r.get("ts") or now) < min_age_h * 3600 or r.get("ephemeral"):
            continue
        if (r.get("label") or "").startswith(("review:", "quota-probe", "selftest", "handoff-from-transcript")):
            continue
        try:
            record = ledger.load_run(p, r["run_id"])
        except (FileNotFoundError, KeyError, ValueError):
            continue
        if _hard_verdict(record) or (record.get("verdict") or {}).get("soft"):
            continue
        if (p.runs / r["run_id"] / "undone.json").exists():
            _soft_verdict(p, record, False, "undone", "undone with ccx undo")
            out.append({"run_id": r["run_id"], "ok": False, "why": "undone"})
            continue
        if record.get("kind") in ("check_failed", "review_issues", "review_failed", "needs_write", "split"):
            continue
        check = record.get("check")
        rev = (record.get("review") or {}).get("verdict")
        checked = (check and check.get("passed")) or \
            (record.get("result") or {}).get("verification", "not-run") not in ("", "not-run")
        if not checked or (check and not check.get("passed")) or rev in ("issues", "unclear"):
            continue
        why = "ccx check passed" if check else "self-checked"
        if rev == "pass":
            why += ", review passed"
        _soft_verdict(p, record, True, "", f"auto after {min_age_h:g} h: {why}, not undone or reworked")
        out.append({"run_id": r["run_id"], "ok": True, "why": why})
    return out


def verify_builtin(p: Paths, rung: str, b: float, ok: bool, agent_id: str | None = None, note: str = "") -> dict:
    """Verdict on work the lead gave its OWN built-in sub-agent (ccx did not run it, so there is no run record).
    With the sub-agent's id its real cost is read from its transcript; routing learns from both."""
    from .usage import claude_events, codex_events
    cost = None
    if agent_id:
        since = time.time() - 7 * 86400
        ids = {agent_id, f"agent-{agent_id}"}
        events = claude_events(since, set()) if rung.startswith("claude") else codex_events(since, set())[0]
        mine = [e for e in events if e.get("role") == "builtin" and e.get("session") in ids]
        if mine:
            agent = rung.split("-")[0]
            cost = round(sum(learn.price_usd(p, agent, e["model"], e["usage"]) or 0 for e in mine), 6)
    tr = learn.module(p, "routing")
    with tr._Lock(tr.state_path()):
        pri, st = tr.load_priors(), tr.load_state()
        if hasattr(tr, "builtin_rungs"):                 # built-in rungs are not in the priors file itself
            pri = {**pri, "rungs": pri["rungs"] + tr.builtin_rungs(pri, rung.replace("-builtin", "", 1))}
        learned = tr.record(rung, float(b), ok, pri, st, cost_usd=cost)
        tr.save_state(st)
    ledger.append_event(p, {"type": "builtin_verdict", "rung": rung, "b": b, "ok": ok, "cost_usd": cost,
                            "agent_id": agent_id, "note": note, "ts": time.time()})
    return {"builtin": rung, "verdict": ok, "cost_usd": cost, "learned": learned,
            **({} if cost is not None or not agent_id else {"note": "no transcript found for that id: cost not learned"})}


def verify(p: Paths, run_id: str, ok: bool, note: str = "", reason: str = "") -> dict:
    """The lead's verdict after checking the work. This is the authoritative learning signal; it overrides a
    verdict ccx drew by itself (soft). `reason` (when not ok): unfinished | wrong | overreach | other."""
    if reason and reason not in REASONS:
        raise ValueError(f"--reason must be one of {', '.join(REASONS)}")
    record = ledger.load_run(p, run_id)
    prev = record.get("verdict")
    record["verdict"] = {"ok": ok, "note": note, "reason": reason, "ts": time.time()}
    learned = []
    how = record.get("learned")
    auto_ok = bool(record.get("ok") and (record.get("result") or {}).get("status") == "done")
    provisional_ok = prev.get("ok") if prev and prev.get("soft") else auto_ok
    if (how is None                                   # nothing recorded yet
            or (how in ("auto", "soft") and provisional_ok != ok)   # the provisional record was wrong: correct it
            or (how == "lead" and prev and prev.get("ok") != ok)):   # the lead changed its mind
        learned = learn.record_outcomes(p, record, final_ok=ok)
        if (record.get("route") or {}).get("b") is not None:
            record["learned"] = "lead"
    if record.get("task") and record.get("step"):
        cwd = Path(record["cwd"])
        if ok:
            learn.checkpoint(p, cwd, "done", record["task"], str(record["step"]), "--note",
                             note or f"verified ccx run {run_id}")
        else:
            learn.checkpoint(p, cwd, "fail", record["task"], str(record["step"]), "--reason", "error",
                             "--note", note or f"ccx run {run_id} failed verification")
    _write_record(p.runs / run_id, record)
    ledger.append_event(p, {"type": "verify", "run_id": run_id, "ok": ok, "reason": reason, "ts": time.time()})
    return {"run_id": run_id, "verdict": ok, "learned": learned, **({"reason": reason} if reason else {})}
