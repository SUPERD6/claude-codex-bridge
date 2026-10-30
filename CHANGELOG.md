# Changelog

## Unreleased
- `ccx q resume` continues the session of the run a `doing` piece was in the middle of (found by its `q:<id>` label,
  a review's fix round included) instead of starting the piece over, and tells the sub-agent it was stopped. A piece
  whose run had finished before `q run` was killed is marked done without running again (`restored: finished`).
  Before, the item only learned its run id when the run returned, which a killed `q run` never reached (r2 4-I).
- `ccx autonomy` (K4): how much the project manager does without asking. L0 only proposes (`ccx run --project`
  answers with a `plan`: agent, model, mode, `expected_usd`), L1 (the default) dispatches read-only runs and stops
  before a run that may edit files, L2 dispatches both and merges a small `--worktree` branch whose check passed and
  whose review said pass into the project's working branch, only where the person allowed it for that project
  (`ccx autonomy set L2 --project NAME --auto-merge on`) and never into `main` or another protected branch.
  `ccx run --approved` passes an L0/L1 stop after the person said yes; `--autonomy L?` sets one run's level; a
  project's own `.ccx/autonomy.toml` can only lower it. `[autonomy]` in `config/tiers.toml`, `autonomy.level` in
  `ccx config set`; the project-manager skill's section 6 follows the level.
- `ccx intake list|pull|ask|done`: tasks from outside. Issues you open with the label `ccx-task` in a PRIVATE
  repository of yours (`ccx config set intake.github owner/repo`) become tasks for the local lead; it asks for an
  approval and reports (result, PR/branch, cost, what was not verified) as comments on the same issue. Only issues
  and comments by the account `gh` is signed in as count (others are skipped and logged once), a public repository
  is refused, a pulled issue is never handed out twice (`<hub>/ccx/intake.json`), and nothing runs on a timer.
  `ccx.intake.pending(p)` gives the open count for other tools. Docs: `docs/intake.md`, with how to reach the lead
  from a phone by Remote Control (checked against Claude Code 2.1.309) and the feasibility of GitHub Projects and a
  self-hosted runner (not implemented).
- The board's private-GitHub helpers moved to `ccx/ghpriv.py`, shared by the board and the intake.
- `ccx ui` is the manager's board (K6): every project in the `ccx projects` catalog (its work queue even without a
  recent run here, its approval lines quoted, quiet projects in one line), and this month's sub-agent spend and saving
  from `ccx report`'s rule, labelled as a relative estimate. Buttons that change something (stop, verify, one more
  round / retry / continue, a raised cap, let it edit, `q done` / `q budget` / `q resume`) run their ccx command from
  the page: the page names the button, the server answers the exact command with a one-time nonce, and the second
  click runs it once (same origin, token, JSON only; a fixed command list as an argument list, no shell, no window;
  logged in `<hub>/ccx/ui-actions.jsonl`). Optional slots show K4's autonomy level and K5's inbox when those exist.
- Fix: the page's "continue the queue" command was `ccx q resume --cwd DIR`, which argparse rejects; it is now
  `ccx q --cwd DIR resume`. The page gets a phone layout below 720px.
- Shared memory (proposal L, L1–L3). `ccx mem search` ranks notes by BM25 (rare words count more, not every word
  is needed; `--all-words` keeps the old filter, `--limit N`, default 10). Five fixed kinds — preference,
  constraint, fact, pitfall, event, plus other: `ccx mem add --kind`, older notes guessed from topic and words when
  read (`ccx mem kinds --list`). `ccx mem compact --by project` writes one short block per project to
  `memory/scenes.md`. New `[memory]` settings, both off until the H11 trial ends on 2026-11-01: `by_kind` (a start
  carries new preferences and constraints only, briefs pick by BM25 without events) and `start_scene` (a start adds
  this project's block); `ccx config set memory.by_kind true`. On a fixed 40-note, 10-query set
  (`tests/memory_bench.py`), relevant notes in the first 3: search 7 → 11 of 13, briefs 11 → 12.
- Session hooks have a time limit (L4): `ccx mem delta`, `ccx turn` and `ccx lead --hint` run in a worker thread
  and, past `[hooks] timeout_s` (default 2 s, `ccx config set hooks.timeout_s N`, 0 = off), print nothing and exit 0
  instead of holding up the session start or the turn. Each one is logged in `<hub>/ccx/hook-timeouts.jsonl`
  (command, seconds, the step it was in); `ccx doctor` shows the count of the last 7 days.
- `ccx skills stats [--days N] [--json]` (L7): how often each shared skill was loaded in Claude Code (Skill tool,
  /name) and Codex (reading its SKILL.md) and when last, from the tools' session files; the ones never loaded and the
  estimated tokens their descriptions take each turn (from characters). Read only, deletes nothing.
- `ccx setup` has an optional step for a new hub (L6): on a terminal it offers once to read the last 7 days of
  Claude Code / Codex sessions with `ccx mem suggest`'s rules (no model) and asks about each preference or pitfall;
  only a yes writes a note (`ccx mem accept`'s path), the rest wait in `ccx mem suggestions`.
- Suggested notes leave out more one-off text (for L6, which reads several sessions at once): a sentence naming a
  PR / issue / commit / proposal id, one that opens with a work verb ("修…", "fix …"), a question or a choice still
  open ("要不要…", "等你决定"), the lead's "right now / 今天" status lines, and the person's half-sentences that open
  with a connective ("然后…", "就是…") or are under 10 characters. Agreement with blind labels: the earlier held-out
  set 13/30 -> 22/30 (good notes kept 5/7 both times; its misses were seen while writing the rules, so it is no
  longer held out), the set the rules were tuned on 21/30 -> 23/30, and 8 suggestions waiting on a real hub 3/8 -> 8/8.
- Warm lanes, off by default: `ccx batch --lanes N` and `ccx q run --lanes N` (`[lanes] default = 0`) cut pieces for
  the same project, agent and read/write mode into at most N lanes; a lane's first piece starts a sub-session and each
  later one continues it as a new task, while lanes run side by side. Each piece stays its own ccx run (own `--check`,
  ledger row, undo snapshot; one commit per piece in a worktree). A piece that does not finish cleanly, a piece that
  used more than `[lanes] max_tokens` (200k), or `max_blocks` (5) pieces hand the next piece a fresh session.
  Measured on round 2's ten small modules (`scripts/eval/warm_lanes.py`, n = 2, Codex luna low): ~40% cheaper than
  one fresh run per piece but not fewer tokens and slower; one run doing all ten is cheaper still
  (docs/research/2026-10-25-warm-lanes.md).
- Round 3 eval (`scripts/eval/r3.py`, `tasks_r3.py`; report `docs/research/2026-10-25-r3.md`): a sonnet lead doing it
  itself vs handing it to Claude Code's built-in Agent sub-agent (haiku) vs `ccx run --tradeoff save --review on
  --context auto`, on 10 multi-file tasks with one requirement to infer. All 60 units right (ceiling); cost per
  success $0.045 / $0.069 / $0.071; ccx vs built-in: same total spend, 25% fewer lead tokens, 26 s slower.
- L8 evidence: finding/reading files is a median 1.9% of a sub-agent's tokens (max 5.3%), so L8 is not built.
- L5 fixed memory test (`scripts/eval/l5_memory.py`): one side writes a note, the other side's new session uses it;
  memory on 15/24 vs off 2/24 (McNemar p = 0.0002); one note never picked by `memory.for_brief` (trailing punctuation,
  stop words).
- Fix: a sub-agent's brief picks shared notes by words without the dots and dashes at their ends (`JSON.` is `json`)
  and without common English and Chinese words (`the`, `with`, `我们`, `这个`). The L5 `mem-json` note, missed 4 of 4
  runs, is now picked; over the 6 L5 cases unrelated notes picked fell from 12 to 1 (`tests/test_brief_words.py`).
  Same number of notes as before.
- `ccx run` and `ccx resume` end their JSON with a `recap` key, one line with run_id, status, check, review, cost
  and `next: ccx show <id>`, so a lead piping the output through `tail` still has the run_id. Other keys unchanged.
- `scripts/collect_changes.py` no longer crashes printing its preview on a GBK (or other legacy) console; unprintable
  characters become `?` in the preview only, the file it writes is unchanged UTF-8.
- Claude sessions are found again when the project sits in a deep folder: Claude Code cuts a project folder name
  past 200 characters to 200 plus `-<hash>`, and the full path can pass Windows' 260-character limit. Shared work
  context, the lead's session lookup, killed-run spend and sub-agent spend all used the full name and silently found
  nothing (seen in round 3's pilot).
- `scripts/eval/r4.py`: round 4. Cheap models given the raw request with no lead (luna, luna + review, haiku,
  deepseek-flash; sonnet as reference) and self / built-in / ccx in a lead session that already holds ~110k tokens of
  history. Report: `docs/research/2026-10-26-r4.md`.
- `scripts/eval/r5.py` + `tasks_r5.py`: round 5 on ten real changes from this repository's history (the whole code
  base at the parent commit, the commit's own tests hidden); arms self / built-in / ccx / direct. Plan:
  `docs/research/2026-10-26-r5-plan.md`.
- `ccx resume` keeps the run's label, acceptance command and risk when it continues the same task: a lead's fix
  round was never checked, and a queue piece lost its `q:<id>` label (round 5 pilot).
- Claude sub-agents' result schema requires only `status` and `summary`: Claude Code made the model re-send a result
  missing an optional key, 51 extra turns over 10 of 181 runs in rounds 4-5. Codex keeps the strict schema.
- `ccx resume` refuses while a run of that session is still alive (the run itself, its fix round or a resume of it)
  and says to wait with `ccx show` or `ccx stop` it: a lead whose Bash call timed out resumed mid fix round and Codex
  refused the second writer (round 5).
- Shared work context keeps the person's newest ask up to 3000 characters (older asks 500, total cap unchanged): a
  1.6k-character spec was cut at 500 and the sub-agent never saw the interface its lead had misread (round 5).
- A sub-agent's rules no longer say "do not delegate to other agents" next to a request to use its own sub-agents
  (a Codex sub-agent stopped as blocked on that); the rule is about handing the task on to another CLI.
- Windows: Codex sub-agents get a short shell note (read files with `Get-Content -Encoding UTF8` or Python, no bash
  heredocs): plain Get-Content in PowerShell 5.1 showed UTF-8 Chinese as mojibake and a round-5 run gave up.
- Round 5 report (`docs/research/2026-10-26-r5.md`): ten real changes from this repository as large tasks. Self 19/20
  at $0.211 per success, built-in sub-agent 19/20 at $0.155, ccx 17/20 at $0.248, a cheap model alone 16/20 at $0.054;
  every ccx and direct failure traced to its cause.
- `ccx ui`: a refused POST (bad Origin, token or Host) reads the request body before answering, so Windows no longer
  resets the connection and the client gets the 403 instead of ConnectionAbortedError (a flaky CI test, now also 10 s
  faster).
- Independent review raises `[must]` only for real problems with the asked-for change (round 5: fix rounds were
  spent on robustness the task never asked for, and units with review issues were not more often right): the
  reviewer must quote the task sentence a `[must]` rests on, or name the existing behaviour, test or task-named
  input it breaks; hardening, extra validation, unasked edge cases, style and extra tests are `[note]`. A `[must]`
  that labels itself out of scope right after the tag ("(out of scope)", "Hardening:", "not asked for", ...) counts
  as a note and starts no fix round.
- Review fix rounds: at most one per run (`[review] fix_rounds` is 0 or 1; larger counts as 1, and the round
  counter now increases so a larger value can no longer loop); the fix round's own review is judged against the
  first run's task instead of the issue list it was handed, and the fix brief says not to add unasked hardening.
- `ccx show <run_id> --wait [SECONDS]` (default 540, under a 10-minute tool-call limit) blocks until the run is
  finished and prints the same compact result as `ccx run`, recap line included; when the run started a review fix
  round it waits for that and reports the last run of the chain. Still running at the end: `status: running` and
  `next: ccx show <id> --wait`, exit 0. `ccx run --bg` and the "still working" refusal of `ccx resume` point to it:
  a lead whose Bash call timed out lost the result and resumed mid fix round (round 5).
- The compact result of a write run in a git repo has a `diffstat` line (`git diff --shortstat` since the run's
  undo snapshot, plus new untracked files), so the lead needs no `git diff` / `git status` of its own after each
  run (round 5). No git or no snapshot: the key is left out.
- agent-delegate skill: a short "Delegate cheaply" section from round 5's lead transcripts. The brief is the
  person's request verbatim (interfaces, names, strings, numbers unchanged) plus known paths and the acceptance
  command, without reading the code base first; long work goes `ccx run --bg` then `ccx show <run_id> --wait`
  (no `tail`/`head` pipes, no resume of a running run); a passed check plus files_changed / diffstat is enough;
  `--review` stays auto; the sub-agent never commits. The brief template and the Chinese README say the same.
- Round-5 evaluation: an opt-in arm `ccx2` (`--arms ccx2`) whose lead follows that guidance, next to the unchanged
  `ccx` arm; the default schedule is unchanged, `summary` reports it, unknown arms are refused.
- Round-5 evaluation: an opt-in arm `builtin2` (`--arms builtin2`): builtin's Agent-tool hand-off with ccx2's brief
  and acceptance wording shared word for word (`LEAN_BRIEF` / `LEAN_ACCEPT`), so ccx2 vs builtin2 differ only in how
  the work is handed away; the worker runs the acceptance command and reports status, check, files_changed and
  diffstat. ccx2's prompt and the default schedule are unchanged.
- Sub-agent prompts: when the task names a command, hook or script, test through it as a separate process from a
  directory outside the repository (an in-process call does not test the wiring); never change what an existing
  test sets up or asserts to make a change pass (`WIRING`, `KEEP_TESTS`).
- Review: a new [must] for any failure of the task's behaviour on its normal path, silent ones included (undefined
  names, swallowed exceptions, imports or subprocesses that only work from the repo). Pre-existing test files the
  change edited (`edited_tests`) are flagged in the brief, always count as weak evidence in auto mode, and are
  shown in the run summary even when no review runs.
- Checks: a pytest exit 4/5 is `check_broken` (no escalation, no review, not learned as a failure); `ccx run --check`
  rejects `tests/...py` paths that don't exist, naming close matches; `ccx resume --check CMD` replaces the stored
  check; unquoted `*`/`?` are expanded on Windows. `review_failed` and `check_broken` runs print `ok: false` with
  `needs_lead`, and `ccx run`/`resume` exit 2 for them.
- Sub-agents are told to iterate with targeted test runs (one file, `-x`, `-k NAME`) and run the full acceptance
  check once at the end, instead of re-running the whole check after every edit.
- `ccx run/resume --check` naming a test file that does not exist: a near-identical name (a typo) is swapped in with a
  one-line notice on stderr; otherwise the error also lists the test files that do exist.
- The independent review now runs while ccx runs its own acceptance check, instead of after it. It is told the
  command and is only counted when the check passes; a failed or broken check stops the review and drops it.
  `--review off` is unchanged.
- `check_broken` is handled like the other failures: it ends a lane's session, gets its own card and history line in
  the dashboard, and the work queue treats it as needing the lead.
- Round 5 follow-up in docs/research/2026-10-26-r5.md §7: after #126–#129, ccx as the agent-delegate skill now teaches
  it was right 19/20 and 20/20 at $0.131 / $0.116 per success (builtin 17/20 at $0.202 beside it); the lean lead recipe
  alone cut cost and correctness (builtin2 17/20); wall time is still ~2.7× the lead working alone.
- Sub-agents with a `--check` are told to run only the tests touching their change and the full check at most once:
  ccx runs it again outside their sandbox and that result counts. The review fix round says the same.
- `--check` naming a missing `tests/X.py` now uses the existing `tests/X_*.py` files (an explicit list), with a
  one-line notice; the typo match stays as the fallback.
- `tests/test_recover.py` sweep tests skip with a reason when the `--bg` ccx process cannot be killed (a sandbox)
  instead of timing out.
- Evaluations start from a clean room: `scripts/eval/preflight.py` checks the machine before `r5.py run` (another eval,
  pytest, `ccx run`, `codex exec` or `claude -p` running, modified code, a dedicated Codex home, the work dir and the
  folders above it, a canary lead that must see only the project's instructions and must fail to read a denied
  folder) and refuses to start on any problem unless `--force-unclean`, which every row records; checking alone
  changes nothing on disk. Each unit gets an allow-listed environment, its own TMP / git identity / CCX_CONFIG /
  DSH_HOME / home for Codex and dsh, Claude without user settings, hooks, CLAUDE.md, skills or auto-memory (deny rules
  in the `//c/...` form for the real homes, every project's memory and transcripts, `~/.agents`), Codex in a dedicated
  CODEX_HOME; its processes start suspended in a Job Object and leftovers are killed and logged. Rows carry
  `fingerprint` (commit, task-file and tiers hashes, CLI versions, models, python / pytest / OS, isolation,
  concurrency, preflight result), `audit`, `leftovers` and `env_clean`; commit, versions and the machine are
  re-checked between units. `r5.py summary --tag` / `export --tag` keep rounds apart.
- New opt-in knobs for sub-agents, unchanged by default: `CCX_CLAUDE_SETTING_SOURCES` (`--setting-sources`),
  `CCX_CLAUDE_SETTINGS` (a JSON file merged into `--settings`), `CCX_CLAUDE_NO_SKILLS=1` (`--disable-slash-commands
  --strict-mcp-config` at every effort), `CCX_CODEX_ISOLATE=1` (`--ignore-user-config --ignore-rules`, Codex memories
  off, at every effort), `CCX_AGENT_HOME` (HOME / USERPROFILE of Codex and dsh sub-agents).
- Evaluation: a hold-out task set (`scripts/eval/tasks_holdout.py`), 10 real past changes of this repository that
  were never used while tuning on round 5 (other commits, other feature areas, same size band: 13-86 changed lines,
  1-4 files, one hidden test file each). `scripts/eval/r5.py run --taskset holdout` runs it (results in their own
  file, the task file's hash in every row); r5 stays the default. `scripts/eval/holdout_check.py` checks every task:
  the hidden test fails at the parent and passes at the commit, size in band, nothing shared with r5.
- Evaluation: a task may `deselect` unrelated tests that fail at random under load (test_bg_run in two hold-out
  tasks); hold-out units leave nothing in the work dir after scoring (repository and hub removed, the lead stream
  moved to `.ccx/eval/r5/streams/<tag>/`), so a later round cannot find an earlier round's answer; the checkout's
  other git worktrees are denied to unit agents and flagged by the audit like the checkout itself.
- Skills brought in line with current behaviour (#135): agent-delegate's result checks are one list in section 4
  (`needs_lead`, `edited_tests`, `check_broken`, the review fix round ccx runs itself; judge `kind` only after
  `ccx show <run_id> --wait`, and a `review_issues` left there means no fix round ran), the duplicated cheap-side and
  project-lookup text is shortened, and `ccx stop` and project memory are taught. project-manager keeps its default
  `--review on`, waits with `ccx show <run_id> --wait`, and names `ccx ui`, `say`/`board`/`peek`, `intake` (its
  comments go to the person first), `stats`/`report`. task-checkpoint resumes a ccx step with
  `ccx task resume <task>`. rubric.md and three-way.md no longer claim ccx is usually cheapest per right task
  (round 5 says otherwise). The Chinese notes follow. New test `tests/test_skills_core.py`: every core feature is
  still named in some SKILL.md and some README.zh.md, and every ccx command, subcommand, fixed value and flag in any
  skill doc exists (replaces the project-manager-only check).
- `namecheck`: after a write run, a static check (stdlib `ast` + `symtable`, a few ms a file) of the functions the
  run changed for names no scope defines, i.e. a NameError waiting on that path. Round 5 shipped two such bugs past
  passing tests (an import missing behind `except Exception`). Default `warn`: hits go to the record (`namecheck`),
  the compact result and the review brief as weak evidence, and keep the run from the 12 h probable verdict;
  `fail` turns a hit into `check_failed` (check `ccx namecheck --run <id>`, reason `namecheck`; the acceptance
  command is not run, and with a rung left it climbs like a failed check); `off`. Set by `[defaults] namecheck` or
  `ccx run|resume --namecheck`; `ccx resume` keeps the mode the run was started with. New command `ccx namecheck`
  (a run's changes with `--run`, the working tree since `--base`, or whole files; exit 1 on a hit). Per-function resolution, annotations never checked, a fixed builtins set (same
  verdict on 3.11-3.13), BOM-safe, files with star imports, `exec`, `globals()`, module-level `vars()`/`locals()`,
  `sys.modules[__name__]`, builtins writes, enum exports or `import cython` skipped; a name imported only under
  `TYPE_CHECKING` and read at run time is reported; a function counts when its lines changed or it uses a module
  name the run removed.
- `review.changes` names files from the repo root and unquoted (`--full-name`, `core.quotepath=off`): a new file
  in a subfolder run, or a non-ASCII path, was missed or read from the wrong place by the review and the namecheck.
- Review prompt: ccx's independent reviewer (caller `ccx-review`, read mode) no longer gets the builder's "run the
  relevant tests" Finish text; it is told to run no tests or builds (reading with file tools or shell read commands
  stays allowed, so a Codex reviewer can still read), to open further files in one batch and to set
  `verification='not-run'`, and its Finish text points at the brief's Checks. Builders are unchanged. Replay of 10
  recorded round-5 reviews (claude haiku low only): median 29.9 s -> 23.1 s and 5,618 -> 4,362 output tokens per
  review; known real bugs found 15/28 -> 19/28, which at this n means no loss detected, not a gain. A Codex reviewer
  with the new text is not measured.
- Review brief: an opt-in `## Code around the change` block after the diff (`[review] context = true`, default
  false), in what the diff leaves of `max_diff_chars`: the changed functions in full, definitions of names they call
  (same file, or imported from the tree) and tests naming them. Off because the replay found fewer known bugs with
  it (11/28), although reviews took about two-thirds of the time (15.3 s vs 23.1 s).
- `scripts/eval/review_replay.py`: re-runs recorded round-5 reviews with old and new prompts (`--variants
  old,new,finish`) through the real review path (claude haiku low, clean room), with a money cap, and counts the
  known real findings kept. It needs the round-5 work folder of the machine that recorded them.
- Eval: the hold-out set is now 5 tasks of this repository and 5 from two other open-source Python libraries
  (humanize, itsdangerous), sizes 8-86 lines; the 6 candidates left out are kept in `DROPPED` with the reason.
  `scripts/eval/ext_repo.py` reads each other repository once per run, before the canary, out of a clone in a
  temporary folder outside the work dir (`--ext-cache` for local copies) that is then removed, pins the full sha and
  gives every unit the parent's tree as a fresh one-commit repository (no future history). Their tests are scored
  with `PYTHONPATH=src` and `--ext-python`, after the parent's test folder and pytest configuration are put back.
  `holdout_check.py` checks them the same way.
- Eval leak guard for external units: the `--ext-cache` copies are denied and flagged, Claude's WebFetch/WebSearch
  are denied, pip gets no index, and the audit flags `pip install/download`, fetching from GitHub/PyPI, the
  repository's URL and `ext-cache`. The run does not start when `--ext-python` is older than 3.11, lacks the test
  modules or a new enough pytest, has the library itself installed, or sits next to the copies; a change to what is
  installed in it during a unit stops the run. Rows record that Python's versions and the commit date, and the
  summary reports results per repository.
- Eval: `scripts/eval/fixround_replay.py` replays recorded review-driven fix rounds offline, with no model calls. It
  rebuilds the tree before each fix round from the run's start commit plus the diff in its review prompt, and the tree
  after it from the fix round's own review prompt (or the unit's final tree). It runs the task's hidden test on both
  and counts fail->pass / pass->fail / unchanged per review reason, per kind of [must] item and per who started the
  round. A new file cut at 4000 characters is completed from the final tree only when the recorded text is a prefix
  of it; otherwise the round is skipped and counted. `--check-final` re-scores each unit's final tree against
  results.jsonl as a second check.
- Eval: `r5.py summary` / `export` add `by_tag`: per tag and arm, n / right / $ per success and wall median, mean and
  p75, with each round kept apart; the per-arm totals also get `wall_mean` and `wall_p75`.
- `ccx show ID... --any [--wait N]`: every finished run among several ids (`finished`) and the ones still running
  (`running`, as asked, and `next`); one id without `--any` is unchanged.
- `ccx q run` refills a slot as soon as a run finishes instead of waiting for the wave; a run whose attempts hit
  quota/auth stops new submissions (`stopped: backpressure`, or a `backpressure` note when nothing is left open);
  new `ccx q run --bg`. An item routing skipped is tried once per `q run` (also with `--lanes`) instead of looping.
  Refill keeps the batch rules: `--gate`, dep_blocked before each fill, no two runs sharing a file, and a writer
  started beside a running writer gets its own worktree (shared folder when uncommitted); with `--lanes`, a quota
  hit also stops the lanes' next items.
- One runner per queue: a second `q run` / `q resume` while one is alive exits 2 (`stopped: already running`).
  `q ls` shows each running item's run id (`live`), the live `runner` and `last_run`.
- Skills: agent-delegate teaches pipelining several pieces (`q add`, `q run --bg`, `show <live ids> --any --wait`)
  and that on `review_failed` the lead checks the `[must]` items and fixes them itself; task-split says `files`
  decides what runs in parallel.
- `ccx q` for batches of pieces: parallel writers in a git project with no uncommitted change get one worktree each
  (the `ccx batch` rule, one commit per piece on `ccx/<run>`; otherwise they share the folder as before, noted under
  `shared_folder`), and what depends on such a piece waits for your merge + `ccx q done <id> --ok 1` (listed under
  `waiting`; branches nothing waits on under `unmerged`); `q add --plan` reads task-split's `pieces` / `depends_on` /
  `files`, resolves dependencies after every id exists and errors on an unknown id or a cycle (they were dropped
  silently); a failed, blocked or needs_write dependency marks its dependents `dep_blocked` (naming the piece to fix)
  instead of leaving them todo forever (back to todo once settled; `q ls` / `tree` only show it); a task-split piece
  without a brief gets one built from the plan and runs in the mode its own title implies (the split hint made it
  read-only); items naming a common file never run side by side; new `q run --gate` / `q ls --gate` (off by
  default) makes every dependent wait for your verdict; `ccx ui` shows `dep_blocked` pieces as needing a decision.
- `ccx run --bg` refused by routing writes a finished record (kind `not_delegated`), so `ccx show <id> --wait`
  returns at once instead of waiting out its timeout.
- Round-5 evaluation, for the confirmation run (all opt-in; the default schedule, arms and done-keys of old tags are
  unchanged): `--lead-model` / `--lead-effort` (default sonnet medium) recorded in every row, its fingerprint and its
  done-key, with another lead's units summarised as their own arm (`ccx2@opus-high`); an opt-in arm `builtin2r`
  (builtin2 whose worker prompt also carries ccx's KEEP_TESTS and WIRING rules, imported from `ccx/prompts.py`), so
  ccx2 vs builtin2r isolates ccx from those rules; the summary pairs every two arms on shared units (McNemar exact p
  with Holm over the pairs, task-level bootstrap 95% CIs of the cost-per-success and wall-median differences), adds a
  Wilson CI and the right count per round per arm, the wall per phase of units that used ccx (sub-agent attempts,
  checks, reviews, fix rounds, the lead waiting; median and p75) and, with arms `balanced` and `save`, the tier
  decision rule (pass / fail per condition). `--budget` now counts only the tag's own spend (plus `--extra-spent`);
  each unit line and the end of a run print the run, tag and file totals.
- Round-5 evaluation statistics, after review: the `direct` arm (no Claude lead) ignores `--lead-model` /
  `--lead-effort`, so its units keep their key, folder, label and summary arm and are not re-run; the paired summary
  adds an exact sign test over tasks (`task_sign_p`, Holm-adjusted too) and flags McNemar when a task has several
  rounds; each arm adds a task-bootstrap CI of its right rate (`ok_rate_ci_tasks`) and flags the row-level Wilson CI
  then; the cost-per-success CI says how many resamples were left out (`cps_diff_ci_dropped`, `cps_diff_note`);
  the tier rule reports `n/a` (not `fail`) when it cannot tell, and uses the same median as `wall_med`; the phase
  wall counts a review that ran while the check ran once (`overlap_s`, also a review stopped when an earlier
  rung's check failed) and the checks of rungs that failed and climbed
  (ccx now keeps that check's time on the attempt, `check_seconds`); `by_repo` keeps another lead apart; rounds sort
  numerically; builtin2r's worker is told to run the acceptance command instead of the whole suite, so it no longer
  contradicts the WIRING rule.
- `ccx q` queue lock: on Windows it now waits when creating its lock file is denied (a file the last holder just
  unlinked is "delete pending" there, which raised PermissionError instead of FileExistsError and failed the write;
  the likely cause of a parallel `q run` row with no run on Windows CI, not reproduced locally, and that test now
  prints the row). A lasting denial (a folder no file can be created in, or any denial off Windows) fails at once,
  and the wait has a hard deadline (2 x timeout) even when a held lock cannot be taken over, so it never spins
  forever. Only a stale lock is taken over (no longer any lock once the waiter has waited that long): one whose
  mtime is older than the timeout, or one the waiter has watched sit unchanged for longer than the timeout, so a
  lock with a future mtime (clock skew on a shared folder, a restored file) no longer blocks every write. A
  release removes only its own lock (also when its mark could not be written), retrying a denied unlink instead
  of failing the write.
- `ccx q run`: an item that errors reports `status: failed` with the error (and `not_recorded` if writing that back
  failed too) instead of raising, and clears its `live` run id; one that errors after its run keeps that run and
  its cost in the row and the queue, and one whose run itself raised keeps the run id it was started as (and its
  cost, if that run wrote its record); a skipped item reports `status: todo`.
- `ccx trial report` no longer crashes with FileNotFoundError / WinError 3 on a Claude or Codex session folder it
  cannot list (removed while walking, or past the Windows path limit): the session readers walk with `usage.walk`,
  which lists long paths with the `\\?\` prefix (a file past the limit in a shorter folder too) and skips what it
  still cannot list, stat or read; folders come out in the same order as `rglob` gave them. Finding one Claude
  conversation's files follows a symlinked project folder again, and one bad folder entry no longer hides the
  others. A delegated task whose lead conversation's files are gone or unreadable, or whose Codex lead has no
  session file at all, is shown under `unmeasured` with the reason and left out of the comparison instead of
  counting as zero; a lead whose files were read but had no turns in the run's window still counts as zero.
- `ccx trial stop --void REASON` records the trial as void (the running one, or the last one if it has ended);
  `ccx trial report`, `--markdown` and the dashboard show it as void with its reason and claim no saving or result.
  An empty reason is an error. `ccx trial stop` without `--void` is unchanged. `ccx trial start` keeps the trial it
  replaces (void reason included) in `state/trials.jsonl`.
- The H11 trial `trial-20261025` is void (docs/DECISIONS.md): defaults that waited for it (`[memory] by_kind`,
  `[lanes] default`) stay off and are decided by the confirmation run's fast vs save tiers; no default changed.
- Whole-workflow tiers on `--tradeoff`: `save | balanced | fast | cheapest` (new value `cheapest`). task-routing
  `tier_plan` (CLI `task_routing.py tier`) sizes a task from the brief plus `--minutes` / `--files` (any one signal
  is enough; state-machine words match whole words, with plain endings) and says who does it: `self`, `ccx2` (delegated, the lead
  accepts; models picked like save) or `direct` (cheapest: nobody re-checks, `may_be_wrong`). Provisional thresholds
  and per-tier rules in `config/tiers.toml [policy.*]`; a knob 0..1 maps onto save/balanced/fast. `ccx propose` /
  `ccx route` show it under `tier` / `policy`.
- New setting `policy.picked` (`ccx config set policy.picked save|balanced|fast|cheapest|none`, shipped none): the
  tier the person picks. Only it pre-authorises: `ccx propose` for that tier returns `authorized: true` with
  `worth_offering: true` and a `say` line (proposal row `preauthorized`); that proposal's run skips the random A/B
  self-run, keeps the proposal's tier in the ledger, and is refused if the setting changed. A pre-authorisation
  covers one run of that task: a second run with the same id (claimed atomically when the run starts), a run
  sized smaller than the proposal, or a run whose own brief the tier would plan `self` (its hard / uncertain rules)
  is refused; with `--bg` the refusal comes before detaching (a refused detached child leaves a finished `refused`
  record, so `ccx show --wait` ends);
  its answer (`source: tier`) is written only when the run starts (an L0/L1 stop or a routing refusal records
  nothing). Project autonomy L0/L1 still asks before edits; a proposal the picked tier planned `self` is not an
  approval for it either (sent out anyway, its answer is `source: lead`). `policy.picked` sets the tier plan, not the
  models: a plain run still picks models by `--tradeoff` / `defaults.tradeoff`; `proposals.stats` leaves tier-decided proposals out of the H12 chain (`tier_decided`). A
  `--tradeoff` the lead passes authorises nothing (offer-first, A/B and the H11 trial as before). Default tier stays
  `save`. The agent-delegate and task-routing skills say what to do with `authorized: true`.
- A bad `[policy.*]` entry: `ccx propose` falls back to offer-first and shows `tier.error`; `ccx doctor` has a
  `tier policy` row (it reads `policy.picked` as routing does, case-insensitive).
- Ledger: run and proposal rows carry `policy_tier`, `band`, `planned_mode`, `tier_explicit`, `estimate_minutes`;
  a pre-authorised proposal's run has its own band and estimate plus `proposal_band`; run rows also `actual_mode`
  and `resume_chain` (follow-ups of the same task: `ccx resume`, review fix rounds, an
  interrupted run resumed; a board message answered in the session is not one); a proposal answer records
  `actual_mode` and, for a pre-authorised run, `source: tier`.
- `ccx turn` reads the hook's stdin as UTF-8 bytes, BOM dropped (a Chinese prompt on a GBK console was garbled).
- `--tradeoff` help no longer says "initially balanced"; `ccx config set defaults.tradeoff cheapest` is accepted.
- Evaluation: opt-in tier arms for the round-5 script (`scripts/eval/r5.py --arms fast,balanced,save,cheapest`), so
  the confirmation run measures every whole-workflow tier. Each unit's hub has the person's `policy.picked = <tier>`
  (set with `ccx config set`, the choice the arm simulates) and the lead is told the person picked it: fast does it
  itself; balanced and save size the task with `ccx propose --minutes --files` on the person's request verbatim (the
  text its run sends, so the run's own re-plan agrees) and follow its answer (authorized: run its `next` the ccx2
  way; otherwise, or when `ccx run` refuses the proposal, do it itself); cheapest is the shipped cheapest tier as a
  script runs it, propose's `next` without a lead (`ccx run --to codex --tradeoff save --review off`: no explicit
  model, so save's model pick; no fixed `--minutes`, since nobody sizes it, so ccx makes no tier plan for the run and
  its model comes from the brief's keywords as ccx2's does; no review; its `--check` is the repository's whole existing
  suite, the same command for every task of a repository, so it names no hidden test file, and its result is taken as it
  is, while save's climb on a failed ccx re-check can fire), in a hub that picked cheapest, labelled may_be_wrong.
  The explicit `--tradeoff save` wins over the hub's pick and the run is unsized, so ccx plans nothing for it: the row's
  plan says `source: eval-script`, `ccx_planned: false`, and the summary counts plan sources (`plan_sources`); it is not the direct arm under a new name (direct keeps gpt-6-luna low, `--minutes 60` and its
  review). Where save differs from ccx2: save's lead makes one more call (`ccx propose`) and its run carries the
  lead's `--minutes` / `--files`, so its model is picked from that difficulty, while ccx2's run picks from the brief's
  keywords; a save-vs-ccx2 difference is the tier path plus that model pick, not the tier path alone. ccx2 stays the all-delegated baseline; the default
  arms, schedule and done-keys are unchanged. Rows record the tier, what `ccx propose` planned (band, mode,
  authorized, from the unit hub's ledger), the reference change's size (non-test code lines and files, and the band
  those files give), the mode that actually ran, the misbanding (`misband`: the lead's `--files` band vs the
  reference files' band; `misband_overall`: the planned band vs it, which leans over by construction) and whether
  ccx's `--check` passed; every row that used ccx also keeps each run's route (`ccx_routes`: source, difficulty, rung),
  since save's run carries `--minutes` / `--files` and so picks its model from that difficulty while ccx2's falls back
  to keywords; a failed read of this metadata is kept as `bookkeeping_error` and the unit is still scored. A full
  `--lead-model` id is passed to `ccx propose --lead` as its family alias. `summary` adds a `tiers` block per arm
  (right, $/success, wall median/mean/p75, misbanding with its basis, route sources, planned vs actual modes, check
  passed on failures) and `tier_rules` per lead (each with its `pair`), so the balanced-vs-save rule also fires under
  `--lead-model opus`. `run --dry-run` now prints each unit's estimated cost and a per-arm and total estimate against
  the budget (measured r5 means per unit, an Opus lead's share x1.7, tier arms by the mode the shipped tier plans for
  each task; cheapest from the direct arm's mean, which paid a review cheapest does not).
- `ccx run ... --bg --wait N` and `ccx resume ... --bg [--wait N]`: one call instead of `--bg` plus
  `ccx show ID --wait`. The run id goes to stderr at once (flushed), then the same process waits up to N s:
  finished -> the final compact result with recap (exit 0 / 2 as a foreground run); not finished -> exactly what
  plain `--bg` prints. The detached child gets no `--wait`; the wait starts after the routing / autonomy /
  pre-authorisation checks, a refused child (not_delegated, refused) ends it at once, and so does a child that exits
  before its run record exists (state failed, with the end of its log). `ccx resume` accepts `--bg` (it was an
  unknown argument, exit 2) and, like a foreground resume, refuses before detaching when another run is still working in that session (before, plain `resume --bg` printed `started` and `ccx show ID --wait` waited out its timeout); a detached resume that finds the session busy anyway writes a finished `refused` record. A finished waited result also carries the keys a foreground run adds after the run (`route`, `continued_from`, `project`, `autonomy` with the L2 merge outcome), read from the child's own result. The child's argv loses argparse's prefixes of `--wait` (`--wai 540`) too. `--wait` without `--bg` is an error; plain `--bg` and foreground runs are unchanged.
  The `--parallel` help no longer says it switches on by itself for a brief that lists 3+ items.
- Windows: `run_check` turns a single-quoted token with no double quote inside into a double-quoted one, in the
  same word pass as the glob expansion; words are split with the quote state tracked (MSVC rules: `\"` does not end a double-quoted argument), so a `'...'` inside a double-quoted argument (`"print('a b')"`, `--opt="a 'b c' d"`) is left alone (`-k 'a or b'` reached pytest as three words under cmd.exe, exit 4); the
  rewritten command is in `check.ran`, `&&`, `|` and redirects are kept as they are. The check text shown to the
  sub-agent (ccx/prompts.py) is not rewritten yet.
- Run ids handed out up front (`--bg`, `ccx q run`'s `live` id) now come from `ledger.new_run_id`, which creates
  the run folder exclusively, so two runs started in the same second can no longer draw the same id (second + 4
  random hex digits) and share a folder: the second then found the first's `final.lock` (CI flake in
  `test_archive_shared_session_once`). `ccx/delegate.py` draws a foreground run's id the same way. The parallel worktree test
  (`test_unmerged_branches_nothing_waits_on_are_listed`) only prints each piece's result when it fails: its CI
  flake was not reproduced (12/12 local passes, 120 concurrent `git worktree add` + commit clean), so its cause is
  not known; a run-id collision is the one mechanism found that gives exactly 1 of 2, and it is closed now.
- New batch / pipeline throughput eval (`scripts/eval/batch.py`, opt-in, its own results file; r5 and its arms,
  schedule, done-keys and rows are unchanged), planned in `docs/research/2026-10-27-batch-plan.md`: one lead session
  gets several hold-out changes at once, put on one common start (`scripts/eval/batch_start.py`: the first commit
  that has all of them, every batch commit reverted on it with git's three-way revert; a code or test conflict drops
  that change and says so). `batch.py check` builds and checks each batch (holdout_check's band and leakage checks,
  hidden nodes that fail at the start and pass at the end, none of them in the start's test files word for word, the
  start imports, the declared same-file overlap and end). Batches (`scripts/eval/tasks_batch.py`): five changes of
  this repository with one deliberate same-file overlap, its largest conflict-free variant (four: no five-change set
  is both revertible on one start and conflict-free), humanize's four (one overlap) and three (none; neither humanize batch checked
  yet); itsdangerous has no batch (its two candidates' revert conflicted on an earlier try, not re-run). Arms `self`, `builtin` (parallel workers allowed), `ccx-batch`,
  `ccx-pipeline` (`q add --plan`, `q run --bg`, `show <ids> --any --wait`, merge `waiting` / `unmerged`, `q done`)
  and `balanced`; `--lead-model` / `--lead-effort` as r5 (default opus medium). Per unit: wall, lead and sub-agent
  $, hidden tests on the final merged tree (per change and all-right, with regressions), merge conflicts and markers
  left, the lead's turns, requests, tokens, wake-ups and idle ratio (from line arrival times), quota events (every
  ccx attempt, not only the last); round 5's clean room, fingerprint and audit. `run --dry-run` prints the plan and a
  cost estimate (a projection, about $27 for four batches x five arms x two repeats); the summary gives median / p90
  wall per batch and arm and plain paired per-batch numbers with n (no bootstrap). No paid run yet.
- Batch eval fixes after review: hidden test files run with `--continue-on-collection-errors`, so a file that does
  not import (at the start, or a change the lead left out) fails only its own nodes instead of the whole session
  (the first check's empty `start_passed` and false `coupled` came from this; collection errors of every run are
  recorded); the start's commits get a fixed date and a cached check is keyed on the start tree and on the check
  code (`batch_start.py`, `batch.py`), so `run` can reuse it; `without_one`'s cherry-pick fallback settles
  documentation-only conflicts as `revert_all` does; a merge conflict counts once per `CONFLICT` line; review runs
  (label `review:`) are left out of `delegated`; builtin's sub-agent $ is not split when the lead runs on the
  worker's model, and every row keeps the worker model's share as `lead_worker_model_usd`.
- F14 default change: the "explicitly asked to use sub-agents" words are added only with `--parallel`, no longer
  when a brief lists 3 or more items (round 5: 40/100 first runs got them, +$0.007-0.024 a run, no wall gain).
- The sub-task prompt says that delegation / acceptance instructions written for the lead in the shared context
  were already carried out: the sub-agent is the implementer (only for a write run with the shared-context block;
  not ccx's read-only reviewer or read tasks). The shared context for a delegated task also drops a clause only
  when the whole clause is the hand-off ("Do not edit files yourself", "hand the implementation to a sub-agent
  through ccx", ...); specs about delegation itself stay. The block says how many were left out and the run
  record lists them (`shared_context.lead_only_dropped`).
- A resume or review fix round of a write run inherits its chain's undo snapshot: reviewing after resuming a fix
  run sees the whole change, and `ccx undo` of any run in the chain puts back what the chain changed (the output
  says so). Only while nothing changed between the links: after a commit or an edit by the lead, or for a board
  message answered in the session, the run takes its own snapshot, so undo keeps the lead's work.
- `ccx run --parallel` help text no longer says the words are added by themselves for 3+ listed items.
- `edited_tests` (changed pre-existing tests) is shown for every write run, also with `--review off`.
- `[review] cache_ttl` (default off): "5m" or "1h" sets Claude Code's `promptCacheTtl` for ccx's Claude reviewer
  only.
- `ccx fresh` / `ccx handoff` never overwrite a hand-written or edited `.ccx/handoff.md`: it is updated only while it
  is ccx's own unedited copy (its `<!-- ccx:handoff ... -->` header and the same text as a file in
  `.ccx/handoffs/`); otherwise the new handoff lives only in `.ccx/handoffs/` and the result carries
  `latest_skipped` (with `latest` pointing at that file). The session-start hook reads `.ccx/handoffs/` first, so it
  still shows the new one once. A `.ccx/handoff.md` ccx wrote before `.ccx/handoffs/` existed (ccx header, no
  history yet) is copied there once, byte for byte, and then updated as ccx's copy, unless it was modified more
  than a few seconds after its header's time: then the copy is named `...-edited.md`, never counts as ccx's copy,
  and the edited `.ccx/handoff.md` is kept like a hand-written one. Whoever was shown it stays marked as having seen
  it. The comment in `cmd_fresh` that said fresh never wrote `.ccx/handoff.md` is fixed.
  `scripts/eval/preflight_e2e.py` checks the handoff file the command prints, not `.ccx/handoff.md`.
- agent-delegate (SKILL.md + README.zh.md) teaches one call for long work, `ccx run ... --bg --wait 540` with a
  600000 ms shell timeout (Codex / DeepSeek leads set `--wait` about a minute under their own tool timeout), keeps
  `ccx show <run_id> --wait` for a run still going, judges `kind` from either final result, and adds: the lead's own
  sub-agents and ccx never write the same files at once; a ccx writer beside native writers uses `--worktree` or
  `ccx q run`. `scripts/eval/batch.py` counts `run/resume --bg --wait` as a blocking wait, reading the flags with
  quoted text blanked (a brief that mentions `--wait` or `--bg` does not count).
- Docs no longer teach a 70% quota gate for DeepSeek (task-routing SKILL.md, the `ccx run --quota` help,
  `config/tiers.toml`): routing prices quota by its shadow price (E4); the unread `[cash] from_quota` is removed
  from priors.toml. three-way.md no longer calls ccx the cheapest way while saying the built-in sub-agent cost
  less; rubric.md points to `--tier` / `ccx stats` / `ccx verify`, and says a lasting change to an agent's default
  tier is the person's own edit of their hub tiers.toml (`ccx config set` has no per-agent tier key).
- `tests/test_skills_core.py` guards pipelining (`ccx q ...`, `--any`), whole-workflow tiers (`--tradeoff`) and the
  result-reading rules in every skill trim: `namecheck` / `weak`, and the rules themselves by their own wording in
  agent-delegate SKILL.md and README.zh.md (don't re-send a run's brief, never resume a running run, judge `kind`
  only from a final result, `review_issues` after `--wait`, no resume for `review_failed`, re-run tests when the
  check is `weak`, own sub-agents and ccx never write the same files at the same time), plus the one-call wait
  and the removed stale rules. `.gitignore` ignores `.claude/` (local state).
- Eval gates (PR-E): r5 summaries and the tier rule count `env_clean` rows only and report the left-out rows per arm
  and tag, plus pairs lost per side (`lost_pairs`; a pass with a one-sided loss is Unknown); the tier rule's right
  condition is a paired task-bootstrap CI (>= -1 task pass, wholly below fail, else Unknown); a tag runs on one
  pinned commit; every arm splits lead / ccx and lead-only / delegated spend; `--dry-run` prices non-Sonnet leads at
  list prices; opt-in `ccx2-skill` arm with `--claude-isolation ccx-home` (its own `@ccx-home` arm, bundled Claude
  Code skills allowed by name and recorded, a skill canary not yet run against a real claude); per-unit timeline
  (`scripts/eval/r5_timeline.py`).
- Offline experiments: C3 counts a builder run as ccx's check only when the check is one whole statement (no more substring matches such as a single `::test` id). Compound commands are judged by their pytest summary line. Corrected figures: 110 matches, 4 + 7 mismatches (the 7 are 5 sandbox and 2 PowerShell glob).
- Offline experiments: the C4 filter gate counts every planned rescue. A rescue that is unjudged, failed, skipped or cut by the budget is not kept.
- Offline experiments: C2 `generate` runs each test writer in the round-5 clean room and drops files whose brief carried shared notes.
- Offline experiments: C1 reports reviewed trees it could not rebuild (`reviewed_skipped`). C5 and C2 stop when the results file is missing or has no rows. A replay insert rule whose anchor is missing fails the job.
- New `scripts/eval/b1_skip_count.py`: `unsure` is the only review trigger in 1 of 107 first reviews (0.9%) and `tests_miss_change` in 20. The report marks B2's replay as not done.
- Added `[review] fix_rereview` (default `"full"`, unchanged). `"focus"` gives a fix round's review the first review's problems and the fix-only diff. It stays off because its paired replay of 40 round-5 fix-round reviews saved a median of only 2.4 s against a 10 s bar ($0.70 spent). See docs/DECISIONS.md.
- Added `scripts/eval/rereview_replay.py`, an offline paired replay of fix-round reviews (full vs focus). Its summary counts unclear verdicts in an `other` bucket. Its [must] matching requires a shared identifier when the recorded item names no file.
- Dropped B1 (re-review only when the sub-agent says it is unsure): 2/120 (1.7%) of reviews are triggered that way only, below the 5% bar.
- `ccx batch` with uncommitted changes: parallel writers no longer get worktrees made from the last commit (which
  lacked those changes); like `ccx q run`, they share the project folder and the output lists them under
  `shared_folder` with "commit first" and "keep pieces on separate files" (their checks, reviews and undo can see
  each other's edits). Clean repos are unchanged; the plan file itself does not count, also with a non-ASCII name
  (git status is read with `-z`, so quoted names and renames are parsed right); `--lanes` too. A task that sets
  `"worktree": true` in a dirty project keeps its worktree and is listed under `stale_base`. The git check moved to
  `ccx/gitstate.py`, shared by both.
- Codex builder notes: every Codex sub-run (fresh exec and exec resume, any system) is told to print the whole
  exec_command result or at least exit_code and session_id, and to continue a still-running command with
  `write_stdin` instead of starting it again; the Windows note no longer recommends `python -c` (`;` not `&&`, `*` is
  not expanded for python/pytest, Python with quotes/non-ASCII/several statements in a temp .py file, rg patterns in
  single quotes). Checked on codex-cli 0.164.0.
- `ccx run/ask/resume/way`: words after an option join the brief (`ccx resume R --check X "fix"` exited 2); a
  mistyped option still exits 2. A bare word right after a one-value text option's value (`--check make test`,
  `--check pytest tests/x.py`, `--label a b`) exits 2 with "quote a value of several words" instead of quietly
  shortening the check. The agent-delegate skill example puts the brief first.
- Hub config hygiene: a `~/.ccx/config.toml` or `layout.toml` that does not parse prints the file, line/column and a
  Windows-path hint on stderr (the hub fallback was silent); `ccx doctor` has a `ccx config` row (FAIL: does not
  parse, WARN: a control character in a value) and, with a broken `layout.toml`, still prints its whole table with a
  `hub layout` FAIL row (it stopped with a bare JSON error); `ccx init --hub` writes a single-quoted literal string; `ccx setup`
  counts [n/7].
- Claude sub-runs: `errors[]` of a failed result goes into the run's error (e.g. "No conversation found"), and
  `ccx resume` then says to send the task again with `ccx run --new` when that is the final failure (added after
  any other hint, not in its place).
- Eval: harness audit fixes. life.no_leftovers reads the process-audit keys preflight writes (procs, ports, unkilled, worktrees). Unit keys and arms come from r5.unit_key / r5.arm_of, so suffixed units such as ccx2@ccx-home are matched. Setting CODEX_HOME to a test's own home is no longer counted as a private-memory read. Chains are listed only for wrong units; right units keep the same pairs as co_occurring. [must] scope uses the tree the review saw when undo.json records it, with diff_basis on every item. is_test_file no longer counts latest.py-style names as tests. --skip rejects unknown criteria.
- Docs: harness audit report (EN + ZH) corrected after re-running on r5e-r5h: 28 private-memory runs, direct 0/20 on that criterion, direct macro 0.76. The adjusted table separates the eval-environment criterion from the ccx defect fixed in #149. The final-tree [must] bias and the in-diff rules are documented.
- Review fix round: the fixer now gets each [must] item whole (`issues_full`, up to 1500 characters, at most 8; the summary uncut when there are no items), instead of the 300-character form the lead still reads in `review.issues` / `needs_lead`. A review whose `REVIEW: issues` / `REVIEW: pass` line landed in its first item instead of the summary is read by that line (only when the summary names no verdict).
- A write run that says done/partial but changed nothing since its undo snapshot (same HEAD, so a commit of its own counts as a change; no edit; no new file) is `kind: no_changes`: `ok` false with `needs_lead`, not learned from, never auto-judged right; its check is shown as `ran on unchanged tree` (`passed: null`). A label only: no retry. Read runs and ccx's reviewer are untouched. A pre-existing untracked file that is gone counts as a change, and files with non-ASCII names are checked too. It is measured before ccx's check runs on that attempt (also when the check runs inside the escalation loop), so files the check writes are not the builder's. Files that are .gitignore'd or outside the repo are not seen (the hint says so). `ccx q` marks such a piece `failed` (its dependents wait, `restored` = decide), a lane starts the next piece fresh, and `ccx ui` asks the person ("have it make the change" / "already met: accept") instead of showing an ordinary review card.
- `plan_build`'s fix round also gets the planner's [must] items whole (`issues_full`).
- `ccx run --worktree` in a project with uncommitted changes records `base: HEAD, uncommitted changes not included: commit first` (run.json `base_note`, the result's `base`); the run itself is unchanged.
- A Claude reviewer is told to read with Read/Grep/Glob and use Bash only for git diff/log/status, without `cd` (its allow-list refused the `cat` / `rg` the old text offered); Codex's text is unchanged. Claude's `permission_denials` are counted per attempt in run.json and summed in the ledger.
- Lead model by task (opt-in, `ccx config set lead.model_by_task on`; default off, nothing changes when off): where ccx starts or recommends a new lead conversation, its model follows the task's difficulty (the same b as `ccx route`). Up to `easy_max_b` (4.0, about 16 minutes) it uses `[lead_by_task] easy.claude` (sonnet); above that it uses the lead's own model (`[lead] claude`, opus). `--risk critical` always gets the strong lead. `ccx fresh` takes `--minutes` / `--b` (or `--difficulty`) / `--risk`. `ccx handoff` takes `--minutes` / `--difficulty` / `--risk`; it has no `--b`, so `--b` still abbreviates `--by`. Only the easy band adds `--model` (fresh's command line and `--launch`; handoff's `start` line). The hard band passes no `--model`, so the tool keeps the model it normally runs on. handoff's `--minutes` are adjusted by the handing-off lead's estimating bias, as in its own `ccx route`. `ccx route` / `ccx propose` add `new_lead`. They also add `builtin_model` (easy band only; Claude Code's Agent tool `model` for the lead's own sub-agent), but only when route's `choice` did not recommend a built-in sub-agent; when it did, that choice's `how` names the rung's model and wins. fresh, handoff and propose record a `lead_model` ledger event. A running conversation never switches model. An older task-routing copy without `--minutes` support gives no pick instead of an error.
- Skills (EN + ZH): agent-delegate, task-routing and project-manager teach the built-in sub-agent's model (a `builtin` choice's `how` first, then `builtin_model`, else omitted) and the new-lead model.
- Eval: `scripts/eval/r5.py run --lead-model auto` picks each task's lead model with the same rule, as its own arm (`ccx2@auto-medium`). Difficulty comes from a task's minutes, else from its reference change's size band (an oracle stand-in). `--dry-run` shows each pick and the repriced cost, for comparing auto with fixed opus and fixed sonnet. Auto with the reference band is an oracle upper bound: only tasks with pre-estimated minutes count for the on/off decision. An auto unit's done-key leaves out its picked model, so a changed rule never re-runs a done task into the same arm.
- Removed a tracked local test log (`two-way-test-log.txt`) that held personal paths; `*-test-log.txt` is now ignored.
- Queue lock (`ccx q`, Windows CI flake in `test_threads_never_lose_a_write`): threads of one process now take turns on an in-process lock before the lock file (polling was unfair: a writer that had just released took it again before a sleeping waiter woke, and one waiter gave up after 20 s while the others wrote). A waiter's deadline (2 x timeout) now counts from the last time it saw the lock file change hands, with a hard cap of 30 x timeout; waits are short and jittered. The "can this folder be written at all" probe got a unique name per call (two threads in one 15 ms clock tick on Windows < 3.13 drew the same name, and one hit the other's delete-pending probe and failed with a bare PermissionError). A denied release is retried for about 2 s instead of 0.2 s (a lock left behind stalls everyone until it is stale). The in-process wait has the same rules: it fails after 2 x timeout without a turn changing hands, i.e. a thread hung holding the lock. The file deadline counts from when the thread got its turn, so a long in-process wait does not make it fail on its first look at another process's lock. A change of holder is also detected by the holder's token in the lock file (Linux reuses a freed inode at once and has no birth time). Locally: max wait for one write 7.1 s -> 0.2 s (6 threads, 10 ms writes).
- `ccx show ID` without `--wait` follows a review fix round like `--wait`. It reports the chain's final record (with `chain`) and shows a fix round still running as running. While one is about to start it says `fix_round: starting` (ok false, `next` = `--wait`), but not once the run has a verdict or was dismissed. In the moment before the parent tags its fix round it says `fix_round: finishing`. A fix round started in its parent's second is found too (run ids sort by second, then random hex; it was missed when its hex sorted lower). Only the run's own fix round is followed (`review_of`, or the new `review_round` field >= 1), not a later `ccx resume` of it. `--full` of a chain also prints the first run's logs path. A final `review_issues` (no fix round ran) is no longer `ok`: `ccx run` and `ccx batch` now exit 2 for it (they exited 0). The `--bg` output's `check` field (the `ccx show` command) is now `peek`, so it is not read as the acceptance check.
- `review_failed`: the hint, the `ccx ui` card and the agent-delegate skill now say the same thing: the lead checks each [must] against the diff and fixes the real ones itself; another round costs a run and happens only on the person's word (a secondary ui button). `check_broken` and `over_budget` hints name the action their ui button gives. A table-driven test keeps hint, ui and skill in step for every kind.
- After a review fix round the result has `cost_chain`: tokens, API-equivalent and billed $ of every run and review in the chain, from the ledger; `recap`'s cost is the chain's. The per-run fields are unchanged; if the ledger cannot be read, `cost_chain_error` says why instead of the field silently missing.
- Tests: the personal-path hygiene scan now matches home folders in any case (Codex's lowercase `c:\users\...` trust entries) and Claude Code's `C--Users-<name>-...` project-folder names; `All Users` and the `…` placeholder are allowed.
- Docs: measured.md puts the round-5 r5h ccx2 row in context: all four post-fix ccx2 runs (r5e–r5h: 19, 20, 18, 19 of 20, $0.116–0.135 per success), builtin2 (17/20, $0.114 per success), that self/builtin come from the first run on older ccx, and the harness audit headline (76/76 right ccx2 units failed at least one harness criterion). The research index's round-5 row now reads the same in English and Chinese.
- Tests: the queue-lock churn test sets its stop flag before removing the lock file, so a waiter that takes the
  lock in between no longer fails the test (CI ubuntu 3.13 flake after #161).
- eval r5: opt-in arm `ccx2nc` (ccx2 with the unit hub's `[defaults] namecheck = "fail"`, asserted before the lead starts) and `<arm>@auto` entries in `--arms` (that arm's lead model picked per task), so r6a runs ccx2, ccx2nc and ccx2@auto interleaved in one invocation; ccx's shipped namecheck default stays `warn`.
- eval r5: rows record `namecheck_mode` and `ccx_namecheck` (mode, hits, `climbs` past a hit, `final_fail`); the summary's per-arm `namecheck` stats include `climbs_by_it`. A failed unit whose last check was namecheck's stand-in gets `ccx_check_reason = "namecheck"` and is left out of `check_passed_on_fail` (counted as `failed_on_namecheck`).
- ccx run: each attempt keeps its own namecheck result, and an in-loop namecheck failure keeps `check_reason = "namecheck"`, so a climb past a hit stays visible after a clean next rung.
- eval preflight: a unit's process markers end at `@` too, so a ccx2 unit never claims its ccx2@auto-medium sibling's processes.
- Eval clean room (scripts/eval): `--codex-home` is made absolute when parsed and a relative path is refused (r6a:
  `../x` passed preflight but every Codex resolved it from its unit's work dir and failed). Eval Codex runs
  (CCX_CODEX_ISOLATE=1 only) turn off the `plugins`, `remote_plugin` and `apps` features, the eval config.toml gets
  the same `[features]`, a starting run removes the remote plugins codex-cli 0.164 synced into `plugins/`, and the
  home is checked again after every unit (plugins, skills, features, connector / plugin catalog caches): a change
  stops the run. Rows of r5.py and batch.py record `codex_home_after`; rows record `fingerprint.codex_cli` and
  `codex_features_off`. A check-only preflight no longer fails after the canary on a home whose `[features]` table
  a starting run would write.
- eval preflight: the canary judges every text the lead wrote (and its result), not only its last message; an
  isolated lead that answered, then used Read, then ended on a line about the Read was failed as not isolated.
- `ccx ui` review cards: "agent says" (summary, verification) beside "ccx ran" (check command, exit, last output);
  the files actually changed and the diff come from the run's own snapshots (`undo.json` to `end.json` / `after`,
  read-only `/api/judge/<run>`, capped and marked truncated), never the live folder; a red box when the agent's
  file list and the real change differ. Older runs keep the old view with a note.
- `ccx ui` home: a "running now" strip (agent, time, tokens, stop with the usual confirmation); a task without a
  title takes its first piece's.
- `ccx ui` heartbeat: sent again when the tab is shown or focused; a hidden tab says so and the server waits 5
  minutes instead of 60 s. To-do chips are buttons; one aria-live region announces new to-dos.
- `ccx resume` and `ccx task resume` keep the review setting of the run they continue (`--review off` stayed off;
  before, a resume reviewed with the default `auto`); `ccx resume --review X` still overrides it. Run records carry
  `review_mode` (a review fix round keeps the setting of the run it fixes; older records count as `auto`).
- eval seven_func: every check runs with a fresh hub under its own scratch dir and refuses to start when its
  environment would point at the person's hub; its verdict reads rows only from that hub, by task or by label and
  start time. The resume check records `killed_after_s` right after the kill (it included scoring and the resume
  before) plus `resume_s`, and reports `mechanism_ok` (its `ok`: killed run unfinished, same task and session,
  label/check/review inherited, resume rc 0) apart from `task_ok` (the hidden test); its visible test now covers
  `low_stock`, so ccx's own check can catch the mistake the hidden test found.
- seven_func codex-lead: on Windows the hand-off command starts with PowerShell's call operator `&` (a quoted program path is a syntax error without it), as the agent-delegate skill already teaches.
- `ccx ui` Agent conversation page (per project, `#/conv/<project>`): the agents' board threads (`ccx say` /
  `ccx reply`), newest first, each message with who, when, to whom, `via` and its text, always escaped; read only,
  capped in size, a new message shows on the next poll. Two new to-dos on the home page: a thread stopped by the
  machine-message cap, and a message that asks the person (`@person` in its text as a plain mention, not in code; the
  board's `AGENTS.md` rules say so: projects set up earlier re-run `ccx board --init` to get that line). Both link to
  the thread.
- `ccx ui` reply: the person answers a thread from the page, through the same prepare -> confirm (one-time nonce)
  as the other buttons; at most 4000 characters (longer is refused, never cut); written by the board code as one
  message from the person, `via: ui`, never run. It clears the stopped-thread to-do by the board's own rules.
- `ccx q accept <id...>` (or `--all-ready`) lands the pieces a `ccx q run` left on worktree branches: it merges them
  one at a time in dependency order into the branch the project has checked out, runs the joint check (`--check`,
  else each piece's own) after each merge and rolls that merge back when it fails. A merged piece gets the lead's
  verdict, as `ccx q done --ok 1`, and a `q_accept` ledger row. Pieces that are not done (running, failed,
  no_changes, review failed), whose review is still running, that have no evidence (no passed check, review or
  verdict, and no `--check` here) or that wait on a piece not accepted are refused, each with the reason. A conflict
  aborts that merge and skips what waits on it; the other pieces still land. A run you rejected (`ccx verify --ok 0`)
  is refused, even with `--check`. When a rollback does not go through, or the joint check leaves edits in tracked
  files, the batch stops and nothing more is merged on top. A worktree piece given `ccx q done --ok 1` before its
  branch was merged still shows as `unmerged` and can be accepted (`q done` says so). It never pushes and never merges into
  main or another protected branch without `--into-protected`. `--dry-run` shows the plan. The merge steps of
  `ccx autonomy merge` are now shared helpers (its behaviour is unchanged).
- `ccx q ls` prints one line per piece by default (id, state, agent, seconds, $, then what to do next). A worktree
  piece that has not landed shows as `unmerged` with `next: ccx q accept qN`. `--long` prints the old JSON (anything parsing `ccx q ls` as JSON must add `--long`). The
  `q run` summary points `unmerged` / `waiting` pieces at `ccx q accept`.
- `ccx q add --dep 1` means q1 (before, a bare number was an unknown dependency). `ccx q done` takes several ids;
  with `--ok 1`, each needs a passed check or review of its own, or a `--note "<id>: ..."`.
- skills/agent-delegate: a short pipeline section. Hand off independent pieces with `ccx q`, collect them with
  `ccx show --any --wait`, and land finished ones in dependency order with `ccx q accept` while the others run.
- First delegation: a person at a terminal (no lead tool detected, or `--from user`) who names `--to` gets a task
  routing calls too small delegated anyway, on the cheapest rung, with one stderr line saying doing it yourself
  would be cheaper (`route.cheaper_self`); a lead's call is still refused as before. README, docs/install and
  `ccx setup` now suggest the same first command, one a lead's call delegates too.
- Environment failures (the agent CLI's own launcher could not start, seen in its stderr: ShellExecuteExW /
  CreateProcessWithLogonW / orchestrator_helper_launch) end the run as `kind: env` with a fix hint: no climb to a
  pricier rung, no retry, not learned from. The sub-agent's summary and generic "CreateProcess failed" lines do not
  count, so a task about process code still climbs. `ok` is false whenever the status is blocked or failed, in
  `ccx run` and `ccx selftest` alike (exit codes unchanged). A foreground `ccx run` / `resume` on a terminal prints
  one progress line to stderr about every 30 s (`CCX_PROGRESS_SEC`); a lead's piped call gets none.
- `ccx setup` without a terminal shows every remaining step as the exact command (`ccx init --hub`, `ccx sync`,
  `ccx sync --apply`, `ccx doctor`, the first delegation) and changes nothing; a CLI that is not logged in skips the
  selftest (also with `--yes`) and its login is listed first at the end.
- `ccx doctor`: the login row shows the real status line and the login command; the closing lines list what to do in
  order (logins, `ccx init`, then sync); "Codex as lead (sandbox)" is one info line unless `--codex-lead` (or Codex
  runs doctor). The recap after an auth failure points at the login.
- On a terminal, `ccx run` / `resume` / `route` end with two or three plain lines (result, cost, next command);
  piped output is the same JSON as before. `ccx route` labels follow `ui.lang` (English unless set to zh).
- `ccx undo` is listed under Everyday, `--apply` has help text, and a run that changed nothing says so in one line;
  when git cannot list the run's files (base commit gone) it reports `git_error` instead.
- Routing: a one-line edit ("add a line ... to README.md") no longer scores standard dev (T2); it starts on T1.
  Briefs that also carry hard, design or critical work keep their tier, and the pull-down never makes a brief T0.
- README (EN + ZH) states the same rule for the first command: from your own terminal `--to` delegates even a very
  small task; a lead's call still gets it turned back.
- `ccx demo` (also `ccx ui --demo`): `ccx ui` on made-up data in a new folder of the system's temporary folder, no
  account, offline: two projects, runs in every state (the review card with a real snapshot diff and a file mismatch,
  a running run, an environment failure), a three-piece queue with one unmerged piece, a board thread stopped at the
  machine cap and an `@person` question, a month of ledger costs. Marked "demo data" on every page; your hub and tools'
  folders are untouched; a button that would start an agent only shows its command; the folder is removed when the page
  closes or the export is written (`--keep` and `--dir` keep it; `--dir` takes only a new or empty folder or an earlier
  demo). The same data is the headless smoke test `tests/test_demo.py`.
- `ccx ui` switch-lead panel (project page and under a task's history): the current lead, when each lead worked (from
  `.ccx/handoffs/`), and "Continue with Codex / Claude" (DeepSeek where `dsh` is installed). It runs `ccx handoff --to X
  --by <current> --cwd <project>` after the usual second click, from the current lead's conversation file when it is
  there (`--from-transcript ... --no-model`), and shows the handoff file and the one line to paste into the other tool.
  Without that file the page says, before and after, that the handoff is a blank template to fill in first.
  The task timeline shows who was leading and each switch.
- `ccx handoff --cwd DIR` (the project folder; default the current one); its answer carries `paste`, the line to give
  the incoming lead (for dsh and gemini, which show no handoff at start-up, it tells them to read the file).
- New setting `defaults.focused_retry` (default false): when ccx's `--check` fails after the sub-agent said done and
  the next rung is on the same agent, that attempt continues the same session with the failing command and the last
  ~2000 characters of its output, told to fix only what fails (re-running only the failing part when the check's command can select it). Without a session id it starts fresh as before; the
  escalation ladder is unchanged. Off until a measured round shows it does not lower the right-rate.
- Independent review: the brief says ccx already ran the acceptance check ("You need not run it yourself", with the
  end of its output when ccx has it), and a Claude reviewer is asked for one plain git command per Bash call. No new
  permission: in r6a the refused reviewer calls were compound reads (`| head`, `cd && grep`), not test commands.
- `ccx -h`: show and q join Everyday; where, projects, intake, init, uninstall, repair and agents move to a new
  Advanced group; trial, ab, bench, improve and namecheck move to a Developer group listed last. Every command is
  still callable.
- `ccx ui`: a run that stopped on an environment failure (`kind: env`) shows how to fix it (in the page's language),
  `ccx doctor`, and `ccx resume` once fixed, instead of "Try again". An empty overview says what to run first (the same first delegation as README and `ccx setup`) and,
  once this ccx has it, `ccx demo`.
- `ccx sync` dry run: a missing Codex `config.toml` is one line ("will create ... with the hook block") instead of an
  "add hook block" line plus "nothing to import"; a file that does not exist yet says "create" rather than "update
  managed block". A community lead (dsh) found only inside its installed app, not on PATH, is no longer connected by
  default (one optional note instead); one connected before keeps its block, and `ccx uninstall` still removes it.
- `ccx doctor`: rows about ccx's own workings (python, tiers.toml, ccx config, hub format, hub layout, routing prior,
  tier policy, hook timeouts) show only when they are not ok, or with the new `--verbose`; one line says how many
  were left out. The task-routing skill's docs now point to `ccx doctor --verbose` for the "routing prior" row.
- eval (hold-out, batch): a finished unit's stream is moved with shutil.move, so a work dir on another drive than the repo (temp on C:, repo on D:) no longer fails every unit with WinError 17; a failed move is recorded in the audit instead of losing the unit.
- report / ui / stats: the saving estimate prices only the task-sized part of the sub-agent's tokens (fresh input
  and output, minus its start-up: cache reads and writes, and the ~20k fresh tokens a Codex run reads to start) at
  the lead's price; the old figure is kept for comparison as `saving_old_model` (not an upper bound; left out when
  a trial measured the saving). `ccx ui` ("Is it worth it"), `ccx report` and `ccx stats --summary` show the spend first and the
  estimate after it, labelled "model estimate; measured totals so far about even" with a link to docs/measured.md;
  `ccx stats --summary` gains `spend` and `saving` (the old `totals` keys stay). `ccx -h` no longer promises savings.
- run: a write run with no `--check` prints one reminder line on stderr; stdout and what ccx does are unchanged.
- docs: the README's first screen is the one job (a checkable chore from Claude Code to Codex on a cheaper model)
  with a self / built-in sub-agent / ccx table of round-5 dev-set ranges (hold-out pending) and a quick start with
  `--check`; the four best-case numbers moved to docs/measured.md. The FAQ compares with Claude Code's built-in
  sub-agent and no longer contradicts `ccx discuss` / `ccx send`; the plugin marketplace says five skills.
- `ccx ui`: a finished write run's card has "Undo this run" next to the diff (`ccx undo <id> --apply`, prepare and
  confirm like every button; it starts nothing, so it also runs in `ccx demo`), and a run that still fails its
  independent review has "The review is wrong: accept" (`ccx verify <id> --ok 1` with a note). A text meant for your
  lead is labelled "paste this to your lead", not "command".
- One order for a worktree queue piece in `ccx q ls` and `ccx ui`: the verdict first, then the merge. `q ls` prints
  `next: ccx q done qN --ok 1, then ccx q accept qN` until a verdict is in; the page says the same before the verdict
  and shows a "Merge into the project" button (`ccx q accept`, in the background) after it. `--cwd` now works after
  every `ccx q` subcommand, and `ccx q --cwd DIR done ...` no longer loses DIR.
- `ccx -h` lists the person's commands; `ccx -h --all` lists every group, with peek / board / say / reply under
  "Between agents" (all still callable). `ccx run -h` groups the routing rubric and coordinator options under
  "advanced". Help text for `verify --ok`, `reply`'s id and `--from`; `ccx demo -h` has a description, and `ccx demo` /
  `ccx ui` print `next: open <url or file>`.
- Naming: the Chinese page and docs call the lead 主导 everywhere; `ccx handoff --to/--by deepseek` means dsh, and the
  page shows "DeepSeek (dsh)" (`ccx run --to deepseek` is still the deepseek provider).
- The overview: each waiting item says first what you need to do, with a colour per kind (your call, check the
  result, a question for you), then the agent's own words; count badges are neutral; each project card says who leads
  with a link to its switch-lead panel. After a verdict the side panel moves to the next waiting piece ("Next
  waiting", keys j / k). Times past two days read in days and weeks; a machine failure with no reason shows no empty
  brackets; the queue's top box says "Work queue: N pieces" instead of a quote you never typed.
- `ccx ui` "Undo this run" lists the files `ccx undo`'s dry run would put back and move aside, and refuses (prepare
  and again at run) when that goes beyond the files the run left changed (a later commit, your own edits, another
  run's work) or a run going on from it is running: `ccx undo <id>` in a terminal shows the list first. "Merge into
  the project" runs `ccx q accept --dry-run` first, so a refusal such as a protected branch shows on the page. On a
  queue piece whose review failed, "The review is wrong: accept" and "I'll handle it" are `ccx q done` verdicts on
  the piece, so it can be merged next.

## 0.5.0 — 2026-10-25 (save, check, split, share, control: cheaper defaults, review that checks the task, project catalog, shared work context, the board, stop and archive)
- Highlights: everything since 0.4.0 (PRs up to #104), grouped by theme below; 523 tests. Measured on real CLIs:
  shared work context, right the first time 36/36 vs 7/36 and 63 % less spend
  ([report](docs/research/2026-10-25-shared-context-ab.md)); project memory 9/9 vs 0/9 and hub memory 9/9 vs 0/9;
  seven-cores round 1 ([report](docs/research/2026-10-24-seven-cores-ab.md)): delegating cut the lead's tokens 32 %
  but not the total spend, routing gave no gain, review after the fix 3/3.
  Round 2 ([report](docs/research/2026-10-25-seven-cores-r2.md)): a cheap model was right 47/49 on trap tasks;
  review 36/36 vs 33/36 at +$0.004 a task; dividing the work 14/14 vs 12/14 at 20–39× the spend; ten parallel
  runs 2.5× faster but 4.7× the tokens. Default shape: one cheap model plus another vendor's cheap review.

### Save: routing and cost
- Default `tradeoff` is now `save` (was `balanced`): routing starts small work on the cheap model. With routing fed
  the seven-cores A/B (PR #30), 5-minute work goes to codex luna low (predicted 0.94, about $0.004) instead of
  claude sonnet medium (0.997, about $0.04); 15-minute work still goes to sonnet. An existing hub keeps its own
  `defaults.tradeoff` if it set one (`ccx config get defaults.tradeoff`).
- Explicit picks can teach routing. A verdict reaches routing only with a difficulty b, and a run with `--model`
  / `--effort` but no `--minutes` (or rubric flags) has none: in the seven-cores A/B (PR #30) 63 verified luna-low
  runs left routing at n = 0, still predicting p = 0.48 where they were right 55 times out of 63. agent-delegate's
  explicit-pick line now includes `--minutes <n>` and says why, and the result of such a run says
  `route.learns: "no: give --minutes ..."`. (The A/B's 84 runs were fed back into one person's routing state with
  b from the minutes the A/B used; luna low at 5 minutes then predicts 0.94 and `--tradeoff save` picks it.)
- H14, a head start for new users: the task-routing priors carry the seven-cores A/B round 1 per rung (`[observed]`:
  runs and first-rung successes by hidden tests, per difficulty). Until a hub records a rung's first outcome, that rung
  starts from the theta shift these outcomes imply at weight 0.5 (cap 1.5): luna low +0.67 (5-minute work 0.55 → 0.74,
  measured 38/45), sonnet medium +0.78 (42/42). A hub that already learned a rung is not affected. `ccx doctor` shows
  where routing starts ("routing prior"). See task-routing references/method.md §6b.
- `ccx route --lead` reads your own conversation's size from its last request when `--lead-ctx` is not given
  (`ctx_source: lead_session`; `given` / `none` otherwise; Claude Code and Codex leads) and prices it as its own
  term: each request you make re-reads it, and doing the task yourself takes more of them than delegating (new
  priors `lead_turns_self_base` / `lead_turns_self_per_b` / `lead_turns_delegate`, from the seven-cores A/B: 3 vs 2
  at small tasks). `--ctx-tokens` keeps its meaning (context the task adds). `task_routing.py route --lead-ctx`.
- `ccx propose` (H12): the same flags as `ccx route --lead`, plus a proposal id, whether it is worth offering and
  one line to say. `ccx run --proposal ID` records the yes and links the run; `ccx propose --no ID` records a no.
  `ccx propose --stats [--days 7]`: proposed -> agreed -> delegated -> judged, and the share of real
  (non-evaluation) runs with a verdict from the lead or the person (target 60 %).
- `--to auto` / `ccx route` no longer read a week of Codex session logs to know its quota. `quota.codex_readings`
  reads only the end (64 KB) of the session files changed in the last 48 hours (at most 40, newest first), plus
  small pieces further back at twice the distance each time, and parses only lines with `rate_limits`; when none of
  those has one it looks at up to 5 older files. Each file's readings are cached in
  `<hub>/ccx/codex-quota-cache.json` by (path, mtime, size). The pace now says when its reading was taken
  (`read_at`). Measured on one machine (144 session files, 2.5 GB): `ccx route --minutes 5` 13.9 s -> 0.70 s
  (quota 13.87 s -> 0.10 s uncached, 0.04 s cached), same projection as the full scan (0.224 vs 0.223).
- H2: every attempt taken for a quota stop leaves its evidence in `<hub>/ccx/quota-stops.jsonl`: Claude's rejected
  `rate_limit_event` as it came, or the hint that matched and the words around it (Codex and others), with run,
  agent, model and retry time. `ccx quota` shows the last five (`recent_quota_stops`). A wrong call (the word
  "quota" in a task's own output, a new wording of a real limit) can then be found and the hints corrected without
  spending quota to test. No quota stop has happened in real use yet (0 of 337 runs on the author's machine).
- A sub-agent's own sub-agents, limited by spend and quota rather than head count (proposals F10–F14, narrowed
  by the PR #6 measurements). F10: Codex's concurrency and F13: its sub-agent model are no longer forced to 3 and
  the parent's rung; ccx sets them only when quota is tight (1 at a time, one rung down) or snug (2), or when the
  lead says `--subagents N|off`. F11: the spend cap is the piece's budget (`--budget`, a queue item's remaining
  share), else `[subagents] max_usd`; a run over it stops as `over_budget` and `ccx resume RUN --budget X` goes on.
  F12: Claude write sub-runs get the Agent tool, because their sub-agents' spend shows while they run (stream
  events and `<session>/subagents/*.jsonl`, checked live with Claude Code 2.1.309); the watchdog reads it, and a
  Claude result is now counted from `modelUsage` — `usage` covered only the main conversation's last request
  (11.6k vs 19.9k cache-write tokens with one sub-agent), so sub-agent tokens were missed. F14: a brief listing
  3+ parts (or `--parallel`) explicitly asks for sub-agents on the independent parts. Docs now say that with
  codex-cli 0.164 + gpt-6-luna/low sub-agents were not started even when asked, so these limits are untested live.
- The lead's own context (proposal H10). Almost all spend is the lead re-reading its whole conversation every turn
  (here: sub-agents $0.34 in 30 days; the median lead turn re-reads ~220k tokens, ~$0.06, over ~19k turns). `ccx lead`
  lists recent lead conversations: turns, what the last and the largest turn read, cost per turn, advice. `ccx sync`
  adds a Claude Code UserPromptSubmit hook (`ccx lead --hint`) that prints one line when a conversation re-reads more
  than 150k tokens a turn (at most once per 20 turns, never fails the turn); `ccx uninstall` removes it. Codex: no
  per-turn hook yet. `ccx report` shows "Lead cost per turn"; agent-delegate says to send big reads out and hand a
  long conversation over to a fresh one.
- A model for the lead itself (proposal J5): `ccx lead --suggest` reads the last 30 turns of this conversation
  (Claude Code), sorts them into code edits, doc edits, reading/running and talk (files changed through the shell
  count as code), and compares what a turn costs at this context size on each model. When code is under a fifth of
  the turns it suggests one rung down, with the saving per 100 turns and how many turns pay back the one cache
  rewrite a switch costs; otherwise it says to stay. `ccx report` adds what the same lead turns would have cost one
  rung down. Here: 7 days of lead turns $1,204 AE, one rung down $952 less; this conversation (~440k tokens a turn,
  half its recent turns editing code) is told to stay on opus.
- Long output cut down before the lead reads it (proposal J3): `ccx sum -- <command>` runs the command, keeps the
  full output in `.ccx/sum/` (git-ignored, last 20) and prints only what matters — for tests each failure's header,
  last frame and error line plus the summary; for diffs files changed with +/− counts and the first hunks; for logs
  error lines with one line of context, repeats folded, and the tail. Capped at 2,000 characters
  (`--max-chars`); `--ask "..."` lets a cheap routed model answer from the saved output; the exit code is the
  command's. agent-delegate tells the lead to use it. Here a 40,657-character `git diff` came back as 2,053.
- What the lead re-reads every turn (proposal J1): `ccx lead --breakdown` splits the first turn's measured
  prefix into system prompt, built-in tool definitions, each MCP server's tool definitions, each instruction file,
  the skill list, the start hook's output and the rest, from the tools' own session files (Claude Code's request
  shape and start-up attachments; Codex's base instructions, tools and AGENTS.md). Sizes are estimated from the text
  and scaled to the measured count; each part shows its cost per 100 turns, and big ones get advice (turn off an
  MCP server this project doesn't use, link fewer skills, shorten an instruction file). Here: 78.6k tokens a turn,
  of which built-in tool definitions ~23k, the skill list ~6k, one browser MCP server ~5.6k.
- Where the prompt cache broke (proposal J2): `ccx lead --cache` finds turns that re-wrote the conversation into
  the cache (Claude: cache writes jump; Codex: uncached input jumps) and names the likely cause — idle longer than
  the cache lives (1 h when Claude Code asks for it, else 5 min; ~10 min for Codex), a model switch, the
  conversation compacted, an instruction file edited, the tool list changed — with what each break cost over a
  cache read. The previous long session here had 5 breaks costing ~$8.5 extra (3 idle, 2 compactions).
- A formal comparison over a week (proposal H11). `ccx trial start [--days 7] [--rate 0.5]` puts about half of the
  delegable tasks on the lead's side ("do this one yourself", closed with `ccx ab done`) and delegates the rest,
  balanced per kind of work and difficulty. Both halves are measured the same way: the lead conversation the task
  belongs to (and its own built-in helpers) in the task's window, plus the sub-agent's spend and ten minutes for
  checking a delegated result; unjudged runs don't count as having held up. `ccx trial report [--markdown]` and a
  card in `ccx report`; fewer than 10 tasks a half is shown but not called a result. Usage events now carry the
  built-in helper's parent conversation, and self-run samples count only their own conversation.
- `ccx trial` has a third half, "native": a Claude Code conversation that did the task with its own built-in
  helpers or a dynamic workflow (ultracode). Tag it with `ccx trial tag --arm native --session ID [--kind K --b B
  --ok 1|0 --since/--until ISO]`; its spend is read from that conversation's files, every helper and workflow agent
  included. The report compares each half with the lead doing it itself only within the same kind and difficulty
  (weighted by task count, 95 % interval resampled within buckets) and says "deferred, no conclusion" below 10
  matched tasks a half. `ccx trial report --markdown` shows three columns.
- Lead usage now ties a workflow's agents (`<session>/subagents/workflows/wf_*/agent-*.jsonl`) to their
  conversation; before, their tokens were counted as separate conversations and missed by per-session windows.
- `claude -p` sub-runs pass `--settings {"ultracode": false, "workflowKeywordTriggerEnabled": false}` and no longer
  inherit `CLAUDE_CODE_EFFORT_LEVEL`, which overrode the routed `--effort` (checked against Claude Code 2.1.309).
- The dashboard's saving is measured from `ccx trial` when a trial has enough tasks in both halves, otherwise it is
  labelled a model ("Estimated saving (model)", `saving_kind` in `ccx stats --summary`) with what it assumes.
- Smaller APIs through Claude Code as providers, each with `daily_usd = 1.0` and taking part only when its key is
  set: `kimi`, `glm`, `qwen` (base URL from `DASHSCOPE_ANTHROPIC_BASE_URL`), `openrouter`. A provider can carry its
  own `prices`; a pay-per-token model with no price is refused, since its daily cap could not hold.
- Pay-per-token agents are never a quota fallback or a reviewer unless pinned; `ccx agents` shows `ready`,
  `needs_env` and `daily_usd`; `ccx report` counts every DeepSeek route as one stream and other providers as one more.
- `ccx discuss --dry-run` estimates turn by turn: the price of each agent's model at `--tier` × (the CLI's start-up
  overhead + question + context + the points passed so far), for the longest talk (`usd_max_est`: every round, then
  the judge) and the shortest (`usd_min_est`: agreement in round 1). Earlier discuss turns on the same rung
  (agent:model:effort) in the ledger replace the model. It also says which model each agent will use (`models`) and
  where each number comes from (`basis`). The old estimate averaged all recent read runs and said $0.036 for a talk
  that cost $0.283 (discuss-r1); replayed on the same inputs the new one says $0.17–0.40.
- `ccx discuss --tier` defaults to `auto`: every agent talks at T2, except one whose subscription quota is projected
  past 100% by its reset (`ccx/quota.py`): it steps down to T1 (Claude on haiku, Codex on luna). `--dry-run` shows
  each agent's tier, model and why (`tier`, `models`, `tier_why`); the saved discussion keeps `tiers`. A tier given
  (`--tier T1`) applies to all, as before.

### Check: review and acceptance
- Independent review is cheaper and checks the task, not the tests (seven-cores A/B, PR #30: routing picked
  claude sonnet medium as the reviewer, 20–40x the luna-low work it reviewed; it mostly asked for more tests and
  missed the same real bug three times). Now each other vendor's T1 rung (claude haiku low, codex luna low, ...)
  comes before the routed rung, so sonnet is only the fallback in `[review] also`. The review brief asks the reviewer
  to go through the task requirement by requirement (each return value, case, rule and error it names), since the
  acceptance tests may cover only some; a requirement not met is `[must]`, missing tests are a `[note]`. Real check
  (inventory task, luna low worker, `--review on`, 3 runs): haiku low found the bug each time ("returns Item
  objects, the task asks for SKUs"), the fix round made the hidden test pass 3/3 (round 1 with review: 0/3), review
  cost $0.004–0.009 per run (round 1: $0.04–0.09).
- H13, a review when the evidence is weak: in `--review auto` (the default) a write run is also reviewed once, by the
  cheapest rung of another vendor (about $0.005), when its acceptance command is `weak` (it passed wrong work before,
  J7) or there is no acceptance command and only the sub-agent checked itself. At most `[review] weak_daily` (20) a
  day, counted from `weak_review` ledger events; `[review] weak = false` or `--review off` switches it off. Whether
  this catches more wrong work is left to the next evaluation round.
- J7, how far an acceptance command can be trusted: `ledger.check_trust(rows, p=None)` groups runs by their
  `--check` command and place (the folder name, numbers collapsed; a ccx worktree counts as its repository) and counts
  how often a pass was then judged wrong by the person or the lead. With at least 3 judged and more than 20% wrong the
  command is `weak`: its pass no longer makes a probable verdict (the run waits for a person), the run result's `check`
  says `weak` with a note, and `ccx report` has a "Where it was wrong" card listing such commands. The run's ledger row
  now keeps its check (`check: {key, cmd, passed}`); older rows are read from their run.json. Replayed on the
  seven-cores round-1 ledger: all 19 runs that passed the check but failed the hidden tests (the report's 14 in groups c
  and d, 3 inventory runs of the delegation arm, 2 of the pilot) fall in weak groups, and no group without such a run is flagged.
- A failed `--check` now escalates. When the sub-agent says done and ccx's own run of the acceptance command fails,
  the attempt is marked `check_failed` (learned as a failure of its rung) and, while a rung is left, the same session
  continues on the next rung with the check's output; before, only blocked/failed escalated and a cheap model that
  wrongly said done stopped there. The check runs once per attempt (the last result is reused, not re-run).
- `ccx undo --apply` no longer records the run as wrong. It restores the files, writes `undone.json` and an `undo`
  event (`reason: undone`), and the run waits for your verdict (the 12-hour sweep skips undone runs). Add `--wrong` to
  record it as wrong in the same step (a lead verdict: it teaches routing). Seven-cores A/B question 8: undoing to
  retry or to split the work used to teach routing a failure. See docs/DECISIONS.md.
- J7 spot checks: `ccx verify --sample N` picks N random probable verdicts (soft) of this week that nobody judged
  since, shows what each run changed (summary, files, check or self-check, why it was judged), and asks ok / wrong /
  skip; an answer is your verdict (`ccx verify`), so it teaches routing and feeds `ledger.soft_trust`. Without a
  terminal, or with `--list`, it prints the picks as JSON. Evaluation runs are left out unless `--include-evals`.
- Trust in probable verdicts (proposal J7). `ccx stats --summary` / `ccx report` count how many probable verdicts
  (H13) were later judged again by you or the lead and how many of those the other way; once 5+ were re-judged and
  over 20% overturned, new probable verdicts stop teaching routing (a weak check may pass wrong work as right).
- Verdicts without asking (proposal H13). A finished run nobody judged for 12 h gets a probable verdict from the
  evidence: right when ccx's check passed or the sub-agent self-checked, the independent review (if any) passed, and
  it was neither undone nor sent back; runs without such evidence wait for a person. `ccx undo --apply` records the
  run as wrong. Verdicts drawn this way are marked `soft`, kept apart in `ccx stats` / `ccx report` ("judged by you
  or the lead · N probable"), feed routing only where nothing was learned yet, and any `ccx verify` overrides them.
  `ccx verify --ok 0 --reason unfinished|wrong|overreach|other` records what was wrong; the report counts reasons.
  Runs quietly at session start; `ccx verify --sweep [--after-h H]` by hand.
- H14, a weekly "where it was wrong" in `ccx report` (`ccx/accuracy.py`), this week next to last week: per agent ×
  tier × kind of work the share of judged pieces that were wrong and that needed rework; routing's prediction `p`
  against what happened (Brier score and binned calibration; right = judged right and done by the rung routing
  picked); how many probable verdicts were overturned later; and the acceptance commands that let wrong work through
  (J7). Evaluation runs are left out (`ledger.is_eval`); `ccx report --include-evals` counts them. `ways.pieces` rows
  now carry `ts`, `p`, `attempts` and `ok`.
- H9 statistics without evaluations: `ccx way --stats` (and the builder order `ccx way` uses) leave evaluation runs
  out (`ledger.is_eval`: label `eval-...`, `--no-ab`, ccx's own probes); `--include-evals` counts them. Each agent's
  rates are also split by tier (`tiers`, by the model:effort that finished the piece), so a cheap tier's misses are
  seen apart from the strong one's. On the maintainer's hub (30 days, code) the seven-cores A/B had made codex 116
  judged pieces at 71% first-time-right and claude 51; real use alone is codex 9 at 78% and claude 4.
- `ledger.is_eval(row, runs=None)`: one rule for "this run measured ccx, not the person's work" — label `eval-...`,
  started with `--no-ab`, or ccx's own probe (`selftest`, `quota-probe`). Verdict rows are judged by the run they
  point at (`ledger.runs_by_id`). `--no-ab` is now kept in the run's ledger row (`no_ab`) so it can be told apart.
  Statistics that learn or judge from real use call this to leave evaluations out.
- The session-start line "N delegated piece(s) wait for you" leaves out evaluation runs (`ledger.is_eval`: label
  `eval-...`, started with `--no-ab`, ccx's own probes). On one real hub the count went from 33 to 16. `ccx ui` itself
  still lists those runs.
- agent-delegate: when ccx already ran your `--check` and it passed, don't run it again yourself (H11: that is what
  makes delegating save the lead a turn).
- Read-only sub-tasks are told their shell still works: in a real E8 run gpt-6-luna/low once answered that it had
  no tool to read the file it was asked to read.
- `ccx resume --review auto|on|off`, as `ccx run` has. A write follow-up was always reviewed `auto`, so a Codex-only
  preflight called Claude (haiku) for the review.

### Split: delegation, the lead, projects
- agent-delegate skill, new section 0 "Offer it; the person decides" (H12): before a large, checkable piece of work
  nobody asked to delegate, the lead runs `ccx propose`, offers in one line only when it is worth it, delegates only
  on a yes with `ccx run --proposal ID` (never `--no-ab`, which marks an evaluation run) and always gives
  `ccx verify`; a no is recorded with `ccx propose --no ID`. Section 7 offers a discussion the same way (H4).
  The skill's description now covers that offer; task-routing points to `ccx propose` and `--lead-ctx`.
  `ccx propose`'s line says the odds as a percentage.
- `ccx projects scan` / `ccx projects` / `ccx projects show <name>`: a catalog of the person's projects, found by
  code (no model, no network) under the folders in `projects.roots` (default empty; `ccx config set projects.roots
  "DIR;DIR"`). A project is a folder with `.git`, rule files (AGENTS.md / CLAUDE.md) or a build file, or a README
  right under a root. A folder with projects right inside it and no work of its own (no `.ccx/`, `topics/` or
  STATUS) is a group: not listed, its rules are inherited by the projects inside. Repositories inside a project
  (e.g. `shared/source/X`) are listed too, with `parent`. Dependency, build, backup, worktree, topics and archive
  folders are skipped, and a link or junction to a folder already seen is recorded once (`also_at`). Each entry
  keeps a one-line summary (README / AGENTS first paragraph), aliases (folder, titles, git remote, package name,
  Chinese names in titles), keywords (README titles one level down), the rule files to read first (nearest
  first), state files (STATUS, handoff, .ccx/context.md, topics/), last activity and the latest commit subjects
  and journal lines. The catalog is `<hub>/ccx/projects.json`, on this machine only; a scan of a real workspace
  with 31 projects took about 1.4 s (`ccx/projects.py`, `tests/test_projects.py`).
- The project catalog stays fresh by itself: at session start (`ccx mem delta`, the start-up hook) ccx rescans
  `projects.roots` in a detached, windowless process when the catalog is older than `[projects] refresh_hours`
  (24; 0 = off), or when roots are set and nothing was scanned yet. The start never waits; one scan at a time
  (a start within 10 minutes of the last one leaves it). `ccx projects scan` is still the full manual rescan
  (`ccx/projects.py` `refresh_later`).
- `ccx run --project <name, alias or sentence>`: delegate into a project from the catalog. The name is resolved
  like `ccx where` (one project, else an error listing the candidates); the run goes to that folder and the
  brief starts with the project's rule files (nearest first) and state files. When the project's rule files
  speak of approval, authorization or a freeze, ccx does not start the run: it quotes those lines as written
  (`approval_rules`, file and line) and the lead decides from them, or asks the person, then runs again with
  `--rules-ok`. `ccx where` shows the same lines with its pick. The agent-delegate skill and the session start
  (one line, only when a catalog exists) say: a project named without a path -> `ccx where` first.
- `ccx where "<a sentence>"`: which project a vague sentence is about ("改一下那个桌宠", "the harness PR"), by
  code only, free. Words that say what to do (fix, PR, 改一下, 那个 ...) are dropped; the rest is looked up in each
  catalog entry's name, aliases, path, sub-folder README titles, topics, summary and latest commits / journal
  lines (Chinese by two-character pieces, English with one-letter typos allowed). One clear candidate is given as
  `pick` with its path and the files to read first; when several fit, all are listed with a confidence and why,
  for the person to choose (`ccx/projects.py` `where`).
- One adapter per agent CLI (proposals I1–I4). `ccx/agents/<name>.py` answers the same questions for Codex, Claude
  Code and Gemini CLI: how to run it headless and parse the result, where its sessions live, how to check its
  login, its instruction file and start hook, how permissions are given, its vendor, official or community
  support, the CLI version checked, and what it can do (`can_lead`, `can_work`, `can_resume`, `builtin_subagents`,
  `quota_readable`, `live_cost`, `turn_hook`). `runners.py` keeps the shared parts and re-exports the old names.
  `ccx agents` lists them (plus providers); `ccx doctor` shows each one's vendor, support and capabilities, and only
  the official agents are required. "Another agent" now means another vendor: DeepSeek through the Claude CLI is
  its own vendor (a provider can say `vendor = "..."`), so Claude may review DeepSeek's work. The quota fallback
  lets routing pick the cheapest in total among installed agents of another vendor, and reviewers default to
  routing's cheapest easy-read rung per other-vendor agent; `[review] by` is empty by default and only pins.
- `--as` (in `ccx mem delta`, `ccx fresh`, `ccx lead`) takes its choices from the adapters: an agent is a possible
  lead when its adapter says `can_lead` (`ccx.agents.leads()`), instead of a list written into each command.
  docs/research/2026-10-25-gemini-lead (EN + ZH): what a Gemini CLI lead would need (its SessionStart and
  BeforeAgent hooks exist by its docs), the work in pieces and how big; not built, the person decides.
- DeepSeek as the fourth vendor: an adapter for DeepSeek's own agent, DeepSeek Harness (`--to dsh`; headless
  profile, `--json` events, model in a `--patch` overlay, sandbox in `DSH_PERMISSION_MODE`, session-log upload and
  telemetry turned off; checked against dsh-v0.2.1-rc.3 source, not run for real), and DeepSeek through Codex
  (`--provider deepseek-codex`, a `-c model_providers.deepseek` override with `env_key`; run for real). Provider runs
  on Codex disable `apps` and `plugins` (219k vs 10k input tokens per request, measured) and Codex's own sub-agents.
- DeepSeek can lead, by two routes, tested on a real machine: DeepSeek Harness (`dsh` 0.2.1-rc.3 headless) handed
  work to Codex, and Claude Code running a DeepSeek model (`--bare`, ANTHROPIC_BASE_URL) handed work to Claude.
  `lead_identity()` tells the lead from the environment (`DSH_SESSION_ID`; the provider whose ANTHROPIC_BASE_URL
  Claude Code uses; Codex's config.toml `model_provider`; or `CCX_LEAD`), `--from` accepts dsh and the providers,
  and every run records `caller_vendor` (deepseek on all three routes). `dsh` is `can_lead`; `ccx mem delta --as
  claude` counts the notes for the provider when Claude Code runs one. A Claude sub-agent of such a lead gets neither
  the lead's DeepSeek endpoint and key nor `CLAUDE_CODE_SIMPLE` (which made it bare and "Not logged in").
- ccx finds the `dsh` bundled with the DeepSeek Harness desktop app on Windows from the uninstall registry's
  InstallLocation when it is not on PATH (adapters get an optional `locate()`); `ccx doctor` shows where. Tests set
  `CCX_NO_LOCATE` so they never find a real CLI.
- A dsh session keeps the read-only / write mode it started with, so ccx no longer continues a dsh session across
  read and write (a write task continued in a read-only session could not edit, real run).
- `ccx sync` warns when, with an external snapshot, a lead such as dsh does not load it. agent-delegate says how
  DeepSeek leads (PowerShell 5.1 shell, `--brief-file`, dsh needs `danger-full-access` and what that means). README
  (EN + ZH): leads are Claude Code, Codex and DeepSeek (tested); Gemini CLI untested.
- `ccx discuss "question"` (proposals H3, H4, I7): 2–3 models from different vendors talk a decision through. Roles
  by order (`--with A,B[,C]`, default the installed agents, one per vendor): one proposes, one finds faults
  (`CRITIQUE: objections|agree`, `[must]`/`[note]`), one judges (`RECOMMEND:` plus `[consensus]`, `[disagreement]`,
  `[reason]`); with two vendors the proposer also judges and the result says so. At most 3 rounds (`--rounds`), and
  it stops early when the critic agrees; between turns only the points travel (summary ≤500 characters, ≤8 items of
  ≤300 each), never a whole answer. Every turn is a read-only, ephemeral ccx run with no review and no sub-agents,
  so it is accounted like any run. The result has recommendation, consensus, disagreements and reasons;
  `--dry-run` shows who would take part, the most calls and an estimate from each agent's recent read runs;
  `--show ID`, `--list`. `ccx ui` gets a Discussions page (turns drawn as a conversation, the outcome under it) and
  a "recent discussions" list on the overview. H4: agent-delegate section 7 tells the lead to propose a discussion
  for decisions costly to get wrong and to start one only on the person's yes.
- `ccx discuss` names the model for every turn, so a provider such as `deepseek` (no row in the tier table) can take
  part: it runs on its own model instead of failing with "tier T2 has no deepseek model".
- `ccx discuss` reads the critic as agree / objections / unparsed (`discuss.critique`): `[must]` items count as
  objections even without the `CRITIQUE:` line; no line and no `[must]` is unparsed, which neither ends the talk
  early nor counts as agreement. An unparsed critic, or a judge without `RECOMMEND:` or without tagged items, is asked
  once more in the same session (resume) with the rule repeated; if it still does not keep to it, the turn says
  `unparsed` and the result lists `unparsed_turns` (and `unparsed` for the judge) instead of guessing. `ccx ui` marks
  such turns. Discuss turns now keep their CLI session (`Request.keep_session`) so they can be resumed, and
  auto-archive tidies them like other finished runs.
- H4 in code, not only in the skill: when a lead (Claude Code or Codex, told from the environment, not from
  `--from`) or a ccx sub-agent starts `ccx discuss` without `--confirmed`, it gets the estimate and `"ran": false`
  instead of a discussion; the person typing it in a terminal runs it as before. agent-delegate §7 says to add
  `--confirmed` on the person's yes.
- docs/research/2026-10-25-discuss-three-vendors (EN + ZH, data JSON): the first real three-vendor `ccx discuss`
  (Codex proposes, Claude criticises, DeepSeek judges, T1): independent judge, every tag read, $0.016 against an
  estimate of $0.009–0.021, shown in `ccx ui`. The critic never agreed in three rounds (its `[must]` items were
  refinements); Gemini CLI, `dsh`, Kimi, GLM, Qwen and OpenRouter: not run (not installed / no key). README (EN + ZH)
  says discuss ran for real.
- `ccx discuss --bg` runs the discussion detached, the same way as `ccx run --bg` (one shared `detach()` in
  `ccx/commands/common.py`): the id is fixed and a "starting" record saved up front, so `ccx discuss --show ID` and
  `ccx ui` follow it turn by turn; the detached process's output goes to `<hub>/ccx/discussions/<id>.log`.
- `ccx way "brief" --risk low|visible|critical` (proposals H8, H9): the risk picks one of three ways of working.
  low = one agent builds, another vendor reviews when it is worth it (F1); visible = another vendor plans (`[step]`,
  `[accept]` items), one builds with the plan in its brief, the planner accepts the diff (one fix round; the
  acceptance is stored as the build's review, so probable verdicts see it); critical = two vendors each build a
  version in their own worktree and a third (or the second's vendor in a fresh run) compares them (`PICK: A|B`),
  only with `--yes` because it costs about twice as much; nothing is merged automatically. `--dry-run` shows the way
  and roles. H9: `ccx way --stats` gives, per kind of work (code / read / research / write) and agent, how often a
  piece was right the first time (judged right, no follow-up, no review fix) and how often it needed rework (a
  follow-up, a review fix, or judged wrong), over judged pieces only. With 5+ judged pieces these rates order who
  builds, and a builder right the first time under 50% gets a planner (solo -> plan_build). `ccx ui` shows the
  table under "Who is reliable at what".
- `ccx task resume` restarts a step whose run was killed before its agent session began. A real run killed after
  12 s (seven-cores functional check) left a run record with no session id and no ledger row; resume then only
  printed "do step 1 yourself" and exited 0. Now every fresh run saves the person's brief (`runs/<id>/brief.md`) and
  its acceptance command (`check_cmd` in run.json), and resume starts the step again on the same agent and rung from
  that brief plus the checkpoint brief, telling the agent to look at `git diff` first. The result says
  `restarted: <old run id>`. Checked on a real Codex run (gpt-6-luna low) killed after 4 s.
- `ccx send --to` offers only `codex`, the one it can do (`codex queue`); `--to claude` used to be offered and then
  fail. The README says why: a Claude Code session, terminal or desktop app, has no way in for a message from
  another program; a Claude sub-agent is followed up with `ccx resume <run_id>`.
- Two small fixes from the seven-cores A/B (PR #30): the spend-cap message shows amounts below a cent with four
  places (a $0.0001 cap read "spent $0.00 (cap $0.00)"); agent-delegate tells the lead that a printed result with a
  `run_id` means the delegation ran, so it must not send the same brief again (a real Codex lead did, after a run
  that had already passed) and should use `ccx resume <run_id>` to add to it.

### Share: memory, shared work context, the board
- Shared work context (docs/shared-context.md): ccx reads what a session has been doing from the tool's own session
  file, by code (Claude Code projects record, Codex rollout, dsh session; dsh's zstd files through Node or dsh's own
  Electron), and the other tools can read it. `ccx run --context auto|on|off` attaches the lead's recent asks,
  settled sentences, plan, changed files and latest message, each with time and source, ~1k tokens (auto: write
  tasks only; `[shared_context] run`); `ccx peek claude|codex|deepseek` is a read-only look at another tool's open
  session here; the per-turn hook adds one line per other tool that did something since you last looked
  (`[shared_context] turn = false` turns it off). All of it framed as data, not instructions, in the sub-agent's
  rules, the leads' memory block and the board's AGENTS.md block. Each tool keeps its own context: this is a shared
  summary, not one shared context. A/B on real CLIs in docs/research/2026-10-25-shared-context-ab.md.
- Shared memory in use (proposals H5, H6, I6). H5: `ccx mem suggest [--from-transcript claude|codex]` gathers
  notes worth keeping from a lead session (what the person asked to be done a certain way, decisions, pitfalls,
  each with its source); `ccx fresh` and `ccx handoff --from-transcript` gather them too; the session start says
  how many wait; nothing is written until `ccx mem accept N [--text ...]` (or `ccx mem reject N`). The gathering is
  heuristic and lets ordinary sentences through, which is why the person decides. H6: this project's notes come
  first at session start; each note counts how often it is shown or found (`mem search`), and `ccx mem stale` also
  lists notes nobody used for 60 days. I6: a tool with no start hook (Gemini CLI) gets up to 4 notes that share
  words with the task in its brief (~300 tokens at most, none when nothing matches); `ccx sync` writes the memory
  block into the context file of every tool that can lead (from the adapters, not a fixed pair), naming the hub
  original.
- Shared hub notes now reach Claude and Codex sub-agents too (I6). Before, a tool with a start hook was skipped on
  the assumption that its hook shows memory, but under a sub-agent `ccx mem delta` prints nothing, so hub notes
  never reached Claude or Codex sub-agents at all. Every sub-agent's brief now carries up to 4 notes that share a
  word with the task (`memory.for_brief`, budget unchanged at ~300 tokens); no shared word, no note.
- `ccx mem report [--days 14] [--json]` (H6): who wrote the shared notes that were used and who used them (a
  writer x user matrix), per project, by way of use (session start, search, a sub-agent's brief), and how many
  notes written in that time nobody used yet. `memory.mark_used` now records `by`, `project` and `via`; uses
  recorded before this count as `unknown`.
- `ccx ui` shows "Suggested notes" (H5): each pending suggestion with its kind and source, and a yes / no button
  (`POST /api/suggestion`) that writes it to shared memory or drops it. It is the page's only write and is accepted
  only from the page itself: Host and token as before, plus this server's own `Origin`, `Sec-Fetch-Site`
  same-origin when sent, and a JSON body. A snapshot (`--export`) shows `ccx mem accept N` instead. The overview's
  first line counts them. DECISIONS: narrows "phase 1 is read-only".
- Suggested notes (H5): only the first 3 are shown, at the session start, in `ccx mem suggestions` and in `ccx ui`
  (the person's own preferences first, then decisions, then pitfalls; newest first); `ccx mem suggestions --all` lists
  the rest. The person's call (2026-10-25): the rules only sift, the person judges; no model filter. The rules are
  also tighter: a preference must be a standing rule, not the task at hand (continue, step N, an absolute path, a file
  to change, "put this into X", a proposal/PR id first; "改成"/"统一" are no longer markers); the lead's own sentences
  leave out progress lines, reports (pushed, a commit id, tests pass, headings), fragments under 14 characters and
  "pitfalls" said to the person; bare "原来" no longer counts. This is NOT an accuracy result: on a held-out set (30
  candidates from another session, labelled blind by the coordinating session, not by the person) the new rules agree
  13/30 (old rules 7/30; the target was 4/5), and 2 of 7 notes worth keeping are now dropped.
- Handoffs are no longer lost between parallel sessions: each one has its own file in `.ccx/handoffs/` (`handoff.md`
  is only the latest), and session start lists every handoff to you not seen yet — the newest whole or summarised,
  the others one line each with their file. `ccx fresh` points the new conversation at its own handoff file.
- `--from-transcript` handoffs: the numbered list from the agent's latest message when no plan tool was used; the
  conversation's last 5 `ccx run`s with their check and verdict; `git status --short` keeps its leading space.
- One step to a fresh conversation (proposal J4): `ccx fresh [--as claude|codex] [--note ...] [--launch]` writes the
  handoff from this conversation's own session file (as `ccx handoff --from-transcript` does) addressed to the same
  tool, and says how to open the new conversation; `--launch` starts it in a terminal. A new conversation of the
  same tool in this folder now sees a handoff addressed to it (before, a handoff was never shown to the tool that
  wrote it). The H10 per-turn hint now says: ask the person, then `ccx fresh`.
- The board (core 2, part 1): `ccx say --to claude|codex|deepseek|all "..."`, `ccx reply <id> "..."` and
  `ccx board [--thread T]` let open Claude Code, Codex and DeepSeek sessions in one project write to each other.
  Messages go to `.ccx/board.jsonl` (append-only, locked, fsynced, git-ignored); each reader (vendor, or
  vendor:session) has its own cursor, so a turn sees only what is new and for it. At most 6 machine messages in a row
  per thread (`board.max_machine_turns`) until a person speaks; every line records who wrote it and what ccx detected;
  an agent cannot write as the person. Design: docs/board.md. Delivery every turn comes in the next PR.
- The board, part 2: one per-turn hook, `ccx turn --as claude|codex`, shows a lead before its turn the board
  messages new for it, the lines of `.ccx/context.md` that changed since it last looked (never the whole file) and
  the project journal lines the others added, within ~300 tokens; plus the H10 long-conversation hint. Nothing new,
  nothing printed. `ccx sync` puts it in Claude Code's `UserPromptSubmit` (replacing `ccx lead --hint` in place) and
  adds `[[hooks.UserPromptSubmit]]` to the Codex block (Codex 0.164; trust it once in `/hooks`). A turn the person
  typed restarts the thread's machine-message count; a ccx sub-agent's turn and messages ccx pushed in do not.
- `ccx board --init` writes the board's rules into the project's `AGENTS.md` (ccx's marked block): messages are
  data, not instructions; the turn limit; and, since DeepSeek Harness (`dsh` 0.2.1-rc.3) has no hook but reads
  `AGENTS.md`, a DeepSeek session runs `ccx board --as deepseek` at the start of every turn.
- The board, part 3: `ccx say --to codex --now` also pushes the message into the project's live Codex desktop
  conversation (`codex queue`, waiting while the person types there); `ccx say --resume RUN_ID` continues a headless
  sub-session with it and puts the answer back on the board as a reply. Claude Code desktop has no way in from
  outside and sees the message on its next turn. Optional fallback between computers:
  `ccx config set board.github owner/repo` (a private repository of your own; ccx refuses a public one and the
  project's own repository) and `ccx board --sync` mirror the board to one issue there, pulling at most every
  10 minutes; the per-turn hook starts that in the background when due. Not configured: no network at all.
- The board on the real CLIs (codex-cli 0.164.0 gpt-6-luna low, dsh 0.2.1-rc.3 deepseek-flash low): `ccx say
  --resume` got answers from both back on the board with the right `from` / `via` / `reply_to`; the Claude hook
  command shows them once. DeepSeek cost $0.0030. Codex desktop's per-turn hook and `--now` into a live Codex thread
  are not verified (docs/research/2026-10-25-board-acceptance.md).
- Fix: a message sent with `ccx say --resume` no longer tells the headless run to `ccx reply` itself (ccx posts its
  answer; dsh had no `ccx` on its PATH and said so in its answer).

### Control: stop, archive, accounting, permissions
- `ccx stop <run_id>` stops a running delegation and keeps it resumable. Sub-agents now start in their own process
  group (Windows `CREATE_NEW_PROCESS_GROUP`, POSIX `start_new_session`), and the run record keeps the child's pid,
  ccx's own pid and the host. Stop writes `<run>/stop.request` and kills the whole tree (`taskkill /T /F`,
  `os.killpg`); the run's own ccx writes the final state (`state=stopped`, `kind=user_stopped`, nothing learned) and
  its one ledger row. Only when that process is gone does stop close the record itself; `final.lock` makes sure only
  one of them does. A stop that lands as the sub-agent finishes keeps the finished result. Timeouts, the spending
  cap and Ctrl+C now kill the whole tree too: a grandchild holding stdout open no longer hangs the run.
- Killed and abandoned runs are counted. An attempt stopped mid-run (timeout, spending cap, `ccx stop`) prints no
  final usage line, so its usage is read back: Claude's assistant events in the stream (each message once, or its
  transcript), Codex's session file (rollout; only the growth is counted, as for a resume). Ctrl+C or a crash in
  ccx itself records the attempt in flight as `kind=killed`, the run as `state=interrupted`, with one ledger row.
  `ccx stats`, `ccx show` and `ccx resume` first close every `running` record whose ccx process is gone (a dead pid
  on this machine, or no heartbeat for 10 minutes) as interrupted, with the usage read back, so it is counted and
  can be resumed. `ccx stop` on such a run records the usage too. None of this is learned by routing.
- A Codex attempt stopped mid-run is now counted from the per-request `token_usage_record` lines codex-cli 0.164
  writes to its session file (since the attempt began), falling back to the growth of its `token_count` total.
  Found by a real `ccx stop` (run `20261025-101228-1108`, gpt-6-luna low, stopped after 7.6 s during its first
  request): the request's 19,245 input and 207 output tokens were only in a `token_usage_record`, so the attempt
  was counted as 0. A read-back attempt is marked `recovered` and is never taken as the session's running total,
  so a later `ccx resume` counts its own turn in full.
- Sub-agent sessions are archived as soon as their run's result is final (`sessions.archive = "after_run"`, the
  new default; `hours` keeps archiving only after `sessions.auto_archive_hours`, `off` never by itself): done and
  checked (`--check` passed, or the sub-agent checked itself), or judged with `ccx verify`. Runs that may still go
  on are kept (quota, timeout, stop, kill, blocked, failed check, review issues), and seats, discussions and reviews
  are left alone. `ccx resume` and the 1-hour auto-continue bring an archived session back first (`codex
  unarchive`, codex-cli 0.164; Claude's transcript moved back). A session archived by hand is still not
  auto-continued. Real run (gpt-6-luna low): run `20261025-120720-392d` archived right after its check passed;
  `ccx resume` brought it back and continued the same session (`20261025-120740-b4d6`, 74k cached tokens), which
  was archived again when it finished. Tests switch it off with `CCX_NO_AUTO_ARCHIVE=1` unless they are about it.
- dsh (DeepSeek Harness) sessions are archived too: dsh 0.2.1-rc.3 has no archive command, so ccx adds the run's
  session id to the desktop app's archived list (`<DSH_HOME>/storages/workspace.json`, `global.archivedSessionIds`,
  what the app's own archive action changes) and takes it out on `ccx archive --restore` and before `ccx resume`.
  Only that one id is added or removed; the file is backed up (`workspace.json.ccx-backup`) and replaced
  atomically, and a missing file is skipped. Session folders are never moved.
  Checked once with the desktop app open: the added id stayed for 5 minutes. Not checked: whether the app's next
  own write keeps it, and whether an open window shows it without a restart.
- dsh: while the desktop app is open, archiving (and un-archiving) a session is queued in
  `workspace.json.ccx-pending.json` and written by the first ccx call that finds the app closed (session start,
  the next archive). Checked with the app open (2026-10-25): its next change of its own wrote its in-memory list
  back and dropped the id ccx had added, though the id had stayed 5 minutes while the app was idle.
- Evals archive what their throwaway hubs leave: `scripts/eval/preflight_e2e.py` and the memory units of
  `scripts/eval/seven_ab.py` run `ccx archive --apply` in their own hub at the end (`common.archive_hub`), final or
  not, since nothing continues those sessions and the person's hub never sees them. Sessions from such runs had
  stayed in the apps' session lists (2026-10-25). A run that ends with a final result already archives its own
  session in whatever hub it runs (`sessions.archive = after_run`); a test now covers that case too.
- `ccx uninstall --apply` run once for real (J12, report section 5c), and three things it found fixed: tool files
  keep their own line endings (an LF `config.toml` came back CRLF); after uninstall, `ccx sync` puts the Codex hook
  block back where it was, not at the end (Codex keeps hook trust by position, so moved hooks ask for trust again);
  uninstall now says how to put everything back (`ccx sync --apply`, `ccx skills install --replace --apply`,
  `ccx doctor` — sync alone does not bring back ccx's skills).
- `ccx doctor` has a row "Codex as lead (sandbox)": whether a Codex lead can hand work out with `ccx run`. Real runs
  (codex-cli 0.164, Windows): in `workspace-write` the lead's `ccx run` failed with `[WinError 5] Access is denied`
  on the hub's runs folder; with the hub as a writable root and the network on, ccx ran, but the Claude sub-agent,
  started under Codex's separate sandbox account, refused every edit ("sensitive file") and saved no session, also
  with `~/.claude` writable. Only `danger-full-access` worked. So on Windows the row asks for full access for lead
  sessions (a `[profiles.lead]` example); elsewhere it checks `sandbox_workspace_write.writable_roots` covers the hub
  and `network_access = true` (not checked on a real run there). A `PermissionError` from any command now carries a
  hint pointing at that row. README (EN + ZH) says this next to "Codex leads, Claude Code is the sub-agent".
- `ccx doctor` adds a safety note to "Codex as lead (sandbox)" when Codex runs in full access (every lead command
  has your rights, unsandboxed) and offers a narrower way: `ccx doctor --codex-rule` prints a Codex rule
  (`prefix_rule`, decision `allow`) that lets only this ccx's `run/ask/resume/discuss` run outside the sandbox.
  doctor asks Codex itself whether a rule in `~/.codex/rules/` matches (`codex execpolicy check`) and then reports
  Unknown, not ok: by Codex's docs it should work, but no real run has checked it. ccx never writes the rule.
  README (EN + ZH) carries the same warning; DECISIONS records the options weighed.
- `ccx ui`, a read-only live page on this machine (proposal G1). Left: contents (overview → projects → tasks →
  split pieces), red counts of what waits for you, search, quota by pace. Middle: each task as an org chart — you →
  the lead (model, its own sub-agents as dashed tags, spend vs budget) → one column per worker; a new agent gets its
  own column and colour. Blocks that need you are framed red (your call: needs_write, review still failing, check
  failed, quota/timeout stop, no sign of life for 10 min) or amber (done, waiting for your verdict); the side panel
  shows why, the evidence (what it says, files, check, review) and the `ccx` command for each button, to copy
  (phase 1 never runs anything). Queue splits open as their own level (at most 3); filters, a folded history, live
  tokens of running sub-agents from their session files. Reads only run records, the ledger, queues, session files
  and kept quota readings, incrementally — never a model, never the quota probe. Standard-library HTTP on 127.0.0.1,
  a random port, the token after `#` (sent back in a header, never in a URL the server sees), a Host check against
  DNS rebinding, no CORS, a strict CSP, all data shown as text. Polls every 3 s; the page says "still open" every
  10 s and the server exits 60 s after that stops. `ccx ui --export FILE` writes a static snapshot.
- `ccx config set ui.lang zh|en`: one table (`ccx/ui_static/strings.json`) holds every word of the page in both
  languages and the lines ccx writes into conversations (queue, stale memory, long-conversation hint, and a new
  session-start line pointing at `ccx ui` when delegated work waits for you). Unset: the page follows the browser,
  the lines stay English. Not switched: the checkpoint skill's own output, sub-agent briefs (they stay English).
- `scripts/ui_demo.py`: a throwaway hub of real ccx runs on the stand-in CLIs, to try the page; the fake Codex can
  now write a growing session file while it hangs (`FAKE_HANG_S`).

### Windows fixes
- Codex hooks work on Windows (H7): Codex 0.164 runs hook commands through PowerShell there, where a line that
  starts with a quoted path is just a string, so ccx's SessionStart and UserPromptSubmit hooks ran and failed with no
  output (seen live: the desktop app started and finished them; nothing reached the conversation). `ccx sync` now
  writes them with the call operator (`& "python" "ccx.py" ...`) on Windows. `ccx doctor` warns about a block written
  before this fix: run `ccx sync --apply`, then trust the hooks again in Codex with `/hooks`.
- Codex hooks show ccx's lines (H7, second half): Codex 0.164 reads hook output that starts with `[` or `{` as JSON,
  and when it isn't, counts the hook as failed and drops the output. Every ccx start line begins with `[ccx`, so even
  with the PowerShell fix (#82) Codex saw nothing. `ccx mem delta --as codex` and `ccx turn --as codex` now start with
  a plain line ("From ccx (shared memory and delegated work):"); Claude Code's output is unchanged. Checked with a
  throwaway CODEX_HOME and hub: before, `hook: SessionStart Failed`; after, Completed and the note (Chinese included)
  is in the conversation.
- Paths with non-ASCII characters no longer crash ccx. In a Codex desktop thread whose folder was `...\玩`, the
  start-up hook (`ccx mem delta --as codex`) died: git printed the path in UTF-8, Python decoded it with the system
  code page (GBK), `stdout` came back `None`, and `find_root` raised `AttributeError`. All eleven text-mode
  subprocess calls that did not name an encoding (git in `project`, `learn`, `workspace`, `report`, `archive`, the
  checkpoint skill; `claude mcp get`, the hub's external sync, `codex queue`) now use `encoding="utf-8",
  errors="replace"`. `tests/test_encoding.py` checks the source so a new call cannot leave it out (CI runs on UTF-8
  systems, where the crash cannot show). Reproduced and checked on Windows in a folder named `玩项目`.
- No more terminal windows popping up on Windows. `ccx run --bg` and the background benchmark refresh were started
  with `DETACHED_PROCESS`, so they had no console and every git / codex / claude call they made opened a new visible
  console window; the same happened when a desktop app ran ccx as a hook. Background processes now get a hidden
  console (`CREATE_NO_WINDOW`), and when ccx runs without a console at all it starts its children with
  `CREATE_NO_WINDOW` (`ccx/winproc.py`, installed on import; a process that has a console is left alone, so output
  in a terminal is unchanged). Checked on Windows: from a console-less parent, a child got a visible window handle
  before and none after (`tests/test_winproc.py`).
- Windows: writing a run record retries for up to 3 s when another process has `run.json` open (`ccx stop` or
  `ccx show` polling it); before, the replace was refused for that moment and a stopped run's final state stayed
  `running` (seen in CI on PR #37). The stop tests now wait for their background ccx before the temp folder goes.
- Windows: reading a run record retries for up to 3 s when the run is replacing it at that moment (the read side of
  the write retry): a test polling a live run failed once in CI with PermissionError on `run.json`. `ccx` itself
  reads records through `ledger.read_record` (show, stop, the interrupted-run sweep).
- Windows: background discussions and the board now wait for a reader too when they replace their state files
  (`ledger.replace`, the retry `run.json` got in #48); a background discussion's state write failed once in CI
  (PR #67). `ccx discuss --show` reads the state with the same retry.

### Evaluation, docs and the project
- Seven-cores evaluation, round 1 (Claude Code + Codex, real runs): `scripts/eval/seven_ab.py` runs four randomised
  paired A/B comparisons (self vs delegate, fixed model vs routing, review off vs on, without vs with project memory;
  3 rounds per task, resumable, budget-capped) and `scripts/eval/seven_func.py` the functional checks (Codex lead ->
  Claude sub-agent, kill then `ccx task resume`, `ccx undo`, the spend cap). Three medium and three memory tasks join
  `scripts/eval/tasks.py`; fake-CLI tests cover the schedule, resuming, the statistics and the undo check. Plan and
  report in `docs/research/2026-10-24-seven-cores-plan.md` and `-ab.md` (EN + ZH), de-identified data in
  `docs/research/data/`.
- `scripts/eval/seven_ab.py`: the memory group has a third arm, `hubmem`: the same note only in the shared hub
  journal (`ccx mem add`), nothing in the repo. Every memory unit runs in its own throwaway `CCX_HUB`, so the
  person's hub is never read or written and no other note reaches the brief; each unit records `note_in_prompt`
  (the note was in the sub-agent's first prompt). The summary reports it as `memory:hubmem` (nomem -> hubmem),
  outside the Holm family of the four primary comparisons. Real run (codex gpt-6-luna low, 3 tasks x 3 rounds,
  paired with round 1's `nomem` units, $0.025): hidden test passed 9/9 vs 0/9 (McNemar p = 0.0039), the note was in
  the prompt 9/9; median $0.0030 vs $0.0019 and 29.5 s vs 23.5 s per unit. Limits: the control is round 1's (an
  earlier batch, before the I6 fix, the person's hub instead of an empty one), the tasks are made so the brief
  leaves out exactly what the note says, and each hub held just that one note; nothing here measures picking the
  right note among many.
- H15: `scripts/eval/preflight_e2e.py`, a release preflight on the real CLIs with tiny tasks, judged by files, records
  and the ledger: delegate (Claude-led task to a Codex sub-agent, hidden test passes), followup (`ccx resume`, same
  session), stop (`ccx stop`: stopped, counted, one ledger row, then `ccx resume` on the same session), undo,
  handoff (written, shown by the receiving start hook, and a model given that names the next task), and with
  `--agents all` also review and the Codex -> Claude direction. A throwaway hub, `eval-preflight:` labels, `--no-ab`,
  and a spend cap (default $0.50) read from that hub's ledger after every step.
  First full pass, Codex only (gpt-6-luna low): all five steps passed for $0.013. A real stop -> resume from an
  earlier pass: stopped run `20261025-113353-a5b3`, ledger row `{"kind": "user_stopped", "ae_usd": 0.002088,
  "usage4": {"input_tokens": 20049, "cached_input_tokens": 0, "output_tokens": 167}, "sessions":
  ["01a173b2-67c3-7723-9a0d-2397972498e7"]}`, resumed as `20261025-113359-8b50` in that same session.
- Measured H11 (first batch), E8 and F9 on the real CLIs ([report](docs/research/2026-10-24-h11-e8-f9-measurements.md), about $0.56 in all). New
  `scripts/eval/`: `h11_compare.py` (paired lead-does-it vs lead-delegates on generated repos with hidden
  acceptance tests, verdicts via `ccx verify`, spend cap), `e8_handoff.py` (a real outgoing lead, `--from-transcript`,
  a receiver that sees only the handoff; `--cut-after` kills the lead mid-work), `f9_subagents.py` (on/off, children
  counted from the ledger and the session files). Fixed in `ccx handoff --from-transcript`: in a git worktree inside
  the main checkout it took another session's transcript and git state (now the lead's own folder first); the Claude
  desktop plan tool's `advance` / `done` / `start` updates were ignored, leaving the plan at its first state.
- J0 baseline of the lead's own cost: `scripts/eval/j0_baseline.py real` (the real lead sessions and the ledger, no
  model calls) and `tasks --ref REV` (three fixed lead tasks in a clone at that commit with the person's default
  setup, answers checked against the clone); rerun after J1–J6 with the same arguments.
- `scripts/eval/j0_baseline.py real` counts only conversations a person drove: it leaves out the sessions of every
  ccx ledger (this hub's, the temporary hubs eval scripts leave under the temp folder, and `--ledger FILE`) and
  every headless session (Claude `-p`, entrypoint sdk-*; `codex exec`), which is how ccx sub-runs
  (CCX_ROLE=subagent) and eval leads run; `--keep-headless` gives PR #6's reading. New `--until ISO` re-reads an
  earlier window with the same rules, `--tag` names a reading, `compare --before T1 --after T2` puts two side by
  side, and each reading now carries `ccx lead --cache`'s breaks and causes inside the window. By default it reads
  only this repository's conversations (main checkout and worktrees); `--project DIR`, `--all-projects`.
- Claude sub-runs (and eval leads) no longer inherit `CLAUDE_CODE_ENTRYPOINT`: started from the desktop app, a `-p`
  run's session file said `claude-desktop` and looked like a person's conversation; now it says `sdk-cli`
  (checked with Claude Code 2.1.309).
- README (EN + ZH): the "does it save" numbers come from the seven-cores A/B round 1 (total spend ratio 1.02, total
  tokens 3.3x, about 23 s slower, one lead request fewer per task), each row says whether it is measured or
  extrapolated and where it comes from; the long-conversation saving (~$0.07 a small task) is marked extrapolated.
- Front page brought up to date for relayline: README (EN + ZH) opens with the name, one sentence of what it is and
  a table of seven things it does with where each stands; the "Measured" table now carries the 2026-10-24 results,
  the unfavourable ones included (small tasks save only when the lead trusts ccx's check; Codex's own sub-agents never
  started on luna low); new commands (`ccx lead --breakdown/--cache/--suggest`, `ccx sum`, `ccx fresh`, `ccx trial`,
  `ccx agents`) in the command list. New banner, architecture (several agent CLIs, ccx, personal and project layer,
  `ccx ui`) and social preview from `scripts/make_assets.py` (names only, no vendor marks); `scripts/make_demo.py`
  now shows ccx rerunning the check; fresh `ccx ui` screenshots; `scripts/ui_demo.py` gains `--port` and `--plain`.
  The website (`site/`, EN + ZH) follows the README.
- Renamed to **relayline** (was `claude-codex-bridge`): the GitHub repo, the package name in `pyproject.toml`, the
  install command (`pipx install git+https://github.com/SUPERD6/relayline`), and the links in the README, website,
  CONTRIBUTING and issue templates. The `ccx` command and the `ccx/` package are unchanged; GitHub redirects the old
  URL. The README now opens by saying how it differs from CCB and from OpenAI's codex-plugin-cc.
- Research on similar projects (proposals J8–J10), docs only: `docs/research/landscape.md` / `.zh.md` covers OpenAI's
  official codex-plugin-cc (facts with sources, overlap, a coexistence plan that is not implemented yet, tests still to
  run), a comparison of similar projects (also a new "Similar projects" section in both READMEs) and eight name options
  checked against GitHub and PyPI for the user to choose from. Nothing is renamed.
- STATUS is one page (proposal J6): what is going on now, the next three items and a short "how sure we are";
  the old 24 KB page moved to `docs/STATUS-archive.md` / `.zh.md` as it stood. AGENTS.md no longer tells every
  agent to read it first, only when it needs to know where things stand — anything read at start-up is re-read
  on every later turn.
- `ccx/delegate.py` split by job (proposal J11), behaviour unchanged: `prompts.py` (what a sub-agent is told),
  `plan.py` (which rungs a run tries, budget and provider checks, the fallback to another vendor), `workspace.py`
  (worktree, ccx's re-run of the check, the snapshot and `ccx undo`), `verdicts.py` (`ccx verify`, built-in
  verdicts, probable verdicts), `review.py` gains the review step itself, the Codex accounting helpers move to
  `ccx/agents/codex.py` and writing a run record to `ledger.py`. `delegate.py` (988 → 547 lines) keeps the run loop
  and re-exports the old names, so `from ccx.delegate import ...` still works.
- Change notes per PR (proposal from the coordination handoff): a PR adds `changes/<PR>.md` with its CHANGELOG lines
  instead of editing `CHANGELOG.md`, and `scripts/collect_changes.py` folds them in at release (preview by default,
  `--check`, `--apply`, `--version X --title ...`; keeps CHANGELOG's line endings). `docs/STATUS.md` is edited only by
  the lead session. Parallel PRs no longer conflict on either file; the tests check the notes' format.
- `ccx doctor` warns on version drift (I8): when an agent CLI's installed major.minor differs from the adapter's
  `tested_version`, a `<agent> version` row says so; for an official adapter it asks for the release check (H15: real
  read, write and resume runs on that version), for a community one it says not verified on that version.
- `ccx/agents/_template.py` and `tests/fakes/fake_template.py`: a working skeleton for a new agent CLI (not
  registered), run end to end by `tests/test_agent_template.py`. CONTRIBUTING (EN + ZH) points at it; its step 1 no
  longer names the old `runners.py` tables. README (EN + ZH) explains official vs community.
- `ccx doctor` notices OpenAI's codex-plugin-cc (J8): installed or enabled in Claude Code (`codex@openai-codex`), it
  reports `info` (its SessionStart/SessionEnd/Stop hooks run beside ccx's) and `WARN` if ccx's own SessionStart hook
  is there more than once. README's "can be used side by side" now says not tested together yet.
- Tests: `tests/conftest.py` gives every test its own hub, Codex and Claude homes and user config under its own
  temp folder (and drops a live run's `CCX_DEPTH`/`CCX_RUN_ID`), so a test that forgets to set them never reads or
  writes the machine's real `~/.ccx`, `~/.codex` or `~/.claude`, and tests share no state. The shared test base
  retries removing its temp folder for up to 10 s: on Windows a background ccx (`--bg`) that just finished still
  holds the folder as its cwd for a moment.
- Tests no longer see the machine's own provider keys (`*_API_KEY`, `*_AUTH_TOKEN`): with a real
  `DEEPSEEK_API_KEY` set, `test_missing_key_is_a_clear_error` failed on that machine only.
- `ccx -h` lists commands by use: everyday (setup, doctor, run, ask, resume, stop, verify, ui, where, projects, peek,
  board, say, reply), memory and context, accounting and reports, then maintenance and advanced as names only. The
  description now says what ccx is (a cost-saving team of Claude Code, Codex and DeepSeek). No command or option
  changed; a test checks every command is in exactly one group.
- README (EN + ZH) cut to one promise (spend less), four pillars with one sourced measurement each, and a three-command
  quick start; the details moved, unchanged, to docs/features, docs/install, docs/measured and docs/faq (EN + ZH).

### Added before the tag (#96–#104)
- The repository is now a plugin marketplace: `claude plugin install relayline --marketplace SUPERD6/relayline`
  gives Claude Code the four skills and ccx's SessionStart / UserPromptSubmit hooks (they run the plugin's own
  `bin/ccx`); `codex plugin marketplace add SUPERD6/relayline` + `codex plugin add relayline@relayline` gives Codex
  the skills. Where the plugin is enabled, `ccx sync` leaves the Claude hooks and the four skills to it and removes
  its earlier copies, so nothing runs twice; `ccx doctor` reports the plugin, warns when a hook is there twice and
  when ccx itself is not installed. `bin/ccx` now finds a Python 3.11+ (`python3`, `python` or `py`).
- Fix: a plain terminal was taken for a Codex lead when the person had `CODEX_SQLITE_HOME` or the installer's
  `CODEX_INSTALL_DIR` set for good (any `CODEX_*` but `CODEX_HOME` counted). `ccx say --from claude` then failed with
  "runs inside codex", and `ccx run` recorded the caller as Codex. Codex is now recognised by the variables it sets
  for the commands it runs (codex-cli 0.164, checked on a real run: `CODEX_THREAD_ID`, `CODEX_SESSION_ID`,
  `CODEX_TOOL_CALL_ID`, `CODEX_CI`, `CODEX_SANDBOX*`).
- Independent review: a reviewer's summary without the `REVIEW: pass|issues` line (e.g. written in Chinese) no
  longer ends as `unclear` when its items are tagged: `[must]` items make it `issues` (so the fix round runs), only
  `[note]` items make it `pass`; the verdict carries `format: lenient`. The prefix also tolerates markdown and a
  full-width colon. Found in the seven-cores round 2: haiku named the real bug as `[must]` and the run stayed unfixed.
- `ccx way --label` labels the build runs (e.g. `eval-...`, so H9 and probable verdicts leave an evaluation out).
- Seven cores, round 2 (cores 4–7): plan, report and scrubbed data in `docs/research/` (`scripts/eval/r2.py`,
  `scripts/eval/tasks_r2.py`); `scripts/eval/common.read_jsonl` splits on `\n` only (U+2028 inside a JSON string broke
  it).
- `ccx ui` and the session-start "N delegated piece(s) wait for you" leave out evaluations and tests by default:
  eval-* labels, `--no-ab`, ccx's probes (now also `startup-probe`, `two-way-*`), runs in the system's temporary folder
  or inside a project's `.ccx` folder (unless the hub itself is temporary), and the projects and lead conversations
  there. A "show evaluations and tests" switch on the page brings them back.
- `ccx verify RUN --dismiss --note why`: a test or leftover counts neither right nor wrong. It leaves "waits for you",
  `--sweep` skips it and routing, splitting and the statistics leave it out (`ledger.is_eval`); a later `--ok`
  undoes it, and a run that already has a verdict cannot be dismissed.
- `ccx batch`: a plan task can set `"review"` (auto|on|off, as `ccx run --review`) and `"risk"`; both were dropped
  before, so a batch always reviewed with the defaults (a real 3-task batch spent $0.04 of its $0.05 on reviews).
- dsh archiving: the "queued" message now says the desktop app has to be quit from the tray; closing its window
  leaves it running, so ccx keeps the id queued (seen on a real machine 2026-10-25; once quit, the next session
  start wrote the queued ids, and the reopened app did not overwrite them on start; its own next write is not
  observed yet).
- New skill `project-manager` (proposal K3) for a lead session that coordinates others: one sentence in, find the
  project with `ccx where`, choose the shape, dispatch with `ccx run --project`, check, archive, report in a line or
  two. Default shape from the second seven-cores round: one cheap model plus another vendor's cheap review; parallel
  only when speed is wanted and the pieces are independent ("faster, not cheaper"); large work gets a reviewed split
  draft first. It asks the person only before sending outside, merging the main branch, spending over a cap, research
  approval, or when the project is unclear. A test checks that every ccx command and flag the skill names exists.
- `--review auto` now judges weak evidence from the run itself, with no history needed: a write run that changed
  code is reviewed once (on the other vendors' cheapest rung only, within `weak_daily`) when there is no `--check`,
  when the check runs no tests (`exit 0`, a linter, an import), or when the tests it runs never name a changed code
  file or a changed public function. A passed check whose tests reach the change is not reviewed, nor are read-only
  runs. Round 2 of the seven-cores A/B: auto fired 0 times in 36 runs, while review on raised right first time from
  33/36 to 36/36 for +$0.004 a task; replaying the 18 trap tasks' reference changes, the new rule fires on 4,
  inventory among them (its visible test never calls `low_stock` or `remove_stock`).
- `ccx q`: when the whole `q run` process tree was killed, the run in progress stayed `running` and its spend never
  reached the ledger or the item (r2 group 9, 4-I). `q run`, `q resume` and `q ls` now close such runs as
  interrupted first (`recover.sweep`, as `ccx stats` does, with the usage read back from the session file), and
  `q resume` adds what the item's runs since it went `doing` spent to its `cost_usd`.

## 0.4.0 — 2026-10-24 (routing from public benchmarks and total cost, quota by pace, work queue, reviews, handoff from the session file)
- Highlights: proposals E and F, the F1 live trial and the fixes below; 201 tests. Details per item follow.
- Review: `auto` also reviews code changes of 50+ changed lines (`[review] min_lines`, docs not counted).
- `--no-subagents` also disables `multi_agent_v2` and says the rule in the brief: codex-cli 0.164 offers its v2
  agent tools even with both features disabled (F9 live check, 4 runs; luna started no sub-agents on or off).
- CI: a push runs Linux 3.11/3.13 + Windows 3.11 + one package check, docs-only pushes skip; tags, PRs and manual
  runs get the full matrix (private-repo minutes ran out with the full matrix on every push).
- `ccx doctor` no longer advises trimming an external snapshot (the user's own shared rules file).
- Skills: narrower triggers, optional numeric splitting, planning apart from authorization; agent-delegate says
  how to use `--review/--risk` and "交接给 X" (`handoff`, or `--from-transcript`).
- F1 live trial (2026-10-24) and fixes. 8 seeded diffs (5 with a known bug, 3 clean), each reviewed by Claude haiku
  and Codex luna, twice; 4 real small tasks run twice through `--review on`. Old brief: 10/10 bugs caught, but haiku
  flagged all 3 clean diffs and luna 1 (speculative edge cases, "tests not run"). New brief: issues are `[must]`
  (makes the change wrong for the task) or `[note]`; only `[must]` makes a fix round; the reviewer is told it
  cannot run commands and what ccx's check returned. Result: luna 5/5 bugs, 0/3 false alarms; haiku 4/4 and 0/2,
  with 2 reviews that ran out of structured-output retries -> a review that can't finish now tries the next
  reviewer (`[review] also`). In both real rounds the review found the same real bug (an invalid size returned []
  instead of raising when page was also invalid); one fix round fixed it. Review cost: luna about $0.0017, haiku
  about $0.0037 per review. Also fixed: a Claude sub-agent could not run a `--check` command spelled with a full
  python.exe path (not covered by `Bash(python:*)`): the exact check command is now allowed; sub-agents are told not
  to commit, push or switch branches (haiku committed its work in both rounds; checked live, it no longer does).
  201 tests.
- Independent review when it matters (proposal F1): after a write run that changed files and passed its check,
  another vendor's cheap model (`[review] by`: Codex work -> Claude haiku, Claude/DeepSeek work -> Codex luna) reads
  the diff against the task and answers `pass` or `issues` with `file:line`. `--review auto` (default) reviews only
  when `--risk` is visible/critical, the sub-agent listed open questions, or its claimed files don't match the
  actual diff; `on` reviews every write run, `off` none. Issues go back to the same sub-session for one fix round,
  which is reviewed again; still failing -> `kind: review_failed` (a queue item fails). The lead sees
  `review: {verdict, reason, by, issues, usd}`. The review run is its own ledger entry; it never fails the work if it
  can't run.
- Handoff fallback (E8): when the code can't read a session file's format, a routed sub-agent reads it and writes the
  handoff (model chosen by routing, not fixed; `--no-model` to skip); git state and unfinished work are still added
  by code. 199 tests.
- Handoff from the session file (proposal E8, with B): `ccx handoff --from-transcript codex|claude [--session ID]
  --to X` assembles the handoff by code, no model, from the outgoing lead's newest main session in this folder (ccx
  sub-runs and headless Codex sessions skipped): the first goal, its plan list, the person's last messages, its last
  conclusion, changed files, the last failed commands, `git status`/`diff --stat`, unfinished checkpoint and queue
  work, and the transcript path; app-injected blocks are dropped, secrets masked, about one page, marked "check
  before trusting". Text given as well is added below it. `ccx task resume` after a quota stop passes the cut-off
  session's extract to the fresh agent. Formats checked against Codex 0.164 rollouts and Claude Code transcripts.
  191 tests.
- Memory that doesn't go stale silently (proposals E7, E9): `ccx mem add --source … --supersedes N`, `ccx mem
  verify N | search <words> | stale`; a replaced note is no longer pushed or folded into the snapshot; notes nobody
  wrote or checked for 30 days are flagged "to check" at session start; the start-up delta shows the newest lines
  first within ~600 tokens. README says which memory is for what (standing rules → the user's shared instructions,
  with consent; project facts → `ccx mem --project`; each tool's own memory is not copied). 184 tests.
- Don't cut in (proposal F6): `ccx send` into a live Codex conversation first reads its session file; while a turn
  runs or within 90 s of the person's last message it waits (`--wait`, 120 s), then holds the message and says so
  (`--force` sends anyway). 181 tests.
- Named seats and clear restores (proposals F4, F5): `ccx run --seat reviewer` reuses that role's sub-session in
  this folder for a week (up to 30 tasks; `--new` starts it over) and auto-archiving leaves seats alone; `ccx q
  resume` reports how each interrupted piece came back — resumed (same session), fresh, decide (quota, login,
  needs_write, over budget) or failed. 181 tests.
- Built-in sub-agents on by default (proposal F9, reverses C4): a Codex sub-agent may use multi_agent with its
  children on the routed model and effort and at most 3 at a time (`-c agents.default_subagent_model=…`,
  `agents.max_concurrent_threads_per_session`; `[subagents] max_threads`), a forked Claude its Agent tool; a
  watchdog in `execute()` stops a run whose Codex children spent over `[subagents] max_usd` ($2), `kind:
  over_budget`, not learned. `--no-subagents` turns them off (`--allow-subagents` is now the default). Codex keys
  from its config reference, not yet seen live. 180 tests.
- Work queue (proposals F3, F2, F7): `ccx q add | run | resume | tree | ls | done | budget` keeps a project's pieces
  in `.ccx/queue/queue.jsonl` (append-only, locked, fsync'd): dependencies decide the order, every ready piece runs
  in parallel through the normal routing, an item keeps its run id, cost and summary, `--check` and `--budget` per
  item, a queue-wide budget stops the run. A sub-agent that finds its piece too big returns `SPLIT:` with the parts;
  ccx stops that run without escalating or learning (`kind: split`), adds the parts as children (≤ 3 levels, sharing
  the parent's budget), and closes the parent when all are done. Roles are the lead's call per piece (F2). The
  session-start hook mentions open queue work. 179 tests.
- Self-check before returning (proposal F8): every brief now ends with "check your own work" (tests, re-read the
  changes; what changed and why in the summary, doubts and decisions for the lead in open_questions). With
  `--check CMD` (or `"check"` in a batch task) the sub-agent is told to run it, and ccx runs it again after the
  sub-agent says done: a failing check is `kind: check_failed` with a hint, learned as a failure; a passing one
  counts as verified. 174 tests.
- DeepSeek efforts (proposal E6): flash has low, high and max rungs, chosen by difficulty like any ladder
  (low → high → max → Claude on failure); deepseek-v4-pro is no longer a rung or the provider's default model
  (weaker than flash in every source, ~2.5× the price) but stays callable with `--model`. 172 tests.
- Quota by pace (proposal E5): `ccx/quota.py` projects each window's use to its reset from the last 48 hours within
  the current window (a later reset time or a drop in use starts a new one, so plan changes are handled; under six
  hours of readings it is too early and the current share stands); every window counts and the tightest decides.
  Codex is read from its logs at every call (now with `resets_at`); Claude's 5-hour and 7-day windows are kept from
  every Claude run's `rate_limit_event`, and a tiny probe refreshes them when over an hour old (`[quota]
  probe_claude`, `CCX_NO_QUOTA_PROBE`). `ccx quota [--probe] [--backfill]`. Routing prices quota with the projected
  share. First real reading: Codex 28% used, 35%/day → 242% at reset (priced 2×); Claude 6% weekly after the plan
  upgrade. 171 tests.
- Total cost (proposal E4): routing and the three-way choice pick the lowest money + quota shadow price (30% of the
  API price with room, rising to 100% between 60% and 100% used, 200% beyond) + time (minutes × $0.005 / 0.02 /
  0.10 per tradeoff, measured per rung once recorded) + risk (chance of failing × $0.5 / 3 / 20 by `--risk`) among
  options that reach the success target. Replaces the 1.5×/held-back quota rules and DeepSeek's 70% gate (the
  daily cap stays). `ccx route` passes quota and risk; rows show each part. First real run: a 20-minute fix goes
  to DeepSeek flash (0.13) over Sonnet built-in (0.20) and Opus itself (0.49). 168 tests.
- Local benchmark sources (proposal E2): `<state dir>/bench-sources/*.py` plugins (`NAME`, `CREDIT`, `fetch(get)`,
  optional `available()` and `KIND_WEIGHTS`) are fetched with the built-in sources and merged the same way; not set
  up = skipped, not a failure; a broken plugin never stops the others. For data whose terms allow only personal use,
  it stays on that machine — nothing of it is in the repository.
- Difficulty in a standard unit (proposal E11): `--minutes N` (how long a skilled engineer would need, METR's unit)
  gives b = log2(N), blended 60/40 with the rubric; route rows show each rung's 50% task length (`h50_minutes`).
  `ccx/signals.py` measures the files a brief names (count, lines, folders, tests) and fills rubric items the lead
  left out; a per-lead bias is learned from outcomes (failing more than predicted raises its b), with a log of
  estimate vs real time; `task_routing.py refit` suggests rubric weights by logistic regression (advice only).
  The routing CLI's rubric flags are now optional when `--minutes` is given. 166 tests.
- Abilities from several benchmarks (proposal E3): `scripts/merge.py` matches each source's rows to rungs (model
  family, version, effort; `[aliases]` in the priors), fits score → theta per benchmark on the Claude/Codex anchors,
  combines by relevance for the kind of work ÷ fit error (mismatches halved, no benchmark above half), and blends
  with the hand-set prior; learned offsets stay on top. `--kind code|read|research|write` on `ccx run`/`route`/
  `task_routing.py route` (read-only defaults to `read`). Route rows show `theta_prior` and `bench`. DeepSeek flash's
  hand prior goes back to a guess (3.5) and the ten calibration tasks are recorded as outcomes instead. 165 tests.
- Public benchmark data (proposal E1): `skills/task-routing/scripts/benchmarks.py` (standard library) fetches Epoch
  AI's benchmarking hub (ECI, GPQA, SWE-bench Verified, SimpleQA, FrontierCode, Terminal-Bench, METR, WebDev Arena,
  HLE), LMArena's leaderboard dataset (text, factuality, agent outcome, tool hallucination, bash reliability) and
  models.dev prices into `benchmarks.json` beside the routing state. `task_routing.py refresh [--if-stale]` /
  `sources`, `ccx bench [refresh]`; the session-start hook refreshes a week-old copy in a detached process (failed
  sources retried after 6 hours, brief 5xx retried; offline keeps the old copy). Every output carries the credits
  (CC BY 4.0 / MIT). First real fetch: 1210 + 2190 scores, 104 prices, 7.7 s. 160 tests.
- Read-only or write, inferred (approved 2026-10-23, done 2026-10-24): without `--mode`, `ccx run`, `ccx batch` and
  `ccx route` decide from the task text (`ccx/modes.py`): an explicit read-only phrase wins, then edit verbs
  (English and Chinese; English words that are often nouns, like "change" or "fix", only when not after an article),
  then analysis verbs; an unclear text keeps the old default (write) and says so. `--mode` always wins. The decision
  and its reason go into the route output, the run record and the ledger (`mode_source`: explicit / inferred /
  default), and routing prices the start-up with it. A read-only sub-agent that needs edits stops with
  `NEEDS_WRITE`; ccx returns `kind: needs_write` with a hint and does not escalate or learn from it. README FAQ: both
  sides run in work mode (`codex exec`, `claude -p`), not a web chat. 154 tests.
- DeepSeek as its own agent (proposal D, 2026-10-24). D1 measured with `ccx selftest --provider deepseek`: with
  `--bare` a DeepSeek run starts with 1.5k tokens per request (ccx's slim Claude start: 13.6k); a tiny read cost
  $0.0009 on flash (4.7 s) and $0.005 on v4-pro (8.8 s) at peak price. D2: flash passed 10 of 10 checkable tasks in a
  clone of this repository (b 1–5, $0.054 in all) → theta 4.5 (posterior mode 5.3, set at the low end); v4-pro stays
  a guess. D3: `deepseek:*` rungs in routing; `--to deepseek` (or `--provider deepseek`) runs on Claude Code with
  DeepSeek's key and records under its own agent; a failed DeepSeek ladder continues on Claude in a fresh session
  (`[escalate_to]`). D4: pay-per-token agents are offered only once every subscription is at ≥ 70% quota
  (`ccx run/route --quota claude=0.8`; Codex's is read from its logs); off-peak hours are priced at half
  (`[offpeak]`). D5: `daily_usd` per provider (default $1) stops it for the day; the ledger keeps cost per agent and
  `ccx report` shows DeepSeek on its own line. D6: agent-delegate's `references/three-way.md` says which work suits
  it. Also: through a provider the CLI's own cost figure (priced with Claude's table, 15× too high here) is ignored.
  150 tests.
- Security fix: a provider run (DeepSeek through Claude Code) started from inside a Claude Code / desktop session
  inherited that session's login, and Claude Code sent the caller's own credential to the provider's server instead
  of the provider key (found in the first live DeepSeek run; the server answered 401). Provider runs now drop the
  caller's auth variables, pass the key as `ANTHROPIC_API_KEY` and add `--bare` (auth strictly the API key; OAuth and
  keychain never read — claude 2.1.309). Checked against a local server that records which headers arrive: before,
  an `Authorization` header that was not the key; after, only the key in `x-api-key`.
- `ccx selftest --provider deepseek` tests each model of a provider.
- Measured (proposal C1, 2026-10-24): a Claude Code built-in sub-agent (Agent tool, Haiku) starts with 58.4k tokens
  of context in its first request — 4.3× ccx's slim start — and a tiny read task cost $0.0083 (via ccx: $0.0029 to
  Claude Haiku, $0.0023 to Codex luna). A Codex sub-agent's own multi_agent child is a separate session (22.2k first
  request) whose tokens are not in the parent's reported usage: 59% of that run's real cost was missing.
- Accounting (C5): after each Codex attempt ccx adds the usage of the sessions it spawned (`codex_children`,
  counted as growth so resumed sessions and retries count once); the dashboard no longer bills those children to the
  lead, and children of a lead session show as a new "Codex · built-in sub-agent" stream. 141 tests.
- Three-way choice (C2): `ccx route … --lead <rung>` adds `choice` — do it yourself, hand it to your own built-in
  sub-agent (Claude Code's Agent tool on Haiku/Sonnet/Opus; Codex's multi_agent on the lead's model), or delegate
  through ccx. Built-in options are priced with their measured start-up (58.4k / 22.2k) as one attempt (ccx cannot
  escalate them); `--needs undo,worktree,other-vendor,resume` rules them out; quota pressure avoids an agent at ≥ 90%
  and counts it 1.5× at ≥ 70% (Codex's quota is read from its logs, Claude's from `--quota claude=0.4`). A delegated
  option still has to be 15% cheaper than doing it yourself and reach 0.6 success. `self_vs_delegate` is unchanged.
  143 tests.
- Built-in work, carried out (C3): `choice.how` says the next step — for a built-in sub-agent, which model to give
  the Agent tool and the `ccx verify --builtin <rung> --b <b> --ok 1|0 --agent-id <id>` that records the verdict (cost
  read from that sub-agent's own transcript or rollout) into routing. `skills/agent-delegate/references/three-way.md`
  explains the three ways.
- Sub-agents don't start their own sub-agents (C4): Codex runs get `--disable multi_agent`, forked Claude runs
  `--disallowed-tools Agent` (slim Claude runs have no Agent tool anyway). `ccx run --allow-subagents` lifts it; the
  children's tokens are then counted into that run. The Claude tool name was checked against `claude --help` 2.1.309,
  not in a live run. 145 tests.
- Follow-up skill audit: reuse explicit delegation choices and valid checks, remove checkpoint-to-routing coupling, and require authorization for context/memory maintenance.
- Skill guidance: narrow task-routing triggers; make numeric task-split planning optional and preserve delegation authorization. Keep estimates distinct from measurements and avoid mandatory skill chains.
- GitHub look: README.md / README.zh.md open with a banner (light/dark `<picture>`), badges, a three-command start, an
  animated demo, measured numbers, six features, an architecture diagram and an FAQ. Images live in `docs/assets/`
  and are regenerated by `scripts/make_assets.py` (banner, architecture, social preview) and `scripts/make_demo.py`
  (the demo, from a real session against the stand-in CLIs).
- Website: `site/` (English and Chinese homepage, one stylesheet, no CDN, light/dark) built by
  `scripts/build_site.py` into `_site/` with the images from `docs/assets/` and a sample dashboard — the real
  `ccx report` on stand-in data, marked as such on the page. `.github/workflows/pages.yml` deploys it, manual only.
- Repository front matter: CONTRIBUTING (EN/ZH, including how to add an adapter for another agent CLI), a short
  code of conduct, issue forms (bug, idea; security goes to a private advisory) and a PR template; a 1280×640 social
  preview in `docs/assets/social-preview.png`.
- Dashboard: negative amounts read `-$0.14` instead of `$-0.14`. 140 tests.
- Packaging: `config/`, `skills/` and `hub-seed/` ship inside the package (`ccx._config`, `ccx._skills`,
  `ccx._hubseed`), so `pipx install git+…` works without a clone; a clone or editable install keeps using the
  folders in place (`ccx.config.data_dir`). `python -m ccx` works; an installed copy writes `python -m ccx …` as
  its hook command (a clone's hook command is unchanged). CI gains a `package` job: build the wheel, install it
  into a clean venv on Linux/Windows/macOS and run `tests/smoke_installed.py` with the installed `ccx`.
- Untried paths run for real on Windows: `--bg`, `ccx undo --apply`, `ccx task resume` after a killed run,
  `ccx report --publish`, `install.ps1`. Fixes found that way: `task resume` finds runs killed before they reached
  the ledger (their record and session id are on disk) and keeps the model they started on (`first_rung`);
  `ccx show` reports `running` instead of `error` while a run is going; `install.ps1` checks exit codes instead of
  `ErrorActionPreference = Stop` (which aborted whenever its output was redirected) and exits 1 when pipx fails;
  both install scripts point to `ccx setup`. 139 tests.
- `docs/plan/` (the 2026-10-22 plan snapshots, the only files with personal names and folders) moved out of this
  repo; the design lives in `docs/DESIGN.md`, progress in `docs/STATUS.md`.
- `SECURITY.md` / `SECURITY.zh.md`: what the session-start hook runs, what config ccx edits, what a writable
  sub-agent may change and how to undo it, how outside text is treated, and how to report a vulnerability.
- `ccx/cli.py` (1,130 lines) split into `ccx/commands/` — `common`, `delegation`, `memory`, `install`, `records`, each
  with `register(sub)` for its part of the parser; `cli.py` keeps `build_parser()` and `main()` (32 lines). Every
  subcommand's help text is unchanged; the top-level command list is now grouped. The wheel includes the new package.
- `ccx setup`: guided first run — checks tools and logins, picks the hub, `init`, shows the `sync` plan and
  applies it only on a yes, `doctor` and the Codex `/hooks` reminder, an optional `selftest`, then the first
  delegation command. `--yes` for scripts; not on a terminal without `--yes` it changes nothing. Tests never
  touch the real `~/.ccx/config.toml` (`CCX_CONFIG`). 137 tests.
- task-checkpoint `init` no longer adds `.ccx/tasks/` to `.gitignore` when git already ignores it.
- `ccx repair [--apply]`: re-counts Codex attempts recorded before 0.3.0 counted only the growth of a resumed
  session (dry run by default; idempotent; the ledger is backed up first). On the test machine: 4 runs,
  AE$ 0.0321 → 0.0162. 133 tests.
- agent-delegate skill: the lead delegates with the skill and the brief only and does not read the project's
  README/STATUS/handoff to do so (the Codex desktop lead read five files to delegate a one-line read).
- Session start shows a long handoff (> 2000 chars) as a summary: the next/open items (finished `[x]` items left
  out), key files, notes and rules, plus a pointer to `.ccx/handoff.md` (6987 → 1360 bytes on this project).
  134 tests.
- Start-up context per request depends on how the agent starts: priors gain `startup_by` (`codex:lean` 18.1k for
  low rungs, which start without the user's config; `claude:read` 10.6k for read-only runs), and `ccx run` passes
  its mode to routing. Older installed task-routing copies keep working. 135 tests.

## 0.3.0 — 2026-10-23 (installed and verified on a real Windows machine: both directions, terminal and desktop apps)
- A command the agent's own sandbox rejects before it runs (codex-cli 0.164 on Windows, read-only: PowerShell
  `Get-Content` → "blocked by policy") is a new attempt kind `policy`. Instead of escalating to a stronger model,
  ccx retries once on the same rung and session, telling the agent which command was rejected and to use another
  (the second two-way test paid ~3× and ~80 s extra for that escalation). Not counted against the model's ability;
  the result shows `policy_blocked: N`, and `escalated` no longer lists a same-rung retry. 124 tests.
- Root cause of those rejections: the lean start-up on low rungs passes `--ignore-user-config`, which also dropped
  the user's `[windows] sandbox = "elevated"`. Without it codex-cli 0.164 rejects every shell command in read-only
  mode; with it all six read commands tried passed. A lean Codex start now carries `windows.sandbox` over from the
  user's `config.toml` (`CODEX_KEEP` in `ccx/runners.py`). Real re-run: done on luna/low in one attempt.
- "Model unavailable" marks last 7 days instead of 30, and record the CLI version; a mark made under another
  version is dropped the next time ccx checks that model (luna failed on codex-cli 0.153, works on 0.164).
- Flags re-checked against codex-cli 0.164.0 (`exec` and `exec resume`); `TESTED_VERSIONS` and READMEs updated.
  126 tests.
- `ccx skills install --replace` keeps its backups in `<hub>/ccx/skill-backups/` instead of next to the skill;
  a hub sync that links every folder with a `SKILL.md` would have installed the backup as a second copy. If an
  older task-routing copy is installed, ccx falls back to the old function signatures. 127 tests.
- Lead-usage magnitudes checked against Codex's own weekly quota: API-equivalent $ per 1% of quota stayed within
  $2.8–4.4 across windows whose raw tokens per 1% differed 14× (model mix), so no double counting is visible; the
  ~600 M cached tokens/day are real (long contexts re-read from cache). Removed `lead_to_sub_ratio` from
  `ccx stats --summary`: it compared all lead work with the few delegated tasks and meant nothing.
- Sub-agent accounting: `codex exec resume` reports the session's running total in `turn.completed`, not the
  turn's own usage, so every Codex escalation, follow-up and auto-continue was counted again with all earlier
  turns (a 46k-token answer was recorded as 268k). Attempts now keep `codex_total` and record the growth; older
  records are read as running totals. Ledger rows written before this fix over-count resumed Codex runs.
- Priors: start-up context measured per request with `ccx selftest` and single-request probes — Claude haiku slim
  13.6k (write) / 10.6k (read), codex-cli 0.164 21.0k (full user config) / 18.1k (lean). `startup_tokens` was
  20k / 30k. 128 tests.
- Fixes from the real desktop tests: `ccx send --list` reads Codex's session files (desktop chats with folder and
  last activity) because `codex agents` needs a TTY; the lead session follows the caller's own variable; a session
  shared by auto-continued runs is archived once; `ccx uninstall` also removes the hub's skill links and restores
  the backups of `skills install --replace`; `ccx skills install` is a dry run unless `--apply`. 131 tests.
- `ccx project init` adds only the ignore lines git doesn't already cover (a repo that ignores all of `.ccx/` got
  six redundant lines). Real check: the SessionStart hook delivers project memory to a new Claude Code session
  intact (UTF-8); `codex exec` does not run SessionStart hooks (codex-cli 0.164), so for Codex it matters only in
  the desktop app / TUI. 132 tests.

## 0.2.4 — 2026-10-23 (fixes from the first real two-way test on Windows)
- A model the account can't use ("not supported when using Codex with a ChatGPT account", model not found, …) is a
  new failure kind `model`: no pointless same-model escalation; it is remembered for 30 days in the shared routing
  state, the run moves to the cheapest usable model at least as able (fresh session), routing skips it, and later
  runs swap it out before starting. Not counted against the model's ability.
- Codex lead usage is now the growth of `total_token_usage` per session file. Summing `last_token_usage` double
  counted repeated token_count lines and history copied into resumed/forked sessions (the test showed 615 M cached
  tokens in one day).
- Failed runs no longer count toward "estimated saving". doctor reads `claude auth status` JSON and shows the CLI
  version each adapter's flags were checked against. 122 tests.

## 0.2.3 — 2026-10-23
- `ccx handoff --by claude --to codex "…" [--next "task 5" --next "task 6"]`: switch leads mid-project. Writes
  `.ccx/handoff.md` (done / decisions / where it stopped / next / key files / open questions; history in
  `.ccx/handoffs/`), adds one project-journal line, and optionally creates a task-checkpoint plan for the next tasks.
  The receiving agent's session start shows the handoff once, in full, plus the unfinished plan.
- Claude Code's own built-in sub-agents (`<session>/subagents/agent-*.jsonl`) are now measured: a separate
  "Claude · built-in sub-agent" stream and a per-task cost table (built-in sub-agent vs ccx → codex/claude/gemini)
  on the dashboard and in `ccx stats --summary`. 119 tests.

## 0.2.2 — 2026-10-23
- Auto-continue: a new `ccx run` from the same lead conversation (Claude Code `CLAUDE_CODE_SESSION_ID`, Codex
  `CODEX_THREAD_ID`), same folder and same agent, within 1 hour (the prompt-cache lifetime) and after a clean finish,
  goes into the **same sub-session** as the previous task, so the sub-agent keeps what it already read. At most
  5 tasks per sub-session; `--new` forces a fresh one; batch and worktree runs are always fresh.
- `--fork` (Claude lead → Claude sub only): the sub-agent starts from a copy of the lead's whole conversation
  (`--resume <lead> --fork-session`). Full context, but every turn re-reads it — use when the brief can't carry it.
- One-shot runs leave no history: `ccx ask` / `ccx selftest` use `--no-session-persistence` (Claude) and `--ephemeral`
  (Codex).
- `ccx archive [run…] [--older-than H] [--apply] | --restore <run>`: Codex sessions via `codex archive` (reversible);
  Claude transcripts moved to `<claude home>/ccx-archive/` (nothing deleted). `sessions.auto_archive_hours = 2`
  archives finished sub-sessions quietly at session start (after the continue window). 116 tests.

## 0.2.1 — 2026-10-23
- Smaller Claude sub-agent start-up (measured, haiku): ccx now passes `--tools` (6 tools for write, 4 for read),
  `--exclude-dynamic-system-prompt-sections` (the system prompt no longer changes per folder, so the prompt cache is
  reused across runs *and projects*) and `--strict-mcp-config` (MCP tool schemas only with `ccx run --mcp` or
  `claude_subagent.mcp = true`). Prompt ~46k → ~20k tokens; a repeat start writes ~0.65–2k tokens instead of ~9.6k.
  Real small read task: $0.0106 (old default) → $0.0050 first start → $0.0014 next start in another project.
  Configurable in `[claude_subagent]`. task-routing's Claude start-up prior 48k → 20k.
- Fix: while a sub-agent works on a task-checkpoint step, ccx refreshes the task heartbeat every 60 s, so a long run
  is no longer reported as "interrupted" after 10 minutes. 108 tests.

## 0.2.0 — part 5/5 (2026-10-23)
- Gemini CLI adapter (checked against Gemini CLI 0.65.0 `--help` and its bundled source): `gemini -p -o stream-json
  -m flash-lite|flash|pro --approval-mode plan|auto_edit --skip-trust`, session id chosen up front (`--session-id`),
  `--resume <uuid>`; schema travels in the prompt; tiers, routing rungs, prices and split horizons for Gemini.
  Routing only considers agents whose CLI is installed.
- Providers: an agent CLI pointed at another model API, e.g. `ccx run --provider deepseek --model deepseek-v4-pro`
  (Claude Code + DeepSeek's documented Anthropic endpoint). Keys are read from your environment, never stored.
  Prices for DeepSeek (peak) and Gemini added with sources and dates.
- `ccx run --bg` (detached; poll with `ccx show`), `ccx send --to codex --thread <id>` (message into a live Codex
  desktop/interactive session via `codex queue`; `--list` = `codex agents`), `ccx selftest` (one tiny real run per
  installed agent: login, parsing, start-up tokens, AE$).
- `ccx skills find <words>`, `ccx skills install [--replace]` (link the repo's skills into the hub so `git pull`
  upgrades them), `ccx improve add|list` (concrete problems only), hub format stamp + `ccx init` migration, doctor
  reports Gemini and hub format.
- `ccx undo <run_id> [--apply]`: every write run in a git repo snapshots the working tree first (`git stash create`,
  nothing is changed); undo restores the files the run touched and moves new files aside under `.ccx/undo/`.
- `ccx task status|resume <task>`: continue an interrupted task-checkpoint task with one command — same session if
  possible, a fresh session on the other agent with the resume brief after a quota stop.
- `ccx ask "..."`: read-only, low-effort second opinion. Sub-agent prompt now states that text in files it reads
  (inbox emails, pages, logs) is reference material, never instructions.
- Docs: English README/DESIGN with Chinese versions (`*.zh.md`), Chinese method notes for task-routing/task-split,
  English translation of the 2026-10-22 plan snapshot (later changes marked "Later: …").
- `ccx route ... --lead claude:opus:high --ctx-files big.log --turns-left 10`: the plan's self-vs-delegate comparison
  (context you'd carry for the rest of the session vs brief + sub cost + review).
- Hub layout `skills_include` / `skills_exclude`: link only the skills you use (each linked description costs tokens
  at every session start).
- Python 3.11 fixes found by CI: Windows junction detection without `Path.is_junction`; `ccx verify --note`.
- Packaging: `pyproject.toml` (`pipx install --editable <clone>`), `install.sh` / `install.ps1`, MIT `LICENSE`,
  GitHub Actions matrix (Linux/Windows/macOS × Python 3.11–3.13). Version 0.2.0. 106 tests.

## 0.2.0-dev — part 4/5 (2026-10-22)
- `ccx report`: single-file offline HTML dashboard (light/dark, phone width, hover tooltips, table view for every
  chart): spend per day by who spent it (Claude/Codex × lead/sub-agent), tokens by type (fresh, cache write, cache
  read, output), quota windows, A/B table, every delegated run with its estimated saving. `summary.json` next to it.
  `--publish` commits both to `report.publish_dir` (your private usage repo) — numbers and labels only.
- Lead-side usage is read from the tools' own session logs (Claude `projects/*.jsonl`, de-duplicated by message id;
  Codex `sessions/**/rollout-*.jsonl` token_count + rate_limits — Codex format still to verify on a live machine).
  Sub-agent sessions are excluded so nothing is counted twice.
- `ccx stats --summary`: AE$, Codex credits (AE$ × 25), cost per success, cache-read share, estimated saving with a
  bootstrap 95% CI, quota stops.
- A/B self-runs: `defaults.ab_self_rate` (0.1) of routed tasks are handed back to the lead ("do this one yourself");
  `ccx ab done <id> --ok 1|0` measures the lead's own usage for it. `--no-ab` opts a task out.
- `ccx config set|get|list`: the save↔fast knob (`defaults.tradeoff` = save | balanced | fast or 0..1; task-routing
  maps k to a success target 0.70 + 0.20k, cascading while k < 0.75), A/B rate, lead models, publish dir.
  Written to `<hub>/ccx/settings.toml`. 85 tests.

## 0.2.0-dev — part 3/5 (2026-10-22)
- Routing: `ccx run/route/batch` take the 5-item rubric (`--files --coupling --clarity --risk --novelty`, or `--b`)
  and ask the task-routing skill for `agent:model:effort`; explicit `--model/--effort` overrides; `--tier` and the
  keyword heuristic remain as fallbacks. "do it yourself" / "split first" advice is returned instead of running
  (`--force` to run anyway). Escalation follows the routing ladder, in the same session.
- Sub-agents may edit files by default (`--mode write`); `--mode read` for analysis.
- Streaming: Claude runs with `--output-format stream-json --verbose`; the session/thread id is written to the run
  record the moment it appears, so a crash, closed window or timeout still leaves a resumable run.
- Failures are classified (ok / quota / auth / timeout / error). A quota or rate-limit stop retries once on the other
  agent (`--no-fallback` to stop). Timeouts and quota stops tell the lead how to resume.
- task-checkpoint integration (`--task --step`): step started, session id saved, failed with reason quota/error, or
  noted for verification.
- Learning loop: every attempt is fed back to task-routing (ability + cost) and, with `--minutes`, task-split
  (horizon). Definite failures and self-checked successes are learned at once; `ccx verify <run> --ok 1|0` gives the
  lead's verdict (corrects a wrong provisional record, never double counts) and closes the checkpoint step.
- `ccx plan ...` wraps task-split. Usage is normalized to fresh / cache-write / cache-read / output for both agents
  (Codex counts cached inside input; Claude separately). Each attempt carries an API-equivalent cost (AE$) from the
  routing price table, including Anthropic's cache-write premium (1h entries bill 2x input); checked against one
  real run: AE$ 0.01041 vs billed 0.01056. 77 tests.

## 0.2.0-dev — part 2/5 (2026-10-22)
- Project layer `.ccx/` (`ccx project init|status|compact`): context.md snapshot, journal + per-agent cursors,
  `inbox/` for files/emails the user gave either agent (`ccx inbox "one line" --file X`), git-ignored state.
- `ccx mem add --project`; the session-start hook (`ccx mem delta --as X`) now prints personal increments +
  project increments + unfinished task-checkpoint tasks in one go, and nothing when there is nothing. 60 tests.

## 0.2.0-dev — part 1/5 (2026-10-22)
- Configurable hub layout (`<hub>/ccx/layout.toml`, `ccx init --snapshot ... --external-sync ...`): plug into an
  existing shared setup instead of duplicating it. External snapshot mode never writes into CLAUDE.md/AGENTS.md;
  an external sync command owns skill links + MCP registration.
- Shared notes are compacted into a marked section of the snapshot, written in place (hard links survive).
- MCP registry reads both `{"servers": ...}` and the common `{"mcpServers": ...}` format.
- `ccx uninstall [--apply]`: removes only what ccx added (hooks, managed blocks, links to its bundled skills).
- Skills: automatic calibration (routing cost factor, split horizons), validation, review cost. 56 tests.

## 0.1.4 — 2026-10-22
- New standalone skill `skills/task-split/`: quantified task decomposition — piece size from METR time
  horizons (p = 1/(1+(t/h50)^0.86)), number of pieces by cost per success, "only cut where you can check"
  (uncheckable splits compound failure), as-needed recursive splitting (ADaPT), DAG waves / critical path /
  Brent bound, file-clash and size flags, ready `checkpoint.py init` line. Method notes with citations,
  Chinese README. 9 tests (48 total).
- task-routing: "split" advice points to task-split.

## 0.1.3 — 2026-10-22
- New standalone skill `skills/task-checkpoint/`: resumable long tasks (step status, append-only fsync'd log,
  atomic writes, heartbeat-based interruption detection, quota/crash/closed reasons, `git stash create`
  snapshots under `refs/checkpoints/` that never touch the branch; worktrees share the main task folder).
- task-routing: learned state shared via the hub when installed under `<hub>/skills/`; file lock for concurrent
  records; UTF-8 output on Windows.
- Skills: descriptions cut ~50% (they load every session); agent-delegate now defers to task-routing and has a
  Chinese README.
- Plan §20: integrate with an existing personalization layout (shared AGENTS.md snapshot, skills dir, MCP registry)
  instead of duplicating it.
- 39 tests.

## 0.1.2 — 2026-10-22
- New standalone skill `skills/task-routing/`: quantified model/effort/agent choice
  (IRT 2PL success probability, cascade rule, cost per success, Elo-style learning), stdlib-only script,
  dated priors with sources, method notes with citations, Chinese README. 11 tests.
- docs: working plan snapshot (`docs/plan/2026-10-22-plan.zh.md`), research notes on token-cost
  quantification (EN + ZH), bilingual decision log (`docs/DECISIONS.md`).
- Not yet bilingual everywhere: EN plan and ZH versions of README/DESIGN/method follow in v0.2.

## 0.1.1 — 2026-10-22
- Personal content removed from the repo; hub location via `ccx init --hub` / `~/.ccx/config.toml`.

## 0.1.0 — 2026-10-22
- First draft: bidirectional delegation (`ccx run/resume/batch`), T0–T4 routing with
  same-session auto-escalation, schema-enforced compact results, token ledger (`ccx stats`),
  incremental shared memory (snapshot + journal + per-agent cursors, SessionStart hooks),
  skill/MCP/memory sync with dry-run and backups, `ccx doctor`, `agent-delegate` skill.
- 18 tests against fake CLIs. Not yet run against real CLIs on the target machine.
