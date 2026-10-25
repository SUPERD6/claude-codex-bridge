- Independent review: a reviewer's summary without the `REVIEW: pass|issues` line (e.g. written in Chinese) no
  longer ends as `unclear` when its items are tagged: `[must]` items make it `issues` (so the fix round runs), only
  `[note]` items make it `pass`; the verdict carries `format: lenient`. The prefix also tolerates markdown and a
  full-width colon. Found in the seven-cores round 2: haiku named the real bug as `[must]` and the run stayed unfixed.
- `ccx way --label` labels the build runs (e.g. `eval-...`, so H9 and probable verdicts leave an evaluation out).
- Seven cores, round 2 (cores 4–7): plan, report and scrubbed data in `docs/research/` (`scripts/eval/r2.py`,
  `scripts/eval/tasks_r2.py`); `scripts/eval/common.read_jsonl` splits on `\n` only (U+2028 inside a JSON string broke
  it).
