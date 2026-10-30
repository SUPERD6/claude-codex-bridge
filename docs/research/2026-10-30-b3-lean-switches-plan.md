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
| `clean` (false) | true: empty HOME for Codex / dsh (only `~/.agents/skills` goes; CODEX_HOME's AGENTS.md, skills and memories stay), Claude without skills or user settings, one prompt line on the summary's language, Agent tool only with `--parallel` | Claude 5–8k per run; Codex: only what `~/.agents/skills` costs (the earlier 4–6k per request assumed all personal skills and rules go, which this switch does not do) |
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

- The login is the eval Codex home's own `auth.json`, copied into the unit's folder. Only files of a known text type
  (`.md`, `.txt`, scripts, `.json`, `.toml`, `.yaml` ...) are copied. Nothing that holds the person's login or a secret
  is copied, at any depth: no `auth.json`, credential files, keys and certificates (`id_*`, `*.pem`, `*.key`, `*.p12`),
  secrets, `.netrc` / `.npmrc` / `.pypirc`, `.ssh` / `.aws` / `.git` folders, `config.toml` (hooks, trust state,
  profiles, MCP servers), sessions, logs, history, databases, rules, hooks or plugins. Links, Windows junctions
  included (skill folders often are one), are followed into their target, since that is what Codex loads, and what
  they hold passes the same filters; the copy holds plain files only. The folder is walked again after the copy and
  any such name, link or other file type stops the unit.
- A ChatGPT login refreshes its token inside the unit's copy, and a refresh token works once. Before the unit's folder
  goes, a refreshed copy is written back to the eval home (atomically, only if the eval home's file is still the one
  copied; otherwise the row is unclean and the round should stop). So the daily arms need `--jobs 1`; r5 refuses more.
- Its config.toml is written, not copied: the settings ccx carries over on a lean start (`windows.sandbox`), the eval's
  features off (apps, plugins, remote_plugin: no account connectors) and only the person's own memory settings.
  So the apps / plugins part of `codex_lean_tools` is not measured by these arms; web search, image generation and
  goals are.
- On Windows, that config.toml also has `[windows] sandbox = "unelevated"`, for all four daily arms alike (it replaces
  the person's own `windows.sandbox`); elsewhere nothing is added. Why: Codex's elevated Windows sandbox runs commands
  as machine-wide sandbox accounts (`CodexSandboxOffline` / `CodexSandboxOnline`) whose passwords sit in each
  CODEX_HOME's `.sandbox-secrets`. A fresh per-unit home has none, so Codex starts its setup helper, which needs UAC;
  with nobody at the machine it is cancelled and every command fails, and the sub-agent stops blocked with no files
  changed (seen live, codex-cli 0.164.0, 2026-10-30). Running setup again from any home rotates the shared accounts
  and breaks the other homes. With the unelevated sandbox the same home runs commands and writes files with no UAC and
  no secrets. Limitation: the person's real daily setup uses the elevated sandbox; these arms measure the switches
  against each other under the unelevated one, not the elevated sandbox itself. Rows record it as
  `daily.windows_sandbox` (and `isolation.daily_windows_sandbox`); `daily-check` prints it.
- It lives in the unit's `x-` folder and is removed with it after the unit.
- The eval Codex home gets nothing of the person's (its own refreshed login is the only write), so the preflight and
  between-unit checks of every other arm, which refuse memories, AGENTS.md or skills there, are unchanged. This
  per-unit home is the daily arms' documented exception, and so are two audit rules: a daily unit's Claude sub-runs
  may load skills, slash commands and plugins (recorded per run in `audit.sub_skills`, not problems; the lead is
  audited as in ccx2), and a sub-agent reading the unit's own daily home (its memories copy, `$CODEX_HOME`) is not a
  private-context read in `harness_audit`. Claude sub-agents keep the unit's settings file (hooks off, auto-memory off, deny rules for the real
  homes), and the lead's isolation and audit are those of ccx2. In `--claude-isolation flags` mode the user settings
  layer is the person's real `~/.claude/settings.json` (its hooks still off, the user CLAUDE.md still excluded); in
  `config-dir` / `ccx-home` it is the unit's fresh home, so the daily Claude side is closer to daily in flags mode.
- Every row has `daily` (what was copied, by name, and from which sources; the memory settings; the switches read
  back from the hub; `sha256` over the names and bytes of the copy, so pairs with different snapshots of the person's
  setup can be told apart; the login's fate), `sub_usage` (ccx's sub-agent tokens per class: input, cached, output,
  reviews apart), its fingerprint's `models.daily`, and an `isolation` block that says `daily` for the homes and the
  real setting sources. Each ccx run's record has `subagent_switches`.
- On the Codex side, `clean` changes only HOME. In these arms CODEX_HOME holds copies of the person's AGENTS.md,
  skills and memories, so `ccx2daily_clean` measures, for Codex, only the `~/.agents/skills` copy (plus the Claude
  side, the language line and the Agent tool).

Self-test without spending anything: `python scripts/eval/r5.py daily-check --codex-home <eval codex home>` builds
one daily home in a temporary folder, prints what it holds (names only) and removes it; `run --dry-run` with a daily
arm lists what would be copied and the overlays.

## Measurement (from the B3 plan; about $20)

- **M1** (`codex_memories`, `clean`): A = `ccx2daily`, B = `ccx2daily_nomem`, C = `ccx2daily_clean`. Hold-out 10
  tasks × 3 rounds + r5 10 tasks × 2 rounds: 50 paired units per arm, about $5 per arm.
- **M2** (`codex_lean_tools`): D = `ccx2daily_leantools` against the same baseline, same tasks.
- **Decision rule, fixed now:** a switch's default changes only if all of: right_B ≥ right_A (right not lower: the person's rule); at most 2 pairs lost
  (A right, B wrong; McNemar); no task that B gets wrong in every round while A got it right at least once; the
  sub-agent's median prompt tokens per unit (`sub_usage.prompt` = input + cached of ccx's work runs) down by at least
  15 %, the same metric for every switch. A one-sided missing pair or a missing token count makes it Unknown, and the
  switch stays off. `r5.py summary` applies it on clean paired units (`b3_rules`).
- Power is limited: near a 95 % baseline, 50 pairs only show a drop of 10 points or more. On the edge (2–3 pairs lost),
  that arm alone gets 50 more units (about $5).

Commands (not run):

```bash
python scripts/eval/r5.py daily-check --codex-home <eval codex home>
python scripts/eval/r5.py run --taskset holdout --rounds 3 --arms ccx2daily,ccx2daily_nomem,ccx2daily_clean \
    --tag b3m1 --codex-home <eval codex home> --budget 20 --jobs 1 --dry-run
```

## Harness changes before the second half (report-only evidence; the rule is unchanged)

The hold-out half passed `codex_memories = false` on the median token condition, but a paired look showed the median
alone is fragile (the arm's prompt was lower in fewer than half of the pairs, and its total higher). Before the r5 half
runs, `scripts/eval/r5.py` gives more evidence without changing the registered rule:

- **The rule's median is the true median** (`statistics.median`: the mean of the two middle values for an even count),
  as the rule says, not the upper middle the wall fields use. The four conditions and Unknown cases are as fixed above.
- **Paired statistics next to it, report only** (`b3_rules[...].paired`): the share of pairs where the arm's prompt is
  lower, the median of the per-pair ratio arm / base, the total ratio, and a pair-bootstrap 95% CI of the ratio of
  medians (2000 resamples, fixed seed). `token_effect` is `consistent` only if the rule's token condition passes,
  the total ratio is ≤ 0.85 and the arm is lower in ≥ 60% of pairs; otherwise `not shown`. It never changes `result`.
- **Both halves judged together:** `summary --results a.jsonl b.jsonl --tag <hold-out tag> --tag <r5 tag>` reads
  several results files (a row in two of them counts once) and several tags, so the registered 50 pairs are one rule.
- **Pairs on different snapshots:** a pair whose two units' `daily.sha256` differ compared two setups of the person's,
  not a switch. Both units are left out of the rule and of the paired statistics (symmetric, so not a one-sided loss),
  and `snapshot_mismatch` lists them. A side without a hash is kept.
- **The snapshot is frozen per invocation:** `run` copies the person's memories / AGENTS.md / skills (and only the
  config settings a daily home takes from theirs) once into `<work>/daily-snapshot`; every daily unit copies from it,
  rows record `daily.snapshot` (`frozen`, its `sha256`), and the folder is removed at the end of the run.
- **What the switches did per run:** each row has `switches_applied` from every ccx run.json of the unit
  (`subagent_switches`, mode, agents) with the Codex memory / web search / image generation flags those switches add.
  ccx's run.json does not record the CLI's argv, so those flags are derived (`argv_recorded: false`), not read back.
- **Balanced arm order:** `run --arm-order balanced` rotates one seeded arm order by task and round (Latin square), so
  each arm runs first about equally often; rows record `arm_order` and `arm_pos`. The default stays `shuffle`, so
  earlier runs' schedules are unchanged. The second half should run with `--arm-order balanced`.
- **Evidence of failed units:** a unit that is not right records `hidden_failed` (the failing hidden test ids) and
  keeps the full hidden pytest output and its final diff (taken before the hidden tests go in) under
  `<results stem>-artifacts/<tag>-<unit>/`.
- **Postflight attribution:** when the person's real hub ledger grew during the run, the report lists each new row's
  type, run_id and ts and whether the run_id is one of the units' `ccx_run_ids` (an eval leak) or not (most likely a
  real session running at the same time); `preflight.json` keeps it as `postflight_ledger`.
