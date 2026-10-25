- `ccx way "brief" --risk low|visible|critical` (proposals H8, H9): the risk picks one of three ways of working.
  low = one agent builds, another vendor reviews when it is worth it (F1); visible = another vendor plans (`[step]`,
  `[accept]` items), one builds with the plan in its brief, the planner accepts the diff (one fix round; the
  acceptance is stored as the build's review, so probable verdicts see it); critical = two vendors each build a
  version in their own worktree and a third (or the second's vendor in a fresh run) compares them (`PICK: A|B`),
  only with `--yes` because it costs about twice as much; nothing is merged automatically. `--dry-run` shows the way
  and roles. H9: `ccx way --stats` gives, per kind of work (code / read / research / write) and agent, how often a
  piece was right the first time (judged right, no follow-up, no review fix) and how often it needed rework (a
  follow-up, a review fix, or judged wrong), over judged pieces only. With 5+ judged pieces these rates order who
  builds, and a builder right the first time under 50% gets a planner (solo -> plan_build). `ccx ui` shows the
  table under "Who is reliable at what".
