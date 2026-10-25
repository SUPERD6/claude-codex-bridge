- dsh (DeepSeek Harness) sessions are archived too: dsh 0.2.1-rc.3 has no archive command, so ccx adds the run's
  session id to the desktop app's archived list (`<DSH_HOME>/storages/workspace.json`, `global.archivedSessionIds`,
  what the app's own archive action changes) and takes it out on `ccx archive --restore` and before `ccx resume`.
  Only that one id is added or removed; the file is backed up (`workspace.json.ccx-backup`) and replaced
  atomically, and a missing file is skipped. Session folders are never moved.
  Checked once with the desktop app open: the added id stayed for 5 minutes. Not checked: whether the app's next
  own write keeps it, and whether an open window shows it without a restart.
