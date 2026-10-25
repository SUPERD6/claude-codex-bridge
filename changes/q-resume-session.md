- `ccx q resume` continues the session of the run a `doing` piece was in the middle of (found by its `q:<id>` label,
  a review's fix round included) instead of starting the piece over, and tells the sub-agent it was stopped. A piece
  whose run had finished before `q run` was killed is marked done without running again (`restored: finished`).
  Before, the item only learned its run id when the run returned, which a killed `q run` never reached (r2 4-I).
