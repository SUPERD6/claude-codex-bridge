"""A formal comparison over a week (proposal H11): of the delegable tasks that come up, about half the lead does
itself and half go out through ccx, balanced by kind of work and difficulty, and both halves are measured the same
way — the lead's own tokens and spend in the task's window, the sub-agent's spend, wall time, and whether the work
held up. The everyday A/B sampling (`defaults.ab_self_rate`, ~10 %) stays as it is; a trial only raises the share
for its days and makes the halves comparable.

Windows: a self-run is measured from the moment ccx said "do this one yourself" to `ccx ab done`; a delegated run
from its start to its end plus TAIL_S for the lead reading and checking the result. Both count only the lead
conversation the task belongs to when it is known.

A third half, "native": Claude Code doing the task with its own built-in helpers or a dynamic workflow
(ultracode). ccx does not see those, so the person tags the conversation afterwards (`ccx trial tag --arm native
--session ID`), and its whole spend — the conversation plus every helper and workflow agent it started — is read
from that conversation's own files. The report compares each half with the lead doing it itself only within the
same kind of work and difficulty, weighted by how many tasks each bucket has."""
from __future__ import annotations

import json
import random
import time

from .config import Paths

ARMS = ("self", "delegated", "native")
TAIL_S = 600              # the lead reads and checks a delegated result in about this long after it returns
MIN_PER_ARM = 10          # below this, the numbers are shown but not called a result


def _file(p: Paths):
    return p.state / "trial.json"


def active(p: Paths, now: float | None = None) -> dict | None:
    try:
        t = json.loads(_file(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    now = now or time.time()
    return t if t.get("stopped") is None and now < float(t["end"]) else None


def start(p: Paths, days: float = 7.0, rate: float = 0.5, note: str = "") -> dict:
    if not 0 < rate < 1:
        raise ValueError("--rate must be between 0 and 1")
    t = {"id": time.strftime("trial-%Y%m%d-%H%M%S"), "start": time.time(), "end": time.time() + days * 86400,
         "rate": rate, "note": note, "stopped": None}
    old = active(p)
    if old:
        raise ValueError(f"a trial is already running ({old['id']}); `ccx trial stop` first")
    _file(p).parent.mkdir(parents=True, exist_ok=True)
    _file(p).write_text(json.dumps(t), encoding="utf-8")
    return t


def stop(p: Paths) -> dict:
    t = active(p)
    if not t:
        return {"stopped": None, "note": "no trial running"}
    t["stopped"] = time.time()
    _file(p).write_text(json.dumps(t), encoding="utf-8")
    return t


def bucket(kind: str | None, b: float | None) -> str:
    return f"{kind or 'any'}:b{round(b) if b is not None else '?'}"


def _counts(p: Paths, t: dict) -> dict[str, dict[str, int]]:
    from . import ledger
    out: dict[str, dict[str, int]] = {}
    for r in ledger.rows(p):
        if r.get("type") not in (None, "selfrun") or r.get("trial") != t["id"]:
            continue
        arm = "self" if r.get("type") == "selfrun" else "delegated"
        c = out.setdefault(r.get("bucket") or bucket(r.get("kind"), r.get("b")), {"self": 0, "delegated": 0})
        c[arm] += 1
    for f in (p.state / "ab").glob("*.json") if (p.state / "ab").exists() else ():   # still-open self-runs
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if s.get("trial") == t["id"]:
            out.setdefault(s.get("bucket", "?"), {"self": 0, "delegated": 0})["self"] += 1
    return out


def assign(p: Paths, t: dict, kind: str | None, b: float | None, rng=random) -> str:
    """'self' or 'delegated' for the next task of this kind and difficulty: the half that is behind the chosen
    split gets it; a draw at the rate only when the bucket is exactly on it (e.g. its first task)."""
    c = _counts(p, t).get(bucket(kind, b), {"self": 0, "delegated": 0})
    n = c["self"] + c["delegated"]
    if n and abs(c["self"] - t["rate"] * n) > 1e-9:
        return "self" if c["self"] < t["rate"] * n else "delegated"
    return "self" if rng.random() < t["rate"] else "delegated"


def _lead(p: Paths, agent: str, start_ts: float, end_ts: float, session: str | None, subs: set[str]) -> dict:
    from . import learn, usage
    evs = usage.claude_events(start_ts, subs) if agent == "claude" else usage.codex_events(start_ts, subs)[0]
    tok, usd, n = 0, 0.0, 0
    from .context import turn_tokens
    for e in evs:
        if not start_ts <= e["ts"] <= end_ts:
            continue
        if session and session not in (e.get("session"), e.get("parent")):
            continue                       # this conversation and its own built-in helpers only
        tok += turn_tokens(e["usage"]) + int(e["usage"].get("output_tokens", 0) or 0)
        usd += learn.price_usd(p, agent, e.get("model") or "", e["usage"]) or 0.0
        n += 1
    return {"tokens": tok, "usd": round(usd, 6), "turns": n}


def samples(p: Paths, t: dict, now: float | None = None) -> list[dict]:
    """One row per task in the trial, both halves measured the same way."""
    from . import ledger
    now = now or time.time()
    rows = ledger.rows(p)
    subs = {s for r in rows if not r.get("type") for s in r.get("sessions", [])}
    verdicts = {r["run_id"]: r for r in rows if r.get("type") == "verify"}        # the last one wins
    out = []
    for r in rows:
        if r.get("type") == "selfrun" and r.get("trial") == t["id"]:
            u = r.get("usage4") or {}
            from .context import turn_tokens
            out.append({"arm": "self", "bucket": r.get("bucket") or bucket(r.get("kind"), r.get("b")),
                        "lead_tokens": turn_tokens(u) + int(u.get("output_tokens", 0) or 0),
                        "lead_usd": r.get("ae_usd") or 0.0, "sub_usd": 0.0,
                        "minutes": round((r.get("seconds") or 0) / 60, 1), "ok": bool(r.get("ok")),
                        "judged": "lead", "agent": r.get("agent")})
        elif not r.get("type") and r.get("trial") == t["id"]:
            end_ts = float(r["ts"]) + float(r.get("seconds") or 0) + TAIL_S
            lead = _lead(p, r.get("caller") or "claude", float(r["ts"]), min(end_ts, now),
                         r.get("lead_session"), subs)
            v = verdicts.get(r["run_id"])
            ok = v["ok"] if v else (r.get("status") == "done")
            out.append({"arm": "delegated", "bucket": r.get("bucket") or bucket(r.get("kind"), r.get("b")),
                        "lead_tokens": lead["tokens"], "lead_usd": lead["usd"], "sub_usd": r.get("ae_usd") or 0.0,
                        "minutes": round((end_ts - TAIL_S - float(r["ts"])) / 60, 1), "ok": bool(ok),
                        "judged": ("soft" if v.get("soft") else "lead") if v else "none",
                        "agent": r.get("caller"), "run_id": r["run_id"]})
        elif r.get("type") == "trialtag" and r.get("trial") == t["id"]:
            out.append({k: r.get(k) for k in ("arm", "bucket", "lead_tokens", "lead_usd", "sub_usd", "minutes",
                                              "agent", "session")}
                       | {"ok": bool(r.get("ok")), "judged": "none" if r.get("ok") is None else "lead"})
    return out


def session_cost(p: Paths, session: str, since: float | None = None, until: float | None = None,
                 home=None) -> dict:
    """Everything one Claude conversation spent in a window: its own turns and every built-in helper or
    workflow agent it started."""
    from . import learn, usage
    from .context import turn_tokens
    evs = [e for e in usage.claude_session_events(session, home)
           if (since is None or e["ts"] >= since) and (until is None or e["ts"] <= until)]
    if not evs:
        raise ValueError(f"no Claude turns found for session {session!r} in that window")
    c = {"lead_tokens": 0, "lead_usd": 0.0, "sub_tokens": 0, "sub_usd": 0.0, "turns": 0, "helper_turns": 0}
    helpers, workflows = set(), set()
    for e in evs:
        tok = turn_tokens(e["usage"]) + int(e["usage"].get("output_tokens", 0) or 0)
        usd = learn.price_usd(p, "claude", e.get("model") or "", e["usage"]) or 0.0
        side = "sub" if e.get("role") == "builtin" else "lead"
        c[f"{side}_tokens"] += tok
        c[f"{side}_usd"] += usd
        c["helper_turns" if side == "sub" else "turns"] += 1
        if side == "sub":
            helpers.add(e["session"])
            if e.get("workflow"):
                workflows.add(e["workflow"])
    ts = [e["ts"] for e in evs]
    return {**c, "lead_usd": round(c["lead_usd"], 6), "sub_usd": round(c["sub_usd"], 6),
            "helpers": len(helpers), "workflows": len(workflows), "first": min(ts), "last": max(ts),
            "minutes": round((max(ts) - min(ts)) / 60, 1)}


def tag(p: Paths, session: str, arm: str = "native", kind: str | None = None, b: float | None = None,
        ok: bool | None = None, since: float | None = None, until: float | None = None, note: str = "",
        home=None) -> dict:
    """Count one task done outside ccx's own assignment — Claude Code's built-in helpers or a workflow
    (native), or the lead on its own (self) — into the running trial (the last one when none is running)."""
    from . import ledger
    if arm not in ("native", "self"):
        raise ValueError("--arm must be native or self (delegated runs are counted by ccx itself)")
    t = active(p) or _last(p)
    if not t:
        raise ValueError("no trial yet: `ccx trial start` first")
    if any(r.get("type") == "trialtag" and r.get("trial") == t["id"] and r.get("session") == session
           and r.get("since") == since for r in ledger.rows(p)):
        raise ValueError(f"session {session} is already tagged in {t['id']}")
    c = session_cost(p, session, since, until, home)
    row = {"type": "trialtag", "ts": time.time(), "trial": t["id"], "arm": arm, "session": session,
           "agent": "claude", "kind": kind, "b": b, "bucket": bucket(kind, b), "ok": ok,
           "since": since, "until": until, "note": note, **c}
    ledger.append_event(p, row)
    return row


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 5) if xs else None


def summarize(p: Paths, t: dict | None = None) -> dict:
    t = t or active(p) or _last(p)
    if not t:
        return {"trial": None, "note": "no trial yet: `ccx trial start` (7 days, half the delegable tasks done "
                                       "by the lead itself)"}
    ss = samples(p, t)
    arms = {}
    for arm in ARMS:
        xs = [s for s in ss if s["arm"] == arm]
        total = [s["lead_usd"] + s["sub_usd"] for s in xs]
        judged = [s for s in xs if s["judged"] != "none"]        # unjudged runs don't count as having held up
        arms[arm] = {"n": len(xs), "ok_rate": round(sum(s["ok"] for s in judged) / len(judged), 3) if judged else None,
                     "rework": sum(not s["ok"] for s in judged), "unjudged": len(xs) - len(judged),
                     "lead_tokens_mean": _mean([s["lead_tokens"] for s in xs]),
                     "lead_usd_mean": _mean([s["lead_usd"] for s in xs]),
                     "sub_usd_mean": _mean([s["sub_usd"] for s in xs]),
                     "total_usd_mean": _mean(total), "minutes_mean": _mean([s["minutes"] for s in xs]),
                     "judged_by_lead": sum(s["judged"] == "lead" for s in xs)}
    compare = {arm: balanced(ss, arm) for arm in ("delegated", "native")}
    d = compare["delegated"]
    res = {"trial": {k: t[k] for k in ("id", "start", "end", "rate", "note", "stopped")},
           "running": active(p) is not None, "arms": arms, "compare": compare,
           "saving_per_task_usd": d["saving_per_task_usd"], "saving_ci95": d["saving_ci95"], "enough": d["enough"],
           "buckets": sorted({s["bucket"] for s in ss})}
    if not d["enough"]:
        res["note"] = d["note"]
    return res


def balanced(ss: list[dict], arm: str, base: str = "self", n: int = 2000, seed: int = 11) -> dict:
    """What `arm` saves per task against the lead doing it itself (base $ minus arm $, so positive = cheaper),
    compared only within a bucket (kind of work x difficulty) both halves have, weighted by the bucket's task
    count; 95 % interval by resampling within each bucket."""
    by: dict[str, tuple[list[float], list[float]]] = {}
    for s in ss:
        if s["arm"] in (arm, base):
            by.setdefault(s["bucket"], ([], []))[0 if s["arm"] == base else 1].append(s["lead_usd"] + s["sub_usd"])
    matched = {k: v for k, v in by.items() if v[0] and v[1]}
    nb = sum(len(v[0]) for v in matched.values())
    na = sum(len(v[1]) for v in matched.values())
    out = {"arm": arm, "base": base, "buckets": sorted(matched), "n_base": nb, "n_arm": na,
           "left_out": sum(len(v[0]) + len(v[1]) for k, v in by.items() if k not in matched),
           "saving_per_task_usd": None, "saving_ci95": None, "enough": min(na, nb) >= MIN_PER_ARM}

    def est(groups):
        w = sum(len(x) + len(y) for x, y in groups)
        return sum((len(x) + len(y)) * (sum(x) / len(x) - sum(y) / len(y)) for x, y in groups) / w
    if matched:
        groups = list(matched.values())
        out["saving_per_task_usd"] = round(est(groups), 5)
        if na >= 3 and nb >= 3:
            rng = random.Random(seed)
            ds = sorted(est([([rng.choice(x) for _ in x], [rng.choice(y) for _ in y]) for x, y in groups])
                        for _ in range(n))
            out["saving_ci95"] = [round(ds[int(0.025 * n)], 5), round(ds[int(0.975 * n)], 5)]
    if not out["enough"]:
        out["note"] = (f"deferred, no conclusion: fewer than {MIN_PER_ARM} tasks in a half within matching "
                       f"buckets ({nb} {base}, {na} {arm})")
    return out


def _last(p: Paths) -> dict | None:
    try:
        return json.loads(_file(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def markdown(s: dict) -> str:
    """The table for the README once the week is over."""
    if not s.get("trial"):
        return ""
    arms = [s["arms"][k] for k in ARMS if k in s["arms"]]
    def f(v, kind="usd"):
        if v is None:
            return "–"
        return f"${v:.4f}" if kind == "usd" else (f"{v:,.0f}" if kind == "n" else f"{v:.0%}" if kind == "%" else
                                                   f"{v:.1f}")
    rows = [("Tasks", "n", "n"), ("Lead tokens per task", "lead_tokens_mean", "n"),
            ("Lead spend per task", "lead_usd_mean", "usd"), ("Sub-agent spend per task", "sub_usd_mean", "usd"),
            ("Total per task", "total_usd_mean", "usd"), ("Minutes per task", "minutes_mean", "m"),
            ("Held up (no rework)", "ok_rate", "%")]
    t = s["trial"]
    head = (f"Trial {t['id']} ({time.strftime('%Y-%m-%d', time.localtime(t['start']))} – "
            f"{time.strftime('%Y-%m-%d', time.localtime(t.get('stopped') or t['end']))}), API-equivalent dollars.")
    names = ["Lead did it itself", "Delegated with ccx", "Claude Code's own helpers / workflow"][:len(arms)]
    lines = [head, "", "| | " + " | ".join(names) + " |", "|---|" + "---:|" * len(arms)]
    lines += [f"| {name} | " + " | ".join(f(x[key], k) for x in arms) + " |" for name, key, k in rows]
    for arm, label in (("delegated", "Delegated with ccx"), ("native", "Claude Code's own helpers / workflow")):
        c = (s.get("compare") or {}).get(arm)
        if not c or not s["arms"].get(arm, {}).get("n"):
            continue
        ci = c.get("saving_ci95")
        lines += ["", f"{label} vs the lead itself, same kind and difficulty ({c['n_base']} vs {c['n_arm']} tasks): "
                  + ("saving per task " + f(c["saving_per_task_usd"]) if c["saving_per_task_usd"] is not None else "")
                  + (f" (95 % interval {f(ci[0])} to {f(ci[1])})" if ci else "")
                  + ("" if c["enough"] else f" — {c['note']}")]
    return "\n".join(lines)
