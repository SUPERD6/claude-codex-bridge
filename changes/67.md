- `ccx discuss --bg` runs the discussion detached, the same way as `ccx run --bg` (one shared `detach()` in
  `ccx/commands/common.py`): the id is fixed and a "starting" record saved up front, so `ccx discuss --show ID` and
  `ccx ui` follow it turn by turn; the detached process's output goes to `<hub>/ccx/discussions/<id>.log`.
