- `ccx doctor` has a row "Codex as lead (sandbox)": whether a Codex lead can hand work out with `ccx run`. Real runs
  (codex-cli 0.164, Windows): in `workspace-write` the lead's `ccx run` failed with `[WinError 5] Access is denied`
  on the hub's runs folder; with the hub as a writable root and the network on, ccx ran, but the Claude sub-agent,
  started under Codex's separate sandbox account, refused every edit ("sensitive file") and saved no session, also
  with `~/.claude` writable. Only `danger-full-access` worked. So on Windows the row asks for full access for lead
  sessions (a `[profiles.lead]` example); elsewhere it checks `sandbox_workspace_write.writable_roots` covers the hub
  and `network_access = true` (not checked on a real run there). A `PermissionError` from any command now carries a
  hint pointing at that row. README (EN + ZH) says this next to "Codex leads, Claude Code is the sub-agent".
