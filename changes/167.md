- `ccx ui` review cards: "agent says" (summary, verification) beside "ccx ran" (check command, exit, last output);
  the files actually changed and the diff come from the run's own snapshots (`undo.json` to `end.json` / `after`,
  read-only `/api/judge/<run>`, capped and marked truncated), never the live folder; a red box when the agent's
  file list and the real change differ. Older runs keep the old view with a note.
- `ccx ui` home: a "running now" strip (agent, time, tokens, stop with the usual confirmation); a task without a
  title takes its first piece's.
- `ccx ui` heartbeat: sent again when the tab is shown or focused; a hidden tab says so and the server waits 5
  minutes instead of 60 s. To-do chips are buttons; one aria-live region announces new to-dos.
