# Contributing

English · [中文](CONTRIBUTING.zh.md)

Thanks for helping. ccx is small on purpose: Python 3.11+, standard library only, and every claim about an external
CLI checked against that CLI. Please keep it that way.

## Before you start

- Bugs and ideas: open an issue (templates are provided). Security problems: see [SECURITY.md](SECURITY.md), not a
  public issue.
- Bigger changes: open an issue first, so we agree on the shape before you write it.
- Where things stand and what's next: [docs/STATUS.md](docs/STATUS.md). Design and reasons:
  [docs/DESIGN.md](docs/DESIGN.md), [docs/DECISIONS.md](docs/DECISIONS.md). Known issues, the switches that ship off
  and how to run an evaluation: [docs/maintenance.md](docs/maintenance.md).

## Set up

```bash
git clone https://github.com/SUPERD6/relayline
cd relayline
python -m pip install -e . pytest
python -m pytest -q tests            # must pass before every commit
```

The tests never call a real agent: `tests/fakes/` holds stand-in `codex`, `claude` and `gemini` CLIs that speak the
same event formats. A pull request runs them on Windows 3.11 and Ubuntu 3.13 and builds the wheel on Ubuntu; every
push to main (and every version tag) runs Linux, Windows and macOS × Python 3.11–3.13 and checks the wheel on all
three (it installs the wheel and runs the installed `ccx`, `tests/smoke_installed.py`).

## Rules

- **Tests with every change.** A fix comes with a test that fails without it.
- **Tests don't depend on the clock, the date or timing.**
  - Code that reads the time takes it as a parameter (`now=`, as `tokenflow.since_of(period, now)`), and the test
    passes a fixed one. A test that used "now − 60 s" as today failed in the first minute after midnight (#193).
  - Don't hard-code a date that a time window is measured against; build it from that fixed now. A test with a
    written-out 2026-10-24 timestamp failed once it fell out of a 7-day window (#190).
  - Concurrent code is tested with a fixed interleaving: mock the slow call and hold a lock or barrier, as
    `tests/test_worktree_race.py` does. Never sleep or raise a timeout to make a race go away.
  - Tests that start real processes on the same repository or hub run them one after another (a fixture that
    serializes them), not side by side.
- **Keep the core.** Commands and options are not removed; a PR that changes one says in a line what it kept and how
  that was checked. Paths not run for real are called experimental where they are described.
- **Nothing personal in the repo**: no names, local paths, e-mail addresses, machine names or data. Personal things live in the
  user's hub. `tests/test_repo_hygiene.py` checks every tracked file (text, and the strings inside images) on every
  push; look at screenshots yourself too, since a path drawn in the pixels is not caught.
- **Two languages for docs**: `x.md` (English) and `x.zh.md` (Chinese), linking to each other. Record real decisions
  in `docs/DECISIONS.md`.
- **One change note per PR**: add `changes/<PR number>.md` with the lines for the CHANGELOG instead of editing
  `CHANGELOG.md` (see [changes/README.md](changes/README.md)); they are folded in when releasing, so parallel PRs
  don't conflict. `docs/STATUS.md` is kept by the maintainers.
- **Check external facts**: a flag, event field or price you rely on must be confirmed with `--help` or official docs;
  note the version you checked (`TESTED_VERSIONS` in `ccx/runners.py`, the "External facts" section of [docs/measured.md](docs/measured.md)).
- **Never touch credentials**, and never edit a tool's config outside ccx's marked blocks.
- Small commits with clear messages; behaviour changes go in the PR's change note.

## Adding an adapter for another agent CLI

Copy `ccx/agents/_template.py` (a working skeleton with notes) and `tests/fakes/fake_template.py`; Gemini CLI
(`ccx/agents/gemini.py`) is a real example.

1. `ccx/agents/<agent>.py`: the argv for a headless run (resume and permission flags) and the parser of its output
   (status, JSON result, usage in the four buckets of `usage_dict`, session id, failure kind), in an `ADAPTER` with
   `support="community"` and the version you checked in `tested_version`. Add the name to `NAMES` in
   `ccx/agents/__init__.py`.
2. `ccx/config.py`: add the agent to `DELEGATE_AGENTS`.
3. `config/tiers.toml`: a model and effort per tier, and `[permissions.<agent>]` for `read` and `write`.
4. `skills/task-routing/data/priors.toml`: rungs (model, effort, ability) and prices, with the source of the prices.
5. `tests/fakes/fake_<agent>.py`: a stand-in that prints the same events as the real CLI, and tests like
   `TestGemini` in `tests/test_adapters.py`.
6. Run it once against the real CLI and say so in the PR (version, what you ran, what came back).

## Pull requests

Describe what changed and why, how you tested it, and anything you could not test. The template asks for exactly
that. By contributing you agree that your work is released under the [MIT license](LICENSE) and that you follow the
[code of conduct](CODE_OF_CONDUCT.md).
