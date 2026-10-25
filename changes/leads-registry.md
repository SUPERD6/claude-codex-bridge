- `--as` (in `ccx mem delta`, `ccx fresh`, `ccx lead`) takes its choices from the adapters: an agent is a possible
  lead when its adapter says `can_lead` (`ccx.agents.leads()`), instead of a list written into each command.
  docs/research/2026-10-25-gemini-lead (EN + ZH): what a Gemini CLI lead would need (its SessionStart and
  BeforeAgent hooks exist by its docs), the work in pieces and how big; not built, the person decides.
