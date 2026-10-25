- dsh archiving: the "queued" message now says the desktop app has to be quit from the tray; closing its window
  leaves it running, so ccx keeps the id queued (seen on a real machine 2026-10-25; once quit, the next session
  start wrote the queued ids, and the reopened app did not overwrite them on start; its own next write is not
  observed yet).
