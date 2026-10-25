- No more terminal windows popping up on Windows. `ccx run --bg` and the background benchmark refresh were started
  with `DETACHED_PROCESS`, so they had no console and every git / codex / claude call they made opened a new visible
  console window; the same happened when a desktop app ran ccx as a hook. Background processes now get a hidden
  console (`CREATE_NO_WINDOW`), and when ccx runs without a console at all it starts its children with
  `CREATE_NO_WINDOW` (`ccx/winproc.py`, installed on import; a process that has a console is left alone, so output
  in a terminal is unchanged). Checked on Windows: from a console-less parent, a child got a visible window handle
  before and none after (`tests/test_winproc.py`).
