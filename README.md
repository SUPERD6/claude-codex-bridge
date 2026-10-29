<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.svg">
  <img alt="relayline (command ccx): coding agents as each other's lead and sub-agent; a real run: Codex luna/low, done in one attempt, verified, $0.0023" src="docs/assets/banner-light.svg" width="100%">
</picture>

<p align="center">
  <a href="https://github.com/SUPERD6/relayline/actions/workflows/test.yml"><img alt="tests" src="https://github.com/SUPERD6/relayline/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <img alt="dependencies: standard library only" src="https://img.shields.io/badge/dependencies-stdlib%20only-1f7a3a">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-0f7c80"></a>
  <a href="https://github.com/SUPERD6/relayline/releases"><img alt="release" src="https://img.shields.io/github/v/release/SUPERD6/relayline"></a>
</p>

<p align="center">English · <a href="README.zh.md">中文</a> · <a href="https://superd6.github.io/relayline/">Website</a></p>

# relayline

**One promise: spend less on AI coding.** Claude Code, Codex and DeepSeek become one team that hands work to each
other: each piece goes to the cheapest agent likely to get it right, every piece is checked, and all of them share
memory and working context. The command is `ccx`; Python standard library only.

## Four pillars

| | What ccx does | Measured |
|---|---|---|
| **Save money** | Routes each piece to the cheapest agent, model and effort likely to finish it (or says "do it yourself"); slim sub-agent start-up; `ccx lead` shows what every turn of your lead re-reads. | Delegated tasks that carried the lead's recent work cost **63 % less in all**, with 0 reworks instead of 29 ([A/B](docs/research/2026-10-25-shared-context-ab.md)) |
| **More accurate** | ccx reruns the acceptance check itself, another vendor can review the diff, every run gets a verdict that calibrates routing. | First try right **36/36 with the shared work context vs 7/36 without** ([A/B](docs/research/2026-10-25-shared-context-ab.md)) |
| **Split the work** | A five-question difficulty score picks agent, model and effort; the lead keeps only the summary; any of the three can lead. | The lead made **one request fewer on every task, 21/21**, after delegating ([seven-cores A/B](docs/research/2026-10-24-seven-cores-ab.md)) |
| **Share** | Project and personal memory, handoffs between leads, a shared work context (`ccx run --context`, `ccx peek`), a board open sessions write to. | A project note reached the sub-agent and was followed: **9/9 right with it, 0/9 without** ([seven-cores A/B](docs/research/2026-10-24-seven-cores-ab.md)) |

**Read the numbers with their limits.** They come from small, controlled tasks on one machine. The shared-context
A/B is that feature's best case by design. Delegating small tasks *alone* left the total spend about even (ratio 1.02,
3.3× the tokens, about 23 s slower); the saving with a real, long lead conversation is extrapolated, not yet measured.
Every number, the unfavourable ones too: [docs/measured.md](docs/measured.md).

**Try it without accounts:** `ccx demo` opens `ccx ui` on made-up projects, runs and costs in a temporary
folder (offline, no Claude or Codex login; your own setup is not touched).

## Quick start

```bash
claude plugin install relayline --marketplace SUPERD6/relayline   # the skills and hooks in Claude Code (2.1.275+)
pipx install git+https://github.com/SUPERD6/relayline             # ccx itself, for your terminal and Codex
ccx setup                    # guided: explains each step and asks before changing anything
ccx run --to codex --mode read "Summarise README.md in three lines for a new user: what this project does, how to install it, and the first command to try"
```

Your first delegation is the last line: Codex reads this README and answers in three lines, on the cheapest model.
From your own terminal, `--to` delegates even a very small task (stderr notes that doing it yourself is cheaper);
when a lead session calls ccx, a task that small is still turned back to it.
The hub `ccx setup` asks about is one folder of your own for shared memory, skills and the record of every run.

You need Python 3.11+ and the `claude` and `codex` CLIs, logged in; DeepSeek (`dsh`, or a key in
`DEEPSEEK_API_KEY`) is optional. `ccx -h` lists the commands you type (run, resume, show, q, undo, ui, ...); `ccx -h --all` also lists the ones agents call to each other (board, say, reply, peek), the advanced and maintenance ones, and the developer ones (trial, ab, bench) last.

**Switching leads.** Claude Code did the first half and Codex should do the rest (or the other way round)? On a
project's page in `ccx ui`, "Continue with Codex" / "Continue with Claude" runs `ccx handoff` for that project
after a second click: it writes what is done, the decisions and what comes next into the project (from the current
lead's own conversation file when it is there) and gives you the one line to paste when you open the other tool
there. The task timeline shows which lead worked when.

<p align="center"><img alt="Animated demo: ccx route picks codex:gpt-6.1-sol:medium, ccx run finishes in one attempt and ccx reruns the check, ccx verify records the verdict" src="docs/assets/demo.svg" width="100%"></p>

## Who works with whom

| | Lead | Takes work |
|---|---|---|
| Claude Code | yes | yes |
| Codex | yes | yes |
| DeepSeek (`dsh`, or through Claude Code; as a sub-agent also through Codex) | yes | yes |
| Gemini CLI; Kimi, GLM, Qwen, OpenRouter through Claude Code | no | adapted, not run for real |

All "yes" cells ran for real on one Windows machine; macOS and Linux run in CI only. This is v0.5, work in progress:
what is verified and how is in [docs/STATUS.md](docs/STATUS.md).

## More

| Page | What is there |
|---|---|
| [What it does, and how](docs/features.md) | the seven things in detail, `ccx ui`, one example end to end, where shared things live, tiers, safety |
| [Install and commands](docs/install.md) | install from a clone, plugging in your own setup, every command |
| [Measured](docs/measured.md) | all measurements with their limits, how savings are counted, external facts checked |
| [Shared work context](docs/shared-context.md) · [The board](docs/board.md) | what open sessions share with each other, and how |
| [Questions and similar projects](docs/faq.md) | cost, subscriptions, safety, which tools work; how ccx differs from similar projects |
| [Design](docs/DESIGN.md) · [Decisions](docs/DECISIONS.md) · [Changes](CHANGELOG.md) | the inside |

**Not the similarly named projects:** relayline was called `claude-codex-bridge`, but it is not
[CCB](https://github.com/SeemSeam/claude_codex_bridge) and not OpenAI's
[codex-plugin-cc](https://github.com/openai/codex-plugin-cc) ([how they differ](docs/faq.md#similar-projects)).

## Security, contributing, license

What ccx runs and may change, and how to report a problem: [SECURITY.md](SECURITY.md). Contributing (tests, rules,
adding an adapter for another agent CLI): [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md). MIT, see [LICENSE](LICENSE).
