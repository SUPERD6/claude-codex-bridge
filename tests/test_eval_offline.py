"""Offline experiments C1-C6 (scripts/eval/c*_*.py, offline_common.py): fake repositories, hubs, streams and event
logs; no real CLI, no model call."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import c1_namecheck_scan as C1  # noqa: E402
import c2_lead_accept as C2  # noqa: E402
import c3_check_reuse as C3  # noqa: E402
import c4_must_filter as C4  # noqa: E402
import c5_diff_read as C5  # noqa: E402
import c6_reuse_rule as C6  # noqa: E402
import offline_common as oc  # noqa: E402


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def repo(d: Path, files: dict) -> Path:
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@example.invalid")
    git(d, "config", "user.name", "t")
    for n, t in files.items():
        (d / n).write_text(t, encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "start")
    return d


def jsonl(f: Path, rows: list) -> Path:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return f


# ------------------------------------------------------------------ shared helpers

def test_fisher_and_median():
    assert oc.fisher_exact(5, 0, 0, 5) < 0.01
    assert oc.fisher_exact(3, 3, 3, 3) == 1.0
    assert oc.median([3, None, 1, 2]) == 2 and oc.median([]) is None


def test_unit_key_and_lead_tool_calls(tmp_path):
    assert oc.unit_key("r5e", "2-quota-stop-log-ccx2") == "eval-r5:r5e:2:quota-stop-log:ccx2"
    s = jsonl(tmp_path / "s.jsonl", [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "a", "name": "Bash",
                                                       "input": {"command": "git diff"}}]}},
        {"type": "assistant", "parent_tool_use_id": "x",
         "message": {"content": [{"type": "tool_use", "id": "b", "name": "Read", "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": "d",
                                                  "is_error": True}]}}])
    calls = oc.lead_tool_calls(s)
    assert [c["name"] for c in calls] == ["Bash"] and calls[0]["error"] and calls[0]["result"] == "d"


# ------------------------------------------------------------------ C1

SWALLOW = "def f():\n    try:\n        g(nope)\n    except Exception:\n        pass\n    other()\n"


def test_c1_swallow_ranges():
    r = C1.swallow_ranges(SWALLOW)
    assert C1.in_swallow(r, 3) and not C1.in_swallow(r, 6)
    reraise = "try:\n    x()\nexcept Exception:\n    raise\n"
    narrow = "try:\n    x()\nexcept OSError:\n    pass\n"
    assert C1.swallow_ranges(reraise) == [] and C1.swallow_ranges(narrow) == []
    assert C1.swallow_ranges("try:\n    x()\nexcept:\n    pass\n") == [(2, 2)]


def test_c1_changed_lines():
    d = "+++ b/a.py\n@@ -1,0 +2,3 @@\n+x\n+++ /dev/null\n@@ -4 +0,0 @@\n+++ b/b.py\n@@ -5 +7 @@\n"
    assert C1.changed_lines(d) == {"a.py": {2, 3, 4}, "b.py": {7}}


def test_c1_scan_changes_marks_swallowed_hits(tmp_path):
    r = repo(tmp_path / "u", {"m.py": "def other():\n    return 1\n"})
    (r / "m.py").write_text("def other():\n    return 1\n\n\n" + SWALLOW.replace("g(nope)", "other(nope)"),
                            encoding="utf-8")
    (r / "new.py").write_text("def h():\n    return missing\n", encoding="utf-8")
    out = C1.scan_changes(r)
    hits = {h["name"]: h for h in out["hits"]}
    assert hits["nope"]["swallowed"] and not hits["missing"]["swallowed"]
    assert out["files"] == 2


def test_c1_labels_and_tally():
    labels = {"r5x/1-t-ccx2:m.py:nope": ("true", "why")}
    h = {"file": "m.py", "name": "nope"}
    assert C1.label("r5x/1-t-ccx2", h, labels) == ("true", "why")
    assert C1.label("whole", {"file": "r5x/1-t-ccx2/m.py", "name": "nope"}, labels)[0] == "true"
    assert C1.label("whole", {"file": "x.py", "name": "y"}, labels)[0] == "unlabelled"
    t = C1.tally([{"label": "true", "swallowed": True}, {"label": "false", "swallowed": False}])
    assert t == {"hits": 2, "true": 1, "true_swallowed": 1, "false": 1, "false_swallowed": 0, "unlabelled": 0,
                 "unlabelled_swallowed": 0}


def test_c1_main_on_fake_round(tmp_path, capsys):
    r = repo(tmp_path / "r5c" / "1-t-ccx2", {"m.py": "x = 1\n"})
    (r / "m.py").write_text("x = 1\n\n\ndef f():\n    return y\n", encoding="utf-8")
    rep = C1.main(["--records", str(tmp_path), "--tags", "r5c", "--json", str(tmp_path / "o.json")])
    assert rep["units"] == 1 and rep["totals"]["changes"]["hits"] == 1
    assert rep["totals"]["whole"]["unlabelled"] == 1
    assert json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))["totals"]


# ------------------------------------------------------------------ C3

def codex_log(f: Path, events: list) -> Path:
    return jsonl(f, [{"type": "item.completed", "item": e} for e in events])


def test_c3_classify_codex_log(tmp_path):
    cmd = "python -m pytest -q tests/test_a.py"
    log = codex_log(tmp_path / "e.log", [
        {"type": "command_execution", "command": f"powershell -Command '{cmd}'", "exit_code": 1},
        {"type": "file_change", "changes": [{"path": "a.py"}]},
        {"type": "command_execution", "command": f'powershell -Command "{cmd}"', "exit_code": 0}])
    assert C3.classify(cmd, *C3.builder_commands(log)) == "exact_pass"
    log2 = codex_log(tmp_path / "f.log", [
        {"type": "command_execution", "command": cmd, "exit_code": 0},
        {"type": "file_change", "changes": []},
        {"type": "command_execution", "command": "python -m pytest -q", "exit_code": 0}])
    assert C3.classify(cmd, *C3.builder_commands(log2)) == "other_pass"
    assert C3.classify(cmd, [], -1) == "none"


def test_c3_classify_claude_stream(tmp_path):
    log = jsonl(tmp_path / "c.log", [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "w", "name": "Edit", "input": {}}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "b", "name": "Bash",
                                                       "input": {"command": "pytest -q t.py"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "b", "is_error": True}]}}])
    assert C3.classify("pytest -q t.py", *C3.builder_commands(log)) == "exact_fail"


def test_c3_run_rows_and_summary(tmp_path):
    cmd = "pytest -q t.py"
    for i, (passed, review, code) in enumerate([(True, False, 0), (False, False, 0), (True, True, 1)]):
        d = tmp_path / "r5g" / f"h-{i}-t-ccx2" / "ccx" / "runs" / f"run{i}"
        d.mkdir(parents=True)
        (d / "run.json").write_text(json.dumps({
            "run_id": f"run{i}", "caller": "claude", "mode": "write",
            "check": {"cmd": cmd, "passed": passed, "seconds": 10.0 + i},
            "review": {"run_id": "rv", "verdict": "pass"} if review else None}), encoding="utf-8")
        codex_log(d / "events.0.log", [{"type": "file_change"},
                                       {"type": "command_execution", "command": cmd, "exit_code": code}])
    rv = tmp_path / "r5g" / "h-0-t-ccx2" / "ccx" / "runs" / "rv"
    rv.mkdir(parents=True)
    (rv / "run.json").write_text(json.dumps({"run_id": "rv", "caller": "ccx-review", "mode": "read"}), "utf-8")
    rows = C3.run_rows(tmp_path, ["r5g"])
    s = C3.summarize(rows)
    assert s["runs"] == 3 and s["match"] == 1 and s["mismatch"] == 2
    assert s["builder"]["exact_pass"] == 2 and s["builder"]["exact_fail"] == 1
    assert s["check_seconds_no_review"]["n"] == 2 and s["saveable_no_review"]["sum"] == 10.0


# ------------------------------------------------------------------ C5

def test_c5_diff_commands():
    assert C5.diff_commands("git diff")
    assert C5.diff_commands("cd x && git -C repo show HEAD")
    assert not C5.diff_commands("git diff --stat")
    assert C5.diff_commands("git diff --stat; git diff a.py")
    assert C5.diff_commands("git log --oneline -p -3")
    assert not C5.diff_commands("git status")


def test_c5_lead_reads():
    def call(i, name, **inp):
        return {"i": i, "name": name, "input": inp}
    before = [call(0, "Bash", command="git diff")]
    run = call(1, "Bash", command='python ccx.py run --check "pytest" "do it"')
    assert C5.lead_reads(before, set()) == {"delegated": False, "diff": False, "file": False}
    assert C5.lead_reads(before + [run], set())["diff"] is False          # only calls after delegating count
    r = C5.lead_reads([run, call(2, "Read", file_path="C:/x/ccx/a.py")], {"ccx/a.py"})
    assert r == {"delegated": True, "diff": False, "file": True}
    assert C5.lead_reads([call(0, "Agent"), call(1, "Bash", command="git show")], set())["diff"]


def test_c5_unit_rows_and_table(tmp_path):
    rows = []
    for unit, ok, cmd in (("1-t-ccx2", True, "git diff"), ("2-t-ccx2", True, "ls"), ("1-u-ccx2", False, "ls")):
        repo(tmp_path / "r5e" / unit, {"a.py": "x = 1\n"})
        jsonl(tmp_path / "r5e" / f"{unit}.stream.jsonl", [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "python ccx.py run x"}},
            {"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": cmd}}]}}])
        lab = oc.unit_key("r5e", unit)
        rows.append({"tag": "r5e", "label": lab, "arm": "ccx2", "ok": ok})
    res = jsonl(tmp_path / "results.jsonl", rows)
    out = C5.main(["--records", str(tmp_path), "--results", str(res), "--tags", "r5e"])
    t = out["table"]["ccx2"]
    assert (t["right"], t["wrong"], t["no_read_strict_right"], t["no_read_strict_wrong"]) == (2, 1, 1, 1)
    assert 0 < t["p_strict"] <= 1


# ------------------------------------------------------------------ C4

def test_c4_brief_decisions_and_gate(tmp_path):
    prompt = "## The task it was given\nT\n\n## Checks\nok\n\n## Answer\nold rules"
    b = C4.filter_brief(prompt, ["[must] a.py:1 bad"])
    assert "old rules" not in b and "1. [must] a.py:1 bad" in b and b.startswith("## The task")
    assert C4.decisions(["[keep] a", "2. [DROP] b", "noise"]) == ["keep", "drop"]
    g = C4.gate([{"outcome": "fail->pass", "items": ["[keep] x"]},
                 {"outcome": "pass->pass", "items": ["[drop] y", "[drop] z"]},
                 {"outcome": "pass->pass", "items": ["[keep] y"]},
                 {"outcome": "fail->fail", "items": []}])
    assert g == {"rescues": 1, "rescues_kept": 1, "wasted": 2, "wasted_dropped": 1, "unparsed": 1,
                 "passes_gate": True}
    assert not C4.gate([{"outcome": "fail->pass", "items": ["[drop] x"]}])["passes_gate"]


def test_c4_plan_dry_run(tmp_path):
    hub = tmp_path / "h-1-t-ccx2"
    for rid, rec in (("b", {"run_id": "b", "review": {"run_id": "rv", "verdict": "issues"}}),
                     ("rv", {"run_id": "rv", "caller": "ccx-review"})):
        d = hub / "ccx" / "runs" / rid
        d.mkdir(parents=True)
        (d / "run.json").write_text(json.dumps(rec), encoding="utf-8")
    (hub / "ccx" / "runs" / "rv" / "prompt.md").write_text("## The task it was given\nT\n\n## Answer\nx", "utf-8")
    rows = {"rows": [{"hub": str(hub), "run": "b", "issues": ["[must] a", "[note] b"], "outcome": "pass->pass"},
                     {"hub": str(hub), "run": "b", "issues": ["[must] a"], "outcome": None}]}
    f = tmp_path / "rows.json"
    f.write_text(json.dumps(rows), encoding="utf-8")
    out = C4.main(["--rows", str(f), "--dry-run"])
    assert out["rounds"] == 1 and out["by_outcome"] == {"pass->pass": 1} and out["est_usd"] > 0


# ------------------------------------------------------------------ C2

def test_c2_plan_and_score(tmp_path):
    rows = []
    for unit, ok in (("1-t-ccx2", True), ("2-t-ccx2", False), ("1-u-ccx2", True), ("1-t-direct", False)):
        repo(tmp_path / "r5h" / unit, {"a.py": "x = 1\n"})
        m = oc.UNIT.match(unit)
        rows.append({"tag": "r5h", "label": oc.unit_key("r5h", unit), "arm": m["arm"], "task": m["task"], "ok": ok})
    res = jsonl(tmp_path / "results.jsonl", rows)
    us = C2.units(tmp_path, oc.results(res, ["r5h"]), "ccx2", ["r5h"])
    p = C2.plan(us, "sonnet")
    assert (p["units"], p["wrong_units"], p["tasks_with_wrong_units"], p["tasks"]) == (3, 1, ["t"], ["t", "u"])
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "accept_t.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    s = C2.score(us, tests, runner=lambda f, tree: {"passed": "1-t" in tree.name})
    assert (s["scored"], s["wrong"], s["caught"], s["right"], s["false_alarms"]) == (2, 1, 1, 1, 0)
    assert not s["passes_gate"]


def test_c2_run_accept_outside_repo(tmp_path):
    tree = repo(tmp_path / "tree", {"mod_c2.py": "def f():\n    return 2\n"})
    t = tmp_path / "accept_x.py"
    t.write_text("import os, mod_c2\n\ndef test_f():\n    assert mod_c2.f() == 2\n"
                 "    assert os.environ['CCX_REPO'] and os.getcwd() != os.environ['CCX_REPO']\n", encoding="utf-8")
    assert C2.run_accept(t, tree)["passed"]


# ------------------------------------------------------------------ C6

def test_c6_matcher_and_score():
    assert C6.found("[must] ccx/quota.py:30 - QUOTA_HINTS is redefined; ccx/runners.py:15 already has one")
    assert not C6.found("[must] ccx/quota.py:42 - ev.get on a non-dict")
    s = C6.score([{"variant": "rule", "ok": True, "musts": ["[must] QUOTA_HINTS duplicates runners"],
                   "items": ["[must] QUOTA_HINTS duplicates runners"], "usd": 0.01},
                  {"variant": "base", "ok": True, "musts": [], "items": ["[note] QUOTA_HINTS vs runners.py"],
                   "usd": 0.02}])
    assert s == {"base": {"n": 1, "must": 0, "any": 1, "usd": 0.02}, "rule": {"n": 1, "must": 1, "any": 1, "usd": 0.01}}
    assert C6.ANCHOR in (Path(__file__).resolve().parents[1] / "ccx" / "review.py").read_text(encoding="utf-8")


def test_c6_dry_run_spends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("CCX_REPLAY_RECORDS", str(tmp_path))
    out = C6.main(["--dry-run", "--reps", "2"])
    assert out["reviews"] == 4 and out["exists"] is False and out["est_usd"] <= 0.5
