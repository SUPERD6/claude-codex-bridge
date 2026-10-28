# Offline experiments C1-C6 and the B3 pre-checks (report)

English · [中文](offline-experiments.zh.md) · 2026-10-28 · ccx after main `0837da1` (#152) · codex-cli 0.164.0 · Windows 11

What this is: the cheap experiments of the improvement plan's group C (no paid CLI, or a few cents) run on the
round-5 development records (r5c..r5h: 180 unit trees, 100 ccx2 units with a lead stream), plus the checks the plan
requires before B3 (a lean Codex start for tier-routed low runs) may be built. Every number is from the development
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
| -  | `offline_common.py` | - | shared helpers |

Records are read from the system temp folder (`%TEMP%/r5c..r5h`) or `CCX_REPLAY_RECORDS`; results rows from
`.ccx/eval/r5/results.jsonl`.

## Results at a glance

| # | Question | Answer | Plan's gate | Next |
|---|---|---|---|---|
| C1 | Does `ccx namecheck` raise false alarms? | 0 false of 8 hits in changed code (180 final trees + 183 reviewed trees), 0 false in 681 whole files + 28 external files + this repo (214) | FP = 0: passed | before/after comparison (tiers.toml) before `fail` |
| C3 | Can ccx reuse the builder's passing check? | 121 exact matches, 4 builder-pass/ccx-fail (all the pre-#147 quoting bug), check median 4.8 s in no-review runs | measure only | no runtime switch |
| C5 | Does "lead did not read the diff" separate right from wrong? | no: 85/93 right and 7/7 wrong ccx2 units had no `git diff`; p = 1.0 | must separate | drop the skill variant |
| C6 | Does a "reuse existing constants" review rule catch r5e:2? | rule 3/3 as [must], today's brief 0/3 as [must] (2/3 as a note) | must catch | candidate; needs controls |
| C2 | Lead-written acceptance tests | not run (5 tasks with wrong units, 10 tasks to cover, est. $1.20) | catch >= 2, FP <= 3% | needs approval to spend |
| C4 | Strong reviewer filters [must] | not run (52 rounds: 9 fail->pass, 35 pass->pass; est. $1.83-5.50) | keep all rescues | over the $0.5 the plan assumed |
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
| changes, reviewed trees | 183 trees | 7 | 7 | 0 | 6 |
| whole files, final trees | 681 distinct | 1 (the same bug) | 1 | 0 | 1 |
| external + this repo | 242 | 0 | - | - | - |

The 8 change hits are 6 distinct bugs in 5 units: `load_config` / `cfg` used but never bound in `cmd_mem`
(projects-refresh, 4 units; all inside `except Exception: pass` on the session-start path, so no test sees a
NameError, only a missing refresh), and `_caller` never imported in `delegate.py` (r5g:1 mem-report; outside any
try, it would crash every brief that gets notes). Only r5c:2 projects-refresh-ccx2 kept its bug to the end (that
unit is wrong); the other five were gone after a fix round. The reviewers named the undefined name in 2 of the 6
reviewed trees; 4 reviews missed it.

Reading against the plan's rule: no false positive anywhere, so the next step is the before/after comparison that
`config/tiers.toml` already asks for before `namecheck = "fail"`. A `swallow` mode is not needed (it was meant for
false alarms outside swallow blocks; there are none). Whether `warn` already makes the lead or reviewer fix a hit
cannot be read from r5 (no namecheck in those runs) and needs the hold-out records.

## C3 reuse of the builder's check

176 write runs with `--check` (all Codex builders; review children left out). After its last file edit the builder
ran ccx's own check command (same text up to quotes and spaces):

| Builder's last run | Runs | ccx's check passed | failed |
|---|---|---|---|
| exact command, passed | 125 | 121 (match) | 4 |
| exact command, failed | 11 | 8 | 3 |
| other test command passed | 27 | - | - |
| no test after the last edit | 13 | - | - |

The 4 "builder passed, ccx failed" are all `ERROR: file or directory not found: or`: ccx's own run of a quoted
`-k "a or b"` on Windows, fixed by #147 (all r5 records predate it). The 8 "builder failed, ccx passed" are the
builder's sandbox (kill/process tests that fail inside Codex's sandbox), so a builder failure is no signal either.
Seconds: runs without a review spend a median 4.8 s on the check (56 runs, 474 s in all; per unit median 2.5 s);
the 30 of them that reuse could have skipped add up to 328 s over 100 units. Following the plan: measurement only, no
runtime switch (it would need 0 mismatches after #147 and a no-review check median above 30 s).

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
  file: est. $1.20 with sonnet (one brief-only session per task). `score` is free and runs each file in a temp cwd
  outside the repository with `CCX_REPO` on `PYTHONPATH`.
- **C4** `c4_must_filter.py --dry-run` on the fix-round replay rows: 52 rounds with [must] items (9 fail->pass,
  35 pass->pass, 8 fail->fail); median brief 10.1k characters; est. $5.50 with sonnet, $1.83 with haiku (no prompt
  cache assumed, 25k tokens of file reading per review). The 10th rescue (r5e:2 projects-refresh) had no [must]
  items, so no filter of [must] items can keep or drop it: the gate is 9/9. The plan's "about $0.5" was too low.

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
