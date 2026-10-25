# Three vendors talk a decision through: the first real run (2026-10-25)

English · [中文](2026-10-25-discuss-three-vendors.zh.md) · ccx main `485d322` · codex-cli 0.164.0 · claude 2.1.309 ·
DeepSeek through Claude Code (`--bare`) · Windows 11 · data: [data/2026-10-25-discuss-three-vendors.json](data/2026-10-25-discuss-three-vendors.json)

**Result: it works (n = 1).** Codex proposed, Claude found faults, DeepSeek judged; three rounds, seven turns,
$0.016 and 85 seconds. The judge was independent, every tagged line was read, and the estimate was right within
the asked factor of two. One run is one run: this shows the mechanism works with real models, not how good the
advice is in general.

## How it was run

`ccx discuss --with codex,claude,deepseek --tier T1 --question-file q.txt` in a temporary `CCX_HUB` (so the
routing data and the person's ledger were not touched), after PRs #38 (estimate), #42 (format) and #51 (tier).
T1 means Codex on `gpt-6-luna low`, Claude on `haiku low`, DeepSeek on `deepseek-flash low`.

The question had a known answer: how a CLI should write a small JSON file that a page polls, on Windows, macOS and
Linux. (A) write in place, (B) temp file + `os.replace`, (C) temp file + `os.rename`, (D) a lock file. The right
choice is (B): `os.rename` fails on Windows when the target exists, (A) exposes half-written files, (D) needs every
reader to honour the lock.

## Acceptance

| Check | Asked | Got |
|---|---|---|
| Independent judge | `judge_independent = true` | true (three vendors) |
| Judge's tags read | RECOMMEND + `[consensus]` / `[disagreement]` / `[reason]` | all four: 3 consensus, 3 disagreements, 2 reasons; no turn unparsed, no format reminder needed |
| Estimate | actual within 0.5–2× of it | dry run said $0.0094–0.0213 (modelled); actual $0.0163 = 0.77× the maximum, and all three rounds ran |
| `ccx ui` | shows it | the Discussions page drew the seven turns and the outcome (checked in a browser on the local page) |
| Cost cap | ≤ $1 this session; DeepSeek ≤ $1 a day | $0.016 in all, DeepSeek $0.0017 |

## What happened

| Turn | Agent · model | $ | s | Tokens in (cached) / out | What it said |
|---|---|---|---|---|---|
| r1 propose | Codex · luna low | 0.0021 | 6 | 19.5k (0) / 240 | (B), retry briefly on a Windows sharing error, reader keeps the last good state |
| r1 critique | Claude · haiku low | 0.0043 | 20 | 13.0k (0) / 3.3k | objections: how many retries and what then; `fsync` before the swap |
| r2 revise | Codex | 0.0007 | 6 | 20.1k (16.1k) / 266 | (B) + `mkstemp`, `fsync`, bounded retries, keep the old file when they run out |
| r2 critique | Claude | 0.0027 | 15 | 13.9k (6.5k) / 2.2k | objections: exact numbers, how staleness shows, clean-up of temp files |
| r3 revise | Codex | 0.0021 | 6 | 19.4k (0) / 232 | 5 tries within 0.5 s, a timestamp in the JSON, clean old temp files |
| r3 critique | Claude | 0.0028 | 17 | 14.8k (6.5k) / 2.2k | objections: retry budget unproven, `mkstemp` makes 0600 files, several writers |
| judge | DeepSeek · flash low | 0.0017 | 14 | 7.9k (3.8k) / 1.8k | RECOMMEND (B) with the details; 3 consensus, 3 disagreements, 2 reasons |

The recommendation is right, and the critic's points were real ones that the proposer took up (unique temp names,
`fsync`, what happens when retries run out, a staleness timestamp).

## What to change next (not done here)

1. **The critic never agreed.** Each round its `[must]` items were new implementation details (retry counts, file
   permissions, several writers), none of which made the choice (B) wrong, so the talk always went to round 3.
   The critique instruction says `[must]` is "what would make the choice wrong", and the cheap model did not keep
   to that. Worth trying: tell the critic to compare with the previous round and agree when what is left are
   refinements (`[note]`), and count "agreed in round N" over more runs.
2. **Start-up overhead differs by route.** DeepSeek through Claude Code with `--bare` read 7.9k tokens, against
   13–15k for Claude Code itself and 19–20k for Codex; the estimate's table uses Claude Code's numbers for every
   Claude-Code route, which overstates providers slightly (harmless at these prices).
3. **The Claude critic answered in Chinese** while the others answered in English, probably from the person's own
   instructions that Claude Code loads. It did not break parsing (tags are ASCII), but the page mixes languages.

## Not run (I5)

On this machine Gemini CLI and DeepSeek Harness (`dsh`) are not installed, and there are no keys for Kimi
(`MOONSHOT_API_KEY`), GLM (`ZAI_API_KEY`), Qwen (`DASHSCOPE_API_KEY`) or OpenRouter (`OPENROUTER_API_KEY`), so
none of them has run: **Gemini: not run. dsh: not run. Kimi, GLM, Qwen, OpenRouter: not run.** DeepSeek through
Claude Code ran above as the judge. *Later the same day the DeepSeek Harness desktop app was installed: `dsh` read,
write and resume then ran for real, see [2026-10-25-deepseek-lead.md](2026-10-25-deepseek-lead.md); the person chose
not to install Gemini CLI.*
