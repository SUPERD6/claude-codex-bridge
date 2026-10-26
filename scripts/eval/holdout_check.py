"""Check a task set the way r5.py scores it: for every task the hidden test fails at the commit's parent and passes
at the commit, the reference change is in the difficulty band, and (for the hold-out set) nothing leaks from r5.

For each task: `git archive` of the parent and of the commit into a scratch folder, today's tests/conftest.py, the
commit's own test files over whatever is there, then only those files run with r5.score (throwaway HOME / CCX_HUB /
CODEX_HOME / CLAUDE_CONFIG_DIR / CCX_CONFIG). No agent CLI is called.

  python scripts/eval/holdout_check.py                       # the hold-out set, 3 tasks at a time
  python scripts/eval/holdout_check.py --taskset r5 --tasks waiting-evals
  python scripts/eval/holdout_check.py --static              # band and leakage only, no pytest
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r5  # noqa: E402
from common import ROOT  # noqa: E402

BAND_LINES = (5, 91)        # changed non-test lines of the reference change (r5: 5-91, median ~40)
BAND_FILES = (1, 5)
CODE = (".py", ".toml")     # what counts: code and config, not docs, CHANGELOG or changes/*.md


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout


def ref_change(commit: str) -> dict:
    """The reference change's size: changed lines and files in code outside tests/."""
    lines, files = 0, []
    for row in _git("diff", "--numstat", f"{commit}^", commit).splitlines():
        add, rem, name = row.split("\t", 2)
        if name.startswith("tests/") or not name.endswith(CODE) or add == "-":
            continue
        lines += int(add) + int(rem)
        files.append(name)
    return {"size": lines, "files": files}


def _tree(rev: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    data = subprocess.run(["git", "archive", rev], cwd=ROOT, capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(data)).extractall(dest)


def static(task: dict, against: list[dict]) -> list[str]:
    """Problems found without running anything: band, recorded size, leakage from the other set's tasks."""
    out = []
    ch = ref_change(task["commit"])
    if not BAND_LINES[0] <= ch["size"] <= BAND_LINES[1]:
        out.append(f"size {ch['size']} outside {BAND_LINES}")
    if not BAND_FILES[0] <= len(ch["files"]) <= BAND_FILES[1]:
        out.append(f"{len(ch['files'])} files outside {BAND_FILES}")
    if "size" in task and (task["size"], task["files"]) != (ch["size"], len(ch["files"])):
        out.append(f"recorded size/files {task['size']}/{task['files']} != {ch['size']}/{len(ch['files'])}")
    for t in task["tests"]:
        if not _git("ls-tree", "--name-only", task["commit"], t).strip():
            out.append(f"{t} missing at {task['commit']}")
    for node in task.get("deselect") or ():
        f, _, name = node.partition("::")
        if f not in task["tests"] or f"def {name.split('::')[-1]}(" not in _git("show", f"{task['commit']}:{f}"):
            out.append(f"deselect {node} is not a test of {task['tests']} at {task['commit']}")
    full = _git("rev-parse", task["commit"]).strip()
    for o in against:
        if _git("rev-parse", o["commit"]).strip() == full:
            out.append(f"same commit as {o['id']}")
    return out


def dynamic(task: dict, work: Path) -> dict:
    """The hidden test at the parent (must fail) and at the commit (must pass)."""
    res = {}
    for side, rev in (("parent", f"{task['commit']}^"), ("commit", task["commit"])):
        d = Path(tempfile.mkdtemp(prefix=f"{task['id']}-{side}-", dir=work))
        try:
            _tree(rev, d / "repo")
            res[side] = r5.score(d / "repo", task, d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return res


def check(task: dict, against: list[dict], work: Path, run_tests: bool) -> dict:
    ch = ref_change(task["commit"])
    row = {"id": task["id"], "commit": task["commit"], "area": task.get("area"), "size": ch["size"],
           "files": ch["files"], "tests": task["tests"], "problems": static(task, against)}
    shared = sorted(set(ch["files"]) & {f for o in against for f in ref_change(o["commit"])["files"]})
    if shared:
        row["files_shared_with_other_set"] = shared        # allowed, but worth seeing (a different function)
    if run_tests:
        dyn = dynamic(task, work)
        row.update(parent=dyn["parent"]["pytest"], commit_result=dyn["commit"]["pytest"])
        if dyn["parent"]["ok"]:
            row["problems"].append("hidden test passes at the parent")
        if not dyn["commit"]["ok"]:
            row["problems"].append("hidden test fails at the commit")
    row["ok"] = not row["problems"]
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--taskset", choices=sorted(r5.TASKSETS), default="holdout")
    ap.add_argument("--tasks", default="", help="comma-separated ids (default: the whole set)")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--static", action="store_true", help="band and leakage only, no pytest")
    ap.add_argument("--workdir", default="", help="scratch folder (default: a new temp folder, removed after)")
    a = ap.parse_args(argv)
    mod = r5.TASKSETS[a.taskset]
    ids = a.tasks.split(",") if a.tasks else mod.IDS
    against = [t for name, m in r5.TASKSETS.items() if name != a.taskset for t in m.T]
    work = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="holdout-check-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
            rows = list(ex.map(lambda i: check(mod.by_id(i), against, work, not a.static), ids))
    finally:
        if not a.workdir:
            shutil.rmtree(work, ignore_errors=True)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False), flush=True)
    bad = [r["id"] for r in rows if not r["ok"]]
    print(f"{len(rows) - len(bad)}/{len(rows)} ok" + (f"; failing: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
