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


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


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


AGAIN = """{mark} {did} role={role} round={rnd}/{rounds} format-again] ccx could not read your answer: {missing}.
{rule}
Give the same answer again in that format. Status done."""

RULE = {
    "critique": "Start summary with exactly `CRITIQUE: objections` (at least one `[must] ` item) or `CRITIQUE: agree`; "
                "open_questions items start with `[must] ` or `[note] `.",
    "judge": "Start summary with `RECOMMEND: ` and the recommendation; every open_questions item starts with "
             "`[consensus] `, `[disagreement] ` or `[reason] `.",
}


def critique(turn: dict) -> str:
    """agree / objections / unparsed. [must] items are objections even without the header; no header and no
    [must] means the critic did not keep to the format, which is neither agreement nor objection."""
    s = " ".join((turn.get("summary") or "").upper().split())
    if _tagged(turn.get("points") or [], "must") or s.startswith("CRITIQUE: OBJECTIONS"):
        return "objections"
    return "agree" if s.startswith("CRITIQUE: AGREE") else "unparsed"


def agrees(turn: dict) -> bool:
    """The critic found nothing that makes the choice wrong."""
    return critique(turn) == "agree"


def judge_missing(turn: dict) -> list[str]:
    """What the judge's answer lacks for ccx to read it: the RECOMMEND line, the tagged items."""
    out = [] if (turn.get("summary") or "").strip().upper().startswith("RECOMMEND:") else ["RECOMMEND"]
    if not any(_tagged(turn.get("points") or [], t) for t in ("consensus", "disagreement", "reason")):
        out.append("[consensus]/[disagreement]/[reason] items")
    return out


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
    out = {"recommendation": rec, "consensus": _tagged(pts, "consensus"),
           "disagreements": _tagged(pts, "disagreement"), "reasons": _tagged(pts, "reason")}
    if judge_missing(judge):
        out["unparsed"] = "judge's answer lacks " + " and ".join(judge_missing(judge)) + \
            ": the recommendation is its summary as written"
    return out


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


# One read-only discuss turn, as measured in discuss-r1 (2026-10-24; codex-cli 0.164.0, claude 2.1.309, 5 turns):
# the CLI's own start-up prompt and tools dominate, the brief adds little. A CLI not measured yet gets the larger.
TURN_TOKENS = {
    "codex": {"input_tokens": 24000, "cached_input_tokens": 24000, "output_tokens": 900},
    "claude": {"input_tokens": 0, "cache_write_tokens": 7500, "cache_write_1h_tokens": 7500,
               "cached_input_tokens": 18000, "output_tokens": 1500},
}
DEFAULT_TURN = {"input_tokens": 24000, "cached_input_tokens": 24000, "output_tokens": 1500}
CHARS_PER_TOKEN = 3.5
TURN_CHARS = SUMMARY_CHARS + MAX_POINTS * POINT_CHARS    # what one turn adds to "So far" at most
MEASURED = 20                                            # last discuss turns on the same rung that are averaged


AUTO_TIER, LOW_TIER = "T2", "T1"
OVER = 1.0          # projected share of a quota window at its reset above which that agent steps down


def tiers(p: Paths, names: list[str], tier: str = "auto", quota: dict | None = None) -> tuple[dict, dict]:
    """(agent -> tier, agent -> why). A tier given applies to all. `auto`: T2, except an agent whose subscription
    quota is projected past 100% by its reset (ccx/quota.py): it talks at T1 (Claude on haiku, Codex on luna)."""
    if tier != "auto":
        return {n: tier for n in names}, {}
    if quota is None:
        from . import quota as qmod
        try:
            quota = qmod.pressure(p)["quota"]
        except Exception:  # noqa: BLE001 — unreadable quota: no step down, and it says so
            quota = {}
    out, why = {}, {}
    for n in names:
        x = quota.get(n)
        if x is not None and x > OVER:
            out[n], why[n] = LOW_TIER, f"quota projected at {x:.0%} by its reset: {LOW_TIER}"
        else:
            out[n] = AUTO_TIER
            why[n] = AUTO_TIER + (f" (quota projected at {x:.0%})" if x is not None
                                  else " (no quota reading: pay per token, or not read yet)")
    return out, why


def _tier_of(tier: str | dict, agent: str) -> str:
    return tier.get(agent, AUTO_TIER) if isinstance(tier, dict) else tier


def rung(cfg: dict, agent: str, tier: str) -> tuple[str, str]:
    """(model, effort) of `agent` at `tier`; a provider (deepseek, kimi ...) has no tier row: its own model."""
    spec = ((cfg.get("tiers") or {}).get(tier) or {}).get(agent)
    if spec:
        return spec["model"], spec["effort"]
    pv = (cfg.get("providers") or {}).get(agent) or {}
    if pv.get("models"):
        return pv["models"][-1], "low"
    raise ValueError(f"tier {tier} has no model for {agent}")


def _measured(p: Paths, agent: str, model: str, effort: str) -> list[float]:
    """API-equivalent USD of earlier discuss turns on this very rung (agent:model:effort)."""
    from . import ledger
    want = f"{agent}:{model}:{effort}"
    return [r["ae_usd"] for r in ledger.rows(p) if str(r.get("label") or "").startswith("discuss:")
            and r.get("to") == agent and (r.get("rungs") or [None])[-1] == want
            and r.get("ae_usd") is not None][-MEASURED:]


def _modelled(p: Paths, cfg: dict, agent: str, model: str, chars: int) -> float | None:
    """Start-up overhead + what the brief carries (question, context, points so far), at the model's price."""
    from . import learn
    cli = ((cfg.get("providers") or {}).get(agent) or {}).get("agent", agent)
    u = dict(TURN_TOKENS.get(cli, DEFAULT_TURN))
    u["input_tokens"] += int(chars / CHARS_PER_TOKEN)
    return learn.price_usd(p, agent, model, u)


def estimate(p: Paths, names: list[str], rounds: int, *, tier: str | dict = "T2", cfg: dict | None = None,
             question: str = "", context: str = "") -> dict:
    """What a discussion may cost, turn by turn: price of each agent's model at `tier` x (start-up overhead +
    question + the points passed so far), for the longest talk (every round, then the judge) and the shortest
    (agreement in round 1). Earlier discuss turns on the same rung, when the ledger has some, replace the model."""
    from .config import load_config
    cfg = cfg or load_config(p)
    rl = roles(names)
    seq = [r for _ in range(rounds) for r in ("proposer", "critic")] + ["judge"]
    base = len(question) + min(len(context), 4000)
    rungs = {a: rung(cfg, a, _tier_of(tier, a)) for a in dict.fromkeys(rl.values())}
    seen = {a: _measured(p, a, *rungs[a]) for a in rungs}
    usd, calls = [], {}
    for k, role in enumerate(seq):
        a = rl[role]
        calls[a] = calls.get(a, 0) + 1
        usd.append(sum(seen[a]) / len(seen[a]) if seen[a] else _modelled(p, cfg, a, rungs[a][0], base + k * TURN_CHARS))
    short = [usd[0], usd[1], usd[-1]]
    known = all(x is not None for x in usd)
    missing = sorted({rl[r] for r, x in zip(seq, usd) if x is None})
    return {"roles": rl, "tier": {a: _tier_of(tier, a) for a in rungs}, "calls_max": len(seq), "calls": calls,
            "models": {a: f"{m} {e}" for a, (m, e) in rungs.items()},
            "usd_max_est": round(sum(usd), 4) if known else None,
            "usd_min_est": round(sum(short), 4) if known else None,
            "basis": {a: (f"measured: mean of {len(seen[a])} earlier discuss turn(s) on {a}:{m}:{e}" if seen[a]
                          else f"modelled: start-up overhead + brief at {m}'s price") for a, (m, e) in rungs.items()}
            | ({"unknown": f"no price for {', '.join(missing)}: add prices to its [providers] entry"} if missing
               else {})}


def run(p: Paths, question: str, names: list[str], *, rounds: int = MAX_ROUNDS, caller: str = "the lead",
        context: str = "", cwd: Path | None = None, tier: str | dict = "T2", runner=None,
        did: str | None = None) -> dict:
    """Talk it through. `runner(agent, brief, label, resume=None) -> run record` is delegate.run by default (tests
    pass a fake); `resume` is the turn's run id when ccx asks once more, in the same session, for the format."""
    rounds = max(1, min(MAX_ROUNDS, int(rounds)))
    if not question.strip():
        raise ValueError("empty question")
    cwd = (cwd or Path.cwd()).resolve()
    if runner is None:
        from .config import load_config
        from .delegate import Request, run as delegate_run
        cfg = load_config(p)

        def runner(agent, text, label, resume=None):   # the rung named: a provider has no tier row
            model, effort = rung(cfg, agent, _tier_of(tier, agent))
            return delegate_run(Request(to=agent, brief=text, tier=_tier_of(tier, agent), model=model, effort=effort, mode="read",
                                        cwd=cwd, caller="ccx-discuss", resume_run=resume,
                                        escalate=False, fallback=False, review="off", allow_subagents=False,
                                        ephemeral=True, keep_session=True, label=label), p)
    did = did or new_id()
    rl = roles(names)
    d = {"id": did, "ts": time.time(), "question": question.strip(), "context": context.strip()[:4000],
         "caller": caller, "cwd": str(cwd), "rounds": rounds, "roles": rl, "judge_independent": len(names) > 2,
         "tiers": {n: _tier_of(tier, n) for n in names},
         "state": "running", "turns": [], "usd": 0.0}
    save(p, d)

    def call(agent: str, text: str, label: str, resume: str | None = None) -> tuple[dict, float]:
        try:
            rec = runner(agent, text, label, resume=resume) if resume else runner(agent, text, label)
        except Exception as e:  # noqa: BLE001 — one failed turn ends the talk, the record keeps what was said
            rec = {"ok": False, "error": str(e)[:300]}
        usd = sum(a.get("ae_usd") or 0 for a in rec.get("attempts") or [])
        d["usd"] = round(d["usd"] + usd, 6)
        ok = rec.get("ok") and (rec.get("result") or {}).get("status") == "done"
        return rec if ok else {**rec, "ok": False}, usd

    def missing(part: str, t: dict) -> list[str]:
        if part == "critique":
            return [] if critique(t) != "unparsed" else ["no `CRITIQUE:` line and no [must] item"]
        return judge_missing(t) if part == "judge" else []

    def turn(role: str, part: str, rnd: int) -> dict | None:
        agent = rl[role]
        text = brief(d, role, part, d["turns"], rnd)
        t0 = time.time()
        rec, usd = call(agent, text, f"discuss:{did}:{role}")
        if not rec.get("ok"):
            status = (rec.get("result") or {}).get("status")
            d["error"] = f"{role} ({agent}): {rec.get('error') or status or 'did not finish'}"
            save(p, d)
            return None
        summary, pts = points(rec.get("result"))
        last = (rec.get("attempts") or [{}])[-1]
        t = {"round": rnd, "role": role, "agent": agent, "model": last.get("model"), "part": part,
             "summary": summary, "points": pts, "run_id": rec.get("run_id")}
        lacks = missing(part, t)
        if lacks and rec.get("run_id"):    # once, same session: say what was missing and the rule again
            again = AGAIN.format(mark=MARK, did=did, role=role, rnd=rnd, rounds=d["rounds"], missing="; ".join(lacks),
                                 rule=RULE[part])
            rec2, usd2 = call(agent, again, f"discuss:{did}:{role}:format", resume=rec["run_id"])
            usd += usd2
            t["format_retry"] = True
            if rec2.get("ok"):
                t2 = {**t}
                t2["summary"], t2["points"] = points(rec2.get("result"))
                if len(missing(part, t2)) < len(lacks):
                    t, lacks = t2, missing(part, t2)
        if part == "critique":
            t["verdict"] = critique(t)
        if lacks:
            t["unparsed"] = "; ".join(lacks)
        t.update(usd=round(usd, 6), seconds=round(time.time() - t0, 1))
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
    bad = [f"{t['role']} r{t['round']}" for t in d["turns"] if t.get("unparsed")]
    if bad:     # still not in the format after one reminder: said, not guessed
        d["result"]["unparsed_turns"] = bad
    if not d["judge_independent"]:
        d["result"]["note"] = (d["result"].get("note", "") + "; " if d["result"].get("note") else "") + \
            "only two vendors: the proposer also judged"
    d["state"] = "done" if judged else "failed"
    d["ended"] = time.time()
    save(p, d)
    return d


def view(d: dict) -> dict:
    """What `ccx discuss` prints and the page lists: no briefs, just the talk and its outcome."""
    return {k: d.get(k) for k in ("id", "state", "question", "roles", "tiers", "rounds", "agreed", "judge_independent",
                                  "result", "usd", "error", "ts", "ended", "cwd")} | \
        {"turns": [{k: t.get(k) for k in ("round", "role", "agent", "model", "summary", "points", "usd", "run_id",
                                          "verdict", "format_retry", "unparsed") if k in t}
                   for t in d.get("turns") or []]}
