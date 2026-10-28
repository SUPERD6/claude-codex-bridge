# Research reports

English · [中文](README.zh.md) · back to [Measured](../measured.md)

Every report keeps its limits and unfavourable results; read the report before quoting a number. Plans were written
before their runs. Round 5 and everything after it use a development set (tasks also used while tuning ccx): signal,
not proof. Scrubbed data is in [data/](data/).

| Date | Question | Result in one line | Report |
|---|---|---|---|
| 2026-10-23 | How should token savings be measured? | One unit (API-equivalent USD); headline metric is cost per success against the lead doing it itself | [token-cost quantification](2026-10-23-token-cost-quantification.md) |
| 2026-10-24 | What does the lead itself cost, and does delegating small tasks save it anything? | Only if the lead trusts ccx's check (one request fewer per task); a lead that re-checks pays more | [H11 / E8 / F9 measurements](2026-10-24-h11-e8-f9-measurements.md) |
| 2026-10-24 | Do the seven cores work on real CLIs (round 1, Claude Code + Codex)? | Leading each other and project memory work; no evidence yet that working together is better | [seven cores A/B](2026-10-24-seven-cores-ab.md) ([plan](2026-10-24-seven-cores-plan.md)) |
| 2026-10-24 | How does ccx live with the official plugin, and what similar projects exist? | Overlap only on the Claude → Codex side; no other project found that routes by odds and cost with a ledger | [landscape](landscape.md) |
| 2026-10-25 | Round 2: does dividing the work beat one model, and is it cheaper? | Review and dividing point the right way, not significant; the cheap model is near the ceiling on clear tasks | [round 2](2026-10-25-seven-cores-r2.md) ([plan](2026-10-25-seven-cores-r2-plan.md)) |
| 2026-10-25 | Does the lead's recent work, attached to a brief, help the sub-agent? | First try right 36/36 vs 7/36, 63 % less spend; the feature's best case by design | [shared-context A/B](2026-10-25-shared-context-ab.md) |
| 2026-10-25 | Does the board work with the real Codex and DeepSeek CLIs? | Yes: messages, replies and per-turn delivery right; one wording bug found and fixed | [board acceptance](2026-10-25-board-acceptance.md) |
| 2026-10-25 | Can three vendors talk a decision through (`ccx discuss`)? | Works, n = 1: right answer, $0.016, 85 s | [three-vendor discuss](2026-10-25-discuss-three-vendors.md) |
| 2026-10-25 | DeepSeek as lead and as `dsh` sub-agent | Works as a sub-agent; as a lead only with full access or through Claude Code | [DeepSeek lead](2026-10-25-deepseek-lead.md) |
| 2026-10-25 | Could Gemini CLI be a lead? | Not built and not run; what it would take | [Gemini lead](2026-10-25-gemini-lead.md) |
| 2026-10-25 | Round 3: ccx versus Claude Code's built-in sub-agent on harder tasks | All arms 20/20; doing it yourself is cheapest; ccx cuts the lead's tokens but is slower | [round 3](2026-10-25-r3.md) ([plan](2026-10-25-r3-plan.md)) |
| 2026-10-25 | Do warm lanes (continuing a session per piece) save? | About 40 % cheaper than a fresh session per piece, but slower and still dearer than one run; stays off | [warm lanes](2026-10-25-warm-lanes.md) |
| 2026-10-26 | Round 4: where do cheap models fail; does delegating save in a long lead session? | Hardly fail (ceiling); in a long session doing it yourself is cheapest | [round 4](2026-10-26-r4.md) |
| 2026-10-26 | Round 5: large real tasks, does delegating save, is it more right? | First run: no; after the fixes ccx2 39/40 at $0.116–0.131 per success (dev set) | [round 5](2026-10-26-r5.md) ([plan](2026-10-26-r5-plan.md)) |
| 2026-10-27 | Batch / pipeline: several changes at once, scored on the merged tree | Plan only, nothing measured yet | [batch plan](2026-10-27-batch-plan.md) |
| 2026-10-28 | Offline experiments C1–C6 on the round-5 records | namecheck 0 false alarms; most other candidates dropped or still need paid runs | [offline experiments](offline-experiments.md) |
| 2026-10-28 | Did ccx keep its own obligations in round 5 (r5e–r5h)? | Right answers hid harness problems: 76/76 right ccx2 units failed at least one criterion | [harness audit](2026-10-28-harness-audit.md) |
