"""The lead offers to delegate (proposal H12): before a large, checkable piece of work it asks `ccx propose` what
delegating would cost and how likely it is to work, offers it in one line when it pays, and delegates only on the
person's yes. Each step leaves a ledger row, so a week of real use shows the chain proposed -> agreed -> delegated
-> judged, and how many real (non-evaluation) runs got a verdict at all."""
from __future__ import annotations

import time
import uuid

from .config import Paths


def new(p: Paths, route: dict, text: str, lead_session: str | None) -> dict:
    from . import ledger
    c = route.get("choice") or {}
    sv = route.get("self_vs_delegate") or {}
    opt = {o["way"]: o for o in c.get("options", [])}
    row = {"type": "proposal", "proposal": time.strftime("p%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
           "ts": time.time(), "b": route.get("b"), "kind": route.get("kind"), "rung": route.get("rung"),
           "recommend": c.get("recommend") or sv.get("recommend"),
           "self_usd": (opt.get("self") or {}).get("usd", sv.get("self_usd")),
           "delegate_usd": (opt.get("delegate") or {}).get("usd", sv.get("delegate_usd")),
           "p": (opt.get("delegate") or {}).get("p", route.get("chain_p")),
           "lead_ctx_tokens": c.get("lead_ctx_tokens", sv.get("lead_ctx_tokens")),
           "lead_session": lead_session, "task": text[:200]}
    ledger.append_event(p, row)
    return row


def answer(p: Paths, proposal: str, yes: bool) -> dict:
    from . import ledger
    if not any(r.get("type") == "proposal" and r.get("proposal") == proposal for r in ledger.rows(p)):
        raise ValueError(f"no proposal {proposal!r} (`ccx propose` prints its id)")
    row = {"type": "proposal_answer", "proposal": proposal, "yes": yes, "ts": time.time()}
    ledger.append_event(p, row)
    return row


def stats(p: Paths, days: float = 7.0, now: float | None = None) -> dict:
    """Over the last `days`: the proposal chain, and the share of real runs that got a verdict (from the lead or
    the person; probable verdicts ccx gave by itself are counted apart)."""
    from . import ledger
    now = now or time.time()
    since = now - days * 86400
    rows = ledger.rows(p)
    runs_by = ledger.runs_by_id(rows)
    runs = [r for r in runs_by.values() if float(r.get("ts") or 0) >= since and not ledger.is_eval(r)]
    verdicts: dict[str, dict] = {}
    for r in rows:
        if r.get("type") == "verify" and r.get("run_id") in runs_by:
            verdicts[r["run_id"]] = r                                  # the last one wins
    props = {r["proposal"]: r for r in rows if r.get("type") == "proposal" and float(r.get("ts") or 0) >= since}
    answers = {r["proposal"]: r["yes"] for r in rows if r.get("type") == "proposal_answer" and r["proposal"] in props}
    sent = [r for r in runs if r.get("proposal") in props]
    judged = [r for r in sent if r["run_id"] in verdicts and not verdicts[r["run_id"]].get("soft")]

    def share(a: int, b: int):
        return round(a / b, 3) if b else None
    by_lead = [r for r in runs if r["run_id"] in verdicts and not verdicts[r["run_id"]].get("soft")]
    soft = [r for r in runs if r["run_id"] in verdicts and verdicts[r["run_id"]].get("soft")]
    return {"days": days, "since": since,
            "proposals": {"proposed": len(props), "agreed": sum(v for v in answers.values()),
                          "declined": sum(not v for v in answers.values()),
                          "unanswered": len(props) - len(answers), "delegated": len({r["proposal"] for r in sent}),
                          "judged": len(judged), "held_up": sum(bool(verdicts[r["run_id"]].get("ok")) for r in judged),
                          "chain_complete_share": share(len({r["proposal"] for r in judged}), len(props))},
            "verdicts": {"real_runs": len(runs), "judged_by_lead_or_person": len(by_lead),
                         "probable_only": len(soft), "coverage": share(len(by_lead), len(runs)),
                         "coverage_incl_probable": share(len(by_lead) + len(soft), len(runs)),
                         "target": 0.6},
            "note": "real runs leave out evaluation runs (eval-* labels, --no-ab, probes: ledger.is_eval)"}
