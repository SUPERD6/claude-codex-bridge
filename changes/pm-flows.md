- `ccx ui`: a finished write run's card has "Undo this run" next to the diff (`ccx undo <id> --apply`, prepare and
  confirm like every button; it starts nothing, so it also runs in `ccx demo`), and a run that still fails its
  independent review has "The review is wrong: accept" (`ccx verify <id> --ok 1` with a note). A text meant for your
  lead is labelled "paste this to your lead", not "command".
- One order for a worktree queue piece in `ccx q ls` and `ccx ui`: the verdict first, then the merge. `q ls` prints
  `next: ccx q done qN --ok 1, then ccx q accept qN` until a verdict is in; the page says the same before the verdict
  and shows a "Merge into the project" button (`ccx q accept`, in the background) after it. `--cwd` now works after
  every `ccx q` subcommand, and `ccx q --cwd DIR done ...` no longer loses DIR.
- `ccx -h` lists the person's commands; `ccx -h --all` lists every group, with peek / board / say / reply under
  "Between agents" (all still callable). `ccx run -h` groups the routing rubric and coordinator options under
  "advanced". Help text for `verify --ok`, `reply`'s id and `--from`; `ccx demo -h` has a description, and `ccx demo` /
  `ccx ui` print `next: open <url or file>`.
- Naming: the Chinese page and docs call the lead 主导 everywhere; `ccx handoff --to/--by deepseek` means dsh, and the
  page shows "DeepSeek (dsh)" (`ccx run --to deepseek` is still the deepseek provider).
- The overview: each waiting item says first what you need to do, with a colour per kind (your call, check the
  result, a question for you), then the agent's own words; count badges are neutral; each project card says who leads
  with a link to its switch-lead panel. After a verdict the side panel moves to the next waiting piece ("Next
  waiting", keys j / k). Times past two days read in days and weeks; a machine failure with no reason shows no empty
  brackets; the queue's top box says "Work queue: N pieces" instead of a quote you never typed.
