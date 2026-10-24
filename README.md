<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="ccx — Claude Code and Codex hand work to each other; a real run: routed to luna/low, done in one attempt, verified, $0.0023" src="docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  <a href="https://github.com/SUPERD6/claude-codex-bridge/actions/workflows/test.yml"><img alt="tests" src="https://github.com/SUPERD6/claude-codex-bridge/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="dependencies: standard library only" src="https://img.shields.io/badge/dependencies-stdlib%20only-1f7a3a">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0f7c80"></a>
  <a href="https://github.com/SUPERD6/claude-codex-bridge/releases"><img alt="release" src="https://img.shields.io/github/v/release/SUPERD6/claude-codex-bridge"></a>
</p>

<p align="center">English · <a href="README.zh.md">中文</a> · <a href="https://superd6.github.io/claude-codex-bridge/">Website</a></p>

> **Work in progress (v0.4, October 2026).** It runs every day on one Windows machine, both directions, terminal and
> desktop apps. Not done yet:
> - **No real savings numbers.** Two weeks of real use with verdicts haven't been collected, so routing priors are
>   uncalibrated and "how much it saves" is not measured; the numbers below are single real runs.
> - **Tested only with stand-in CLIs:** the work queue (`ccx q`), seats, worktrees and `ccx batch`, fallback to the
>   other agent on a real quota stop, `ccx uninstall --apply`. Gemini CLI has never run for real. macOS and Linux
>   run in CI only.
> - **Not built yet:** a local live view (`ccx ui`) and an `en`/`zh` switch for the few lines ccx injects into
>   sessions. The website above is not published yet.
>
> Commit ids in older notes (CHANGELOG, docs/STATUS) refer to the private history before it was squashed for this
> public release. Issues and feedback are welcome; see [STATUS](docs/STATUS.md) for what is verified and how.

**Let Claude Code and Codex hand tasks to each other.** ccx picks the cheapest model likely to finish each piece,
runs it in the other tool, has the lead check the result and records what it cost — so the expensive lead stops
doing the cheap work. Either tool can lead; Gemini CLI, and DeepSeek through Claude Code, can take work too.

```bash
pipx install git+https://github.com/SUPERD6/claude-codex-bridge
ccx setup                    # guided: explains each step and asks before changing anything
ccx run --to codex --mode read "Summarise README.md in three lines"
```

<p align="center"><img alt="Animated demo: ccx route picks codex:gpt-6-luna:low, ccx run finishes in one attempt, ccx verify records the verdict" src="docs/assets/demo.svg" width="100%"></p>

## Measured on a real machine

| What | Result |
|---|---|
| Starting a Claude sub-agent (fixed context per request) | 46k → **13.6k** tokens with ccx's slim start |
| Small read task, Claude Code → Codex | **1 attempt**, luna/low, **$0.0023** |
| Usage accounting vs. Codex's own weekly quota | **$2.8–4.4** API-equivalent per 1%, stable across 4 windows |
| Tests | 139, on Linux, Windows and macOS × Python 3.11–3.13 |

Two weeks of everyday numbers (what delegating actually saved) will replace this table before 1.0.

## What it does

| | |
|---|---|
| **Both directions** — Claude Code leads and Codex works, or the other way round; terminal or desktop app. | **Picks the model** — a five-question difficulty score → agent, model, effort and the odds; learns from every `ccx verify`. |
| **Cheap starts** — slim sub-agent start-up; the same sub-session is continued within an hour, so the cache stays warm. | **Shared memory** — only the other side's new lines arrive at session start; a project layer both tools see. |
| **Resumable** — quota stop, crash or closed window: `ccx task resume` picks up the same session. | **Receipts** — every run's tokens and cost, and a dashboard of what delegating saved. |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture-dark.svg">
  <img alt="Either tool leads; ccx routes a brief to the other, runs it headless and returns JSON; a session-start hook brings memory, handoffs and unfinished tasks from your hub; the project's .ccx folder holds context, journal, inbox, checkpoints and undo snapshots" src="docs/assets/architecture-light.svg" width="100%">
</picture>

Design: [docs/DESIGN.md](docs/DESIGN.md) · Progress: [docs/STATUS.md](docs/STATUS.md) ·
Decisions: [docs/DECISIONS.md](docs/DECISIONS.md) · Changes: [CHANGELOG.md](CHANGELOG.md)

## How it works (one example)

In Claude Code you say: "make `loader.py` accept a custom delimiter and add tests."

1. **Score and brief.** Claude (lead) scores the task on 5 items: 2 files, one module, clear goal, low risk, an
   existing pattern to follow. It writes a brief of under 200 words: the goal, the files to look at, and what
   "done" means.
2. **Pick a model.** It runs `ccx run --from claude --files 2 --coupling one --clarity goal "…"`. ccx asks the
   **task-routing** skill for each agent:model:effort's success probability and cost per success. Here it picks
   `codex:gpt-6.1-sol:medium`. If doing it yourself is cheaper, or the task should be split first, ccx says so and
   delegates nothing.
3. **Run headless.** ccx runs `codex exec -m gpt-6.1-sol -c model_reasoning_effort="medium" …`. The session id is
   saved the moment it appears. Codex reads the files, edits and runs the tests on Codex's own quota.
4. **Return a summary.** Codex must answer in a JSON schema (`status / summary / files_changed / verification / …`).
   Claude reads only that, glances at `git diff`, and records its verdict with `ccx verify <run_id> --ok 1`.
5. **Recover from problems.**
   - Codex reports `blocked`: ccx continues **in the same Codex session** one rung up (high), with no re-briefing.
   - Codex is out of quota: Claude takes over.
   - A timeout or crash: `ccx resume <run_id>` continues.
6. **Learn and report.** Every run goes into a ledger and back into task-routing / task-split, so the next pick is
   better. `ccx report` builds a dashboard: who spent how many tokens of which kind, quota use, estimated savings.

The other way round, run the same command inside Codex with `--to claude`: Codex leads, Claude Code is the sub-agent.

**Does the sub-agent know what you discussed with the lead?** Not directly: copying a long conversation into every
sub-agent would be expensive, and Claude and Codex can't share a context window anyway. The sub-agent gets the
brief (the lead's distilled summary), the project background, shared memory and the files themselves. What gives
continuity is the **sub-session**: the next task from the same conversation, folder and agent within an hour
continues the same sub-session automatically, so it remembers what it already read and did (`--new` for a fresh one).
From Claude Code to a Claude sub-agent, `--fork` can start it from a copy of your whole conversation.

## Where shared things live

Everything personal lives in **your hub** folder. `ccx init --hub <path>` sets it and stores it in
`~/.ccx/config.toml`. The default is `~/.ccx-hub`, and `CCX_HUB` overrides it. The repo holds no personal content.

| What | Where | How both tools see it |
|---|---|---|
| memory snapshot "1" | `memory/MEMORY.md` | Claude: `@import` in `~/.claude/CLAUDE.md`; Codex: a managed block in `AGENTS.md` |
| memory increments "+2" | `memory/journal.jsonl` + `ccx/cursors.json` | a SessionStart hook runs `ccx mem delta --as <me>`: only the other side's new lines, once |
| skills | one copy each (`hub/skills/`) | linked into both tools (junction / symlink) |
| MCP servers | `mcp/servers.json` | `ccx sync` registers them with `claude mcp add-json` / `codex mcp add` |
| project background | `<project>/.ccx/context.md` | every brief points to it; the sub-agent reads it itself |
| runs / ledger | `ccx/runs/`, `ccx/ledger.jsonl` | `ccx show` / `ccx stats` / `ccx report` |
| learned estimates | `ccx/routing-state.json`, `ccx/split-state.json` | shared by both agents, updated after each verified run |
| settings | `ccx/settings.toml` | `ccx config set ...` |
| work queue | `<project>/.ccx/queue/` | `ccx q tree`; open work is shown at session start |

**Which memory for what.** A standing rule the user states ("always commit each change") belongs in the user's
shared instructions file, added only once the user agrees. A fact about a project goes into `ccx mem add --project`
(with `--source` where it came from). A note that is no longer true is replaced (`--supersedes N`), not left next
to the new one; one nobody has checked for 30 days is shown as "to check" (`ccx mem stale`, `ccx mem verify N`);
`ccx mem search` finds older ones, and a session start carries at most ~600 tokens of new lines. Each tool's own
automatic memory stays its own: ccx doesn't copy one into the other.

## Install

**Requirements:**
- Python 3.11+ (standard library only).
- `codex` and `claude` CLIs, both logged in. `gemini` is optional.

**Without a clone** (the skills and config ship inside the package):

```bash
pipx install git+https://github.com/<you>/claude-codex-bridge
ccx init --hub <your hub path>
ccx doctor
```

**From a clone** (to develop, or to let `git pull` upgrade the skills linked into your hub):

```powershell
git clone https://github.com/<you>/claude-codex-bridge
cd claude-codex-bridge
.\install.ps1 -Hub <your hub path>      # Windows; macOS/Linux: ./install.sh <hub path>
```

**The install script:**
- Runs `pipx install --editable .` if pipx is there, so `ccx` is on your PATH. Otherwise it tells you to add `bin/`
  to PATH.
- Runs `ccx init`, which only creates files and never changes existing ones.
- Runs `ccx doctor`, which checks CLIs, logins and wiring and reports Unknown when unsure.

**Then** run the guided first run, `ccx setup` (it explains each step and asks before changing anything), or do it
step by step:

```powershell
ccx sync            # dry run: lists every change, touches nothing
ccx sync --apply    # apply; each changed file is backed up as *.ccx-backup-YYYYMMDD
ccx selftest        # one tiny real task per installed agent on its cheapest model: login, parsing, start-up cost
```

Finally, open `/hooks` in Codex once and trust the "ccx: shared memory delta" hook.

**Already have a shared setup?** For example, one AGENTS.md both tools read and your own sync script. Plug it in:

```powershell
ccx init --hub <path> --snapshot AGENTS.md --external-sync "<your sync command>"
```

ccx then never edits the tools' instruction files, and leaves skills and MCP to your script.

## Commands

```text
ccx run "task" --from claude --files 3 --coupling cross --clarity goal   # routed by the rubric (recommended)
ccx run "task" --model gpt-6.1-sol --effort high                         # explicit model and effort
ccx run "task" --tier T2                                                 # fixed tier
     [--mode read] [--check "pytest -q tests/test_x.py"] [--kind code|read|research|write] [--minutes 60]
     [--review auto|on|off] [--risk visible] [--seat reviewer] [--worktree] [--task <id> --step <n>] [--no-subagents] [--no-fallback] [--force] [--bg]
ccx quota [--probe]                   # each subscription window projected to its reset (what routing prices quota at)
ccx bench [refresh]                   # the public benchmark data routing uses, its age and credits
ccx run "task" --to gemini --tier T2                         # Gemini CLI as the sub-agent
ccx run "task" --to deepseek       # DeepSeek flash through Claude Code (key in DEEPSEEK_API_KEY), effort by difficulty
ccx verify <run_id> --ok 1|0 [--note "..."]   # the lead's verdict: calibrates routing/splitting, closes the checkpoint step
ccx resume <run_id> "follow-up"       # same sub-session; also how an interrupted run continues
ccx task status | resume <task>       # long tasks: one command continues the interrupted step (hands off on quota)
ccx handoff --by claude --to codex "what's done / decided / next" [--next "task 5" ...]   # switch leads
ccx lead                                     # what each turn of your lead conversations re-reads and costs
ccx verify <run_id> --ok 0 --reason wrong     # your verdict (unjudged runs get a probable one after 12 h)
ccx handoff --from-transcript codex --to claude   # the old lead can't write it (quota out): built from its session file
                                                  # (by code; a format the code can't read goes to a routed sub-agent, --no-model to skip)
ccx undo <run_id> [--apply]           # put back what a write run changed (new files are moved aside, not deleted)
ccx ask "question"                    # quick read-only second opinion from the other agent, low effort
ccx archive [--apply] | --restore <run>   # archive finished sub-sessions (also automatic after 2 h)
ccx batch plan.json                   # independent tasks in parallel; parallel writers get separate worktrees
ccx q add "title" --brief "..." [--dep q1] [--check CMD] [--minutes 30] [--budget 1]   # the project's work queue
ccx q run | resume | tree | done q3 --ok 1   # run every ready piece in parallel; a piece too big splits itself
ccx route --files 3 --coupling cross ... [--lead claude:opus:high --ctx-files log.txt]  # recommendation; + self vs delegate
ccx plan size --minutes 240 --rung codex:gpt-6.1-sol:medium # how many pieces for a big task (task-split)
ccx show <run_id> [--full]            # compact result by default
ccx stats [--summary]                 # per agent × tier; --summary: spend, savings, cache share
ccx report [--days 30] [--publish]    # offline one-file dashboard; --publish commits it to your private repo
ccx config set defaults.tradeoff 0.3  # the save <-> fast knob: save / balanced / fast, or 0..1
ccx ab done <id> --ok 1               # close an A/B sample (the ~10% the lead does itself)
ccx send --list | --thread <id> "msg" # message a live Codex desktop / interactive session
ccx skills find pdf table             # search the shared skill library before writing a new skill
ccx skills install [--replace] [--apply]   # link this repo's skills into the hub (dry run first), so `git pull` upgrades them
ccx improve add <skill> "concrete problem" --fix "what to change"   # log real problems only
ccx mem add "one sentence" --by claude    # shared memory
ccx mem delta --as codex                  # the other side's new lines (the hook runs this)
ccx mem compact                           # fold the journal into the snapshot
ccx ctx init | add "…" | show             # project background file
ccx project init | status | compact ; ccx inbox "note" --file mail.eml   # project layer
ccx sync [--apply] [--only skills,memory,hooks,mcp] ; ccx doctor ; ccx uninstall [--apply]
```

## Tiers (`config/tiers.toml`, override in `hub/ccx/tiers.toml`)

Fixed tiers are the fallback. With rubric flags, task-routing picks by success probability and cost per success,
and calibrates itself from real outcomes.

| Tier | Work | Codex | Claude Code | Gemini CLI |
|---|---|---|---|---|
| T0 | two or three steps | don't delegate | don't delegate | don't delegate |
| T1 | mechanical | gpt-6-luna · low | haiku · low (no MCP loaded) | flash-lite |
| T2 | routine development | gpt-6.1-sol · medium | sonnet · medium | flash |
| T3 | hard | gpt-6.1-sol · high | opus · high | pro |
| T4 | critical / research | gpt-6-astra · xhigh | opus · max | pro |

Gemini uses the CLI's aliases, so new model releases need no config change. Gemini CLI has no effort flag.

## Safety

- Sub-agents **may edit files** by default:
  - Codex: `workspace-write` sandbox.
  - Claude: `acceptEdits` plus a tool allow-list; only git/python/pytest/npm/node commands are allowed.
  - Gemini: `auto_edit` approval mode.
  - `--mode read` makes any of them analysis-only. Parallel writers go to separate git worktrees.
- A sub-agent cannot delegate again (`CCX_DEPTH`).
- `ccx sync` is a dry run unless `--apply`:
  - Each changed file is backed up once a day.
  - Codex's `config.toml` only gets one marked hook block, validated with a TOML parser before writing.
  - MCP servers are added only through each tool's own CLI.
- ccx never reads or copies account credentials. Provider keys are read from your environment and never stored.

## Tests

```bash
python -m pytest -q tests        # or: python -m unittest discover -s tests
```

The tests drive fake codex/claude/gemini CLIs (`tests/fakes/`). They cover:
- argv and stream parsing;
- escalation, resume, quota fallback and timeouts;
- the depth guard and incremental memory;
- sync idempotence and backups;
- the learning loop and the dashboard.

GitHub Actions runs them on Linux/Windows/macOS × Python 3.11–3.13. **The tests prove the logic, not that the real
CLIs work on your machine.** Run `ccx selftest` there; the acceptance list is in
[docs/DESIGN.md](docs/DESIGN.md#acceptance).

## How savings are measured

- **AE$ (API-equivalent USD):** tokens × list price, per bucket (fresh input, cache write, cache read, output).
  Subscriptions don't bill per token, so AE$ is the common yardstick. Against one real run it was 1.5% from
  Claude's own reported cost.
- **Estimated saving per delegated run:** the same tokens at the lead model's price, minus what the sub-agent cost,
  minus the brief/review overhead. Reported with a bootstrap 95% CI.
- **Measured A/B:** about 10% of tasks that would have been delegated are randomly handed back to the lead
  (`defaults.ab_self_rate`; 0 turns it off). Costs are compared at the same difficulty, which tests the estimate
  above.
- **The lead's own usage** is read from each tool's session logs (Claude `~/.claude/projects`, Codex
  `~/.codex/sessions`). Sub-agent sessions are excluded so nothing is counted twice.

## External facts checked (2026-10-22/23)

- **codex-cli 0.164.0** `exec --help`: `--json`, `-m`, `-c`, `--output-schema`, `-o`, `--ignore-user-config`, `--ephemeral`, `exec resume <id>`. A lean start (`--ignore-user-config`) must keep the user's `windows.sandbox`, or read-only rejects every command on Windows.
  `resume` takes no `-s`, so the sandbox is set with `-c sandbox_mode=…`.
- **Claude Code 2.1.309** `--help`: `-p --output-format json|stream-json` (stream-json requires `--verbose`),
  `--model`, `--effort low..max`, `--json-schema`, `--resume`, `--strict-mcp-config`. Measured:
  - the first event carries session_id;
  - the final result event carries `structured_output`, `usage`, `total_cost_usd`;
  - `--resume` reports per-call usage;
  - a headless start with default flags is ~46k tokens, written to the 1-hour cache; with ccx's slim flags ~20k, and a repeat start (any project, within the hour) writes only ~0.65–2k.
- **OpenAI GPT-6 docs:** `gpt-6-astra` / `gpt-6.1-sol` / `gpt-6-luna`; 6.1-sol efforts low/medium/high/xhigh/max.
- **Codex hooks docs:** `[[hooks.SessionStart]]`; stdout is injected as developer context; new hooks must be trusted
  in `/hooks`.
- **Gemini CLI 0.65.0** `--help` and bundled source:
  - `-p` runs headless, appended after stdin;
  - `-o stream-json` emits init / message / tool_use / tool_result / error / result events;
  - also `--approval-mode plan|auto_edit`, `--session-id`, `--resume <uuid>`;
  - model aliases `flash-lite / flash / pro`.
- **DeepSeek docs:** Claude Code uses `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` and the key; ccx passes
  it as `ANTHROPIC_API_KEY` with `--bare`, so the caller's own Claude login never reaches DeepSeek (2026-10-24).
  Peak prices per 1M tokens (input / cache hit / output), off-peak half:
  - deepseek-flash $0.30 / $0.006 / $1.20;
  - deepseek-v4-pro $1.32 / $0.044 / $3.96.
- **Gemini pricing** (ai.google.dev/pricing), per 1M tokens (input / cached / output):
  - 3.5-flash-lite $0.30 / $0.03 / $2.50;
  - 3.8-flash $0.75 / $0.075 / $3.75 (until 2026-12-31);
  - 3.1-pro-preview $2.00 / $0.20 / $12.00.

## Questions

**Doesn't a second agent cost more tokens?** Only for tiny tasks, and then ccx tells you to do them yourself
(`delegated: false`). Otherwise the sub-agent runs on a cheaper model than your lead and starts slim; `ccx report`
shows the difference from your own runs, and roughly one task in ten is done by the lead itself to measure it.

**I'm on a subscription, not the API.** Costs are shown at API prices so runs can be compared; the dashboard also
shows how much of each tool's quota went where. When one tool runs out, the work moves to the other.

**Is it safe to let a sub-agent edit files?** Edits stay in the task's folder, every write run is snapshotted for
`ccx undo`, and `--mode read` or `--worktree` keep your tree untouched. Details in [SECURITY.md](SECURITY.md).

**Read-only or allowed to edit?** Without `--mode`, ccx decides from the task text: analysis words (review,
explain, compare, 分析, 解释 …) mean read-only, edit words (fix, add, refactor, 修复, 改成 …) mean it may edit, and
an unclear text keeps the old default (edit) and says so. `--mode` always wins. A read-only sub-agent that finds it
must edit stops with `needs_write` and hands the decision back to you.

**Does it drive the chat apps?** No. Both sides run in their work mode (`codex exec`, `claude -p`) — the same agents
you use in a terminal, not a web chat.

**Which tools work?** Claude Code and Codex CLI, tested on a real machine in both directions. DeepSeek-backed
Claude Code is calibrated on real tasks; Gemini CLI is adapted but not yet run for real.

## Security

What ccx runs, what it may change and how to report a problem: [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) (tests, rules, adding an adapter for another agent CLI) and the
[code of conduct](CODE_OF_CONDUCT.md).

## License

MIT, see [LICENSE](LICENSE). The repository is private for now and opens after v1.0.
