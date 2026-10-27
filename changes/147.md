- `ccx run ... --bg --wait N` and `ccx resume ... --bg [--wait N]`: one call instead of `--bg` plus
  `ccx show ID --wait`. The run id goes to stderr at once (flushed), then the same process waits up to N s:
  finished -> the final compact result with recap (exit 0 / 2 as a foreground run); not finished -> exactly what
  plain `--bg` prints. The detached child gets no `--wait`; the wait starts after the routing / autonomy /
  pre-authorisation checks, a refused child (not_delegated, refused) ends it at once, and so does a child that exits
  before its run record exists (state failed, with the end of its log). `ccx resume` accepts `--bg` (it was an
  unknown argument, exit 2) and, like a foreground resume, refuses before detaching when another run is still working in that session (before, plain `resume --bg` printed `started` and `ccx show ID --wait` waited out its timeout); a detached resume that finds the session busy anyway writes a finished `refused` record. A finished waited result also carries the keys a foreground run adds after the run (`route`, `continued_from`, `project`, `autonomy` with the L2 merge outcome), read from the child's own result. The child's argv loses argparse's prefixes of `--wait` (`--wai 540`) too. `--wait` without `--bg` is an error; plain `--bg` and foreground runs are unchanged.
  The `--parallel` help no longer says it switches on by itself for a brief that lists 3+ items.
- Windows: `run_check` turns a single-quoted token with no double quote inside into a double-quoted one, in the
  same word pass as the glob expansion; words are split with the quote state tracked (MSVC rules: `\"` does not end a double-quoted argument), so a `'...'` inside a double-quoted argument (`"print('a b')"`, `--opt="a 'b c' d"`) is left alone (`-k 'a or b'` reached pytest as three words under cmd.exe, exit 4); the
  rewritten command is in `check.ran`, `&&`, `|` and redirects are kept as they are. The check text shown to the
  sub-agent (ccx/prompts.py) is not rewritten yet.
- Run ids handed out up front (`--bg`, `ccx q run`'s `live` id) now come from `ledger.new_run_id`, which creates
  the run folder exclusively, so two runs started in the same second can no longer draw the same id (second + 4
  random hex digits) and share a folder: the second then found the first's `final.lock` (CI flake in
  `test_archive_shared_session_once`). `ccx/delegate.py` draws a foreground run's id the same way. The parallel worktree test
  (`test_unmerged_branches_nothing_waits_on_are_listed`) only prints each piece's result when it fails: its CI
  flake was not reproduced (12/12 local passes, 120 concurrent `git worktree add` + commit clean), so its cause is
  not known; a run-id collision is the one mechanism found that gives exactly 1 of 2, and it is closed now.
