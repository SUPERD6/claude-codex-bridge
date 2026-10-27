- `ccx fresh` / `ccx handoff` never overwrite a hand-written or edited `.ccx/handoff.md`: it is updated only while it
  is ccx's own unedited copy (its `<!-- ccx:handoff ... -->` header and the same text as a file in
  `.ccx/handoffs/`); otherwise the new handoff lives only in `.ccx/handoffs/` and the result carries
  `latest_skipped` (with `latest` pointing at that file). The session-start hook reads `.ccx/handoffs/` first, so it
  still shows the new one once. The comment in `cmd_fresh` that said fresh never wrote `.ccx/handoff.md` is fixed.
- agent-delegate (SKILL.md + README.zh.md) teaches one call for long work, `ccx run ... --bg --wait 540` with a
  600000 ms shell timeout (Codex / DeepSeek leads set `--wait` about a minute under their own tool timeout), keeps
  `ccx show <run_id> --wait` for a run still going, judges `kind` from either final result, and adds: the lead's own
  sub-agents and ccx never write the same files at once; a ccx writer beside native writers uses `--worktree` or
  `ccx q run`. `scripts/eval/batch.py` counts `run/resume --bg --wait` as a blocking wait.
- Docs no longer teach a 70% quota gate for DeepSeek (task-routing SKILL.md, the `ccx run --quota` help,
  `config/tiers.toml`): routing prices quota by its shadow price (E4); the unread `[cash] from_quota` is removed
  from priors.toml. three-way.md no longer calls ccx the cheapest way while saying the built-in sub-agent cost
  less; rubric.md points to `--tier` / `ccx stats` / the person's own config instead of hand-editing tiers.toml.
- `tests/test_skills_core.py` guards pipelining (`ccx q ...`, `--any`), whole-workflow tiers (`--tradeoff`) and the
  result-reading rules (`needs_lead`, `edited_tests`, `namecheck`, `weak`, fix round, resume) in every skill
  trim, plus the one-call wait and the removed stale rules. `.gitignore` ignores `.claude/` (local state).
