"""Ways of working by risk (proposal H8) and who is good at what (H9).

H8 — three ways, picked by how costly a wrong result is:
  solo          ordinary work: one agent does it; another vendor reviews when it is worth it (F1, `--review auto`)
  plan_build    visible or important work: one vendor plans, another builds, the planner accepts it (one fix round)
  two_versions  the most critical work: two vendors each build a version in their own worktree, a third (or the
                planner's vendor) compares them and picks; about twice the cost, so only after the person says yes

H9 — from finished runs: per kind of work (code / read / research / write) and per agent, how often a piece was
right the first time (judged right, no follow-up, no review fix) and how often it needed rework (a follow-up, a
review fix, or judged wrong). Only judged pieces count. These rates order who builds, and a low first-time rate
moves a piece one way up (solo -> plan_build). Each agent's rates are also kept per tier (model:effort), so a cheap
tier's misses are seen apart from the strong one's; evaluation runs (ledger.is_eval) are left out unless asked."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Paths

WAYS = ("solo", "plan_build", "two_versions")
BY_RISK = {"low": "solo", "visible": "plan_build", "critical": "two_versions"}
MIN_JUDGED = 5            # below this many judged pieces a rate is shown but does not steer anything
LOW_FIRST_RIGHT = 0.5     # a builder right the first time less often than this gets a planner on its side
INTERNAL = ("review:", "discuss:", "way:", "quota-probe", "selftest", "handoff-from-transcript")

PLAN = """[ccx way {wid}: plan] You plan, another agent builds, and afterwards you accept or reject its change.
Do not edit anything; read what you need.

## Task
{task}

## Answer
summary: the approach in at most 100 words. open_questions: the plan as items, each starting with `[step] ` (at
most 8, in order, naming files) and then `[accept] ` items: what you will check to accept the change (at most 4)."""

BUILD = """{task}

## Plan from {planner} (follow it; where you depart from it, say so and why in open_questions)
{plan}"""

PICK = """[ccx way {wid}: pick] Two agents each built a version of the same task in their own worktree. Compare them
and pick the better one. Do not edit anything.

## Task
{task}

## Version A ({a}): {a_sum}
```diff
{a_diff}
```

## Version B ({b}): {b_sum}
```diff
{b_diff}
```

## Checks
{checks}

## Answer
Start summary with exactly `PICK: A` or `PICK: B`, then one sentence why. open_questions: `[reason] ...` (at most 4)
and `[take] ...` for anything worth taking over from the other version (at most 2). Status done."""


# ------------------------------------------------------------------ H9: who is good at what

def _records(p: Paths, since: float) -> list[dict]:
    out = []
    if p.runs.exists():
        for d in p.runs.iterdir():
            f = d / "run.json"
            try:
                if f.stat().st_mtime < since:
                    continue
                r = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(r, dict) and r.get("run_id") and r.get("state") != "running":
                out.append(r)
    return out


def _verdicts(p: Paths) -> dict[str, dict]:
    from . import ledger
    v: dict[str, dict] = {}
    for r in ledger.rows(p):
        if r.get("type") == "verify" and r.get("run_id"):
            if r.get("soft") and v.get(r["run_id"]) and not v[r["run_id"]].get("soft"):
                continue                      # the person's verdict wins over a probable one
            v[r["run_id"]] = r
    return v


def _tier(r: dict) -> str:
    """model:effort of the attempt that finished the piece (its last rung)."""
    rungs = [a.get("rung") for a in r.get("attempts") or [] if a.get("rung")]
    return rungs[-1].split(":", 1)[1] if rungs and ":" in rungs[-1] else "?"


def pieces(p: Paths, days: float = 90, include_evals: bool = False) -> list[dict]:
    """One row per piece of work (a run that is not a follow-up of another): agent, tier, kind, judged,
    first_right, rework. Evaluation runs (ledger.is_eval) only with include_evals."""
    from .ledger import is_eval
    from .learn import task_kind
    recs = [r for r in _records(p, time.time() - days * 86400)
            if not r.get("ephemeral") and not str(r.get("label") or "").startswith(INTERNAL)
            and (include_evals or not is_eval({"label": r.get("label"), "no_ab": (r.get("route") or {}).get("no_ab"),
                                                    "dismissed": r.get("dismissed")}))]
    by_id = {r["run_id"]: r for r in recs}
    follow: dict[str, int] = {}
    for r in recs:
        base = r.get("review_of") or (r.get("resumed_from") if not r.get("continued") else None)
        seen = set()
        while base in by_id and base not in seen:       # walk up to the head of the chain
            seen.add(base)
            nxt = by_id[base].get("review_of") or (by_id[base].get("resumed_from")
                                                  if not by_id[base].get("continued") else None)
            if nxt not in by_id:
                break
            base = nxt
        if base:
            follow[base] = follow.get(base, 0) + 1
    verdicts = _verdicts(p)
    out = []
    for r in recs:
        if r.get("review_of") or (r.get("resumed_from") and not r.get("continued")):
            continue
        chain = [r["run_id"]] + [x["run_id"] for x in recs
                                 if x.get("review_of") == r["run_id"] or x.get("resumed_from") == r["run_id"]]
        v = next((verdicts[x] for x in reversed(chain) if x in verdicts), None)
        n_follow = follow.get(r["run_id"], 0)
        review_fix = (r.get("review") or {}).get("verdict") == "issues"
        row = {"run_id": r["run_id"], "agent": r.get("provider") or r.get("to"), "tier": _tier(r),
               "kind": (r.get("route") or {}).get("kind") or task_kind(r.get("mode")),
               "judged": v is not None, "follow_ups": n_follow, "ts": r.get("ts"),
               "p": (r.get("route") or {}).get("p"), "attempts": len(r.get("attempts") or [])}
        if v is not None:
            row["ok"] = bool(v.get("ok"))
            first_v = verdicts.get(r["run_id"])
            row["first_right"] = bool(first_v and first_v.get("ok")) and not n_follow and not review_fix
            row["rework"] = bool(n_follow or review_fix or not v.get("ok"))
        out.append(row)
    return out


def _new() -> dict:
    return {"pieces": 0, "judged": 0, "right": 0, "redo": 0}


def _add(s: dict, x: dict) -> None:
    s["pieces"] += 1
    if x["judged"]:
        s["judged"] += 1
        s["right"] += x["first_right"]
        s["redo"] += x["rework"]


def _rates(s: dict) -> dict:
    n = s["judged"]
    s["first_right"] = round(s["right"] / n, 3) if n else None
    s["rework"] = round(s["redo"] / n, 3) if n else None
    s["enough"] = n >= MIN_JUDGED
    del s["right"], s["redo"]
    return s


def track(p: Paths, days: float = 90, include_evals: bool = False) -> dict[str, dict[str, dict]]:
    """kind -> agent -> {judged, first_right, rework, pieces, tiers: {model:effort -> the same}}: rates over judged
    pieces only. The agent's own rates order who builds; `tiers` shows which of its tiers they come from."""
    out: dict[str, dict[str, dict]] = {}
    for x in pieces(p, days, include_evals):
        s = out.setdefault(x["kind"], {}).setdefault(x["agent"], {**_new(), "tiers": {}})
        _add(s, x)
        _add(s["tiers"].setdefault(x["tier"], _new()), x)
    for agents in out.values():
        for s in agents.values():
            _rates(s)
            for t in s["tiers"].values():
                _rates(t)
    return out


def _score(s: dict | None) -> float:
    """First-time-right, smoothed toward 1/2 so a 1-for-1 agent does not beat a 9-for-10 one."""
    if not s or not s.get("judged"):
        return 0.5
    return (s["first_right"] * s["judged"] + 1) / (s["judged"] + 2)


# ------------------------------------------------------------------ H8: which way

def choose(risk: str, kind: str, stats: dict, candidates: list[str], cfg: dict | None = None) -> dict:
    """The way and who does what. candidates: installed agents, preferred first."""
    from .agents import same_vendor
    if not candidates:
        raise ValueError("no agent installed to do the work")
    way = BY_RISK.get(risk or "low", "solo")
    why = [f"risk {risk or 'low'} -> {way}"]
    ks = stats.get(kind) or {}
    order = sorted(candidates, key=lambda a: (-_score(ks.get(a)) if (ks.get(a) or {}).get("enough") else -0.5,
                                              candidates.index(a)))
    builder = order[0]
    bs = ks.get(builder)
    if bs and bs.get("enough"):
        why.append(f"{builder} was right the first time in {bs['first_right']:.0%} of {bs['judged']} judged "
                   f"{kind} pieces")
        if way == "solo" and bs["first_right"] < LOW_FIRST_RIGHT:
            way = "plan_build"
            why.append(f"below {LOW_FIRST_RIGHT:.0%}: a planner from another vendor checks it")
    others = [a for a in order if not same_vendor(a, builder, cfg)]
    if way != "solo" and not others:
        why.append("only one vendor installed: falls back to solo with review")
        way = "solo"
    roles = {"builder": builder}
    if way == "plan_build":
        roles["planner"] = others[0]
    elif way == "two_versions":
        roles["second"] = others[0]
        third = [a for a in others[1:] if not same_vendor(a, others[0], cfg)]
        roles["judge"] = third[0] if third else others[0]
        if not third:
            why.append("no third vendor: the second builder's vendor also compares (a fresh run, not its own session)")
    return {"way": way, "roles": roles, "why": why, "needs_yes": way == "two_versions"}


# ------------------------------------------------------------------ running a way

def _usd(rec: dict) -> float:
    return sum(a.get("ae_usd") or 0 for a in rec.get("attempts") or [])


def _diff(p: Paths, rec: dict) -> str:
    from .review import changes
    f = p.runs / rec["run_id"] / "undo.json"
    snap = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return changes(Path(rec.get("cwd") or "."), snap)[1]


def run(p: Paths, brief: str, choice: dict, *, cwd: Path, check: str | None = None, caller: str = "unknown",
        risk: str = "low", kind: str | None = None, yes: bool = False, runner=None, max_diff: int = 12000,
        label: str = "") -> dict:
    """Carry out the chosen way. `runner(**request fields) -> run record` is delegate.run (tests pass a fake).
    `label` goes on the build runs (e.g. eval-... so H9 and probable verdicts leave an evaluation out)."""
    import uuid
    from . import review
    if runner is None:
        from .delegate import Request, run as delegate_run

        def runner(**kw):
            return delegate_run(Request(**kw), p)
    way, roles = choice["way"], choice["roles"]
    if choice.get("needs_yes") and not yes:
        raise ValueError("two_versions costs about twice as much: ask the person, then run again with --yes")
    wid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    out = {"way": way, "roles": roles, "id": wid, "why": choice.get("why"), "steps": []}
    common = dict(cwd=cwd, caller=caller, route={"kind": kind or "code", "way": way})   # H9 counts by kind

    def step(name: str, rec: dict) -> dict:
        out["steps"].append({"step": name, "run_id": rec.get("run_id"), "agent": rec.get("to"),
                             "ok": rec.get("ok"), "status": (rec.get("result") or {}).get("status"),
                             "usd": round(_usd(rec), 6)})
        return rec

    if way == "solo":
        rec = step("build", runner(to=roles["builder"], brief=brief, mode="write", check=check, risk=risk, label=label,
                                   **common))
        out.update(result=_brief_result(rec), run_id=rec["run_id"])
    elif way == "plan_build":
        plan = step("plan", runner(to=roles["planner"], brief=PLAN.format(wid=wid, task=brief), mode="read",
                                   review="off", allow_subagents=False, fallback=False, label=f"way:{wid}:plan",
                                   **common))
        res = plan.get("result") or {}
        if not plan.get("ok") or res.get("status") != "done":
            out.update(state="failed", error=f"the planner ({roles['planner']}) did not finish")
            return _done(p, out)
        items = [str(x) for x in res.get("open_questions") or []]
        plan_text = (res.get("summary") or "") + "\n" + "\n".join(f"- {x}" for x in items)
        out["plan"] = {"summary": res.get("summary"), "items": items[:12]}
        build = step("build", runner(to=roles["builder"], brief=BUILD.format(task=brief, planner=roles["planner"],
                                                                             plan=plan_text),
                                     mode="write", check=check, review="off", label=label, **common))
        for rnd in (0, 1):
            diff = _diff(p, build)
            acc_brief = review.brief(build["run_id"], brief + "\n\n## The plan it was given\n" + plan_text,
                                     (build.get("result") or {}).get("summary", ""), diff, max_diff,
                                     build.get("check"))
            acc = step("accept", runner(to=roles["planner"], brief=acc_brief, mode="read", review="off",
                                        allow_subagents=False, fallback=False, ephemeral=True,
                                        label=f"review:{build['run_id']}", **common))
            v = review.verdict(acc.get("result")) if acc.get("ok") else {"verdict": "not-run", "issues": []}
            out["acceptance"] = {**v, "by": roles["planner"], "round": rnd}
            # the acceptance is this build's independent review: probable verdicts and H9 read it from the record
            build["review"] = {**v, "reason": "planner acceptance (plan_build)", "by": roles["planner"],
                               "run_id": acc.get("run_id"), "usd": round(_usd(acc), 6)}
            _save_record(p, build)
            if v["verdict"] != "issues" or rnd == 1 or not build.get("session_id"):
                break
            # the planner's [must] items whole (review.ISSUE_FULL_CHARS each), as delegate's fix round gets them
            issues = "\n".join(f"- {x}" for x in (v.get("issues_full") or v["issues"]))
            first = build
            build = step("fix", runner(to=roles["builder"], resume_run=build["run_id"], mode="write", check=check,
                                       review="off", fallback=False, label=label,
                                       brief=f"The planner checked your change against the plan and found:\n{issues}\n"
                                             "Fix the real ones (say which you think are wrong and why).",
                                       **common))
            build["review_of"], build["first_review"] = first["run_id"], first["review"]
            _save_record(p, build)
        out.update(result=_brief_result(build), run_id=build["run_id"])
    else:
        recs = {}
        for slot, agent in (("A", roles["builder"]), ("B", roles["second"])):
            recs[slot] = step(f"build {slot}", runner(to=agent, brief=brief, mode="write", check=check,
                                                      worktree=True, review="off", fallback=False,
                                                      label=f"{label}:{slot}" if label else "", **common))
        done = {k: r for k, r in recs.items() if r.get("ok") and (r.get("result") or {}).get("status") == "done"}
        if len(done) < 2:
            out["pick"] = {"slot": next(iter(done), None), "why": "only one version finished" if done
                           else "neither version finished"}
        else:
            def chk(k):
                c = recs[k].get("check")
                return f"{k}: " + (("check passed" if c.get("passed") else f"check FAILED (exit {c.get('exit')})")
                                   if c else "no check command")
            text = PICK.format(wid=wid, task=brief, a=roles["builder"], b=roles["second"],
                               a_sum=(recs["A"]["result"].get("summary") or "")[:600],
                               b_sum=(recs["B"]["result"].get("summary") or "")[:600],
                               a_diff=_diff(p, recs["A"])[: max_diff // 2] or "(empty)",
                               b_diff=_diff(p, recs["B"])[: max_diff // 2] or "(empty)",
                               checks="; ".join(chk(k) for k in ("A", "B")))
            j = step("pick", runner(to=roles["judge"], brief=text, mode="read", review="off", allow_subagents=False,
                                    fallback=False, ephemeral=True, label=f"way:{wid}:pick", **common))
            s = ((j.get("result") or {}).get("summary") or "").strip()
            slot = "A" if s.upper().startswith("PICK: A") else "B" if s.upper().startswith("PICK: B") else None
            out["pick"] = {"slot": slot, "why": s[:400], "items": (j.get("result") or {}).get("open_questions") or []}
        slot = out["pick"]["slot"]
        out["versions"] = {k: {"run_id": r.get("run_id"), "agent": r.get("to"), "worktree": r.get("cwd"),
                               "branch": f"ccx/{r.get('run_id')}"} for k, r in recs.items()}
        if slot:
            out.update(run_id=recs[slot]["run_id"], result=_brief_result(recs[slot]))
        out["next"] = ("merge the picked branch yourself (nothing is merged automatically); remove the other "
                       "worktree with `git worktree remove`")
    out["state"] = "done" if out.get("run_id") else "failed"
    return _done(p, out)


def _save_record(p: Paths, rec: dict) -> None:
    if rec.get("run_id") and (p.runs / rec["run_id"]).is_dir():
        from .ledger import write_record
        write_record(p.runs / rec["run_id"], rec)


def _brief_result(rec: dict) -> dict:
    r = rec.get("result") or {}
    return {k: r.get(k) for k in ("status", "summary", "files_changed", "verification", "open_questions")} | \
        {"check": rec.get("check"), "review": rec.get("review")}


def _done(p: Paths, out: dict) -> dict:
    out["usd"] = round(sum(s["usd"] for s in out["steps"]), 6)
    d = p.state / "ways"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{out['id']}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
