- The board, part 3: `ccx say --to codex --now` also pushes the message into the project's live Codex desktop
  conversation (`codex queue`, waiting while the person types there); `ccx say --resume RUN_ID` continues a headless
  sub-session with it and puts the answer back on the board as a reply. Claude Code desktop has no way in from
  outside and sees the message on its next turn. Optional fallback between computers:
  `ccx config set board.github owner/repo` (a private repository of your own; ccx refuses a public one and the
  project's own repository) and `ccx board --sync` mirror the board to one issue there, pulling at most every
  10 minutes; the per-turn hook starts that in the background when due. Not configured: no network at all.
