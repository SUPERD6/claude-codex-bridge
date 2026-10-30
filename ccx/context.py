"""The lead's own context (proposal H10). Almost all spend is the lead re-reading its whole conversation every turn
(2026-10-24: sub-agents $0.34 vs the lead's own $5111 API-equivalent), so the cheapest saving is a short lead
conversation: big reads go to a sub-agent that hands back a conclusion, and a long conversation hands over to a fresh
one. This module measures it from the tools' own session files (no model calls) and words a hint."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

THRESHOLD = 150_000         # tokens a turn re-reads before the hint shows (about $0.03–0.60 a turn, by model)
EVERY = 20                  # then at most once per this many turns, per conversation


def turn_tokens(u: dict) -> int:
    """What one request read: new input + cache writes + cache reads (output excluded)."""
    return int(u.get("input_tokens", 0) or 0) + int(u.get("cache_write_tokens", 0) or 0) \
        + int(u.get("cached_input_tokens", 0) or 0)


def sessions(p, hours: float = 24.0) -> list[dict]:
    """Recent lead conversations, newest first: turns, what the last and the largest turn read, cost per turn."""
    from . import learn, ledger, usage
    since = time.time() - hours * 3600
    mine = {s for r in ledger.rows(p) if not r.get("type") for s in r.get("sessions", [])}
    evs, _ = usage.lead_events(since, mine)
    by: dict[tuple, list] = {}
    for e in evs:
        if e.get("role") == "lead":
            by.setdefault((e["agent"], e["session"]), []).append(e)
    out = []
    for (agent, sid), es in by.items():
        es.sort(key=lambda e: e["ts"])
        last = es[-1]
        read_only = {k: v for k, v in last["usage"].items() if k != "output_tokens"}
        out.append({"agent": agent, "session": sid, "model": last.get("model"), "turns": len(es),
                    "last_turn_tokens": turn_tokens(last["usage"]),
                    "peak_turn_tokens": max(turn_tokens(e["usage"]) for e in es),
                    "usd_per_turn": round(learn.price_usd(p, agent, last.get("model") or "", read_only) or 0, 4),
                    "usd_total": round(sum(learn.price_usd(p, agent, e.get("model") or "", e["usage"]) or 0
                                           for e in es), 2),
                    "last_ts": last["ts"]})
    out.sort(key=lambda s: s["last_ts"], reverse=True)
    return out


def advice(s: dict, threshold: int = THRESHOLD) -> str:
    if s["last_turn_tokens"] < threshold:
        return ""
    from .lang import say
    return say("hint_context", k=f"{s['last_turn_tokens'] / 1000:,.0f}", usd=f"{s['usd_per_turn']:.3f}",
               turns=s["turns"], agent=s["agent"])


def _last_turn_claude(transcript: Path) -> tuple[dict, str, int] | None:
    """(usage, model, turns) from a Claude Code transcript, reading only that file."""
    from .runners import usage_dict
    last, turns, seen = None, 0, set()
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        if '"assistant"' not in line or '"usage"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        m = e.get("message") or {}
        if e.get("type") != "assistant" or e.get("isSidechain") or not m.get("usage"):
            continue
        if m.get("id") in seen:              # one reply can span several lines with the same id
            continue
        seen.add(m.get("id"))
        turns += 1
        u = m["usage"]
        last = (usage_dict(fresh=u.get("input_tokens", 0) or 0, write=u.get("cache_creation_input_tokens", 0) or 0,
                           cached=u.get("cache_read_input_tokens", 0) or 0, out=u.get("output_tokens", 0) or 0),
                m.get("model") or "")
    return (last[0], last[1], turns) if last else None


def lead_now(agent: str, session: str | None, home: Path | None = None) -> int | None:
    """Tokens the lead's conversation reads per request right now (its last request), from that conversation's own
    file; None when it can't be found."""
    if not session:
        return None
    if agent == "claude":
        from .transcript import claude_session_file
        for f in filter(None, [claude_session_file(session, home)]):
            got = _last_turn_claude(f)
            if got:
                return turn_tokens(got[0])
        return None
    if agent == "codex":
        from . import usage
        evs = [e for e in usage.codex_events(time.time() - 6 * 3600, set(), home)[0]
               if e["session"] == session and e.get("role") == "lead"]
        return turn_tokens(max(evs, key=lambda e: e["ts"])["usage"]) if evs else None
    return None


def _in_subagent() -> bool:
    try:
        return int(os.environ.get("CCX_DEPTH", "0") or 0) > 0
    except ValueError:
        return False


def hint(p, agent: str, hook_input: dict, threshold: int = THRESHOLD, every: int = EVERY) -> str:
    """One line for the lead's next turn when its conversation is long; '' otherwise, and at most once per
    `every` turns per conversation (state in the hub). Advice for the lead only: a ccx sub-agent (CCX_DEPTH > 0)
    gets nothing, since handing over to a fresh conversation is not its call."""
    from . import learn
    if agent != "claude" or not hook_input.get("transcript_path") or _in_subagent():
        return ""
    got = _last_turn_claude(Path(hook_input["transcript_path"]))
    if not got:
        return ""
    u, model, turns = got
    read_only = {k: v for k, v in u.items() if k != "output_tokens"}
    s = {"agent": agent, "turns": turns, "last_turn_tokens": turn_tokens(u),
         "usd_per_turn": learn.price_usd(p, agent, model, read_only) or 0.0}
    text = advice(s, threshold)
    if not text:
        return ""
    state_f = p.state / "context-hints.json"
    try:
        state = json.loads(state_f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    sid = hook_input.get("session_id") or hook_input["transcript_path"]
    if sid in state and turns - int(state[sid]) < every:
        return ""
    state[sid] = turns
    state_f.parent.mkdir(parents=True, exist_ok=True)
    state_f.write_text(json.dumps(state), encoding="utf-8")
    return text
