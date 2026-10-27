"""A sub-agent's own sub-agents (proposals F10–F14): limits on spend and quota, not on head count.

How many run at once, which model they use and how a piece is split stay the tool's own choice; ccx only sets the
edges. F10: concurrency is left to the tool unless quota is tight (then 2, or 1) or the lead gave a number. F11: the
spend cap is the piece's budget (`--budget`, a queue item's share) or `[subagents] max_usd`; a run over it stops as
over_budget and can be continued with more budget. F12: a Claude sub-run gets the Agent tool too, since its
sub-agents' spend shows up while it runs (stream events and <session>/subagents/*.jsonl, checked 2026-10-24 with
Claude Code 2.1.309). F13: their model is the tool's default, one rung down only when quota is tight. F14: a piece
run with `--parallel` says so in the words Codex's own instructions wait for ("explicitly asked ... sub-agents").
Since 2026-10-26 a brief that merely lists 3+ items no longer gets them (`has_parts` is kept for callers that want
the hint): in round 5, 40/100 first runs got the words, cost $0.007-0.024 more a run with no wall-clock gain, and
3/100 stopped as blocked in 7-8 s.

Measured caveat (PR #6, 2026-10-24): codex-cli 0.164 tells its model not to start sub-agents unless the user,
AGENTS.md or a skill explicitly asks; gpt-6-luna/low started none in 5 runs, even when asked. So these limits have
not been hit by a real run yet."""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_CAP_USD = 2.0
TIGHT = 1.0         # projected share of the tightest quota window at its reset: over the limit at this pace
SNUG = 0.8
PARALLEL = ("This task has parts that do not depend on each other. You are explicitly asked to use sub-agents for "
            "them: start one sub-agent per independent part (spawn_agent in Codex, the Agent tool in Claude Code), "
            "let them work in parallel, then combine their work and check the whole result yourself.")
_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.M)


def has_parts(brief: str, minimum: int = 3) -> bool:
    """A brief that lists at least `minimum` items (bullets or numbers) is taken to have separate parts."""
    return len(_ITEM.findall(brief or "")) >= minimum


def parse_spec(value: str | None) -> str:
    """--subagents auto | off | N -> the same, validated."""
    v = (value or "auto").strip().lower()
    if v in ("auto", "off") or (v.isdigit() and int(v) > 0):
        return v
    raise ValueError("--subagents takes auto, off or a number")


def plan(agent: str, model: str, spec: str, quota: dict, ladder: dict) -> dict:
    """What ccx sets for this attempt's own sub-agents: threads (None = the tool's default), model (None = the
    tool's default), and why."""
    out = {"threads": None, "model": None, "why": "left to the tool"}
    if spec.isdigit():
        out.update(threads=int(spec), why=f"--subagents {spec}")
    share = quota.get(agent)
    if share is None:
        return out
    rungs = ladder.get(agent, [])
    from .leadcost import _rung_of
    cur = _rung_of(agent, model)
    if share >= TIGHT:
        if not spec.isdigit():
            out["threads"] = 1
        if cur and cur in rungs and cur != rungs[-1]:
            out["model"] = rungs[rungs.index(cur) + 1]
        out["why"] = f"{agent} quota tight ({share:.0%} of a window projected at its reset)"
    elif share >= SNUG and not spec.isdigit():
        out.update(threads=2, why=f"{agent} quota snug ({share:.0%} projected)")
    return out


def cap_usd(budget: float | None, cfg: dict) -> float:
    if budget is not None:
        return float(budget)
    return float((cfg.get("subagents") or {}).get("max_usd", DEFAULT_CAP_USD))


def claude_children(session: str, cwd: Path, home: Path | None = None) -> list[dict]:
    """Usage of a Claude session's own sub-agents so far, from <projects>/<cwd slug>/<session>/subagents/."""
    from .config import claude_home
    from .runners import usage_dict
    from .transcript import claude_project_dirs
    d = next((x / session / "subagents" for x in claude_project_dirs(Path(cwd), home or claude_home())
              if (x / session / "subagents").exists()), Path(cwd) / session / "subagents")
    out, seen = [], set()
    for f in sorted(d.glob("agent-*.jsonl")) if d.exists() else []:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"usage"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = e.get("message") or {}
            u = m.get("usage")
            if e.get("type") != "assistant" or not u or m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            out.append({"model": m.get("model") or "", "usage": usage_dict(
                fresh=u.get("input_tokens", 0) or 0, write=u.get("cache_creation_input_tokens", 0) or 0,
                cached=u.get("cache_read_input_tokens", 0) or 0, out=u.get("output_tokens", 0) or 0)})
    return out
