"""One module per agent CLI (proposal I1). Adding a tool = adding `ccx/agents/<name>.py` with an ADAPTER and its
name below; nothing in the core changes. Providers (another model API behind one of these CLIs, e.g. DeepSeek
through Claude Code or Codex) are configured in [providers.<name>] and count as their own vendor (I3). `dsh` is
DeepSeek's own agent (DeepSeek Harness), the same vendor as the deepseek providers."""
from __future__ import annotations

import importlib

from .base import Adapter

NAMES = ("codex", "claude", "gemini", "dsh")


def get(name: str) -> Adapter:
    if name not in NAMES:
        raise KeyError(f"no adapter for {name!r}; known: {', '.join(NAMES)}")
    return importlib.import_module(f".{name}", __name__).ADAPTER


def all_adapters() -> list[Adapter]:
    return [get(n) for n in NAMES]


def leads() -> tuple[str, ...]:
    """Agents that can sit in the lead's chair (`can_lead`: a start hook and memory wiring): the `--as` choices.
    A tool becomes a possible lead by saying so in its adapter, not by an edit to each command."""
    return tuple(a.name for a in all_adapters() if a.can_lead)


def vendor(name: str, cfg: dict | None = None) -> str:
    """Who makes the model behind this agent name. A provider is its own vendor unless its config says
    otherwise (`vendor = "..."`), so DeepSeek through Claude Code is not "the same as Claude"."""
    pv = ((cfg or {}).get("providers") or {}).get(name)
    if pv is not None:
        return str(pv.get("vendor") or name)
    return get(name).vendor if name in NAMES else name


def same_vendor(a: str, b: str, cfg: dict | None = None) -> bool:
    return vendor(a, cfg) == vendor(b, cfg)


def installed(names=None) -> list[str]:
    from ..runners import find_bin
    return [n for n in (names or NAMES) if find_bin(n)]


def others(agent: str, cfg: dict | None = None, *, need: str = "can_work", only_installed: bool = True) -> list[str]:
    """Agents of a different vendor that can do `need`, official ones first (I3/I4). Routing then picks among
    them by total cost; this list never decides on its own which one is cheapest. Pay-per-token agents (dsh) are
    left out, like the providers: real money is spent only when the person or routing's cash rule asks for it."""
    from ..runners import find_bin
    out = [a for a in all_adapters() if getattr(a, need) and not same_vendor(a.name, agent, cfg)
           and not a.pay_per_token and (not only_installed or find_bin(a.name))]
    out.sort(key=lambda a: (a.support != "official", NAMES.index(a.name)))
    return [a.name for a in out]
