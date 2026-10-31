"""The polyglot task set (P0-5): 30 Python exercises of aider's polyglot benchmark, an outside benchmark with a
difficulty spread, so that routing, review and climbing a rung can show on tasks a cheap model fails.

Source: github.com/Aider-AI/polyglot-benchmark, pinned at one commit (REPOS). The exercises come from Exercism's
Python track (MIT); aider picked the 225 (of 697, six languages) that 3 or fewer of 7 models solved in 2024. Which 30,
and why, is in polyglot_selection.json (read here, so the list lives in one place); the choice looked at no solution.

A unit is one exercise, not a commit: scripts/eval/ext_repo.exercise_material reads, from a clone made before the
run, the exercise folder's starting files (the stub the person edits: `solution` in .meta/config.json) and nothing
else, so the unit's repository has no .meta/ (the example solution), .approaches/, .docs/ or tests, and no history.
The brief is the exercise's own instructions (.docs: introduction, instructions, instructions.append, as aider gives
them) plus a short addendum like aider's. The exercise's test files are the hidden test: scoring copies only the
solution files the agent left into a fresh folder with the tests and a pytest.ini of its own, so nothing else the
agent wrote (tests of its own, conftest.py, pytest settings) applies.

Default arms for this set: self (the lead does it), ccx2 (the lead hands it to ccx), direct (no lead, ccx on Codex
gpt-6-luna low): r5.py run --taskset polyglot.
"""
from __future__ import annotations

import json
from pathlib import Path

SELECTION_FILE = Path(__file__).with_name("polyglot_selection.json")
SELECTION = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
COMMIT = SELECTION["source"]["commit"]

REPOS = {
    "polyglot": {"url": SELECTION["source"]["repo"] + ".git", "license": "MIT (Exercism Python track)",
                 "name": "a small Python exercise",
                 "pythonpath": ".", "stubs": [], "needs": ["pytest"], "kind": "exercise",
                 # what the audit flags besides the repository's own URL: fetching from the exercises' public
                 # homes (a fetch command naming them; the word alone is in some instructions, e.g. image links,
                 # so a lead that copies the brief into a ccx call is not flagged for it)
                 "flags": [r"\b(curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm|git\s+clone)\b[^\n]*"
                           r"(exercism|problem-specifications|polyglot-benchmark)",
                           # a copy of the benchmark (e.g. an --ext-cache clone): its example solutions and notes
                           r"\.meta[\\/]+example", r"\.approaches\b", r"\bpolyglot\.git\b"]},
}
ARMS = ("self", "ccx2", "direct")           # the default schedule of this task set

ADDENDUM = """
####

Use the above instructions to modify the supplied files: {files}
Don't change the names of existing functions or classes, as they may be referenced from other code like unit tests.
Only use the standard library; nothing can be installed. The exercise's own tests are not in this folder: they are
hidden and run on {files} after you finish, so write and run checks of your own if you want them. Only {files} is
scored; other files you add are not used."""


# What a delegating lead (ccx2) is told to pass as --check for an exercise, in place of "a pytest command for the
# relevant test files" (there are none): the sub-agent writes a test file of its own and ccx runs it. self's lead
# can do the same with the addendum's "write and run checks of your own".
CHECK_PLACEHOLDER = "<a pytest command for the relevant test files>"
CHECK_EXERCISE = ("<a pytest command for a test file of its own that your brief asks the sub-agent to write next to "
                  "the solution, e.g. python -m pytest -q test_own.py>")

# ... and how it passes the brief: an exercise's instructions are long and full of backticks and $ signs, which a
# shell would expand inside double quotes (only the delegating arm puts the brief on a command line)
BRIEF_FILE = ("The instructions contain backticks and $ signs: write the brief to a file first (e.g. brief.md in "
              "this folder; it is not scored) and pass it with --brief-file <that file> instead of in quotes.")


def _task(it: dict) -> dict:
    d = f"python/exercises/practice/{it['slug']}"
    return {"id": it["id"], "repo": "polyglot", "commit": COMMIT, "kind": "exercise", "dir": d,
            "language": it["language"], "solution": list(it["solution"]), "tests": list(it["test"]),
            "area": f"polyglot: {it['slug']}", "difficulty": it["exercism_difficulty"], "n_tests": it["tests"],
            "brief": f"(the instructions of the Exercism exercise {it['slug']}, read when the run starts)"}


T: list[dict] = [_task(it) for it in SELECTION["tasks"]]
DROPPED: list[dict] = [{**_task(it), "dropped": it["why"]} for it in SELECTION["dropped"]]
IDS = [t["id"] for t in T]


def by_id(task_id: str) -> dict:
    return dict(next(t for t in T if t["id"] == task_id))


def brief(task: dict, docs: dict[str, str]) -> str:
    """The brief of one exercise: its .docs texts in aider's order, then the addendum naming the solution files."""
    parts = [docs[n] for n in ("introduction.md", "instructions.md", "instructions.append.md") if docs.get(n)]
    files = ", ".join(task["solution"])
    return ("\n\n".join(p.strip() for p in parts) + ADDENDUM.format(files=files)).strip()
