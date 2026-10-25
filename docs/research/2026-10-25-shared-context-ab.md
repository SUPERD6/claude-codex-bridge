# Shared work context: A/B on real CLIs (2026-10-25)

English · [中文](2026-10-25-shared-context-ab.zh.md)

**Question.** When a lead delegates a task whose brief leans on something it and its person settled in their
conversation ("the way we agreed"), does attaching the lead's recent work (`ccx run --context on`) make the
sub-agent get it right, at what cost, and does it hurt when the brief is already complete?

**Answer, for this design.** Yes, by a wide margin: first-try right 36/36 with the context against 7/36 without
(paired, McNemar exact p ≈ 4e-9), no rework instead of 29 reworks, and 63 % less money in all. On the neutral task
both arms were 6/6; the context added about $0.0002 a run on Codex and nothing measurable on DeepSeek. This is the
best case for the feature by construction (below): it shows the mechanism delivers what was settled, not how often
real work depends on it.

## Design

- **Script:** `scripts/eval/shared_context_ab.py` (data: `docs/research/data/2026-10-25-shared-context-ab.json`).
- **Agents:** Codex `gpt-6-luna` low (codex-cli 0.164.0); DeepSeek `deepseek-flash` low through `dsh` 0.2.1-rc.3
  (pay per token, no cap, every run in the ledger). Both `--mode write --new --review off --no-escalate
  --no-subagents`, throwaway hub.
- **Tasks:** 6 "settled" tasks, each brief pointing at a decision that is only in the lead's conversation (empty
  mean returns None; slug style `Hello_World`; timeout 45 s; loader named `load_rows`; dates DD/MM/YYYY; negative
  quantity clamped to 0 with a warning) + 1 neutral task with a complete brief. 5 of the 6 settled tasks also have
  an earlier option the person reversed (raise ValueError, hyphens, 30 s, read_rows, raise).
- **Lead conversation:** a fake Claude Code session file (~10 turns: the ask, unrelated chatter, the reversed
  option, the decision, a plan update and an edit), found through `CCX_LEAD_SESSION`. The project folders sit away
  from the folder holding these files, so a sub-agent that looks around can't find them.
- **Arms:** `--context on` vs `--context off`, same task, same agent, same repetition = one pair; 3 repetitions →
  7 × 2 agents × 3 = 42 pairs, 84 runs.
- **Right or wrong:** a hidden pytest test the agents never see. A failed run gets one rework round
  (`ccx resume`) with the failing assertion lines, as a lead would send back; **rework rate** = share of runs that
  needed it. Money = the run plus its rework (ledger, API prices; DeepSeek is real money).

## Results

| Scope | Arm | First try right | Rework | Right after one rework | Money |
|---|---|---|---|---|---|
| Settled tasks, both agents | off | 7/36 (19 %, CI 10–35 %) | 29 | 23/36 | $0.2063 |
| | **on** | **36/36** (100 %, CI 90–100 %) | **0** | 36/36 | **$0.0768** |
| Codex luna low | off | 2/18 | 16 | 11/18 | $0.0632 |
| | on | 18/18 | 0 | 18/18 | $0.0430 |
| DeepSeek flash low | off | 5/18 | 13 | 12/18 | $0.1432 |
| | on | 18/18 | 0 | 18/18 | $0.0339 |
| Neutral task, both agents | off | 6/6 | 0 | 6/6 | $0.0109 |
| | on | 6/6 | 0 | 6/6 | $0.0122 |

Paired: only-on-right 29, only-off-right 0 (Codex 16 / 0, p = 3e-5; DeepSeek 13 / 0, p = 2.4e-4). Per task, off:
1/6, 1/6, 1/6, 0/6, 3/6, 1/6 (the date format was guessed right half the time); on: 6/6 each.

The context attached was 1,130–1,388 characters (~300–350 tokens) for these short conversations.

**Total spend of the A/B: $0.3063** at API prices; DeepSeek's real money $0.1856, Codex $0.1207 API-equivalent
inside the subscription.

## What the arm without context did

Without the context the agents behaved well but could not know: they either stopped and asked (Codex and DeepSeek
on the empty mean, the date format, the loader name: "no record of the earlier agreement in the workspace") or made
a reasonable but wrong guess (timeout 10 s, `load_csv`, lowercase-hyphen slugs, raise ValueError on negative
quantities). Even with the failing assertion sent back, 13 of 29 reworks still failed (mostly runs that had stopped
to ask and then misread the assertion, or kept their own convention).

## Limits — read before quoting the numbers

- **Best case by design.** Every settled task can only be done right with the decision; in real delegation most
  briefs say what is needed. The number to watch in real use is how often a brief leans on the conversation, which
  this does not measure.
- **Short, clean lead conversations** (~10 turns, the decision in plain words near the end). Real conversations
  are long and noisy; the extractor keeps the last 5 asks and 8 "settled" sentences, picked by keywords. A decision
  worded without those words, or older than the last 5 asks, can be missed. A look at real sessions (`ccx peek` on
  this project's coordinating session) showed both kinds of noise: status sentences picked as "settled" and, before
  a fix in this PR, scratch files outside the project and table rows.
- **Fake lead sessions, real sub-agents.** The lead side was a written Claude Code session file, not a live lead;
  `ccx peek` and the hook line were checked on real Claude, Codex and dsh session files, but not in an A/B.
- **One model each, low effort, 3 repetitions.** The 95 % intervals are wide for the per-agent rows.
- **Not measured:** a lead that is Codex or DeepSeek (only a Claude lead session was used); the per-turn hook line
  ("what the others did") in a live desktop session (Codex desktop hooks are still unverified, H7).

## Reproduce

```bash
CCX_DSH_BIN=/path/to/dsh.cmd python scripts/eval/shared_context_ab.py run --out /tmp/scab --reps 3 --jobs 6
python scripts/eval/shared_context_ab.py summary --out /tmp/scab
```
