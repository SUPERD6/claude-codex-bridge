# Tier rubric (lead agent's judgment comes first)

Ask these in order; stop at the first "yes".

1. **Would writing the brief take about as long as doing it?** → T0, do it yourself.
2. **Could a careful junior follow exact instructions without understanding the system?**
   (rename symbol, apply a known pattern to N files, convert format, summarise logs,
   find where X is used) → **T1**
3. **Is the cause/approach already clear and confined to one area?**
   (implement a specified function, fix a reproduced bug, add tests for module M,
   write a script with known inputs/outputs) → **T2**
4. **Does it need understanding across modules, or finding an unknown cause?**
   (intermittent failure, performance, refactor touching several packages,
   "read this codebase and propose") → **T3**
5. **Is a mistake expensive or subtle?** (security, auth, concurrency, data
   migration, numerical/scientific correctness, public API design) → **T4**

Adjustments
- Many files (≥ 8) or a long unfamiliar codebase: +1 tier.
- Very well specified with a test that defines success: −1 tier.
- Review / second opinion of your own work: same tier as the work, `--mode read`.
- Parallel pieces: split so each piece has its own files; give each the lowest tier it needs.

Which agent
- Default: the *other* agent (that is the point — it spends the other account's tokens).
- Same-agent sub-tasks: yourself, your built-in sub-agent or ccx — compare them with `three-way.md`
  (round 5, large tasks: a built-in sub-agent cost less per right task than ccx; with lean briefs both were
  about even, `docs/research/2026-10-26-r5.md`).
- Check `ccx stats` after a while: if a tier's done_rate is low for one agent, raise
  that tier in `<hub>/ccx/tiers.toml`; if it is ~1.0 and cheap, try one tier lower.

Escalation
- ccx retries once, one tier up, **in the same session** (no re-briefing) when the
  sub-agent returns blocked/failed. Logged-out errors are not retried.
- If it still fails, do not loop: read open_questions and decide yourself.
