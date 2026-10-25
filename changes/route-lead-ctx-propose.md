- `ccx route --lead` reads your own conversation's size from its last request when `--lead-ctx` is not given
  (`ctx_source: lead_session`; `given` / `none` otherwise; Claude Code and Codex leads) and prices it as its own
  term: each request you make re-reads it, and doing the task yourself takes more of them than delegating (new
  priors `lead_turns_self_base` / `lead_turns_self_per_b` / `lead_turns_delegate`, from the seven-cores A/B: 3 vs 2
  at small tasks). `--ctx-tokens` keeps its meaning (context the task adds). `task_routing.py route --lead-ctx`.
- `ccx propose` (H12): the same flags as `ccx route --lead`, plus a proposal id, whether it is worth offering and
  one line to say. `ccx run --proposal ID` records the yes and links the run; `ccx propose --no ID` records a no.
  `ccx propose --stats [--days 7]`: proposed -> agreed -> delegated -> judged, and the share of real
  (non-evaluation) runs with a verdict from the lead or the person (target 60 %).
