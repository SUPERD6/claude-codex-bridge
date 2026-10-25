# changes/

English · [中文](README.zh.md)

One file per pull request, instead of editing `CHANGELOG.md`: parallel PRs then never conflict on it.

- Name it `changes/<PR number>.md` (e.g. `changes/21.md`). Before the PR has a number, use the branch name
  (`changes/fix-site-out.md`) and rename it once the PR is open, or leave it — numbered notes are folded first,
  the rest by name.
- Write the lines as they would appear under `## Unreleased`: one or more `- ` bullets, continuation lines indented
  two spaces, wrapped at about 120 columns. English, like the rest of the CHANGELOG.
- Don't edit `CHANGELOG.md` or `docs/STATUS.md` in a feature PR. The lead (coordinating) session updates STATUS, and
  folds the notes into the CHANGELOG when releasing:

```bash
python scripts/collect_changes.py --check                                  # format only (the tests run this too)
python scripts/collect_changes.py                                          # preview
python scripts/collect_changes.py --version 0.5.0 --title "..." --apply    # write CHANGELOG.md, delete the notes
```
