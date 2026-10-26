"""External repositories for the hold-out set (backlog C1/7: tasks from another code base).

A task of another repository names it (`repo`) and pins the commit by its full sha. Per run, each repository is
fetched once into a cache folder (`git clone --bare` from its URL, or from a local copy given with --ext-cache), and
every unit gets the repository at the commit's parent with no future history visible: a fresh `git init` and one
commit of the parent's tree, so the unit's git has no remote, tag, reflog, packed ref or later object. Files the
package needs at import time but that its build backend writes at install time (hatch-vcs's `_version.py`) are
written as a stub and committed with `-f` (they are git-ignored upstream; ccx worktrees must have them too). The
hidden acceptance test is the commit's own version of the test files, read from the cache, and the tests run with
`PYTHONPATH=src` (relative: the repository root or a ccx worktree of it), since nothing is installed.

The cache holds the commit's future (the fix and its tests): it is one of the folders a unit's agents are denied
(preflight.forbidden via Unit.hidden) and that the audit flags when a tool call names it.

Only git reads the cached repositories here; nothing in them is executed except, at scoring time, their tests.
"""
from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path

CODE = (".py", ".toml")
VERSION_STUB = '__version__ = version = "0.0"\n__version_tuple__ = version_tuple = (0, 0)\n'


def _git(cwd: Path | None, *args: str, data: bool = False):
    r = subprocess.run(["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid",
                        "-c", "core.autocrlf=false", *args], cwd=cwd, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return r.stdout if data else r.stdout.decode("utf-8", "replace")


def cache_path(cache: Path, name: str) -> Path:
    return Path(cache) / f"{name}.git"


def fetch(name: str, spec: dict, cache: Path, source: Path | None = None) -> Path:
    """The bare clone of one repository in `cache`, made once: from `source/<name>` (or `source/<name>.git`) when a
    local copy is given, otherwise from the spec's URL. An existing clone is reused as it is."""
    dest = cache_path(cache, name)
    if (dest / "HEAD").exists():
        return dest
    origin = spec["url"]
    if source is not None:
        cands = [Path(source) / name, Path(source) / f"{name}.git"]
        local = next((c for c in cands if c.exists()), None)
        if local is None:
            raise FileNotFoundError(f"--ext-cache has no copy of {name} (looked for {', '.join(map(str, cands))})")
        origin = str(local)
    Path(cache).mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    _git(None, "clone", "--bare", "--quiet", origin, str(tmp))
    tmp.rename(dest)
    return dest


def pin(cache_repo: Path, sha: str) -> str:
    """The task's commit must be in the clone under exactly this full sha (a short or moved one is refused)."""
    if len(sha) != 40:
        raise ValueError(f"external tasks pin the full 40-character sha, got {sha!r}")
    got = _git(cache_repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}").strip()
    if got != sha:
        raise LookupError(f"commit {sha} is not in {cache_repo}")
    parents = _git(cache_repo, "rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 2:
        raise ValueError(f"{sha} must have exactly one parent (has {len(parents) - 1})")
    return parents[1]


def write_stubs(dest: Path, spec: dict) -> list[str]:
    """Files the build backend would write at install time; written only when missing."""
    out = []
    for rel in spec.get("stubs") or ():
        f = Path(dest) / rel
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(VERSION_STUB, encoding="utf-8")
            out.append(rel)
    return out


def export_tree(cache_repo: Path, rev: str, spec: dict, dest: Path) -> list[str]:
    """The files of `rev` (no .git) in a new folder `dest`, plus the stubs; returns the stubs written."""
    Path(dest).mkdir(parents=True)
    data = _git(cache_repo, "archive", "--format=tar", rev, data=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:                                      # Python before 3.11.4: git archive writes no links outside
            tf.extractall(dest)
    return write_stubs(dest, spec)


def make_parent_repo(cache_repo: Path, sha: str, spec: dict, dest: Path) -> dict:
    """`dest` as a new repository holding only the parent's tree in a single commit (plus the stubs)."""
    parent = pin(cache_repo, sha)
    stubs = export_tree(cache_repo, parent, spec, dest)
    _git(dest, "init", "-q")
    _git(dest, "add", "-A")
    if stubs:
        _git(dest, "add", "-f", "--", *stubs)
    _git(dest, "commit", "-q", "--no-verify", "-m", "start")
    return {"parent": parent, "stubs": stubs}


def hidden_tests(cache_repo: Path, sha: str, tests: list[str]) -> dict[str, bytes]:
    """The commit's own versions of the test files."""
    return {t: _git(cache_repo, "show", f"{sha}:{t}", data=True) for t in tests}


def ref_change(cache_repo: Path, sha: str, test_dirs: tuple[str, ...] = ("tests/",)) -> dict:
    """The reference change's size, counted as for this repository: changed lines in code and config files outside
    the test folders (docs and changelogs not counted)."""
    lines, files = 0, []
    for row in _git(cache_repo, "diff", "--numstat", f"{sha}^", sha).splitlines():
        add, rem, name = row.split("\t", 2)
        if name.startswith(test_dirs) or not name.endswith(CODE) or add == "-":
            continue
        lines += int(add) + int(rem)
        files.append(name)
    return {"size": lines, "files": files}


def run_env(spec: dict) -> dict:
    """Environment additions for running the repository's tests uninstalled (relative, so a worktree uses its own)."""
    return {"PYTHONPATH": spec.get("pythonpath", "src")}
