---
name: agent-delegate
description: Execute an authorized cross-agent delegation through ccx and verify the result, or offer one in a line before a large, checkable piece of work (the person decides). Use for "派给 Codex/Claude", an already-approved handoff, or that offer; task splitting or token saving alone does not start a delegation.
---

# Delegate to the other agent with ccx

`ccx` runs the other agent headless and returns a small JSON result. Use the configured command;
if it is not on PATH, resolve this skill directory to the bridge checkout and run
`python -X utf8 <checkout>/ccx.py`. Sub-agents never delegate again. Only if you can't find the command, run
`ccx -h` / `ccx run -h`.

**Your own context is the biggest cost:** every turn re-reads the whole conversation. Send big reads (many files,
long logs, research) out read-only and take back the conclusion. Run long-output commands as
`ccx sum -- <command>` (tests, logs, `git diff`): you get the failures or the per-file summary, the full output
stays on disk. `ccx lead` shows what a turn costs you now; `ccx lead --breakdown` what it is made of.

**If you are DeepSeek:** ccx tells who leads from the environment (dsh: `DSH_SESSION_ID`; Claude Code on DeepSeek:
`ANTHROPIC_BASE_URL`; Codex on DeepSeek: `model_provider` in config.toml, else set `CCX_LEAD=deepseek-codex`), so
`--from` is not needed. dsh on Windows has Windows PowerShell 5.1: call `& "<python>" "<ccx.py>" run ...` and put a
brief longer than a line in a file (`--brief-file`). dsh needs `DSH_PERMISSION_MODE=danger-full-access` (in
`workspace-write` ccx cannot write its run records; 0.2.1-rc.3, real run). That gives every command the person's
rights: say so before asking for it.

## 0. Offer it; the person decides

Nobody asked you to delegate, but the next piece is large and checkable: about 15 minutes or more for a skilled
engineer, with an acceptance command or a plain test of "done", and a brief of ≤ 200 words can carry what it needs.
Estimate before saying anything:
```
ccx propose --lead <your rung, e.g. claude:opus:high> --minutes <n> [--files N --coupling one|cross|system] "the task in one line"
```
It reads your own conversation's size by itself and returns `worth_offering`, the cost delegated vs here, the
odds, and `say`.
- `authorized: true` (it comes with `worth_offering: true`; only when the person picked a tier in their own
  settings, `ccx config set policy.picked <tier>`, never from a flag you pass): the tier already decided, so don't
  ask; tell the person its `say` line, run its `next` once, for that task, with the estimate you proposed with,
  and accept as it says (task-routing, Tiers). A project's autonomy level (L0/L1) may still stop the run before
  edits: then ask as that output says.
- `worth_offering: false` → do it yourself and don't mention it.
- `worth_offering: true` without `authorized` → ask with that one line (cost and odds, nothing more) and wait;
  don't start the work meanwhile.
- yes → `ccx run --proposal <id> --minutes <n> [--check "CMD"] "brief"`, **without `--no-ab`** (that flag marks an
  evaluation run, which no statistic counts; a running `ccx trial` may hand the task back to you: then do it and
  close it with `ccx ab done`). Check it (section 4) and always give `ccx verify <run_id> --ok 1|0`.
- no → `ccx propose --no <id>`, do it yourself, and don't offer that kind of piece again in this conversation.
One offer per piece. Small edits, questions, and work that needs your judgement turn by turn are never offered.
The same rule — one line with what it costs, act only on a yes — holds for a discussion between vendors (section 7).

## 1. Decide who and with what

Preserve the authorized target, model, effort and read/write scope. A specified model skips
routing; do not score it again. Use task-routing only for a real unresolved model choice,
and task-split only if the job needs decomposition. When the requested target/model must
stay fixed, use `--no-escalate --no-fallback`. Delegate self-contained, checkable pieces;
parallel execution requires authorization as well as independent work.
Choosing between doing it yourself, your own built-in sub-agent and ccx, and when DeepSeek fits:
`references/three-way.md`. Picking a tier yourself (`--tier T0..T4`): `references/rubric.md`.

## 2. Delegate cheaply

Round 5 (2026-10-26, large tasks): a lead using ccx sent a median 8 requests, against 6 with its built-in
sub-agent. The extra requests came from the habits below.
- **Brief = the person's own words, verbatim** (above all interfaces, names, exact strings, numbers) + file paths
  you already know + the acceptance command. Never paraphrase an interface ("the first hint that matches"
  re-worded as "earliest position" came back wrong). Don't read the code base, README, STATUS or docs to write
  it: the sub-agent reads them (and `.ccx/context.md`) on the cheaper model. Reuse an existing `.ccx/context.md`;
  update it only when keeping that context is part of what you were asked to do. Shape: `references/brief-template.md`.
- **Long or multi-file work: one call,** `ccx run ... --bg --wait 540` with your shell tool's timeout at 600000 ms
  (Claude Code's Bash limit is 10 minutes; a Codex or DeepSeek lead sets `--wait` about a minute under its own
  tool-call timeout). It prints the run_id at once (stderr) and the final result in the same call, like a plain
  `ccx run`. If it is still running then: `ccx show <run_id> --wait`, again while it says running. Never
  `ccx resume` a run that is still running. Don't pipe ccx output through `tail`/`head`: the result is one small
  JSON object, and a pipe on a long run hits your shell's timeout.
- **Your own sub-agents next to ccx:** pieces done by your built-in sub-agents and pieces done through ccx never
  write the same files at the same time; a ccx writer running beside your own writers goes in `--worktree` or
  through `ccx q run` (its undo snapshot, diff and check would otherwise take in their edits). Their model: the
  one ccx names (a `builtin` choice's `how`, or `builtin_model` from `ccx route`) as Claude Code's Agent tool
  `model` (sonnet | opus | haiku | fable, Claude Code 2.1.309); otherwise omit it (they inherit yours).
- **Several authorized pieces:** plan with task-split `check`; pieces sharing a file go to one piece or to you,
  never in parallel (`q run` gives parallel writers in a clean git checkout their own worktree; otherwise they
  share this checkout). `ccx q add "<title>" --brief "..." --check "..."`
  per piece (`--dep <id>` for an order), then `ccx q run --bg`. Your own pieces, shortest first, must not touch
  a queued piece's files (its undo snapshot and check would take in your edits). `ccx q ls` shows a running
  piece's run id as `live`: `ccx show <live ids> --any --wait` hands back each one as it finishes. Accept by
  check+review plus a diff glance, then run the union of the checks. Pieces under `waiting` / `unmerged` ran in a
  worktree: merge each listed branch, then `ccx q done <id> --ok 1` and `ccx q run` again; `dep_blocked` pieces wait
  on one that failed (`references/three-way.md`). `last_run` with `stopped: backpressure`
  (quota/auth): start nothing new until it has reset.
- **Leave `--review` at its default (auto)**; `--review on` / `--risk visible` only for risky or user-facing work
  (and for an L2 auto-merge, which needs a passed review).
- **Never ask the sub-agent to commit** (Codex's sandbox blocks `.git` writes: wasted turns). You commit after
  accepting.
- **A project named, no path given** ("the desk pet"): `ccx where "<their words>"` (code only, free); one `pick` →
  `ccx run --project <name>`, several → ask which. If its rules speak of approval, ccx stops and quotes them
  (`approval_rules`): decide from them or ask the person; only then run again with `--rules-ok`. More: project-manager.

## 3. Run

```
ccx run --from <you> --files 3 --coupling cross --clarity goal "brief..."  # routed; may edit (default)
ccx run --from <you> --model <m> --effort <e> --minutes <n> "brief..."   # explicit pick; --minutes = how long a
#   skilled engineer would need. Without it (or the rubric flags) the verdict can't teach routing
ccx run ... --bg --wait 540      # long work, one call (shell timeout 600000 ms): the result, or still running
ccx show <run_id> --wait         # still running after that: wait again (again while it says running)
ccx stop <run_id>                # stop a running delegation (its whole process tree); resume continues it
ccx run ... --task <id> --step <n>   # session id saved into task-checkpoint at once
ccx run ... --mode read          # analysis only (without --mode, ccx infers read/write from the brief; follow it)
ccx run ... --check "CMD"        # acceptance command: the sub-agent runs it, ccx runs it again (failure = failure)
ccx run ... --risk visible       # user-facing / critical work: another vendor's cheap model reviews the diff
ccx run ... --review on|off      # force or skip it; default auto (risk, 50+ code lines, unsure, claims vs diff,
                                 # weak evidence: no check, a check running no tests, tests not naming the
                                 # changed files/functions, or a check that passed wrong work before;
                                 # these use the other vendor's cheapest rung, at most 20 a day: weak_daily)
ccx run ... --worktree           # isolate edits on branch ccx/<run_id>
ccx batch plan.json              # independent tasks in parallel (writers auto-isolated once committed)
ccx resume <run_id> "follow-up"  # same sub-session: no re-briefing, cache stays warm
# the next `ccx run` from this conversation (same folder + agent, < 1 h) continues the sub-session by itself;
# --new for a fresh one; --fork (Claude -> Claude) starts from a copy of your whole conversation
```
Result JSON: status, summary, files_changed, diffstat, check, verification, open_questions, next_step, tokens.
A quota/rate-limit stop retries once on the other agent (`--no-fallback` to stop instead);
a timeout, crash or `ccx stop` keeps the session id — `ccx resume <run_id>` continues where it stopped.

For work where a wrong result costs more, let the risk choose how it is done:
`ccx way --risk low|visible|critical "brief" [--check CMD]`. low = one agent (review when worth it); visible = another vendor plans, one builds, the
planner accepts (one fix round); critical = two vendors each build a version in a worktree and a third compares —
about twice the cost, so ask the person first and pass `--yes`. Nothing is merged for you. Builders are ordered by
their first-time-right rate for that kind of work (`ccx way --stats`).

## 4. Check, don't trust

A printed result with a `run_id` means that delegation ran: do not send the same brief again; to add to it,
`ccx resume <run_id>`. The summary is a claim.
- **Look first at `needs_lead`, `edited_tests` and `namecheck`** when the result has them (`namecheck`: names
  no scope defines in the changed functions, a likely NameError the tests missed).
- **A passed `check` that runs the relevant tests, plus `files_changed` / `diffstat`, is enough**: don't re-run it
  (H11, 2026-10-24: a lead that re-ran it saved nothing by delegating). Run tests or read the full diff yourself
  only when the check failed, was absent or `weak` (that command has passed wrong work here before), or the status
  is partial/blocked.
- `check_broken` = the check tested nothing: `ccx resume <run_id> --check "..."`. The task names an entry point
  (a command, a CLI) and no test runs it as a real process: resume once asking for one.
- `verification: not-run` = unverified — say so.
- A `review` field is the independent review: `pass` (its notes are optional reading) or `issues` with
  `file:line`. ccx runs one fix round itself (`show --wait` follows it); after that, `needs_lead` is
  your call and `review_failed` is below. Judge `kind` only from a final result: `ccx run ... --bg --wait` that
  printed one, or `ccx show <run_id> --wait` (both follow the fix round; a plain `show` can see the first record
  before the fix round starts, and resuming then collides with it). `review_issues` there means no fix round
  ran (no session to resume, or it failed to start): fix it yourself or dispatch it again.
- `review_failed` (the fix round did not satisfy the review): check each `[must]` item against the diff; fix
  the real ones yourself and drop the wrong ones. Don't `ccx resume` for it.

Then give your verdict:
`ccx verify <run_id> --ok 1|0 [--reason unfinished|wrong|overreach|other] [--note "..."]` — this calibrates
routing (and splitting, if `--minutes` was given) and closes the checkpoint step. Unjudged runs get a probable
verdict after 12 h when the check or self-check and the review passed; an undone run waits for yours
(`ccx undo --apply --wrong` records it as wrong in the same step). Your verdict always overrides it, so give one
whenever you actually looked. `ccx show <id> --full` only when the compact result is not enough.

## 5. Switching leads

Handing the rest of the work to the other tool as the new lead: `ccx handoff --by <you> --to <other> "…"`
(done · decisions and why · where it stopped · next · key files · open questions; ≤ 1 page) and `--next "…"` per
remaining task. The other side's next session start shows it once.
"交接给 X" / "hand over to X": you can still write → the command above. The old lead can't (quota out, crashed,
window closed) → `ccx handoff --from-transcript <old lead> --to <X>`: built from its session file by code. Whoever
takes over checks its claims (files exist, tests pass) before trusting them.
Your own conversation got long (the per-turn hint says so) and the next piece is new work: ask the person, then
`ccx fresh` — the handoff comes from this conversation's file and a new conversation of the same tool here starts
with it. Give `--minutes` for the next work: with `lead.model_by_task` on (the person's setting) `ccx fresh` and
`ccx handoff` start the new lead on a model by difficulty. Never switch a running conversation's model.

## 6. Memory

Only when memory maintenance is authorized: store a needed durable fact with
`ccx mem add "one sentence" --by <you>` (`--project` puts it in this project's journal under `.ccx/` instead;
`ccx project status` shows that layer). Delegation alone does not authorize a memory write.
No task chatter; the other side receives only new lines at its next session start.
Add `--source` (where it came from); replace a note that stopped being true with `--supersedes N`. A standing rule
the user states goes to the user's shared instructions, only after they agree; never copy one tool's own
automatic memory into the other.

## 7. A decision that is costly to get wrong

Hard to undo (a data format, a migration, a public interface, a dependency), touching safety or money, or the person
said it matters: offer a discussion between models from other vendors the way section 0 offers a delegation — one
line with the question and what it may cost (`ccx discuss --dry-run "question"`: who takes part, how many calls at
most, estimated $, which model each uses), then wait. Only on a yes:
`ccx discuss --confirmed "question" [--context-file notes.md] [--with codex,claude,gemini] [--rounds 1-3]` (without
`--confirmed` you get only the estimate, nothing runs; `--bg` to keep working; follow it with `ccx discuss --show ID`).
One proposes, one finds faults, one judges. Read `result` (recommendation, consensus, disagreements, reasons); the
person sees the turns in `ccx ui`. It advises; the decision stays with you and the person. Not for routine choices:
every turn is a full model call.
