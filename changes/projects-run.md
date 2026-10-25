- `ccx run --project <name, alias or sentence>`: delegate into a project from the catalog. The name is resolved
  like `ccx where` (one project, else an error listing the candidates); the run goes to that folder and the
  brief starts with the project's rule files (nearest first) and state files. When the project's rule files
  speak of approval, authorization or a freeze, ccx does not start the run: it quotes those lines as written
  (`approval_rules`, file and line) and the lead decides from them, or asks the person, then runs again with
  `--rules-ok`. `ccx where` shows the same lines with its pick. The agent-delegate skill and the session start
  (one line, only when a catalog exists) say: a project named without a path -> `ccx where` first.
