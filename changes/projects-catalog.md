- `ccx projects scan` / `ccx projects` / `ccx projects show <name>`: a catalog of the person's projects, found by
  code (no model, no network) under the folders in `projects.roots` (default empty; `ccx config set projects.roots
  "DIR;DIR"`). A project is a folder with `.git`, rule files (AGENTS.md / CLAUDE.md) or a build file, or a README
  right under a root. A folder with projects right inside it and no work of its own (no `.ccx/`, `topics/` or
  STATUS) is a group: not listed, its rules are inherited by the projects inside. Repositories inside a project
  (e.g. `shared/source/X`) are listed too, with `parent`. Dependency, build, backup, worktree, topics and archive
  folders are skipped, and a link or junction to a folder already seen is recorded once (`also_at`). Each entry
  keeps a one-line summary (README / AGENTS first paragraph), aliases (folder, titles, git remote, package name,
  Chinese names in titles), keywords (README titles one level down), the rule files to read first (nearest
  first), state files (STATUS, handoff, .ccx/context.md, topics/), last activity and the latest commit subjects
  and journal lines. The catalog is `<hub>/ccx/projects.json`, on this machine only; a scan of a real workspace
  with 31 projects took about 1.4 s (`ccx/projects.py`, `tests/test_projects.py`).
