- Lead model by task (opt-in, `ccx config set lead.model_by_task on`; default off, nothing changes when off): where
  ccx starts or recommends a new lead conversation, its model follows the task's difficulty (the same b as
  `ccx route`): `[lead_by_task] easy.claude` (sonnet) up to `easy_max_b` (4.0, about 16 minutes), else the lead's own
  model (`[lead] claude`, opus); `--risk critical` always gets the strong lead. `ccx fresh` and `ccx handoff` take
  `--minutes` / `--b` / `--risk` (fresh adds `--model` to its command line and `--launch`; handoff gives a `start`
  line); `ccx route` / `ccx propose` add `new_lead` and `builtin_model` (Claude Code's Agent tool `model` for the
  lead's own sub-agent). fresh, handoff and propose record a `lead_model` ledger event. A running conversation never
  switches model.
- Skills (EN + ZH): agent-delegate, task-routing and project-manager teach the built-in sub-agent's model (the one ccx
  names, else omitted) and the new-lead model.
- Eval: `scripts/eval/r5.py run --lead-model auto` picks each task's lead model with the same rule (a task's minutes,
  else its reference change's size band, an oracle stand-in), as its own arm (`ccx2@auto-medium`); `--dry-run` shows
  each pick and the repriced cost, for comparing auto with fixed opus and fixed sonnet.
