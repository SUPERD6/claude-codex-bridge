# Harness audit of round 5 (r5e–r5h): did ccx keep its own obligations?

English · [中文](2026-10-28-harness-audit.zh.md) · 2026-10-28 · run on data already on disk, no new paid runs

Earlier: [round 5](2026-10-26-r5.md). Round 5 scored one thing: whether a unit's hidden tests passed. This audit
scores a second, separate thing on the same units: whether **ccx** (the harness) did what it is supposed to do
around the agents, whatever the outcome. The idea and the seven components come from "Trial by Trace"
(arXiv 2610.32285, metadata checked 2026-10-28; we read the abstract, not the full text). The criteria below are
ours, written for ccx; they are not the paper's list, and they were written by the same project they judge.

Script: `scripts/eval/harness_audit.py`. Data: `data/2026-10-28-harness-audit.json` (per unit: which criteria
failed; local paths and notes left out).

## 1. What is measured

- **Agent layer**: the unit's hidden tests (results row `ok`), as in round 5.
- **Harness layer**: 28 binary criteria in 7 components. Each one is a deterministic rule over what the unit left on
  disk (run.json, ledger, events.N.log, stderr, shared-context.md, undo.json, archived.jsonl, the lead's stream) and
  says pass / fail / not_exercised, with the file that shows it. A component fails when any of its exercised criteria
  fails; a unit's harness score is the share of its exercised components that pass (macro).
- **Mechanism chains**: a small table "harness criterion → agent condition" (e.g. lead-only lines in the shared
  context → the builder stopped early). Only for a unit that came out wrong, the chains whose harness criterion
  failed and whose agent condition holds are listed as *activated*. That is a possible mechanism, never a proven
  cause. In units that came out right the same pairs are counted apart as co-occurrence (§5), not attributed.
- **LLM rubric**: three judgement items (prompt carries lead-only instructions; review verdict grounded in what it
  checked; summary contradicted by its check), off by default, on the cheapest model (haiku), with `--dry-run`
  giving the cost first. **Not run for this report** (dry run: 506 calls, about $1.42).

| Component | Criteria (short) |
|---|---|
| Context | shared context delivered when recorded/asked · no lead-only delegation clauses in it (the rule ccx now applies, `ccx/context_share.py`) · no false start (builder blocked/partial, no files, < 20 s) · no read of the person's private agent memory / tool homes |
| Execution | runs end in a final state with final.lock · failed last attempts not reported ok · kind agrees with check, review and ledger |
| Governance | edits inside the workspace/worktree · read runs (reviews) edit nothing · no credential paths · a run's own sub-agents within the cap · no ccx run from inside a sub-agent |
| Lifecycle | no stray locks / running state · every write run has its own undo.json (fix rounds and resumes too) · resume stays in the continued session · finished runs archived · stop requests honoured |
| Observability | one ledger row per run · ledger $ = sum of attempts, reviews counted, results-row $ = ledger total · events log per attempt · run ids unique |
| Tools | the --check tested something (not exit 4/5, not "not found") · a sandbox/OS refusal did not end the attempt · no Claude sub-agent refused a tool (permission_denials) · tool-call errors recovered |
| Verification | ccx re-ran the check after "done" · weak evidence got a review verdict · ccx's final claim matches the hidden tests |

## 2. Results (r5e–r5h, 120 units)

| Arm | Units | Agent layer (hidden tests right) | Harness macro | All components pass | Task success but ≥ 1 harness fail |
|---|---|---|---|---|---|
| ccx2 | 80 | 76/80 | 0.67 | 0/80 | **76/76** |
| direct | 20 | 18/20 | 0.76 | 3/20 | 15/18 |
| builtin | 20 | 17/20 | — | — | not exercised (no ccx runs) |

Two other views (see §3 for who caused what):

| View | Left out | ccx2: macro / all pass / success but harness fail | direct |
|---|---|---|---|
| Without the criterion the **eval environment** caused | `ctx.no_private_context` (the eval's real CODEX_HOME) | 0.67 / 0/80 / 76/76 | 0.76 / 3/20 / 15/18 |
| Also without a **ccx defect fixed since these runs** | + `ctx.no_lead_only_lines` (fixed in #149; not environmental) | 0.80 / 20/80 / 56/76 | 0.76 / 3/20 / 15/18 |

The second view is not a cleaner measure of these runs: the lead-only lines did reach every ccx2 builder. It only
shows what is left once the one failure every ccx2 unit shares is set aside.

The paper's 31% (task success despite a harness failure) is not comparable: different criteria, harnesses, tasks.
What carries over is the shape: right answers hide harness problems. Per tag, ccx2's harness macro was flat
(0.66–0.67 in each of r5e, r5f, r5g, r5h), so nothing in this audit separates the four days.

**Failures per criterion** (units failing / exercised; only criteria with a failure):

| Criterion | ccx2 | direct | Where it comes from (runs) |
|---|---|---|---|
| ctx.no_lead_only_lines | 80/80 | — | every ccx2 builder got "Do not edit files yourself: hand the implementation to a sub-agent through ccx" from the person's message in its shared context |
| ctx.no_false_start | 5/80 | 0/20 | 5 Codex builder runs stopped blocked/partial in 7–9 s without a file: 3 on "use sub-agents" vs "do not hand on", 2 on the shared context / workspace |
| ctx.no_private_context | 27/80 | 0/20 | 28 Codex builder runs read the person's Codex memory file outside the workspace (its own instructions told it to); 2 direct runs that only set CODEX_HOME to a test's own temp home are not counted |
| life.undo_snapshot | 50/80 | 12/20 | 82 write runs without their own undo.json: all 51 fix rounds and all 31 resumes (`ccx undo <their id>` refused) |
| tool.check_ran | 5/80 | — | 5 checks with pytest exit 4 (a test file that does not exist); ccx reported them `check_broken`, as intended |
| tool.no_permission_denials | 37/68 | 14/20 | 65 of 142 Claude review runs were refused Bash ("don't ask" mode) and reviewed by reading only |
| ver.claim_matches_hidden | 15/80 | 8/20 | ccx2: 4 false passes, 11 false alarms (6 `ok/partial`, 4 `review_failed`, 1 `check_broken` on work that was right); direct: 1 false pass, 7 false alarms (`review_failed`) |

Passed everywhere they were exercised: run states and final.lock, kind consistency with check/review/ledger, writes
inside the workspace, reviews editing nothing, no credential paths, the sub-agent budget cap (Codex children priced
from the routing priors), ledger rows and $ (attempts, reviews, results-row total), events logs, run ids, resume in
the same session, archiving, stop requests, ccx re-running the check after "done", weak evidence reviewed.
Not exercised in this data: the depth guard (no sub-agent command called ccx; the rule tells nested runs apart by
caller only, so a nested run under the lead's own vendor would pass it), worktrees, timeouts, leftover processes
(the r5e–r5h rows predate the per-unit process audit).

**Wrong units and activated chains** (activated, not proven):

| Unit | Chains | Reading |
|---|---|---|
| r5e 2-quota-stop-log ccx2 | M1, M2, M4, M5, M7 | lead-only lines + "use sub-agents" → false start; reviewer refused Bash; ccx's last word was ok |
| r5h 1-q-killed-spend ccx2 | M1, M2, M7 | false start ("rules outside the workspace"), then a run ccx called ok |
| r5g 1-mem-report ccx2 | M7 | false pass only |
| r5g 2-q-resume-session ccx2 | M7 | false pass only |
| r5e 2-quota-stop-log direct | M4, M5, M7 | reviewer refused Bash; false pass |
| r5e 1-q-resume-session direct | none | no harness criterion failed that a chain links to |
| r5f builtin × 3 | — | no ccx runs to audit |

All four wrong ccx2 units ended with ccx saying ok (M7). That is the most useful line here: when ccx2 was wrong,
ccx's own final verdict gave the lead no warning (whether the lead then checked further is not read here). Two of
the four also started with a false start.

## 3. What is ccx's, what is the eval's, what is already fixed

| Finding | Whose | Status |
|---|---|---|
| Lead-only lines reached the builder | ccx (shared context copied the person's delegation sentence) and the eval (the lead prompt said it) | fixed after these runs: #149 drops whole lead-only clauses (`drop_lead_only`) and the sub-task prompt says the hand-off already happened |
| "Use sub-agents" vs "do not hand on" false starts | ccx prompt | fixed after these runs: #149 (F14) adds the sub-agent line only with `--parallel` |
| Fix rounds and resumes without undo.json | ccx | fixed after these runs: #149 (chain snapshot) |
| Builders reading the person's Codex memory | eval environment (real CODEX_HOME) | fixed for later rounds by the clean room (`scripts/eval/preflight.py`); these rows are not `env_clean` |
| Claude reviewers refused Bash | ccx (reviewer permissions) | open; backlog item "Claude reviewer permission note per vendor, record permission_denials" |
| False alarms (`review_failed`, `ok/partial` on right work) | ccx verdicts | open; the cost is extra lead work, not a wrong unit |
| False passes on the 4 wrong ccx2 units | ccx verdicts + agents | open; a harness audit cannot say which link failed, only that the check and review passed |

So a re-run on today's ccx should show Context and Lifecycle much better; that is a prediction, not measured here.

## 4. [must] categories (record-only, backlog build item 11)

Every `[must]` of a review is given categories from all its file:line references and the unit's diff: **in-diff**
(every reference within 3 lines of a changed line; a reference without a line number counts as in-diff when its
file has any change, and a new untracked file counts as changed throughout), **out-of-diff** (at least one reference outside the diff),
**exception-only** (it says swallowed/silent explicitly: 吞 / 静默 / swallow; a bare "except" or "silent" does not
count), **test-only** (every file it names is a test). Nothing in ccx changes; `r5.py` now stores the same fields in
every new row (`must_categories`), so the hold-out runs can measure rescue rates per category later.

| Category | [must] items | Units with one | of them right / wrong |
|---|---|---|---|
| in-diff | 50 | 35 | 30 / 5 |
| out-of-diff | 43 | 34 | 31 / 3 |
| exception-only | 8 | 7 | 6 / 1 |
| test-only | 4 | 4 | 4 / 0 |

(ccx2 and direct, deduplicated: a fix round's first review repeats the review it fixes.) These counts cannot say
which category rescues units: that needs the first review's outcome per category and a hold-out set, as the item
says.

**The diff here is the final tree's, and that is biased.** These runs did not record the tree each review saw, so
every item above was placed against the unit's final state (`diff_basis: final_tree` for every item). When a fix
round edited the line an out-of-diff [must] named, that line is in the final diff, so the item counts as in-diff:
the [must]s that got fixed drift from out-of-diff to in-diff, which skews exactly the per-category rescue rate the
record is for. Runs of today's ccx record how each write run left the tree (undo.json `after`, written after its
review); for those the script uses that tree (`diff_basis: review_tree`: a run's `review` against its own end tree,
a fix round's `first_review` against the end tree of the run it fixes). Hold-out units are deleted by r5's
clean-up, so r5 stores these categories in their rows before that; they cannot be audited from disk afterwards.

## 5. Caveats

- **Development data.** r5e–r5h are the units ccx was tuned on, before the clean room; n = 80 ccx2, 20 direct,
  20 builtin. Nothing here is a claim about other tasks or repositories.
- **Our criteria.** Written by this project for its own obligations, adapted from the paper's components, not its
  criteria or tasks; thresholds (20 s false start, 3-line in-diff tolerance, the private-path patterns) are choices.
  A criterion can be wrong; every failure lists its evidence file so it can be checked by hand.
- **Approximations.** The [must] diff is the final tree's for these rows (biased toward in-diff for fixed items,
  §4). Writes are read from the edit tools' events; a shell redirect or a Codex child session's edits are
  not seen. The budget check covers Codex child sessions only. Leftover processes could not be checked for these rows.
- **Mechanism chains are hypotheses.** An activated chain says two things co-occurred in a wrong unit. The same
  pairs also co-occur in units that came out right (ccx2: M4 in 36, M1 in 3; direct: M4 in 13), which is why they
  are not causes; the JSON keeps those apart (`chains_co_occurring_not_wrong`).
- **builtin** has no ccx runs, so its harness layer is not measured here at all; this is not a comparison of
  harnesses.
- The LLM rubric was not run.

How to reproduce:

```
python scripts/eval/harness_audit.py audit <work>/r5e <work>/r5f <work>/r5g <work>/r5h --results .ccx/eval/r5/results.jsonl --json audit.json
python scripts/eval/harness_audit.py audit ... --skip ctx.no_private_context
python scripts/eval/harness_audit.py audit ... --skip ctx.no_private_context --skip ctx.no_lead_only_lines
python scripts/eval/harness_audit.py audit ... --llm-rubric --dry-run
```
