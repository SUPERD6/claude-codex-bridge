- Skills trimmed and brought in line with current behaviour: agent-delegate's result checks are one list in
  section 4 (`needs_lead`, `edited_tests`, `check_broken`, the review fix round ccx runs itself), the duplicated
  cheap-side and project-lookup text is shortened, and `ccx stop` is taught. project-manager's default run leaves
  `--review` on auto (on only for an L2 auto-merge or visible risk), waits with `ccx show <run_id> --wait`, and
  names `ccx ui`, `say`/`board`/`peek`, `intake`, `stats`/`report`. task-checkpoint resumes a ccx step with
  `ccx resume <run_id>`. rubric.md no longer says built-in sub-agents beat ccx. The Chinese notes follow.
  New test `tests/test_skills_core.py`: every core feature is still named in some skill, and every ccx command and
  flag in any skill doc exists.
