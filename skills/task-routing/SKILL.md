---
name: task-routing
description: Choose a model/effort or compare self versus delegation when the user requests that choice, or before an already-authorized delegation. A general request to save tokens does not trigger cost estimation or delegation.
---

# Task routing

Compare only models and tools actually available and allowed for this task. Routing is advice,
not permission to start another agent. Ordinary work stays with the current agent when no
model choice is needed. Method and assumptions: [references/method.md](references/method.md).

## When a comparison affects the decision

Use `scripts/task_routing.py` (Python 3.11+, stdlib). Describe what is known:

| Flag | Values |
|---|---|
| `--files` | expected files touched |
| `--coupling` | `one`, `cross`, `system` |
| `--clarity` | `spec`, `goal`, `unknown` |
| `--risk` | `low`, `visible`, `critical` |
| `--novelty` | `pattern`, `new` |

```text
python scripts/task_routing.py route --files 3 --coupling cross --clarity goal --risk low --novelty pattern
```

Use `--not-verifiable` if available checks cannot establish success; it disables cheap-first
escalation. Add `--lead`, `--ctx-tokens`, `--lead-ctx` (your conversation's size: each of your turns re-reads it;
ccx reads it by itself) and `--remaining-turns` when comparing continuation with delegation. To offer a delegation
nobody asked for, use `ccx propose` (agent-delegate, section 0): the same estimate, recorded, one line to ask. Use `--agents` to restrict providers; `--explain` shows alternatives.
`--agents codex,claude,deepseek` adds DeepSeek, which costs real money per token; through ccx it is offered only
once every subscription's quota reaches 70% (agent-delegate's `references/three-way.md`).
Consult `--help` only for needed unfamiliar options.

The output's probabilities and dollar costs are estimates, not measured guarantees or
subscription quota predictions. Inspect `calibration`, `stale`, and `new_models_without_prior`;
unverified priors must stay labelled as such. Verify current official prices only when using
stale prices to make a cost decision, not for every ordinary task.

## Act within the task's scope

Use the estimate alongside checkability, startup/handoff cost and actual availability.
A `split` recommendation does not automatically trigger multiple skills or agents. If a
verified failure justifies an authorized escalation, resume the same session where supported.
When authorization or available models prevent the suggested choice, explain the constraint
and use an allowed option.

Record only an actually checked outcome; ccx already records its own runs:

```text
python scripts/task_routing.py record --rung codex:gpt-6.1-sol:medium --b 4 --ok 1
```

No new model run is needed merely to calibrate the estimator. Optional `--cost-usd` records
measured cost; without real measurements, retain the uncertainty.
