#!/usr/bin/env python3
"""task-split: how big should each piece be, and is this split any good — with numbers.

Standalone: Python 3.11+ standard library only.

Model (citations in ../references/method.md):
  p(t)    = 1 / (1 + (t / h50) ** beta)          METR: success falls logistically in log task length
  cost(n) = n * (o + t) * attempts(p)             o = per-piece overhead (brief, startup, review, handoff)
  checkable pieces: retry a failed piece (<= 3 tries)  -> success compounds mildly
  NOT checkable:    one shot each                      -> P(all) = p(t) ** n  (errors compound!)
  pick n that minimises expected cost per successful task, with every piece at p >= target.
  plan check: DAG waves, critical path, Brent bound T_w <= W/w + S, file clashes, size flags.

Usage:
  split_plan.py size  --minutes 240 [--rung codex:gpt-6.1-sol:medium] [--overhead delegated|self|<min>]
                      [--not-checkable] [--lanes 3]
  split_plan.py check plan.json [--lanes 3]
  split_plan.py template            # prints an example plan.json
  split_plan.py record --rung R --minutes 30 --ok 1   # calibrate the horizon from a verified outcome
  split_plan.py show
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    sys.exit("task-split needs Python 3.11+")

import os
import time

HERE = Path(__file__).resolve().parent
CFG = tomllib.loads((HERE.parent / "data" / "horizons.toml").read_text(encoding="utf-8"))
MAX_TRIES = 3
LEARN_RATE = 0.3        # online logistic update of ln(h50): d logL / d ln h50 = beta * (y - p)


def state_path() -> Path:
    """Learned horizons, shared by every agent that uses this skill folder (same rules as task-routing)."""
    if os.environ.get("TASK_SPLIT_HOME"):
        return Path(os.environ["TASK_SPLIT_HOME"]).expanduser() / "state.json"
    if os.environ.get("CCX_HUB"):
        return Path(os.environ["CCX_HUB"]).expanduser() / "ccx" / "split-state.json"
    skills_dir, hub = HERE.parent.parent, HERE.parent.parent.parent
    if (skills_dir.name == "skills" and not (hub / "ccx" / "__init__.py").exists()
            and any((hub / m).exists() for m in ("AGENTS.md", "memory", "mcp"))):
        return hub / "ccx" / "split-state.json"
    return Path.home() / ".task-split" / "state.json"


def load_state() -> dict:
    f = state_path()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"ln_h50": {}, "n": {}}
    except json.JSONDecodeError:
        return {"ln_h50": {}, "n": {}}


STATE = load_state()


def p_success(minutes: float, h50: float, beta: float = CFG["beta"]) -> float:
    if minutes <= 0:
        return 1.0
    return 1.0 / (1.0 + (minutes / h50) ** beta)


def horizon(rung: str) -> float:
    """Learned h50 if outcomes were recorded for this rung, else the dated prior."""
    if rung in STATE.get("ln_h50", {}):
        return math.exp(STATE["ln_h50"][rung])
    try:
        return float(CFG["h50_minutes"][rung])
    except KeyError:
        raise SystemExit(f"unknown rung {rung!r}; known: {', '.join(CFG['h50_minutes'])}")


def record(rung: str, minutes: float, ok: bool) -> dict:
    """One verified piece outcome -> nudge this rung's horizon (fit p(t) to reality)."""
    global STATE
    STATE = load_state()        # re-read: the other agent may have recorded since this process started
    h = horizon(rung)
    p = p_success(minutes, h)
    ln_h = math.log(h) + LEARN_RATE * CFG["beta"] * ((1.0 if ok else 0.0) - p)
    STATE.setdefault("ln_h50", {})[rung] = ln_h
    STATE.setdefault("n", {})[rung] = STATE.get("n", {}).get(rung, 0) + 1
    f = state_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return {"rung": rung, "predicted_p": round(p, 3), "outcome": ok, "h50_minutes_now": round(math.exp(ln_h), 1),
            "n": STATE["n"][rung]}


def max_minutes_for(p_target: float, h50: float, beta: float = CFG["beta"]) -> float:
    """Inverse of p_success: longest piece that still succeeds with probability p_target."""
    return h50 * ((1 - p_target) / p_target) ** (1 / beta)


def overhead(value: str) -> float:
    if value in CFG["overhead_minutes"]:
        return float(CFG["overhead_minutes"][value])
    return float(value)


def evaluate(total: float, n: int, h50: float, o: float, checkable: bool) -> dict:
    t = total / n
    p = p_success(t, h50)
    if checkable:
        p_piece = 1 - (1 - p) ** MAX_TRIES                 # verified retries
        tries = (1 - (1 - p) ** MAX_TRIES) / p             # expected attempts, capped
        p_all = p_piece ** n
        cost = n * (o + t) * tries
    else:
        p_all = p ** n                                      # no check -> no retry, errors compound
        cost = n * (o + t)
    return {"pieces": n, "piece_minutes": round(t, 1), "p_piece": round(p, 3), "p_task": round(p_all, 3),
            "cost_minutes": round(cost, 1), "cost_per_success": round(cost / max(p_all, 1e-9), 1)}


def size(total: float, rung: str, o: float, checkable: bool, lanes: int) -> dict:
    if total <= 0:
        raise SystemExit("--minutes must be > 0")
    h50 = horizon(rung)
    g = CFG["guards"]
    rows = [evaluate(total, n, h50, o, checkable) for n in range(1, 41)]
    rows = [r for r in rows if r["piece_minutes"] >= min(g["min_piece_minutes"], total)]
    ok = [r for r in rows if r["p_piece"] >= g["target_p"]] if checkable else rows
    best = min(ok or rows, key=lambda r: r["cost_per_success"])
    best["wall_minutes_if_independent"] = round(math.ceil(best["pieces"] / lanes) * (best["piece_minutes"] + o), 1)
    advice = []
    if not checkable:
        advice.append("pieces are not checkable: every extra cut multiplies failure risk — add a test/check "
                      "per piece before splitting finer")
    if best["pieces"] > g["max_children"]:
        advice.append(f"{best['pieces']} pieces > {g['max_children']}: split hierarchically — first 3-5 "
                      "milestones, then split each milestone only if it fails (as-needed)")
    if best["pieces"] == 1:
        advice.append("do it in one piece: splitting would cost more in overhead than it saves")
    return {"rung": rung, "h50_minutes": round(h50, 1),
            "h50_source": f"learned from {STATE['n'][rung]} outcomes" if rung in STATE.get("n", {}) else "prior (dated guess)", "max_piece_minutes_at_target": round(max_minutes_for(g["target_p"], h50), 1),
            "overhead_minutes": o, "checkable": checkable, "best": best, "advice": advice,
            "table": [r for r in rows if r["pieces"] <= 12]}


# ------------------------------------------------------------------ plan check
def waves(pieces: dict[str, dict]) -> list[list[str]]:
    indeg = {k: 0 for k in pieces}
    for k, v in pieces.items():
        for d in v.get("depends_on", []):
            if d not in pieces:
                raise SystemExit(f"piece {k!r} depends on unknown piece {d!r}")
            indeg[k] += 1
    out, ready, seen = [], sorted(k for k, d in indeg.items() if d == 0), 0
    while ready:
        out.append(ready)
        seen += len(ready)
        nxt = []
        for k in ready:
            for j, v in pieces.items():
                if k in v.get("depends_on", []):
                    indeg[j] -= 1
                    if indeg[j] == 0:
                        nxt.append(j)
        ready = sorted(nxt)
    if seen != len(pieces):
        raise SystemExit("dependency cycle in plan: " + ", ".join(k for k, d in indeg.items() if d > 0))
    return out


def critical_path(pieces: dict[str, dict], order: list[list[str]], o: float) -> tuple[float, list[str]]:
    finish, prev = {}, {}
    for wave in order:
        for k in wave:
            deps = pieces[k].get("depends_on", [])
            start = max((finish[d] for d in deps), default=0.0)
            prev[k] = max(deps, key=lambda d: finish[d]) if deps else None
            finish[k] = start + pieces[k]["minutes"] + o
    end = max(finish, key=finish.get)
    path, cur = [], end
    while cur:
        path.append(cur)
        cur = prev[cur]
    return finish[end], list(reversed(path))


def check(plan: dict, lanes: int) -> dict:
    g = CFG["guards"]
    if not plan.get("pieces"):
        raise SystemExit("plan has no pieces")
    for p in plan["pieces"]:
        if "id" not in p or "minutes" not in p:
            raise SystemExit(f"every piece needs 'id' and 'minutes' (estimated human-minutes): {p}")
    default_rung = plan.get("rung", "codex:gpt-6.1-sol:medium")
    o = overhead(plan.get("overhead", "delegated"))
    pieces = {p["id"]: p for p in plan["pieces"]}
    order = waves(pieces)
    report, p_all, cost = [], 1.0, 0.0
    for p in plan["pieces"]:
        rung = p.get("rung", default_rung)
        h50 = horizon(rung)
        ps = p_success(p["minutes"], h50)
        checkable = p.get("checkable", True)
        flags = []
        cap = max_minutes_for(g["target_p"], h50)
        if p["minutes"] > cap:
            flags.append(f"too big for {rung}: {p['minutes']} min > {cap:.0f} min (80% horizon) — split it, "
                         "or route it to a stronger rung")
        if p["minutes"] < g["min_piece_minutes"]:
            flags.append(f"tiny ({p['minutes']} min < {g['min_piece_minutes']}): overhead-dominated — merge "
                         "with a neighbour")
        if not checkable:
            flags.append("no check: failure here goes unnoticed and propagates — define a test/criterion")
        if len(p.get("depends_on", [])) > 3:
            flags.append("depends on >3 pieces: high handoff load — consider merging with its inputs")
        if checkable:
            pe = 1 - (1 - ps) ** MAX_TRIES
            cost += (o + p["minutes"]) * (pe / ps)
        else:
            pe = ps
            cost += o + p["minutes"]
        p_all *= pe
        report.append({"id": p["id"], "minutes": p["minutes"], "rung": rung, "p": round(ps, 3), "flags": flags})
    clashes = []
    for wave in order:
        for i, a in enumerate(wave):
            for b in wave[i + 1:]:
                shared = set(pieces[a].get("files", [])) & set(pieces[b].get("files", []))
                if shared:
                    clashes.append({"pieces": [a, b], "files": sorted(shared),
                                    "fix": "they run in parallel and edit the same files: make one depend on "
                                           "the other, merge them, or isolate each in its own worktree"})
    work = sum(p["minutes"] + o for p in plan["pieces"])
    span, path = critical_path(pieces, order, o)
    return {"title": plan.get("title"), "pieces": len(pieces), "waves": order,
            "total_work_minutes": round(work, 1), "critical_path_minutes": round(span, 1), "critical_path": path,
            "wall_minutes_with_lanes": round(max(span, work / lanes), 1),
            "wall_minutes_upper_bound": round(work / lanes + span, 1),
            "parallel_speedup": round(work / max(span, work / lanes), 2),
            "p_task": round(p_all, 3), "expected_cost_minutes": round(cost, 1),
            "cost_per_success_minutes": round(cost / max(p_all, 1e-9), 1),
            "pieces_report": report, "file_clashes": clashes,
            "checkpoint_init": "checkpoint.py init --title " + json.dumps(plan.get("title", "task")) + " "
                               + " ".join("--step " + json.dumps(p.get("title", p["id"])) for wave in order
                                          for p in (pieces[k] for k in wave))}


TEMPLATE = {
    "title": "Add caching layer to data loader",
    "rung": "codex:gpt-6.1-sol:medium",
    "overhead": "delegated",
    "pieces": [
        {"id": "api", "title": "Define cache interface + tests", "minutes": 30, "files": ["cache/api.py"],
         "checkable": True},
        {"id": "disk", "title": "Disk backend", "minutes": 45, "depends_on": ["api"], "files": ["cache/disk.py"]},
        {"id": "mem", "title": "Memory backend", "minutes": 30, "depends_on": ["api"], "files": ["cache/mem.py"]},
        {"id": "wire", "title": "Wire into loader", "minutes": 40, "depends_on": ["disk", "mem"],
         "files": ["loader.py"], "rung": "claude:sonnet:high"},
        {"id": "docs", "title": "Docs", "minutes": 15, "depends_on": ["wire"], "files": ["README.md"],
         "checkable": False},
    ],
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="split_plan")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("size")
    s.add_argument("--minutes", type=float, required=True, help="whole task, in human-minutes")
    s.add_argument("--rung", default="codex:gpt-6.1-sol:medium")
    s.add_argument("--overhead", default="delegated")
    s.add_argument("--not-checkable", action="store_true")
    s.add_argument("--lanes", type=int, default=3)
    c = sub.add_parser("check")
    c.add_argument("plan")
    c.add_argument("--lanes", type=int, default=3)
    sub.add_parser("template")
    r = sub.add_parser("record", help="record a verified piece outcome to calibrate the horizon")
    r.add_argument("--rung", required=True)
    r.add_argument("--minutes", type=float, required=True)
    r.add_argument("--ok", type=int, choices=[0, 1], required=True)
    sub.add_parser("show")
    a = ap.parse_args(argv)
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    if a.cmd == "template":
        print(json.dumps(TEMPLATE, indent=2))
    elif a.cmd == "record":
        print(json.dumps(record(a.rung, a.minutes, bool(a.ok))))
    elif a.cmd == "show":
        print(json.dumps({"state_file": str(state_path()),
                          "h50_minutes": {k: round(math.exp(v), 1) for k, v in STATE.get("ln_h50", {}).items()},
                          "n": STATE.get("n", {})}, indent=2))
    elif a.cmd == "size":
        print(json.dumps(size(a.minutes, a.rung, overhead(a.overhead), not a.not_checkable, a.lanes), indent=2))
    else:
        plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
        print(json.dumps(check(plan, a.lanes), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
