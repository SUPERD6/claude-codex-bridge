# Measured: does delegating save the lead anything (H11, first batch), real two-way handovers (E8), built-in sub-agents on/off (F9)

English · [中文](2026-10-24-h11-e8-f9-measurements.zh.md) · 2026-10-24 · ccx 0.4.0 · claude 2.1.309 · codex-cli 0.164.0 · Windows 11

## Results first

| Question | Result | Confidence |
|---|---|---|
| H11: small tasks sent to Codex — does the lead save? | **Only if the lead trusts ccx's check.** A sonnet lead made one request fewer per task when delegating (3 → 2, 6/6 pairs, sign test p = 0.031). A haiku lead re-ran the tests itself after every delegation: same number of requests (3 → 3), plus the sub-agent's cost (median total $0.0024 → $0.0056, p = 0.008). Delegating took ~16–18 s longer (~2.5×) either way. Both arms 100% correct (14/14 pairs). | Good for tasks this small; the step to a real lead is an **estimate** |
| What would a real lead (re-reading ~220k tokens per request) save? | One request fewer ≈ 219k tokens ≈ $0.044 at Opus cache-read price, minus ~$0.003 sub-agent: **~$0.04 saved per small task, ~16 s slower**. A lead that re-checks saves no request: ~$0.003 more, ~18 s slower. | Medium-low: requests × measured median context, not run in a real long conversation |
| E8: can the next lead say where things stand and what's next from the handoff alone? | Controlled: 3/3 right (Codex → Claude clean stop, Codex → Claude killed mid-work, Claude → Codex clean stop). **The real long session (this one → Codex) was wrong at first**: the handoff's plan was stuck at its first state, so the receiver thought no experiment had run. Right after the fix. | Controlled: good; one real session only |
| F9: do built-in sub-agents actually start when on? | **0 of 5 runs started any** (on ×2, off ×2, and on with a brief that explicitly asks for one sub-agent per module). Cost ($0.0024–0.0037) and time (22–26 s) differ within noise; all correct. | Good for gpt-6-luna low; higher tiers not tried (this week's Codex quota) |

Two ccx bugs found and fixed in this PR (both in `ccx handoff --from-transcript`); six more listed in section 5.

## 1. Budget and spend

Cap: about $1 API-equivalent for all real runs; Codex gpt-6-luna low only, Claude haiku or sonnet.

| Part | Runs | Spend |
|---|---|---|
| H11 pilot | 1 pair (haiku lead) | $0.009 |
| H11 haiku batch | 8 pairs = 16 leads + 8 Codex sub-runs | $0.064 |
| H11 sonnet batch | 6 pairs + 1 single arm (stopped by its $0.5 cap) | $0.446 |
| E8 | 3 controlled handovers + 2 asks on the real session | ~$0.02 |
| F9 | 5 Codex sub-runs | $0.017 |
| **Total** | | **~$0.56** |

Leads: `total_cost_usd` reported by `claude -p`; sub-runs: AE$ from the ccx ledger.

## 2. H11: the lead does it vs the lead delegates

### Method
`scripts/eval/h11_compare.py` (tasks in `scripts/eval/tasks.py`, helpers in `scripts/eval/common.py`).
- **Tasks:** 8 checkable small Python tasks, each a freshly generated git repo (implement slugify / duration parsing /
  Roman numerals / dedupe / top words, fix pagination / interval merging, add `--json` to a CLI). Each has a visible
  test the agents see and a hidden acceptance test only the evaluator runs. `tests/test_eval_tasks.py` checks that
  the start code fails the hidden test and a reference solution passes it.
- **Pairs:** the same task twice, each time in a new scratch repo with a new headless lead (`claude -p`, slim start:
  6 tools, no MCP, a system prompt that does not change per folder — the flags ccx uses for lean Claude sub-agents).
  *self*: "do it yourself, do not delegate". *delegate*: "write a short brief and run `ccx run --to codex --model
  gpt-6-luna --effort low --mode write --new --no-ab --review off --check "python -m pytest -q" --label eval-h11:…`
  once; ccx has already re-run the acceptance command (see its check field); on failure follow up once or fix it".
  Both say "make sure the acceptance passes before you answer". Arm order alternates per pair.
- **Right or wrong:** the hidden test is dropped into the repo and the whole suite run; the delegated run's verdict is
  recorded with `ccx verify <run_id> --ok 1|0 --note "eval-h11 hidden acceptance: …"`.
- **Measured:** lead requests (API calls, deduplicated by message id), input tokens read over all requests, output
  tokens, lead $, sub-run AE$, wall time, rework (follow-ups, lead edits after delegating, failed sub-run checks).
- **Statistics:** median of paired differences, bootstrap 95% interval, exact two-sided sign test. A spend guard stops
  the batch before a new arm once `--budget` is reached.

### haiku lead, 8 pairs (self / delegate; delegate $ = lead + sub-run)

| Task | Right | Requests | Tokens read | self $ | delegate $ | s |
|---|---|---|---|---|---|---|
| slugify | ✓ / ✓ | 3 / 3 | 37,031 / 39,102 | 0.0019 | 0.0024 + 0.0048 | 9 / 26 |
| paginate | ✓ / ✓ | 3 / 4 | 37,432 / 51,871 | 0.0021 | 0.0025 + 0.0016 | 10 / 26 |
| duration | ✓ / ✓ | 3 / 3 | 37,675 / 40,045 | 0.0024 | 0.0028 + 0.0036 | 11 / 35 |
| roman | ✓ / ✓ | 3 / 3 | 37,739 / 38,996 | 0.0024 | 0.0025 + 0.0030 | 11 / 28 |
| dedupe | ✓ / ✓ | 3 / 3 | 37,886 / 39,692 | 0.0024 | 0.0025 + 0.0041 | 12 / 37 |
| intervals | ✓ / ✓ | 3 / 3 | 37,984 / 39,171 | 0.0025 | 0.0025 + 0.0030 | 12 / 29 |
| topk | ✓ / ✓ | 3 / 3 | 37,228 / 39,031 | 0.0021 | 0.0023 + 0.0018 | 10 / 29 |
| cli-json | ✓ / ✓ | 5 / 4 | 66,172 / 52,979 | 0.0032 | 0.0027 + 0.0030 | 15 / 32 |

Delegate − self: requests 0 [0, 0], p = 1.0; tokens read +1,805 [+1,187, +2,370], p = 0.07; total $ +0.0030
[+0.0020, +0.0042], p = 0.008; wall time +17.5 s [+16.7, +23.8], p = 0.008. In 8 of 8 delegations haiku read the file
and ran pytest again afterwards.

### sonnet lead, 6 pairs (a 7th stopped after its self arm at the cap)

| Task | Right | Requests | Tokens read | self $ | delegate $ | s |
|---|---|---|---|---|---|---|
| slugify | ✓ / ✓ | 3 / 2 | 33,739 / 23,190 | 0.0525* | 0.0296 + 0.0018 | 8 / 22 |
| paginate | ✓ / ✓ | 3 / 2 | 33,693 / 23,169 | 0.0312 | 0.0297 + 0.0031 | 9 / 22 |
| duration | ✓ / ✓ | 3 / 2 | 33,950 / 23,363 | 0.0328 | 0.0314 + 0.0036 | 12 / 27 |
| roman | ✓ / ✓ | 3 / 2 | 34,012 / 23,259 | 0.0329 | 0.0304 + 0.0032 | 10 / 26 |
| dedupe | ✓ / ✓ | 3 / 2 | 34,221 / 23,229 | 0.0347 | 0.0304 + 0.0035 | 11 / 28 |
| intervals | ✓ / ✓ | 3 / 2 | 34,042 / 23,142 | 0.0335 | 0.0299 + 0.0030 | 11 / 28 |

\* first run of the batch, writes the prompt cache.

Delegate − self: requests −1 [−1, −1], p = 0.031; tokens read −10,670 [−10,946, −10,537], p = 0.031; lead $ −0.0030
[−0.0136, −0.0015], p = 0.031; total $ +0.00003 [−0.011, +0.0019], p = 1.0; wall time +15.5 s [+13.5, +17.2],
p = 0.031. sonnet called `ccx run` once and answered from its JSON when the check had passed.

### To a real lead
These leads read ~11–13k tokens per request. `ccx stats --summary` measures a median of **219,465 tokens** re-read per
request of the real lead. If a real lead behaves like these: like sonnet, one request fewer ≈ $0.044 at Opus
cache-read price ($0.2/M, ccx's price table) − $0.003 sub-run ≈ **$0.04 saved per small task, 16 s slower**; like
haiku, nothing saved, ~$0.003 more, 18 s slower. This is an extrapolation, not a measurement.

### The "estimated saving" in `ccx report`
It reprices the **sub-agent's** tokens at the lead's model price, minus the sub-run and a fixed brief overhead
(currently $6.82, n = 92). The paired data say what the lead saves is the requests it does not make × its own context;
the sub-agent's tokens hardly matter (here 73–152k per sub-run, median ~93k, while doing it itself took the lead 3
requests and ~38k tokens). The two estimates can be far apart; better: requests avoided × the lead's context per
request, calibrated by A/B self-run samples (section 7). Not changed here. The eval runs (labels `eval-h11:*`,
`eval-f9:*`, `eval-e8:*`) are in the real ledger and count in that figure; filter by label to leave them out.

## 3. E8: real handovers both ways

`scripts/eval/e8_handoff.py`. **Controlled** (`run`): a scratch repo with four independent stub modules; a real
outgoing lead (headless `claude -p` or `codex exec`, session file kept) writes a numbered plan and works in order,
either told to stop after a and b, or killed after 20 s (`--cut-after 20`, a quota cut or crash). `ccx handoff
--from-transcript <from> --no-model` builds the handoff; a fresh agent of the other kind (`ccx run --mode read`,
luna low / haiku) gets only the handoff text in an empty folder, may not open files or run commands, and answers
DONE / NEXT / MISSING. Ground truth from the repo. **Real** (`ask`): the handoff built from this Claude Code desktop
session's file, given to Codex. I judged each answer and recorded it with `ccx verify`.

| # | Direction | Case | Receiver's position | Next | Verdict | Missing |
|---|---|---|---|---|---|---|
| 1 | Codex → Claude | clean stop after a, b | a, b + tests done | c, d + tests | ✓ | plan not found; test results only as the outgoing lead's claim |
| 2 | Claude → Codex | clean stop after a, b | same | same | ✓ | same |
| 3 | Codex → Claude | killed at 20 s, no last message | a, b done, from changed files + git state | c, d | ✓ | "where it stopped" empty; whether a, b's tests pass unknown (the receiver said so) |
| 4 | real Claude session → Codex | before the fix | "no experiment reported" | start H11/E8/F9 | ✗ | plan stuck at step 1 (bug 2); results only in tool output |
| 5 | same | after the fix | H11/E8/F9 done, writing the report | report, checks, PR | ✓ (first step slightly stale) | "where it stopped" is the last chat text, a few steps behind; no measurements |

Code alone (no model tokens) was enough in the simple cases, even the kill without a last message (changed files +
git state). The real session showed a stale plan (fixed) and that results are not carried over (not fixed). The
controlled outgoing leads were headless; Codex headless sessions have `originator = codex_exec` and are skipped when
`--from-transcript codex` picks automatically, so `--session <id>` is needed. A real Codex *desktop* → Claude handover
is still not done: the Codex desktop sessions on this machine belong to other projects, and building a handoff there
would write `.ccx/` into another project.

## 4. F9: built-in sub-agents on / off

`scripts/eval/f9_subagents.py`: the four-module task, a new scratch repo each time, `ccx run --to codex --model
gpt-6-luna --effort low --mode write --check "python -m pytest -q"`: on (default) ×2, off (`--no-subagents`) ×2, and
on with "spawn one sub-agent per module" in the brief ×1. Whether children started, from two sources: the ledger's
`codex_children`, and the session files (child rollouts whose parent is the run's session; `spawn_agent` calls in its
rollout). codex-cli 0.164 calls tools through a code-mode `exec` tool, so a spawn shows as `tools.spawn_agent(` inside
an `exec` call; every rollout contains the tool's *definition*, which is not a call (my first counter got that wrong).

| Arm | # | Right | AE$ | s | children (ledger / files / spawn calls) |
|---|---|---|---|---|---|
| on | 1 | ✓ | 0.0035 | 25.1 | 0 / 0 / 0 |
| off | 1 | ✓ | 0.0037 | 24.9 | 0 / 0 / 0 |
| on | 2 | ✓ | 0.0037 | 21.8 | 0 / 0 / 0 |
| off | 2 | ✓ | 0.0024 | 21.8 | 0 / 0 / 0 |
| on + explicit ask | 1 | ✓ | 0.0035 | 25.8 | 0 / 0 / 0 |

Why: codex-cli 0.164 gives the model a `<multi_agent_mode>` developer message: do not spawn sub-agents unless the user
or AGENTS.md / a skill explicitly asks. A neutral brief is no such ask; with the explicit ask, luna low still wrote all
four modules in one patch. At the tier this week allows, F9's "on by default" behaves as off; the `agents.*` keys,
concurrency cap and spend watchdog are not exercised. Claude sub-agents start slim with `Read,Grep,Glob,Edit,Write,
Bash` and no `Agent` tool, so "on" cannot start any there either (the code comments say so; the docs don't).

## 5. ccx problems found

| # | Problem | Status |
|---|---|---|
| 1 | **`--from-transcript` in a worktree picks the wrong session.** Claude Code's worktrees live inside the main checkout (`.claude/worktrees/<name>`); the project layer is the main checkout's by design, but the handoff also looked for the lead's session file and read git state there, and so took **another session's** transcript. | **Fixed**: look in the lead's own folder (cwd) first, then the project root; git state from where the session was found. Test added (fails before, passes after). |
| 2 | **The desktop plan tool's updates were ignored.** Claude desktop's `update_plan` sends the whole list once, then only `advance` / `done` / `start`; the reader took only whole lists, so the plan stayed at its first state. | **Fixed**, with a test. |
| 3 | One `.ccx/handoff.md` per project: with parallel sessions the last writer wins and overwrites a handoff not yet seen (a copy stays in `handoffs/`). Problem 1's run overwrote another session's 17:43 handoff; I restored it from `handoffs/` and removed my extra journal line. | Not fixed. Suggest: don't overwrite an unseen handoff, or one file per session. |
| 4 | A plan written in a normal message ("Plan: 1. … 2. …") isn't found ("no plan list found"). | Not fixed. Fallback: a numbered list in assistant text when no plan tool was used. |
| 5 | The handoff carries no results: "where it stopped" is the last chat text (can lag), experiment numbers and ccx run results live only in tool output. | Not fixed. Could add the session's recent `ccx run` ids, check results and summaries (already in the ledger). |
| 6 | F9 "on by default" starts nothing with codex-cli 0.164 + luna low; slim Claude sub-agents have no Agent tool. | Not fixed; the docs should say so. |
| 7 | The report's "estimated saving" is not what was measured to save (section 2). | Not fixed. |
| 8 | "On disk now": `strip()` drops the first `git status --short` line's leading space (` M a.py` reads as staged `M a.py`). | Not fixed (cosmetic). |

## 6. Limits
- **Tasks too small and easy:** both arms always right, so correctness and rework could not differ (0 follow-ups, 0
  lead edits after delegating, 0 failed sub-run checks). Self needs 3 requests, delegating at least 2: at most one
  request to save. Larger tasks (10+ self requests) are where a bigger difference could show.
- **Not a real lead:** headless, slim, ~12k context per request, vs a long conversation (median 219k) with Opus. The
  dollar figures for a real lead are extrapolated.
- **Small samples:** haiku 8 pairs, sonnet 6; E8 3 controlled + 1 real session; F9 5 runs. The sonnet request
  difference is 6/6 consistent (p = 0.031); total $ is not.
- **Cheapest tier only:** Codex luna low (quota); conclusions may change with higher tiers, F9 especially.
- **Prompt choice matters:** the delegate prompt says ccx already re-ran the check; that may make sonnet skip
  re-checking, while haiku re-checked anyway. A design choice, not a neutral measurement.
- **Time:** delegate wall time includes the sub-run (13–23 s on its own in the haiku batch, ledger `seconds`).

## 7. A week of collection
1. **A small controlled batch each day** (~$0.05): `python scripts/eval/h11_compare.py run --pairs 4 --tag $(date
   +%Y%m%d) --budget 0.1`, alternating haiku / sonnet leads; add 3–4 medium tasks that take a lead 8+ requests
   (several files, reading first), otherwise "at most one request saved" is all that can show. After a week:
   `python scripts/eval/h11_compare.py summary`.
2. **A/B self-run samples in real work:** ccx already has it: with `ccx config set defaults.ab_self_rate 0.2`,
   routing picks 20% of tasks it would delegate for the lead to do itself, and `ccx ab done <id> --ok 1|0` records
   what the lead used (`selfrun` events). Compare "lead requests × context" with delegated tasks of the same
   difficulty after a week.
3. **A verdict for every delegated task:** `ccx verify <run_id> --ok 1|0`, or at least the session-start
   `ccx verify --sweep`. Before this run the ledger had 2 human verdicts; now 31 (25 from this run).
4. **E8:** at every real switch of leads (quota out, changing tools), build the handoff with `--from-transcript`, have
   the new lead first write where it thinks things stand and what's next, compare with the old session, `ccx verify`.
5. **F9:** when the Codex quota allows, `python scripts/eval/f9_subagents.py run --model gpt-6.1-sol --effort medium`;
   if still nothing starts, document "allowed, but Codex 0.164 rarely starts any by itself".

## 8. Reproduce
Logged-in `claude` and `codex` CLIs; run the scripts with a Python that has pytest (it is put first on the agents'
PATH, so the agents use it in the scratch repos).

```
python scripts/eval/h11_compare.py list
python scripts/eval/h11_compare.py run --pairs 8 --tag haiku1 --budget 0.6
python scripts/eval/h11_compare.py run --pairs 8 --tag sonnet1 --lead-model sonnet --lead-effort medium --lead-budget 0.3 --budget 0.5
python scripts/eval/h11_compare.py summary --tag haiku1
python scripts/eval/e8_handoff.py run --from codex --to claude [--cut-after 20]
python scripts/eval/e8_handoff.py run --from claude --to codex
python scripts/eval/f9_subagents.py run --repeat 2 --explicit 1
python scripts/eval/f9_subagents.py summary
```

Raw results: `.ccx/eval/{h11,e8,f9}/results.jsonl` (not in git: they hold local paths). Verdicts are in the ccx ledger
under the labels `eval-h11:*`, `eval-e8:*`, `eval-f9:*`.
