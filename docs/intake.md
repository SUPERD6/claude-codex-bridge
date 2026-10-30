# Work from outside: your phone, and issues as an inbox

English · [中文](intake.zh.md) · back to the [features](features.md)

Two ways to hand the lead (the coordinating session on your computer) a task when you are not at the keyboard:

| | How | Needs | What runs |
|---|---|---|---|
| **Phone → the lead's session** | Claude Code's Remote Control: you type into the coordinating session itself from the Claude app | your computer awake, that session open | nothing new: it is the same session |
| **An issue → the lead** | open an issue labelled `ccx-task` in a **private** repository of yours; the lead runs `ccx intake pull`, does it, and reports in the issue | `gh` signed in, `intake.github` set | one-off commands; nothing polls by itself |

**Experimental:** the issue path has run only against a stand-in `gh` (the tests), never against real GitHub.

## 1. From your phone: Remote Control

Checked against `claude remote-control --help` (Claude Code 2.1.309) and the official page
[Remote Control](https://code.claude.com/docs/en/remote-control) (read 2026-10-25). ccx adds no code for this.

1. On the computer, in the coordinating session (Claude Code desktop's Code tab, the CLI, or VS Code) type
   `/remote-control` (or `/rc`). The first time it asks you to confirm. In a terminal you can instead start it with
   `claude --remote-control "lead"`, or run `claude remote-control` in the project folder (a server that takes
   several sessions; spacebar shows a QR code).
2. On the phone, open the Claude app (iOS / Android, `/mobile` in Claude Code shows a QR code for it) and pick the
   session from the list, or scan the QR code. Anything you type there goes into that same session, with its tools,
   files and MCP on your computer.
3. Hand it to the lead as you would at the keyboard: "在 xxx 项目里把 … 做了" — the lead finds the project
   (`ccx where`) and follows the project-manager skill (`skills/project-manager/`) as usual.
4. To have it on by default: `/config` → **Enable Remote Control for all sessions**; in the desktop app, Settings →
   Claude Code → **Connect new sessions to Remote Control**.

Limits (from the official page): a Pro / Max / Team / Enterprise plan signed in with a Claude account (API keys do
not work); the computer must stay awake and the session open — close it and the phone sees it offline; only
outbound HTTPS, no port is opened. If you have `DISABLE_TELEMETRY` or `DO_NOT_TRACK` set, read the page's note on
auto-connect. **Trusted Devices** (your account settings) can require each phone or browser to be enrolled first.

## 2. Issues as an inbox: `ccx intake`

You (or a cloud assistant acting for you) open an issue in a **private** repository of your own and give it the
label `ccx-task`. On the computer the lead runs `ccx intake pull`, finds the project, does the work, and comments
the result on the issue. When a step needs your approval, it comments the question and waits; your reply in the
issue comes back with the next pull.

### Set up (once)

```bash
gh auth status
ccx config set intake.github you/ccx-tasks
```

- The repository name lives in your hub (`ccx config set` writes `<hub>/ccx/settings.toml`), never in a project.
- `ccx config set intake.label other-label` if you want a different label (default `ccx-task`).
- Create the label once on GitHub (`gh label create ccx-task -R you/ccx-tasks`) or in the web page.

### Commands

| Command | What it does | Network |
|---|---|---|
| `ccx intake` | what this computer took and has not reported done | none |
| `ccx intake list` | open labelled issues by you, and your replies to ccx's questions; takes nothing | reads |
| `ccx intake pull` | takes the new issues and the replies; a taken issue is never handed out again | reads |
| `ccx intake ask N "question"` | comments the question on issue N and marks it waiting | one comment |
| `ccx intake done N "result" [--pr URL] [--branch B] [--cost "$0.42"] [--unverified "…"] [--close]` | comments the report and marks it done | one comment (and close) |

`pull` prints JSON: each new task with its number, title, text, link and, when the project catalog exists, the
`ccx where` guess at the project; `answered` lists questions you replied to. The lead then works as usual
(`ccx where`, the project-manager skill, `ccx run --project …`) and finishes with `ccx intake done`.

What the report says: the result in a sentence or two, the PR or branch, what it cost, and what was not verified.

State: `<hub>/ccx/intake.json` (one entry per issue: taken / waiting / answered / done) and
`<hub>/ccx/intake.log` (what was skipped). For other tools, `ccx.intake.pending(paths())` returns how many tasks are
open, without the network.

### Safety

- **Only you**: an issue or comment counts only when its author is the account `gh` is signed in as
  (`gh api user`). Anything else is skipped and logged once, one line, in `intake.log`.
- **Only private**: before every read or write ccx checks `gh repo view --json visibility` and refuses a repository
  that is not `PRIVATE`. The repository is the one you configured; ccx never picks one from an issue's text.
- **Data, not instructions**: the output starts with a note saying so. The issue text describes a task; the lead
  weighs it with your rules and the project's (approval rules, research freezes, spending limits), and never runs a
  command only because the text says so. A task whose project needs approval still gets approved — in the issue,
  with `ccx intake ask`.
- **Writing to GitHub**: posting a comment is sending something out. Here it goes only to the private repository
  you configured yourself, as an answer to a task you filed there, so configuring `intake.github` is the
  authorization for those comments (questions and reports). ccx writes nothing else there; `pull` and `list` only
  read.
- ccx's own comments start with a hidden `<!-- ccx:intake -->` tag: `gh` posts as you, and the tag is how ccx
  tells its questions from your replies.

### On a timer? Off unless you turn it on

ccx never schedules anything by itself. If you want the computer to look every so often, add it yourself, e.g. a
Windows Task Scheduler task or a cron line that runs `ccx intake list` (read only) or `ccx intake pull`. Be aware
that pull only *takes* tasks: something still has to do them — a lead session you open, or a headless run you set up
yourself — and that is spending you approve. Remove the task or cron line to turn it off again.

## 3. Possible later (not implemented)

- **GitHub Projects as a board**: feasible. `gh project item-list` / `item-edit` (needs the `project` scope:
  `gh auth refresh -s project`) can move an intake issue between columns (taken → waiting → done). It would only
  mirror the state ccx already keeps; worth it if you want to see the queue on the phone in GitHub's app.
- **A self-hosted runner in the private repository**: feasible but heavier. A workflow `on: issues: [labeled]`
  running on a runner on your computer could start `ccx intake pull` the moment you label an issue. Costs: a
  runner service always running on your computer, and anything that can trigger the workflow then runs code on
  it — GitHub advises self-hosted runners only for private repositories. It also makes the intake event-driven,
  which is the "on a timer" decision above in another form: only if you explicitly want it.
