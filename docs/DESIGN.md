# Design (generic)

English · [中文](DESIGN.zh.md)

This document describes the **mechanism** only, with no personal paths or data. Your own hub is set at install time
with `ccx init --hub <path>`.

## Layers

| Layer | Contents | Where |
|---|---|---|
| tool | ccx code, default config, five skills (agent-delegate, task-routing, task-split, task-checkpoint, project-manager), tests | this repo |
| personal (hub) | your skills, MCP registry, personal memory, ledger, learned estimates, settings, improvement log | the folder given to `ccx init --hub` (default `~/.ccx-hub`) |
| project | background `context.md`, project journal, `inbox/`, resumable tasks `tasks/` | each project's `.ccx/` |

Rule: **mechanism belongs to the project, content belongs to the person.** Anyone who installs it gets the same
mechanism; the content stays on their own machine.

## Parts

1. **Delegation** (`ccx/delegate.py`, `ccx/runners.py`): runs another tool headless:
   - Codex: `codex exec --json`. On Windows, several CODEX_HOMEs on one machine share Codex's elevated sandbox
     accounts (their passwords are in each home's `.sandbox-secrets`): whichever home last ran the sandbox setup is
     the one that works (seen with codex-cli 0.164.0; the eval's per-unit homes use the unelevated sandbox for this);
   - Claude Code: `claude -p --output-format stream-json --verbose`;
   - Gemini CLI: `gemini -p -o stream-json`.
   - DeepSeek Harness: `dsh --profile headless --patch <run>/dsh.patch.yml --json -` (model in the patch, sandbox in
     `DSH_PERMISSION_MODE`).

   The sub-agent must answer in a JSON schema. The lead reads only that compact result; the full log stays on disk.
   - The session id is saved the moment it appears, so a crash or timeout can be continued with `ccx resume`.
   - Failures are classified ok / quota / auth / timeout / error:
     - quota or rate limit: one retry on the other agent;
     - `blocked` or `failed`: one rung up, in the same session.
   - A *provider* is the same tool pointed at another API (e.g. DeepSeek through Claude Code, or through Codex with a
     `-c model_providers.<id>` override). Keys come only from the environment.
   - DeepSeek is a vendor of its own, whichever route: `dsh`, `deepseek` and `deepseek-codex` all say vendor =
     deepseek, so review and fallback treat them as "another vendor" from Claude and Codex, and `ccx report` counts
     them as one DeepSeek stream.
   - Pay-per-token agents (providers and `dsh`) have a `daily_usd` cap; a model with no known price is refused, and
     they are never chosen as a quota fallback or reviewer unless pinned.
2. **Model choice** (task-routing skill, wired in by `ccx/learn.py`):
   - A 5-item rubric gives a difficulty b. The IRT formula P = 1/(1+e^(−1.2(θ−b))) gives each agent:model:effort's
     success probability.
   - Cost per success and a cascade rule choose the starting rung and the escalation path.
   - Each outcome updates θ Elo-style and corrects a per-rung cost factor from real spend.
   - The save ↔ fast knob k ∈ [0,1] sets the success target 0.70 + 0.20k.
3. **Splitting** (task-split skill):
   - Piece size sits at the 80% point of the METR time-horizon curve p(t) = 1/(1+(t/h50)^0.86).
   - Cut only where results can be checked. Start with 3–5 milestones and split further only on failure (ADaPT).
   - h50 is calibrated online from outcomes.
4. **Resume after interruption** (task-checkpoint skill):
   - State: `plan.json`, an append-only fsync'd `progress.jsonl`, and a heartbeat lock.
   - Code snapshots: `git stash create` refs under `refs/checkpoints/`, which never touch the branch.
   - `ccx run --task --step` records the start, the session id and the failure reason; `ccx verify` marks the step
     done.
5. **Incremental memory** (`ccx/memory.py`, `ccx/project.py`): a snapshot + an append-only journal + one cursor per
   agent.
   - A SessionStart hook prints only the other side's lines this side hasn't seen, plus unfinished tasks. If there is
     nothing new, it prints nothing.
   - A sub-agent (any tool) gets no delta; its brief carries up to 4 notes that share words with the task
     (`memory.for_brief`, ~300 tokens at most). No shared word, no note.
   - Each use (shown at a start, found by a search, put in a brief) is logged with who saw it and in which project;
     `ccx mem report --days 14` prints who wrote the notes that were used and who used them.
   - The project layer (`.ccx/`) works the same way. A file or email given to one side is archived by `ccx inbox`,
     and the other side reads one line about it.
6. **Sync** (`ccx/sync.py`):
   - Each skill is one real copy, linked into the other tool (junction on Windows, symlink elsewhere). MCP servers are
     registered through each tool's own CLI.
   - Every change is a dry run first and is backed up. `ccx uninstall` removes only what ccx added.
   - An existing shared setup is plugged in (external mode) rather than duplicated.
7. **Accounting and dashboard** (`ccx/ledger.py`, `ccx/usage.py`, `ccx/report.py`):
   - Tokens are normalized to 4 buckets (fresh, cache write, cache read, output) and priced into API-equivalent USD.
   - The lead's own usage is read from the tools' session logs, excluding sub-agent sessions.
   - Savings come two ways: a per-run estimate with a CI, and ~10% measured A/B samples.
   - `ccx report` writes an offline one-file dashboard; `--publish` commits it to a private repo.

## The self-calibration loop

```
ccx run (rung chosen from the rubric) -> sub-agent works -> result into the ledger
   -> definite failure / success the sub-agent checked itself: recorded at once into task-routing (θ, cost factor)
      and task-split (h50)
   -> the lead's `ccx verify` is authoritative: it corrects a wrong provisional record and never double counts
   -> the next routing / splitting decision uses the updated numbers (one shared copy for both agents)
```

Prices older than 30 days trigger a warning; Gemini uses model aliases, so new releases need no config change.

## Acceptance

On your own machine:

| # | Check | How |
|---|---|---|
| A1 | health | `ccx doctor` is all ok, or says why not |
| A2 | Claude → Codex | `ccx selftest --agents codex`, then delegate one real small task from Claude Code |
| A3 | Codex → Claude | `ccx selftest --agents claude`, then delegate one real small task from Codex |
| A4 | memory increments only | `ccx mem add` on one side; a new session on the other side sees just that line |
| A5 | project layer shared | `ccx inbox "…" --file mail.eml`; the other side's next session shows one line |
| A6 | skills on both sides | both tools list the same skill |
| A7 | MCP on both sides | both tools list the same MCP server |
| A8 | dashboard | `ccx report` shows lead/sub and Claude/Codex tokens and AE$ |
| A9 | resume | close the window during a `--task --step` run; `ccx resume` continues |
| A10 | quota fallback | point `--to` at a side that is out of quota; the run moves to the other side |
