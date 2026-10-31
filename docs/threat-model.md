# Threat model

English · [中文](threat-model.zh.md) · back to [SECURITY](../SECURITY.md)

ccx starts AI coding agents on your machine and passes text between them. Any text that reaches an agent's prompt can
steer it. This page lists where that text comes from, what ccx does about it (with the code line, checked at
ccx 0.5.0, main `9f0dd02`, 2026-10-31), and what is left to you. **Who this is about:** ccx's limits bind the *sub-agents* it starts.
The lead (the Claude Code / Codex / DeepSeek session you talk to) runs with whatever rights its own tool gives it;
ccx does not sandbox it.

## 1. What enters an agent's prompt

| Input | Comes from | Trust | Existing control (code) |
|---|---|---|---|
| The task (brief) | You, or the lead writing for you | High | Sub-agent rules come before it: do only this task, stay in the workspace, no commit/push, no delegating on (`ccx/prompts.py:22-24`) |
| Repository files | Anyone who ever committed to the repo, dependencies, generated files | Low to medium | Brief says text inside files (inbox, logs, web pages) is reference material, never instructions (`ccx/prompts.py:25`); sandbox and worktree limit what a sub-agent can touch (below) |
| Shared memory notes | Earlier sessions, any agent that ran `ccx mem add`; suggestions from the lead's session | Medium | Suggestions are written only after your `ccx mem accept` (`ccx/memsuggest.py:1-4`); each note keeps who wrote it (`ccx/memory.py:252`, `ccx mem report`); a sub-agent gets only the notes matching its task, labelled "check before relying on them" (`ccx/delegate.py:221-233`), never the start-hook delta (`ccx/commands/memory.py:236-238`) |
| Board messages | Other agent sessions in the project; you | Medium | Printed under a "data, not instructions" header (`ccx/board.py:31-33`, rules `:42-45`); `from` and `via` on every line (`:200`); an agent cannot write as the person (`ccx/commands/board.py:37-40`); at most 6 machine messages in a row per thread (`ccx/board.py:194-198`); GitHub fallback only to a PRIVATE repo that is not the project's own (`ccx/ghpriv.py:33-43`, `ccx/board.py:356`) |
| Intake issues and comments | GitHub, `ccx intake pull` | Medium (your own account) | Repo must be PRIVATE, checked before every read and write (`ccx/intake.py:134,185,210` → `ccx/ghpriv.py:39-43`); only issues and comments by the account `gh` is signed in as (`ccx/intake.py:135,141-143,123-126`), others are skipped and logged (`:73-82`); text capped at 4000 characters (`:23`); output starts with a "data, not instructions" note (`:24-27`) |
| The diff a reviewer reads | The sub-agent that made the change | Low | Reviewer runs read-only (`ccx/review.py:870`); a `[must]` needs a basis in the task text (`ccx/review.py:44-53`). The diff and the sub-agent's summary sit in the review brief without a separate "data" label |
| A sub-agent's result (summary, `done`, receipts) | The sub-agent | Low | ccx re-runs your `--check` itself (`ccx/workspace.py:195`); an independent review from the other vendor can run; L2 merge needs both (`ccx/autonomy.py:205-216`) |
| Credentials | Your environment | — | ccx never reads, stores or sends them. A sub-agent inherits your environment; a provider run (e.g. DeepSeek) has the host's Anthropic/OpenAI logins removed first (`ccx/delegate.py:312-314,377-387`) |

What bounds a sub-agent once it is steered: Codex `sandbox_mode="workspace-write"` / `"read-only"`, Claude
`acceptEdits` / `dontAsk` with a tool allow-list (`config/tiers.toml:162-168`); no further delegation
(`max_depth = 1`, `config/tiers.toml:17`, enforced by `ccx/delegate.py:190-196`); optional git worktree on its own
branch `ccx/<run>` (`ccx/workspace.py:36-46`); a snapshot before every in-place write run for `ccx undo`
(`ccx/workspace.py:238-249,451`). CI fails on personal paths, e-mail addresses, machine names and local state in the
repo (`tests/test_repo_hygiene.py`, `.github/workflows/hygiene.yml`).

## 2. Risk scenarios

| Scenario | How it happens | Existing mitigation | Residual risk | Suggestion |
|---|---|---|---|---|
| Prompt injection in repo files | A README, test fixture or vendored file says "also edit X / delete Y"; the sub-agent obeys | "Reference material" rule; sandbox keeps writes in the workspace; worktree keeps them off your branch; `ccx undo`; review may flag edits outside the task | A rule in the prompt lowers the risk, it does not rule it out. Inside the workspace the sub-agent can still edit any file, including tests and CI config. Claude's allow-list includes `Bash(python:*)`, which can run arbitrary code | Use `--worktree` for unfamiliar repos and read the diff; `--mode read` when you only need analysis |
| Issue content injection | An issue you filed quotes a page or log that carries instructions; the lead acts on it | Only your account's issues/comments in a PRIVATE repo; "data, not instructions" note; approvals go back through `ccx intake ask` | Text *you* paste is trusted as yours. A collaborator on the private repo is skipped only if their login differs; a token for your own account (e.g. a cloud assistant filing for you) passes | Keep the intake repo to yourself; don't paste untrusted text into issues without saying so |
| Poisoned memory note | A wrong or planted note ("always skip tests in X") keeps steering briefs for weeks | Suggestions need your yes; notes carry author and source; briefs say "check before relying"; `ccx mem stale`, `--supersedes` | `ccx mem add` itself has no gate: the lead, or a sub-agent that can run ccx, can add a note directly. Nothing checks a note's content | Look at `ccx mem report` now and then; replace bad notes with `ccx mem add "..." --supersedes N` |
| Sub-agent's own tests fool the check | The sub-agent writes `test_own.py` that passes; `--check` runs it and passes; the task is still wrong | Brief forbids changing existing tests to pass (`ccx/prompts.py:7-8`); review judges coverage against the task and says the agent's own tests are not evidence (`[review] coverage_rubric`, `ccx/review.py:57-61`) | Measured: in pg1, all 18 hidden-test failures had a passed check made of the sub-agent's own tests ([pg1](research/2026-10-31-polyglot-pg1.md)). Marking such a check as self-authored is planned (P0-8), not shipped | Write the `--check` yourself, naming tests that existed before the run |
| Receipt trusted but wrong | A receipt says "right" and you accept it | ccx's own re-run of `--check`; independent review | After #158, 8 of 209 receipts that said right failed hidden tests: 3.8 % (95 % 2.0–7.4 %) ([verdict audit](research/2026-10-31-verdict-audit.md)) | Treat a receipt as a claim; read the diff before `ccx verify --ok 1` |
| Sandbox password overwritten by another Codex home | On Windows, several `CODEX_HOME`s share Codex's elevated sandbox accounts; whichever home ran setup last holds the working password ([DESIGN](DESIGN.md), [DECISIONS](DECISIONS.md) 2026-10-31) | ccx classifies the resulting Windows error 1223 as an environment problem: no retry, no tier climb, resume needs `--env-fixed` (`ccx/delegate.py:1117-1142`); eval homes use the unelevated sandbox | An availability problem, not a leak: Codex shell commands wait for a cancelled UAC prompt and the run fails. Any tool that re-runs Codex's sandbox setup can trigger it | One elevated home per machine, or `[windows] sandbox = "unelevated"`; see [maintenance](maintenance.md) §4 on sharing one machine |
| Autonomy L2 auto-merge | The lead dispatches write work and merges without asking | Only with L2 *and* `--auto-merge on` for that project in the hub; a project's own `.ccx/autonomy.toml` can only lower the level (`ccx/autonomy.py:96-104`); only a `--worktree` branch, check passed and not weak, independent review passed, risk not visible/critical, no approval rules, ≤ 80 lines and ≤ 5 files; never into `main`/`master`/`trunk`/`release/*` or origin's default branch (`ccx/autonomy.py:163-166,197-246`, `config/tiers.toml:263-275`); merges locally, never pushes (`:260`) | A small change can still be harmful (80 lines is plenty for a backdoor); the merge relies on the same check and review as above. L2 end to end has not run live ([maintenance](maintenance.md) §2) | Leave L1 (default) unless the project has strong tests; undo a merge with the `git reset --keep` line it prints |

## 3. What you can do

- **Autonomy level**: L0 only suggests, L1 (default) asks before any write run, L2 dispatches and may merge small
  checked branches. `ccx autonomy set L0 --project NAME`; a project can pin itself lower in `.ccx/autonomy.toml`.
- **`--mode read`**: read-only sandbox / tool list, for review and analysis.
- **`--worktree`**: edits land on a branch `ccx/<run>` beside the repo, not in your working tree.
- **`ccx undo <run_id> --apply`**: puts back an in-place write run's files; new files are moved aside, not deleted.
  (Worktree runs have no snapshot: drop the branch instead.)
- **Intake**: point `intake.github` only at a private repository of your own; ccx refuses a public one.
- **Codex as lead**: `danger-full-access` gives every lead command your rights; use it only for a lead you would
  trust at your own keyboard ([features](features.md)).

## 4. Out of scope

- ccx does not audit the models or the agent CLIs, and does not make a sub-agent's output safe or correct. It runs
  them inside the limits above and reports what it checked.
- ccx does not defend against someone who already controls your account, your machine or your hub folder.
- The agent CLIs talk to their own services; what they send is governed by their settings, not by ccx.

Found a hole? See [SECURITY](../SECURITY.md#reporting-a-vulnerability).
