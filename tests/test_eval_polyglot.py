"""The polyglot task set (scripts/eval/tasks_polyglot.py, ext_repo.exercise_material, r5.score_exercise), on a local
fake upstream laid out like aider's polyglot benchmark: no network, no real agent CLI."""
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import ext_repo  # noqa: E402
import r5  # noqa: E402
import tasks_polyglot  # noqa: E402

DIR = "python/exercises/practice/fake-ex"
STUB = "def double(x):\n    pass\n"
EXAMPLE = "def double(x):\n    return x * 2  # SECRET-EXAMPLE\n"
HELPER = "TWO = 2\n"
TEST = ("import unittest\n\nfrom fake_ex import double\nfrom fake_utils import TWO\n\n\n"
        "class FakeTest(unittest.TestCase):\n"
        "    def test_two(self):\n        self.assertEqual(double(TWO), 4)\n\n"
        "    def test_neg(self):\n        self.assertEqual(double(-3), -6)\n")
TESTS = ["fake_ex_test.py", "fake_utils.py"]
CONFIG = {"files": {"solution": ["fake_ex.py"], "test": TESTS, "example": [".meta/example.py"]}}


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c",
                           "core.autocrlf=false", *args], cwd=cwd, capture_output=True, text=True, check=True
                          ).stdout.strip()


@pytest.fixture(autouse=True)
def fresh_material():
    r5._EXT.clear()
    yield
    r5._EXT.clear()


@pytest.fixture()
def upstream(tmp_path, monkeypatch):
    """source/fakepoly: one exercise folder with its stub, test, docs, example solution and approaches."""
    src = tmp_path / "source" / "fakepoly"
    files = {f"{DIR}/fake_ex.py": STUB, f"{DIR}/fake_ex_test.py": TEST, f"{DIR}/fake_utils.py": HELPER,
             f"{DIR}/.meta/config.json": json.dumps(CONFIG), f"{DIR}/.meta/example.py": EXAMPLE,
             f"{DIR}/.approaches/introduction.md": "SECRET-APPROACH\n",
             f"{DIR}/.docs/instructions.md": "# Instructions\n\nDouble the number.\n",
             f"{DIR}/.docs/instructions.append.md": "# Append\n\nRaise nothing.\n",
             f"{DIR}/.docs/hints.md": "SECRET-HINT\n"}
    for rel, text in files.items():
        f = src / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(text.encode("utf-8"))
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "copy")
    sha = git(src, "rev-parse", "HEAD")
    spec = {**tasks_polyglot.REPOS["polyglot"], "url": "https://example.invalid/fakepoly.git"}
    monkeypatch.setitem(tasks_polyglot.REPOS, "fakepoly", spec)
    task = {"id": "pg-fake-ex", "repo": "fakepoly", "commit": sha, "kind": "exercise", "dir": DIR,
            "language": "python", "solution": ["fake_ex.py"], "tests": TESTS, "area": "polyglot: fake",
            "n_tests": 2, "brief": "(read at the start)"}
    monkeypatch.setattr(tasks_polyglot, "T", tasks_polyglot.T + [task])
    monkeypatch.setattr(tasks_polyglot, "IDS", tasks_polyglot.IDS + [task["id"]])
    return {"source": tmp_path / "source", "sha": sha, "task": task}


# ------------------------------------------------------------------ the selection

def test_selection_is_thirty_python_exercises_pinned_and_recorded():
    sel = tasks_polyglot.SELECTION
    assert len(tasks_polyglot.IDS) == len(set(tasks_polyglot.IDS)) == 30
    assert re.fullmatch(r"[0-9a-f]{40}", sel["source"]["commit"]) and sel["source"]["checked"]
    assert "MIT" in sel["source"]["license"] and sel["rule"] and sel["gradient_note"]
    for it in sel["tasks"] + sel["dropped"]:
        assert it["language"] == "python" and it["why"] and it["id"] == "pg-" + it["slug"]
        assert it["solution"] and it["test"] and all(t.endswith(".py") for t in it["test"])
    dropped = {it["slug"] for it in sel["dropped"]}
    assert len(dropped) == 4 and not dropped & {it["slug"] for it in sel["tasks"]}
    # the rule as written: the dropped ones are the 4 lowest by (Exercism difficulty, number of tests)
    every = sorted(sel["tasks"] + sel["dropped"], key=lambda it: (it["exercism_difficulty"], it["tests"]))
    assert {it["slug"] for it in every[:4]} == dropped
    assert tasks_polyglot.DROPPED and all(t["dropped"] for t in tasks_polyglot.DROPPED)


def test_selection_holds_no_solution_text():
    text = tasks_polyglot.SELECTION_FILE.read_text(encoding="utf-8")
    assert not re.search(r"\bdef \w+\(|\breturn\b|\bclass \w+[:(]|\bimport \w+", text)       # no code at all


def test_task_ids_are_unique_across_task_sets():
    ids = [i for mod in r5.TASKSETS.values() for i in mod.IDS]
    assert len(ids) == len(set(ids))
    t = r5.by_id("pg-zipper")
    assert r5.is_exercise(t) and t["repo"] == "polyglot" and t["commit"] == tasks_polyglot.COMMIT


# ------------------------------------------------------------------ material: nothing of the answer reaches a unit

def test_material_has_the_stub_only_and_the_tests_hidden(upstream, tmp_path):
    task, work = upstream["task"], tmp_path / "work"
    work.mkdir()
    m = r5.ext_material(task, work, upstream["source"], cache=tmp_path / "c")
    assert ext_repo.tar_names(m["tar"]) == ["fake_ex.py"]
    assert m["tests"] == {"fake_ex_test.py": TEST.encode(), "fake_utils.py": HELPER.encode()}
    brief = r5.by_id(task["id"])["brief"]                     # the instructions replace the placeholder
    assert "Double the number." in brief and "Raise nothing." in brief and "fake_ex.py" in brief
    assert "SECRET" not in brief and "SECRET" not in m["tar"].decode("utf-8", "replace")
    assert brief.index("Double the number.") < brief.index("Raise nothing.") < brief.index("####")


def test_material_refuses_a_task_whose_files_differ_from_the_config(upstream, tmp_path):
    with pytest.raises(ValueError):
        ext_repo.exercise_material(ext_repo.fetch("fakepoly", tasks_polyglot.REPOS["fakepoly"], tmp_path / "c",
                                                  upstream["source"]),
                                   upstream["sha"], DIR, ["fake_ex.py"], ["fake_ex_test.py"])
    with pytest.raises(ValueError):
        ext_repo.exercise_material(tmp_path, upstream["sha"][:7], DIR, ["fake_ex.py"], TESTS)


def test_unit_repository_has_no_meta_docs_tests_or_history(upstream, tmp_path):
    task, work = upstream["task"], tmp_path / "work"
    work.mkdir()
    r5.ext_material(task, work, upstream["source"], cache=tmp_path / "c")
    repo = work / "1-pg-fake-ex-self"
    r5.make_repo(task, repo, work, upstream["source"])
    assert git(repo, "ls-files").split() == ["fake_ex.py"]
    assert git(repo, "rev-list", "--count", "HEAD") == "1" and not git(repo, "remote")


# ------------------------------------------------------------------ scoring

def _unit(upstream, tmp_path):
    task, work = upstream["task"], tmp_path / "work"
    work.mkdir()
    r5.ext_material(task, work, upstream["source"], cache=tmp_path / "c")
    repo = work / "1-pg-fake-ex-self"
    r5.make_repo(task, repo, work, upstream["source"])
    return task, work, repo


def test_score_fails_the_stub_and_passes_a_right_answer(upstream, tmp_path):
    task, work, repo = _unit(upstream, tmp_path)
    before = r5.score(repo, task, work, source=upstream["source"])
    assert not before["ok"] and "2 failed" in before["pytest"] and len(before["failed"]) == 2
    (repo / "fake_ex.py").write_text("def double(x):\n    return 2 * x\n", encoding="utf-8")
    after = r5.score(repo, task, work, source=upstream["source"])
    assert after["ok"] and "2 passed" in after["pytest"]


def test_nothing_else_the_agent_writes_applies_to_scoring(upstream, tmp_path):
    task, work, repo = _unit(upstream, tmp_path)
    # a wrong answer, plus everything that could make the hidden tests pass or vanish
    (repo / "fake_ex_test.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (repo / "conftest.py").write_text("collect_ignore_glob = ['*_test.py']\n", encoding="utf-8")
    (repo / "pytest.ini").write_text("[pytest]\naddopts = -p no:unittest\n", encoding="utf-8")
    (repo / "unittest.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    sc = r5.score(repo, task, work, source=upstream["source"])
    assert not sc["ok"] and "2 failed" in sc["pytest"]
    assert not list(work.glob("r5iso-*"))                     # the scoring folder is gone


def test_a_missing_solution_file_is_a_failure(upstream, tmp_path):
    task, work, repo = _unit(upstream, tmp_path)
    (repo / "fake_ex.py").unlink()
    sc = r5.score(repo, task, work, source=upstream["source"])
    assert not sc["ok"] and "missing solution" in sc["pytest"]


def test_hidden_tests_never_reach_the_unit_repository(upstream, tmp_path):
    task, work, repo = _unit(upstream, tmp_path)
    r5.score(repo, task, work, source=upstream["source"])
    assert not (repo / "fake_ex_test.py").exists() and not (repo / "fake_utils.py").exists()


# ------------------------------------------------------------------ the lead, the guard and the schedule

def test_exercise_prompt_env_and_guard(upstream, tmp_path):
    task = upstream["task"]
    spec = r5.ext_spec(task)
    text = r5.LEAD_PROMPT_EXERCISE.format(name=spec["name"], brief="BRIEF", how="HOW")
    assert "BRIEF" in text and "HOW" in text and "PYTHONPATH=src" not in text and "{" not in text
    assert "relayline" not in text and "Exercism" not in text
    env = r5.task_env(task, {"PATH": "p"})
    assert env["PIP_NO_INDEX"] == "1" and env["PYTHONPATH"] == "."
    g = r5.ext_guard(task, type("A", (), {"ext_cache": ""})(), tmp_path)
    assert g["deny"] == ("WebFetch", "WebSearch")
    flags = [re.compile(f, re.I) for f in g["flags"]]
    assert any(f.search("curl -s https://raw.githubusercontent.com/exercism/python/main/x") for f in flags)
    assert any(f.search("git clone https://github.com/Aider-AI/polyglot-benchmark") for f in flags)
    # a brief copied into a ccx call mentions the word (image links, notes): not flagged
    assert not any(f.search('ccx run "... https://assets.exercism.org/images/x.svg ..."') for f in flags)


def _dry(tmp_path, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = r5.main(["run", "--dry-run", "--rounds", "1", "--out", str(tmp_path / "res.jsonl"),
                      "--workdir", str(tmp_path / "work"), *extra])
    return rc, buf.getvalue()


def test_polyglot_schedules_thirty_tasks_on_its_three_arms(tmp_path):
    rc, out = _dry(tmp_path, "--taskset", "polyglot")
    assert rc == 0
    units = re.findall(r"\[dry\] eval-r5:r5:1:(pg-[a-z-]+):(\w+)", out)
    assert len(units) == 90 and {a for _t, a in units} == set(tasks_polyglot.ARMS)
    assert {t for t, _a in units} == set(tasks_polyglot.IDS)
    assert not (tmp_path / "work").exists()                    # a dry run fetches nothing


def test_other_task_sets_keep_their_default_arms(tmp_path):
    rc, out = _dry(tmp_path, "--taskset", "holdout")
    arms = set(re.findall(r"\[dry\] eval-r5:r5:1:[\w-]+:(\w+)", out))
    assert rc == 0 and arms == set(r5.ARMS)
    assert r5.results_file("polyglot") == r5.OUT / "polyglot-results.jsonl"


# ------------------------------------------------------------------ after the adversarial review

@pytest.mark.parametrize("cheat", [
    "import unittest\nraise unittest.SkipTest('x')\n",                    # the whole module skipped, rc 0
    "import pytest\npytest.skip('x', allow_module_level=True)\n",
    "import os\nos._exit(0)\n",                                            # no summary line at all
])
def test_a_solution_that_skips_or_exits_is_not_right(upstream, tmp_path, cheat):
    task, work, repo = _unit(upstream, tmp_path)
    (repo / "fake_ex.py").write_text(cheat, encoding="utf-8")
    assert not r5.score(repo, task, work, source=upstream["source"])["ok"]


def test_exercise_passed_wants_every_hidden_test_and_nothing_else():
    P = r5.exercise_passed
    assert P(0, "14 passed in 0.21s", 14) and P(0, "14 passed, 2 warnings in 0.2s", 14) and P(0, "3 passed in 1s", None)
    assert not P(0, "13 passed in 0.2s", 14)                     # fewer than the exercise has
    assert not P(0, "13 passed, 1 skipped in 0.2s", 14) and not P(0, "1 skipped in 0.1s", None)
    assert not P(0, "", 14) and not P(1, "14 passed in 0.2s", 14) and not P(0, "14 passed, 1 xfailed", 14)
    assert not P(0, "no tests ran in 0.01s", None) and not P(0, "13 passed, 1 error in 0.3s", None)


def test_every_task_carries_its_test_count():
    assert all(t["n_tests"] > 0 for t in tasks_polyglot.T)
    assert r5.by_id("pg-paasio")["tests"] == ["paasio_test.py", "test_utils.py"]


def test_a_delegating_lead_gets_a_check_it_can_run_and_the_brief_by_file(upstream):
    task = upstream["task"]
    u = {"arm": "ccx2", "label": "L"}
    how = r5.unit_how(u, task)
    assert tasks_polyglot.CHECK_PLACEHOLDER not in how and tasks_polyglot.CHECK_EXERCISE in how
    assert "--brief-file" in how
    assert r5.unit_how({"arm": "self", "label": "L"}, task) == r5.lead_how("self", "L")     # self: unchanged
    other = r5.by_id(r5.IDS[0])                                                           # r5 tasks: unchanged
    assert r5.unit_how(u, other) == r5.lead_how("ccx2", "L")


def test_an_exercise_is_never_cloned_into_the_work_dir(upstream, tmp_path):
    with pytest.raises(RuntimeError):
        r5.ext_material(upstream["task"], tmp_path / "work", upstream["source"])      # no cache: not prepared
    assert not (tmp_path / "work").exists()


def test_a_copy_next_to_the_work_dir_is_refused(upstream, tmp_path, monkeypatch):
    work = tmp_path / "work"
    a = type("A", (), {"ext_cache": str(upstream["source"]), "ext_python": ""})()
    probs = r5.prepare_external([{"task": upstream["task"]["id"]}], a, work)
    assert any("--ext-cache copies" in p and "work dir" in p for p in probs), probs
    a.ext_cache = str(tmp_path / "x" / "y" / "copies")          # its parent (x/y) does not hold the work dir
    probs = r5.prepare_external([{"task": upstream["task"]["id"]}], a, tmp_path / "elsewhere" / "work")
    assert not any("work dir" in p for p in probs), probs


def test_polyglot_check_grades_stub_and_example(upstream, tmp_path):
    import polyglot_check
    res = polyglot_check.check(upstream["task"], tmp_path / "w", tmp_path / "c", str(upstream["source"]))
    assert res["ok"] and "2 failed" in res["stub"] and "2 passed" in res["example"], res
