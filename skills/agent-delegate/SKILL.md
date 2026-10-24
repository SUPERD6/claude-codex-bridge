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
ccx run --from <you> --model <m> --effort <e> "brief..."   # explicit pick
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

## 4. Check, don't trust

The summary is a claim. Inspect the changed files or returned evidence. Reuse valid checks
for the same artifact; run affected checks when missing, stale or contradicted.
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

## 6. Memory

Only when memory maintenance is authorized: store a needed durable fact with
`ccx mem add "one sentence" --by <you>`. Delegation alone does not authorize a memory write.
No task chatter; the other side receives only new lines at its next session start.
Add `--source` (where it came from); replace a note that stopped being true with `--supersedes N`. A standing rule
the user states goes to the user's shared instructions, only after they agree; never copy one tool's own
automatic memory into the other.
