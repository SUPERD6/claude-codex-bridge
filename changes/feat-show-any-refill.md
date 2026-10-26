- `ccx show ID... --any [--wait N]`: every finished run among several ids (`finished`) and the ones still running
  (`running`, `next`); one id without `--any` is unchanged.
- `ccx q run` refills a slot as soon as a run finishes instead of waiting for the wave; a run whose attempts hit
  quota/rate/auth stops new submissions (`stopped: backpressure`); new `ccx q run --bg`. An item routing skipped is
  tried once per `q run` instead of looping.
- Skills: agent-delegate teaches pipelining several pieces (`q run --bg`, `show --any --wait`) and that on
  `review_failed` the lead checks the `[must]` items and fixes them itself; task-split says `files` decides what runs
  in parallel.
