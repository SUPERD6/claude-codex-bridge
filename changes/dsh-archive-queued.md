- dsh: while the desktop app is open, archiving (and un-archiving) a session is queued in
  `workspace.json.ccx-pending.json` and written by the first ccx call that finds the app closed (session start,
  the next archive). Checked with the app open (2026-10-25): its next change of its own wrote its in-memory list
  back and dropped the id ccx had added, though the id had stayed 5 minutes while the app was idle.
