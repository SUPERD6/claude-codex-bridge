#!/usr/bin/env python3
"""task-routing: pick (agent, model, effort) for a task, with numbers you can check.

Standalone: Python 3.11+ standard library only. Works with or without ccx.

Method (details + citations in ../references/method.md):
  1. difficulty  b in [0,10]  from a 5-item rubric the lead agent fills in
  2. ability     theta(rung)  prior from data/priors.toml + learned offset
  3. success     P = 1 / (1 + exp(-a (theta - b)))              (IRT 2PL)
  4. cost        C = estimated API-equivalent USD for one attempt
  5. choose      cascade:  E_r = C_r + (1 - P_r) * E_next  (start cheap, escalate on verified failure)
                 no cascade: cheapest rung with P >= tau
  6. learn       theta_offset += lr * (outcome - P)                (Elo-style online IRT)

Usage:
  task_routing.py route --files 3 --coupling cross --clarity goal --risk low --novelty pattern
                        [--agents codex,claude] [--tradeoff balanced] [--not-verifiable]
                        [--lead claude:opus:high --ctx-tokens 40000 --remaining-turns 10] [--explain]
  task_routing.py record --rung codex:gpt-6.1-sol:medium --b 4 --ok 1 [--cost-usd 0.12]
  task_routing.py show
  task_routing.py rubric
  task_routing.py refresh [--if-stale]     public benchmark data, at most weekly (scripts/benchmarks.py)
  task_routing.py sources                  how old it is and whom to credit
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    sys.exit("task-routing needs Python 3.11+")

HERE = Path(__file__).resolve().parent
PRIORS = HERE.parent / "data" / "priors.toml"

RUBRIC = {
    "files":    "how many files will be touched: 1 -> 0, 2-3 -> 1, 4-8 -> 2, 9+ -> 3",
    "coupling": "one = single module (0) | cross = several modules (1) | system = architecture-wide (2)",
    "clarity":  "spec = spec + a test defines done (0) | goal = clear goal, no test (1) | unknown = cause/approach unknown (2)",
    "risk":     "low (0) | visible = user-visible behaviour (1) | critical = security, data, correctness, money (2)",
    "novelty":  "pattern = an existing pattern in the repo to follow (0) | new = new design (1)",
}
POINTS = {
    "coupling": {"one": 0, "cross": 1, "system": 2},
    "clarity": {"spec": 0, "goal": 1, "unknown": 2},
    "risk": {"low": 0, "visible": 1, "critical": 2},
    "novelty": {"pattern": 0, "new": 1},
}


# ------------------------------------------------------------------ state
def state_path() -> Path:
    """Where learned abilities live. Both agents must hit the SAME file to learn together."""
    if os.environ.get("TASK_ROUTING_HOME"):
        return Path(os.environ["TASK_ROUTING_HOME"]).expanduser() / "state.json"
    if os.environ.get("CCX_HUB"):
        return Path(os.environ["CCX_HUB"]).expanduser() / "ccx" / "routing-state.json"
    # installed as <hub>/skills/task-routing (linked into each agent): resolve() follows the
    # junction/symlink, so Claude and Codex land on the same hub file
    hub = installed_hub(HERE.parent.parent)
    if hub:
        return hub / "ccx" / "routing-state.json"
    return Path.home() / ".task-routing" / "state.json"


class _Lock:
    """Tiny cross-process lock so two agents recording at once don't lose an update."""
    def __init__(self, target: Path):
        self.path = target.with_suffix(target.suffix + ".lock")

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.time() - t0 > 10:          # stale lock from a crashed writer
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                time.sleep(0.05)

    def __exit__(self, *exc):
        os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def installed_hub(skills_dir: Path) -> Path | None:
    """The hub this skill is installed in, if any: <hub>/skills/<skill> with a hub marker next to skills/.
    The source repo (which has a ccx/ python package) never counts."""
    hub = skills_dir.parent
    if skills_dir.name != "skills" or (hub / "ccx" / "__init__.py").exists():
        return None
    if any((hub / m).exists() for m in ("AGENTS.md", "memory", "mcp")):
        return hub
    return None


def load_state(p: Path | None = None) -> dict:
    p = p or state_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"offsets": {}, "counts": {}, "last_decay": time.time(), "outcomes": []}


def save_state(s: dict, p: Path | None = None) -> None:
    p = p or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    s["outcomes"] = s.get("outcomes", [])[-1000:]
    p.write_text(json.dumps(s, indent=1), encoding="utf-8")


def bench():
    """The benchmark cache module (scripts/benchmarks.py), importable however this file was loaded."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import benchmarks
    return benchmarks


def bench_path() -> Path:
    """Public benchmark data cached next to the learned state (same file for both agents)."""
    return state_path().parent / "benchmarks.json"


def bench_plugin_dirs() -> list[Path]:
    """Where the user's own extra sources live (never in the repository): <state dir>/bench-sources."""
    return [state_path().parent / "bench-sources"]


KINDS = ("code", "read", "research", "write")
_MERGE_CACHE: dict = {}


def with_benchmarks(pri: dict, kind: str = "code") -> dict:
    """Priors whose rung thetas blend the hand-set value with public benchmarks (scripts/merge.py) for this kind
    of task. Without a benchmark cache, or with an older priors file, the priors come back unchanged."""
    if pri.get("_merged") or not pri.get("aliases"):
        return pri
    f = bench_path()
    try:
        stamp = f.stat().st_mtime
    except OSError:
        return pri
    key = (str(f), stamp, kind, id(pri.get("rungs")))
    if key not in _MERGE_CACHE:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import merge
        cache = bench().load(f)
        scores = cache.get("scores") or []
        aliases = {m: [tuple(x) for x in v] for m, v in pri["aliases"].items()}
        cfg = dict(pri.get("merge") or {})
        extra = cache.get("kind_weights") or {}          # weights declared by local source plugins
        if extra:
            kinds = {k: dict(v) for k, v in (cfg.get("kinds") or merge.DEFAULTS["kinds"]).items()}
            for k, ws in extra.items():
                kinds.setdefault(k, {}).update(ws)
            cfg["kinds"] = kinds
        _MERGE_CACHE.clear()
        _MERGE_CACHE[key] = merge.merged_thetas(scores, pri["rungs"], aliases, kind=kind, cfg=cfg)
    m = _MERGE_CACHE[key]
    rungs = [{**r, "theta": m[rung_key(r)]["theta"], "theta_prior": r["theta"],
              "bench": {"theta": m[rung_key(r)]["bench_theta"], "sd": m[rung_key(r)]["sd"],
                        "used": m[rung_key(r)]["used"][:4]}} if rung_key(r) in m else r for r in pri["rungs"]]
    return {**pri, "rungs": rungs, "_merged": kind}


def load_priors(path: Path = PRIORS) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def rung_key(r: dict) -> str:
    return f"{r['agent']}:{r['model']}:{r['effort']}"


# ------------------------------------------------------------------ core math
def difficulty(files: int, coupling: str, clarity: str, risk: str, novelty: str) -> int:
    f = 0 if files <= 1 else 1 if files <= 3 else 2 if files <= 8 else 3
    return (f + POINTS["coupling"][coupling] + POINTS["clarity"][clarity]
            + POINTS["risk"][risk] + POINTS["novelty"][novelty])


# ---- difficulty in a standard unit: minutes a skilled engineer would need (METR's task-length unit) -----------
# b = log2(minutes): 1 min -> 0, 8 min -> 3, ~1 h -> 6, ~17 h -> 10. The 50%-success task length of a rung is then
# 2**theta minutes. An assumption about our scale, refitted from outcomes (refit) — not a METR measurement.
MINUTES_WEIGHT = 0.6        # when both are given, the minutes estimate counts 60%, the rubric 40%
BIAS_LR = 0.1               # how fast a lead's habit of over- or under-estimating is learned


def b_from_minutes(minutes: float) -> float:
    return max(0.0, min(10.0, math.log2(max(1.0, float(minutes)))))


def h50_minutes(theta: float) -> float:
    return 2.0 ** theta


def combine_difficulty(b_rubric: float | None, minutes: float | None, bias: float = 0.0) -> dict:
    """b from the human-minutes estimate and/or the rubric, plus the lead's learned bias."""
    parts = {}
    if minutes:
        parts["minutes"] = round(b_from_minutes(minutes), 2)
    if b_rubric is not None:
        parts["rubric"] = float(b_rubric)
    if not parts:
        raise ValueError("need a rubric or a minutes estimate")
    b = (MINUTES_WEIGHT * parts["minutes"] + (1 - MINUTES_WEIGHT) * parts["rubric"]
         if len(parts) == 2 else next(iter(parts.values())))
    if bias:
        parts["lead_bias"] = round(bias, 2)
    return {"b": round(max(0.0, min(10.0, b + bias)), 2), "parts": parts}


def lead_bias(state: dict, lead: str | None) -> float:
    return float((state.get("lead_bias") or {}).get(lead or "", 0.0))


def record_bias(state: dict, lead: str, ok: bool, predicted_p: float, b_items: dict | None = None,
                minutes: float | None = None, seconds: float | None = None) -> float:
    """A lead whose tasks fail more often than predicted is underestimating them: its b goes up (and down for the
    opposite). Keeps a short log of estimate vs actual time and the rubric items, for refit."""
    lb = state.setdefault("lead_bias", {})
    lb[lead] = round(max(-3.0, min(3.0, lb.get(lead, 0.0) + BIAS_LR * (predicted_p - (1.0 if ok else 0.0)))), 4)
    log = state.setdefault("difficulty_log", [])
    log.append({"ts": time.time(), "lead": lead, "ok": ok, "p": round(predicted_p, 3), "items": b_items or {},
                "minutes": minutes, "seconds": seconds})
    del log[:-500]
    return lb[lead]


def refit(state: dict, min_n: int = 30) -> dict:
    """Logistic regression of outcome on the rubric items and the minutes estimate (gradient descent, stdlib).
    Advice only: it prints suggested weights, the priors are not changed."""
    rows = [r for r in state.get("difficulty_log", []) if r.get("items")]
    if len(rows) < min_n:
        return {"n": len(rows), "note": f"need at least {min_n} recorded outcomes with rubric items"}
    names = ["files", "coupling", "clarity", "risk", "novelty", "minutes"]
    enc = {"files": lambda v: 0 if int(v) <= 1 else 1 if int(v) <= 3 else 2 if int(v) <= 8 else 3}
    X, y = [], []
    for r in rows:
        it = r["items"]
        x = [float(enc["files"](it.get("files", 1)))]
        x += [float(POINTS[k].get(it.get(k), 0)) for k in ("coupling", "clarity", "risk", "novelty")]
        x.append(b_from_minutes(r["minutes"]) if r.get("minutes") else 0.0)
        X.append(x)
        y.append(1.0 if r["ok"] else 0.0)
    w, c = [0.0] * len(names), 0.0
    for _ in range(3000):
        gw, gc = [0.0] * len(names), 0.0
        for x, t in zip(X, y):
            z = c - sum(wi * xi for wi, xi in zip(w, x))        # more difficulty -> lower success
            pr = 1 / (1 + math.exp(-max(-30, min(30, z))))
            for i, xi in enumerate(x):
                gw[i] += (pr - t) * -xi        # d(loss)/dw_i, with z = c - w.x
            gc += pr - t
        w = [wi - 0.05 * g / len(X) for wi, g in zip(w, gw)]
        c -= 0.05 * gc / len(X)
    return {"n": len(rows), "weights": dict(zip(names, (round(x, 3) for x in w))), "intercept": round(c, 3),
            "note": "suggested weights (difficulty points per unit); compare with the equal weights in use"}


# ---- total cost: money + the shadow price of subscription quota + time + risk, all in dollars ---------------------
TOTAL = {"lambda_floor": 0.3, "lambda_from": 0.6, "lambda_over": 2.0,
         "value_of_time": {"save": 0.005, "balanced": 0.02, "fast": 0.10},          # $ per minute of waiting
         "failure_cost": {"low": 0.5, "visible": 3.0, "critical": 20.0},            # $ for a wrong result shipped
         "minutes_per_attempt": {"low": 1.5, "medium": 3.0, "high": 6.0, "xhigh": 10.0, "max": 15.0,
                                 "default": 4.0},
         "minutes_per_b": 0.25}


def _total_cfg(pri: dict) -> dict:
    t = {**TOTAL, **(pri.get("total_cost") or {})}
    for k in ("value_of_time", "failure_cost", "minutes_per_attempt"):
        t[k] = {**TOTAL[k], **((pri.get("total_cost") or {}).get(k) or {})}
    return t


def shadow_lambda(used: float | None, pri: dict | None = None) -> float:
    """What a dollar of subscription quota is worth, as a share of its API price: a floor while there is room
    (the quota is kept for the lead and hard work), rising to the full price as it runs out, doubled beyond.
    `used` is the share of the window used (or, with pacing, projected by the reset)."""
    t = _total_cfg(pri or {})
    if used is None or used < t["lambda_from"]:
        return t["lambda_floor"]
    if used >= 1.0:
        return t["lambda_over"]
    return t["lambda_floor"] + (1.0 - t["lambda_floor"]) * (used - t["lambda_from"]) / (1.0 - t["lambda_from"])


def attempt_minutes(r: dict, b: float, pri: dict, state: dict | None = None) -> float:
    """Wall time of one attempt: measured average for this rung when there is one, else by effort and difficulty."""
    k = rung_key(r)
    seen = ((state or {}).get("minutes") or {}).get(k)
    if seen:
        return float(seen)
    t = _total_cfg(pri)
    base = t["minutes_per_attempt"].get(r.get("effort"), t["minutes_per_attempt"]["default"])
    return base * (1 + t["minutes_per_b"] * b)


def is_cash(pri: dict, agent: str) -> bool:
    return agent in ((pri.get("cash") or {}).get("agents") or [])


def p_success(theta: float, b: float, a: float) -> float:
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))


def startup_tokens(pri: dict, r: dict, mode: str | None = None) -> int:
    """Fixed context per request for this rung: codex low rungs start lean (no user config), claude read-only
    runs load fewer tools. Falls back to the per-agent default."""
    c = pri["cost"]
    by = c.get("startup_by") or {}
    if r["agent"].endswith("-builtin"):                # the lead's own sub-agents: full tools, not ccx's slim start
        return by.get(r["agent"]) or c["startup_tokens"].get(r["agent"].split("-")[0], 30000)
    key = (f"{r['agent']}:lean" if r["agent"] == "codex" and r["effort"] == "low" else
           f"{r['agent']}:read" if mode == "read" else None)
    return by.get(key) or c["startup_tokens"].get(r["agent"], 30000)


def price_mult(pri: dict, agent: str, ts: float | None = None) -> float:
    """Off-peak discount for agents billed by the hour of day ([offpeak.<agent>] in the priors), else 1."""
    o = (pri.get("offpeak") or {}).get(agent)
    if not o:
        return 1.0
    t = time.gmtime(time.time() if ts is None else ts)
    peak = (not o.get("weekdays_only", True) or t.tm_wday < 5) and         any(lo <= t.tm_hour < hi for lo, hi in o.get("peak_utc", []))
    return 1.0 if peak else float(o.get("mult", 1.0))


def attempt_cost(r: dict, b: float, pri: dict, ctx_tokens: int = 0, factor: float = 1.0,
                 mode: str | None = None) -> dict:
    c, price = pri["cost"], pri["prices"][r["price"]]
    factor *= price_mult(pri, r["agent"])
    turns = c["turns_base"] + c["turns_per_b"] * b
    total_in = turns * startup_tokens(pri, r, mode) + ctx_tokens + turns * c["fresh_input_per_turn"]
    cached = c["cached_share"] * total_in
    fresh = total_in - cached
    out = c["output_base"] * (1 + b / 2) * c["effort_mult"].get(r["effort"], 1.0)
    usd = factor * (fresh * price["input"] + cached * price["cached"] + out * price["output"]) / 1e6
    return {"usd": usd, "calibrated": factor != 1.0, "input": int(total_in), "cached": int(cached), "output": int(out), "turns": round(turns, 1)}


def observed_offsets(pri: dict) -> dict[str, float]:
    """Starting offsets from built-in outcomes ([observed] in the priors): per rung, the theta shift that makes the
    model expect the observed successes (smoothed, so 42 of 42 gives a finite shift), times `weight`, capped at
    `max_shift`. A low-weight head start for a new hub, not a measurement of it."""
    obs = pri.get("observed") or {}
    a, w, cap = pri["irt"]["a"], float(obs.get("weight", 0.5)), float(obs.get("max_shift", 1.5))
    theta = {rung_key(r): r["theta"] for r in pri["rungs"]}
    by: dict[str, list] = {}
    for d in obs.get("data") or []:
        if d["rung"] in theta:
            by.setdefault(d["rung"], []).append(d)
    out = {}
    for k, ds in by.items():
        n, ok = sum(d["n"] for d in ds), sum(d["ok"] for d in ds)
        want = (ok + 0.5) / (n + 1) * n
        lo, hi = -4.0, 4.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if sum(d["n"] * p_success(theta[k] + mid, d["b"], a) for d in ds) < want:
                lo = mid
            else:
                hi = mid
        out[k] = round(max(-cap, min(cap, w * (lo + hi) / 2)), 3)
    return out


def offset(state: dict, pri: dict, rung: str) -> float:
    """What this hub has learned about a rung; before its first outcome, the built-in head start (observed_offsets)."""
    offs = state.get("offsets", {})
    return offs[rung] if rung in offs else observed_offsets(pri).get(rung, 0.0)


def decay(state: dict, pri: dict) -> None:
    weeks = (time.time() - state.get("last_decay", time.time())) / (7 * 86400)
    if weeks >= 1:
        f = pri["irt"]["decay_per_week"] ** int(weeks)
        state["offsets"] = {k: v * f for k, v in state["offsets"].items()}
        state["last_decay"] = time.time()


# ------------------------------------------------------------------ model discovery
def available_codex_models() -> set[str] | None:
    """Models Codex says are available on this machine (None = unknown, don't filter)."""
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    f = home / "models_cache.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return {m["slug"] for m in data.get("models", []) if m.get("visibility") == "list"}
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ models this account can't use
UNAVAILABLE_DAYS = 7       # re-try after a week: model access changes with rollouts and CLI versions


def unavailable(state: dict, agent: str, model: str, cli: str | None = None) -> bool:
    """True while the mark is fresh. A mark made under another CLI version (`cli`) no longer counts."""
    e = (state.get("unavailable") or {}).get(f"{agent}:{model}")
    if isinstance(e, (int, float)):            # older state files: a bare timestamp
        e = {"ts": e}
    if not e:
        return False
    if cli and e.get("cli") and e["cli"] != cli:
        return False
    return time.time() - e.get("ts", 0) < UNAVAILABLE_DAYS * 86400


def mark_unavailable(state: dict, agent: str, model: str, cli: str | None = None) -> None:
    state.setdefault("unavailable", {})[f"{agent}:{model}"] = {"ts": time.time(), "cli": cli or ""}


# ------------------------------------------------------------------ routing
def tradeoff_params(pri: dict, tradeoff) -> dict:
    """Named preset (save | balanced | fast) or a knob 0..1 (0 = cheapest, 1 = fastest/safest).
    Knob -> tau = 0.70 + 0.20*k (success target), cascade while k < 0.75. balanced == 0.5."""
    if isinstance(tradeoff, str) and tradeoff in pri["tradeoff"]:
        return pri["tradeoff"][tradeoff]
    try:
        k = min(1.0, max(0.0, float(tradeoff)))
    except (TypeError, ValueError):
        raise ValueError(f"tradeoff must be one of {', '.join(pri['tradeoff'])} or a number 0..1, got {tradeoff!r}")
    return {"tau": round(0.70 + 0.20 * k, 3), "cascade": k < 0.75}


def route(b: float, pri: dict, state: dict, agents: list[str], tradeoff: str = "balanced",
          verifiable: bool = True, ctx_tokens: int = 0, max_escalations: int = 2, mode: str | None = None,
          kind: str = "code", quota: dict | None = None, risk: str = "low") -> dict:
    pri = with_benchmarks(pri, kind)
    tc = _total_cfg(pri)
    vot = tc["value_of_time"].get(tradeoff if isinstance(tradeoff, str) else "balanced", tc["value_of_time"]["balanced"])
    fail_cost = tc["failure_cost"].get(risk, tc["failure_cost"]["low"])
    quota = quota or {}
    t = tradeoff_params(pri, tradeoff)
    tau, cascade = t["tau"], t["cascade"] and verifiable
    a = pri["irt"]["a"]
    avail = available_codex_models()
    unknown_new = sorted(avail - {r["model"] for r in pri["rungs"]}) if avail else []
    rows = []
    for r in pri["rungs"]:
        if r["agent"] not in agents:
            continue
        if r["agent"] == "codex" and avail is not None and r["model"] not in avail:
            continue
        if unavailable(state, r["agent"], r["model"]):
            continue
        k = rung_key(r)
        theta = r["theta"] + offset(state, pri, k)
        p = p_success(theta, b, a)
        cost = attempt_cost(r, b, pri, ctx_tokens, state.get("cost_factor", {}).get(k, 1.0), mode=mode)
        rows.append({"rung": k, "agent": r["agent"], "theta": round(theta, 2), "p": p, "cost": cost,
                     "h50_minutes": round(h50_minutes(theta)),
                     "n": state["counts"].get(k, 0),
                     **({"theta_prior": r["theta_prior"], "bench": r["bench"]} if "bench" in r else {})})
    if not rows:
        raise ValueError("no rungs available for agents " + ",".join(agents))

    # expected cost of "start here, escalate up this agent's ladder on verified failure"; an agent with an
    # [escalate_to] entry continues on that agent's stronger rungs once its own run out
    for agent in agents:
        ladder = sorted([x for x in rows if x["agent"] == agent], key=lambda x: x["theta"])
        nxt = (pri.get("escalate_to") or {}).get(agent)
        if ladder and nxt in agents:
            ladder += sorted([x for x in rows if x["agent"] == nxt and x["theta"] > ladder[-1]["theta"]],
                             key=lambda x: x["theta"])
        for i, x in enumerate(ladder):
            if x["agent"] != agent:
                break                                          # those start on their own agent's ladder
            chain = ladder[i:i + 1 + max_escalations]
            exp_cost, fail = 0.0, 1.0
            parts = {"money": 0.0, "quota": 0.0, "time": 0.0, "minutes": 0.0}
            for y in chain:
                exp_cost += fail * y["cost"]["usd"]
                if is_cash(pri, y["agent"]):
                    parts["money"] += fail * y["cost"]["usd"]
                else:
                    parts["quota"] += fail * y["cost"]["usd"] * shadow_lambda(quota.get(y["agent"]), pri)
                mins = attempt_minutes(next(r for r in pri["rungs"] if rung_key(r) == y["rung"]), b, pri, state)
                parts["minutes"] += fail * mins
                parts["time"] += fail * mins * vot
                fail *= (1 - y["p"])
            parts["risk"] = fail * fail_cost
            x["chain_success"] = 1 - fail
            x["expected_usd"] = exp_cost
            x["cps"] = exp_cost / max(1 - fail, 1e-6)          # cost per success
            x["total"] = {k: round(v, 4) for k, v in parts.items()} | {
                "sum": round(parts["money"] + parts["quota"] + parts["time"] + parts["risk"], 4)}
            x["escalates_to"] = [y["rung"] for y in chain[1:]]

    if cascade:
        ok = [x for x in rows if x["chain_success"] >= tau]
        pick = min(ok, key=lambda x: x["total"]["sum"]) if ok else max(rows, key=lambda x: x["chain_success"])
        rule = (f"cascade: lowest total cost (money + quota shadow price + time + risk) among starts whose "
                f"escalation chain reaches P>={tau}")
    else:
        ok = [x for x in rows if x["p"] >= tau]
        pick = min(ok, key=lambda x: x["cost"]["usd"] / x["p"]) if ok else max(rows, key=lambda x: x["p"])
        rule = (f"no cascade ({'not verifiable' if not verifiable else tradeoff}): "
                f"cheapest single attempt with P>={tau}")
    advice = None
    pol = pri.get("policy", {})
    if b < pol.get("min_delegate_b", 2):
        advice = "do-it-yourself: too small to delegate (startup + review cost more than the edit)"
    elif pick["chain_success"] < pol.get("split_below_p", 0.5):
        advice = ("split: no model is likely to finish this in one go; break it into smaller, "
                  "verifiable sub-tasks (task-split skill) and route each")
    if not ok:
        rule += " — none qualified, took the most capable rung"
    stale = None
    try:
        age = (time.time() - time.mktime(time.strptime(pri.get("as_of", ""), "%Y-%m-%d"))) / 86400
        if age > 30:
            stale = f"priors/prices are {int(age)} days old: check the official pricing pages and update data/priors.toml"
    except ValueError:
        pass
    return {"b": b, "advice": advice, "stale": stale, "tradeoff": tradeoff, "tau": tau, "rule": rule, "pick": pick,
            "rows": sorted(rows, key=lambda x: (x["agent"], x["theta"])),
            "new_models_without_prior": unknown_new}


def lead_rereads(pri: dict, price: dict, b: float, lead_ctx: int, way: str) -> float:
    """$ for the lead re-reading its own conversation (`lead_ctx` tokens a request, a cache read) on the turns this
    way costs it: more when it does the task itself than when it only briefs and reads back a result."""
    c = pri["cost"]
    turns = (c.get("lead_turns_self_base", 2) + c.get("lead_turns_self_per_b", 0.5) * b if way == "self"
             else c.get("lead_turns_delegate", 2))
    return turns * lead_ctx * price["cached"] / 1e6


def self_vs_delegate(b: float, pri: dict, state: dict, lead: str, best: dict,
                     ctx_tokens: int, remaining_turns: int, lead_ctx: int = 0) -> dict:
    agent, model, effort = lead.split(":")
    r = next((x for x in pri["rungs"] if rung_key(x) == lead), None)
    if r is None:
        return {"note": f"lead rung {lead} not in priors; cannot compare"}
    price = pri["prices"][r["price"]]
    persist = lambda tok: tok * (price["input"] * 1.25 + remaining_turns * price["cached"]) / 1e6  # noqa: E731
    c_self = attempt_cost(r, b, pri, ctx_tokens)["usd"] - pri["cost"]["startup_tokens"].get(agent, 0) \
        * (pri["cost"]["turns_base"] + pri["cost"]["turns_per_b"] * b) * price["cached"] / 1e6 + persist(ctx_tokens) \
        + lead_rereads(pri, price, b, lead_ctx, "self")
    brief, readback = 400, 600
    review = 1500 + 1000 * b          # lead reads the diff / runs the check before trusting the result
    c_del = brief * price["output"] / 1e6 + best["expected_usd"] + persist(readback + review) \
        + lead_rereads(pri, price, b, lead_ctx, "delegate")
    p_floor = best["chain_success"] >= 0.6
    delegate = p_floor and c_del < 0.85 * c_self
    return {"self_usd": round(c_self, 4), "delegate_usd": round(c_del, 4),
            "recommend": "delegate" if delegate else "self",
            "why": ("delegating is >15% cheaper and likely to succeed" if delegate else
                    "success too uncertain to delegate" if not p_floor else
                    "doing it yourself is cheaper or within the 15% noise margin")}


# ------------------------------------------------------------------ self / built-in sub-agent / delegate
BUILTIN_MODELS = {"claude": [("haiku", "low"), ("sonnet", "medium"), ("opus", "high")]}   # Agent tool picks a model
NEEDS_DELEGATE = ("undo", "worktree", "other-vendor", "resume")   # only a ccx run gives these


def builtin_rungs(pri: dict, lead: str) -> list[dict]:
    """The lead's own sub-agents as rungs. Claude Code's Agent tool chooses Haiku/Sonnet/Opus; a Codex child runs on
    the lead's own model and effort (seen with codex-cli 0.164). Ability = the nearest ordinary rung; ccx verify
    calibrates them like any other rung (keys `<agent>-builtin:model:effort`)."""
    agent, model, effort = lead.split(":")
    pairs = BUILTIN_MODELS.get(agent) or [(model, effort)]
    out = []
    for m, e in pairs:
        base = next((x for x in pri["rungs"] if x["agent"] == agent and x["model"] == m and x["effort"] == e), None) \
            or next((x for x in pri["rungs"] if x["agent"] == agent and x["model"] == m), None)
        if base:
            out.append({**base, "agent": f"{agent}-builtin"})
    return out


def three_way(b: float, pri: dict, state: dict, lead: str, delegate_agents: list[str], ctx_tokens: int,
              remaining_turns: int, tradeoff: str = "balanced", needs: tuple = (), quota: dict | None = None,
              kind: str = "code", risk: str = "low", lead_ctx: int = 0) -> dict:
    """Do it yourself, hand it to your own built-in sub-agent, or delegate it through ccx — lowest total cost
    (money + subscription quota at its shadow price + time + risk) among options likely to succeed. Hard needs (undo,
    worktree, another vendor, resume) rule out the built-in sub-agent."""
    agent = lead.split(":")[0]
    pri = with_benchmarks(pri, kind)
    r = next((x for x in pri["rungs"] if rung_key(x) == lead), None)
    if r is None:
        return {"note": f"lead rung {lead} not in priors; cannot compare"}
    tc = _total_cfg(pri)
    vot = tc["value_of_time"].get(tradeoff if isinstance(tradeoff, str) else "balanced", tc["value_of_time"]["balanced"])
    fail_cost = tc["failure_cost"].get(risk, tc["failure_cost"]["low"])
    quota = quota or {}
    lam = shadow_lambda(quota.get(agent), pri)             # the lead's own quota pays for self, built-in and overhead
    price = pri["prices"][r["price"]]
    persist = lambda tok: tok * (price["input"] * 1.25 + remaining_turns * price["cached"]) / 1e6  # noqa: E731
    overhead = 400 * price["output"] / 1e6 + persist(600 + 1500 + 1000 * b) \
        + lead_rereads(pri, price, b, lead_ctx, "delegate")                    # brief + read-back + review
    self_usd = attempt_cost(r, b, pri, ctx_tokens)["usd"] - pri["cost"]["startup_tokens"].get(agent, 0)         * (pri["cost"]["turns_base"] + pri["cost"]["turns_per_b"] * b) * price["cached"] / 1e6 + persist(ctx_tokens) \
        + lead_rereads(pri, price, b, lead_ctx, "self")
    p_self = p_success(r["theta"] + offset(state, pri, lead), b, pri["irt"]["a"])
    # the lead checks its own work and can redo it once: expected 1 + (1 - p) attempts, a wrong result left only
    # when both tries fail
    self_total = (self_usd * lam + attempt_minutes(r, b, pri, state) * vot) * (2 - p_self)         + (1 - p_self) ** 2 * fail_cost
    options = [{"way": "self", "rung": lead, "usd": round(self_usd, 4), "p": round(p_self, 3), "agent": agent,
                "total": round(self_total, 4)}]
    blocked = [n for n in needs if n in NEEDS_DELEGATE]
    q2 = {**quota, f"{agent}-builtin": quota.get(agent)}   # built-in sub-agents spend the lead's quota
    if not blocked:
        bpri = {**pri, "rungs": pri["rungs"] + builtin_rungs(pri, lead)}
        try:
            # one attempt: ccx cannot escalate a sub-agent it does not run
            pick = route(b, bpri, state, [f"{agent}-builtin"], tradeoff=tradeoff, max_escalations=0, quota=q2,
                         risk=risk)["pick"]
            options.append({"way": "builtin", "rung": pick["rung"], "usd": round(pick["expected_usd"] + overhead, 4),
                            "p": round(pick["chain_success"], 3), "agent": agent,
                            "total": round(pick["total"]["sum"] + overhead * lam, 4)})
        except ValueError:
            pass
    try:
        pick = route(b, pri, state, delegate_agents, tradeoff=tradeoff, quota=quota, risk=risk)["pick"]
        options.append({"way": "delegate", "rung": pick["rung"], "usd": round(pick["expected_usd"] + overhead, 4),
                        "p": round(pick["chain_success"], 3), "agent": pick["agent"],
                        "total": round(pick["total"]["sum"] + overhead * lam, 4),
                        "money": pick["total"]["money"]})
    except ValueError:
        pass
    usable = [o for o in options if o["way"] == "self" or o["p"] >= 0.6]
    own = options[0]
    best = min(usable, key=lambda o: o["total"])
    if best is not own and best["total"] >= 0.85 * own["total"]:
        best = own                                                 # within the 15% noise margin: stay
    why = {"self": "doing it yourself is cheapest or within the 15% margin",
           "builtin": "your own sub-agent is cheapest and likely to succeed",
           "delegate": "delegating through ccx is cheapest and likely to succeed"}[best["way"]]
    if blocked:
        why += f"; built-in sub-agent ruled out (needs: {', '.join(blocked)})"
    used = {a: q for a, q in quota.items() if q is not None and not a.endswith("-builtin")}
    if used:
        why += "; quota priced at " + ", ".join(f"{a} {shadow_lambda(q, pri):.0%} of API ({q:.0%} used)"
                                                for a, q in sorted(used.items()))
    return {"recommend": best["way"], "rung": best["rung"], "why": why, "options": options,
            "value_of_time_per_min": vot, "failure_cost": fail_cost}


def record(rung: str, b: float, ok: bool, pri: dict, state: dict, cost_usd: float | None = None,
           seconds: float | None = None) -> dict:
    pri = with_benchmarks(pri, "code")     # offsets are learned on top of the benchmark-informed base
    decay(state, pri)
    if seconds:                            # measured wall time per attempt feeds the time part of the total cost
        mins = state.setdefault("minutes", {})
        mins[rung] = round(0.7 * mins[rung] + 0.3 * seconds / 60, 2) if rung in mins else round(seconds / 60, 2)
    r = next((x for x in pri["rungs"] if rung_key(x) == rung), None)
    base = r["theta"] if r else 5.0
    off = offset(state, pri, rung)
    p = p_success(base + off, b, pri["irt"]["a"])
    off += pri["irt"]["learning_rate"] * ((1.0 if ok else 0.0) - p)
    state["offsets"][rung] = off
    state["counts"][rung] = state["counts"].get(rung, 0) + 1
    if cost_usd is not None and r is not None:
        est = attempt_cost(r, b, pri)["usd"]           # uncorrected model estimate
        if est > 0:
            ratio = max(0.05, min(20.0, cost_usd / est))
            old = state.setdefault("cost_factor", {}).get(rung, 1.0)
            state["cost_factor"][rung] = round(0.7 * old + 0.3 * ratio, 4)   # EMA: follows reality, damps noise
    state.setdefault("outcomes", []).append({"ts": time.time(), "rung": rung, "b": b, "ok": ok,
                                             "p": round(p, 3), "cost_usd": cost_usd})
    return {"rung": rung, "predicted_p": round(p, 3), "outcome": ok, "theta_now": round(base + off, 2)}


# ------------------------------------------------------------------ CLI
def _fmt(res: dict) -> str:
    lines = [f"difficulty b={res['b']}  tradeoff={res['tradeoff']} (tau={res['tau']})", res["rule"], "",
             f"{'rung':34} {'theta':>5} {'P':>5} {'$/try':>8} {'chainP':>6} {'$/success':>9}"]
    for x in res["rows"]:
        mark = " <-" if x["rung"] == res["pick"]["rung"] else ""
        lines.append(f"{x['rung']:34} {x['theta']:>5} {x['p']:>5.2f} {x['cost']['usd']:>8.4f} "
                     f"{x['chain_success']:>6.2f} {x['cps']:>9.4f}{mark}")
    if res.get("advice"):
        lines.append("\nADVICE: " + res["advice"])
    if res.get("new_models_without_prior"):
        lines.append("\nnew models with no prior (add to priors.toml): " + ", ".join(res["new_models_without_prior"]))
    if res.get("self_vs_delegate"):
        s = res["self_vs_delegate"]
        lines.append(f"\nself ${s.get('self_usd')} vs delegate ${s.get('delegate_usd')} -> {s.get('recommend')}: {s.get('why')}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="task_routing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route")
    r.add_argument("--files", type=int, default=1)
    for k in ("coupling", "clarity", "risk", "novelty"):
        r.add_argument(f"--{k}", choices=list(POINTS[k]))
    r.add_argument("--minutes", type=float, help="how long a skilled engineer would need (the standard unit)")
    r.add_argument("--lead-name", help="who estimated (its learned bias is applied)")
    r.add_argument("--agents", default="codex,claude")
    r.add_argument("--tradeoff", default="balanced", help="save | balanced | fast, or a knob 0..1")
    r.add_argument("--not-verifiable", action="store_true")
    r.add_argument("--ctx-tokens", type=int, default=0, help="tokens of files/logs the task needs to read")
    r.add_argument("--lead", help="agent:model:effort of the lead, to compare self vs delegate")
    r.add_argument("--remaining-turns", type=int, default=10)
    r.add_argument("--lead-ctx", type=int, default=0,
                   help="tokens your own conversation re-reads each request (its size now); each turn you spend costs that")
    r.add_argument("--explain", action="store_true", help="human-readable table instead of JSON")
    r.add_argument("--kind", choices=KINDS, default="code",
                   help="kind of work; decides which public benchmarks count (see references/method.md 10)")
    rec = sub.add_parser("record")
    rec.add_argument("--rung", required=True)
    rec.add_argument("--b", type=float, required=True)
    rec.add_argument("--ok", type=int, choices=[0, 1], required=True)
    rec.add_argument("--cost-usd", type=float)
    sub.add_parser("show")
    sub.add_parser("rubric")
    sub.add_parser("refit", help="suggest rubric weights from recorded outcomes (advice only)")
    rf = sub.add_parser("refresh", help="fetch public benchmark data (Epoch AI, LMArena, models.dev) into the cache")
    rf.add_argument("--if-stale", action="store_true", help="only when the cache is a week old or missing")
    sub.add_parser("sources", help="where the benchmark data came from, how old it is, and the credits")
    a = ap.parse_args(argv)
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page
        except Exception:  # noqa: BLE001
            pass

    if a.cmd == "refresh":
        b = bench()
        if a.if_stale and not b.is_stale(bench_path()):
            print(json.dumps({"skipped": "fresh", "age_days": round(b.age_days(bench_path()), 2)}))
            return 0
        print(json.dumps(b.refresh(bench_path(), plugin_dirs=bench_plugin_dirs()), indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "sources":
        b = bench()
        d = b.load(bench_path())
        print(json.dumps({"cache": str(bench_path()), "age_days": b.age_days(bench_path()), **b.summary(d)}
                         if d else {"cache": str(bench_path()), "empty": "run: task_routing.py refresh"},
                         indent=2, ensure_ascii=False))
        return 0
    pri = load_priors()
    state = load_state()
    if a.cmd == "refit":
        print(json.dumps(refit(state), indent=2))
        return 0
    if a.cmd == "rubric":
        print(json.dumps(RUBRIC, indent=2))
        return 0
    if a.cmd == "show":
        print(json.dumps({"state_file": str(state_path()), "theta_offsets": state["offsets"],
                          "cost_factor": state.get("cost_factor", {}), "counts": state["counts"],
                          "outcomes": len(state.get("outcomes", []))}, indent=2))
        return 0
    if a.cmd == "record":
        with _Lock(state_path()):
            state = load_state()            # re-read under the lock: the other agent may have written
            out = record(a.rung, a.b, bool(a.ok), pri, state, a.cost_usd)
            save_state(state)
        print(json.dumps(out))
        return 0
    items = [a.coupling, a.clarity, a.risk, a.novelty]
    b_rub = (difficulty(a.files, a.coupling or "one", a.clarity or "goal", a.risk or "low", a.novelty or "pattern")
             if any(items) else None)
    if b_rub is None and not a.minutes:
        ap.error("route needs the rubric (--coupling --clarity --risk --novelty) and/or --minutes")
    diff = combine_difficulty(b_rub, a.minutes, lead_bias(state, a.lead_name))
    b = diff["b"]
    res = route(b, pri, state, [x.strip() for x in a.agents.split(",") if x.strip()],
                a.tradeoff, not a.not_verifiable, a.ctx_tokens, kind=a.kind)
    if a.lead:
        res["self_vs_delegate"] = self_vs_delegate(b, pri, state, a.lead, res["pick"], a.ctx_tokens,
                                                   a.remaining_turns, a.lead_ctx)
    if a.explain:
        print(_fmt(res))
    else:
        p = res["pick"]
        out = {"b": b, "difficulty": diff["parts"], "pick": p["rung"], "pick_h50_minutes": p.get("h50_minutes"),
               "p_first_try": round(p["p"], 2),
               "p_with_escalation": round(p["chain_success"], 2), "usd_per_success": round(p["cps"], 4),
               "escalates_to": p["escalates_to"], "rule": res["rule"]}
        if res.get("advice"):
            out["advice"] = res["advice"]
        if res.get("stale"):
            out["stale"] = res["stale"]
        out["calibration"] = {"outcomes_for_pick": p["n"], "cost_calibrated": p["cost"]["calibrated"]}
        if res.get("self_vs_delegate"):
            out["self_vs_delegate"] = res["self_vs_delegate"]
        if res["new_models_without_prior"]:
            out["new_models_without_prior"] = res["new_models_without_prior"]
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
