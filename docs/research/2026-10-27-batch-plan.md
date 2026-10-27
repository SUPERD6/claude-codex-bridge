# Batch / pipeline eval: several changes handed off at once, scored on the merged tree (plan)

English · [中文](2026-10-27-batch-plan.zh.md) · 2026-10-27 · written before any paid run; nothing here is measured

Earlier: [round 5](2026-10-26-r5.md). Round 5 measured one change per lead session. The person's request 7 is
different: "hand off A, B, C... in parallel and accept the results as they come back". What counts there is the
whole batch: total wall time, total money, and whether the tree at the end, after every merge, is right. No earlier
round scored a merged tree.

## 1. Batches (`scripts/eval/tasks_batch.py`)

Batches are made only of hold-out changes (`scripts/eval/tasks_holdout.py` and its dropped candidates), never of the
round-5 tasks ccx was tuned on. One batch = several changes of **one** repository (one lead works in one checkout).

**Common start** (`scripts/eval/batch_start.py`): the end is the first commit on the first-parent line that has every
batch commit as an ancestor; every batch commit is reverted on it, newest first, with git's three-way revert. A revert
that conflicts in code or tests drops that change (said in the check); conflicts in docs only are settled by taking
the reverted side. The lead gets the start as a fresh one-commit repository (no history to read the fix from).

| batch | repository | changes | same-file overlap |
|---|---|---|---|
| ho5-overlap | this one | undo-not-verdict, doctor-codex-sandbox, discuss-auto-tier, init-gitignore, send-busy-guard | `ccx/commands/delegation.py` (one, on purpose) |
| ho4-disjoint | this one | the same without send-busy-guard | none |
| hz4-overlap | humanize | intword-carry, naturaldelta-nonfinite, naturaldate-tz, natural-list-iterables | `src/humanize/time.py` |
| hz3-disjoint | humanize | the same without naturaldate-tz | none |

**Fallbacks, said plainly**: of the 252 five-change sets of this repository's ten hold-out changes (kept and
dropped), only two revert onto one start, and both have a same-file overlap (the other one has two); so the
conflict-free variant has four changes. In ho5-overlap, send-busy-guard alone does not revert on the end
(undo-not-verdict sits on top of it in the same file), so its hidden nodes are found on the start with the other four
put back. `batch.py check` said ok for both batches of this repository on 2026-10-27, but that check ran all hidden
files in one pytest session, which a file that does not import at the start (test_codex_lead_sandbox.py) stopped:
the start passed no node, so the regression check had nothing to compare and `coupled` was false. The check now
runs with `--continue-on-collection-errors` and must be run again before a paid run (old cached checks no longer
match). Humanize has only four hold-out changes; itsdangerous's two candidates both change `timed.py`, and on an
earlier try (not re-run here) the older one's revert conflicted there, so it has no batch. The design asked for
N=8–10 conflict-free batches: the hold-out set is too small for that.

**Check** (`python scripts/eval/batch.py check`, no agent): per change, holdout_check's band and leakage checks
against round 5; its hidden nodes are those of its own test files that pass at the end and fail with only that change
reverted, minus any that already pass at the start; none of them may sit in the start's test files word for word; the
start must import; the declared overlap must be the real one; the end must be the recorded one. A batch with any
problem does not run.

## 2. Arms (one lead session per batch)

The lead is a fresh headless Claude Code in round 5's clean room; `--lead-model` / `--lead-effort` as in round 5
(default opus medium, recorded in every row, part of the done-key).

| arm | what the lead is told |
|---|---|
| self | do everything itself |
| builtin | hand changes to the built-in `worker` sub-agent; several Agent calls at once allowed for file-disjoint changes |
| ccx-batch | one plan, today's `ccx batch` (parallel, a worktree per writer), merge the branches |
| ccx-pipeline | `ccx q add --plan`, `ccx q run --bg`, `ccx show <ids> --any --wait`, accept each result as it comes back, merge the branches under `waiting` / `unmerged`, `ccx q done`; stop starting work on backpressure |
| balanced | large file-disjoint changes to `ccx run --bg --worktree --tradeoff balanced`, small and same-file ones itself, then `show --any --wait` and merge |

## 3. Metrics (per batch × repeat × arm)

- total wall; lead $ and sub-agent $ (builtin: the worker model's share of the lead's bill, which also holds Claude
  Code's own side calls on that model; every row keeps that share as `lead_worker_model_usd`, so the other arms
  show its usual size; a lead on the worker's model gets no split; ccx arms: the hub ledger)
- hidden tests on the **final tree of the lead's checkout**: per change (all its nodes pass), all-right (every change
  right and no node that passed at the start fails), regressions
- merge conflicts the lead met (`CONFLICT` lines in its tool results) and conflict markers left in the tree
- the lead's requests, turns, tokens, wake-ups (blocking waits that came back) and idle ratio (the union of those
  waits over the wall, from each stream line's arrival time)
- quota events: rejected rate-limit events of the lead, quota / rate-limit / auth attempts in any ccx run attempt (not
  only the last, which a fallback hides), backpressure stops
- round 5's environment fingerprint, audit, leftovers and `env_clean` on every row; preflight before the first unit
  and checks between units

`summary` gives per batch and arm the median / p90 wall over repeats and the rest, and every two arms paired on the
same batch's repeats as plain counts with n. There is no bootstrap: a handful of batches is too few.

## 4. Cost

`python scripts/eval/batch.py run --dry-run --reps 2` prints every unit and an estimate. The per-change figures in
`EST_USD_PER_TASK` are a projection from round 5 (self about $1.0 for five changes, the pipeline about $0.6–0.8),
not a measurement. Four batches × five arms × two repeats is roughly $25–30 with an opus lead. A paid run needs the
person's go-ahead; nothing in this change spends money.

## 5. What this does not tell

- Any claim of "faster" or "as right" waits for the measured rows.
- Four batches of three to five changes are not N=8–10; a pipeline that only pays off on wide batches is not tested.
- The humanize batches have never been checked: that all four revert onto ca892b3 and the declared overlap are
  expectations, confirmed only when `batch.py check` runs on a clone of humanize.
- Hidden test files run in one pytest session per tree with `--continue-on-collection-errors`: a file that does not
  import fails only its own nodes. Two changes that share a test file still fail together when it does not import.
