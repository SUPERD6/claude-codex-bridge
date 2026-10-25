"""What ccx needs to know about one agent CLI (proposal I1/I2). Every adapter answers the same questions; what a
tool can't do is a False / None here, never an error somewhere else."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Adapter:
    name: str
    vendor: str                       # who makes the model: "another vendor" means a different value here (I3)
    support: str                      # official = tested on a real machine every release; community = fakes only
    tested_version: str               # CLI version the flags below were checked against
    build: Callable                   # (model, effort, perm, cwd, prompt, run_dir, resume_id, lean) -> Invocation
    parse: Callable                   # (stdout, stderr, rc, last_message_file) -> Outcome
    login_argv: tuple | None          # `<cli> <these>` says whether it is logged in; None = ccx can't tell
    home: Callable[[], Path] | None   # the tool's own config folder
    session_files: str                # where its conversations live (for usage, handoff, archive)
    lead_events: str | None           # "module:function" reading its lead usage, None = not read
    context_file: str                 # the instruction file it loads by itself (memory points it at the hub)
    start_hook: str | None            # how ccx shows memory at session start; None = carry memory in the brief
    permissions: str                  # how read-only / write is given
    can_lead: bool                    # start hook + memory wiring: can sit in the lead's chair
    can_work: bool                    # runs a headless sub-task and returns the JSON result
    can_resume: bool                  # continues a session by id
    builtin_subagents: bool           # has its own sub-agents (Agent tool, multi_agent)
    quota_readable: bool              # its subscription windows can be read
    live_cost: bool                   # ccx can see its built-in sub-agents' spend while a run is going
    turn_hook: bool                   # a per-turn hook exists (the H10 context hint)
    pay_per_token: bool = False       # billed in real money per token (an API key, no subscription quota):
                                      # never picked by a quota fallback or as a reviewer on its own
    run_env: Callable | None = None   # (mode) -> extra environment for one run, e.g. read-only via a variable
    locate: Callable | None = None    # () -> path of the CLI when it is installed but not on PATH (a desktop app's own)

    def capabilities(self) -> dict:
        return {k: getattr(self, k) for k in ("can_lead", "can_work", "can_resume", "builtin_subagents",
                                              "quota_readable", "live_cost", "turn_hook", "pay_per_token")}

    def read_lead_events(self, since: float, exclude: set[str]) -> list[dict]:
        if not self.lead_events:
            return []
        import importlib
        mod, fn = self.lead_events.split(":")
        got = getattr(importlib.import_module(mod), fn)(since, exclude)
        return got[0] if isinstance(got, tuple) else got
