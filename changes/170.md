- `ccx ui` Agent conversation page (per project, `#/conv/<project>`): the agents' board threads (`ccx say` /
  `ccx reply`), newest first, each message with who, when, to whom, `via` and its text, always escaped; read only,
  capped in size, a new message shows on the next poll. Two new to-dos on the home page: a thread stopped by the
  machine-message cap, and a message that asks the person (`@person` in its text as a plain mention, not in code; the
  board's `AGENTS.md` rules say so: projects set up earlier re-run `ccx board --init` to get that line). Both link to
  the thread.
- `ccx ui` reply: the person answers a thread from the page, through the same prepare -> confirm (one-time nonce)
  as the other buttons; at most 4000 characters (longer is refused, never cut); written by the board code as one
  message from the person, `via: ui`, never run. It clears the stopped-thread to-do by the board's own rules.
