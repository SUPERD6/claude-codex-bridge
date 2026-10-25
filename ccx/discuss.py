"""`ccx discuss` (proposals H3, H4, I7): up to three models from different vendors talk a decision through before
the lead commits to it. One proposes, one looks for what is wrong, one judges; at most three rounds, and between
turns only the points travel (a few short lines each), never a whole answer or conversation. The result says where
they agree, where they don't, the reasons and a recommendation; `ccx ui` shows the turns as a conversation.

It costs several model calls, so it is for decisions that are expensive to get wrong. The lead proposes it and asks
the person first (H4, skills/agent-delegate); `--dry-run` says who would take part and what it may cost."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from .config import Paths

MARK = "[ccx discuss"
MAX_ROUNDS = 3
MAX_POINTS = 5
POINT_CHARS = 300
SUMMARY_CHARS = 500
ROLES = ("proposer", "critic", "judge")

BRIEF = """{mark} {did} role={role} round={rnd}/{rounds}] Models from different vendors are talking a decision through
for {caller}; you are the {role}. You may read files in the workspace; do not edit anything.

## The question
{question}
{context}{so_far}
## Your part
{part}
Status done. Only summary and open_questions are read; keep each item to one line."""

PART = {
    "propose": ("Propose the approach you would choose. summary: the proposal in at most 80 words. open_questions: "
                "its key points, each starting with `[point] ` and carrying its reason, at most 5."),
    "revise": ("The critic objected (above). Revise the proposal: keep what holds, change what doesn't. summary: the "
               "revised proposal in at most 80 words. open_questions: its key points, each starting with `[point] `; "
               "where you still disagree with an objection, `[keep] what — because ...`. At most 5."),
    "critique": ("Look for what is wrong or risky in the proposal for this question. Start summary with exactly "
                 "`CRITIQUE: objections` (at least one [must]) or `CRITIQUE: agree`, then one sentence. "
                 "open_questions: `[must] ...` for what would make the choice wrong, `[note] ...` for minor things; "
                 "at most 5, [must] first."),
    "judge": ("Judge the discussion above. Start summary with `RECOMMEND: ` and the recommendation in at most 80 "
              "words. open_questions: each item starts with one of `[consensus] ` (both sides agree), "
              "`[disagreement] ` (still open, say both positions) or `[reason] ` (why you recommend it); at most 8."),
}


def _dir(p: Paths) -> Path:
    return p.state / "discussions"


def _file(p: Paths, did: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", did or ""):
        raise ValueError("bad discussion id")
    return _dir(p) / f"{did}.json"


def save(p: Paths, d: dict) -> None:
    f = _file(p, d["id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)                      # the page may read it at any moment


def load(p: Paths, did: str) -> dict:
    try:
        return json.loads(_file(p, did).read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"no discussion {did}") from None


def recent(p: Paths, since: float = 0.0) -> list[dict]:
    out = []
    if _dir(p).is_dir():
        for f in _dir(p).glob("*.json"):
            try:
                if f.stat().st_mtime >= since:
                    out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return sorted(out, key=lambda d: -(d.get("ts") or 0))


def participants(cfg: dict, wanted: list[str] | None, installed=None) -> list[str]:
    """2–3 agents of different vendors, in the order of the roles. Not given: the installed ones, one per vendor."""
    from . import agents
    if wanted:
        names = [w.strip() for w in wanted if w.strip()]
    else:       # pay-per-token agents (dsh) spend real money: only when named
        names = [n for n in (installed or agents.installed)() if not agents.get(n).pay_per_token]
    out: list[str] = []
    for n in names:
        if n not in agents.NAMES and n not in (cfg.get("providers") or {}):
            raise ValueError(f"unknown agent {n!r}")
        if any(agents.same_vendor(n, o, cfg) for o in out):
            if wanted:
                raise ValueError(f"{n} is the same vendor as one already taking part; a discussion needs different "
                                 "vendors (the same model misses its own mistakes)")
            continue
        out.append(n)
    if len(out) < 2:
        raise ValueError("a discussion needs at least two agents from different vendors (installed: "
                         f"{', '.join(names) or 'none'})")
    return out[:3]


def roles(names: list[str]) -> dict[str, str]:
    """proposer, critic, judge. With two, the proposer also judges and the result says so."""
    return {"proposer": names[0], "critic": names[1], "judge": names[2] if len(names) > 2 else names[0]}


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def points(result: dict | None) -> tuple[str, list[str]]:
    """(summary, points) of one answer, cut down to what travels to the next turn."""
    r = result or {}
    return (_clip(r.get("summary"), SUMMARY_CHARS),
            [_clip(x, POINT_CHARS) for x in (r.get("open_questions") or []) if str(x).strip()][:MAX_POINTS + 3])


def _tagged(items: list[str], tag: str) -> list[str]:
    t = f"[{tag}]"
    return [x.strip()[len(t):].strip() for x in items if x.strip().lower().startswith(t)]


def agrees(turn: dict) -> bool:
    """The critic found nothing that makes the choice wrong."""
    s = (turn.get("summary") or "").upper()
    return not _tagged(turn.get("points") or [], "must") and not s.startswith("CRITIQUE: OBJECTIONS")


def outcome(judge: dict | None, turns: list[dict]) -> dict:
    """consensus / disagreements / reasons / recommendation, from the judge's tagged items."""
    if not judge:
        last = next((t for t in reversed(turns) if t["role"] == "proposer"), {})
        crit = next((t for t in reversed(turns) if t["role"] == "critic"), {})
        return {"recommendation": last.get("summary", ""), "consensus": [],
                "disagreements": _tagged(crit.get("points") or [], "must"), "reasons": [],
                "note": "no judgement (the judge's turn did not finish): the last proposal and open objections"}
    s = judge.get("summary") or ""
    rec = s[len("RECOMMEND:"):].strip() if s.upper().startswith("RECOMMEND:") else s
    pts = judge.get("points") or []
    return {"recommendation": rec, "consensus": _tagged(pts, "consensus"),
            "disagreements": _tagged(pts, "disagreement"), "reasons": _tagged(pts, "reason")}


def _so_far(turns: list[dict]) -> str:
    if not turns:
        return ""
    lines = ["\n## So far (points only)"]
    for t in turns:
        lines.append(f"### Round {t['round']}, {t['role']} ({t['agent']})")
        if t.get("summary"):
            lines.append(t["summary"])
        lines += [f"- {x}" for x in t.get("points") or []]
    return "\n".join(lines) + "\n"


def brief(d: dict, role: str, part: str, turns: list[dict], rnd: int) -> str:
    ctx = d.get("context") or ""
    return BRIEF.format(mark=MARK, did=d["id"], role=role, rnd=rnd, rounds=d["rounds"], caller=d["caller"],
                        question=d["question"], context=f"\n## Context\n{ctx}\n" if ctx else "",
                        so_far=_so_far(turns), part=PART[part])


def _avg_usd(p: Paths, agent: str) -> float | None:
    from . import ledger
    xs = [r["ae_usd"] for r in ledger.rows(p) if r.get("to") == agent and r.get("mode") == "read"
          and r.get("ae_usd") is not None][-30:]
    return sum(xs) / len(xs) if xs else None


def estimate(p: Paths, names: list[str], rounds: int) -> dict:
    """What a discussion may cost: at most 2 calls a round plus the judge, priced at each agent's recent read runs."""
    rl = roles(names)
    calls = {rl["proposer"]: rounds, rl["critic"]: rounds}
    calls[rl["judge"]] = calls.get(rl["judge"], 0) + 1
    per = {a: _avg_usd(p, a) for a in calls}
    known = all(v is not None for v in per.values())
    return {"roles": rl, "calls_max": sum(calls.values()), "calls": calls,
            "usd_max_est": round(sum(per[a] * n for a, n in calls.items()), 4) if known else None,
            "basis": "average of each agent's last read-only runs (API-equivalent)" if known
            else "no read-only runs recorded for some agent yet: cost unknown"}


def run(p: Paths, question: str, names: list[str], *, rounds: int = MAX_ROUNDS, caller: str = "the lead",
        context: str = "", cwd: Path | None = None, tier: str = "T2", runner=None) -> dict:
    """Talk it through. `runner(agent, brief, label) -> run record` is delegate.run by default (tests pass a fake)."""
    rounds = max(1, min(MAX_ROUNDS, int(rounds)))
    if not question.strip():
        raise ValueError("empty question")
    cwd = (cwd or Path.cwd()).resolve()
    if runner is None:
        from .delegate import Request, run as delegate_run

        def runner(agent, text, label):
            return delegate_run(Request(to=agent, brief=text, tier=tier, mode="read", cwd=cwd, caller="ccx-discuss",
                                        escalate=False, fallback=False, review="off", allow_subagents=False,
                                        ephemeral=True, label=label), p)
    did = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    rl = roles(names)
    d = {"id": did, "ts": time.time(), "question": question.strip(), "context": context.strip()[:4000],
         "caller": caller, "cwd": str(cwd), "rounds": rounds, "roles": rl, "judge_independent": len(names) > 2,
         "state": "running", "turns": [], "usd": 0.0}
    save(p, d)

    def turn(role: str, part: str, rnd: int) -> dict | None:
        agent = rl[role]
        text = brief(d, role, part, d["turns"], rnd)
        t0 = time.time()
        try:
            rec = runner(agent, text, f"discuss:{did}:{role}")
        except Exception as e:  # noqa: BLE001 — one failed turn ends the talk, the record keeps what was said
            rec = {"ok": False, "error": str(e)[:300]}
        usd = sum(a.get("ae_usd") or 0 for a in rec.get("attempts") or [])
        d["usd"] = round(d["usd"] + usd, 6)
        status = (rec.get("result") or {}).get("status")
        if not rec.get("ok") or status != "done":
            d["error"] = f"{role} ({agent}): {rec.get('error') or status or 'did not finish'}"
            save(p, d)
            return None
        summary, pts = points(rec.get("result"))
        last = (rec.get("attempts") or [{}])[-1]
        t = {"round": rnd, "role": role, "agent": agent, "model": last.get("model"), "part": part,
             "summary": summary, "points": pts, "run_id": rec.get("run_id"), "usd": round(usd, 6),
             "seconds": round(time.time() - t0, 1)}
        d["turns"].append(t)
        save(p, d)
        return t

    agreed, r = False, 0
    for r in range(1, rounds + 1):
        if not turn("proposer", "propose" if r == 1 else "revise", r):
            break
        crit = turn("critic", "critique", r)
        if not crit:
            break
        if agrees(crit):
            agreed = True
            break
    judged = turn("judge", "judge", r) if d["turns"] and "error" not in d else None
    d["agreed"] = agreed
    d["result"] = outcome(judged, d["turns"])
    if not d["judge_independent"]:
        d["result"]["note"] = (d["result"].get("note", "") + "; " if d["result"].get("note") else "") + \
            "only two vendors: the proposer also judged"
    d["state"] = "done" if judged else "failed"
    d["ended"] = time.time()
    save(p, d)
    return d


def view(d: dict) -> dict:
    """What `ccx discuss` prints and the page lists: no briefs, just the talk and its outcome."""
    return {k: d.get(k) for k in ("id", "state", "question", "roles", "rounds", "agreed", "judge_independent",
                                  "result", "usd", "error", "ts", "ended", "cwd")} | \
        {"turns": [{k: t.get(k) for k in ("round", "role", "agent", "model", "summary", "points", "usd", "run_id")}
                   for t in d.get("turns") or []]}
