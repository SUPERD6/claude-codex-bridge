"""Is a folder in git, and does it have uncommitted work? Shared by `ccx q run` and `ccx batch`, which only give
parallel writers their own worktree when the project is clean: a worktree starts from the last commit, so with
uncommitted work (an earlier piece that ran in the project folder, the lead's own edits) a writer there would start
from code that lacks it."""
from __future__ import annotations

import subprocess
from pathlib import Path

# what `ccx q run` and `ccx batch` print (under "shared_folder") when they kept writers in the project folder
SHARED_WHY = ("the project has uncommitted changes, which a worktree (made from the last commit) would not see: "
              "these writers worked side by side in the project folder, so each one's check, review and undo can "
              "also see the others' edits; keep pieces on separate files, and commit first to give each its own "
              "worktree")
# what `ccx batch` prints (under "stale_base") for a task that asked for a worktree while the project was dirty
STALE_WHY = ("these tasks asked for a worktree, which starts from the last commit and lacks the project's "
             "uncommitted changes; commit first if they need them")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL)


def in_git(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0


def clean(root: Path, ignore: tuple[Path, ...] = ()) -> bool:
    """No uncommitted change in the repository (ccx's own .ccx folders aside, and the files in `ignore`, such as
    the plan file `ccx batch` was given)."""
    # -z: paths come back raw (no quoting of spaces or non-ASCII names), NUL-separated; a rename's or copy's
    # entry is followed by its old path as a field of its own
    args = ["status", "--porcelain", "-z"] + (["--untracked-files=all"] if ignore else [])
    r = _git(root, *args)
    if r.returncode != 0:
        return False
    skip: set[Path] = set()
    top = None
    if ignore:
        t = _git(root, "rev-parse", "--show-toplevel")
        if t.returncode == 0 and t.stdout.strip():
            top = Path(t.stdout.strip()).resolve()
            skip = {Path(f).resolve() for f in ignore}
    fields = r.stdout.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths = [entry[3:]]
        if entry[0] in "RC":                      # the old path follows
            if i < len(fields):
                paths.append(fields[i])
            i += 1
        for path in paths:
            if ".ccx" in path.replace("\\", "/").split("/"):
                continue
            if top is not None and (top / path).resolve() in skip:
                continue
            return False
    return True
