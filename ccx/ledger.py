"""Run records and the token ledger.

Every run appends one line to <hub>/ccx/ledger.jsonl. `ccx stats` reads it so
routing can be tuned from real numbers instead of guesses.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

from .config import Paths


def append_event(p: Paths, event: dict) -> None:
    """Non-run rows (e.g. the lead's verdict). Readers that aggregate runs skip rows with a 'type'."""
    p.ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(p.ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def append(p: Paths, record: dict) -> None:
    p.ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(p.ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(_slim(record), ensure_ascii=False) + "\n")


def _slim(record: dict) -> dict:
    slim = {k: record.get(k) for k in ("run_id", "label", "to", "caller", "tier", "start_tier",
                                       "mode", "ok", "ts", "kind", "task", "step", "cwd", "session_id",
                                       "lead_session", "continue_depth", "ephemeral", "mode_source")}
    slim["rungs"] = [a.get("rung") for a in record["attempts"]]
    slim["sessions"] = sorted({a["session_id"] for a in record["attempts"] if a.get("session_id")})
    slim["b"] = (record.get("route") or {}).get("b")
    ae = [a["ae_usd"] for a in record["attempts"] if a.get("ae_usd") is not None]
    slim["ae_usd"] = round(sum(ae), 6) if ae else None
    by: dict[str, float] = {}
    for a in record["attempts"]:
        if a.get("ae_usd") is not None:
            by[a["agent"]] = round(by.get(a["agent"], 0.0) + a["ae_usd"], 6)
    slim["ae_by_agent"] = by
    slim["status"] = (record.get("result") or {}).get("status", "error")
    slim["usage"] = sum_usage(record["attempts"])
    u4: dict[str, int] = {}
    for a in record["attempts"]:
        for k, v in (a.get("usage") or {}).items():
            u4[k] = u4.get(k, 0) + int(v or 0)
    slim["usage4"] = u4
    slim["seconds"] = round(sum(a["seconds"] for a in record["attempts"]), 1)
    costs = [a["cost_usd"] for a in record["attempts"] if a.get("cost_usd") is not None]
    slim["cost_usd"] = round(sum(costs), 5) if costs else None
    slim["attempts"] = len(record["attempts"])
    return slim


def sum_usage(attempts: list[dict]) -> dict:
    """input = fresh + cache writes (all non-cached prompt), cached = cache reads, output."""
    tot = {"input": 0, "cache_write": 0, "cached": 0, "output": 0}
    for a in attempts:
        u = a.get("usage") or {}
        tot["input"] += int(u.get("input_tokens", 0)) + int(u.get("cache_write_tokens", 0))
        tot["cache_write"] += int(u.get("cache_write_tokens", 0))
        tot["cached"] += int(u.get("cached_input_tokens", 0))
        tot["output"] += int(u.get("output_tokens", 0))
    return tot


def load_run(p: Paths, run_id: str) -> dict:
    f = p.runs / run_id / "run.json"
    if not f.exists():
        raise FileNotFoundError(f"no ccx run {run_id!r} under {p.runs}")
    return json.loads(f.read_text(encoding="utf-8"))


def spent_today(p: Paths, agent: str) -> float:
    """USD this agent's attempts cost since local midnight (for a daily cap on pay-per-token providers)."""
    t = time.localtime()
    midnight = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    return sum((r.get("ae_by_agent") or {}).get(agent, 0.0) for r in rows(p) if (r.get("ts") or 0) >= midnight)


def rows(p: Paths) -> list[dict]:
    if not p.ledger.exists():
        return []
    out = []
    for line in p.ledger.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def stats(p: Paths) -> list[dict]:
    agg: dict[tuple, dict] = defaultdict(lambda: {"runs": 0, "done": 0, "escalated": 0,
                                                 "input": 0, "cached": 0, "output": 0,
                                                 "seconds": 0.0, "cost_usd": 0.0, "cost_known": 0})
    for r in rows(p):
        if r.get("type"):
            continue
        a = agg[(r["to"], r["start_tier"])]
        a["runs"] += 1
        a["done"] += r.get("status") == "done"
        a["escalated"] += r.get("attempts", 1) > 1
        for k in ("input", "cached", "output"):
            a[k] += r["usage"].get(k, 0)
        a["seconds"] += r.get("seconds", 0)
        if r.get("cost_usd") is not None:
            a["cost_usd"] += r["cost_usd"]
            a["cost_known"] += 1
    out = []
    for (agent, tier), a in sorted(agg.items()):
        n = a["runs"]
        out.append({"agent": agent, "tier": tier, "runs": n,
                    "done_rate": round(a["done"] / n, 2), "escalated": a["escalated"],
                    "avg_input": a["input"] // n, "avg_cached": a["cached"] // n,
                    "avg_output": a["output"] // n, "avg_seconds": round(a["seconds"] / n, 1),
                    "cost_usd": round(a["cost_usd"], 4) if a["cost_known"] else None})
    return out


def repair(p: Paths, apply: bool = False) -> dict:
    """Re-count Codex attempts written before ccx counted only the growth of a resumed session (`codex exec
    resume` reports the session's running total). Dry run unless apply; idempotent (fixed attempts carry
    codex_total). The ledger is backed up first."""
    import os
    import time
    from . import learn
    from .delegate import _codex_growth, _codex_total
    recs = []
    for f in sorted(p.runs.glob("*/run.json")) if p.runs.exists() else []:
        try:
            recs.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    recs.sort(key=lambda x: x[1].get("ts") or 0)
    seen, changed, fixed = {}, [], []
    for f, rec in recs:
        before = sum(a.get("ae_usd") or 0 for a in rec.get("attempts", []))
        touched = False
        for a in rec.get("attempts", []):
            sid, u = a.get("session_id"), a.get("usage")
            if a.get("agent") != "codex" or not sid or not u:
                continue
            if a.get("codex_total"):                       # counted correctly already
                seen[sid] = a["codex_total"]
                continue
            total = _codex_total(u)
            if sid in seen and all(total[k] >= seen[sid].get(k, 0) for k in total):
                a["usage"] = _codex_growth(total, seen[sid])
                ae = learn.price_usd(p, "codex", a.get("model"), a["usage"])
                a["ae_usd"] = round(ae, 6) if ae is not None else None
                touched = True
            a["codex_total"] = total
            seen[sid] = total
        if touched:
            after = sum(a.get("ae_usd") or 0 for a in rec["attempts"])
            changed.append({"run_id": rec["run_id"], "ae_before": round(before, 5), "ae_after": round(after, 5)})
            fixed.append((f, rec))
    out = {"applied": apply, "runs_fixed": len(changed), "runs": changed,
           "ae_before": round(sum(c["ae_before"] for c in changed), 5),
           "ae_after": round(sum(c["ae_after"] for c in changed), 5)}
    if not apply or not fixed:
        out["note"] = "dry run: add --apply" if not apply else "nothing to fix"
        return out
    for f, rec in fixed:
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, f)
    if p.ledger.exists():
        by_id = {rec["run_id"]: rec for _, rec in fixed}
        lines = p.ledger.read_text(encoding="utf-8").splitlines()
        bak = p.ledger.with_name(f"ledger.jsonl.bak-{time.strftime('%Y%m%d%H%M%S')}")
        bak.write_text("\n".join(lines) + "\n", encoding="utf-8")
        new = []
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                new.append(line)
                continue
            rid = row.get("run_id")
            new.append(json.dumps(_slim(by_id[rid]), ensure_ascii=False)
                       if not row.get("type") and rid in by_id else line)
        tmp = p.ledger.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new) + "\n", encoding="utf-8")
        os.replace(tmp, p.ledger)
        out["ledger_backup"] = str(bak)
    return out
