# Status

English · [中文](STATUS.zh.md) · updated 2026-10-29 · version 0.5.0 + Unreleased (#105–#177) · 1376 tests passing (2 skipped)

One page on purpose: whatever an agent reads at start-up it re-reads on every later turn. Older pages, the full
confidence table, acceptance checks and the done list are in [STATUS-archive.md](STATUS-archive.md); what changed
is in [CHANGELOG.md](../CHANGELOG.md). Keep this page short: when something is done, say so in one line here and
put the detail in the changelog. Only the lead session edits this page; PRs add a `changes/<PR>.md` instead.

## Now

**Hold-out run hc1 (2026-10-29, pre-registered):** on 10 tasks not used while building ccx, ccx was not seen to be
less right (29/30 vs self 29/30 and the built-in sub-agent's default usage 27/28) and cost $0.063 per success, about
30 % / 39 % less; about 3× self's wall time. Limits: builtin2 (lean recipe) not in the run, this repository's tasks
may leak answers (external tasks only: 15 % / 42 %), 10 tasks, one lead model. The 2026-10-26 page is in the archive.

| Result | Numbers | Source |
|---|---|---|
| Hold-out confirmation (hc1) | self 29/30 $0.090 21 s; built-in default usage 27/28 $0.103 123 s; ccx 29/30 $0.063 61 s; paired CIs exclude 0; a pointwise rule, not a statistical non-inferiority test | [hc1](research/2026-10-29-hc1-holdout.md) |
| Shared work context (`ccx run --context`) | right the first time 36/36 with it vs 7/36 without (McNemar p ≈ 4e-9), 0 vs 29 reworks, 63 % less spend in all; best case by design | [shared-context A/B](research/2026-10-25-shared-context-ab.md) |
| Project memory reaches the sub-agent | hidden test 9/9 with the note vs 0/9 without (Holm p = 0.016) | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.5 |
| Review (round 2) | off 33/36, on 36/36 (p = 0.25), caught the real bug every time, +$0.004 a task | [round 2](research/2026-10-25-seven-cores-r2.md) 4-C |
| Round 5, dev set | after the fixes ccx 18–20/20 at $0.116–0.135 per success; builtin2 (lean recipe) 17/20 at $0.114; self 19/20 at $0.211; ccx 2.5–2.8× self's wall time | [round 5](research/2026-10-26-r5.md) §7 |

Since the 0.5.0 tag (#105–#177, all under Unreleased in the CHANGELOG): coordinator autonomy, intake and board
(#109–#111), memory L1–L4, L6, L7 (#112–#113), round 3–5 fixes, the PM review's honest story and flows (#176–#177).
Running: the H11 week-long `ccx trial` (ends 2026-11-01).

## Next three

1. **Release 0.6.0, PyPI, launch**: waits for the person's yes (version bump, tag, publish).
2. **H11 trial ends 2026-11-01**: read it; decide `memory.by_kind` / `memory.start_scene`.
3. **Wrap-up**: a token-usage view in `ccx ui`; context-efficiency measurements (sub-agent start-up ~93k tokens a
   run; batching small pieces into one run); mark unverified paths as experimental.

## How sure we are (short)

**real** = run on a real Windows machine with logged-in CLIs; **fake** = tests with fake CLIs only.

- **real**: delegation both ways, `--check`, review (rounds 1–2), `ccx way`, `ccx stop` → `ccx resume` and killed
  runs counted, archiving after a run, DeepSeek leading, a three-vendor `ccx discuss`, the board via
  `ccx say --resume`, shared work context A/B, the hold-out run hc1 (90 units, three arms), project catalog scan,
  the plugin marketplace install (Claude Code, from a temporary config), `ccx ui` hiding tests, a 3-task
  `ccx batch` (#100), non-ASCII paths, no console pop-ups, Codex hooks on Windows (H7, #82 + #92), the queue killed
  and resumed, worktree delegation with `ccx undo`, a parallel 3-run batch (Codex + dsh), `--fork` (the forked run knew
  what only the lead's session held), `ccx say --now` and the per-turn hook in the interactive Codex CLI, dsh
  archiving queued while the app is open and written after it is quit.
- **fake only**: quota fallback, seats.
- **not verified**: Gemini CLI and a real quota stop (fake tests only); real runs on macOS and Linux (CI only);
  `ccx say --now` in the Codex desktop app's own window; the Codex rule from `ccx doctor --codex-rule`; the dsh
  app's own later writes after a queued archive; the Codex plugin from a GitHub address; own sub-agent limits live
  (F11 did not fire); the new `--review auto` trigger rate; a hook timeout in a real session; `ccx intake` against
  real GitHub; L2 auto-merge end to end; routing beyond the evaluation tasks.
