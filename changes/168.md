- `ccx resume` and `ccx task resume` keep the review setting of the run they continue (`--review off` stayed off;
  before, a resume reviewed with the default `auto`); `ccx resume --review X` still overrides it. Run records carry
  `review_mode` (a review fix round keeps the setting of the run it fixes; older records count as `auto`).
- eval seven_func: every check runs with a fresh hub under its own scratch dir and refuses to start when its
  environment would point at the person's hub; its verdict reads rows only from that hub, by task or by label and
  start time. The resume check records `killed_after_s` right after the kill (it included scoring and the resume
  before) plus `resume_s`, and reports `mechanism_ok` (its `ok`: killed run unfinished, same task and session,
  label/check/review inherited, resume rc 0) apart from `task_ok` (the hidden test); its visible test now covers
  `low_stock`, so ccx's own check can catch the mistake the hidden test found.
