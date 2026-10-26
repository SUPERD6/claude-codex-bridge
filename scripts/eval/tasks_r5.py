"""Round 5 tasks: real changes from this repository's own history (docs/research/2026-10-26-r5-plan.md).

Each task is the whole repository at the parent of a merged commit (~19k lines of ccx code, ~300 files), a brief
written like an issue (what is wrong or missing, then the interface the maintainers' tests use), and as the hidden
acceptance test the test files of that commit. Screened: those tests fail on the parent and pass on the commit.

Unlike rounds 1-4 the agent has to find where the change goes in a large code base, so a lead doing it itself needs
many requests; that is what this round measures.
"""
from __future__ import annotations

T = []


def task(id: str, commit: str, tests: list[str], brief: str) -> None:
    T.append({"id": id, "commit": commit, "tests": tests, "brief": brief.strip()})


task("brief-words", "21cb3da", ["tests/test_brief_words.py", "tests/test_ccx.py"], """
Two problems with `ccx run`:

1. The shared notes a sub-agent's brief gets (`memory.for_brief`, by word overlap) are picked badly. Words keep the
   dots and dashes at their ends (`JSON.` is not `json`), and common words such as `the`, `with`, `我们`, `这个` count
   as overlap, so unrelated notes get in and the right one is missed. The L5 memory cases in
   `scripts/eval/l5_memory.py` show it: the `mem-json` note never reaches its brief.
2. A lead that pipes `ccx run`'s JSON through `| tail -5` loses the run_id, which is the first key.

Interface the tests use:
- `memory._words(text) -> set[str]`: lower-cased words with the `.` and `-` at their ends stripped (`ccx-run-` is
  `ccx-run`, `a.b.c` stays), no common English words (at least `the`, `and`, `with`, `this`, `that`); Chinese runs
  are split into two-character pairs and common pairs (at least `我们`, `这个`) are dropped:
  `_words("我们这个") == {"们这"}` and `"记忆" in _words("我们的记忆")`.
- Over the 6 L5 cases (each with the 3 distractor notes), every case's own note is picked and at most 2 unrelated
  notes are picked in total.
- `ccx run` and `ccx resume` output: the JSON's LAST key is `recap`, one line like
  `ccx run <run_id>: status=done ok=true check=passed review=<verdict or none> ... next: ccx show <run_id>`
  (it must contain `ccx run <run_id>: status=done ok=true check=passed review=` and end with
  `next: ccx show <run_id>`). Other keys unchanged.
""")

task("q-killed-spend", "8887d6d", ["tests/test_recover.py"], """
`ccx q`: when the whole `ccx q run` process tree is killed (the machine sleeps, the terminal is closed), the run that
was in progress stays `running` in its run.json forever, and what it spent never reaches the ledger or the queue
item. `ccx stats` already knows how to close dead runs (`recover.sweep`, usage read back from the session file).

Wanted: `ccx q run`, `ccx q resume` and `ccx q ls` first close such dead runs as interrupted (state `interrupted`,
last attempt kind `killed`, its spend written to the ledger once), and `ccx q resume` adds what the item's runs
since it went `doing` spent to the item's `cost_usd`, then finishes the item as usual.

Interface the tests use: after a killed `q run` and a `ccx q resume`, the old run's record has state `interrupted`
and last attempt kind `killed` with `ae_usd > 0`, exactly one ledger row for that run, and the item (from
`ccx q ls`) is `done` with `cost_usd` at least the killed attempt's `ae_usd`. Tests use the fake CLIs in
`tests/fakes` (`FAKE_STATUS=hang`).
""")

task("q-resume-session", "6cdae1e", ["tests/test_queue.py", "tests/test_recover.py"], """
`ccx q resume` starts a `doing` piece over from scratch when `q run` was killed, even though its sub-agent session
was half way through. The item only learns its run id when the run returns, which a killed `q run` never reaches.

Wanted: `ccx q resume` finds the run a `doing` piece was in the middle of by its `q:<item id>` label (a review's fix
round included) and continues that run's session instead of starting over, telling the sub-agent it was stopped.
A piece whose run had already finished before `q run` was killed is marked done without running again.

Interface the tests use:
- `ccx q resume` prints JSON with `restored: {<item id>: "resumed" | "finished" | ...}`.
- A resumed piece continues the same session (for Codex: `exec resume <session_id>`), and the brief it gets starts
  with this note, word for word: "ccx was stopped while you were working on this piece. Go on from where you were:
  check what is already done before redoing anything." followed by a blank line and the original brief.
- A finished piece: `restored` says `finished`, no sub-agent is called again, the item becomes `done` and its
  `cost_usd` is greater than 0 (what its run spent).
""")

task("batch-review-risk", "528a5b6", ["tests/test_ccx.py"], """
`ccx batch --plan plan.json`: a task in the plan can say `"review": "off"` (or on/auto, as `ccx run --review`) and
`"risk": "visible"`, but both are dropped, so every batch runs with the default review (a real 3-task batch spent
$0.04 of its $0.05 on reviews it did not want).

Interface the tests use: `ccx.commands.delegation.cmd_batch(argparse.Namespace(plan=..., caller=...))` builds one
`Request` per plan task and calls `delegation.run(request, paths)`; the request's `review` comes from the task's
`review` (default `auto`) and its `risk` from the task's `risk` (default None). The request's `label` is the task id.
""")

task("codex-hook-text", "f51996c", ["tests/test_ccx.py"], """
Codex never shows ccx's session-start lines. Codex 0.164 reads hook output that starts with `[` or `{` as JSON; when
it is not valid JSON it counts the hook as failed and drops the output. Every ccx start line begins with `[ccx`.

Wanted: output meant for Codex (`ccx mem delta --as codex`, `ccx turn --as codex`) starts with a plain line, e.g.
"From ccx (shared memory and delegated work):", followed by the usual lines. Claude Code's output is unchanged.

Interface the tests use: `ccx.commands.common.hook_text(text, as_) -> str`: for `as_ == "codex"` text that starts
with `[` or `{` gets the plain line in front, other text is returned as it is (`hook_text("plain text", "codex") ==
"plain text"`); for other tools it returns the text unchanged (`hook_text("[x]", "claude") == "[x]"`).
`ccx mem delta --as codex --peek` still contains `[ccx shared memory` but does not start with `[` or `{`;
`--as claude` still starts with `[ccx`.
""")

task("projects-refresh", "2978690", ["tests/test_projects.py"], """
The project catalog (`ccx projects`, `ccx where`) goes stale: it is only rebuilt by a manual `ccx projects scan`.

Wanted: at session start (`ccx mem delta`, which the start-up hook runs) ccx rescans the catalog in a detached
background process when it is due; the start never waits for it, and only one scan runs at a time.

Interface the tests use:
- `ccx.projects.refresh_due(p, cfg, now=None) -> bool`: False with no roots and no catalog; True when roots are set
  and nothing was scanned yet; False right after `projects.refresh(p, cfg)`; True once the catalog is older than
  `[projects] refresh_hours` hours (default 24), also when the roots are no longer configured but the last scan had
  roots; `refresh_hours = 0` turns it off. While the guard file `p.state / "projects.scanning"` is less than
  10 minutes old a scan is in progress: not due.
- `refresh_later(p, cfg)` starts the background scan (writes the guard first); `ccx mem delta --as claude` calls it
  when due. Two quick starts in a row produce one scan; after it, `projects.load(p)["projects"]` holds the projects
  and the guard file exists.
""")

task("dsh-archive", "cae823e", ["tests/test_archive_after_run.py"], """
ccx archives sub-agent sessions after a run (`sessions.archive = after_run`), but not DeepSeek Harness (dsh)
sessions: dsh 0.2.1 has no archive command. The desktop app keeps its archived sessions in
`<DSH_HOME>/storages/workspace.json` under `global.archivedSessionIds`.

Wanted: archive a dsh run's session by adding its session id to that list; `ccx archive --restore <run_id>` and
`ccx resume` (before resuming) take it out again. Only that one id is added or removed, everything else in the file
stays as it was; the file is backed up once as `workspace.json.ccx-backup` and replaced atomically. A missing file is
skipped, not created. Session folders are never moved.

Interface the tests use: `ccx.archive.dsh_mark(sid, archived: bool) -> tuple[bool, str]`: `(True, "ok")` when it
changed the list, `(True, "already so")` when there was nothing to change, `(False, <reason>)` when the file does not
exist, the reason containing "never opened" (the desktop app was never opened). A `ccx run --to dsh` (fake dsh in
`tests/fakes`) ends with the session id appended to `archivedSessionIds`.
""")

task("quota-stop-log", "4b4eb2f", ["tests/test_quota_stop_log.py"], """
When ccx takes a failed attempt for a quota stop it falls back or waits, but leaves no trace of why. A wrong call
(the word "quota" in a task's own output, a new wording of a real limit) cannot be found later.

Wanted: every attempt taken for a quota stop appends its evidence to `<hub>/ccx/quota-stops.jsonl`, and `ccx quota`
shows the last five.

Interface the tests use:
- `ccx.quota.stop_evidence(cli, stdout, stderr, error) -> dict`: for Claude, a rejected `rate_limit_event` in the
  stream gives `{"by": "rate_limit_event", "event": <its rate_limit_info as it came>}`; otherwise the first quota
  hint that matches the text gives `{"by": "hint", "hint": <the hint>, "text": <the words around it>}`; nothing
  known gives `{"by": "unknown"}`.
- Each line of `quota-stops.jsonl` has `ts`, `run_id`, `agent`, `model` and the evidence keys.
- `ccx quota` JSON gets `recent_quota_stops` (the last five rows) only when there is at least one; other failures
  (an auth error) write nothing.
""")

task("waiting-evals", "05ffff9", ["tests/test_ui.py"], """
The session-start line "N delegated piece(s) wait for you" counts evaluation runs too, so on a real hub it says 33
when 16 are real. ccx already has one rule for runs that measured ccx: `ledger.is_eval` (label `eval-...`, started
with `--no-ab`, ccx's own probes such as `quota-probe`).

Wanted: the count leaves those out; `ccx ui` itself still lists them.

Interface the tests use: `ccx.ui.waiting(p) -> int`, the number of finished runs nobody judged yet, without
evaluation runs (a run labelled `eval-7c:...`, a run whose `route` has `no_ab: true`, a run labelled `quota-probe`).
""")

task("mem-report", "f223125", ["tests/test_memsuggest.py"], """
Nobody can tell whether the shared memory is used across tools: `memory.mark_used` only counts uses.

Wanted: record who used a note, in which project and how (session start, a search, a sub-agent's brief), and a
report `ccx mem report [--days 14] [--json]`: who wrote the notes that were used and who used them (writer x user),
per project, by way of use, and how many notes written in that time nobody used yet. Uses recorded before this
change count as `unknown`.

Interface the tests use:
- `memory.mark_used(p, seqs, by=None, project=None, via=None)`; the start-up line (`ccx mem delta --as claude`) marks
  with `via="start"`, a sub-agent's brief with `via="brief"`, search with `via="search"`; `project` is the working
  folder's name.
- `memory.use_report(p, days=14) -> dict` and `ccx mem report --json` print
  `{"matrix": {writer: {user: n}}, "via": {way: n}, "by_project": {project: {writer: {user: n}}},
  "written": {writer: n}, "written_never_used": n, ...}`; a use without `by` counts under user `unknown`, a writer
  whose notes nobody used is not in `matrix`.
- `ccx mem report` (text) has a header containing `written by \\ used by` and a total like `3 time(s)`.
""")

IDS = [t["id"] for t in T]


def by_id(task_id: str) -> dict:
    return next(t for t in T if t["id"] == task_id)
