"""Hold-out tasks for round 5 (backlog C1: overfitting; backlog 7: another code base): real changes that were never
used while ccx was tuned on scripts/eval/tasks_r5.py. Final claims about ccx come from these, not from r5.

Ten tasks: five from this repository's own history and five from two other open-source Python libraries (humanize,
MIT; itsdangerous, BSD-3). Same form as tasks_r5.py: the whole repository at the parent of a merged commit, a brief
written from the person's point of view (what is wrong or missing, then the interface a fair task needs: names,
flags, required strings, but none of the hidden test's inputs or expected values), and as the hidden acceptance test
the commit's own test file. Chosen so that

- no commit is an r5 task commit, and none touches the feature area of an r5 task (r5: memory for briefs and the run
  recap, the work queue, batch plans, Codex hook text, the project catalog, dsh archiving, quota stops, the ui
  count, the memory use report); where a file is shared (delegation.py, delegate.py, commands/memory.py) the
  function is a different one;
- none is one of the loop's own fixes made while tuning on r5 (#122 and later);
- the reference change is 5-91 changed non-test lines (`.py` / `.toml` outside tests/, docs not counted) in 1-5
  files, like r5 (5-91 lines, median ~40). The external fixes are small (8-21 lines), so the five tasks of this
  repository are the larger ones (32-86): together 8-86 lines, median ~26;
- the hidden test file fails at the parent and passes at the commit: `python scripts/eval/holdout_check.py`
  (external tasks: checked the same way with the commit's tests on the parent tree, PYTHONPATH=src);
- `deselect` (optional) names tests of that file that are unrelated to the task and fail at random under load
  (test_bg_run polls a background run for 10 s and reads its run.json while it is being replaced): scoring leaves
  them out, so a right answer is never marked wrong by them.

External tasks carry `repo` (a key of REPOS) and the full 40-character sha; scripts/eval/ext_repo.py fetches each
repository once per run and gives every unit the parent's tree in a fresh one-commit repository (no future history).
Their tests need the modules in REPOS[...]["needs"] in the Python that runs them (r5.py --ext-python), which must not
have the library itself installed (REPOS[...]["module"]).

Report results per repository and by commit date (r5.py summary: by_repo, ext_dates): the itsdangerous commits are
from 2018, humanize's a47a89e from February 2026, all before the models' training cutoffs (mid-2026), so they may be
remembered; only the humanize commits from August-September 2026 are after them.

Why ten and not all sixteen candidates: the confirmation run is 10 tasks x 5 arms x 3 rounds (~$19, ~5 h at two
tasks at a time, the size the loop budgeted), the same unit count per round as r5, and half of it from another code
base. The six candidates left out are kept in DROPPED with the reason; they are not scheduled.

Use: `python scripts/eval/r5.py run --taskset holdout ...` (results go to their own file).
"""
from __future__ import annotations

T: list[dict] = []
DROPPED: list[dict] = []        # candidates checked like the others but not in the set (`dropped` says why)

REPOS = {
    "humanize": {"url": "https://github.com/python-humanize/humanize.git", "license": "MIT",
                 "name": "humanize, a Python library that turns numbers, dates and times into human-readable text",
                 "pythonpath": "src", "stubs": ["src/humanize/_version.py"],   # hatch-vcs writes it at install time
                 "needs": ["pytest", "freezegun"], "pytest_min": "9.0", "module": "humanize",
                 # its benchmarks need pytest plugins (the `benchmark` fixture) that the eval does not install
                 "note": "If tests/test_benchmarks.py is there, it needs pytest plugins that are not installed here: "
                         "leave it out (--ignore=tests/test_benchmarks.py)."
                 # the whole existing suite, as a script's --check (r5's cheapest arm), without those benchmarks
                 , "suite": "python -m pytest -q tests --ignore=tests/test_benchmarks.py"},
    "itsdangerous": {"url": "https://github.com/pallets/itsdangerous.git", "license": "BSD-3-Clause",
                     "name": "itsdangerous, a Python library that signs data so it can be sent to untrusted places "
                             "and loaded back safely",
                     "pythonpath": "src", "stubs": [], "needs": ["pytest", "freezegun"], "module": "itsdangerous"},
}


BG_RUN = "tests/test_adapters.py::TestBackgroundAndSend::test_bg_run"


def task(id: str, commit: str, tests: list[str], area: str, size: int, files: int, brief: str,
         deselect: tuple[str, ...] = (), repo: str | None = None, dropped: str | None = None) -> None:
    t = {"id": id, "commit": commit, "tests": tests, "area": area, "size": size, "files": files,
         "brief": brief.strip(), **({"deselect": list(deselect)} if deselect else {}),
         **({"repo": repo} if repo else {}), **({"dropped": dropped} if dropped else {})}
    (DROPPED if dropped else T).append(t)


def external(t: dict) -> bool:
    """A task of another repository (scripts/eval/ext_repo.py), not of this one."""
    return bool(t.get("repo"))


task("init-gitignore", "ee18c59", ["tests/test_ccx.py"], "project init", 13, 1, """
`ccx project init` appends its `.ccx/...` ignore lines to the project's `.gitignore` even when git already ignores
those paths, for example when the `.gitignore` already ignores the whole `.ccx/` folder. The file then collects
lines nobody needs.

Wanted: before adding a line, ask git whether it already ignores what that line covers (for example with
`git check-ignore`), and add only the lines git does not cover yet. When nothing is missing, `.gitignore` stays
exactly as it was. The `gitignore_added` list in `ccx project init`'s JSON output names only the lines that were
really added. Outside a git repository (or when git cannot be run) it behaves as before.
""",
     dropped="the small end is now covered by the external tasks (8-21 lines)")

task("leads-from-adapters", "b67572f", ["tests/test_leads.py"], "adapter registry", 18, 3, """
Which tools can be the lead is written out by hand in each command: the `--as` choices of `ccx mem delta`,
`ccx fresh` and `ccx lead` are separate hard-coded lists (one of them is the list of agents wired for shared memory),
so making another agent a lead means finding and editing all three. Every adapter in `ccx/agents/` already says
whether it can lead (`can_lead`).

Wanted: `ccx.agents.leads()` returns the names of the adapters whose `can_lead` is true, worked out from the
adapter registry each time it is called, so that a new lead only needs its adapter changed. All three commands take
their `--as` choices from it, and an agent that cannot lead is rejected by the argument parser like any other
invalid choice.
""",
     dropped="the small end is now covered by the external tasks (8-21 lines)")

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
""", deselect=(BG_RUN,),
     dropped="mid band kept by the 32 and 37 line tasks; test_adapters.py is slow, needs a flaky test deselected")

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
""",
     dropped="mid band kept by review-min-lines / undo-not-verdict (32, 37 lines)")

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
""", deselect=(BG_RUN,),
     dropped="same size as discuss-auto-tier (57/56); test_adapters.py is slow, needs a flaky test deselected")

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

# ---------------------------------------------------------------- other repositories (scripts/eval/ext_repo.py)

task("hz-intword-carry", "ca892b368a535a79cc5e2181d052245b94fd6652", ["tests/test_number.py"],
     "humanize: intword rounding", 8, 1, """
`humanize.intword()` writes a big number with a word for its unit, and a value that rounds up to a whole next unit is
written as 1 of that next unit (with the default format, "1.0 <next unit>", never "1000.0 <unit>"). For very large
numbers, from about the sextillions up, this no longer happens: a value that rounds up to the next unit comes out as
"1000.0" (or "1000" with a "%.0f" format) of the smaller unit.

Wanted: the round-up carry works for every named unit up to decillion, whatever format is passed. Numbers above a
decillion and below a googol have no unit of their own; they stay written in decillions exactly as today.
""", repo="humanize")

task("hz-naturaldelta-nonfinite", "b48b37b187682ccc55b28ed1b7cfaa853dbca72f", ["tests/test_time.py"],
     "humanize: naturaldelta input checks", 10, 1, """
`humanize.naturaldelta()` given a float that is not a number (NaN) returns it unchanged as text, but given an
infinite float (positive or negative) it raises OverflowError.

Wanted: every non-finite float (NaN, infinity, minus infinity) is returned unchanged, as `str(value)`. A finite number
of seconds that is too large for a `datetime.timedelta` still raises OverflowError, as the docstring promises.
""", repo="humanize")

task("hz-naturaldate-tz", "a47a89ea9111a5eaba138c391e8a564134a15c60", ["tests/test_time.py"],
     "humanize: naturalday / naturaldate time zones", 19, 1, """
`humanize.naturalday()` and `humanize.naturaldate()` compare the date of the value with today's date on the
machine's local clock. For a timezone-aware datetime that is wrong near midnight: a moment that is "today" where the
datetime's own time zone is can come out as "tomorrow" or "yesterday", because "today" was taken somewhere else.

Wanted: when the value is a timezone-aware datetime, "today" is the current date in that value's own time zone, in
both functions. Dates and naive datetimes behave as before. `naturaldate()` keeps its rule of adding the year when
the date is more than about five months away, and otherwise hands the value, with its time zone, on to
`naturalday()`.
""", repo="humanize")

task("hz-natural-list-iterables", "ffdf407fdfe1a5738159b989eb2df190ed780448", ["tests/test_lists.py"],
     "humanize: natural_list input types", 20, 1, """
`humanize.natural_list()` joins items into readable text ("a, b and c"), but it only really works for lists (and
other sequences): a dictionary's keys view or a generator fails, although they are perfectly good collections of
items.

Wanted: `natural_list(items)` accepts any iterable, read only once (so a generator works), and gives the same text as
it does for a list of the same items: nothing gives "", one item gives that item as text, two give "x and y", more
give "x, y and z". Every item is turned into text with `str()` as now. The type hint and the docstring say Iterable.
""", repo="humanize")

task("its-timed-fallback-signers", "6c58e969a513646c8e37260417929770a4ab1b67",
     ["tests/test_itsdangerous/test_timed.py"], "itsdangerous: timed serializer key rotation", 21, 1, """
`itsdangerous.Serializer` takes `fallback_signers`, so that after a change of signer settings (another digest
method, say) data signed with the old settings still loads: `loads()` tries the main signer and then each fallback.
`TimedSerializer` accepts the same argument but its `loads()` ignores it: timed data signed with settings that are
only in `fallback_signers` is rejected as a bad signature.

Wanted: `TimedSerializer.loads()` tries the main signer and then the fallbacks, as `Serializer.loads()` does, and
returns the payload (with the timestamp when `return_timestamp=True`) from the first one that accepts the data;
`max_age` is checked as before. When none accepts it, the error from the last one tried is raised.
""", repo="itsdangerous")

task("its-future-timestamp", "c30678d19e37011890e2374cca04f7789e101793", ["tests/test_itsdangerous/test_timed.py"],
     "itsdangerous: timestamp age", 7, 1, """
`TimestampSigner.unsign(..., max_age=...)` accepts a signature whose timestamp lies in the future (a negative age,
e.g. after the clock or the timestamp offset changed), so such a value looks valid however large it is.

Wanted: with `max_age` given, a signature whose age is below zero raises `SignatureExpired` (with the payload and
the date it was signed, like the too-old case), instead of being accepted.
""", repo="itsdangerous",
     dropped="smallest external fix (one condition, 7 lines) and the oldest commit (2019), the likeliest to be "
             "remembered by a model; the other itsdangerous task keeps the second code base in the set")

IDS = [t["id"] for t in T]


def by_id(task_id: str) -> dict:
    return next(t for t in T if t["id"] == task_id)


def dropped_by_id(task_id: str) -> dict:
    return next(t for t in DROPPED if t["id"] == task_id)


# ------------------------------------------------------------ derives_from: every hidden check -> its brief sentence
# Round 5 lost 8 of its 13 failures on two briefs that left the hidden test's demand open. For the hold-out set each
# test the commit added or changed (NEW_TESTS: test functions whose body differs between the parent and the commit,
# read with ast from both versions; the rest of the file is the existing suite, a regression check) is mapped to the
# brief text it follows from, quoted word for word (whitespace aside): DERIVES_FROM[task] lists, per test, what it
# checks and the quotes. An entry with no quote says why (`regression`: behaviour the brief keeps "as today").
# tests/test_eval_holdout.py checks completeness only: every task has entries, they cover exactly NEW_TESTS (for
# this repository's tasks also recomputed from git when the commit is there), every quote is in the brief.
# Rules: the briefs are not edited to fit this map (r5's briefs are frozen; a hold-out brief changes only on an
# independent reviewer's finding, recorded here), and a test's literal inputs or expected values are never copied
# into a brief. REVIEW says who has checked the map; until an independent reviewer (a person or a model that did
# not tune ccx on r5) has, its fit is Unknown.
REVIEW = {"status": "draft", "mapped_by": "the PR-E author (Claude), from the commits' test diffs",
          "independent_review": None}

NEW_TESTS = {
    "review-min-lines": ["tests/test_review.py::TestReason::test_when"],
    "undo-not-verdict": ["tests/test_verdicts.py::TestVerdicts::test_undo_is_not_a_verdict_unless_wrong"],
    "doctor-codex-sandbox": [f"tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::{n}" for n in (
        "test_full_access_is_fine", "test_workspace_write_needs_the_hub_and_network",
        "test_configured_workspace_write_is_fine", "test_unset_and_read_only", "test_windows_needs_full_access",
        "test_bad_toml_is_unknown")],
    "discuss-auto-tier": ["tests/test_discuss.py::TestDiscuss::test_dry_run_runs_nothing",
                          "tests/test_discuss.py::TestEstimate::test_auto_tier_steps_down_the_agent_that_would_run_out"],
    "ledger-repair": ["tests/test_ccx.py::TestDelegation::test_repair_recounts_records_from_before_the_fix"],
    "hz-intword-carry": ["tests/test_number.py::test_intword_rounding_rollover"],
    "hz-naturaldelta-nonfinite": ["tests/test_time.py::test_naturaldelta_non_finite",
                                  "tests/test_time.py::test_naturaldelta_too_large_value_raises"],
    "hz-naturaldate-tz": ["tests/test_time.py::test_naturaldate_tz_aware"],
    "hz-natural-list-iterables": ["tests/test_lists.py::test_natural_list"],
    "its-timed-fallback-signers": ["tests/test_itsdangerous/test_timed.py::TestTimedSerializer::test_fallback_signers"],
}


def _d(test: str, checks: str, *brief: str, regression: str | None = None) -> dict:
    return {"test": test, "checks": checks, "brief": list(brief), **({"regression": regression} if regression else {})}


DERIVES_FROM = {
    "review-min-lines": [
        _d("tests/test_review.py::TestReason::test_when",
           "reason() on a diff of enough code lines names them; min_lines=0 turns that off",
           "`ccx.review.reason(mode, risk, result, claimed, actual, lines=0, min_lines=50)`",
           "the new trigger's reason is \"<n> changed code lines\"", "`0` turns this trigger off"),
        _d("tests/test_review.py::TestReason::test_when",
           "code_lines() counts added and removed lines of code files only, from `+++ ` headers",
           "`ccx.review.code_lines(diff: str) -> int`: added plus removed lines in the code files of a unified diff",
           "A file's lines start at its `+++ ` header (the diff may come without `diff --git` or `---` lines).",
           "Documentation files (`.md`, `.txt`, `.rst`, `.adoc`) do not count."),
    ],
    "undo-not-verdict": [
        _d("tests/test_verdicts.py::TestVerdicts::test_undo_is_not_a_verdict_unless_wrong",
           "plain undo: files back, verdict starts with none, routing state and verdict events unchanged",
           "`ccx undo <run_id> --apply` puts back the files a write run changed",
           "Undoing alone records no verdict: the routing state and the verdict events stay as they were, and the "
           "`verdict` field of the JSON output starts with `none`"),
        _d("tests/test_verdicts.py::TestVerdicts::test_undo_is_not_a_verdict_unless_wrong",
           "the ledger gets one undo event (reason undone, wrong false); the sweep leaves the run alone",
           "Every applied undo appends an event to the ledger: `{\"type\": \"undo\", \"run_id\": ..., \"reason\": "
           "\"undone\", \"wrong\": <true|false>, \"ts\": ...}`.",
           "An undone run is left alone by the probable-verdict pass (`ccx verify --sweep`): it waits for the person."),
        _d("tests/test_verdicts.py::TestVerdicts::test_undo_is_not_a_verdict_unless_wrong",
           "undo --wrong: its verdict text, routing changes, an ordinary (not soft) verdict with reason wrong",
           "New flag `ccx undo <run_id> --apply --wrong`: also records the run as wrong with reason `wrong`, exactly "
           "as the person's own `ccx verify <run_id> --ok 0 --reason wrong` records it (an ordinary verdict, not a "
           "soft, probable one)",
           "the JSON `verdict` is then \"recorded as wrong (undo --wrong)\""),
    ],
    "doctor-codex-sandbox": [
        _d("tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::test_full_access_is_fine", "full access: ok",
           "`ccx.doctor.codex_lead_sandbox(config_text: str, hub, windows: bool | None = None) -> tuple[str, str]`",
           "`sandbox_mode = \"danger-full-access\"`: `ok`."),
        _d("tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::test_workspace_write_needs_the_hub_and_network",
           "workspace-write without roots or network: WARN naming both parts and the hub path",
           "Otherwise `WARN`: the detail names each missing part (\"the hub is not a writable root\", "
           "\"network_access is off\") and gives the exact lines to add, with the hub path written with forward "
           "slashes."),
        _d("tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::test_configured_workspace_write_is_fine",
           "a writable root above the hub and network on: ok",
           "is `ok` only when `[sandbox_workspace_write]` lists the hub or a folder above it in `writable_roots` and "
           "has `network_access = true`"),
        _d("tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::test_unset_and_read_only",
           "no sandbox_mode: WARN saying not set; read-only: WARN",
           "or no `sandbox_mode` at all (Codex then decides; check it as workspace-write and say it is \"not set\")",
           "Elsewhere `read-only` is `WARN`."),
        _d("tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::test_windows_needs_full_access",
           "on Windows a configured workspace-write is still WARN, naming danger-full-access",
           "On Windows anything else: `WARN`, and the detail says to give lead sessions `danger-full-access`"),
        _d("tests/test_codex_lead_sandbox.py::TestCodexLeadSandbox::test_bad_toml_is_unknown", "bad TOML: Unknown",
           "Text that is not valid TOML: `Unknown`."),
    ],
    "discuss-auto-tier": [
        _d("tests/test_discuss.py::TestDiscuss::test_dry_run_runs_nothing",
           "the default (auto, no quota readings) talks at T2 and the dry run has tier_why for every agent; an "
           "explicit T1 is everyone's (the T1 models of the shipped config) and has no tier_why",
           "`--tier auto`, the new default: T2",
           "With `auto`, `why` has an entry for every agent",
           "A tier given explicitly applies to everyone as before.",
           "The `ccx discuss --dry-run` JSON has `tier_why` only when the tier is auto."),
        _d("tests/test_discuss.py::TestEstimate::test_auto_tier_steps_down_the_agent_that_would_run_out",
           "tiers() steps an agent above 100% down to T1, says its share as a percentage or no reading; estimate() "
           "takes the per-agent dict; a fixed tier has an empty why",
           "`ccx.discuss.tiers(p, names, tier=\"auto\", quota=None) -> (tiers, why)`",
           "T1 for a participant whose projected quota share at its reset is above 100%",
           "the projected share as a percentage (like \"85%\") when there is a reading, or a text containing \"no "
           "quota reading\" when there is none",
           "take either one tier for everyone or such a per-agent dict; the estimate's `models` and `tier` are per "
           "agent.",
           "With a fixed tier, `why` is empty."),
    ],
    "ledger-repair": [
        _d("tests/test_ccx.py::TestDelegation::test_repair_recounts_records_from_before_the_fix",
           "without --apply nothing changes and the fix is reported; with it the attempt's usage becomes the growth, "
           "the ledger row is rebuilt, and a second repair finds nothing",
           "Without `--apply` it is a dry run: it reports what it would fix and changes nothing.",
           "a Codex attempt without `codex_total` that continues a session seen before gets its `usage` replaced by "
           "the growth over that session's previous total",
           "The ledger rows of the fixed runs are rebuilt the same way `ledger.append` writes them",
           "Every Codex attempt it has looked at then carries `codex_total`, so a second repair finds nothing to fix.",
           "JSON output: `applied`, `runs_fixed`"),
    ],
    "hz-intword-carry": [
        _d("tests/test_number.py::test_intword_rounding_rollover",
           "a value just under each unit up to decillion is written as 1 of that unit, with the default and a %.0f "
           "format; the number before the unit stays below 1000",
           "a value that rounds up to a whole next unit is written as 1 of that next unit (with the default format, "
           "\"1.0 <next unit>\", never \"1000.0 <unit>\")",
           "the round-up carry works for every named unit up to decillion, whatever format is passed."),
        _d("tests/test_number.py::test_intword_rounding_rollover", "a decillion-gap number stays in decillions",
           "Numbers above a decillion and below a googol have no unit of their own; they stay written in decillions "
           "exactly as today."),
        _d("tests/test_number.py::test_intword_rounding_rollover", "a googol multiple is written in googols",
           regression="unchanged behaviour of the googol unit, not touched by the brief's change"),
    ],
    "hz-naturaldelta-nonfinite": [
        _d("tests/test_time.py::test_naturaldelta_non_finite", "NaN, inf and -inf come back as their str()",
           "every non-finite float (NaN, infinity, minus infinity) is returned unchanged, as `str(value)`."),
        _d("tests/test_time.py::test_naturaldelta_too_large_value_raises", "a too large finite value still raises",
           "A finite number of seconds that is too large for a `datetime.timedelta` still raises OverflowError"),
    ],
    "hz-naturaldate-tz": [
        _d("tests/test_time.py::test_naturaldate_tz_aware",
           "naturaldate() of an aware datetime is today / tomorrow by the date in that value's own zone",
           "when the value is a timezone-aware datetime, \"today\" is the current date in that value's own time "
           "zone, in both functions.",
           "otherwise hands the value, with its time zone, on to `naturalday()`."),
    ],
    "hz-natural-list-iterables": [
        _d("tests/test_lists.py::test_natural_list",
           "tuples, a dict's keys, a generator and a range give the same text as a list (the list cases are the "
           "existing ones)",
           "`natural_list(items)` accepts any iterable, read only once (so a generator works), and gives the same "
           "text as it does for a list of the same items",
           "one item gives that item as text, two give \"x and y\", more give \"x, y and z\"",
           "Every item is turned into text with `str()` as now."),
    ],
    "its-timed-fallback-signers": [
        _d("tests/test_itsdangerous/test_timed.py::TestTimedSerializer::test_fallback_signers",
           "a TimedSerializer whose fallback has the old digest loads data signed with it",
           "`TimedSerializer.loads()` tries the main signer and then the fallbacks, as `Serializer.loads()` does, and "
           "returns the payload"),
    ],
}


def derives_from(task_id: str) -> list[dict]:
    """The map of a hold-out task's hidden checks to its brief (DERIVES_FROM)."""
    return DERIVES_FROM.get(task_id, [])
