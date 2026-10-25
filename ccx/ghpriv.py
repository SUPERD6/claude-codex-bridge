"""The person's own PRIVATE GitHub repository, through the `gh` CLI: shared by the board's fallback (ccx/board.py)
and the task intake (ccx/intake.py). Every write goes only to a repository that `gh repo view` says is PRIVATE."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def gh(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    from .runners import bin_argv
    return subprocess.run([*bin_argv("gh"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=timeout)


def failed(what: str, r: subprocess.CompletedProcess) -> RuntimeError:
    return RuntimeError(f"{what} failed: {(r.stderr or r.stdout).strip()[-300:]}")


def own_remotes(root: Path) -> set[str]:
    """owner/repo of every remote of the project itself: a private channel must never go there."""
    try:
        r = subprocess.run(["git", "remote", "-v"], cwd=root, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    out = set()
    for m in re.finditer(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s", r.stdout + "\n"):
        out.add(m.group(1).lower())
    return out


def check_private(repo: str, setting: str, what: str, root: Path | None = None) -> None:
    """ValueError unless `repo` is owner/repo, not one of `root`'s own remotes, and PRIVATE on GitHub."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo or ""):
        raise ValueError(f"{setting} must be owner/repo, got {repo!r}")
    if root is not None and repo.lower() in own_remotes(root):
        raise ValueError(f"{repo} is this project's own repository; {what} goes to a separate private one")
    r = gh(["repo", "view", repo, "--json", "visibility", "-q", ".visibility"])
    if r.returncode != 0:
        raise failed(f"gh repo view {repo}", r)
    if r.stdout.strip().upper() != "PRIVATE":
        raise ValueError(f"{repo} is {r.stdout.strip() or 'not private'}; {what} only uses a PRIVATE repository")


def login() -> str:
    """The GitHub account gh is signed in as (`gh api user`)."""
    r = gh(["api", "user", "-q", ".login"])
    if r.returncode != 0 or not r.stdout.strip():
        raise failed("gh api user", r)
    return r.stdout.strip()


def comment(repo: str, number: int, body: str) -> None:
    r = gh(["issue", "comment", str(number), "-R", repo, "--body", body])
    if r.returncode != 0:
        raise failed("gh issue comment", r)
