<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/banner-dark.svg">
  <img alt="relayline (command ccx): coding agents as each other's lead and sub-agent; a real run: Codex luna/low, done in one attempt, verified, $0.0023" src="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  <a href="https://github.com/SUPERD6/relayline/actions/workflows/test.yml"><img alt="tests" src="https://github.com/SUPERD6/relayline/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="dependencies: standard library only" src="https://img.shields.io/badge/dependencies-stdlib%20only-1f7a3a">
  <a href="https://github.com/SUPERD6/relayline/blob/main/LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0f7c80"></a>
  <a href="https://github.com/SUPERD6/relayline/releases"><img alt="release" src="https://img.shields.io/github/v/release/SUPERD6/relayline"></a>
</p>

<p align="center">English · <a href="https://github.com/SUPERD6/relayline/blob/main/README.zh.md">中文</a> · <a href="https://superd6.github.io/relayline/">Website</a></p>

# relayline

**From Claude Code, hand a checkable chore to Codex on a cheaper model.** ccx re-runs your check itself, another
vendor's model reviews the diff, the cost of the run is recorded, and undoing it is one command. It works the other
ways round too (Codex or DeepSeek leading, Claude Code taking work), with shared memory and working context. The
command is `ccx`; Python standard library only.

<p align="center"><img alt="Animated demo, 15 seconds: ccx route picks Codex gpt-6-luna low; ccx run hands the task from Claude Code to Codex and it is done in one attempt; the receipt shows the check ccx ran again (passed), another vendor's review (pass) and the cost; ccx ui shows the same receipt on its page (stand-in CLIs, made-up costs)" src="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/demo.svg" width="100%"></p>

## Compared with doing it yourself and with Claude Code's own sub-agent

**Hold-out set (hc1, 2026-10-29):** on 10 tasks not used while building ccx (× 3 rounds, a sonnet lead, hidden
tests), ccx was not seen to be less right (29/30, against 29/30 and 27/28) and cost less per success than doing it
yourself and than the built-in sub-agent's default usage, but took about 3× the wall time of doing it yourself
([report and limits](https://github.com/SUPERD6/relayline/blob/main/docs/research/2026-10-29-hc1-holdout.md)). **Dev set** (the other rows): round 5, ten real
changes from this repository × 2, a sonnet lead, hidden tests, the sub-agent Codex gpt-6-luna low. Built-in: every run, the lean builtin2 included; ccx: the four runs
after the round-5 fixes (the first run, before them, was 17/20 at $0.248).

| | Lead does it itself | Claude Code built-in sub-agent | ccx → Codex |
|---|---|---|---|
| Right | 19/20 (one run) | 17–19/20 (three runs) | 18–20/20 (four runs, r5e–r5h) |
| Cost per success | $0.211 | $0.114–0.202 | $0.116–0.135 |
| Wall time, median | 94 s | 276–316 s | 236–267 s |
| [Hold-out set](https://github.com/SUPERD6/relayline/blob/main/docs/research/2026-10-29-hc1-holdout.md) (10 tasks × 3): right, cost per success, wall | 29/30, $0.090, 21 s | 27/28, $0.103, 123 s (default usage) | 29/30, $0.063, 61 s |

- **Cost.** On the hold-out set ccx cost about 30 % less per success than doing it yourself and about 39 % less
  than the built-in sub-agent's **default usage**; on its 5 tasks from other repositories (the clean half: this
  repository's own tasks may have their answers in ccx's code) about 15 % / 42 % less. The lean built-in recipe
  (builtin2, the built-in sub-agent given ccx's lean recipe) was not in that run: on the dev set it cost **$0.114**
  per success and beat our latest ccx run (r5h, **$0.135**; ccx's range $0.116–0.135), so between the two ways to
  delegate there is no clear winner yet. On the dev set's larger tasks both were cheaper per success than the lead
  doing them itself.
- **Speed: ccx is slower than doing it yourself**, about 3× on the hold-out set (61 s vs 21 s; the built-in
  sub-agent's default usage took 123 s), 2.5–2.8× the lead's own wall time on the dev set, about 3× on the small
  tasks of round 1 (34 s vs 11 s) and about 4.5× on round 3's harder, vaguer small-package tasks with fresh short
  leads (63 s vs 14 s): 2.5–4.5× in all. On smaller tasks the total
  spend was about even with doing it yourself in rounds 1 and 4 and higher in round 3 ($0.071 vs $0.045 per success).
- **What ccx adds over the built-in sub-agent:** the work runs on another vendor's model and quota; ccx re-runs your
  `--check` itself instead of trusting the report; a different vendor reviews the diff; every run's cost goes into a
  ledger; `ccx undo` reverts a run.
- **How often the receipt is wrong:** receipt false "right" 8/209 (3.8 %, after #158, evaluations up to 3a15b8b),
  above the 2 % bar and listed as a must-fix before release; being fixed. Those 8 receipts said right while the hidden
  tests failed, because the check passed without testing what the hidden test asked for. The other way round, 47 of
  51 receipts that said wrong were in fact right, most of them a failed review
  ([verdict audit](https://github.com/SUPERD6/relayline/blob/main/docs/research/2026-10-31-verdict-audit.md)).
- **Real use so far:** almost none. In one week the real hub had 283 runs, but only 5 (3–5 tasks) were work outside
  ccx's own tests ([dogfood](https://github.com/SUPERD6/relayline/blob/main/docs/research/2026-10-31-dogfood.md), real use, not a controlled experiment).
- **One ledger across vendors:** every sub-agent run and its own child sessions, Claude and Codex in one book (verified live on 2026-10-30 with codex-cli 0.164.0: a Codex sub-agent asked via `--parallel` started 3 child sessions with `spawn_agent`, and the ledger's run total equalled parent + 3 children exactly, field by field). Claude Code itself has `/context` and `/cost` for its own session; what ccx adds is one book across both vendors plus a per-part breakdown of what the lead re-reads each turn (read from the lead's own session file, not from the ledger) (`ccx lead --breakdown`, and the `ccx ui` page "Measured & where tokens go").
- **Honest measurement:** negative results are published too (ccx is slower; on small tasks it saved nothing; a lean built-in recipe beat it on the dev set), every number carries its limits, and the benchmark can be re-run: tasks, hidden tests and scripts are in the repository ([docs/measured.md](docs/measured.md), [scripts/eval/](scripts/eval/); a standalone `bench/` package is being prepared).
- **Limits:** the hold-out run had 10 tasks and only a sonnet lead, its prices are API-equivalent, and "not seen to
  be less right" is not a statistical non-inferiority test. The dev-set tasks were also used while fixing ccx, the
  lead doing it itself was not re-run after the first run, and round 5 came before the clean-environment checks. Every number, the unfavourable ones and the best-case
  feature A/Bs too: [docs/measured.md](https://github.com/SUPERD6/relayline/blob/main/docs/measured.md).

**Try it without accounts:** `ccx demo` opens `ccx ui` on made-up projects, runs and costs in a temporary
folder (offline, no Claude or Codex login; your own setup is not touched).

<table><tr>
<td width="50%"><img alt="ccx ui, one hand-off's receipt: Codex gpt-6-luna low did it, cost $0.0051 with its review, the check ccx ran again passed, Claude haiku's review passed, the files actually changed from ccx's own snapshots (ccx demo data)" src="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/ui/task-en.png"></td>
<td width="50%"><img alt="ccx ui, where tokens go: one ledger across Claude, Codex and DeepSeek, requests per run, a Codex helper session under its run (ccx demo data)" src="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/ui/tokens-en.png"></td>
</tr><tr><td align="center">Every hand-off's receipt</td><td align="center">Where the tokens went</td></tr></table>

## Quick start

```bash
claude plugin install relayline --marketplace SUPERD6/relayline   # the skills and hooks in Claude Code (2.1.275+)
pipx install git+https://github.com/SUPERD6/relayline             # ccx itself, for your terminal and Codex
ccx setup                    # guided: explains each step and asks before changing anything
ccx run --to codex --mode read "Summarise README.md in three lines for a new user: what this project does, how to install it, and the first command to try"
```

The last line is a read-only first try: Codex reads this README and answers in three lines, on the cheapest model.
From your own terminal, `--to` delegates even a very small task (stderr notes that doing it yourself is cheaper);
when a lead session calls ccx, a task that small is still turned back to it.
The hub `ccx setup` asks about is one folder of your own for shared memory, skills and the record of every run.

Then the job ccx is for, a chore with a check that says whether it is done (in your project, with your test command; the test file the `--check` names must already exist, or ccx stops before starting the sub-agent):

```bash
ccx run --to codex --check "python -m pytest -q tests/test_dates.py" --review on "parse_date() rejects ISO dates that end in Z; make it accept them and add a case for it to tests/test_dates.py"
ccx undo <run_id>            # if you don't want it: shows what would be restored; --apply restores it
```

ccx passes the run only when your `--check` passes when ccx runs it itself; `--review on` has another vendor's model
read the diff; the JSON result carries the run id, the check, the review and the cost. A run that may edit files and
has no `--check` gets a one-line reminder on stderr.

You need Python 3.11+ and the `claude` and `codex` CLIs, logged in; DeepSeek (`dsh`, or a key in
`DEEPSEEK_API_KEY`) is optional. `ccx -h` lists the everyday commands (run, resume, show, verify, q, undo, ui, mem, ...); `ccx advanced` (same as `ccx -h --all`) lists every group: the ones agents call to each other (board, say, reply, peek), the advanced ones (hub, several projects, install), maintenance, and the developer ones (trial, ab, bench) last, which also run as `ccx dev <command>`. Nothing was removed: old command lines work as before ([commands](https://github.com/SUPERD6/relayline/blob/main/docs/features.md#commands-everyday-first-nothing-removed)).

## What else it does

The same seven things as [docs/features.md](https://github.com/SUPERD6/relayline/blob/main/docs/features.md), in one line each: (1) Claude Code, Codex and
DeepSeek as each other's lead and sub-agent; (2) models talking directly (`ccx ask`, `ccx discuss`, the board);
(3) shared memory and working context; (4) splitting the work and routing each piece by difficulty and cost;
(5) a slim sub-agent start-up and `ccx lead` for what the lead re-reads; (6) checks, cross-vendor review and a verdict
for every run; (7) you stay in control (`ccx undo`, `--worktree`, `ccx ui` with confirmed buttons).

**Switching leads.** Claude Code did the first half and Codex should do the rest (or the other way round)? On a
project's page in `ccx ui`, "Continue with Codex" / "Continue with Claude" runs `ccx handoff` for that project
after a second click: it writes what is done, the decisions and what comes next into the project (from the current
lead's own conversation file when it is there) and gives you the one line to paste when you open the other tool
there. The task timeline shows which lead worked when.

## Who works with whom

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/architecture-dark.svg">
  <img alt="Architecture: Claude Code, Codex and DeepSeek connect to ccx, each can lead or take work; a lead hands a brief to another, which runs headless and returns JSON; ccx routes, reruns the check, asks another vendor to review, and writes a receipt for every delegated run (cost, check, review, verdict, undo) into the ledger, and reads the other tools' sessions for the shared working context; below: the personal layer (hub: shared memory, skills, MCP, ledger), the project layer (.ccx: context.md, journal, board, handoffs, checkpoints, undo snapshots, queue) and ccx ui, a local page with the receipts and where tokens go. Gemini CLI: a worker adapter, not run for real" src="https://raw.githubusercontent.com/SUPERD6/relayline/main/docs/assets/architecture-light.svg" width="100%">
</picture>

| | Lead | Takes work |
|---|---|---|
| Claude Code | yes | yes |
| Codex | yes | yes |
| DeepSeek (`dsh`, or through Claude Code; as a sub-agent also through Codex) | yes | yes |
| Gemini CLI; Kimi, GLM, Qwen, OpenRouter through Claude Code | no | experimental: adapted, not run for real |

All "yes" cells ran for real on one Windows machine. **Experimental**, the main ones (not run for real; said so where
each is described, and STATUS says how each is tested): Gemini CLI, a real quota stop, macOS and Linux (CI only, no real
agent CLIs), installing the Codex plugin from a GitHub address, `ccx intake` against real GitHub; the full list is
in STATUS. Still work in progress (the release badge above says which version): what is verified and how is in
[docs/STATUS.md](https://github.com/SUPERD6/relayline/blob/main/docs/STATUS.md).

## More

| Page | What is there |
|---|---|
| [What it does, and how](https://github.com/SUPERD6/relayline/blob/main/docs/features.md) | the seven things in detail, `ccx ui`, one example end to end, where shared things live, tiers, safety |
| [Install and commands](https://github.com/SUPERD6/relayline/blob/main/docs/install.md) | install from a clone, plugging in your own setup, every command |
| [Measured](https://github.com/SUPERD6/relayline/blob/main/docs/measured.md) | all measurements with their limits (the hold-out run, the round-5 comparison, the best-case feature A/Bs), how a saving is estimated, external facts checked |
| [Public benchmark](https://github.com/SUPERD6/relayline/blob/main/bench/README.md) | the hold-out and dev tasks, hidden tests and our result rows: re-run the comparison yourself |
| [Shared work context](https://github.com/SUPERD6/relayline/blob/main/docs/shared-context.md) · [The board](https://github.com/SUPERD6/relayline/blob/main/docs/board.md) | what open sessions share with each other, and how |
| [Questions and similar projects](https://github.com/SUPERD6/relayline/blob/main/docs/faq.md) | cost, subscriptions, safety, which tools work; how ccx differs from similar projects |
| [Design](https://github.com/SUPERD6/relayline/blob/main/docs/DESIGN.md) · [Decisions](https://github.com/SUPERD6/relayline/blob/main/docs/DECISIONS.md) · [Changes](https://github.com/SUPERD6/relayline/blob/main/CHANGELOG.md) | the inside |
| [Maintenance](https://github.com/SUPERD6/relayline/blob/main/docs/maintenance.md) | picking ccx up again: known issues, experimental switches and why they are off, running an evaluation, releasing |

**Not the similarly named projects:** relayline was called `claude-codex-bridge`, but it is not
[CCB](https://github.com/SeemSeam/claude_codex_bridge) and not OpenAI's
[codex-plugin-cc](https://github.com/openai/codex-plugin-cc) ([how they differ](https://github.com/SUPERD6/relayline/blob/main/docs/faq.md#similar-projects)).

## Security, contributing, license

What ccx runs and may change, and how to report a problem: [SECURITY.md](https://github.com/SUPERD6/relayline/blob/main/SECURITY.md). Contributing (tests, rules,
adding an adapter for another agent CLI): [CONTRIBUTING.md](https://github.com/SUPERD6/relayline/blob/main/CONTRIBUTING.md) and the
[code of conduct](https://github.com/SUPERD6/relayline/blob/main/CODE_OF_CONDUCT.md). MIT, see [LICENSE](https://github.com/SUPERD6/relayline/blob/main/LICENSE).
