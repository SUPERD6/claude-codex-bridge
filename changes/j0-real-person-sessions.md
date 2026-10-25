- `scripts/eval/j0_baseline.py real` counts only conversations a person drove: it leaves out the sessions of every
  ccx ledger (this hub's, the temporary hubs eval scripts leave under the temp folder, and `--ledger FILE`) and
  every headless session (Claude `-p`, entrypoint sdk-*; `codex exec`), which is how ccx sub-runs
  (CCX_ROLE=subagent) and eval leads run; `--keep-headless` gives PR #6's reading. New `--until ISO` re-reads an
  earlier window with the same rules, `--tag` names a reading, `compare --before T1 --after T2` puts two side by
  side, and each reading now carries `ccx lead --cache`'s breaks and causes inside the window. By default it reads
  only this repository's conversations (main checkout and worktrees); `--project DIR`, `--all-projects`.
