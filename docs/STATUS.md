# Status

English · [中文](STATUS.zh.md) · updated 2026-10-25 · version 0.5.0 · 495 tests

One page on purpose: whatever an agent reads at start-up it re-reads on every later turn. Older pages, the full
confidence table, acceptance checks and the done list are in [STATUS-archive.md](STATUS-archive.md); what changed
is in [CHANGELOG.md](../CHANGELOG.md). Keep this page short: when something is done, say so in one line here and
put the detail in the changelog. Only the lead session edits this page; PRs add a `changes/<PR>.md` instead.

## Now

0.5.0 holds everything since 0.4.0 (PRs up to #93) (see the CHANGELOG, grouped by theme: save, check, split, share, control, Windows).
What the measurements say, each from a raw record:

| Result | Numbers | Source |
|---|---|---|
| Shared work context (`ccx run --context`) | right the first time 36/36 with it vs 7/36 without (McNemar p ≈ 4e-9), 0 vs 29 reworks, 63 % less spend in all; best case by design | [shared-context A/B](research/2026-10-25-shared-context-ab.md) |
| Project memory reaches the sub-agent | hidden test 9/9 with the note vs 0/9 without (Holm p = 0.016) | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.5 |
| Hub memory (note only in the shared hub) | 9/9 vs 0/9 (McNemar p = 0.0039); control is round 1's arm, one note per hub | CHANGELOG 0.5.0 (PR #45); no separate report |
| Delegating (round 1) | the lead's tokens −32 % (median 35.6k → 24.3k) and one request fewer, but total spend the same (ratio 1.02), total tokens 3.3×, ~23 s slower | [seven-cores A/B](research/2026-10-24-seven-cores-ab.md) §2.2 |
| Routing (round 1) | no gain: it picked the fixed arm's model 21/21 times | same, §2.3 |
| Review (round 1, then fixed) | round 1: 34× the cost, no gain, missed the same bug 3×; after the fix (cheap other-vendor reviewer, requirement by requirement) the fix round passed the hidden test 3/3 at $0.004–0.009 a review | same, §2.4 and §4 item 3 |

Running: the seven-cores **round 2** A/B (division of work and parallel scale; session ccx-eval-r2) and the
H11 week-long `ccx trial` (ends 2026-10-31).

## Next three

1. **K3, the coordinator skill**: a skill for the lead session that coordinates the others.
2. **Round 2 A/B** (division of work, parallel scale) — finish, report with raw data, and act on it (including
   whether the weak-evidence review, H13, catches more wrong work).
3. **Getting ready to go public**: install from the plugin marketplace, a narrower README, a demo GIF, a public
   benchmark. Then tag v0.5.0 and the GitHub Release (the person's go-ahead).

## How sure we are (short)

**real** = run on a real Windows machine with logged-in CLIs; **fake** = tests with fake CLIs only.

- **real**: delegation both ways, `--check`, review (new defaults, 3 runs), `ccx stop` → `ccx resume` and killed
  runs counted, archiving after a run, DeepSeek leading (dsh and Claude Code on a DeepSeek model), a three-vendor
  `ccx discuss`, the board via `ccx say --resume` (Codex, dsh), shared work context A/B, project catalog scan
  (31 projects), non-ASCII paths, no console pop-ups, the release preflight (Codex only, $0.013), Codex hooks on Windows (H7, #82 + #92: a new Codex
  conversation showed "From ccx (shared memory and delegated work):").
- **fake only**: worktrees, `ccx batch`, quota fallback, the queue and seats, `--fork`, Gemini CLI, a real quota
  stop (none yet).
- **not verified**: Codex desktop's per-turn hook and `ccx say --now` into a live thread; the Codex rule from `ccx doctor --codex-rule`; dsh archiving queued until
  the app is closed (#91; the open app was seen dropping the id); own sub-agent limits (F10–F14) live; suggested-note rules (13/30 agreement on a held-out set, not an
  accuracy result); routing priors and the "save" default beyond round 1's tasks.
