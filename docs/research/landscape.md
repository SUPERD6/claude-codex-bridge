# Research: living with the official plugin, similar projects, name options (2026-10-24)

[中文](landscape.zh.md) (the Chinese version is the primary one; this is a faithful translation)

Covers proposals J8 (coexisting with the official codex-plugin-cc), J9 (similar projects) and J10 (name options).

**How and when checked:** every GitHub number here (stars, last push, license, creation date) was read on
**2026-10-24** from the GitHub API (`gh api repos/<owner>/<repo>`, `gh search repos`) and will change. PyPI names were
checked the same day by the status of `https://pypi.org/pypi/<name>/json` (200 = taken, 404 = free). Anything without a
first-hand source is marked "unconfirmed". **No plugin was installed** for this; what needs a real test is listed at the
end of each section.

## Summary

1. **The official plugin exists.** `openai/codex-plugin-cc`, created and released as v1.0.0 on 2026-03-30, Apache-2.0,
   ~34.5k stars, latest v1.0.6 (2026-07-08). It lets Claude Code call Codex for reviews, delegated tasks, moving the
   session to Codex and managing background jobs.
2. **It overlaps with ccx only on the Claude → Codex side.** It does not pick models (without `--model`, Codex uses its
   own defaults), does not record tokens or cost, has no Codex → Claude direction, no lead-cost view and no other
   providers. Coexistence plan: when it is installed, point reviews and session moves to it; ccx keeps routing,
   calibration, accounting, the lead's cost and the other providers (section 1.4).
3. **Many similar projects, each with its own focus.** Closest are PAL MCP's `clink` (calling another CLI from MCP) and
   CCB (`SeemSeam/claude_codex_bridge`, a visible multi-agent terminal workspace). This search found no other project
   that picks the model by success odds and cost, keeps a ledger and measures the lead's own cost; that is what this
   search found, not proof there is none.
4. **A rename is worth considering.** GitHub already has a 3,595-star, almost identically named
   `SeemSeam/claude_codex_bridge` and at least six other `claude-codex-bridge` repos, and the current name carries two
   vendors' product names. Section 3 lists eight options for the user to decide; this change renames nothing.

## 1. J8: OpenAI's official codex-plugin-cc

### 1.1 Facts

| Fact | Detail | Source |
|---|---|---|
| Name | repo `openai/codex-plugin-cc`; marketplace `openai-codex`, plugin `codex` (install id `codex@openai-codex`) | [repo](https://github.com/openai/codex-plugin-cc), [marketplace.json](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json) |
| Released | repo created 2026-03-30T15:29Z, v1.0.0 published 2026-03-30T16:44Z; OpenAI developer forum post dated 2026-03-30 | [releases](https://github.com/openai/codex-plugin-cc/releases), [forum post](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186) |
| Latest | v1.0.6, 2026-07-08; last push the same day | [releases](https://github.com/openai/codex-plugin-cc/releases) |
| License | Apache-2.0 | [LICENSE](https://github.com/openai/codex-plugin-cc/blob/main/LICENSE) |
| Activity | ~34,536 stars | GitHub API |
| Official docs | only the repo README; no page on developers.openai.com was found (unconfirmed whether one exists) | [README](https://github.com/openai/codex-plugin-cc#readme) |
| Requirements | a ChatGPT subscription (Free included) or an OpenAI API key; Node.js 18.18+; uses the locally installed global `codex`, its login and config | README "Requirements", "FAQ" |
| Install | in Claude Code: `/plugin marketplace add openai/codex-plugin-cc` → `/plugin install codex@openai-codex` → `/reload-plugins` → `/codex:setup` | README "Install" |
| Commands | `/codex:review` (read-only, no focus text), `/codex:adversarial-review` (steerable), `/codex:rescue` (delegate via the `codex:codex-rescue` sub-agent), `/codex:transfer` (imports the current Claude session as a Codex session, prints `codex resume <id>`), `/codex:status`, `/codex:result`, `/codex:cancel`, `/codex:setup` | README "What You Get", "Usage" |
| Model choice | `/codex:rescue` takes `--model`, `--effort`; without them "Codex chooses its own defaults"; `spark` maps to `gpt-5.3-codex-spark`. No automatic choice per task | README, [rescue.md](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/commands/rescue.md) |
| How it calls Codex | wraps the Codex app server (`codex app-server`); not a separate runtime | README "Codex Integration" |
| Job state | `$CLAUDE_PLUGIN_DATA/state/<workspace>-<hash>/` (else `codex-companion/` in the system temp dir), at most 50 jobs | [state.mjs](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/scripts/lib/state.mjs) |
| Hooks | `SessionStart`, `SessionEnd`, `Stop`; the optional review gate uses `Stop`, and the README warns it can loop and drain usage limits quickly | [hooks.json](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/hooks/hooks.json), README |
| Tokens / cost | not in the README; searching `codex-companion.mjs` for `usage`/`token` only hits the help text (main, 2026-10-24). **No accounting seen**, though the whole source was not read line by line | source search |
| Other direction | not in this plugin; the community `sendbird/cc-plugin-codex` (Apache-2.0, 226 stars) goes Codex → Claude | [sendbird/cc-plugin-codex](https://github.com/sendbird/cc-plugin-codex) |
| Old `codex mcp-server` | a secondary report says it was deprecated ([inside.com.tw](https://www.inside.com.tw/article/42196-openai-codex-plugin-claude-code)); no official note found, **unconfirmed**. Locally, codex-cli 0.164.0 `codex --help` lists `mcp` (manage external MCP) and `app-server`, no `mcp-server` | local `--help` |
| Launch-day security issue | one report mentions a branch-name command injection disclosed and fixed on launch day ([noqta.tn](https://noqta.tn/en/news/openai-codex-plugin-claude-code-rival-integration-2026)); single source, **unconfirmed** | — |

### 1.2 Overlap with ccx

| Feature | Official plugin | ccx |
|---|---|---|
| Claude Code → Codex delegation | `/codex:rescue` | `ccx run --to codex` |
| Background, status, result | `--background`, `/codex:status`, `/codex:result`, `/codex:cancel` | `--bg`, `ccx show`, `ccx q` |
| Continue the last Codex session | `--resume` / `--fresh`; open in Codex with `codex resume` | same conversation + folder within an hour continues automatically; `ccx resume <run_id>` |
| Code review | `/codex:review`, `/codex:adversarial-review` | `ccx run --review`, `ccx ask` |
| Move the session to Codex | `/codex:transfer`: Codex's session importer, the whole conversation becomes a Codex session | `ccx handoff`: a written summary the next session reads (the conversation itself does not move) |
| Model choice by difficulty, odds and cost | none (manual `--model`, else Codex defaults) | yes (five-question score + task-routing, calibrated by `ccx verify`) |
| Tokens, cost, quota | not seen | `ccx stats` / `ccx report` / `ccx quota` |
| The lead's own cost | none | `ccx lead`, per-turn hint |
| Codex → Claude, Gemini CLI, DeepSeek | none | yes (Gemini CLI not yet run for real) |
| Shared memory, skills, MCP | uses Codex's own config, no sync | `ccx sync`, `ccx mem` |
| Install | Claude Code plugin marketplace, Node.js | pipx, Python standard library |

### 1.3 Where the official plugin is better (plainly)

- Maintained by OpenAI and evolves with the Codex app-server protocol; ccx drives `codex exec` and parses its JSON.
- `/codex:transfer` moves the **whole** Claude conversation into Codex; ccx's handoff is a summary.
- One-line install, and `/codex:setup` helps install and log in to Codex.
- Far more users, so problems are more likely to be found by someone else first.

### 1.4 Coexistence plan (design, not implemented)

**Principle:** don't compete with it and don't touch its files. ccx only reads whether it is installed; it never calls its
internal scripts, changes its config or installs it for the user.

1. **Detect.** `ccx doctor` and `ccx setup` run `claude plugin list --json` (present in Claude Code 2.1.309; its help says
   "List installed plugins"; the list on the test machine is empty, so **the output's field names are unconfirmed**) and
   look for `codex@openai-codex`. If it can't be read, treat it as not installed, without an error.
2. **When it is installed:**
   - `ccx doctor` adds one line: "Official codex-plugin-cc found: use `/codex:review` for reviews and `/codex:transfer` to
     move a session; ccx handles model choice, accounting and the lead's cost."
   - The agent-delegate skill, with Claude as lead, says who does what: **only a second opinion or a review** →
     `/codex:review` / `/codex:adversarial-review`; **model chosen by cost, a ledger entry, resume and fallback** →
     `ccx run --to codex`.
   - To move a whole conversation to Codex, suggest `/codex:transfer` rather than `ccx handoff`.
   - Codex → Claude, Gemini, DeepSeek, memory/skill sync and `ccx lead` are unaffected.
3. **Not done:**
   - No calls into `codex-companion.mjs` or other internal scripts. They promise no stable interface (a judgment, not an
     official statement) and may break on any upgrade.
   - No reads or writes of its job-state folder.
   - The review gate is never switched on for the user. It and ccx's per-turn hint both hang off Claude hooks, and the
     combination is untested.
4. **Be clear about the accounting gap.** Codex jobs run through the plugin bypass ccx, so they are not in ccx's ledger
   and "what delegating saved" in `ccx report` excludes them. ccx reads `~/.codex/sessions` for the Codex lead's usage;
   the plugin's jobs open with `codex resume`, so they **may** land in that folder too. If they do, ccx would count them
   as Codex lead usage, which is the wrong bucket. Test item 3 below.

### 1.5 Follow-ups that need a real test

To be done on a machine where installing the plugin is fine; not done here:

1. The real output of `claude plugin list --json` once installed, to fix the field detection reads.
2. How many tokens the plugin adds to Claude Code's fixed per-turn context (`claude plugin details codex@openai-codex`
   shows a projected token cost; `ccx lead --breakdown` before/after also works).
3. Whether `/codex:rescue` jobs are written to `~/.codex/sessions`; if so, `ccx lead` / `ccx report` must separate them
   from lead sessions.
4. With both the plugin's and ccx's SessionStart hooks, whether both outputs arrive and how much the start grows.
5. In one repo, `/codex:rescue` then `ccx run --to codex` (and the reverse): do they fight over the same Codex session?
6. With the review gate on: does it interact badly with ccx's per-turn hint?

## 2. J9: similar projects

Only projects directly about Claude Code / Codex calling each other or sharing memory. Stars and dates as of 2026-10-24;
"last push" is GitHub's `pushed_at`. Descriptions summarise each project's README without judging it.

| Project | What it does | Stars | Last push | License | How ccx differs |
|---|---|---:|---|---|---|
| [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | OpenAI's official Claude Code plugin: call Codex from Claude for reviews, delegated tasks, session transfer, background jobs | 34,536 | 2026-07-08 | Apache-2.0 | Claude → Codex only; no model choice, no accounting. See section 1 |
| [sendbird/cc-plugin-codex](https://github.com/sendbird/cc-plugin-codex) | A plugin inside Codex that calls Claude Code for review, rescue and background jobs (the other direction) | 226 | 2026-10-19 | Apache-2.0 | Codex → Claude only; ccx runs both directions through one router and ledger |
| [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server) (PAL MCP, formerly Zen MCP) | An MCP server that brings many model providers (Gemini, OpenAI, OpenRouter, Ollama…) into one CLI, with chat, consensus, codereview and other tools; its `clink` tool starts another CLI as a sub-agent | 11,805 | 2025-12-15 (v9.8.2) | Apache-2.0 (the LICENSE is the Apache 2.0 text; GitHub shows NOASSERTION) | Many models and tools, and "auto model selection" (Claude picks); ccx picks by success odds and cost per success, calibrates on real outcomes and keeps a ledger. PAL uses MCP and API keys; ccx uses the two CLIs' subscriptions |
| [SeemSeam/claude_codex_bridge](https://github.com/SeemSeam/claude_codex_bridge) (CCB) | A visible multi-agent terminal workspace: Codex, Claude, Gemini, Kimi, Qwen and other CLIs (16 families) side by side, message queues between agents, take over any time; a background daemon, a shared project memory file `.ccb/ccb_memory.md`, an Android remote | 3,595 | 2026-10-23 (v8.7.18) | AGPL-3.0 (per its LICENSE file; GitHub shows NOASSERTION) | Focused on visible, take-over-able multi-agent collaboration; ccx is a headless delegation tool focused on model choice, cost and accounting. Its name is almost the same as this repo's |
| [umum-ai/claude-codex-bridge](https://github.com/umum-ai/claude-codex-bridge) | A Claude Code plugin linking MCP tools and Channels to `codex app-server`: start Codex tasks asynchronously, follow progress, add instructions mid-run, stop, continue | 10 | 2026-10-15 | MIT | Instructions can be added while a task runs; ccx continues after a run with `ccx resume`. Claude → Codex only; no model choice or accounting |
| [Jayden-X-L/claude-codex-bridge](https://github.com/Jayden-X-L/claude-codex-bridge) | A two-way audit bridge: one side's finished work goes to the other side's CLI for review, the result returns to the same conversation | 16 | 2026-06-02 | MIT | Focused on mutual review; in ccx a review is one step of delegation |
| Other repos named `claude-codex-bridge` ([Dunqing](https://github.com/Dunqing/claude-codex-bridge) 14, [ZhangYiqun018](https://github.com/ZhangYiqun018/claude-codex-bridge) 13, [keng1304](https://github.com/keng1304/claude-codex-bridge) 11, …) | Mostly MCP servers for Claude to consult Codex, or two-way calls | 7–14 | 2025-09 to 2026-05 | MIT / none stated | Small; similar to the groups above |
| [DaizeDong/claude-codex-memory-sync](https://github.com/DaizeDong/claude-codex-memory-sync) | On one machine, syncs Claude Code's skills, instructions, compatible MCP settings, reviewed hooks and project memory into Codex, with preview, backup and rollback | 1 | 2026-10-24 | MIT | One-way (Claude → Codex) config sync, finer than ccx's (commands and sub-agent roles too); no delegation |
| [conradomateu/mycelium](https://github.com/conradomateu/mycelium), [shakystar/memorize](https://github.com/shakystar/memorize) | Sync skills, MCP and memory across Claude Code, Codex, Gemini CLI and more (mycelium); one shared local project memory for Claude Code and Codex (memorize) | 31 / 14 | 2026-10-24 / 2026-09-24 | MIT / MIT | Memory and config only; ccx's memory serves delegation and injects only the other side's new lines |
| [feiyun0112/AgentBridge](https://github.com/feiyun0112/AgentBridge) | Chat with local Claude, Codex, Gemini and others from WeChat (ACP or CLI) | 28 | 2026-03-24 | none stated | A different job: a person reaches agents through a chat app, not agents delegating to each other |
| [catatafishen/agentbridge](https://github.com/catatafishen/agentbridge) | A JetBrains IDE plugin giving AI coding agents full IDE access | 87 | 2026-10-21 | Apache-2.0 | Same name only, different field |

**About repos named agent-bridge / agentbridge / codex-bridge:** searching GitHub by name, most `agentbridge` and
`codex-bridge` repos connect agents to WeChat, Feishu, Slack or ChatGPT on the web (e.g.
[chenhg5/cc-connect](https://github.com/chenhg5/cc-connect), 16,080 stars), a different kind of tool. The table keeps
only those about agents delegating to each other. The proposal didn't say which "agentbridge" it meant; the two most
common ones are listed, **unconfirmed whether either was the one intended**.

**Where ccx stands (plainly):**

- Seen only in ccx: choosing provider + model + effort by success odds and cost per success, calibrated by `ccx verify`;
  a ledger and dashboard of every run's tokens, cost and quota; measuring what the lead re-reads each turn (`ccx lead`);
  one flow for both directions, plus Gemini CLI and DeepSeek as workers.
- Not in ccx: a visible split-screen workspace (CCB), adding instructions mid-run (umum-ai), multi-provider API consensus
  (PAL), moving the whole conversation into Codex (official plugin), chat-app front ends.
- ccx's weak points: v0.4, 0 stars (2026-10-24); savings not measured yet (stated at the top of the README); Gemini CLI
  never run for real.

## 3. J10: name options (for the user to decide)

**Why consider it:**

- GitHub has the 3,595-star `SeemSeam/claude_codex_bridge` (CCB), differing from this repo's name only by underscores, and
  at least six more `claude-codex-bridge` repos (section 2). Hard to tell apart in search.
- "Claude" is Anthropic's product name and "Codex" is OpenAI's, and ccx no longer works with just those two.
- Not renaming is fine too: say how ccx differs from CCB and the official plugin in the README (that section is now there).

**How checked (2026-10-24):** PyPI by the status of `https://pypi.org/pypi/<name>/json`; GitHub by repository search
`<name> in:name`, noting the total and the most-starred hits. **No trademark database was searched** (USPTO, EUIPO …);
the vendor column only checks whether the name contains Claude, Codex, OpenAI, Anthropic, Gemini, GPT or similar. Check a
trademark database and npm again before renaming.

| Option | Meaning | PyPI | GitHub (in:name) | Vendor name | Pros | Cons |
|---|---|---|---|---|---|---|
| **ccx** (rename the repo to ccx, command unchanged) | the existing command | free | 2,774 repos contain "ccx"; top is ccxt/ccxt (44,556 stars, crypto trading) | none, though "cc" is often read as Claude Code | users already type it; smallest change | very short, drowned by ccxt in search; says nothing about what it does |
| **relayline** | a relay line | free | 5, all 0 stars, unrelated | none | almost unused; "relay" fits delegation | says nothing about cost or accounting |
| **crewcost** | crew + cost | free | 0 | none | no collisions at all; names the cost focus | may suggest CrewAI (a different project); sounds like an accounting-only tool |
| **leadwork** | the lead's work | free | 25, top 2 stars, unrelated | none | says "the lead shouldn't do cheap work" | not a common English word; needs explaining |
| **tandem-agents** | agents in tandem | free (`tandem` is taken) | 2, top 1 star | none | easy to grasp; fits "either side leads" | "tandem" (two) fits less once more providers join; Tandem is many products' name |
| **taskbaton** | a task baton | free | 1, 0 stars | none | almost no collisions; clear metaphor | "baton" is already used by similar projects (next row) |
| **batonpass** | passing the baton | free | 13, top 4 stars | none | clear and memorable | similar projects use names like `agent-baton` (e.g. captpascallv-dev/agent-baton, a lead dispatching task cards to CLIs); easy to confuse |
| **agentledger** | an agent ledger | free (but `agent-ledger` is taken) | 109, top cahcacah/AgentLedger 81 stars | none | names the accounting | collides with existing projects; covers accounting only |

**Not recommended:** `agent-baton` (free on PyPI, but 19 GitHub repos, at least two also about relaying work between
agents, the easiest to confuse), and `baton`, `tandem`, `handoff`, `taskrelay`, `delegato`, `agent-ledger` (all taken on
PyPI).

**If renamed, what changes (for the decision; nothing changed here):** the GitHub repo name (GitHub redirects the old
URL), the package name in `pyproject.toml`, links in the README and website, and the `pipx install git+…` command. The
`ccx` command can stay.

**Decision (2026-10-24): renamed to `relayline`** (the `ccx` command and the `ccx/` package stay). Checked before
renaming, all on 2026-10-24:

| Where | Query | Result |
|---|---|---|
| USPTO [Trademark Search](https://tmsearch.uspto.gov/) | `relayline` | no results (a control query `relay` returned 796) |
| [TMview](https://www.tmdn.org/tmview/) (EUIPO and other offices) | `relayline` | no results (control `relay`: 3,015) |
| TMview | `relay line` (contains) | 2 unrelated, ended marks: RELAYPAY ONLINE PAYMENT SOLUTIONS (AU), CHICAGO SHORELINE MARATHON AND RELAY (US) |
| npm | `registry.npmjs.org/relayline`, `/relay-line`; npm search `relayline` | 404, 404; 0 packages |
| PyPI | `pypi.org/pypi/relayline/json` | 404 (free) |
| GitHub | `relayline in:name`; `github.com/relayline` | 5 repos, all 0 stars, other fields; no such user or org |

Not a legal clearance: only exact-name searches; marks that are just `RELAY` exist in software classes (e.g. a live
US registration in class 42), so a compound with `relay` is not unique as a word.

## Sources

All checked 2026-10-24.

- openai/codex-plugin-cc: [repo and README](https://github.com/openai/codex-plugin-cc), [releases](https://github.com/openai/codex-plugin-cc/releases), [marketplace.json](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json), [rescue.md](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/commands/rescue.md), [hooks.json](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/hooks/hooks.json), [state.mjs](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/scripts/lib/state.mjs)
- OpenAI developer forum: [Introducing Codex Plugin for Claude Code](https://community.openai.com/t/introducing-codex-plugin-for-claude-code/1378186) (2026-03-30)
- Secondary reports (used only to mark items unconfirmed): [inside.com.tw](https://www.inside.com.tw/article/42196-openai-codex-plugin-claude-code), [noqta.tn](https://noqta.tn/en/news/openai-codex-plugin-claude-code-rival-integration-2026)
- Similar projects: the repo links in section 2 (README, LICENSE file, GitHub API metadata)
- Local commands: Claude Code 2.1.309 `claude plugin list --help`, `claude plugin details --help`; codex-cli 0.164.0 `codex --help`
- PyPI: `https://pypi.org/pypi/<name>/json`
