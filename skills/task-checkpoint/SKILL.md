---
name: task-checkpoint
description: Make long multi-step tasks resumable after a quota cut, crash or closed window, and resume them. Use for 20+ minute tasks, an "unfinished task" notice, or "从断点继续/resume".
---

# Task checkpoint: never redo finished work

Progress lives on disk, not only in your context. The script is standalone
(Python 3.11+, stdlib; git optional) next to this file:
`python <this skill's folder>/scripts/checkpoint.py ...` (`python3` on macOS/Linux; below: `cp`).
State: `<repo>/.ccx/tasks/<task>/` (auto-added to .gitignore).

## On session start, or when the user says "continue"

`cp status --quiet` lists unfinished tasks; nothing printed = nothing to resume.
For a listed task, read **only** `cp brief <task>` (a few hundred tokens). Then:
1. Skip steps marked `[x]` — they are done and verified.
2. For the stopped step, prefer resuming its recorded session — it remembers its progress. A step dispatched
   with `ccx run --task <task> --step <n>` → `ccx task resume <task>`: it finds the run even after a crash or a
   closed window, resumes its session, restarts a step killed before its session began, and after a quota stop
   hands the step to the other agent with the brief and the diff (`--same` keeps the same session). Otherwise the
   CLI's own resume (`codex exec resume <id>` / `claude --resume <id>`).
3. If that session can't continue (quota still out, other agent), start the step fresh
   from the brief + `git diff <last snapshot>`; uncommitted work is still in the tree.
4. `retry after` shown for a quota stop → wait, or hand off only if delegation is authorized.

## When starting a long task

1. Use **checkable**, **safe-to-resume** milestones with bounded work between checkpoints
   ("ensure X exists", not "append X"). Reuse an existing plan. Use task-split only when the
   dependencies need planning; saving progress does not require choosing a model.
2. `cp init --title "..." --step "..." --step "..."` → prints the task id.
3. Per step:
   - `cp start <task> <n> --agent codex --session <id>` (session id as soon as you know it;
     `cp session <task> <n> <id>` to add it later)
   - work; on anything worth remembering: `cp note <task> --step <n> "..."`
   - after its check passes: `cp done <task> <n> --note "what was verified"`
   - on a stop you can see: `cp fail <task> <n> --reason quota|error|blocked [--retry-after ...]`
4. Long silent work: `cp beat <task>` every few minutes (or `note`), so a crash is detectable.
5. All steps done and verified → `cp finish <task>`.

## What it records (so you know what to trust)

- Step status + who/when + session id → `plan.json`, append-only `progress.jsonl` (fsync'd).
- Code state at each `done` → `git stash create` snapshot kept under `refs/checkpoints/...`
  (does not touch your branch, index or files).
- Heartbeat in `lock.json`; a `doing` step whose heartbeat is > 10 min old is reported `interrupted`.
- Lost on a crash: at most the current step's unsaved reasoning — everything before the last
  `done` is safe.

Details and limits (中文): `README.zh.md`.
