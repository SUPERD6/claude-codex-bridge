"""Batch / pipeline eval (scripts/eval/batch.py): batch definitions, the common start on a small git repository,
merged-tree scoring, the lead's timeline, arms' wording, dry run and summary. No real agent CLI: the lead is
tests/fakes/fake_claude.py (CCX_CLAUDE_BIN), and nothing here touches the real hub."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import batch as BT  # noqa: E402
import batch_start as BS  # noqa: E402
import r5  # noqa: E402
import tasks_batch as TB  # noqa: E402
import tasks_holdout  # noqa: E402

FAKES = Path(__file__).resolve().parent / "fakes"


@pytest.fixture(autouse=True)
def _fake_claude(monkeypatch):
    monkeypatch.setenv("CCX_CLAUDE_BIN", str(FAKES / "fake_claude.py"))       # CI has no claude


# ------------------------------------------------------------------ definitions

def test_batches_are_hold_out_changes_of_one_repository():
    assert len(TB.IDS) == len(set(TB.IDS)) >= 4
    for b in TB.B:
        ts = [TB.task_by_id(t) for t in b["tasks"]]
        assert len({t.get("repo") for t in ts}) == 1 and ts[0].get("repo") == b.get("repo")
        assert all(t["id"] not in r5.tasks_r5.IDS for t in ts)                  # never an r5 (tuning) task
        assert b["end"] and b["note"]
    ho5, dis = TB.by_id("ho5-overlap"), TB.by_id("ho4-disjoint")
    assert len(ho5["tasks"]) == 5 and len(ho5["overlap"]) == 1                    # one deliberate overlap
    assert dis["overlap"] == [] and set(dis["tasks"]) < set(ho5["tasks"])
    hz = TB.by_id("hz4-overlap")
    assert hz["repo"] == "humanize" and len(hz["tasks"]) == 4 and hz["overlap"] == ["src/humanize/time.py"]
    assert TB.by_id("hz3-disjoint")["overlap"] == []
    known = {t["id"] for t in tasks_holdout.T + tasks_holdout.DROPPED}
    assert all(t in known for b in TB.B for t in b["tasks"])


def test_old_eval_arms_and_tasksets_are_untouched():
    assert r5.ARMS == ("self", "builtin", "ccx", "direct")
    assert not set(BT.ARMS) & set(r5.OPT_IN_ARMS) - {"self", "builtin"}
    assert sorted(r5.TASKSETS) == ["holdout", "r5"]


# ------------------------------------------------------------------ the common start, on a small repository

def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c",
                           "core.autocrlf=false", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout.strip()


A_OLD = "def f():\n    return 1\n\n\ndef h():\n    return 0\n"
TEST_A = "from pkg.a import f\n\n\ndef test_f_old():\n    assert f() in (1, 2)\n"
TEST_A2 = TEST_A + "\n\ndef test_f_new():\n    assert f() == 2\n"
TEST_B = "from pkg.b import g\n\n\ndef test_g_old():\n    assert g() in (1, 2)\n"
TEST_B2 = TEST_B + "\n\ndef test_g_new():\n    assert g() == 2\n"


def _small_repo(d: Path) -> dict:
    """base; A (f returns 2, test_f_new); a later change to a.py near A's hunk; B (g returns 2, test_g_new)."""
    d.mkdir()
    _git(d, "init", "-q")

    def w(p, s):
        (d / p).parent.mkdir(parents=True, exist_ok=True)
        (d / p).write_text(s, encoding="utf-8", newline="\n")

    def commit(m):
        _git(d, "add", "-A")
        _git(d, "commit", "-q", "-m", m)
        return _git(d, "rev-parse", "HEAD")
    w("pkg/__init__.py", "")
    w("pkg/a.py", A_OLD)
    w("pkg/b.py", "def g():\n    return 1\n")
    w("tests/test_a.py", TEST_A)
    w("tests/test_b.py", TEST_B)
    w("README.md", "small\n")
    commit("base")
    w("pkg/a.py", A_OLD.replace("return 1", "return 2"))
    w("tests/test_a.py", TEST_A2)
    ca = commit("A")
    w("pkg/a.py", A_OLD.replace("return 1", "return 2").replace("return 0", "return 5"))
    commit("later, same file, another function")
    w("pkg/b.py", "def g():\n    return 2\n")
    w("tests/test_b.py", TEST_B2)
    cb = commit("B")
    return {"A": ca, "B": cb}


def _tasks(c):
    return [{"id": "A", "commit": c["A"], "tests": ["tests/test_a.py"], "brief": "make f return 2"},
            {"id": "B", "commit": c["B"], "tests": ["tests/test_b.py"], "brief": "make g return 2"}]


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    d = tmp_path_factory.mktemp("small")
    c = _small_repo(d / "src")
    b = {"id": "t", "tasks": ["A", "B"], "overlap": [], "end": c["B"][:7], "note": "test"}
    mat = BT.build(b, d / "tmp", source=d / "src", tasks=_tasks(c))
    return {"dir": d, "commits": c, "batch": b, "mat": mat}


def test_common_start_reverts_every_change_and_finds_hidden_nodes(small):
    mat, c = small["mat"], small["commits"]
    assert mat["problems"] == [], mat["problems"]
    assert mat["end"] == c["B"] and mat["tasks"] == ["A", "B"] and not mat["dropped"]
    assert mat["nodes"] == {"A": ["tests/test_a.py::test_f_new"], "B": ["tests/test_b.py::test_g_new"]}
    assert set(mat["start_passed"]) == {"tests/test_a.py::test_f_old", "tests/test_b.py::test_g_old"}
    assert mat["overlap"] == [] and mat["leaks"] == [] and mat["smoke"] is None
    start = BS.extract(mat["start_tar"], small["dir"] / "start-view")
    assert "return 1" in (start / "pkg/a.py").read_text() and "return 5" in (start / "pkg/a.py").read_text()
    assert "test_f_new" not in (start / "tests/test_a.py").read_text()          # the hidden test is not there
    assert b"test_f_new" in mat["hidden"]["tests/test_a.py"]
    assert "start_tar" not in BT.report(mat) and json.dumps(BT.report(mat))


def test_a_conflicting_revert_drops_that_change(tmp_path):
    d = tmp_path / "src"
    c = _small_repo(d)
    (d / "pkg/a.py").write_text(A_OLD.replace("return 1", "return 3"), encoding="utf-8", newline="\n")
    _git(d, "commit", "-qam", "A's line again (not in the batch)")
    (d / "pkg/b.py").write_text("def g():\n    return 4\n", encoding="utf-8", newline="\n")
    _git(d, "commit", "-qam", "C")
    cl = BS.clone(d, tmp_path / "c")
    tip = BS.full(cl, "HEAD")
    end, order = BS.plan(cl, [c["A"], c["B"]], tip)
    assert end == c["B"] and order == [c["B"], c["A"]]          # the end is the first commit that has both
    end2, order2 = BS.plan(cl, [c["A"], tip], tip)
    res = BS.revert_all(cl, end2, order2)
    assert c["A"] in res["dropped"] and "pkg/a.py" in res["dropped"][c["A"]]
    assert res["reverted"] == [tip]


def test_without_one_reverts_alone_or_says_it_cannot(small, tmp_path):
    c = small["commits"]
    cl = BS.clone(small["dir"] / "src", tmp_path / "c")
    end, order = BS.plan(cl, [c["A"], c["B"]], BS.full(cl, "HEAD"))
    rev = BS.revert_all(cl, end, order)
    tar, how = BS.without_one(cl, end, rev["start"], order, c["A"])
    assert how == "revert" and b"return 2" not in _member(tar, "pkg/a.py") and b"return 2" in _member(tar, "pkg/b.py")
    # two batch changes on adjacent lines: A alone cannot be reverted on the end, nor B put back on the start
    d = tmp_path / "adj"
    d.mkdir()
    _git(d, "init", "-q")
    (d / "x.py").write_text("x = 1\ny = 1\n", encoding="utf-8", newline="\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    (d / "x.py").write_text("x = 2\ny = 1\n", encoding="utf-8", newline="\n")
    ca = _git(d, "commit", "-qam", "A") or _git(d, "rev-parse", "HEAD")
    (d / "x.py").write_text("x = 2\ny = 2\n", encoding="utf-8", newline="\n")
    _git(d, "commit", "-qam", "B")
    cb = _git(d, "rev-parse", "HEAD")
    cl2 = BS.clone(d, tmp_path / "c2")
    end2, order2 = BS.plan(cl2, [ca, cb], cb)
    rev2 = BS.revert_all(cl2, end2, order2)
    assert not rev2["dropped"]                                          # newest first, both revert
    assert BS.without_one(cl2, end2, rev2["start"], order2, BS.full(cl2, ca)) == (None, "none")


def test_without_one_falls_back_to_the_start_with_the_others_put_back(tmp_path):
    """A's revert on the end conflicts (README lines B changed next to A's); the start with B cherry-picked back
    conflicts in README only, which is settled by taking B's side: 'start+others', not 'none'."""
    d = tmp_path / "docs"
    d.mkdir()
    _git(d, "init", "-q")

    def w(p, s):
        (d / p).write_text(s, encoding="utf-8", newline="\n")
    w("README.md", "a\nb\n")
    w("x.py", "x = 1\n")
    w("y.py", "y = 1\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    w("README.md", "A\nb\n")
    w("x.py", "x = 2\n")
    _git(d, "commit", "-qam", "A")
    ca = _git(d, "rev-parse", "HEAD")
    w("README.md", "A\nB\n")
    w("y.py", "y = 2\n")
    _git(d, "commit", "-qam", "B")
    cb = _git(d, "rev-parse", "HEAD")
    cl = BS.clone(d, tmp_path / "c")
    end, order = BS.plan(cl, [ca, cb], cb)
    rev = BS.revert_all(cl, end, order)
    assert not rev["dropped"]
    tar, how = BS.without_one(cl, end, rev["start"], order, ca)
    assert how == "start+others"
    assert _member(tar, "x.py") == b"x = 1\n" and _member(tar, "y.py") == b"y = 2\n"
    assert _member(tar, "README.md") == b"A\nB\n"
    # the same batch built twice has the same start (fixed commit dates)
    cl2 = BS.clone(d, tmp_path / "c2")
    assert BS.revert_all(cl2, end, order)["start"] == rev["start"]


TEST_C = "from pkg.c import k\n\n\ndef test_k():\n    assert k() == 3\n"


def test_a_new_test_file_that_does_not_collect_at_the_start_fails_only_its_own_nodes(tmp_path):
    """C adds pkg/c.py and tests/test_c.py: at the start test_c.py cannot import, but the other files still run
    (start_passed is not empty), and on the final tree a missing C fails C only."""
    src = tmp_path / "src"
    c = _small_repo(src)
    (src / "pkg/c.py").write_text("def k():\n    return 3\n", encoding="utf-8", newline="\n")
    (src / "tests/test_c.py").write_text(TEST_C, encoding="utf-8", newline="\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "C")
    c["C"] = _git(src, "rev-parse", "HEAD")
    tasks = _tasks(c) + [{"id": "C", "commit": c["C"], "tests": ["tests/test_c.py"], "brief": "add k"}]
    b = {"id": "t3", "tasks": ["A", "B", "C"], "overlap": [], "end": c["C"][:7], "note": "test"}
    mat = BT.build(b, tmp_path / "tmp", source=src, tasks=tasks)
    assert mat["problems"] == [], mat["problems"]
    assert set(mat["start_passed"]) == {"tests/test_a.py::test_f_old", "tests/test_b.py::test_g_old"}
    assert mat["collect_errors"]["start"] == ["tests/test_c.py"] and mat["collect_errors"]["end"] == []
    assert mat["nodes"]["C"] == ["tests/test_c.py::test_k"] and mat["coupled"] == {}
    repo = tmp_path / "repo"
    BT.make_repo(mat, repo)
    (repo / "pkg/a.py").write_text(A_OLD.replace("return 1", "return 2"), encoding="utf-8")
    (repo / "pkg/b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    s = BT.score_batch(repo, mat, tmp_path)
    assert s["right"] == 2 and not s["ok"] and not s["tasks_ok"]["C"]["ok"] and s["n_regressions"] == 0
    assert s["collect_errors"] == ["tests/test_c.py"]
    (repo / "pkg/a.py").write_text("def f():\n    return 9\n", encoding="utf-8")      # a regression still shows
    s2 = BT.score_batch(repo, mat, tmp_path)
    assert "tests/test_a.py::test_f_old" in s2["regressions"]


def test_a_cached_check_is_used_for_the_same_start_tree_and_check_code(small, monkeypatch):
    d, b, c = small["dir"], small["batch"], small["commits"]
    rep = BT.report(small["mat"])
    again = BT.build(b, d / "tmp2", source=d / "src", tasks=_tasks(c), cached=rep)
    assert again.get("from_cache") and again["start"] == small["mat"]["start"]
    assert again["nodes"] == small["mat"]["nodes"]
    stale = {**rep, "check_sha256": "0" * 16}                       # the selection code changed
    assert not BT.build(b, d / "tmp3", source=d / "src", tasks=_tasks(c), cached=stale, run_tests=False) \
        .get("from_cache")


def test_merge_conflicts_count_one_per_conflicted_file():
    out = ("Auto-merging a.py\nCONFLICT (content): Merge conflict in a.py\n"
           "Automatic merge failed; fix conflicts and then commit the result.\n")
    assert len(BT.CONFLICT.findall(out)) == 1


def test_cost_split_and_review_runs(tmp_path):
    by = {"claude-opus-x": 1.0, "claude-haiku-y": 0.25}
    s = BT.cost_split({"arm": "builtin"}, by, 1.25, 0.0)
    assert s["sub_usd"] == 0.25 and s["lead_only_usd"] == 1.0 and s["lead_worker_model_usd"] == 0.25
    h = BT.cost_split({"arm": "builtin", "lead_model": "haiku"}, {"claude-haiku-y": 0.5}, 0.5, 0.0)
    assert h["sub_usd"] is None and h["lead_only_usd"] is None and "worker" in h["cost_split"]
    x = BT.cost_split({"arm": "ccx-batch"}, by, 2.0, 0.75)
    assert x["sub_usd"] == 0.75 and x["lead_only_usd"] == 1.25 and x["lead_worker_model_usd"] == 0.25
    hub = tmp_path / "hub"
    (hub / "ccx").mkdir(parents=True)
    rows = [{"run_id": "20261027-1-aa", "label": "eval-batch:x"},
            {"run_id": "20261027-2-bb", "label": "review:20261027-1-aa"}, {"type": "verdict", "label": "review:z"}]
    (hub / "ccx" / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert BT.review_run_ids(hub) == {"20261027-2-bb"}


def _member(tar: bytes, name: str) -> bytes:
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        return tf.extractfile(name).read()


def test_leak_check_and_overlap():
    hidden = {"t.py": b"import pytest\n\n\n@pytest.mark.parametrize('x', [1, 2])\ndef test_x(x):\n    assert x\n"}
    same = BS.leaks({"A": ["t.py::test_x[1]"]}, hidden, dict(hidden))
    assert same and "word for word" in same[0]
    fewer = {"t.py": hidden["t.py"].replace(b"[1, 2]", b"[1]")}               # the start lacks a case: no leak
    assert BS.leaks({"A": ["t.py::test_x[1]"]}, hidden, fewer) == []
    ov = BS.overlap({"A": ["x.py", "README.md"], "B": ["x.py", "README.md"], "C": ["y.py"]})
    assert ov == [{"pair": ["A", "B"], "files": ["x.py"]}]


def test_parse_results_reads_the_short_summary():
    out = ("PASSED tests/t.py::test_a\nPASSED tests/t.py::test_p[a b]\nFAILED tests/t.py::test_b - assert 1 == 2\n"
           "ERROR tests/u.py - ImportError: x\nXFAIL tests/t.py::test_c - reason\n1 failed, 2 passed\n")
    r = BS.parse_results(out)
    assert r["passed"] == {"tests/t.py::test_a", "tests/t.py::test_p[a b]", "tests/t.py::test_c"}
    assert r["failed"] == {"tests/t.py::test_b"} and r["errors"] == {"tests/u.py"}


# ------------------------------------------------------------------ scoring the merged tree

def test_score_counts_each_change_and_regressions(small, tmp_path):
    mat = small["mat"]
    repo = tmp_path / "repo"
    BT.make_repo(mat, repo)
    assert _git(repo, "rev-list", "--count", "HEAD") == "1"                     # no history of the end
    s0 = BT.score_batch(repo, mat, tmp_path)
    assert s0["right"] == 0 and not s0["ok"] and s0["n_tasks"] == 2
    BT.make_repo(mat, repo)
    (repo / "pkg/a.py").write_text(A_OLD.replace("return 1", "return 2"), encoding="utf-8")
    s1 = BT.score_batch(repo, mat, tmp_path)
    assert s1["tasks_ok"]["A"]["ok"] and not s1["tasks_ok"]["B"]["ok"] and s1["right"] == 1 and not s1["ok"]
    (repo / "pkg/b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    s2 = BT.score_batch(repo, mat, tmp_path)
    assert s2["ok"] and s2["right"] == 2 and s2["n_regressions"] == 0 and s2["conflict_markers"] == 0
    (repo / "pkg/a.py").write_text("def f():\n    return 9\n", encoding="utf-8")   # breaks test_f_old too
    s3 = BT.score_batch(repo, mat, tmp_path)
    assert not s3["ok"] and "tests/test_a.py::test_f_old" in s3["regressions"]


def test_a_node_left_out_of_the_run_is_not_a_regression(small, tmp_path):
    mat = {**small["mat"], "deselect": ["tests/test_a.py::test_f_old"]}
    repo = tmp_path / "repo"
    BT.make_repo(mat, repo)
    (repo / "pkg/a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    (repo / "pkg/b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    s = BT.score_batch(repo, mat, tmp_path)
    assert s["ok"] and s["n_regressions"] == 0 and s["right"] == 2


def test_conflict_markers_left_in_the_tree_are_counted(small, tmp_path):
    repo = tmp_path / "repo"
    BT.make_repo(small["mat"], repo)
    (repo / "pkg/b.py").write_text("<<<<<<< HEAD\ndef g():\n=======\n>>>>>>> ccx/r1\n", encoding="utf-8")
    assert BT.markers(repo) == 2


# ------------------------------------------------------------------ the lead: argv, prompt, timeline

def _ev(t, obj):
    return (t, json.dumps(obj))


def test_timeline_counts_waits_idle_conflicts_and_quota():
    use = lambda i, name, inp: {"type": "assistant", "parent_tool_use_id": None,  # noqa: E731
                                "message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}}
    res = lambda i, text, parent=None: {"type": "user", "parent_tool_use_id": parent,  # noqa: E731
                                        "message": {"content": [{"type": "tool_result", "tool_use_id": i,
                                                                 "content": text}]}}
    lines = [_ev(1, use("a", "Agent", {"prompt": "x"})),
             _ev(5, res("s", "sub-agent noise CONFLICT (content): x", parent="a")),     # a sub-agent's: ignored
             _ev(11, res("a", "done")),
             _ev(12, use("b", "Bash", {"command": 'python "/r/ccx.py" show r1 r2 --any --wait'})),
             _ev(20, res("b", [{"type": "text", "text": "Auto-merging a.py\nCONFLICT (content): Merge conflict"}])),
             _ev(21, use("c", "Bash", {"command": 'python "/r/ccx.py" q run --bg'})),
             _ev(22, res("c", "started")),
             _ev(23, use("d", "Bash", {"command": "git merge ccx/r1 && git merge ccx/r2"})),
             _ev(24, {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}),
             _ev(25, res("d", "stopped: backpressure")),
             (26, "not json")]
    t = BT.timeline(lines, 40.0)
    assert t["lead_waits"] == 2 and t["lead_wakeups"] == 2
    assert t["lead_idle_s"] == 18.0 and t["lead_idle_ratio"] == 0.45
    assert t["merge_conflicts"] == 1 and t["merges"] == 2
    assert t["rate_limit_rejected"] == 1 and t["backpressure"] == 1


def test_what_counts_as_a_blocking_wait():
    bash = lambda c: BT.is_wait("Bash", {"command": c})  # noqa: E731
    assert bash('python "/r/ccx.py" run --tradeoff save --check "p" "brief"')
    assert not bash('python "/r/ccx.py" run --bg --worktree "brief"')
    assert bash('python "/r/ccx.py" batch /tmp/plan.json') and bash('python "/r/ccx.py" show r1 --wait')
    assert not bash('python "/r/ccx.py" q run --bg') and bash('python "/r/ccx.py" q run')
    assert not bash('python "/r/ccx.py" q add --plan /tmp/p.json') and not bash("git status")
    assert BT.is_wait("Agent", {}) and not BT.is_wait("Read", {"file_path": "x"})


def test_lead_argv_per_arm_and_lead_model():
    u = {"arm": "builtin"}
    argv = BT.lead_argv(u, 2)
    assert argv[argv.index("--model") + 1] == "opus" and "--agents" in argv and "Agent" in argv[argv.index("--tools") + 1]
    for arm in BT.CCX_ARMS:
        argv = BT.lead_argv({"arm": arm, "lead_model": "sonnet", "lead_effort": "low"}, 2)
        assert argv[argv.index("--model") + 1] == "sonnet" and argv[argv.index("--effort") + 1] == "low"
        assert "--no-session-persistence" not in argv and "--agents" not in argv     # ccx --context reads it
    assert "--no-session-persistence" in BT.lead_argv({"arm": "self"}, 2)
    old = {"tag": "t", "rep": 1, "batch": "b", "arm": "self"}
    assert BT.done_key(old) == BT.done_key({**old, "lead_model": "opus", "lead_effort": "medium"})
    other = {**old, "lead_model": "sonnet", "lead_effort": "medium"}
    assert BT.done_key(other) != BT.done_key(old) and BT.arm_of(other) == "self.sonnet-medium"
    assert BT.unit_key(other) == "1-b-self.sonnet-medium" and PF_WORK_ENTRY().match(BT.unit_key(other))
    assert PF_WORK_ENTRY().match("h-" + BT.unit_key(other))


def PF_WORK_ENTRY():
    return BT.PF.WORK_ENTRY


def test_arms_wording():
    pipe = BT.HOW["ccx-pipeline"]
    for s in ("q add --plan", "q run --bg", "--any --wait", "waiting", "unmerged", "q done <id> --ok 1",
              "backpressure", "deps", "verbatim", "do not ask the sub-agent to commit"):
        assert s in pipe, s
    bal = BT.HOW["balanced"]
    assert "--tradeoff balanced" in bal and "--worktree" in bal and "--any --wait" in bal and "yourself" in bal
    assert "batch <plan file>" in BT.HOW["ccx-batch"] and "worktree" in BT.HOW["ccx-batch"]
    assert "several Agent calls in one message" in BT.HOW["builtin"] and "yourself" in BT.HOW["self"]
    for arm in BT.ARMS:
        BT.HOW[arm].format(ccx="CCX", label="L")                                       # every placeholder filled


def test_lead_prompt_carries_every_brief():
    b = TB.by_id("ho5-overlap")
    mat = {"tasks": b["tasks"]}
    p = BT.lead_prompt({"arm": "ccx-pipeline", "label": "L"}, b, mat)
    for i, t in enumerate(b["tasks"]):
        assert f"## Change {'ABCDE'[i]}" in p and TB.task_by_id(t)["brief"] in p
    assert "relayline" in p and "A, B, C, D and E" in p and '{"tasks": [{"id": "A", "title"' in p
    assert "{ccx}" not in p and "{{" not in p and 'python "' in p
    hz = TB.by_id("hz4-overlap")
    p2 = BT.lead_prompt({"arm": "self", "label": "L"}, hz, {"tasks": hz["tasks"]})
    assert "humanize" in p2 and "PYTHONPATH=src" in p2 and "Change D" in p2 and "Change E" not in p2


def test_run_timed_stamps_lines(tmp_path):
    code = "import sys, time\nprint('one', flush=True)\ntime.sleep(0.3)\nprint(sys.stdin.read().strip())\n"
    out, _err, rc, lines = BT.run_timed([sys.executable, "-c", code], cwd=tmp_path, env=dict(os.environ),
                                        timeout=60, input="two\n")
    assert rc == 0 and out.splitlines() == ["one", "two"]
    assert lines[1][0] - lines[0][0] >= 0.25


def test_lead_unit_with_the_fake_lead(small, tmp_path, monkeypatch):
    mat, b = small["mat"], small["batch"]
    repo, hub, work = tmp_path / "repo", tmp_path / "hub", tmp_path / "work"
    work.mkdir()
    (hub / "ccx").mkdir(parents=True)
    BT.make_repo(mat, repo)
    env = {**os.environ, "FAKE_WRITE": f"{repo / 'pkg' / 'a.py'}=def f():\n    return 2\n"}
    monkeypatch.setattr(BT, "batch_tasks", lambda _b: _tasks(small["commits"]))
    monkeypatch.setattr(BT.TB, "task_by_id", lambda t: {x["id"]: x for x in _tasks(small["commits"])}[t])
    a = type("A", (), {"lead_budget": 1.0, "timeout": 120})()
    u = {"arm": "self", "label": "eval-batch:t:1:t:self", "rep": 1, "batch": "t"}
    row = BT.lead_unit(u, a, b, mat, work, repo, hub, env=env)
    assert row["rc"] == 0 and row["lead_usd"] == 0.0123 and row["sub_usd"] == 0 and row["usd"] == 0.0123
    assert row["lead_waits"] == 0 and row["quota_events"] == 0 and (work / "1-t-self.stream.jsonl").exists()
    assert row["delegated"] == 0 and row["ccx_ledger_rows"] == 0
    s = BT.score_batch(repo, mat, tmp_path)
    assert s["tasks_ok"]["A"]["ok"] and not s["tasks_ok"]["B"]["ok"]


# ------------------------------------------------------------------ dry run and summary

def test_dry_run_prints_the_plan_and_an_estimate(tmp_path, capsys):
    f = tmp_path / "r.jsonl"
    assert BT.main(["run", "--dry-run", "--reps", "1", "--out", str(f), "--workdir", str(tmp_path / "w")]) == 0
    out = capsys.readouterr().out
    n = len(TB.IDS) * len(BT.ARMS)
    assert f"units: {n}" in out and "estimate: $" in out and out.count("[dry] eval-batch:") == n
    assert "estimate by arm" in out and not (tmp_path / "w").exists()
    from common import append_jsonl
    append_jsonl(f, {"tag": "bt1", "rep": 1, "batch": TB.IDS[0], "arm": "self", "lead_model": "opus",
                     "lead_effort": "medium"})
    BT.main(["run", "--dry-run", "--reps", "1", "--out", str(f), "--workdir", str(tmp_path / "w")])
    assert f"units: {n - 1}" in capsys.readouterr().out                                # done units are skipped
    BT.main(["run", "--dry-run", "--reps", "1", "--out", str(f), "--lead-model", "sonnet", "--arms", "self",
             "--batches", TB.IDS[0], "--workdir", str(tmp_path / "w")])
    out = capsys.readouterr().out
    assert "units: 1" in out and ":self.sonnet-medium" in out


def test_unknown_arm_or_batch_is_refused(tmp_path):
    for flag, val in (("--arms", "nope"), ("--batches", "nope")):
        with pytest.raises(SystemExit):
            BT.main(["run", "--dry-run", flag, val, "--out", str(tmp_path / "r.jsonl")])


def test_schedule_is_seeded_and_complete():
    us = BT.schedule(2, 71, TB.IDS, list(BT.ARMS))
    assert len(us) == 2 * len(TB.IDS) * len(BT.ARMS) and us == BT.schedule(2, 71, TB.IDS, list(BT.ARMS))
    assert {(u["rep"], u["batch"], u["arm"]) for u in us} == \
        {(r, b, a) for r in (1, 2) for b in TB.IDS for a in BT.ARMS}


def _row(rep, arm, right, ok, usd, wall, **kw):
    return {"tag": "t", "rep": rep, "batch": "ho5-overlap", "arm": arm, "right": right, "n_tasks": 5, "ok": ok,
            "usd": usd, "wall_s": wall, "lead_only_usd": usd / 2, "sub_usd": usd / 2, "lead_wakeups": 3,
            "lead_turns": 9, "lead_tokens": 100, "lead_idle_ratio": 0.5, "merge_conflicts": 1, "quota_events": 0,
            "tasks_ok": {"x": {"ok": right == 5}}, **kw}


def test_summary_pairs_arms_on_the_same_batch_repeats():
    rows = [_row(1, "self", 5, True, 1.0, 500), _row(2, "self", 4, False, 1.1, 520),
            _row(1, "ccx-pipeline", 5, True, 0.7, 900), _row(2, "ccx-pipeline", 5, True, 0.6, 1000),
            _row(3, "ccx-pipeline", 5, True, 0.6, 1000), {"tag": "t", "rep": 1, "batch": "x", "arm": "self",
                                                           "error": "boom"}]
    s = BT.summarize(rows)
    c = s["cells"]["t"]["ho5-overlap"]
    assert c["self"]["n"] == 2 and c["self"]["wall_med"] == 520 and c["self"]["wall_p90"] == 520
    assert c["self"]["all_right"] == 1 and c["self"]["tasks_right"] == {"x": "1/2"}
    assert c["ccx-pipeline"]["n"] == 3 and c["ccx-pipeline"]["merge_conflicts"] == 3
    p = s["paired"]["self vs ccx-pipeline"]
    assert p["all"]["n"] == 2 and p["all"]["ccx-pipeline_faster"] == 0 and p["all"]["ccx-pipeline_cheaper"] == 2
    assert p["all"]["ccx-pipeline_more_right"] == 1 and "no CI" in p["note"] and s["error_rows"] == 1
    assert p["by_batch"]["ho5-overlap"]["n"] == 2
