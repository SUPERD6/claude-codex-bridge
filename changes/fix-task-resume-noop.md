- `ccx task resume` restarts a step whose run was killed before its agent session began. A real run killed after
  12 s (seven-cores functional check) left a run record with no session id and no ledger row; resume then only
  printed "do step 1 yourself" and exited 0. Now every fresh run saves the person's brief (`runs/<id>/brief.md`) and
  its acceptance command (`check_cmd` in run.json), and resume starts the step again on the same agent and rung from
  that brief plus the checkpoint brief, telling the agent to look at `git diff` first. The result says
  `restarted: <old run id>`. Checked on a real Codex run (gpt-6-luna low) killed after 4 s.
