# Status and next steps

English · [中文](STATUS.zh.md) · updated 2026-10-24 · version 0.4.0 · 201 tests

This is the working list for whoever continues the project (person or agent). It says what is done, how sure we
are that it works, and what to do next, in order. Keep it current: when an item is done, move it to "Done" with
the commit, and add anything new you find.

2026-10-24 skill-guidance update: narrow routing triggers, make numeric splitting optional, and separate planning from delegation authorization. Entry points and Chinese summaries agree; structural checks and scenario review only, no model A/B result.

Follow-up skill audit (2026-10-24): delegation now reuses a specified model and valid checks, while checkpointing no longer requires model routing. Context/memory writes remain separately authorized. Instructions checked against current CLI help; no additional agent run.

## 1. Where we are

Legend: **real** = verified on a real Windows machine with logged-in CLIs · **fake** = covered only by tests with
fake CLIs · **none** = not run anywhere yet.

| Area | What | Confidence |
|---|---|---|
| Delegation | `ccx run` Claude → Codex and Codex → Claude, JSON result, read-only and write mode | **real** (both directions; write runs in the F1 trial) |
| | `--check` re-run by ccx, read/write inferred from the brief, sub-agents told not to commit | **real** (F1 trial, 2026-10-24) |
| | worktrees, `ccx batch`, escalation, quota fallback to the other agent | fake |
| | auto-continue of sub-sessions, `--bg`, `ccx send` (waits while you type) | **real** (`--bg`, send, auto-continue); `--fork` fake |
| Review (F1) | another vendor's cheap model reviews the diff, one fix round | **real** (seeded bugs 9/9, false alarms 0/5, 1 real bug caught) |
| Failure kinds | `model`, `policy`, `auth` | **real** |
| Routing | public benchmarks merged per kind, total cost, quota by pace, human-minute difficulty | **real** data and quota readings; priors **uncalibrated** (2 real verdicts so far) |
| Queue / seats | `ccx q`, layered splits, `--seat` | fake |
| Checkpoint | `ccx task resume` after a killed run | **real** (2026-10-23); after a real quota stop: fake |
| Memory | layers, cursors, sources/supersedes/search, `ccx handoff` | Claude side **real**; Codex desktop not checked; `--from-transcript` built once from a real session (not a live handover) |
| Wiring | `ccx init` / `sync --apply` / `skills install --replace` / SessionStart hook | **real** (Codex hook output: desktop not checked) |
| | `ccx uninstall` | dry run **real**; apply not run |
| Accounting | sub-agent tokens + AE$, lead usage, archive, `ccx report` (+ `--publish`) | **real** |
| Adapters | Codex, Claude Code, DeepSeek (provider; 10/10 calibration tasks) | **real** |
| | Gemini CLI | none |
| Built-in sub-agents (F9) | on by default, ≤ 3, routed model, $2 cap | Codex `agents.*` keys: see the F9 note below |
| Packaging | wheel + clean-venv smoke, `install.ps1`, CI | **real**; CI not running since 2026-10-24 (Actions minutes, see 2) |

Measured on the real machine (second two-way test, tiny read-only task):
- Start-up context per request (`ccx selftest` + single-request probes, 2026-10-23): Codex 18.1k lean / 21.0k with
  the user's config; Claude haiku slim 13.6k write / 10.6k read. Written to `startup_tokens` (`d4c97fd`).
- Resumed Codex sessions used to be counted with their whole history (fixed in `2c0e637`): ledger rows before
  that over-count escalations and follow-ups.

## 2. Next steps, in order

### Now (2026-10-24, after v0.4.0): the unified order of proposals F10–F14, G, H, I
1 H13 verdicts without asking — in progress (branch `feat/h13-auto-verdicts`) · 2 H10 keep the lead's context
small · 3 H11 a week-long comparison (with the E8 two-way handover and F9 on/off checks) · 4 I1–I4 adapters for
many vendors · 5 F10–F14 fewer limits on built-in sub-agents · 6 H5–H7 + I6 shared memory in use · 7 H3–H4 + I7
`ccx discuss` · 8 H8–H9 collaboration patterns · 9 G1 UI + `ccx stop` + `lang`, I5 more model sources · 10 H1–H2,
H12, H14–H16, I8, then the open-source release. Each step: a branch, tests, a PR in Chinese, CI green, merge.

### Before (2026-10-24, v0.4.0)
- **Real use with verdicts.** 34 real runs in the ledger, only 2 `ccx verify` verdicts. Routing calibration, the
  learned lead bias (E11), `refit` and the "how much was saved" report all wait on these. Run `ccx verify` after
  each delegated task; read `ccx report` after two weeks.
- **CI.** Jobs have not started since 2026-10-24 (GitHub: payments / spending limit; private-repo minutes, macOS
  10x). The workflow now runs a small set on push and the full matrix on tags/PRs/by hand (`cdfc13a`); it runs
  again once minutes reset or billing is sorted (the user's account). Unlimited once the repo is public.
- **E8 acceptance.** Hand over for real once each way (Claude → Codex, Codex → Claude); the new lead should say
  where things stand and what's next from the handoff alone.
- **F9.** Live check (2026-10-24, 4 runs, the same splittable task, luna/low): all done and checked, $0.0034–0.0057
  each; luna never started sub-agents, on or off, so there is nothing to compare yet. Found: codex-cli 0.164 offers
  its multi_agent v2 tools even with both features disabled, so `--no-subagents` now also says the rule in the
  brief (`0124e0a`). The `agents.*` keys were accepted without error; their effect is unseen (no child started).
- **Proposal G** (`ccx ui`, a local live view): mock-up first, for approval.
- **Open from the plan:** `lang` (en/zh) for the strings ccx injects; Gemini CLI never run live; `ccx uninstall
  --apply` never run; the Codex desktop side of the SessionStart hook (needs a new desktop conversation).
- Not pursued for now: Artificial Analysis (`AA_API_KEY`; the plugin stays in the hub, unused).

### Now (2026-10-23, approved in the shared doc: packaging → setup → split cli.py → clean-up → untried paths)
- **Packaging — done (`4ec0496`, CI `package` job green on 3 OS).** Plan was: keep `config/`, `skills/`, `hub-seed/` where they are (hub links point at
  `skills/`) and ship them as package data (`ccx._config`, `ccx._skills`, `ccx._hubseed`); one resolver uses the
  source tree when present, else `importlib.resources`; `python -m ccx` where `ccx.py` is missing; CI builds the
  wheel, installs it in a clean venv and runs `ccx --version` + a fake-CLI smoke run.
- **`ccx setup` — done.** Plan: a guided first run in `ccx/setup.py` (check tools/logins → hub → init → sync
  preview → apply on yes → doctor + /hooks reminder → optional selftest → first delegation command); asks before
  every change; not on a terminal and no `--yes` = shows the plan only. (This plan line was written after the
  work, not before — corrected here.)
- **Split `ccx/cli.py` — done.** Result: `cli.py` 32 lines; `ccx/commands/{common,delegation,memory,install,records}.py`. Every subcommand's `-h` is identical to before; only the order of the top-level command list changed (now grouped). Plan was: move command groups into `ccx/commands/` (run/route/batch, memory/project,
  sync/skills/setup, reporting, archive/handoff/task) with the parser built from per-module `register()`; `cli.py`
  keeps `main()` and shared helpers; no behaviour change — the full test suite and the installed-wheel smoke test
  must pass unchanged.
- **Clean-up before open source — done except the history squash.** `SECURITY.md` added (`976342c`); `docs/plan/` moved to the private repo `ai-personal` (copies checked byte for byte) and removed here; a scan for names, emails, user folders and local paths now finds nothing (LICENSE keeps the GitHub handle as copyright holder). Still in git history until the squash, which comes last and only after asking. Plan was: add `SECURITY.md` + `SECURITY.zh.md` (what the session-start
  hook runs, how inbox/web text is treated, what a writable sub-agent may touch and how to undo it, how to report a
  vulnerability); move `docs/plan/` (the only files with personal names and folders — 44 hits) out of this repo
  once the user picks where (the private repo `ai-personal` does not exist yet); squash the git history last, and
  only after asking.

- **Untried paths, run once for real — done.** Real runs on Windows: `--bg` (finished on luna/low); `ccx undo
  --apply` after a real write run (file restored with the user's uncommitted edit kept, new file moved aside);
  `ccx task resume` after killing a real run mid-way (same Codex session continued); `ccx report --publish` (committed;
  no push without a remote); `install.ps1` with and without pipx, and with output redirected. Fixed on the way:
  `task resume` now finds runs killed before they reached the ledger and keeps their model; `ccx show` says
  `running` instead of `error` while a run is going; `install.ps1` reports a failed pipx install (exit 1) and no
  longer aborts when its output is redirected. Gemini and DeepSeek still need a login / key. Plan was, each isolated from the real hub/pipx/repo: `--bg` on
  Windows (tiny read run on luna/low, detached, then `ccx show`); `ccx undo --apply` after a real write run in a
  scratch git repo; `ccx task resume` after killing a real run mid-way (`--task/--step`); `ccx report --publish`
  into a scratch local repo; `install.ps1` with temporary `PIPX_HOME`/`PIPX_BIN_DIR`/`CCX_HUB`/`CCX_CONFIG`.
  Gemini and DeepSeek stay for later (need a login / key).

- **GitHub look — done (2026-10-24; `9fd646b`, `9df8bbb`, `d7e7c10`).** README first screen, demo, architecture,
  FAQ; `site/` + sample dashboard + manual Pages workflow; CONTRIBUTING, code of conduct, issue forms, PR template,
  social preview; About text and topics set. GitHub community profile 100%. Left for the user: upload
  `docs/assets/social-preview.png` (Settings → Social preview; the API cannot), and after going public: enable Pages
  (source: GitHub Actions) and run the `website` workflow, turn on private vulnerability reporting, set the homepage
  field. The tests and release badges only show once the repo is public. Plan was: `docs/assets/` gets banner and
  architecture SVGs as light/dark pairs (`<picture>`, so GitHub's own theme decides, not the OS), a demo SVG generated
  by `scripts/make_demo.py` from a real fake-CLI session (re-runnable), and a 1280×640 social preview PNG; README.md /
  README.zh.md get the first screen, measured numbers, six features and an FAQ; `site/` (EN + ZH homepage, sample
  dashboard from `ccx report` on fake data) with a manual-only Pages workflow; CONTRIBUTING (EN/ZH), issue/PR
  templates, a short code of conduct, and the repo About text and topics. Checked on GitHub's own rendering
  (`gh api …/readme` HTML) and in the browser at desktop/phone width in both themes.
- **GitHub look — mock-ups (approved).** README first screen (SVG banner that shows the
  hand-off with a real run's numbers, badges, one-line value, three-command start, measured table) and a static docs
  homepage (no CDN, light/dark + toggle, phone width). Checked rendered at 1440×900 and 390×844 in both themes: no
  overflow, no text under 12 px, tap targets ≥ 32 px, visible keyboard focus. Not in the repo yet; the full set
  (demo animation, architecture SVGs, Pages, social preview, CONTRIBUTING, templates) follows approval.

- **Proposals E and F — approved 2026-10-24, in progress.** Order: step 0 read/write detection (approved
  10/23, missed) → E1 → E3 → E11 → E2 → E4 → E5 → E6 → F8 → F3 (+F2) → F1 → F9 → F7 → F4–F6, with E7 → E8 → E9 in
  between. Step 0 now: `ccx run`/`route`/`batch` infer read or write from the task text when `--mode` is not given
  (Chinese and English verbs; explicit `--mode` wins; unclear → write, said so), record `mode_source`; a read-only
  run whose sub-agent says it needs edits stops with `needs_write` for the lead to decide, no escalation. ✅ `71a3183`.
  E1 ✅ `ca4ced3`: weekly public benchmark data (Epoch AI, LMArena, models.dev) cached next to the routing state.
  E3 ✅ `2910f66`: abilities merged from those benchmarks per kind of work (`--kind`), local outcomes on top.
  F1 live trial (2026-10-24): seeded bugs 9/9 caught by the tightened brief, 0/5 false alarms (2 haiku reviews failed
  and now fall back to the next reviewer); 1 real bug caught in 4 real tasks, fixed in one round; $0.0017 (luna) –
  $0.0037 (haiku) per review. On diffs this small the lead saves only ~300–500 input tokens, about what a review
  costs: the gain is the caught bugs; it pays for itself in tokens from roughly 50+ changed lines.
  F1 ✅: independent review only when needed (`--review auto|on|off`): another vendor's cheap model reviews the diff
  when the task is visible/critical, the sub-agent is unsure, or its claims don't match the diff; one fix round.
  E8 ✅ (+ model fallback for formats the code can't read): `ccx handoff --from-transcript codex|claude` writes the handoff by code from the outgoing lead's newest
  session file (goal, its plan, recent messages, last conclusion, changed files, failed commands, git state,
  unfinished tasks; secrets masked, one page); a quota resume also hands over the cut-off session's state.
  E7 + E9 ✅ `b4740a6`: memory sources, replacement, checks, search, stale flags, a 600-token start-up cap; where memory goes.
  F6 ✅ `e08ce82`: `ccx send` waits while you are working in that Codex conversation, then holds the message.
  F4 + F5 ✅ `b1c26b4`: named seats (`--seat`), restore outcomes in `ccx q resume`.
  F9 ✅ `9383282`: built-in sub-agents on by default — one level, routed model, ≤ 3 at a time, counted, spend watchdog.
  F3 + F2 + F7 ✅ `c66d70d`: durable work queue (`ccx q`), roles left to the lead, layered splits through the queue.
  F8 ✅ `68bcd1b`: sub-agents check their own work; `--check CMD` is run again by ccx and a failure counts.
  E6 ✅ `27e6987`: DeepSeek flash at low / high / max by difficulty; v4-pro out of the ladder.
  E5 ✅ `de2a753`: quota by pace, projected to each window's reset; Claude read from runs and a tiny hourly probe.
  E4 ✅ `1e268ff`: total cost = money + quota shadow price + time + risk (replaces the 70% gate and quota weights).
  E2 ✅ `3731fcd`: local source plugins; the user's Artificial Analysis plugin sits in their hub, not used for now (user decision, 2026-10-24).
  E11 ✅ `78bce81`: difficulty in human minutes (`--minutes`), objective signals from the brief, learned lead bias, `refit`.
- **Proposal D — done (2026-10-24; `9b618d8`, `3175b80`).** First live run found that a provider run sent the
  caller's own Claude login to DeepSeek (401; fixed in `9b618d8`, checked against a local header-recording server).
  D1: 1.5k start-up tokens per request with `--bare`; tiny read $0.0009 flash / $0.005 v4-pro. D2: flash 10/10 on
  checkable repo tasks (b 1–5), $0.054 → theta 4.5 (low end of 4.3–6.8). D3–D5: own `deepseek` agent and rungs,
  escalation to Claude, offered only when every subscription is at ≥ 70% quota, off-peak half price, $1/day cap,
  own dashboard line. D6: guidance in `references/three-way.md`. Not verified live: escalation from DeepSeek to
  Claude (no task failed), v4-pro's ability, and the cap (tests only). The pointers added to task-routing's and
  agent-delegate's SKILL.md sit with the user's own uncommitted edits there.
- **Proposal C — done (2026-10-24; `3100e14`, `4a5f64c`, `839ba87`).** C1 measured: a Claude Code built-in
  sub-agent starts with 58.4k tokens (4.3× ccx's slim start), a Codex multi_agent child 22.2k; a tiny read cost $0.0083
  built-in vs $0.0029 / $0.0023 through ccx. C5: a Codex sub-agent's own children were missing from the ledger (59% of
  one run's cost) — now counted. C2: `ccx route … --lead` gives `choice` (self / builtin / delegate) with `--needs`
  and quota pressure. C3: `choice.how` and `ccx verify --builtin`. C4: no nested sub-agents unless
  `--allow-subagents`. Not verified live: that `--disallowed-tools Agent` removes the Agent tool from a forked Claude
  run (checked against `--help` only). Open: a pointer to `references/three-way.md` in agent-delegate's SKILL.md,
  which has edits of the user's not yet committed.
- **Proposal C (as proposed).** Choose among three ways for each
  piece: the lead itself, the lead's built-in sub-agent (Claude Code's Agent tool, Codex's multi_agent), or ccx to
  the other tool — with hard requirements (undo/worktree, other vendor, resume → ccx) and quota pressure. And a rule
  for nesting: ccx sub-agents don't start their own sub-agents by default. Facts found: a Claude sub-agent under
  ccx's slim start has no Agent tool (except with `--fork`); a Codex sub-agent has `multi_agent` on and can, and
  whether those children's tokens reach the ledger is unverified. No built-in sub-agent runs exist on this machine
  yet, so their start-up cost is unmeasured. Nothing implemented yet.

### P0 — correctness and trust (do first)

1. ~~Check the lead-usage magnitudes~~ — done 2026-10-23. `/status` shows no token totals, only the 7-day quota
   (2% used, matching ccx). Checked instead against quota % per window: AE$ per 1% stayed within $2.8–4.4 while
   raw tokens per 1% differed 14× (model mix), so no double counting is visible. `lead_to_sub_ratio` removed.
   Claude lead usage is not cross-checked yet (no quota % in its transcripts).
2. **First real `ccx sync`** — applied 2026-10-23; doctor all ok. Left:
   - Run the dry run and review every planned change.
   - `--apply` installs the Claude `settings.json` SessionStart hook, the Codex `config.toml` hook block (trust it
     once in `/hooks`), and the `agent-delegate` skill links.
   - Then check:
     - a new session on each side shows the memory delta, unfinished tasks and handoffs;
     - nothing else in either config changed;
     - `ccx uninstall --apply` removes exactly what was added.
   - On a hub with `external_sync`, skills/MCP stay with that script.
3. **Desktop apps as lead.** Claude Code desktop → Codex: **done 2026-10-23** (lead session recorded, luna/low in
   one attempt; a second task auto-continued the same Codex session and was counted as its growth only).
   Codex desktop → Claude: **done 2026-10-23** (message queued with `ccx send --thread`; the agent read the
   agent-delegate and task-routing skills, ran `ccx run` with the rubric → haiku/low, checked the answer and
   recorded `ccx verify --ok 1`; lead session = the desktop thread id). Not seen yet: the SessionStart hook's
   output in a new session — the shared memory is empty, so it has nothing to print.
   The two bugs found here (`send --list` needed a TTY, lead session ignored the caller) are fixed.
   Original item: Ask each desktop app's agent to run one `ccx run` (Codex desktop → Claude,
   Claude Code desktop → Codex). Verify:
   - the lead-session env var is present (`CODEX_THREAD_ID` / `CLAUDE_CODE_SESSION_ID`), so auto-continue works;
   - the sub-agent's sessions do not appear in, or are archived from, the apps' history.
4. ~~Windows read-only sandbox~~ — done (`94d1323`): the rejections came from ccx's own `--ignore-user-config`
   dropping `windows.sandbox`, not from read-only mode. Read-only stays the default for read tasks.

### P1 — make it pay off

5. **Calibrate with real work.** Use ccx for 1–2 weeks of real tasks, with `ccx verify` after each.
   - Then read `ccx report`: which rungs succeed, real cost per success, A/B rows, built-in sub-agent vs ccx.
   - Adjust only from data: priors in `skills/task-routing/data/priors.toml`, horizons in task-split.
6. ~~One copy of the skills~~ — done 2026-10-23 (`6d75a3c` keeps the backups out of the skills folder).
7. ~~Unavailable-model memory is 30 days~~ — done (`94d1323`): 7 days, dropped when the CLI version changes.
8. **Run the untried paths once for real:**
   - `--bg` on Windows;
   - ~~`ccx send` into a live Codex desktop thread~~ (works with `--thread`; `--list` needs a TTY);
   - `ccx task resume` after a real quota stop or a closed window;
   - `ccx undo --apply`;
   - `ccx report --publish` to the private usage repo;
   - Gemini CLI (needs a login);
   - the DeepSeek provider (needs a key);
   - `install.ps1` / pipx.
9. **Doc drift.** Re-checked against codex-cli 0.164.0 / Claude Code 2.1.309 on 2026-10-23 (`94d1323`). Repeat
   whenever a CLI updates: `--help` for the flags ccx uses, then `TESTED_VERSIONS` in `ccx/runners.py`.

### P2 — before v1.0 (open source)

10. Contributing guide + adapter template; a fake-data sample dashboard in `docs/`; issue templates.
11. Optional `lang` setting (en/zh) for the few strings ccx injects into sessions.
12. Version tags (could not be pushed from the cloud session); squash history into one clean commit before making
    the repo public; final check that no personal data is in any file.

## 3. Acceptance (from docs/DESIGN.md)

| # | Check | State |
|---|---|---|
| A1 | `ccx doctor` | ✅ all ok after `ccx sync --apply` |
| A2 | Claude → Codex | ✅ terminal and Claude Code desktop lead (auto-continue too) |
| A3 | Codex → Claude | ✅ terminal and Codex desktop lead (verified with `ccx verify`) |
| A4 | memory increments only | ✅ Claude Code new session; ⏳ Codex desktop |
| A5 | project layer shared | ⏳ hooks are in; not checked with a real inbox file |
| A6 | skills on both sides | ✅ `agent-delegate` + `task-*` linked into both (hub → repo) |
| A7 | MCP on both sides | ⏳ (hub's own sync already handles MCP; confirm) |
| A8 | dashboard | ✅ `ccx report` and `--publish` run on the machine |
| A9 | resume after interruption | ✅ a killed run resumed in the same session (2026-10-23) |
| A10 | quota fallback | ⏳ (only seen with fakes) |

## 4. Done recently

- 2026-10-23 `75c9e54` — start-up priors by mode; `8ea4e8e` — lead stays cheap when delegating, long handoffs summarised; `ce4195a` — `ccx repair` (4 runs, AE$ 0.0321 → 0.0162).
- 2026-10-23 `27b8bf3` — **v0.3.0** released (tag + GitHub release).
- 2026-10-23 `f42939e` — five small fixes: `send --list` without a TTY, lead session by caller, archive a shared session once, uninstall hub links + restore backups, `skills install` dry run by default.
- 2026-10-23 — desktop apps as lead, both directions (P0-3).
- 2026-10-23 `2c0e637` — resumed Codex usage counted as growth, not the session's running total; `d4c97fd` measured start-up priors.
- 2026-10-23 `bf5e1c8` — P0-1: Codex lead usage checked against the weekly quota; `lead_to_sub_ratio` removed.
- 2026-10-23 `6d75a3c` — `skills install --replace` backups kept outside the skills folder; hub `task-*` now link to the repo.
- 2026-10-23 `94d1323` — lean Codex start keeps the user's `windows.sandbox` (root cause of `policy`); unavailable-model marks 7 days + CLI version; flags checked on codex-cli 0.164.0.
- 2026-10-23 — first real `ccx sync --apply` (hooks + agent-delegate), doctor all ok.
- 2026-10-23 `92207a8` — `policy` failure kind: same-rung retry instead of escalation when the sandbox rejects a command.
- 2026-10-23 `8de20b3` — tests read UTF-8 explicitly (Chinese Windows / GBK locale).
- 2026-10-23 `e110a1c` v0.2.4 — unsupported-model swap, Codex usage from `total_token_usage` deltas, doctor JSON login.
- Earlier: see CHANGELOG.md.
