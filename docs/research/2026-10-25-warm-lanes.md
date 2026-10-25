# Warm lanes: how much continuing a warm session saves over a fresh one per piece (report)

English · [中文](2026-10-25-warm-lanes.zh.md)

2026-10-25 · `ccx batch --lanes N` (`ccx/lanes.py`) · script `scripts/eval/warm_lanes.py` · spent $0.25

## In short

| Question | Result |
|---|---|
| How much less does a continued piece read | Fresh (uncached) input falls from ~21k to 2k–5k per piece (−80–90%); cache reads stay at ~80–110k |
| Cheaper? | **About 40% cheaper than a fresh session per piece** (median sub-agent spend $0.020 vs $0.032), but **still 4–5× one run doing all ten pieces** ($0.004) |
| Fewer tokens? | **Not by count**: 0.94–1.21M in all, about the same as ten parallel runs (0.99–1.16M). Codex re-reads its system prompt and tool definitions from the cache on every request; continuing only saves the fresh part |
| Faster? | **Slower**: 2 lanes 97–101 s, 3 lanes 82–93 s; ten parallel runs 28–43 s; one run doing all ten 69–100 s. Pieces in a lane go one after another; a continued piece itself is ~25% faster (13–16 s vs 18–25 s) |
| Right? | 10/10 in every arm and round, no merge conflicts |
| Default | Stays off (`[lanes] default = 0`). The lead decides after the H11 trial ends on 2026-11-01; on this data, **turning it on by default is not recommended** |

## 1. Setup

Round 2's PAR10 task: ten independent small modules, each a function plus tests, judged by a hidden test
(`scripts/eval/tasks_r2.py`). Codex held to `gpt-6-luna` low; each unit in its own throwaway hub (`CCX_HUB`), A/B
self-runs off; check `python -m pytest -q`, `--review` at its default auto. Two rounds per arm (n = 2).

| Arm | What |
|---|---|
| p1 | one `ccx run` with the brief for all ten pieces (`--no-subagents`) |
| p10 | `ccx batch`, one run per piece, all at once, one worktree each |
| l2 / l3 | `ccx batch --lanes 2/3`, one run per piece in 2/3 lanes; a lane's first piece starts a session, later ones continue it (own `--check`, own ledger row, one commit per piece in the worktree); lanes run in parallel |

Round 1 of l2 used the first cap (a lane's cumulative 400k tokens, which cut it after 4–5 pieces); after seeing the
data it became per piece (200k), used for round 2 and for l3. Both caps changed sessions about every five pieces.

## 2. Results

| Arm | Right | Wall (s) | Tokens | Total USD | of which review | Sub-agent work |
|---|---|---|---|---|---|---|
| p1 | 10/10, 10/10 | 69 / 100 | 193k / 265k | 0.011 / 0.091 | 0.007 / 0.086 | **0.0034 / 0.0051** |
| p10 | 10/10, 10/10 | 28 / 43 | 990k / 1163k | 0.028 / 0.038 | 0 / 0.003 | 0.028 / 0.035 |
| l2 | 10/10, 10/10 | 101 / 97 | 1024k / 942k | 0.022 / 0.018 | 0 / 0 | 0.022 / 0.018 |
| l3 | 10/10, 10/10 | 93 / 82 | 932k / 1215k | 0.022 / 0.023 | 0.004 / 0 | 0.019 / 0.023 |

p1 round 2's $0.086 is a `--review auto` review by the other vendor (one large change), not the work; compare the last
column for delegation.

l2 round 1 piece by piece (ledger):

| Pieces | Continued | Fresh in | Cache read | Out | USD |
|---|---|---|---|---|---|
| 3 that started a session | no | 20.5–21.6k | 75–81k | 0.6–1.0k | $0.0032–0.0034 |
| 7 continued | yes | 1.7k–5.4k | 85–116k | 0.5–0.9k | $0.0015–0.0020 |

## 3. What it means

- **Most of the ~93k "start-up" is per request, not per session.** Every Codex request carries the system prompt, the
  tool definitions and the history, mostly from the cache. Continuing cuts a piece's fresh reads from ~20k to a few
  thousand and halves its price, but the token count stays, and grows as the session does.
- **What saves is fewer runs, not continued sessions.** One run doing all ten (p1) costs a fifth of a warm lane and is
  faster. Lanes help only when pieces **must** be separate runs: their own `--check`, undo and verdict, or pieces that
  arrive in a queue over time. There they save ~40% over a fresh session per piece, at the price of going in order.
- A cap on a lane's token count is dominated by cheap cache reads, so the cap is per piece (`max_tokens` = what one
  piece used), plus `max_blocks` (5).

## 4. Recommendations

1. Keep it off by default, also after the trial.
2. For many tiny pieces, the lead (`project-manager`, `task-split`) should first merge what can go together **into one
   brief for one run** (p1, or round 2's p3) instead of starting many runs; keep `--lanes` for pieces that each need
   their own check or undo.
3. A possible third way: a lane that does not continue a session but sends its pieces as one brief to one run, with
   ccx running each piece's `--check` afterwards. Not built or measured here.

## 5. Not verified

- n = 2, descriptive only, no statistical test; one kind of task (ten small modules).
- Codex luna low only; how much continuing saves on Claude (5-minute / 1-hour cache, paid cache writes) or DeepSeek is
  not measured.
- `ccx q run --lanes` is tested with fake CLIs only.
- On real CLIs only the `max_blocks` change of session was seen; the change after a failed piece is fake-CLI only.
- One commit per piece was seen for real (all lane branches merged back without conflicts); undoing one piece with
  `git revert` was not tried for real.
