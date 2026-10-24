# Changelog

## Unreleased
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
- `ccx/delegate.py` split by job (proposal J11), behaviour unchanged: `prompts.py` (what a sub-agent is told),
  `plan.py` (which rungs a run tries, budget and provider checks, the fallback to another vendor), `workspace.py`
  (worktree, ccx's re-run of the check, the snapshot and `ccx undo`), `verdicts.py` (`ccx verify`, built-in
  verdicts, probable verdicts), `review.py` gains the review step itself, the Codex accounting helpers move to
  `ccx/agents/codex.py` and writing a run record to `ledger.py`. `delegate.py` (988 → 547 lines) keeps the run loop
  and re-exports the old names, so `from ccx.delegate import ...` still works.
- Renamed to **relayline** (was `claude-codex-bridge`): the GitHub repo, the package name in `pyproject.toml`, the
  install command (`pipx install git+https://github.com/SUPERD6/relayline`), and the links in the README, website,
  CONTRIBUTING and issue templates. The `ccx` command and the `ccx/` package are unchanged; GitHub redirects the old
  URL. The README now opens by saying how it differs from CCB and from OpenAI's codex-plugin-cc.
- Handoffs are no longer lost between parallel sessions: each one has its own file in `.ccx/handoffs/` (`handoff.md`
  is only the latest), and session start lists every handoff to you not seen yet — the newest whole or summarised,
  the others one line each with their file. `ccx fresh` points the new conversation at its own handoff file.
- `--from-transcript` handoffs: the numbered list from the agent's latest message when no plan tool was used; the
  conversation's last 5 `ccx run`s with their check and verdict; `git status --short` keeps its leading space.
- The dashboard's saving is measured from `ccx trial` when a trial has enough tasks in both halves, otherwise it is
  labelled a model ("Estimated saving (model)", `saving_kind` in `ccx stats --summary`) with what it assumes.
- agent-delegate: when ccx already ran your `--check` and it passed, don't run it again yourself (H11: that is what
  makes delegating save the lead a turn).
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
- A model for the lead itself (proposal J5): `ccx lead --suggest` reads the last 30 turns of this conversation
  (Claude Code), sorts them into code edits, doc edits, reading/running and talk (files changed through the shell
  count as code), and compares what a turn costs at this context size on each model. When code is under a fifth of
  the turns it suggests one rung down, with the saving per 100 turns and how many turns pay back the one cache
  rewrite a switch costs; otherwise it says to stay. `ccx report` adds what the same lead turns would have cost one
  rung down. Here: 7 days of lead turns $1,204 AE, one rung down $952 less; this conversation (~440k tokens a turn,
  half its recent turns editing code) is told to stay on opus.
- One step to a fresh conversation (proposal J4): `ccx fresh [--as claude|codex] [--note ...] [--launch]` writes the
  handoff from this conversation's own session file (as `ccx handoff --from-transcript` does) addressed to the same
  tool, and says how to open the new conversation; `--launch` starts it in a terminal. A new conversation of the
  same tool in this folder now sees a handoff addressed to it (before, a handoff was never shown to the tool that
  wrote it). The H10 per-turn hint now says: ask the person, then `ccx fresh`.
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
- Research on similar projects (proposals J8–J10), docs only: `docs/research/landscape.md` / `.zh.md` covers OpenAI's
  official codex-plugin-cc (facts with sources, overlap, a coexistence plan that is not implemented yet, tests still to
  run), a comparison of similar projects (also a new "Similar projects" section in both READMEs) and eight name options
  checked against GitHub and PyPI for the user to choose from. Nothing is renamed.
- STATUS is one page (proposal J6): what is going on now, the next three items and a short "how sure we are";
  the old 24 KB page moved to `docs/STATUS-archive.md` / `.zh.md` as it stood. AGENTS.md no longer tells every
  agent to read it first, only when it needs to know where things stand — anything read at start-up is re-read
  on every later turn.
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
- Read-only sub-tasks are told their shell still works: in a real E8 run gpt-6-luna/low once answered that it had
  no tool to read the file it was asked to read.
- Trust in probable verdicts (proposal J7). `ccx stats --summary` / `ccx report` count how many probable verdicts
  (H13) were later judged again by you or the lead and how many of those the other way; once 5+ were re-judged and
  over 20% overturned, new probable verdicts stop teaching routing (a weak check may pass wrong work as right).
- J0 baseline of the lead's own cost: `scripts/eval/j0_baseline.py real` (the real lead sessions and the ledger, no
  model calls) and `tasks --ref REV` (three fixed lead tasks in a clone at that commit with the person's default
  setup, answers checked against the clone); rerun after J1–J6 with the same arguments.
- Measured H11 (first batch), E8 and F9 on the real CLIs ([report](docs/research/2026-10-24-h11-e8-f9-measurements.md), about $0.56 in all). New
  `scripts/eval/`: `h11_compare.py` (paired lead-does-it vs lead-delegates on generated repos with hidden
  acceptance tests, verdicts via `ccx verify`, spend cap), `e8_handoff.py` (a real outgoing lead, `--from-transcript`,
  a receiver that sees only the handoff; `--cut-after` kills the lead mid-work), `f9_subagents.py` (on/off, children
  counted from the ledger and the session files). Fixed in `ccx handoff --from-transcript`: in a git worktree inside
  the main checkout it took another session's transcript and git state (now the lead's own folder first); the Claude
  desktop plan tool's `advance` / `done` / `start` updates were ignored, leaving the plan at its first state.
- The lead's own context (proposal H10). Almost all spend is the lead re-reading its whole conversation every turn
  (here: sub-agents $0.34 in 30 days; the median lead turn re-reads ~220k tokens, ~$0.06, over ~19k turns). `ccx lead`
  lists recent lead conversations: turns, what the last and the largest turn read, cost per turn, advice. `ccx sync`
  adds a Claude Code UserPromptSubmit hook (`ccx lead --hint`) that prints one line when a conversation re-reads more
  than 150k tokens a turn (at most once per 20 turns, never fails the turn); `ccx uninstall` removes it. Codex: no
  per-turn hook yet. `ccx report` shows "Lead cost per turn"; agent-delegate says to send big reads out and hand a
  long conversation over to a fresh one.
- Verdicts without asking (proposal H13). A finished run nobody judged for 12 h gets a probable verdict from the
  evidence: right when ccx's check passed or the sub-agent self-checked, the independent review (if any) passed, and
  it was neither undone nor sent back; runs without such evidence wait for a person. `ccx undo --apply` records the
  run as wrong. Verdicts drawn this way are marked `soft`, kept apart in `ccx stats` / `ccx report` ("judged by you
  or the lead · N probable"), feed routing only where nothing was learned yet, and any `ccx verify` overrides them.
  `ccx verify --ok 0 --reason unfinished|wrong|overreach|other` records what was wrong; the report counts reasons.
  Runs quietly at session start; `ccx verify --sweep [--after-h H]` by hand.

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
