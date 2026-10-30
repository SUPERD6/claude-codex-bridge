# B3 lean sub-agent switches: plan and evaluation arms (2026-10-30)

English · [中文](2026-10-30-b3-lean-switches-plan.zh.md) · back to [research reports](README.md)

**Status: plan only. Nothing here has been run; no number below is a result.** The switches are in ccx, each at
today's behaviour, and the arms that measure them are in `scripts/eval/r5.py`.

## Why a new baseline

Every evaluated ccx2 unit so far (r5, hc1) ran its Codex sub-agents in a dedicated eval Codex home with
`--ignore-user-config`, `--ignore-rules` and memories off, and its Claude sub-agents without user settings or skills.
The setup a person really uses, with their Codex memories, AGENTS.md and skills, was never measured. Most of the B3
switches move a sub-agent *toward* the measured setup, so comparing them with the evaluated ccx2 would show nothing:
they need a daily-config baseline.

## The switches (`[subagent]` in config/tiers.toml, all at today's behaviour)

| Key | Changed | Expected (estimate from transcripts, not measured) |
|---|---|---|
| `codex_memories` (true) | false: `-c features.memories=false -c memories.use_memories=false -c memories.generate_memories=false` on every Codex rung | about 6.8k fewer tokens per request, 25–35k per run |
| `clean` (false) | true: empty HOME for Codex / dsh, Claude without skills or user settings, one prompt line on the summary's language, Agent tool only with `--parallel` | Codex 4–6k per request; Claude 5–8k per run |
| `codex_lean_tools` (false) | true, write runs: no web search, image generation, goals; apps / plugins off on OpenAI's server | about 3–4k per request |

Details and risks: [features](../features.md#experimental-lean-sub-agent-switches-subagent-off-until-measured).

## The arms (opt-in, `--arms ...`)

All four are ccx2 to the letter (the same lead, wording and command line). They differ only in the homes their
sub-agents start in and in a `[subagent]` overlay written into the unit hub's own tiers.toml (read back the way ccx
reads it before the lead starts; the code is the same in every arm).

| Arm | Sub-agents |
|---|---|
| `ccx2daily` | the daily-config baseline: Codex in a per-unit home holding copies of the person's `~/.codex` memories/, AGENTS.md and skills/ and of `~/.agents/skills` (as its HOME), no `--ignore-user-config` / `--ignore-rules` / memories off; Claude sub-agents load setting sources `user,project,local` with skills on |
| `ccx2daily_nomem` | the baseline + `codex_memories = false` |
| `ccx2daily_clean` | the baseline + `clean = true` |
| `ccx2daily_leantools` | the baseline + `codex_lean_tools = true` |

How the per-unit home is made (`scripts/eval/daily_home.py`):

- The login is the eval Codex home's own `auth.json`, copied into the unit's folder. Nothing that holds the person's
  login is copied: no `auth.json`, credential files, `config.toml` (hooks, trust state, profiles, MCP servers),
  sessions, logs, history, databases, rules, hooks or plugins, at any depth; links are not followed. The folder is
  walked again after the copy and any such name stops the unit.
- Its config.toml is written, not copied: the settings ccx carries over on a lean start (`windows.sandbox`), the eval's
  features off (apps, plugins, remote_plugin: no account connectors) and only the person's own memory settings.
  So the apps / plugins part of `codex_lean_tools` is not measured by these arms; web search, image generation and
  goals are.
- It lives in the unit's `x-` folder and is removed with it after the unit.
- The eval Codex home itself is never written to, so the preflight and between-unit checks of every other arm, which
  refuse memories, AGENTS.md or skills there, are unchanged. This per-unit home is the daily arms' documented
  exception. Claude sub-agents keep the unit's settings file (hooks off, auto-memory off, deny rules for the real
  homes), and the lead's isolation and audit are those of ccx2. In `--claude-isolation flags` mode the user settings
  layer is the person's real `~/.claude/settings.json` (its hooks still off, the user CLAUDE.md still excluded); in
  `config-dir` / `ccx-home` it is the unit's fresh home, so the daily Claude side is closer to daily in flags mode.
- Every row has `daily` (what was copied, by name; the memory settings; the switches read back from the hub), its
  fingerprint's `models.daily`, and each ccx run's record has `subagent_switches`.

Self-test without spending anything: `python scripts/eval/r5.py daily-check --codex-home <eval codex home>` builds
one daily home in a temporary folder, prints what it holds (names only) and removes it; `run --dry-run` with a daily
arm lists what would be copied and the overlays.

## Measurement (from the B3 plan; about $20)

- **M1** (`codex_memories`, `clean`): A = `ccx2daily`, B = `ccx2daily_nomem`, C = `ccx2daily_clean`. Hold-out 10
  tasks × 3 rounds + r5 10 tasks × 2 rounds: 50 paired units per arm, about $5 per arm.
- **M2** (`codex_lean_tools`): D = `ccx2daily_leantools` against the same baseline, same tasks.
- **Decision rule, fixed now:** a switch's default changes only if all of: right_B ≥ right_A − 1; at most 2 pairs lost
  (A right, B wrong; McNemar); no task that B gets wrong in every round while A got it right at least once; the
  sub-agent's median input per run down by at least 15 % (M2: the per-request prefix down by about 3k). A one-sided
  missing pair or an unclean unit makes it Unknown, and the switch stays off.
- Power is limited: near a 95 % baseline, 50 pairs only show a drop of 10 points or more. On the edge (2–3 pairs lost),
  that arm alone gets 50 more units (about $5).

Commands (not run):

```bash
python scripts/eval/r5.py daily-check --codex-home <eval codex home>
python scripts/eval/r5.py run --taskset holdout --rounds 3 --arms ccx2daily,ccx2daily_nomem,ccx2daily_clean \
    --tag b3m1 --codex-home <eval codex home> --budget 20 --dry-run
```
