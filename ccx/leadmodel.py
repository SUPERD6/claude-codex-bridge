"""Lead model by task (opt-in): when ccx starts or recommends a NEW lead conversation, pick its model from the task's
difficulty — a cheaper lead (claude: sonnet) for easy work, the strong one ([lead] <agent>, e.g. opus) otherwise.

A running lead never switches its own model: its whole prompt cache would be lost (and Goose's per-turn switching
was the negative evidence). So this applies only where a conversation starts: `ccx fresh` (its command line, or
`--launch`), `ccx handoff` (the next line for the incoming lead), and as advice in `ccx route` / `ccx propose`
output for a new conversation on that task (`new_lead`), plus the model for the lead's own built-in sub-agent
(`builtin_model`, Claude Code's Agent tool).

The difficulty is the same b `ccx route` computes (rubric and/or minutes, 0..10, b = log2(minutes)). The rule:
  setting lead.model_by_task off (shipped) -> None: nothing changes anywhere
  no b                                      -> no pick (the tool's own default model stays)
  risk == hard_risk (critical), or b > easy_max_b -> the strong lead ([lead] <agent>)
  otherwise                                 -> [lead_by_task.easy] <agent> (none configured: the strong lead)
Thresholds live in config/tiers.toml [lead_by_task]; they are provisional, to be compared by the r5 eval
(scripts/eval/r5.py --lead-model auto).
"""
from __future__ import annotations

import time

ON = ("on", "true", "yes", "1")
# Claude Code's Agent tool `model` parameter accepts these (Claude Code 2.1.309, its tool schema); omitted, the
# sub-agent inherits the lead's model. Anything else (a full model id) is not passed.
AGENT_TOOL_MODELS = ("sonnet", "opus", "haiku", "fable")


def enabled(cfg: dict) -> bool:
    v = (cfg.get("lead") or {}).get("model_by_task", False)
    return v is True or (isinstance(v, str) and v.strip().lower() in ON)


def rule(cfg: dict) -> dict:
    r = cfg.get("lead_by_task") or {}
    return {"easy_max_b": float(r.get("easy_max_b", 4.0)), "hard_risk": str(r.get("hard_risk", "critical")),
            "easy": dict(r.get("easy") or {})}


def pick(cfg: dict, agent: str, b: float | None, risk: str | None = None, force: bool = False) -> dict | None:
    """{agent, model, band: easy|hard, b, why, rule} for a new lead of `agent` on a task of difficulty b; None when
    the setting is off (unless `force`, the eval's --lead-model auto), when b is unknown, or when no model is
    configured for that agent. Never a reason to switch a running conversation."""
    if not (force or enabled(cfg)) or b is None:
        return None
    ru = rule(cfg)
    strong = str((cfg.get("lead") or {}).get(agent) or "")
    if not strong:
        return None
    easy = str(ru["easy"].get(agent) or "") or strong
    b = round(float(b), 2)
    if risk and risk == ru["hard_risk"]:
        band, why = "hard", f"risk {risk}: the strong lead"
    elif b > ru["easy_max_b"]:
        band, why = "hard", f"b {b} > {ru['easy_max_b']}: the strong lead"
    else:
        band, why = "easy", f"b {b} <= {ru['easy_max_b']}: the cheaper lead"
    model = strong if band == "hard" else easy
    return {"agent": agent, "model": model, "band": band, "b": b, "why": why,
            "rule": {"easy_max_b": ru["easy_max_b"], "easy": easy, "strong": strong}}


def builtin_model(choice: dict | None) -> str | None:
    """The Agent tool `model` value for the same pick when the lead is Claude Code; None otherwise (omit it)."""
    if not choice or choice.get("agent") != "claude":
        return None
    m = str(choice.get("model") or "").lower()
    return m if m in AGENT_TOOL_MODELS else None


def difficulty(p, minutes: float | None = None, b: float | None = None, lead: str | None = None) -> float | None:
    """b from an explicit --b, else from --minutes the way `ccx route` turns them into b (with the lead's learned
    estimating bias); None when neither is given."""
    if b is not None:
        return float(b)
    if not minutes:
        return None
    from . import learn
    return float(learn.combine_difficulty(p, None, float(minutes), lead)["b"])


def model_argv(agent: str, model: str) -> list[str]:
    """The flag that starts a new conversation of `agent` on `model` (Claude Code 2.1.309 `--model <model>`,
    codex-cli 0.164.0 `-m, --model <MODEL>`, both checked with --help); [] for any other lead."""
    return ["--model", model] if agent in ("claude", "codex") and model else []


def record(p, choice: dict, where: str, extra: dict | None = None) -> None:
    """One ledger event per lead started or recommended with a by-task model (readers of runs skip typed rows)."""
    from . import ledger
    ledger.append_event(p, {"type": "lead_model", "ts": time.time(), "where": where, **choice, **(extra or {})})


def add_args(parser) -> None:
    """--minutes / --b / --risk on a command that starts or recommends a new lead (used only when the setting is on)."""
    g = parser.add_argument_group("lead model by task (only with `ccx config set lead.model_by_task on`)")
    g.add_argument("--minutes", type=float, help="how long a skilled engineer would need for the work the new "
                   "conversation takes on (its difficulty picks the lead's model)")
    g.add_argument("--b", type=float, help="or the difficulty directly (0..10, as ccx route gives it)")
    g.add_argument("--risk", choices=["low", "visible", "critical"], help="critical always gets the strong lead")


def for_new_lead(p, cfg: dict, agent: str, a, where: str, extra: dict | None = None) -> dict | None:
    """The pick for a new `agent` conversation from a command's --minutes / --b / --risk, recorded in the ledger;
    None (and nothing recorded) when the setting is off or no difficulty was given."""
    if not enabled(cfg):
        return None
    b = difficulty(p, getattr(a, "minutes", None), getattr(a, "b", None), agent)
    choice = pick(cfg, agent, b, getattr(a, "risk", None))
    if choice:
        record(p, choice, where, extra)
    return choice
