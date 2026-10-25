---
name: agent-delegate
description: Execute an authorized cross-agent delegation through ccx and verify the result. Use for "派给 Codex/Claude" or an already-approved handoff; task splitting or token saving alone does not trigger delegation.
---

# Delegate to the other agent with ccx

`ccx` runs the other agent headless and returns a small JSON result. Use the configured command;
if it is not on PATH, resolve this skill directory to the bridge checkout and run
`python -X utf8 <checkout>/ccx.py`. Sub-agents never delegate again.

**Keep your own side cheap.** Delegating needs this skill and the brief, nothing else: don't open the
project's README, STATUS, handoff or docs just to delegate. The brief names files; the sub-agent reads them
(and `.ccx/context.md`) itself. Only if you can't find the ccx command, run `ccx -h` / `ccx run -h`.
Your own context is the biggest cost: every turn re-reads the whole conversation. Send big reads (many files, long
logs, research) out read-only and take back the conclusion; when the conversation is long and the next piece is
new work, hand over to a fresh one (section 5). Run long-output commands as `ccx sum -- <command>` (tests, logs,
`git diff`): you get the failures or the per-file summary, the full output stays on disk. `ccx lead` shows what a
turn costs you now; `ccx lead --breakdown` what it is made of.

## 1. Decide who and with what

Preserve the authorized target, model, effort and read/write scope. A specified model skips
routing; do not score it again. Use task-routing only for a real unresolved model choice,
and task-split only if the job needs decomposition. When the requested target/model must
stay fixed, use `--no-escalate --no-fallback`. Delegate self-contained, checkable pieces;
parallel execution requires authorization as well as independent work.
Choosing between doing it yourself, your own built-in sub-agent and ccx, and when DeepSeek fits:
`references/three-way.md`.

## 2. Brief (≤ 200 words)

Goal · files/dirs to look at · constraints · how to verify · what "done" means.
Point to existing source files rather than copying background. Reuse `.ccx/context.md` if
present; update it only when context maintenance is part of the authorized task.
Template: `references/brief-template.md`.

## 3. Run

```
ccx run --from <you> --files 3 --coupling cross --clarity goal "brief..."  # routed; may edit (default)
ccx run --from <you> --model <m> --effort <e> --minutes <n> "brief..."   # explicit pick; --minutes = how long a
#   skilled engineer would need. Without it (or the rubric flags) the run has no difficulty and its verdict can't
#   teach routing: in the seven-cores A/B dozens of luna-low runs taught it nothing (2026-10-24)
ccx run ... --task <id> --step <n>   # session id saved into task-checkpoint at once
ccx run ... --mode read          # analysis only (without --mode, ccx infers read/write from the brief; follow it)
ccx run ... --check "CMD"        # acceptance command: the sub-agent runs it, ccx runs it again (failure = failure)
ccx run ... --risk visible       # user-facing / critical work: another vendor's cheap model reviews the diff
ccx run ... --review on|off      # force or skip that review (auto: risk, 50+ code lines, unsure, claims vs diff)
ccx run ... --worktree           # isolate edits on branch ccx/<run_id>
ccx batch plan.json              # independent tasks in parallel (writers auto-isolated)
ccx resume <run_id> "follow-up"  # same sub-session: no re-briefing, cache stays warm
# the next `ccx run` from this conversation (same folder + agent, < 1 h) continues the sub-session by itself;
# --new for a fresh one; --fork (Claude -> Claude) starts from a copy of your whole conversation
```
Result JSON: status, summary, files_changed, verification, open_questions, next_step, tokens.
A quota/rate-limit stop retries once on the other agent (`--no-fallback` to stop instead);
a timeout or crash keeps the session id — `ccx resume <run_id>` continues where it stopped.

For work where a wrong result costs more, let the risk choose how it is done: `ccx way --risk low|visible|critical
"brief" [--check CMD]`. low = one agent (review when worth it); visible = another vendor plans, one builds, the
planner accepts (one fix round); critical = two vendors each build a version in a worktree and a third compares —
about twice the cost, so ask the person first and pass `--yes`. Nothing is merged for you. Builders are ordered by
their first-time-right rate for that kind of work (`ccx way --stats`).

## 4. Check, don't trust

A printed result with a `run_id` means that delegation ran: do not send the same brief again (a real Codex lead
did, after a run that had already passed, in the seven-cores check of 2026-10-24); to add to it, `ccx resume <run_id>`.
The summary is a claim. Inspect the changed files or returned evidence. Reuse valid checks
for the same artifact; run affected checks when missing, stale or contradicted.
**When the result's `check` shows ccx ran your `--check` command and it passed, do not run it again yourself**:
read `check` and the diff. Each extra lead turn re-reads your whole conversation; in the H11 trial (2026-10-24) a lead
that re-ran the check saved nothing by delegating, one that trusted it saved a turn per task. Re-run only what the
check does not cover.
`verification: not-run` = unverified — say so. A `review` field is that independent review: `pass` (its notes
are optional reading) or `issues` with `file:line`; after one fix round, `kind: review_failed` is yours to decide.
Then give your verdict:
`ccx verify <run_id> --ok 1|0 [--reason unfinished|wrong|overreach|other] [--note "..."]` — this calibrates
routing (and splitting, if `--minutes` was given) and closes the checkpoint step. Runs nobody judges get a
probable verdict after 12 h when ccx's check or the self-check and the review passed (`ccx undo --apply` counts as
wrong); your verdict always overrides it, so give one whenever you actually looked.
`ccx show <id> --full` only when the compact result is not enough.

## 5. Switching leads

Handing the rest of the work to the other tool as the new lead: `ccx handoff --by <you> --to <other> "…"`
(done · decisions and why · where it stopped · next · key files · open questions; ≤ 1 page) and `--next "…"` per
remaining task. The other side's next session start shows it once.
"交接给 X" / "hand over to X": you can still write → the command above. The old lead can't (quota out, crashed,
window closed) → `ccx handoff --from-transcript <old lead> --to <X>`: built from its session file by code. Whoever
takes over checks its claims (files exist, tests pass) before trusting them.
Your own conversation got long (the per-turn hint says so) and the next piece is new work: ask the person, then
`ccx fresh` — the handoff comes from this conversation's file and a new conversation of the same tool here starts
with it.

## 6. Memory

Only when memory maintenance is authorized: store a needed durable fact with
`ccx mem add "one sentence" --by <you>`. Delegation alone does not authorize a memory write.
No task chatter; the other side receives only new lines at its next session start.
Add `--source` (where it came from); replace a note that stopped being true with `--supersedes N`. A standing rule
the user states goes to the user's shared instructions, only after they agree; never copy one tool's own
automatic memory into the other.

## 7. A decision that is costly to get wrong

Hard to undo (a data format, a migration, a public interface, a dependency), touching safety or money, or the person
said it matters: before committing to one answer, **ask the person** whether models from other vendors should talk
it through. Say the question in one line and what it may cost (`ccx discuss --dry-run "question"`: who takes part,
at most how many calls, estimated $). Only on their yes:
`ccx discuss "question" [--context-file notes.md] [--with codex,claude,gemini] [--rounds 1-3]` — one proposes, one
finds faults, one judges; only points travel between turns. Read `result` (recommendation, consensus,
disagreements, reasons); the person sees the turns in `ccx ui`. It advises; the decision stays with you and the person.
Not for routine choices: every turn is a full model call.
