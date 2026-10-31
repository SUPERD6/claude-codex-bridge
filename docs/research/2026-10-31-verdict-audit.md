# Verdict audit: how often does ccx's receipt say "right" when the hidden tests fail? (2026-10-31)

English · [中文](2026-10-31-verdict-audit.zh.md) · [all reports](README.md)

## In one line

**After #158, 8 of the 209 receipts that said right failed the hidden tests: 3.8 % (Wilson 95 % 2.0–7.4 %).**
Before #158 it was 18 of 267 (6.7 %). All 8 follow one pattern: ccx's `--check` passed and the review passed, but
the check never tested the behaviour the hidden test asked for. In 1 of them the check did not run the hidden
test's file at all. In the other 7 it ran a file with the same name, but that was the sub-agent's version. None of
the 8 is a patch that did not land, the case that #158 labels `no_changes`. The 3 with hub records had no tool
refused to the reviewer; for the other 5 that is Unknown. The bar set before this audit was 2 %. The point estimate
is above it, and the lower end of the interval is at it, so **this is a must-fix before release**.

The other side matters as much. After #158, 47 of the 51 units whose final receipt said wrong passed the hidden
tests, and 35 of those 47 are a failed review. A further 18 units got a "wrong" receipt first, were resumed by the
lead, and ended right. ccx errs far more often by being too strict than too lenient.

## Method

- **Units.** Every unit of a ccx arm with at least one ccx run, in the six results files the evaluations counted:
  `r4/calib`, `r4/long`, `r5/results` (r5, r5c–r5h, r6a), `r5/holdout-results` (hc1), `r5/m1h2-results`,
  `r5/m1r5-results`. That gives 565 units. A unit whose lead never delegated has no receipt and is left out. The
  52 pilot and aborted rows (`pilot-dropped`, `m1r5-aborted`, `m1h`, `m1r5-part1`, `pg0`, `long-pilot-dropped`)
  are left out too: they ran in a broken environment or were stopped, and later runs reused their work-dir keys.
- **Arms.** With a lead (Sonnet medium): `ccx`, `ccx2`, `ccx2nc`, `ccx2@auto`, `ccx2daily*` (385 units). Without
  a lead, where ccx runs straight from the brief: `direct` and r4's calibration arms (180 units, all before #158).
- **What ccx said.** The verdict comes from the final run of each chain in the unit. A run is not final when a
  later run continued it: ccx's fix round (`review_of`), or the lead's `ccx resume` (`resumed_from` in a hub; in a
  stream, the lead's `ccx resume <run>` command, because a receipt does not say which run it resumed). A unit
  counts as "said right" when every final run passes the receipt's top-line rule (`delegate.compact` /
  `exit_ok`): ok, no kind in `review_issues review_failed check_broken no_changes check_failed env`, no failed
  check, review not `issues` / `failed`, and status `done` or `partial`. A sub-agent's own `partial` counts as
  right, because the receipt prints `"ok": true` for it. The strict variant (`--strict`) counts `partial` as wrong.
- **Where the verdict was read.** For 295 units (r4 long, r5 dev set, r6a, m1r5), from the unit's hub (`run.json`).
  For 150 units (hc1, m1h2) the hub was removed after scoring, so the verdict is the last ccx receipts the lead saw
  in its kept stream. For r4 calibration (120 units), from the result row (`ccx_ok`, `status`, `check`, `review`).
  As a cross-check, 220 units have both a hub and a stream: in 4 the lead's last receipt and the hub's final run
  disagree, and all 4 passed the hidden tests, so none changes the false "right" count.
- **The truth.** The unit's `ok`: pytest on the commit's own test files, added after the run (the hidden tests).
- **Before / after #158** (`12599c0`, 2026-10-28 16:02). A unit is "after" when its ccx commit
  (`fingerprint.commit`) contains `12599c0`. Rows with no fingerprint (r4, r5–r5h) are placed by time: they all ran
  on 10-25/26, so they are "before". After #158: r6a (`c64494d`), hc1 (`b473976`), m1h2 (`600fa7b`), m1r5 (`3a15b8b`).
- **Re-run it.** The script only reads. `--work` is the temp folder that holds the `r4c r4l r5* r6a m1r5` work dirs:

```bash
python scripts/research/verdict_audit.py --eval .ccx/eval --work "$TEMP" --out docs/research/data/2026-10-31-verdict-audit.json
```

  The scrubbed per-unit rows (no paths) are in [data/2026-10-31-verdict-audit.json](data/2026-10-31-verdict-audit.json).

## Tables

Each table has four cells: the receipt said right or wrong, and the hidden tests passed or failed. "False right"
is the dangerous cell, given as a share of the receipts that said right.

| Period | Units | Said right, was right | **Said right, was wrong** | Said wrong, was right | Said wrong, was wrong | False right / said right |
|---|---|---|---|---|---|---|
| All | 565 | 450 | **26** | 79 | 10 | 26/476 = 5.5 % (3.8–7.9) |
| Before #158 | 305 | 249 | **18** | 32 | 6 | 18/267 = 6.7 % (4.3–10.4) |
| ↳ no lead | 180 | 151 | 11 | 15 | 3 | 11/162 = 6.8 % |
| ↳ with a lead | 125 | 98 | 7 | 17 | 3 | 7/105 = 6.7 % |
| **After #158** (all with a lead) | 260 | 201 | **8** | 47 | 4 | **8/209 = 3.8 % (2.0–7.4)** |
| After #158, strict (`partial` = wrong) | 260 | 80 | 4 | 168 | 8 | 4/84 = 4.8 % (1.9–11.6) |

The brackets are Wilson 95 % intervals. They treat units as independent, which they are not (see Limits), so they
are too narrow. As a share of all units after #158, false right is 8/260 = 3.1 %.

By results file:

| File | Period | Units | False right / said right |
|---|---|---|---|
| r4 calibration (no lead) | before | 120 | 4/117 |
| r4 long session | before | 5 | 0/5 |
| r5 dev set r5–r5h | before | 180 | 14/145 |
| r6a (dev set) | after | 30 | 3/25 |
| hc1 (hold-out) | after | 30 | 1/29 |
| m1h2 (hold-out, daily-setup arms) | after | 120 | 4/103 |
| m1r5 (dev set, daily-setup arms) | after | 80 | 0/52 |

## The 26 false "right" receipts, by cause

The cause comes from the records by a fixed rule (`cause()` in the script), tried in this order: the unit changed
no file; the final run had no check; the check command did or did not name the hidden test's file (the task's
`tests` list in `scripts/eval/tasks_r5.py` / `tasks_holdout.py`). The hidden tests are the commit's own test
files, added only after the run, so by construction no check ever runs them. "Same file" means the check ran the
sub-agent's version of that file.

| Cause | Before #158 | After #158 | Evidence in the records |
|---|---|---|---|
| A. The patch did not land | 2 | 0 | `direct · brief-words · 1`: no file changed, status partial (the sub-agent gave up; see the r5 report). `direct · dsh-archive · 1 (r5c)`: diffstat "no changes". #158 added the kind `no_changes` for this case. |
| B. No check, review only | 5 | 0 | All `direct`, which by design has no `--check`: `waiting-evals`, `q-resume-session` ×2, `projects-refresh`, `quota-stop-log`. The review passed (for `projects-refresh` it was `unclear`). |
| C1. The check did not run the hidden test's file | 7 | **1** | Before: r4 calibration `luna` on `inventory` and `debug-line`, 2 each (synthetic tasks: the check runs the visible tests, and the hidden test is a separate file); `r5e quota-stop-log` (check `test_quota_fast.py`, hidden `test_quota_stop_log.py`); `r5g mem-report` (`test_memory_e7.py` vs `test_memsuggest.py`); `r5h q-killed-spend` (`test_queue.py` vs `test_recover.py`). After: `m1h2 doctor-codex-sandbox · 3 · ccx2daily_clean`: the check was `tests/test_ccx.py -k doctor`, and the hidden test is a new file, `tests/test_codex_lead_sandbox.py`. |
| C2. The check ran the same file (the sub-agent's version) | 4 | **7** | Before: `r5 ccx quota-stop-log · 1`; `r5 ccx q-resume-session · 2` and `r5g q-resume-session · 2` (they ran `test_queue.py` but not `test_recover.py`); `r5c projects-refresh · 2`. After: `r6a q-resume-session · ccx2nc` (only `test_queue.py`; the review raised issues, the fix round ran, then the review passed); `r6a codex-hook-text`; `r6a mem-report`; `hc1 discuss-auto-tier · 3`; `m1h2 discuss-auto-tier` ×3. In all 7 the check passed and the review (Claude Haiku low) passed. |

The records show these factors too. They were present, but they are not proven causes:

- **The reviewer was refused tools.** Before #158, 7 of the 14 false-"right" units that have hub records had at
  least one refused tool call in their reviews (the 4 r4 calibration units have no hub). Over all hub units the
  share was 91 of 185 before and 6 of 110 after. None of the 3 after-#158 units read from a hub (r6a) had a
  refusal. For the 5 read from a stream (hc1, m1h2) it is Unknown, because the reviewer's events are not in the
  lead's stream.
- **No review after the fix round.** In `r5c projects-refresh · ccx2` and `r5e quota-stop-log · ccx2` the first
  review raised issues, the fix round's run had no review of its own, and its check passed. Both were before #158.
- **`partial` with `"ok": true`.** 4 of the 8 after #158 (all in m1h2) carried the sub-agent's own status
  `partial`. The strict rule counts them as said wrong, but it also turns 121 more right units into said wrong
  (47 → 168).
- **Root causes known from the round 5 report** ([r5 §2](2026-10-26-r5.md)). In `ccx quota-stop-log · 1` the lead
  re-worded the spec wrongly. In `ccx q-resume-session · 2` and `direct q-resume-session · 2` the review's fix
  rounds chased issues the spec never asked for.
- **"ccx show gave the result from before the fix round"** (fixed in #161). It caused no false "right" in the
  records: the 4 hub-vs-stream differences all passed the hidden tests. Stream-only units have no hub to compare
  against, so for them it is Unknown.
- **Which hidden assertion failed** is not recorded for these units: the row keeps counts only, and m1r5's kept
  failure output (`hidden-pytest.txt`) contains no false "right". It is Unknown.
- **One task holds 4 of the 8 after #158** (`discuss-auto-tier`, hold-out). Its diffs were whole-file rewrites:
  about 700 lines added and 670 removed in a file of about 690 lines, likely a line-ending change.
  `codex-hook-text` (1213/1206) and `doctor-codex-sandbox` (768/692) were rewritten the same way. Whether that
  matters is Unknown.

## The other side: said wrong, was right (47 of 51 after #158)

Each unit goes in one class, decided by its final runs and tried in this order: the check command is broken, the
check failed, the review failed, a rule (`no_changes`) fired, other. The lead itself edited files (Edit tool) in 4
of the 47. In the rest the sub-agent's result was already right and the receipt was too strict. 41 of the 47 are
the daily-setup arms of m1h2 and m1r5. A false "wrong" costs the lead time, fix rounds and money, but it leaves no
wrong code behind.

| Class | Units | Lead edited | What the records show | Example |
|---|---|---|---|---|
| Review `[must]` false alarm (`review_failed`, check passed) | **35** | 2 | Every one was reviewed by Claude Haiku low, and the fix round did not satisfy the reviewer. By task: review-min-lines 8, projects-refresh 5, quota-stop-log 5, mem-report 5, q-killed-spend 4, others 8. Each `[must]` quotes the spec, then asks for an edge case or a reading the hidden test does not ask for. | `m1r5 q-resume-session · 1 · ccx2daily_clean`: a `[must]` against the change adding `--to codex` to an existing test (the check, `tests/test_queue.py`: 7 passed). `hc1 review-min-lines · 1`: a `[must]` on how `---` / `+++` headers count. |
| Check failed (exit 1: the tests ran and failed) | **11** | 2 | Exit 1 means the tests ran, so this is not a broken command or environment (those exit 4/5). In the 3 read from a hub, the failing test is one the sub-agent wrote or changed: in `test_ui.py` and `test_archive_after_run.py`, which the hidden version replaces, and in a new file, `test_batch_review_risk.py`. For the 8 read from a stream, the failing test is not recorded: Unknown. | `m1r5 waiting-evals · 1`: `FAILED tests/test_ui.py::TestData::test_waiting_excludes_evaluation_runs`, while the hidden `test_ui.py` passed. |
| Check command broken, rule `no_changes` | 0 | | Both happened, but in every such unit the lead resumed the run and the last receipt said right (see below). | |
| Other | **1** | 0 | The last run was still `running` when the unit ended, so it has no status. | `m1r5 dsh-archive · 2 · ccx2daily_clean` |

**Wrong receipts the lead resumed: 18 more units.** These units got a "wrong" receipt first, the lead ran
`ccx resume`, and the final receipt said right and the hidden tests passed. The first receipts were: check failed
9, `no_changes` 4, check command broken 2, review failed 3. The broken check was
`python -m pytest -q tests -k undo or verify or verdict` (`m1h2 undo-not-verdict`): the `-k` expression was not
quoted, so the shell split it and pytest exited 4. In the `no_changes` cases the unit's final tree has 1–2 changed
files. Each of these 18 cost a resume, and the records cannot tell which of those resumes were needed.

## Against the bar

The bar set before this audit (release plan P1-10): false "right" above 2 % after #158 is a must-fix before
release. **The result is 3.8 % of the receipts that said right (3.1 % of all units, 4.8 % under the strict
rule), with the interval's lower end at 2.0 %. It does not clear the bar.** What would close the gap is not
decided here. The records point to three options, none of them measured:

- Mark a check that runs only tests the sub-agent wrote or changed as weak evidence.
- Ask for a check that fails before the change and passes after it.
- Show a sub-agent's `partial` on the receipt's top line.

## Limits

- **The check and the hidden tests.** The hidden tests are added only after the run, so ccx's check can never see
  them. "Said right" can only be as good as the check the lead chose and the review. In real use there are no
  hidden tests, and this audit cannot say how often a receipt is wrong there.
- **One lead model.** Every unit with a lead used Sonnet medium. The sub-agent was mostly Codex gpt-6-luna low and
  the reviewer mostly Claude Haiku low. No other lead, model or reviewer was audited.
- **Units are not independent.** The same tasks repeat over rounds and arms. After #158, the 8 false "right" fall
  on 5 tasks, and 4 of them on one task. The Wilson intervals treat units as independent, so they are too narrow.
- **Before and after is not a controlled comparison.** The task sets (dev and hold-out), the arms (the daily-setup
  arms exist only after) and the ccx versions all differ. The drop from 6.7 % to 3.8 % is not a measured effect of
  #158.
- **The dev-set tasks were used while tuning ccx.** For this repository's 5 hold-out tasks, the answer may be in
  ccx's own code (see the [hc1 report](2026-10-29-hc1-holdout.md)).
- **The receipt rule is re-applied** to old records using today's rule. Records from before #158 have no
  `no_changes` kind, so cause A is told from the changed-file count. r4 calibration is read from row fields only.
  Resumes in a stream are found from the lead's `ccx resume <run>` commands. A resume written another way would be
  missed.
