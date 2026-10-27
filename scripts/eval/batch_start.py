"""One common start for a batch of past changes (scripts/eval/batch.py): the newest commit of the batch with every
batch commit reverted on it (newest first, git's own three-way revert), so each change's hidden test fails at the
start and all of them pass at that newest commit (the end).

Kept apart from batch.py so it can be used (and tested) without any agent: it only runs git and, for the node
selection, pytest on the hidden test files.

- The source is a throwaway clone (`git clone --shared --no-checkout`) of this checkout or of another repository's
  bare clone (scripts/eval/ext_repo.py); nothing is written to the source.
- A revert whose conflicts touch code or tests drops that commit from the batch (`dropped`, with the files): the
  largest feasible set is what is left. Conflicts in documentation only (.md, .rst, .txt, .adoc) are settled by
  taking the reverted side, so the start's docs do not describe the change (`docs_from_parent`).
- Hidden tests: the end's versions of each change's test files. Per change, its nodes (`nodes`) are those of its
  own test files that pass at the end and fail at the end with only that change reverted (when that revert
  conflicts with a later batch commit: the start with every other batch commit put back, `without_one`); a node
  that passes at the start too is left out (`not_failing_at_start`). A node that fails at the end is left out of everything
  (`failing_at_end`). The start's own test files must not hold a hidden node's test function word for word
  (`leaks`).
"""
from __future__ import annotations

import ast
import io
import re
import subprocess
import tarfile
from pathlib import Path

DOCS = (".md", ".rst", ".txt", ".adoc")
RESULT = re.compile(r"^(PASSED|FAILED|ERROR|XPASS|XFAIL) (.+)$")


def git(cwd: Path | None, *args: str, data: bool = False, check: bool = True):
    r = subprocess.run(["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid",
                        "-c", "core.autocrlf=false", "-c", "advice.detachedHead=false", *args],
                       cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return r if not check else (r.stdout if data else r.stdout.decode("utf-8", "replace"))


def clone(source: Path, dest: Path) -> Path:
    """A throwaway working clone of `source` (a checkout or a bare repository) that shares its objects read-only.
    The source's replace refs come along (a clone leaves them out), so its history reads the same in the clone."""
    git(None, "clone", "-q", "--shared", "--no-checkout", str(source), str(dest))
    git(dest, "fetch", "-q", "origin", "refs/replace/*:refs/replace/*", check=False)
    return dest


def full(repo: Path, rev: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def _is_ancestor(repo: Path, a: str, b: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def plan(repo: Path, commits: list[str], tip: str = "HEAD") -> tuple[str, list[str]]:
    """(the end, the commits newest first). The end is the first commit on `tip`'s first-parent line that has every
    batch commit as an ancestor: the newest batch commit itself when the others are in its history, else the merge
    that brought the last of them in. The order is git's topological one (a commit before its ancestors)."""
    shas = [full(repo, c) for c in commits]
    for s in shas:
        if len(git(repo, "rev-list", "--parents", "-n", "1", s).split()) != 2:
            raise ValueError(f"{s[:12]} must have exactly one parent")
    line = git(repo, "rev-list", "--first-parent", "--reverse", tip).split()
    end = next((x for x in line if all(_is_ancestor(repo, s, x) for s in shas)), None)
    if end is None:
        raise ValueError(f"no commit on the first-parent line of {tip} has all the batch commits")
    topo = git(repo, "rev-list", "--topo-order", end).split()
    pos = {s: i for i, s in enumerate(topo)}
    return end, sorted(shas, key=lambda s: pos[s])


def changed_files(repo: Path, sha: str) -> list[str]:
    return [x for x in git(repo, "diff", "--name-only", f"{sha}^", sha).split("\n") if x.strip()]


def _unmerged(repo: Path) -> list[str]:
    return [x for x in git(repo, "diff", "--name-only", "--diff-filter=U").split("\n") if x.strip()]


def revert_all(repo: Path, base: str, order: list[str]) -> dict:
    """Check out `base` and revert `order` on it one by one (a commit each). Returns what was reverted, what was
    dropped (code or test conflicts) and the documentation files taken from the reverted side."""
    git(repo, "checkout", "-q", "--detach", base)
    git(repo, "reset", "-q", "--hard", base)
    done, dropped, docs = [], {}, []
    for c in order:
        r = git(repo, "revert", "--no-edit", c, check=False)
        if r.returncode == 0:
            done.append(c)
            continue
        um = _unmerged(repo)
        code = [f for f in um if not f.endswith(DOCS)]
        if code or not um:
            git(repo, "revert", "--abort", check=False)
            git(repo, "reset", "-q", "--hard", "HEAD")
            dropped[c] = code or ["revert failed: " + r.stderr.decode("utf-8", "replace").strip()[:200]]
            continue
        for f in um:
            if git(repo, "checkout", "--theirs", "--", f, check=False).returncode:
                git(repo, "rm", "-q", "--", f, check=False)
            else:
                git(repo, "add", "--", f)
        git(repo, "-c", "core.editor=true", "revert", "--continue")
        docs += um
        done.append(c)
    return {"reverted": done, "dropped": dropped, "docs_from_parent": docs, "start": full(repo, "HEAD")}


def without_one(repo: Path, end: str, start: str, order: list[str], sha: str) -> tuple[bytes | None, str]:
    """The tree with only `sha` taken out: `sha` reverted on the end, or, when that revert conflicts (a later batch
    commit changed the same lines), the start with every other batch commit put back (cherry-picked oldest first).
    -> (tar bytes or None, how: 'revert' / 'start+others' / 'none')."""
    git(repo, "checkout", "-q", "--detach", end)
    git(repo, "reset", "-q", "--hard", end)
    if git(repo, "revert", "--no-edit", sha, check=False).returncode == 0:
        return archive(repo, "HEAD"), "revert"
    git(repo, "revert", "--abort", check=False)
    git(repo, "reset", "-q", "--hard", end)
    git(repo, "checkout", "-q", "--detach", start)
    git(repo, "reset", "-q", "--hard", start)
    for c in reversed(order):
        if c == sha:
            continue
        if git(repo, "cherry-pick", "--no-edit", "--allow-empty", c, check=False).returncode:
            git(repo, "cherry-pick", "--abort", check=False)
            git(repo, "reset", "-q", "--hard", start)
            return None, "none"
    return archive(repo, "HEAD"), "start+others"


def archive(repo: Path, rev: str) -> bytes:
    return git(repo, "archive", "--format=tar", rev, data=True)


def extract(data: bytes, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:
            tf.extractall(dest)
    return dest


def show(repo: Path, rev: str, path: str) -> bytes | None:
    r = git(repo, "show", f"{rev}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


def parse_results(text: str) -> dict:
    """Node ids by outcome from `pytest -rA` output (short test summary). A file-level ERROR (collection) names a
    file, not a node: it is kept in `errors` and every node of that file counts as not passed."""
    passed, failed, errors = set(), set(), set()
    for line in (text or "").splitlines():
        m = RESULT.match(line.strip())
        if not m:
            continue
        kind, rest = m.groups()
        node = rest if kind in ("PASSED", "XPASS") else rest.split(" - ", 1)[0]
        node = node.strip()
        if kind in ("PASSED", "XFAIL"):         # an xfail is the expected outcome
            passed.add(node)
        elif kind == "ERROR" and "::" not in node:
            errors.add(node)
        else:
            failed.add(node)
    return {"passed": passed, "failed": failed - passed, "errors": errors}


def node_file(node: str) -> str:
    return node.split("::", 1)[0]


def select_nodes(end: dict, without: dict[str, dict], start: dict, tests: dict[str, list[str]]) -> dict:
    """Per change: the nodes of its own test files that pass at the end and not with only it reverted
    (`without[change]`), minus those that also pass at the start. Returns nodes, the left-out ones and problems."""
    nodes, not_failing, coupled, probs = {}, {}, {}, []
    for tid, files in tests.items():
        w = without.get(tid)
        if w is None:
            probs.append(f"{tid}: no run with only this change reverted")
            nodes[tid] = []
            continue
        gone = end["passed"] - w["passed"]
        own = {n for n in gone if node_file(n) in files}
        other = sorted(gone - own)
        if other:
            coupled[tid] = other                  # reverting it breaks another change's tests too
        keep = sorted(own - start["passed"])
        lost = sorted(own & start["passed"])
        if lost:
            not_failing[tid] = lost
        nodes[tid] = keep
        if not keep:
            probs.append(f"{tid}: no hidden node fails at the start and passes at the end")
    return {"nodes": nodes, "not_failing_at_start": not_failing, "coupled": coupled, "problems": probs}


def _func_sources(text: str) -> dict[str, list[str]]:
    """Every function's source in a test file, by name (methods too)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    out: dict[str, list[str]] = {}
    lines = text.splitlines()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            first = min([d.lineno for d in n.decorator_list] + [n.lineno])
            out.setdefault(n.name, []).append("\n".join(lines[first - 1:n.end_lineno]))
    return out


def leaks(nodes: dict[str, list[str]], hidden: dict[str, bytes], start_files: dict[str, bytes | None]) -> list[str]:
    """Hidden nodes whose test function (with its decorators: a parametrize table holds the expected values) is in
    the start's version of its file word for word."""
    out = []
    for tid, ns in nodes.items():
        for n in ns:
            f = node_file(n)
            name = n.split("::")[-1].split("[", 1)[0]
            h = _func_sources((hidden.get(f) or b"").decode("utf-8", "replace")).get(name) or []
            s = _func_sources((start_files.get(f) or b"").decode("utf-8", "replace")).get(name) or []
            if h and set(h) <= set(s):
                out.append(f"{tid}: {n} is in the start's {f} word for word")
    return sorted(set(out))


def overlap(files: dict[str, list[str]], ignore=DOCS) -> list[dict]:
    """Pairs of changes that touch the same file (documentation and changes/*.md left out)."""
    ids, out = list(files), []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            same = sorted({f for f in files[a] if not f.endswith(ignore) and not f.startswith("changes/")}
                          & set(files[b]))
            if same:
                out.append({"pair": [a, b], "files": same})
    return out
