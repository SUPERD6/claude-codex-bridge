---
name: task-split
description: Break a large or explicitly requested task into checkable pieces and dependencies. Use for complex multi-hour work or "怎么拆分/拆成几块"; splitting alone does not authorize delegation or require model-cost estimates.
---

# Task split

Define the outcome and acceptance check, then split only where a piece has a useful result
that can be checked. Keep highly coupled work together; concurrent writers must not own the
same files. Start with the milestones needed now and refine uncertain pieces as evidence
arrives, rather than imposing a fixed number of steps or depth.

## A small plan is usually enough

For each piece, record its result, dependencies, affected files and a "done when" check.
Expose decisions whose answers could change the plan. Put routine implementation details
below those decisions. Simple sequential work does not need a numeric planning run.

## Optional estimates for scheduling tradeoffs

When task size, dependencies or parallel cost affect the choice, use `scripts/split_plan.py`
(Python 3.11+, stdlib):

```text
python scripts/split_plan.py size --minutes 240 --rung codex:gpt-6.1-sol:medium
python scripts/split_plan.py template
python scripts/split_plan.py check plan.json --lanes 3
```

The template contains `id`, `title`, `minutes`, `depends_on`, `files`, `checkable`, and optional
`rung`. Outputs include waves, critical path, estimates and flags for file clashes, missing
checks or excessive handoffs. `files` decides which pieces can run in parallel: pieces sharing a file
never do. `--lanes` describes possible concurrency, not permission to
launch agents. Use current-task estimates; defaults are dated guesses, not demonstrated
success rates or precise time limits. Read [references/method.md](references/method.md)
only when the assumptions matter.

## Execute and recover

The current agent can execute the pieces itself. Use task-checkpoint only when interrupted
work needs a resumable record. Use task-routing and agent-delegate only if a model choice
or delegation is actually required and authorized; do not automatically chain all skills.

Record verified outcomes only (ccx handles its own runs):

```text
python scripts/split_plan.py record --rung codex:gpt-6.1-sol:medium --minutes 60 --ok 1
```

The script updates learned estimates and reports their source. A failed check is evidence
about that run, not proof that every similarly sized task needs more agents or more budget.
