- H2: every attempt taken for a quota stop leaves its evidence in `<hub>/ccx/quota-stops.jsonl`: Claude's rejected
  `rate_limit_event` as it came, or the hint that matched and the words around it (Codex and others), with run,
  agent, model and retry time. `ccx quota` shows the last five (`recent_quota_stops`). A wrong call (the word
  "quota" in a task's own output, a new wording of a real limit) can then be found and the hints corrected without
  spending quota to test. No quota stop has happened in real use yet (0 of 337 runs on the author's machine).
