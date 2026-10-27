- Evaluation: opt-in tier arms for the round-5 script (`scripts/eval/r5.py --arms fast,balanced,save,cheapest`), so
  the confirmation run measures every whole-workflow tier. Each unit's hub has the person's `policy.picked = <tier>`
  (set with `ccx config set`, the choice the arm simulates) and the lead is told the person picked it: fast does it
  itself; balanced and save size the task with `ccx propose --minutes --files` on the person's request verbatim (the
  text its run sends, so the run's own re-plan agrees) and follow its answer (authorized: run its `next` the ccx2
  way; otherwise, or when `ccx run` refuses the proposal, do it itself); cheapest is the shipped cheapest tier as a
  script runs it, propose's `next` without a lead (`ccx run --to codex --tradeoff save --review off`: no explicit
  model, so save's model pick; no fixed `--minutes`, since nobody sizes it, so ccx makes no tier plan for the run and
  its model comes from the brief's keywords as ccx2's does; no review; its `--check` is the repository's whole existing
  suite, the same command for every task of a repository, so it names no hidden test file, and its result is taken as it
  is, while save's climb on a failed ccx re-check can fire), in a hub that picked cheapest, labelled may_be_wrong.
  The explicit `--tradeoff save` wins over the hub's pick and the run is unsized, so ccx plans nothing for it: the row's
  plan says `source: eval-script`, `ccx_planned: false`, and the summary counts plan sources (`plan_sources`); it is not the direct arm under a new name (direct keeps gpt-6-luna low, `--minutes 60` and its
  review). Where save differs from ccx2: save's lead makes one more call (`ccx propose`) and its run carries the
  lead's `--minutes` / `--files`, so its model is picked from that difficulty, while ccx2's run picks from the brief's
  keywords; a save-vs-ccx2 difference is the tier path plus that model pick, not the tier path alone. ccx2 stays the all-delegated baseline; the default
  arms, schedule and done-keys are unchanged. Rows record the tier, what `ccx propose` planned (band, mode,
  authorized, from the unit hub's ledger), the reference change's size (non-test code lines and files, and the band
  those files give), the mode that actually ran, the misbanding (`misband`: the lead's `--files` band vs the
  reference files' band; `misband_overall`: the planned band vs it, which leans over by construction) and whether
  ccx's `--check` passed; every row that used ccx also keeps each run's route (`ccx_routes`: source, difficulty, rung),
  since save's run carries `--minutes` / `--files` and so picks its model from that difficulty while ccx2's falls back
  to keywords; a failed read of this metadata is kept as `bookkeeping_error` and the unit is still scored. A full
  `--lead-model` id is passed to `ccx propose --lead` as its family alias. `summary` adds a `tiers` block per arm
  (right, $/success, wall median/mean/p75, misbanding with its basis, route sources, planned vs actual modes, check
  passed on failures) and `tier_rules` per lead (each with its `pair`), so the balanced-vs-save rule also fires under
  `--lead-model opus`. `run --dry-run` now prints each unit's estimated cost and a per-arm and total estimate against
  the budget (measured r5 means per unit, an Opus lead's share x1.7, tier arms by the mode the shipped tier plans for
  each task; cheapest from the direct arm's mean, which paid a review cheapest does not).
