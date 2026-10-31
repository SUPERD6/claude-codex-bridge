"""Write bench/tasks/<set>/<id>.md, one file per task, from the task sets the evaluation runs
(scripts/eval/tasks_r5.py, scripts/eval/tasks_holdout.py). Those modules stay the source of truth: this only reads
them, and tests/test_bench.py fails when a file here no longer matches them.

    python bench/make_tasks.py           # rewrite the files
    python bench/make_tasks.py --check   # exit 1 if any file is out of date

A task of another repository carries only a pointer (its URL, the full commit, the test file's path): none of its code
or tests is copied here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "eval"))
import tasks_holdout  # noqa: E402
import tasks_r5  # noqa: E402

OUT = Path(__file__).resolve().parent / "tasks"
OWN = "https://github.com/SUPERD6/relayline"
SETS = {"r5": tasks_r5, "holdout": tasks_holdout}
INTRO = {
    "r5": "r5 dev set: the tasks ccx was tuned on. Numbers on them are a signal, not a claim.",
    "holdout": "hc1 hold-out set: not used while building ccx, until it was published here. Now that it is public it "
               "is no longer a hold-out set (see bench/README.md).",
}


def pytest_cmd(t: dict, repo: dict | None) -> str:
    args = " ".join([*t["tests"], *(f"--deselect {n}" for n in t.get("deselect") or ())])
    env = f"PYTHONPATH={repo['pythonpath']} " if repo else ""
    color = " --color=no" if repo else ""
    return f"{env}python -m pytest -q -p no:cacheprovider{color} {args}"


def render(set_name: str, t: dict) -> str:
    ext = tasks_holdout.external(t)
    repo = tasks_holdout.REPOS[t["repo"]] if ext else None
    url = repo["url"].removesuffix(".git") if repo else OWN
    lines = [f"# {t['id']}", "", f"Set: `{set_name}`. {INTRO[set_name]}", ""]
    lines += ["| | |", "|---|---|"]
    if ext:
        lines += [f"| Repository | {url} ({repo['license']}; not copied here) |",
                  f"| Commit (the reference change) | `{t['commit']}` |",
                  f"| Starting point | its parent, `{t['commit']}^`, as a fresh one-commit repository |",
                  f"| Python for the tests | 3.11+ with {', '.join(repo['needs'])}"
                  + (f" (pytest {repo['pytest_min']} or newer)" if repo.get("pytest_min") else "")
                  + f", without `{repo['module']}` installed |"]
    else:
        lines += [f"| Repository | this one ({url}) |",
                  f"| Commit (the reference change) | `{t['commit']}` |",
                  f"| Starting point | its parent, `{t['commit']}^`, plus today's `tests/conftest.py` |"]
    if t.get("area"):
        lines.append(f"| Area | {t['area']} |")
    if t.get("size"):
        lines.append(f"| Reference size | {t['size']} non-test lines in {t['files']} file(s) |")
    lines += ["", "## Brief", "", "The person's request, as the lead agent gets it inside its prompt (the whole prompt: `LEAD_PROMPT` / "
             "`LEAD_PROMPT_EXT` in scripts/eval/r5.py).", "", t["brief"], "", "## Acceptance (hidden tests)", ""]
    if ext:
        links = ", ".join(f"[`{p}`]({url}/blob/{t['commit']}/{p})" for p in t["tests"])
        lines += [f"The commit's own test file(s): {links}. Before scoring, the repository's test folder and test "
                  "settings are put back as they were at the parent and these files are written over them"
                  + (f"; the files its install would generate are stubbed ({', '.join(f'`{x}`' for x in repo['stubs'])})"
                     if repo["stubs"] else "")
                  + "; then, from the repository root:"]
    else:
        shows = "; ".join(f"`git show {t['commit']}:{p}`" for p in t["tests"])
        lines += [f"The commit's own test file(s), read from this repository's history: {shows}. They are written "
                  "over whatever the agent left in them, with today's `tests/conftest.py`; then, in throwaway "
                  "HOME / CCX_HUB / CODEX_HOME / CLAUDE_CONFIG_DIR folders:"]
    lines += ["", "```bash", pytest_cmd(t, repo), "```", "",
              "Right = that command exits 0. The tests are public (they always were, in the commit's history), so "
              "an agent that looks the commit up can find the answer. For external tasks the evaluation takes "
              "Claude's web tools and the copies of the repository away from its agents; a download from a shell "
              "is not blocked, only flagged by the audit; and a model may remember an older commit."]
    if t.get("deselect"):
        lines += ["", "Deselected: unrelated tests of the same file that fail at random under load; they are left out "
                  "for every arm."]
    return "\n".join(lines) + "\n"


def expected() -> dict[Path, str]:
    return {OUT / name / f"{t['id']}.md": render(name, t) for name, mod in SETS.items() for t in mod.T}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only report files that are out of date")
    a = ap.parse_args(argv)
    want = expected()
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    extra = [p for p in OUT.glob("*/*.md") if p not in want]
    if a.check:
        for p in stale + extra:
            print(f"out of date: {p.relative_to(ROOT).as_posix()}")
        return 1 if stale or extra else 0
    for p in extra:
        p.unlink()
    for p, text in want.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(want)} task files under {OUT.relative_to(ROOT).as_posix()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
