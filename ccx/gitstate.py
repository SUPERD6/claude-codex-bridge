"""Is a folder in git, and does it have uncommitted work? Shared by `ccx q run` and `ccx batch`, which only give
parallel writers their own worktree when the project is clean: a worktree starts from the last commit, so with
uncommitted work (an earlier piece that ran in the project folder, the lead's own edits) a writer there would start
from code that lacks it."""
from __future__ import annotations

import subprocess
from pathlib import Path

# what `ccx q run` and `ccx batch` print (under "shared_folder") when they kept writers in the project folder
SHARED_WHY = ("the project has uncommitted changes, which a worktree (made from the last commit) would not see: "
              "these writers worked side by side in the project folder, as before; commit first to give each its "
              "own worktree")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL)


def in_git(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0


def clean(root: Path, ignore: tuple[Path, ...] = ()) -> bool:
    """No uncommitted change in the repository (ccx's own .ccx folders aside, and the files in `ignore`, such as
    the plan file `ccx batch` was given)."""
    args = ["status", "--porcelain"] + (["--untracked-files=all"] if ignore else [])
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
    for line in r.stdout.splitlines():
        for path in line[3:].split(" -> "):
            path = path.strip().strip('"')
            if ".ccx" in path.replace("\\", "/").split("/"):
                continue
            if top is not None and (top / path).resolve() in skip:
                continue
            return False
    return True
