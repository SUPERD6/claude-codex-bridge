"""Helpers shared by the command modules (output, caller/lead detection, routing resolution)."""
from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid

from pathlib import Path

from .. import learn, ledger, router
from ..config import AGENTS, DELEGATE_AGENTS
from ..runners import find_bin


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _caller(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if any(k.startswith("CODEX_") and k not in ("CODEX_HOME",) for k in os.environ):
        return "codex"
    return "user"


def _brief(args) -> str:
    if getattr(args, "brief_file", None):
        return Path(args.brief_file).read_text(encoding="utf-8")
    if args.brief and args.brief != ["-"]:
        return " ".join(args.brief)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("give the task as text, --brief-file FILE, or on stdin")


def _target(to: str, caller: str) -> str:
    if to != "auto":
        return to
    return "codex" if caller != "codex" else "claude"


def _tier(tier: str, text: str, files: int) -> tuple[str, dict | None]:
    if tier != "auto":
        return tier, None
    r = router.classify(text, files)
    return r.tier, r.as_dict()


def _agent_of_model(model: str) -> str | None:
    m = model.lower()
    if m.startswith(("gpt", "o3", "o4", "codex")):
        return "codex"
    if m.startswith(("claude", "haiku", "sonnet", "opus")):
        return "claude"
    if m.startswith(("gemini", "flash", "pro")) or m in ("flash-lite", "auto"):
        return "gemini"
    return None


LEAD_VARS = {"claude": ("CLAUDE_CODE_SESSION_ID",), "codex": ("CODEX_THREAD_ID", "CODEX_SESSION_ID")}


def lead_session_id(caller: str | None = None) -> str | None:
    """The conversation the lead is in right now (set by Claude Code / Codex for the commands they run).
    The caller's own variable wins: a Codex started from inside Claude Code also inherits Claude's."""
    own = LEAD_VARS.get(caller or "", ())
    rest = tuple(k for ks in LEAD_VARS.values() for k in ks if k not in own)
    for k in ("CCX_LEAD_SESSION", *own, *rest):
        if os.environ.get(k):
            return os.environ[k]
    return None


CONTINUE_WINDOW_SEC = 3600      # the prompt cache lives 1 h: older sessions would be re-read at full price


CONTINUE_MAX_DEPTH = 5          # after 5 tasks in one sub-session, start fresh (its context keeps growing)


def find_continuable(p, lead: str | None, cwd: Path, to: str) -> str | None:
    """Same lead conversation + same folder + same agent + recent + ended cleanly -> its session can take the
    next task, so the sub-agent keeps what it already read instead of re-reading the repo."""
    if not lead:
        return None
    from ..archive import archived_ids
    gone = archived_ids(p)
    here = str(cwd.resolve())
    for r in reversed(ledger.rows(p)):
        if r.get("type") or r.get("lead_session") != lead:
            continue
        if time.time() - (r.get("ts") or 0) > CONTINUE_WINDOW_SEC:
            return None
        if r.get("cwd") != here or r.get("to") != to or r.get("ephemeral"):
            continue
        if r.get("kind") in ("quota", "auth", "timeout") or not r.get("session_id") or r["run_id"] in gone:
            return None
        if int(r.get("continue_depth") or 0) + 1 >= CONTINUE_MAX_DEPTH:
            return None
        return r["run_id"]
    return None


SEAT_WINDOW_SEC = 7 * 86400     # a named seat keeps its session a week (re-reading after the cache expires is
SEAT_MAX_DEPTH = 30             # still cheaper than starting over); after 30 tasks it starts fresh


def find_seat(p, seat: str, cwd: Path, to: str) -> str | None:
    """The last run of a named seat ("reviewer") in this folder on this agent: its session takes the next task."""
    from ..archive import archived_ids
    gone = archived_ids(p)
    here = str(cwd.resolve())
    for r in reversed(ledger.rows(p)):
        if r.get("type") or r.get("label") != f"seat:{seat}" or r.get("cwd") != here or r.get("to") != to:
            continue
        if time.time() - (r.get("ts") or 0) > SEAT_WINDOW_SEC or r["run_id"] in gone or not r.get("session_id"):
            return None
        if r.get("kind") in ("quota", "auth", "timeout") or int(r.get("continue_depth") or 0) + 1 >= SEAT_MAX_DEPTH:
            return None
        return r["run_id"]
    return None


def installed_agents() -> list[str]:
    """Routing only considers agents whose CLI is actually on this machine (auto-discovery)."""
    return [a for a in DELEGATE_AGENTS if find_bin(a)]


def parse_quota(items: list[str] | None) -> dict:
    """["claude=0.4", "codex=85"] -> {"claude": 0.4, "codex": 0.85} (a fraction or a percentage)."""
    out = {}
    for q in items or []:
        ag, _, v = q.partition("=")
        out[ag.strip()] = float(v) if float(v) <= 1 else float(v) / 100
    return out


def provider_agents(cfg: dict) -> list[str]:
    """Provider agents (e.g. deepseek) whose key is set and whose CLI is installed."""
    out = []
    for name, pv in (cfg.get("providers") or {}).items():
        keys = [str(v)[1:] for v in (pv.get("env") or {}).values() if str(v).startswith("$")]
        if find_bin(pv.get("agent", "claude")) and all(os.environ.get(k) for k in keys):
            out.append(name)
    return out


def cash_ready(p, cfg: dict, quota: dict) -> list[str]:
    """Pay-per-token agents that may take work now: key set and under today's cap. Whether they win is the total
    cost's call (their money against the subscriptions' quota at its shadow price), not a quota threshold."""
    try:
        cash = learn.module(p, "routing").load_priors().get("cash") or {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for ag in provider_agents(cfg):
        cap = (cfg["providers"][ag] or {}).get("daily_usd")
        if ag in cash.get("agents", []) and (cap is None or ledger.spent_today(p, ag) < float(cap)):
            out.append(ag)
    return out


def _maybe_probe_claude(p, cfg: dict, agents: list[str], given: dict) -> None:
    """Claude's quota is only seen in a Claude run's events. When Claude is a candidate and the last reading is
    over an hour old, one tiny request refreshes it (off with [quota] probe_claude = false or CCX_NO_QUOTA_PROBE)."""
    if "claude" not in agents or "claude" in given or os.environ.get("CCX_NO_QUOTA_PROBE") == "1"             or not (cfg.get("quota") or {}).get("probe_claude", True) or not find_bin("claude"):
        return
    from .. import quota
    age = quota.claude_reading_age(p)
    if age is None or age > quota.PROBE_AFTER_S:
        try:
            quota.probe(p)
        except Exception:  # noqa: BLE001 — a failed probe just leaves the old reading
            pass


def resolve(spec: dict, caller: str, p, cfg: dict) -> tuple[dict | None, dict]:
    """One task spec (CLI flags or a batch entry) -> (Request kwargs, routing info).
    kwargs is None when the answer is "don't delegate" (do it yourself / split first).

    Order: explicit --model/--effort  >  rubric (task-routing, learns from outcomes)  >  --tier  >
    keyword heuristic (fallback when no rubric is given)."""
    to = spec.get("to") or "auto"
    tradeoff = spec.get("tradeoff") or cfg["defaults"].get("tradeoff", "save")
    route = {"tradeoff": tradeoff}
    if spec.get("minutes"):
        route["minutes"] = float(spec["minutes"])
    rubric = {k: spec[k] for k in learn.RUBRIC_KEYS[1:] if spec.get(k)}
    if spec.get("brief") and (rubric or spec.get("minutes")):
        from ..signals import measure        # what the brief and the folder show, the same for everyone
        obj = measure(spec["brief"], Path(spec.get("cwd") or os.getcwd()))
        if obj:
            route["objective"] = obj
            if not spec.get("files"):
                spec = {**spec, "files": obj["suggests"]["files"]}
            if rubric and "coupling" not in rubric:
                rubric["coupling"] = obj["suggests"]["coupling"]
    if spec.get("b") is not None:
        route["b"] = float(spec["b"])
    elif rubric or spec.get("minutes"):
        b_rub = None
        if rubric:
            rubric["files"] = int(spec.get("files") or 1)
            b_rub = learn.difficulty(p, rubric)
            route["rubric"] = rubric
        d = learn.combine_difficulty(p, b_rub, spec.get("minutes"), caller)
        route["b"], route["difficulty"] = d["b"], d["parts"]

    if spec.get("provider"):
        pv = (cfg.get("providers") or {}).get(spec["provider"])
        if not pv:
            raise ValueError(f"unknown provider {spec['provider']!r}")
        model = spec.get("model") or (pv.get("models") or [None])[-1]
        if not model:
            raise ValueError(f"provider {spec['provider']} needs --model")
        route["source"] = f"provider:{spec['provider']}"
        return {"to": spec["provider"], "model": model, "effort": spec.get("effort") or "low",
                "tier": "auto", "route": route, "provider": spec["provider"]}, route
    if spec.get("model"):
        agent = to if to != "auto" else (_agent_of_model(spec["model"]) or _target("auto", caller))
        route["source"] = "explicit"
        default_effort = "default" if agent == "gemini" else "medium"
        return {"to": agent, "model": spec["model"], "effort": spec.get("effort") or default_effort,
                "tier": "auto", "route": route}, route
    if "b" in route and spec.get("tier", "auto") == "auto":
        agents = ((installed_agents() or list(AGENTS)) + cash_ready(p, cfg, spec.get("quota") or {})
                  if to == "auto" else [to])
        _maybe_probe_claude(p, cfg, agents, spec.get("quota") or {})
        pk = learn.pick(p, route["b"], agents, tradeoff,
                        max_escalations=int(cfg["defaults"].get("max_escalations", 1)), mode=spec.get("mode"),
                        kind=spec.get("kind"), quota=spec.get("quota"), risk=spec.get("risk"))
        route["kind"] = learn.task_kind(spec.get("mode"), spec.get("kind"))
        route.update(source="task-routing", rung=pk["rung"], ladder=pk["ladder"], p=pk["p"],
                     chain_p=pk["chain_p"])
        if pk.get("stale"):
            route["stale"] = pk["stale"]
        if pk.get("advice") and not spec.get("force"):
            route["advice"] = pk["advice"]
            return None, route
        from .. import trial
        rate = float(os.environ.get("CCX_AB_RATE") or cfg["defaults"].get("ab_self_rate", 0) or 0)
        tr = trial.active(p) if caller in AGENTS and not spec.get("force") and not spec.get("no_ab") else None
        if tr:                                # H11: a formal comparison is running: balanced halves
            route.update(trial=tr["id"], bucket=trial.bucket(route["kind"], route["b"]))
            self_run = trial.assign(p, tr, route["kind"], route["b"]) == "self"
        else:
            self_run = (rate > 0 and caller in AGENTS and not spec.get("force") and not spec.get("no_ab")
                        and random.random() < rate)
        if self_run:
            route["ab"] = _ab_open(p, caller, route["b"], pk["rung"], spec.get("brief", ""),
                                   **({"trial": tr["id"], "bucket": route["bucket"], "kind": route["kind"],
                                       "lead_session": lead_session_id(caller)} if tr else {}))
            why = (f"the {tr['id']} comparison puts about {tr['rate']:.0%} of tasks on your side" if tr else
                   f"randomly chosen ~{rate:.0%} of tasks")
            route["advice"] = (f"ab-sample: do this one yourself ({why}, to measure what delegating saves), then "
                               f"run `ccx ab done {route['ab']} --ok 1|0`. Opt out: --no-ab")
            return None, route
        return {"to": pk["agent"], "model": pk["model"], "effort": pk["effort"], "tier": "auto",
                "route": route}, route
    tier, why = _tier(spec.get("tier", "auto"), spec.get("brief", ""), int(spec.get("files") or 0))
    route.update(source="tier" if spec.get("tier", "auto") != "auto" else "keywords", tier=tier)
    if why:
        route["why"] = why
    if tier == "T0" and not spec.get("force"):
        route["advice"] = "do-it-yourself: delegating costs more than the task"
        return None, route
    if tier == "T0":
        tier = "T1"
    return {"to": _target(to, caller), "tier": tier, "route": route}, route


def _ab_open(p, caller: str, b: float, rung: str, brief: str, **extra) -> str:
    ab_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = p.state / "ab"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ab_id}.json").write_text(json.dumps({"id": ab_id, "caller": caller, "b": b, "would_route": rung,
                                                 "brief_chars": len(brief), "ts": time.time(), **extra}),
                                     encoding="utf-8")
    return ab_id


def apply_mode(spec: dict) -> dict:
    """Fill spec["mode"] from the task text when no --mode was given (ccx/modes.py); keep how it was decided."""
    from ..modes import resolve_mode
    m = resolve_mode(spec.get("mode"), spec.get("brief", ""))
    spec.update(mode=m["mode"], mode_source=m["source"], mode_why=m["why"])
    return m


def _spec_from_args(a, text: str) -> dict:
    return {"no_ab": getattr(a, "no_ab", False), "to": a.to, "brief": text, "tier": a.tier, "files": a.files, "model": a.model,
            "effort": a.effort, "b": a.b, "coupling": a.coupling, "clarity": a.clarity, "risk": a.risk,
            "novelty": a.novelty, "minutes": a.minutes, "tradeoff": a.tradeoff, "force": a.force,
            "provider": getattr(a, "provider", None), "mode": getattr(a, "mode", None),
            "quota": parse_quota(getattr(a, "quota", None)), "kind": getattr(a, "kind", None),
            "cwd": getattr(a, "cwd", None)}


def _routing_args(ap) -> None:
    g = ap.add_argument_group("routing rubric (task-routing; any of these switches on the calibrated pick)")
    g.add_argument("--files", type=int, default=0, help="files touched")
    g.add_argument("--coupling", choices=["one", "cross", "system"])
    g.add_argument("--clarity", choices=["spec", "goal", "unknown"])
    g.add_argument("--risk", choices=["low", "visible", "critical"])
    g.add_argument("--novelty", choices=["pattern", "new"])
    g.add_argument("--b", type=float, help="difficulty 0-10 directly instead of the rubric")
    g.add_argument("--kind", choices=["code", "read", "research", "write"],
                   help="kind of work: decides which public benchmarks count (default: read-only -> read, else code)")
    g.add_argument("--tradeoff", choices=["save", "balanced", "fast"],
                   help="default from config (defaults.tradeoff, initially balanced)")
