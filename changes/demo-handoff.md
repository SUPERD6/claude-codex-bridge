- `ccx demo` (also `ccx ui --demo`): `ccx ui` on made-up data in a new folder of the system's temporary folder, no
  account, offline: two projects, runs in every state (the review card with a real snapshot diff and a file mismatch,
  a running run, an environment failure), a three-piece queue with one unmerged piece, a board thread stopped at the
  machine cap and an `@person` question, a month of ledger costs. Marked "demo data" on every page; your hub and tools'
  folders are untouched; a button that would start an agent only shows its command; the folder is removed when the page
  closes or the export is written (`--keep` and `--dir` keep it; `--dir` takes only a new or empty folder or an earlier
  demo). The same data is the headless smoke test `tests/test_demo.py`.
- `ccx ui` switch-lead panel (project page and under a task's history): the current lead, when each lead worked (from
  `.ccx/handoffs/`), and "Continue with Codex / Claude" (DeepSeek where `dsh` is installed). It runs `ccx handoff --to X
  --by <current> --cwd <project>` after the usual second click, from the current lead's conversation file when it is
  there (`--from-transcript ... --no-model`), and shows the handoff file and the one line to paste into the other tool.
  Without that file the page says, before and after, that the handoff is a blank template to fill in first.
  The task timeline shows who was leading and each switch.
- `ccx handoff --cwd DIR` (the project folder; default the current one); its answer carries `paste`, the line to give
  the incoming lead (for dsh and gemini, which show no handoff at start-up, it tells them to read the file).
