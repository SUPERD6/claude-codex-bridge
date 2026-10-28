# Offline experiments C1-C6, the B1 pre-count and the B3 pre-checks (report)

English · [中文](offline-experiments.zh.md) · 2026-10-28 · ccx after main `0837da1` (#152) · codex-cli 0.164.0 · Windows 11

What this is: the cheap experiments of the improvement plan's group C (no paid CLI, or a few cents) run on the
round-5 development records (r5c..r5h: 180 unit trees, 100 ccx2 units with a lead stream), plus the $0 count the plan
requires before B1 (skip a review by reason) and the checks it requires before B3 (a lean Codex start for tier-routed
low runs) may be built. B2's offline replay (focused fix-round re-review) was **not** done, so PR-B2 stays blocked
(see the table). Every number is from the development
set only (10 tuned tasks); no hold-out round has run yet. **Money spent: $0.051** (C6 only; everything else $0).

Scripts (`scripts/eval/`, standard library, tests in `tests/test_eval_offline.py` on fake data):

| # | Script | Cost | Ran |
|---|---|---|---|
| C1 | `c1_namecheck_scan.py` | $0 | yes |
| C2 | `c2_lead_accept.py` (`plan` / `generate` / `score`) | est. $1.20 (sonnet) | plan only |
| C3 | `c3_check_reuse.py` | $0 | yes |
| C4 | `c4_must_filter.py --dry-run` | est. $1.83 (haiku) - $5.50 (sonnet) | dry-run only |
| C5 | `c5_diff_read.py` | $0 | yes |
| C6 | `c6_reuse_rule.py` (uses `review_replay.py`'s runner) | $0.051 | yes, 6 reviews |
| B1 | `b1_skip_count.py` (`--trees`: C1's `--reviewed` folder) | $0 | yes |
| B2 | (offline replay of a focused re-review) | not priced | **no** |
| -  | `offline_common.py` | - | shared helpers |

Records are read from the system temp folder (`%TEMP%/r5c..r5h`) or `CCX_REPLAY_RECORDS`; results rows from
`.ccx/eval/r5/results.jsonl`.

## Results at a glance

| # | Question | Answer | Plan's gate | Next |
|---|---|---|---|---|
| C1 | Does `ccx namecheck` raise false alarms? | 0 false of 8 hits in changed code (180 final trees + 183 reviewed trees), 0 false in 681 whole files + 28 external files + this repo (214) | FP = 0: passed | before/after comparison (tiers.toml) before `fail` |
| C3 | Can ccx reuse the builder's passing check? | 110 runs where the builder ran exactly ccx's command and both passed; 4 builder-pass/ccx-fail (all the pre-#147 quoting bug); check median 4.8 s in no-review runs | measure only | no runtime switch |
| B1 | Is `unsure` / `tests_miss_change` the only review trigger often? | of 107 first reviews: `tests_miss_change` sole in 20 (18.7%), `unsure` sole in 1 (0.9%; 4 of its 5 would still be reviewed for `tests_miss_change`) | below ~5%: drop | `unsure`-only skip (the plan's only candidate) is below 5%: drop PR-B1 unless the lead decides otherwise |
| B2 | Does a focused fix-round re-review keep every rescue and [must]? | **not run** (no script, not priced) | 10/10 rescues, every [must], median saving >= 10 s | PR-B2 stays blocked |
| C5 | Does "lead did not read the diff" separate right from wrong? | no: 85/93 right and 7/7 wrong ccx2 units had no `git diff`; p = 1.0 | must separate | drop the skill variant |
| C6 | Does a "reuse existing constants" review rule catch r5e:2? | rule 3/3 as [must], today's brief 0/3 as [must] (2/3 as a note) | must catch | candidate; needs controls |
| C2 | Lead-written acceptance tests | not run (5 tasks with wrong units, 10 tasks to cover, est. $1.20) | catch >= 2, FP <= 3% | needs approval to spend |
| C4 | Strong reviewer filters [must] | not run (52 rounds: 9 fail->pass, 35 pass->pass; est. $1.83-5.50) | keep all rescues (9/9 planned, an unjudged one counts as lost) | over the $0.5 the plan assumed |
| B3 | Is a lean Codex start safe for shared memory? | yes: `$CODEX_HOME/AGENTS.md` and the brief's notes survive `--ignore-user-config`; start to first request -3.1 s | pre-checks | PR-L may go ahead (default off) |

## C1 namecheck scan

`ccx namecheck` (this checkout) over (a) every unit's changes since its `start` commit, as `ccx run` checks them;
(b) the 183 trees reviewers saw before a fix round (rebuilt from the review brief's diff; fix rounds overwrite this
state, so a bug a review caught exists only there); (c) every distinct `.py` file of the 180 final trees whole;
(d) the external repositories' source (humanize 13 files, itsdangerous 15) and this repository (214).
Each hit was read and labelled by hand (labels are in the script).

| Scan | Files | Hits | True | False | In a broad `except` that swallows |
|---|---|---|---|---|---|
| changes, final trees | 180 units | 1 | 1 | 0 | 1 |
| changes, reviewed trees | 183 trees (0 skipped) | 7 | 7 | 0 | 6 |
| whole files, final trees | 681 distinct | 1 (the same bug) | 1 | 0 | 1 |
| external + this repo | 242 | 0 | - | - | - |

The 8 change hits are 5 bugs in 5 units (r5g:2 uses its unbound `cfg` twice: 2 hits of one bug; r5c:2 shows up in
its final tree and in two reviewed trees): `load_config` / `cfg` used but never bound in `cmd_mem`
(projects-refresh, 4 units; all inside `except Exception: pass` on the session-start path, so no test sees a
NameError, only a missing refresh), and `_caller` never imported in `delegate.py` (r5g:1 mem-report; outside any
try, it would crash every brief that gets notes). Only r5c:2 projects-refresh-ccx2 kept its bug to the end (that
unit is wrong); the other four were gone after a fix round. The reviewers named the undefined name in 2 of the 6
reviewed trees that had a hit; 4 reviews missed it.

Reviewed trees: the script now counts the ones it could not rebuild (`reviewed_skipped` in the JSON, printed beside
the count). With a short `--reviewed` folder all 183 rebuild (0 skipped). Under a long folder (the session scratchpad,
~110 characters) one tree fails on Windows path length, r5e:2 projects-refresh-direct review 95aa
(`FileNotFoundError`), and the count drops to 182; rebuilt under a short folder that tree has no hit, so the totals
above do not change. Keep `--reviewed` short.

Reading against the plan's rule: no false positive anywhere, so the next step is the before/after comparison that
`config/tiers.toml` already asks for before `namecheck = "fail"`. A `swallow` mode is not needed (it was meant for
false alarms outside swallow blocks; there are none). Whether `warn` already makes the lead or reviewer fix a hit
cannot be read from r5 (no namecheck in those runs) and needs the hold-out records.

## C3 reuse of the builder's check

176 write runs with `--check` (all Codex builders; review children left out). After its last file edit, did the
builder run ccx's own check command? "Exact" means ccx's command is one whole statement of the builder's command:
the shell wrapper (`powershell -Command '...'`) is taken off, the command split on `;` `&&` `||` `|` and new lines,
and a statement must equal ccx's command up to quotes and spaces. A narrower run (`file.py::Test::one`, `-k ...`) or
a wider one (more files) is not exact. In a compound command the exit code is the last statement's, so the outcome
comes from the output's one pytest summary line; with several test runs in one command it is unclear.

| Builder's last run | Runs | ccx's check passed | failed |
|---|---|---|---|
| exact command, passed | 114 | 110 (match) | 4 |
| exact command, failed | 10 | 7 | 3 |
| exact command among other tests in one command (unclear) | 2 | - | - |
| other test command passed (incl. narrower / wider runs) | 37 | - | - |
| no test after the last edit | 13 | - | - |

(An earlier version of this report matched by substring and counted 125 / 121 / 11: it took 10 narrower or wider
runs, e.g. a single `::test` id, as ccx's command, and read 2 compound commands with two test runs by their last
exit code.)

The 4 "builder passed, ccx failed" are all `ERROR: file or directory not found: or`: ccx's own run of a quoted
`-k "a or b"` on Windows, fixed by #147 (all r5 records predate it). The 7 "builder failed, ccx passed" have two
causes: 5 are the builder's sandbox (`tests/test_recover.py::TestSweep` kill tests that fail inside Codex's
sandbox), and 2 are PowerShell not expanding a glob in the check command (`tests/test_q*.py`, r5e:2
q-resume-session; `tests/test_quota*.py`, r5f:1 quota-stop-log: `file or directory not found`) while ccx's own run
expanded it. So a builder failure is no signal either, and the same command text in another shell is not always the
same run. Seconds: runs without a review spend a median 4.8 s on the check (56 runs, 474 s in all; per unit median
2.5 s); the 27 of them that reuse could have skipped add up to 281 s over 100 units. Following the plan: measurement
only, no runtime switch (it would need 0 mismatches after #147 and a no-review check median above 30 s).

## B1 pre-count: is `unsure` or `tests_miss_change` the only review trigger?

`b1_skip_count.py`, $0. ccx records only the first review reason that fired, in `ccx/review.py`'s order (asked,
risk, >= 50 changed code lines, unsure, claimed files mismatch, no files; then the weak-evidence reasons, last of all
`tests_miss_change`). `tests_miss_change` is therefore sole whenever it is recorded. For `unsure` the script checks
the later triggers: files mismatch / none reported (claimed files against the reviewed diff), edited tests, no
check, and `check_gap` on the tree the reviewer saw (C1's rebuilt reviewed trees). The `weak_daily` cap is not
modelled.

| | Reviews | asked | lines | `tests_miss_change` (sole) | `unsure` | `unsure` sole |
|---|---|---|---|---|---|---|
| first reviews | 107 | 39 | 43 | 20 (18.7%) | 5 | 1 (0.9%) |
| all reviews (incl. fix rounds) | 179 | 98 | 51 | 23 | 6 | 1 |

4 of the 5 first-round `unsure` reviews would still be reviewed for `tests_miss_change`; the one sole case is r5h:1
waiting-evals. The two reasons together are sole in 21 of 107 first reviews (19.6%, $0.29 of review spend), but
the plan already rules out skipping `tests_miss_change` (about one fewer right unit per 100), and the near-term
candidate, `unsure` alone, is sole in 1 of 107 (0.9%), under the plan's ~5% line. Reading: PR-B1 as planned
(`unsure` only) is dropped unless the lead decides otherwise. (The plan's "6 of 120" counted reviews differently;
this count is first reviews with a review run on record.)

## B2: not done

B2's gate (offline replay of a focused fix-round re-review: keep 10/10 rescues and every [must] the first full
re-review flagged, median saving >= 10 s) needs a replay script and paid reviews; neither was written or priced
here. PR-B2 stays blocked until that replay runs.

## C5 base rate of "the lead did not read the diff"

Lead calls after its first delegation, per unit. Strict: no `git diff` / `git show` / `git log -p` printing
content. Broad: also no read of a changed file.

| Arm | Right units | no diff (strict) | Wrong units | no diff (strict) | p | no read (broad) right / wrong |
|---|---|---|---|---|---|---|
| ccx2 | 93 | 85 (91%) | 7 | 7 (100%) | 1.0 | 64 / 4, p = 0.68 |
| builtin | 17 | 0 | 3 | 1 | 0.15 | 0 / 1 |
| builtin2 | 17 | 17 | 3 | 3 | 1.0 | 17 / 3 |

The ccx2 lead almost never reads the diff, right or wrong, so "did not read the diff" does not tell the 7 failures
apart. By the plan's rule the conditional read-the-diff skill variant is dropped (no evidence it would change
anything that this signal could detect).

## C6 a review rule "reuse what the code base already has"

r5e:2 quota-stop-log-ccx2 failed its hidden test because the builder wrote its own `QUOTA_HINTS` in `ccx/quota.py`
while ccx classifies quota stops with `ccx/runners.py: QUOTA_HINTS` (different words), so a real quota stop could be
recorded as `{"by": "unknown"}`. The recorded first review (haiku low) did not name it. Replayed on the same tree
with today's reviewer brief, alone and with one added rule ("(e) a constant, list or helper the change defines anew
although the code base already has one for the same purpose ..."), haiku low, 3 runs each, round-5 clean room:

| Brief | Names the duplicate as [must] | Names it at all | Cost |
|---|---|---|---|
| today's | 0/3 | 2/3 (as a [note]) | $0.028 |
| + rule (e) | 3/3 | 3/3 | $0.023 |

It catches this case, but n = 3 on one case says nothing about new [must] items on right code (each one starts a
fix round, and 25 of 39 fix rounds already "fix" right code). Before it goes into the reviewer brief it needs the
review_replay controls (passed reviews) to show it does not add [must] items there.

## C2 and C4: scripts ready, not run

- **C2** `c2_lead_accept.py plan --dry-run`: ccx2 has 7 wrong units in 5 tasks (mem-report, projects-refresh,
  q-killed-spend, q-resume-session, quota-stop-log); false alarms need the 93 right units, so all 10 tasks need a
  file: est. $1.20 with sonnet (one brief-only session per task). `generate` runs each session in the round-5 clean
  room (its own empty hub, no user CLAUDE.md, skills, MCP or auto-memory), so ccx puts no shared notes into the
  writer's brief; a file whose brief did carry notes is reported (`shared_notes`) and not kept. `score` is free and
  runs each file in a temp cwd outside the repository with `CCX_REPO` on `PYTHONPATH`.
- **C4** `c4_must_filter.py --dry-run` on the fix-round replay rows: 52 rounds with [must] items (9 fail->pass,
  35 pass->pass, 8 fail->fail); median brief 10.1k characters; est. $5.50 with sonnet, $1.83 with haiku (no prompt
  cache assumed, 25k tokens of file reading per review). The 10th rescue (r5e:2 projects-refresh) had no [must]
  items, so no filter of [must] items can keep or drop it: the gate is 9/9. The gate counts every planned rescue: one
  whose filter review failed, timed out, was not parsed, lost its tree or was cut by `--budget` counts as not kept,
  so a parsed subset cannot pass it. The plan's "about $0.5" was too low.

## B3 pre-checks (no ccx/ change)

1. **`--ignore-user-config` and `$CODEX_HOME/AGENTS.md`.** `codex exec --help` (codex-cli 0.164.0): "Do not load
   `$CODEX_HOME/config.toml`; auth still uses `CODEX_HOME`". Tested at $0: a local HTTP server as the model
   provider (`-c model_provider=... base_url=http://127.0.0.1:<port>/v1`) captures the request codex would send.
   With a `CODEX_HOME` holding a marker `AGENTS.md` and a `config.toml` with a marker `developer_instructions`:
   without the flag both markers are in the request; with it only the AGENTS.md marker. **AGENTS.md is still
   loaded**; config.toml (MCP servers, hooks, memories, plugins, developer_instructions) is not.
2. **How a Codex sub-agent gets shared memory.** Not through the `ccx mem delta` SessionStart hook: under
   `CCX_ROLE=subagent` (set by ccx for every sub-agent) `mem delta` prints nothing (`ccx/commands/memory.py`), and the
   per-turn hook returns nothing for a sub-agent (`CCX_DEPTH` > 0, `ccx/commands/board.py`). The ways it does get it:
   (a) the prompt's memory line and the brief's shared notes (`_brief_notes`, I6, in `ccx/delegate.py`), which do not
   depend on Codex's config; (b) the managed memory block `ccx sync` writes into `$CODEX_HOME/AGENTS.md`
   (`ccx/sync.py`), or the person's own AGENTS.md when the snapshot is external. Both survive the lean start (1).
3. **What a lean start must inject:** nothing more for memory. It must keep `CODEX_KEEP` (today only
   `windows.sandbox`; it has no auth keys, and auth stays with `CODEX_HOME`). PR-L should still add the test the plan
   names: in lean mode the brief carries the notes and the argv for tier and `--model` routing are the same.
4. **Measured (local, $0, 3 runs each, the maintainer's real Codex home: 87 KB config.toml):**

| Start | Process start to first model request | Request body | Tools |
|---|---|---|---|
| full config | 3.9-4.3 s | 814 KB | 33 |
| `--ignore-user-config` | 0.8-1.0 s | 790 KB | 31 |
| `--ignore-user-config --disable apps` | 0.8-0.9 s | 55 KB | 9 |

The lean start saves about 3.1 s before the first request (MCP servers and hooks no longer start) and drops the
Codex memories section (~20 KB) and two MCP tools. The body barely shrinks because ~750 KB are the ChatGPT-apps
connector tool schemas (Gmail, Drive, Canva ...), which come with the login, not with config.toml. Whether those
bytes are billed as input tokens on every call (they may be cached) is not measured here: the B3 token gate still
needs the 10-run micro-benchmark. `--disable apps` for a coding sub-agent is a new, separate option worth that
benchmark; it would be default-off like the rest.
