- Lead model by task (opt-in, `ccx config set lead.model_by_task on`; default off, nothing changes when off): where
  ccx starts or recommends a new lead conversation, its model follows the task's difficulty (the same b as
  `ccx route`): `[lead_by_task] easy.claude` (sonnet) up to `easy_max_b` (4.0, about 16 minutes), else the lead's own
  model (`[lead] claude`, opus); `--risk critical` always gets the strong lead. `ccx fresh` takes `--minutes` /
  `--b` (or `--difficulty`) / `--risk`, `ccx handoff` `--minutes` / `--difficulty` / `--risk` (no `--b` there, so
  `--b` still abbreviates `--by`). Only the easy band adds `--model` (fresh's command line and `--launch`; handoff's
  `start` line); the hard band passes no `--model`, so the tool keeps the model it normally runs on. handoff's
  `--minutes` are adjusted by the handing-off lead's estimating bias, as in its own `ccx route`. `ccx route` /
  `ccx propose` add `new_lead` and, only when route's `choice` did not recommend a built-in sub-agent (its `how`
  names that rung's model and wins), `builtin_model` (easy band only; Claude Code's Agent tool `model` for the lead's
  own sub-agent). fresh, handoff and propose record a `lead_model` ledger event. A running conversation never
  switches model; an older task-routing copy without `--minutes` support gives no pick instead of an error.
- Skills (EN + ZH): agent-delegate, task-routing and project-manager teach the built-in sub-agent's model (the one ccx
  names, else omitted) and the new-lead model.
- Eval: `scripts/eval/r5.py run --lead-model auto` picks each task's lead model with the same rule (a task's minutes,
  else its reference change's size band, an oracle stand-in), as its own arm (`ccx2@auto-medium`); `--dry-run` shows
  each pick and the repriced cost, for comparing auto with fixed opus and fixed sonnet. Auto with the reference band
  is an oracle upper bound: only tasks with pre-estimated minutes count for the on/off decision. An auto unit's
  done-key leaves out its picked model, so a changed rule never re-runs a done task into the same arm.
