# What ccx does, and how

English · [中文](features.zh.md) · back to the [README](../README.md)

## Seven things it does

| | What | Where it stands |
|---|---|---|
| **1. Each other's lead and sub-agent** | Claude Code leads and Codex works, or the other way round; DeepSeek leads too (as `dsh`, or as Claude Code on a DeepSeek model) and takes work (through Claude Code, Codex, or `dsh`); Gemini CLI takes work (untested). One adapter per CLI; `ccx agents` lists what each can do, the version tested, official or community. | Both directions run for real; DeepSeek as lead (dsh, and Claude Code on DeepSeek) and as sub-agent (all three routes) for real; Gemini untested |
| **2. Two models talking directly** | `ccx ask` gets a quick second opinion from the other vendor; `ccx resume` follows up in the same sub-session; `ccx send` puts a message into a live Codex session; `ccx say` / `ccx board` let open Claude Code, Codex and DeepSeek sessions in one project write to each other (each turn sees what is new for it; Claude Code desktop only sees it on its next turn, a DeepSeek session runs `ccx board` itself); `ccx discuss` lets 2–3 models from different vendors talk a costly decision through (propose, find faults, judge; at most 3 rounds) and shows it as a conversation in `ccx ui`. | The first three work for real; `ccx discuss` ran for real twice, two vendors and then three (Codex, Claude, DeepSeek; [notes](research/2026-10-25-discuss-three-vendors.md)) |
| **3. Shared memory** | A personal layer (your hub: memory, skills, MCP, ledger) and a project layer (`.ccx/`: context, journal, handoffs, checkpoints). The session-start hook brings only the other side's new lines; `ccx handoff` passes the baton, `ccx fresh` moves a long conversation to a fresh one of the same tool. A **shared work context** ([docs](shared-context.md)): what a session has been doing lately, read by code from each tool's session file, goes with delegated tasks (`ccx run --context`), on demand (`ccx peek`) and as one line per turn — each tool still keeps its own context. | Works for real; shared work context: first try right 36/36 vs 7/36 without, on tasks built to need it ([A/B](research/2026-10-25-shared-context-ab.md)) |
| **4. Splitting the work** | A five-question difficulty score → agent, model, effort and the odds; when doing it yourself is cheaper, or the task should be split first, it says so instead of delegating. `ccx batch` / `ccx q` run pieces in parallel; `ccx task resume` continues a long task after a stop. | Routing works for real but priors are uncalibrated; the queue only with stand-ins |
| **5. Cheap and fast** | Slim sub-agent start-up; `ccx lead` shows what every turn of the lead re-reads (`--breakdown` part by part, `--cache` where the prompt cache broke, `--suggest` a model for the lead itself); `ccx sum` gives the lead only what matters of a big output. | The tools exist; how much they save depends on the lead using them (see below) |
| **6. No drop in quality** | ccx reruns the acceptance command itself (`--check`); another vendor's model reviews the diff (`--review`); every run gets a verdict (`ccx verify --ok 0 --reason wrong`), and runs nobody judged get a probable one from the evidence after 12 hours; `ccx trial` runs a week-long comparison. | Works for real; the automatic verdicts haven't been spot-checked yet |
| **7. You stay in control** | Config changes are a dry run first and backed up before applying; `ccx undo` reverts a run's edits; `--mode read` / `--worktree` leave your working tree alone; sub-agents can't delegate further; `ccx ui` shows, read-only on this machine, who works on what and what waits for your call. | Works for real; `ccx ui` opened in Edge only |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/architecture-dark.svg">
  <img alt="Architecture: Claude Code, Codex and Gemini CLI connect to ccx; a lead hands a brief to another, which runs headless and returns JSON; ccx routes, reruns the check, asks another vendor to review, records verdicts and costs; below: the personal layer (hub: memory, skills, MCP, ledger), the project layer (.ccx: context, journal, handoffs, checkpoints, undo snapshots) and ccx ui, a local read-only page" src="assets/architecture-light.svg" width="100%">
</picture>

## See it live: `ccx ui`

`ccx ui` opens a page on this machine: what waits for you (red = your call, amber = please review),
who works on what (one column per agent, new agents get their own), and how the quota windows are going. Click a
block for the reason, the evidence and the `ccx` command to copy. Suggested notes (preferences, decisions, pitfalls
ccx picked from a session) have a yes / no button, the page's only write. It reads only files ccx and the tools already
write — no model is called — listens on 127.0.0.1 only, and exits a minute after the page is closed.
`ccx ui --export snapshot.html` writes a static copy; `ccx config set ui.lang zh|en` picks the language.
Evaluations and tests (eval-* labels, `--no-ab`, ccx's probes, runs in the temporary folder or a project's `.ccx`
folder) stay hidden until you press "show evaluations and tests"; `ccx verify RUN --dismiss --note why` clears a
leftover from "waits for you" without counting it right or wrong, and routing never learns from it.

<img alt="ccx ui task page in English, dark theme: a task as an org chart, one column per worker, the side panel showing why a piece needs your call (demo data)" src="assets/ui/task-en-dark.png" width="100%">

<details><summary>Chinese interface, light</summary>

<img alt="ccx ui overview in Chinese: nine things waiting, the current lead, two projects and the quota forecast (demo data)" src="assets/ui/overview-zh.png" width="100%">

<img alt="ccx ui task page in Chinese (demo data)" src="assets/ui/task-zh.png" width="100%">

</details>

The screenshots come from `python scripts/ui_demo.py --plain`: a throwaway hub with real ccx runs on stand-in CLIs,
nobody's real work.

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
   - You want it to stop: `ccx stop <run_id>` ends the sub-agent and everything it started; `ccx resume` goes on.
6. **Learn and report.** Every run goes into a ledger and back into task-routing / task-split, so the next pick is
   better. `ccx report` builds a dashboard: who spent how many tokens of which kind, quota use, estimated savings.

The other way round, run the same command inside Codex with `--to claude`: Codex leads, Claude Code is the sub-agent.
Codex's sandbox decides whether that works: ccx writes its run records into the hub and the sub-agent needs the
network. `ccx doctor` checks it (row "Codex as lead (sandbox)"). On Windows only `danger-full-access` worked in real
runs (codex-cli 0.164): in `workspace-write` the commands run as a separate sandbox account, and a Claude sub-agent
started there refused every edit, even with the hub and `~/.claude` as writable roots and the network on.
**Safety:** full access means every command the Codex lead runs has your rights, with no sandbox (your files, the
network, your credentials); use it only for a lead you would trust at your own keyboard. A narrower way, by Codex's
docs but **not yet checked on a real run**: keep `workspace-write` and let only ccx's hand-out commands
(`run`, `ask`, `resume`, `discuss`) run outside the sandbox with a Codex rule: `ccx doctor --codex-rule >>
~/.codex/rules/ccx.rules` (rules are experimental in Codex; `ccx doctor` then says Unknown, not ok).

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

**Finding and sorting notes.** `ccx mem search` ranks notes by BM25: a rare word counts more than a common one and a
note needn't contain every word (`--all-words` keeps the old filter, `--limit N`). Every note has one of five kinds —
preference, constraint, fact, pitfall, event (偏好 / 约束 / 事实 / 坑 / 事件), else other: `ccx mem add --kind`, and
an older note's kind is guessed from its topic or words when it is read (`ccx mem kinds --list`; the journal is never
rewritten). With `[memory] by_kind = true` a session start carries only new preferences and constraints, a
sub-agent's brief picks pitfalls, facts and others by BM25, and events are found by search only. It is off by default
until the week-long trial ends (2026-11-01), so starts and briefs carry what they did. `ccx mem compact --by project`
writes one short block per project to `memory/scenes.md`; `[memory] start_scene = true` adds the current project's
block at a session start (off by default: a start's notes are already capped at ~600 tokens).

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
DeepSeek Harness (`--to dsh`): deepseek-flash at low / high / max for T1-T3, deepseek-v4-pro · max for T4.

**Pay-per-token agents** (the providers in `[providers.*]` and `dsh`) spend real money, so each has a `daily_usd` cap
(default $1); a provider whose key isn't in your environment takes part in nothing (`ccx agents` shows `ready`). A
model without a known price is refused, since its spend couldn't be counted against the cap. They are never picked as
a quota fallback or as a reviewer on their own; only DeepSeek through Claude Code is in automatic routing (it has
calibration and prices), the others need `--provider` / `--to` until they are calibrated.

## Safety

- Sub-agents **may edit files** by default:
  - Codex: `workspace-write` sandbox.
  - Claude: `acceptEdits` plus a tool allow-list; only git/python/pytest/npm/node commands are allowed.
  - Gemini: `auto_edit` approval mode.
  - DeepSeek Harness: `DSH_PERMISSION_MODE=workspace-write` (`read-only` with `--mode read`); ccx also turns off its
    default session-log upload to DeepSeek and its telemetry for these runs.
  - `--mode read` makes any of them analysis-only. Parallel writers go to separate git worktrees.
- A sub-agent cannot delegate again (`CCX_DEPTH`).
- `ccx sync` is a dry run unless `--apply`:
  - Each changed file is backed up once a day.
  - Codex's `config.toml` only gets one marked hook block, validated with a TOML parser before writing.
  - MCP servers are added only through each tool's own CLI.
- ccx never reads or copies account credentials. Provider keys are read from your environment and never stored.
