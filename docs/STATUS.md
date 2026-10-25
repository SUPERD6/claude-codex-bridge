# Status

English · [中文](STATUS.zh.md) · updated 2026-10-25 · version 0.5.0 · 523 tests

One page on purpose: whatever an agent reads at start-up it re-reads on every later turn. Older pages, the full
confidence table, acceptance checks and the done list are in [STATUS-archive.md](STATUS-archive.md); what changed
is in [CHANGELOG.md](../CHANGELOG.md). Keep this page short: when something is done, say so in one line here and
put the detail in the changelog. Only the lead session edits this page; PRs add a `changes/<PR>.md` instead.

## Now

0.5.0 holds everything since 0.4.0 (PRs up to #104), grouped by theme in the CHANGELOG. What the measurements
say, each from a raw record:

| Result | Numbers | Source |
|---|---|---|
| Shared work context (`ccx run --context`) | right the first time 36/36 with it vs 7/36 without (McNemar p ≈ 4e-9), 0 vs 29 reworks, 63 % less spend in all; best case by design | [shared-context A/B](research/2026-10-25-shared-context-ab.md) |
| Project memory reaches the sub-agent | hidden test 9/9 with the note vs 0/9 without (Holm p = 0.016) | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.5 |
| Hub memory (note only in the shared hub) | 9/9 vs 0/9 (McNemar p = 0.0039); control is round 1's arm, one note per hub | CHANGELOG 0.5.0 (PR #45); no separate report |
| Cheap model is near the ceiling (round 2) | 22 trap tasks, Codex luna low right 47/49; every "more right" gap below comes from one task (inventory), so none is significant | [round 2](research/2026-10-25-seven-cores-r2.md) |
| Review (round 2) | off 33/36, on 36/36 (p = 0.25), caught the real bug every time, +$0.004 a task; the old `--review auto` never fired (fixed in #103, real trigger rate not measured yet) | same, 4-C |
| Dividing the work (round 2) | one cheap model 12/14; plan → build → accept 14/14 at 38.7× the spend; draft + checked draft 14/14 at 20×; cheap model + cheap review gets the same at ~7 % of `ccx way`'s cost | same, 4-B |
| Parallel runs (round 2) | ten pieces: 1 run 68–83 s, 10 runs 29–31 s, but tokens 210k → 980k (~93k start-up per run): faster, not cheaper | same, §5 |
| Delegating (round 1) | the lead's tokens −32 % but total spend the same (ratio 1.02) | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.2 |
| Routing (rounds 1–2) | no gain in round 1 (21/21 the fixed model); round 2 as right as fixed sonnet, its saving came from the test hub not knowing the quota | round 1 §2.3, round 2 4-D |
| More accurate with use | no evidence yet (everything was right, so nothing to learn from) | round 2 §6 |

So the default shape is **one cheap model plus another vendor's cheap review**; split or parallel only when speed
is wanted (the `project-manager` skill, #102). Running: the H11 week-long `ccx trial` (ends 2026-10-31).
Since the 0.5.0 tag: `q resume` continues the killed run's session instead of redoing it (#105); real-machine checks
of worktrees, `ccx batch`, `--fork` and `ccx say --now` done on 2026-10-25 (about $0.06).

## Next three

1. **Going public** (ask the person first): demo GIF, a public benchmark from the round-1/2 tasks, then the launch.
2. **Coordinator K4–K6**: autonomy levels, work sent in from outside (phone, a private GitHub issue), the
   coordinator board. K7 (an avatar from a separate desktop-pet project) waits for that project.
3. **Measure what is still unproven**: the new `--review auto` trigger rate, and whether routing learns from the
   person's own work (H11 trial results after 2026-10-31).

## How sure we are (short)

**real** = run on a real Windows machine with logged-in CLIs; **fake** = tests with fake CLIs only.

- **real**: delegation both ways, `--check`, review (rounds 1–2), `ccx way`, `ccx stop` → `ccx resume` and killed
  runs counted, archiving after a run, DeepSeek leading, a three-vendor `ccx discuss`, the board via
  `ccx say --resume`, shared work context A/B, project catalog scan, the plugin marketplace install (Claude Code,
  from a temporary config), `ccx ui` hiding tests, a 3-task `ccx batch` (#100), non-ASCII paths, no console pop-ups, Codex hooks on Windows (H7,
  #82 + #92), the queue killed and resumed, worktree delegation with `ccx undo`, a parallel 3-run batch (Codex +
  dsh), `--fork` (the forked run knew what only the lead's session held), `ccx say --now` and the per-turn hook in
  the interactive Codex CLI, dsh archiving queued while the app is open and written after it is quit.
- **fake only**: quota fallback, seats, Gemini CLI, a real quota stop.
- **not verified**: `ccx say --now` in the Codex desktop app's own window; the Codex rule from
  `ccx doctor --codex-rule`; the dsh app's own later writes after a queued archive; the Codex plugin from a GitHub address; own sub-agent limits
  live (F11 did not fire: no agent started sub-agents even when told to); the new `--review auto` trigger rate;
  suggested-note rules (13/30 on a held-out set); routing beyond the evaluation tasks.
