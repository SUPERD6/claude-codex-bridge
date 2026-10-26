"""Hold-out tasks for round 5 (backlog C1: overfitting): real changes from this repository's own history that were
never used while ccx was tuned on scripts/eval/tasks_r5.py. Final claims about ccx come from these, not from r5.

Same form and difficulty band as tasks_r5.py: the whole repository at the parent of a merged commit, a brief written
from the person's point of view (what is wrong or missing, then the interface a fair task needs: names, flags,
required strings, but none of the hidden test's inputs or expected values), and as the hidden acceptance test the
commit's own test file. Chosen so that

- no commit is an r5 task commit, and none touches the feature area of an r5 task (r5: memory for briefs and the run
  recap, the work queue, batch plans, Codex hook text, the project catalog, dsh archiving, quota stops, the ui
  count, the memory use report); where a file is shared (delegation.py, delegate.py, commands/memory.py) the
  function is a different one;
- none is one of the loop's own fixes made while tuning on r5 (#122 and later);
- the reference change is 5-91 changed non-test lines (`.py` / `.toml` outside tests/, docs not counted) in 1-5
  files, like r5 (5-91 lines, median ~40);
- the hidden test file fails at the parent and passes at the commit: `python scripts/eval/holdout_check.py`;
- `deselect` (optional) names tests of that file that are unrelated to the task and fail at random under load
  (test_bg_run polls a background run for 10 s and reads its run.json while it is being replaced): scoring leaves
  them out, so a right answer is never marked wrong by them.

Use: `python scripts/eval/r5.py run --taskset holdout ...` (results go to their own file).
"""
from __future__ import annotations

T = []


BG_RUN = "tests/test_adapters.py::TestBackgroundAndSend::test_bg_run"


def task(id: str, commit: str, tests: list[str], area: str, size: int, files: int, brief: str,
         deselect: tuple[str, ...] = ()) -> None:
    T.append({"id": id, "commit": commit, "tests": tests, "area": area, "size": size, "files": files,
              "brief": brief.strip(), **({"deselect": list(deselect)} if deselect else {})})


task("init-gitignore", "ee18c59", ["tests/test_ccx.py"], "project init", 13, 1, """
`ccx project init` appends its `.ccx/...` ignore lines to the project's `.gitignore` even when git already ignores
those paths, for example when the `.gitignore` already ignores the whole `.ccx/` folder. The file then collects
lines nobody needs.

Wanted: before adding a line, ask git whether it already ignores what that line covers (for example with
`git check-ignore`), and add only the lines git does not cover yet. When nothing is missing, `.gitignore` stays
exactly as it was. The `gitignore_added` list in `ccx project init`'s JSON output names only the lines that were
really added. Outside a git repository (or when git cannot be run) it behaves as before.
""")

task("leads-from-adapters", "b67572f", ["tests/test_leads.py"], "adapter registry", 18, 3, """
Which tools can be the lead is written out by hand in each command: the `--as` choices of `ccx mem delta`,
`ccx fresh` and `ccx lead` are separate hard-coded lists (one of them is the list of agents wired for shared memory),
so making another agent a lead means finding and editing all three. Every adapter in `ccx/agents/` already says
whether it can lead (`can_lead`).

Wanted: `ccx.agents.leads()` returns the names of the adapters whose `can_lead` is true, worked out from the
adapter registry each time it is called, so that a new lead only needs its adapter changed. All three commands take
their `--as` choices from it, and an agent that cannot lead is rejected by the argument parser like any other
invalid choice.
""")

task("check-fail-escalates", "93c4256", ["tests/test_adapters.py"], "run-loop escalation", 30, 4, """
With `ccx run --check CMD`, a cheap model that wrongly says it is done stops there: ccx runs the check, sees it
fail, and the run ends as a failure although a stronger rung was still available. Today only `blocked` / `failed`
results escalate.

Wanted:
- When a sub-agent reports `done` or `partial` but ccx's own run of the check fails, and a higher rung is left in
  the plan, that attempt counts as failed (its `kind` in run.json becomes `check_failed`) and the run climbs one
  rung, continuing the same session when the next rung is the same agent. The next prompt tells the sub-agent
  "you said done, but `<cmd>` failed", with the exit code and the end of the check's output. The run's JSON shows
  the climb in `escalated` as other escalations do.
- The check runs once per attempt: ccx does not run it again at the end for an attempt it has already checked.
- On the last rung, or with `--no-escalate`, a failed check stays a failure as today (`kind` `check_failed`, no
  further sub-agent call).
- `save` becomes the default tradeoff: in `config/tiers.toml` and in the code fallbacks that still assume
  `balanced`.
""", deselect=(BG_RUN,))

task("review-min-lines", "b37a345", ["tests/test_review.py"], "review trigger", 32, 3, """
With `--review auto` (the default) the independent review runs only for `--risk visible/critical`, a sub-agent
that says it is unsure, or claimed files that do not match the diff. A large change that looks routine gets no
review at all.

Wanted: auto mode also reviews a write run whose diff has at least `[review] min_lines` changed code lines
(default 50; `0` turns this trigger off). Documentation files (`.md`, `.txt`, `.rst`, `.adoc`) do not count.

Interface:
- `ccx.review.code_lines(diff: str) -> int`: added plus removed lines in the code files of a unified diff (the
  `---` / `+++` file headers are not changed lines). A file's lines start at its `+++ ` header (the diff may
  come without `diff --git` or `---` lines).
- `ccx.review.reason(mode, risk, result, claimed, actual, lines=0, min_lines=50)`: the new trigger's reason is
  "<n> changed code lines" (e.g. "75 changed code lines"); an explicit request and the risk reasons still come
  before it.
- `min_lines = 50` in the `[review]` table of `config/tiers.toml`; the run loop passes the diff's code-line count
  and the configured value.
""")

task("handoff-summary", "8ea4e8e", ["tests/test_sessions.py"], "handoff at session start", 35, 1, """
A handoff (`ccx handoff --by A --to B "..."`) is shown once at the receiver's next session start
(`ccx mem delta --as B`). A long one is simply cut at 6000 characters, so the new lead mostly reads finished
history and the part about what to do next can be lost.

Wanted: a handoff of up to about 2000 characters is still shown whole. A longer one is shown as a summary: its
`# ` title (if any) plus only the `## ` sections a new lead needs to start, i.e. sections whose heading is about
what comes next, where the work stopped, open questions, key files, notes, rules or todos (also the Chinese headings
接下来, 下一步, 待办, 停在, 未解决, 问题, 关键文件, 注意, 规则). Inside those sections, finished checklist items
(`- [x]`) and their indented continuation lines are left out. The summary is kept to about 2500 characters and ends
with the line "(summary; the full handoff is in .ccx/handoff.md)". The full text stays in `.ccx/handoff.md`.
""")

task("undo-not-verdict", "8353f65", ["tests/test_verdicts.py"], "undo and verdicts", 37, 4, """
`ccx undo <run_id> --apply` puts back the files a write run changed, and it also records the run as wrong. But
people undo to try again or to split the work differently, not only because the work was wrong, and that "wrong"
teaches routing (it changes the routing state) all the same.

Wanted:
- Undoing alone records no verdict: the routing state and the verdict events stay as they were, and the `verdict`
  field of the JSON output starts with `none` (saying the run waits for the person's `ccx verify` or
  `ccx undo --wrong`).
- An undone run is left alone by the probable-verdict pass (`ccx verify --sweep`): it waits for the person.
- Every applied undo appends an event to the ledger: `{"type": "undo", "run_id": ..., "reason": "undone",
  "wrong": <true|false>, "ts": ...}`.
- New flag `ccx undo <run_id> --apply --wrong`: also records the run as wrong with reason `wrong`, exactly as the
  person's own `ccx verify <run_id> --ok 0 --reason wrong` records it (an ordinary verdict, not a soft, probable
  one), unless the run already has a verdict; the JSON `verdict` is then "recorded as wrong (undo --wrong)".
""")

task("doctor-codex-sandbox", "883be56", ["tests/test_codex_lead_sandbox.py"], "doctor", 55, 2, """
A Codex lead working in its sandbox cannot use `ccx run`: ccx writes run records into the hub, and the sub-agent
CLI it starts needs the network. Codex's `workspace-write` sandbox blocks both unless it is configured, and on
Windows even a configured workspace-write did not work in real runs (only `danger-full-access` did). `ccx doctor`
should say so, and a permission error from a ccx command should point there.

Interface:
- `ccx.doctor.codex_lead_sandbox(config_text: str, hub, windows: bool | None = None) -> tuple[str, str]`:
  (state, detail) from the text of Codex's `config.toml`; `windows` defaults to whether this is Windows. The state
  is `ok`, `WARN` or `Unknown`.
  - `sandbox_mode = "danger-full-access"`: `ok`.
  - On Windows anything else: `WARN`, and the detail says to give lead sessions `danger-full-access` (e.g. a
    profile).
  - Elsewhere `read-only` is `WARN`. `workspace-write`, or no `sandbox_mode` at all (Codex then decides; check it
    as workspace-write and say it is "not set"), is `ok` only when `[sandbox_workspace_write]` lists the hub or a
    folder above it in `writable_roots` and has `network_access = true`. Otherwise `WARN`: the detail names each
    missing part ("the hub is not a writable root", "network_access is off") and gives the exact lines to add, with
    the hub path written with forward slashes.
  - Text that is not valid TOML: `Unknown`.
- `ccx doctor` shows a row "Codex as lead (sandbox)" from it when `codex` is installed.
- When a command fails with a PermissionError, the error JSON also gets a `hint` that points to that doctor row.
""")

task("discuss-auto-tier", "5b68121", ["tests/test_discuss.py"], "discussions", 56, 2, """
`ccx discuss` talks at one tier for every participant (`--tier`, default T2). An agent whose subscription quota is
projected to run out before it resets should talk on its cheap model instead.

Wanted: `--tier auto`, the new default: T2, except T1 for a participant whose projected quota share at its reset is
above 100% (the projection `ccx/quota.py` already makes, `quota.pressure`). A tier given explicitly applies to
everyone as before. The tiers chosen are used for the turns, kept in the saved discussion and shown by
`ccx discuss`.

Interface:
- `ccx.discuss.tiers(p, names, tier="auto", quota=None) -> (tiers, why)`: `tiers` maps each agent to its tier;
  `quota` (agent -> projected fraction of its window, e.g. 0.85) is read from ccx when None. With `auto`, `why` has
  an entry for every agent: the projected share as a percentage (like "85%") when there is a reading, or a text
  containing "no quota reading" when there is none. With a fixed tier, `why` is empty.
- `ccx.discuss.estimate(..., tier=...)` and `ccx.discuss.run(..., tier=...)` take either one tier for everyone or
  such a per-agent dict; the estimate's `models` and `tier` are per agent.
- The `ccx discuss --dry-run` JSON has `tier_why` only when the tier is auto.
""")

task("send-busy-guard", "e08ce82", ["tests/test_adapters.py"], "ccx send to a live Codex thread", 57, 2, """
`ccx send --to codex --thread <id> "message"` pushes a message into a live Codex conversation (`codex queue`) even
while the person is typing in it.

Wanted: `send` holds the message while that conversation is busy. Busy means a turn is running (the last
`task_started` event has no `task_complete` after it) or the person's last `user_message` was less than 90 seconds
ago. The events are the `event_msg` lines (with `timestamp` and `payload.type`) of the newest session file whose
name contains the thread id, under `$CODEX_HOME/sessions`.

Interface:
- `ccx.usage.thread_activity(thread, home=None, now=None) -> {"busy": bool, "why": str}`; when busy because of a
  recent message, `why` says how long ago, in the form "you wrote N s ago". No session file: not busy.
- `ccx send` waits up to `--wait` seconds (default 120), looking again every 10 s or so. If the conversation is
  still busy it sends nothing, prints `{"ok": false, "held": true, "thread": ..., "why": ..., "next": ...}` and
  exits with code 2.
- `--force` sends at once.
""", deselect=(BG_RUN,))

task("ledger-repair", "ce4195a", ["tests/test_ccx.py"], "accounting repair", 86, 2, """
Codex usage recorded before a recent counting fix is over-counted. `codex exec resume` reports the whole session's
running total, and old run records stored that total as each resumed attempt's usage, so `ae_usd` and the ledger
count the earlier turns again. New records already store only the growth (`delegate._codex_total`,
`delegate._codex_growth`) and keep the session's total in the attempt's `codex_total`.

Wanted: `ccx repair [--apply]`.
- Without `--apply` it is a dry run: it reports what it would fix and changes nothing.
- With `--apply`: going through the run records (`<hub>/ccx/runs/*/run.json`) oldest first, a Codex attempt without
  `codex_total` that continues a session seen before gets its `usage` replaced by the growth over that session's
  previous total, and its `ae_usd` recomputed from the price table. Every Codex attempt it has looked at then
  carries `codex_total`, so a second repair finds nothing to fix.
- The ledger rows of the fixed runs are rebuilt the same way `ledger.append` writes them, after the ledger has been
  backed up to a file next to it; other rows (events) stay as they are. Files are replaced atomically.
- JSON output: `applied`, `runs_fixed`, `runs` (each with `run_id`, `ae_before`, `ae_after`) and the totals
  `ae_before`, `ae_after`.
""")

IDS = [t["id"] for t in T]


def by_id(task_id: str) -> dict:
    return next(t for t in T if t["id"] == task_id)
