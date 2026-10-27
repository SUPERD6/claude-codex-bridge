- Evaluation: opt-in tier arms for the round-5 script (`scripts/eval/r5.py --arms fast,balanced,save,cheapest`), so
  the confirmation run measures every whole-workflow tier. Each unit's hub has the person's `policy.picked = <tier>`
  (set with `ccx config set`, the choice the arm simulates) and the lead is told the person picked it: fast does it
  itself; balanced and save size the task with `ccx propose --minutes --files` and follow its answer (authorized:
  run its `next` the ccx2 way; otherwise do it itself); cheapest is the direct arm's command in a hub that picked
  cheapest, labelled may_be_wrong. ccx2 stays the all-delegated baseline; the default arms, schedule and done-keys
  are unchanged. Rows record the tier, what `ccx propose` planned (band, mode, authorized, from the unit hub's
  ledger), the reference change's size (non-test code lines and files, and the band those files give), the mode
  that actually ran, the misbanding and whether ccx's `--check` passed; `summary` adds a `tiers` block per arm
  (right, $/success, wall median/mean/p75, misbanding rate, planned vs actual modes, check passed on failures) and
  `tier_rules` per lead, so the balanced-vs-save rule also fires under `--lead-model opus`. `run --dry-run` now
  prints each unit's estimated cost and a per-arm and total estimate against the budget (measured r5 means per
  unit, an Opus lead's share x1.7, tier arms by the mode the shipped tier plans for each task).
