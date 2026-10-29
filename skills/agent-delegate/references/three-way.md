# Yourself, your built-in sub-agent, or ccx

After splitting, each piece goes one of three ways. Let ccx compare them:

```
ccx route --files 2 --coupling one --clarity goal --risk low --novelty pattern \
          --lead claude:opus:high --ctx-tokens <what you'd carry> --turns-left <turns ahead> \
          [--needs undo,worktree,other-vendor,resume] [--quota claude=0.4]
```

Read `choice`: `recommend` (self / builtin / delegate), `rung`, `why`, the three `options` with cost and odds,
and `how` — the next step to take.

| Way | When it wins | How |
|---|---|---|
| **self** | tiny work, or a cheap lead with little context to carry | do it |
| **builtin** — your own sub-agent (Claude Code: Agent tool, Haiku/Sonnet/Opus; Codex: multi_agent, your own model) | the other tool's quota is tight, or the same vendor is cheaper here; nothing below is needed | start it with the brief; check the result; `ccx verify --builtin <rung> --b <b> --ok 1\|0 --agent-id <id>` |
| **delegate** — `ccx run` to another agent | you need an undo snapshot, a worktree, another vendor's model, a `--check` that ccx runs again, or resume after a crash (the only way to get these). Its start-up per request is smaller (slim start), but that is not the whole cost: per right task on round 5's large tasks the built-in sub-agent cost less (about even with lean briefs), so don't pick ccx for price alone | `ccx run …` as in SKILL.md; then `ccx verify <run_id> --ok 1\|0` |

Facts behind the numbers (measured 2026-10-24): a built-in sub-agent starts with its full tools — 58.4k tokens on
Claude Code, 22.2k on Codex — against 13.6k / 18–21k for ccx's slim start. A built-in sub-agent is one attempt:
ccx cannot escalate it.

## A big job: the work queue

Split it once, then let the queue carry it: `ccx q add` each piece (`--dep` for order, `--check` for acceptance,
`--minutes` for size; or `ccx q add --plan plan.json` with task-split's plan), `ccx q run` routes and runs every
ready piece in parallel, again and again until nothing is ready. Nothing ready is not always finished: read the
output. Pieces under `waiting` wait for you: parallel writers in a clean git checkout each work in a worktree, so
land each listed piece (also those under `unmerged`) with `ccx q accept <id>`, after `ccx q done <id> --ok 1` when
there is no check or review evidence (the order `ccx q ls` shows) (merge in dependency order, joint
check after each merge, rollback when it fails), then `ccx q run` again; a piece that ran in this checkout is
accepted with `ccx q done <id> --ok 1`.
Pieces under `dep_blocked` wait on a piece that failed or got stuck: fix it, then accept it the same way. It lives in `.ccx/queue/` (append-only), so a crash or a closed window loses nothing — `ccx q resume` — and
the next lead sees it at session start. A sub-agent that finds its piece too big replies `SPLIT:` with the parts;
they become children (at most 3 levels, each with a share of the parent's `--budget`), routed and checked like the
rest, and the parent is done when they all are. You decide per piece whether it needs a check or a review; the
models are picked by routing. `ccx q budget <usd>` stops the whole queue at a spend.

## Sub-agents and their own sub-agents (limits on spend and quota, not on head count)

A ccx sub-agent may use its own sub-agents (Codex's multi_agent; Claude's Agent tool, given to write runs):
sometimes the tool splits a piece better from the inside. How many run at once and which model they use stay the
tool's own choice; ccx sets only the edges:

- **Spend.** A watchdog adds up what they spend while the run goes (Codex: its child session files; Claude:
  `<session>/subagents/*.jsonl`) and stops the run over the piece's budget — `--budget USD`, a queue item's share,
  else `[subagents] max_usd` ($2). The run ends as `over_budget`; `ccx resume RUN --budget X` goes on.
- **Quota.** When a subscription is projected over its limit at this pace, Codex's children are held to 1 at a
  time and one model rung down; when it is snug (≥ 80 %), 2. `--subagents N` sets a number, `off` none.
- **Asking.** Only `--parallel` tells the sub-agent explicitly to use sub-agents for the independent parts — the
  words Codex's own instructions wait for. A brief that just lists several parts no longer does (round 5: it cost
  more per run and saved no time), so pass `--parallel` only when the parts really are independent and large.
- **Counting.** Their tokens are added to the run (Claude's result now counts the whole session, sub-agents
  included).

What has been seen live (2026-10-24): codex-cli 0.164 tells its model not to start sub-agents unless the user,
AGENTS.md or a skill explicitly asks, and gpt-6-luna/low started none in 5 runs, even when asked; until this change
a slim Claude sub-run had no Agent tool at all. So "on by default" has meant "rarely used", and none of the limits
above has been hit by a real run yet. Deeper splits go through the queue (`SPLIT:` → `ccx q`).

## DeepSeek: pay per token, for simple pieces

ccx runs DeepSeek through Claude Code as its own agent (`--to deepseek`), with its own rungs, prices and learning.
It costs real money (a few tenths of a cent per small piece) instead of subscription quota, so:

- **When.** Routing compares its real money with the subscriptions' quota at a shadow price (30% of the API
  price while there is room, rising to the full price near the limit, double beyond; task-routing's method.md
  section 11). So it often wins mid-sized work even with quota to spare, and wins more as quota runs short
  (ccx reads both quotas by itself and projects them to the reset — `ccx quota`; `--quota claude=0.8` overrides). Ask for it directly with `--to deepseek` when the user
  wants it.
- **What suits it.** Self-contained, checkable work: reformatting, adding tests, following an existing pattern,
  small fixes with a failing test, reading and summarising. Name the files and the check in the brief.
- **What doesn't.** Design trade-offs, anything where a wrong answer is costly (security, data, money) unless a test
  pins it down, and work that needs the user's own MCP tools or settings (DeepSeek runs with `--bare`: no hooks,
  no CLAUDE.md, no MCP).
- **Effort and failure.** Routing picks flash at low, high or max by difficulty; on failure low → high → max → Claude,
  each checked; Claude starts a fresh session on the user's own login. v4-pro is not used (weaker and pricier).
- **Limits.** `daily_usd` in `[providers.deepseek]` (default $1) stops it for the day; `ccx report` shows its spend on
  its own line. Off-peak hours (outside UTC 01–04 and 06–10 on weekdays) are half price.
- **Key.** Only from the environment variable `DEEPSEEK_API_KEY`, and only that key is sent to DeepSeek's server.

Measured 2026-10-24: start-up 1.5k tokens per request (vs 13.6k for ccx's slim Claude start); a tiny read
$0.0009 (flash) / $0.005 (v4-pro) at peak price; flash passed 10 of 10 small calibration tasks in this repository
(b 1–5, $0.054 in all) — see task-routing's method.md section 8.
