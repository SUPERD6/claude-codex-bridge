- `ccx intake list|pull|ask|done`: tasks from outside. Issues you open with the label `ccx-task` in a PRIVATE
  repository of yours (`ccx config set intake.github owner/repo`) become tasks for the local lead; it asks for an
  approval and reports (result, PR/branch, cost, what was not verified) as comments on the same issue. Only issues
  and comments by the account `gh` is signed in as count (others are skipped and logged once), a public repository
  is refused, a pulled issue is never handed out twice (`<hub>/ccx/intake.json`), and nothing runs on a timer.
  `ccx.intake.pending(p)` gives the open count for other tools. Docs: `docs/intake.md`, with how to reach the lead
  from a phone by Remote Control (checked against Claude Code 2.1.309) and the feasibility of GitHub Projects and a
  self-hosted runner (not implemented).
- The board's private-GitHub helpers moved to `ccx/ghpriv.py`, shared by the board and the intake.
