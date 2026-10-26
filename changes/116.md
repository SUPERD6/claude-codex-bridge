- Fix: a sub-agent's brief picks shared notes by words without the dots and dashes at their ends (`JSON.` is `json`)
  and without common English and Chinese words (`the`, `with`, `我们`, `这个`). The L5 `mem-json` note, missed 4 of 4
  runs, is now picked; over the 6 L5 cases unrelated notes picked fell from 12 to 1 (`tests/test_brief_words.py`).
  Same number of notes as before.
- `ccx run` and `ccx resume` end their JSON with a `recap` key, one line with run_id, status, check, review, cost
  and `next: ccx show <id>`, so a lead piping the output through `tail` still has the run_id. Other keys unchanged.
