"""Hold-out task set (backlog C1) and its selection in r5.py: task list and flags only (no git history, no real CLI)."""
import contextlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import holdout_check  # noqa: E402
import r5  # noqa: E402
import tasks_holdout  # noqa: E402
import tasks_r5  # noqa: E402


def test_holdout_tasks_are_complete_and_in_band():
    assert len(tasks_holdout.IDS) == len(set(tasks_holdout.IDS)) == 10
    lo, hi = holdout_check.BAND_LINES
    for t in tasks_holdout.T:
        assert t["brief"] and t["area"] and len(t["commit"]) >= 7
        assert len(t["tests"]) == 1 and t["tests"][0].startswith("tests/") and t["tests"][0].endswith(".py")
        assert lo <= t["size"] <= hi and holdout_check.BAND_FILES[0] <= t["files"] <= holdout_check.BAND_FILES[1]
        assert "\\" not in t["brief"] and ":/" not in t["brief"]          # generic: no local paths


def test_holdout_shares_nothing_with_r5():
    assert not set(tasks_holdout.IDS) & set(tasks_r5.IDS)
    r5_commits = [t["commit"] for t in tasks_r5.T]
    for t in tasks_holdout.T:
        assert not any(c.startswith(t["commit"]) or t["commit"].startswith(c) for c in r5_commits), t["id"]
    assert len({t["area"] for t in tasks_holdout.T}) == 10                # one task per feature area


def test_r5_stays_the_default():
    a = r5.parser().parse_args(["run"])
    assert a.taskset == "r5" and r5.IDS == tasks_r5.IDS
    assert r5.results_file("r5") == r5.OUT / "results.jsonl"
    assert r5.results_file("holdout") != r5.results_file("r5")
    assert r5.parser().parse_args(["summary"]).taskset == "r5"


def test_by_id_finds_tasks_of_either_set():
    assert r5.by_id(tasks_r5.IDS[0])["commit"] == tasks_r5.T[0]["commit"]
    assert r5.by_id(tasks_holdout.IDS[0])["commit"] == tasks_holdout.T[0]["commit"]
    with pytest.raises(KeyError):
        r5.by_id("no-such-task")


def _dry(tmp_path, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = r5.main(["run", "--dry-run", "--rounds", "1", "--arms", "self", "--out", str(tmp_path / "res.jsonl"),
                      "--workdir", str(tmp_path / "work"), *extra])
    return rc, buf.getvalue()


def test_taskset_flag_schedules_the_holdout_tasks(tmp_path):
    rc, out = _dry(tmp_path, "--taskset", "holdout")
    assert rc == 0
    assert {ln.split(":")[3] for ln in out.splitlines() if ln.startswith("[dry]")} == set(tasks_holdout.IDS)
    rc, out = _dry(tmp_path)
    assert {ln.split(":")[3] for ln in out.splitlines() if ln.startswith("[dry]")} == set(tasks_r5.IDS)


def test_tasks_must_belong_to_the_chosen_set(tmp_path):
    with pytest.raises(SystemExit):
        _dry(tmp_path, "--tasks", tasks_holdout.IDS[0])                  # a hold-out id under the default r5 set
    rc, out = _dry(tmp_path, "--taskset", "holdout", "--tasks", tasks_holdout.IDS[0])
    assert rc == 0 and out.count("[dry]") == 1


def test_deselected_tests_are_left_out_of_scoring():
    t = tasks_holdout.by_id("send-busy-guard")
    assert t["deselect"] and all(n.startswith(t["tests"][0] + "::") for n in t["deselect"])
    assert r5.pytest_args(t) == [*t["tests"], "--deselect", t["deselect"][0]]
    assert r5.pytest_args(tasks_r5.T[0]) == tasks_r5.T[0]["tests"]          # r5 tasks run as before


def test_other_worktrees_of_the_checkout_are_forbidden(tmp_path):
    import preflight as PF
    other = tmp_path / "sibling-worktree"
    real = {**PF.real_paths(), "root_worktrees": [other]}
    u = PF.Unit(key="k", work=tmp_path / "work", repo=tmp_path / "work" / "k", hub=tmp_path / "work" / "h-k",
                real=real)
    assert other in PF.forbidden(u)
    assert any("sibling-worktree" in d for d in PF.claude_settings(u)["permissions"]["deny"])
