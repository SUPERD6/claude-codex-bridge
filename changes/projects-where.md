- `ccx where "<a sentence>"`: which project a vague sentence is about ("改一下那个桌宠", "the harness PR"), by
  code only, free. Words that say what to do (fix, PR, 改一下, 那个 ...) are dropped; the rest is looked up in each
  catalog entry's name, aliases, path, sub-folder README titles, topics, summary and latest commits / journal
  lines (Chinese by two-character pieces, English with one-letter typos allowed). One clear candidate is given as
  `pick` with its path and the files to read first; when several fit, all are listed with a confidence and why,
  for the person to choose (`ccx/projects.py` `where`).
