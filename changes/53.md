- `ccx doctor` adds a safety note to "Codex as lead (sandbox)" when Codex runs in full access (every lead command
  has your rights, unsandboxed) and offers a narrower way: `ccx doctor --codex-rule` prints a Codex rule
  (`prefix_rule`, decision `allow`) that lets only this ccx's `run/ask/resume/discuss` run outside the sandbox.
  doctor asks Codex itself whether a rule in `~/.codex/rules/` matches (`codex execpolicy check`) and then reports
  Unknown, not ok: by Codex's docs it should work, but no real run has checked it. ccx never writes the rule.
  README (EN + ZH) carries the same warning; DECISIONS records the options weighed.
