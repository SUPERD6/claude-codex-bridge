"""Which rungs a run tries, in order: the plan from tier or route, budget and provider checks, unusable
models swapped out, and the first rung on another vendor after a quota stop (from delegate.py)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import learn, ledger
from .config import Paths, next_tier, provider_env, provider_of, tier_spec

if TYPE_CHECKING:
    from .delegate import Request

def other(agent: str, cfg: dict | None = None) -> str:
    """Quota fallback target when nothing better is known: an installed agent of another vendor, official first
    (ccx/agents). With a difficulty, _fallback_plan lets routing choose among all of them by total cost."""
    from .agents import others
    got = others(agent, cfg) or others(agent, cfg, only_installed=False)
    return got[0] if got else "codex"


def _provider_envs(cfg: dict, plan: list[dict]) -> dict:
    """agent -> (cli, env) for every provider agent in the plan. A missing key fails the run up front when the
    first rung needs it; later rungs that need it are simply not reached (their entry is left out)."""
    out = {}
    for k, spec in enumerate(plan):
        ag = spec["agent"]
        if ag in out or not provider_of(cfg, ag):
            continue
        try:
            out[ag] = provider_env(cfg, ag)
        except ValueError:
            if k == 0:
                raise
            plan[k:] = [x for x in plan[k:] if x["agent"] != ag]
    return out


def _within_budget(p: Paths, cfg: dict, plan: list[dict]) -> list[dict]:
    """Drop pay-per-token rungs once today's spend reached the provider's daily_usd cap."""
    keep = []
    for spec in plan:
        pv = provider_of(cfg, spec["agent"])
        cap = (pv or {}).get("daily_usd")
        if cap is not None and ledger.spent_today(p, spec["agent"]) >= float(cap):
            continue
        keep.append(spec)
    if not keep:
        ag = plan[0]["agent"]
        raise ValueError(f"{ag}: today's budget is used up (daily_usd = {provider_of(cfg, ag).get('daily_usd')} in "
                         f"[providers.{ag}]); raise it, wait until tomorrow, or pick another agent")
    return keep


def _rung_spec(rung: str) -> dict:
    agent, model, effort = rung.split(":", 2)
    return {"agent": agent, "model": model, "effort": effort, "lean": effort == "low", "rung": rung}


def _plan(req: Request, p: Paths, cfg: dict, max_esc: int) -> list[dict]:
    """Ordered list of rung specs: first attempt, then the escalation path."""
    if req.model:
        effort = req.effort or "medium"
        rung = f"{req.to}:{req.model}:{effort}"
        ladder = list((req.route or {}).get("ladder") or [])
        if not ladder:
            try:
                ladder = learn.ladder_after(p, rung, max_esc)
            except Exception:  # noqa: BLE001 — routing skill missing: no escalation path
                ladder = []
        nxt = learn.escalates_to(p, req.to)           # e.g. a DeepSeek ladder continues on Claude
        return [_rung_spec(rung)] + [_rung_spec(r) for r in ladder[:max_esc]
                                     if r.split(":", 1)[0] in (req.to, nxt)]
    out, tier = [], req.tier
    while tier and len(out) <= max_esc:
        if not cfg["tiers"].get(tier, {}).get(req.to):
            break
        spec = tier_spec(cfg, tier, req.to)
        out.append({"agent": req.to, "model": spec["model"], "effort": spec["effort"],
                    "lean": bool(spec.get("lean", False)), "tier": tier,
                    "rung": f"{req.to}:{spec['model']}:{spec['effort']}"})
        tier = next_tier(tier)
    if not out:
        raise ValueError(f"tier {req.tier} has no {req.to} model configured")
    return out


def _fallback_plan(req: Request, p: Paths, cfg: dict, failed: dict) -> dict | None:
    """First rung on another vendor's agent after a quota stop: routing picks the cheapest in total among the
    installed ones that can work (I4); without a difficulty, the first of them."""
    from .agents import others
    to = other(failed["agent"], cfg)
    b = (req.route or {}).get("b")
    if b is not None:
        try:
            pk = learn.pick(p, float(b), others(failed["agent"], cfg) or [to],
                            (req.route or {}).get("tradeoff", "balanced"), mode=req.mode)
            return _rung_spec(pk["rung"])
        except Exception:  # noqa: BLE001
            pass
    tier = failed.get("tier") or req.tier
    if tier in cfg["tiers"] and cfg["tiers"][tier].get(to):
        spec = tier_spec(cfg, tier, to)
        return {"agent": to, "model": spec["model"], "effort": spec["effort"],
                "lean": bool(spec.get("lean", False)), "tier": tier,
                "rung": f"{to}:{spec['model']}:{spec['effort']}"}
    return None


def _usable(p: Paths, spec: dict) -> dict:
    """Swap a model this account is known not to have (learned from an earlier 'not supported' error)."""
    if spec["agent"] in ("codex", "claude", "gemini") and learn.is_unavailable(p, spec["agent"], spec["model"]):
        sub = learn.substitute(p, spec["agent"], spec["model"], spec["effort"])
        if sub:
            new = _rung_spec(f"{spec['agent']}:{sub[0]}:{sub[1]}")
            new["substituted_for"] = spec["rung"]
            if spec.get("tier"):
                new["tier"] = spec["tier"]
            return new
    return spec
