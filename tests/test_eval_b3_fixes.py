"""The six eval-harness fixes found while checking the B3 result (scripts/eval/r5.py only; the rules are unchanged)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import pytest  # noqa: E402
import r5  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _row(arm, rd, task, ok, prompt, clean=True):
    return {"tag": "b3", "round": rd, "task": task, "arm": arm, "ok": ok, "env_clean": clean,
            "sub_usage": {"prompt": prompt}, "daily": {"sha256": "s1"}}


def _pairs(n, arm="ccx2daily_nomem", clean=lambda i: True):
    rows = []
    for i in range(n):
        rows += [_row("ccx2daily", 1, f"t{i}", True, 100, clean(i)), _row(arm, 1, f"t{i}", True, 50, clean(i))]
    return rows


# 1. --include-unclean says neither rule counts unclean rows

def test_include_unclean_help_says_the_rules_take_clean_rows_only(capsys):
    with pytest.raises(SystemExit):
        r5.main(["summary", "-h"])
    out = " ".join(capsys.readouterr().out.split())
    assert "tier rule and the B3 rule still take clean rows only" in out
    note = r5.excluded_line({"excluded_rows": {"unclean": 2}})
    assert "tier and B3 rules never do" in note


# 2. pairs left out on both sides alike are said; a B3 rule on fewer pairs than registered is said loudly

def test_an_even_loss_of_pairs_is_said_too():
    rows = _pairs(50, clean=lambda i: i < 30)                   # 20 pairs unclean on both sides: an even loss
    lp = r5.lost_pairs(rows, "ccx2daily", "ccx2daily_nomem")
    assert lp["lost"] == 20 and lp["of"] == 50 and "note" not in lp
    assert lp["left_out"].startswith("20 of 50 shared pairs left out") and "counted on 30 pairs only" in lp["left_out"]
    assert "left_out" not in r5.lost_pairs(_pairs(5), "ccx2daily", "ccx2daily_nomem")


def test_a_b3_rule_on_fewer_pairs_than_registered_says_so_and_keeps_its_result():
    rows = _pairs(50, clean=lambda i: i < 30)
    br = r5.b3_rule(rows, "ccx2daily_nomem")
    assert br["units"] == 30 and br["result"] == "pass"         # report-only: the result is the conditions'
    assert br["registered"] == {"pairs": 50, "counted": 30, "note": br["registered"]["note"]}
    lines = r5.b3_rule_lines("ccx2daily vs ccx2daily_nomem", br)
    assert lines[0].startswith("!! b3 rule") and "registered 50 pairs, counted 30" in lines[0]
    assert any("20 of 50 shared pairs left out" in ln for ln in lines)
    full = r5.b3_rule(_pairs(50), "ccx2daily_nomem")
    assert "registered" not in full and not r5.b3_rule_lines("x", full)[0].startswith("!!")


def test_the_tier_rule_lines_say_an_even_loss():
    tr = {"units": 3, "result": "unknown", "conditions": {}, "lost_pairs": {"left_out": "2 of 5 shared pairs left "
                                                                                         "out (...)"}}
    assert any("2 of 5 shared pairs left out" in ln for ln in r5.tier_rule_lines(tr))


# 3. the B3 plan no longer reads as two thresholds

@pytest.mark.parametrize("name, words", [("2026-10-30-b3-lean-switches-plan.md", "was not a second threshold"),
                                         ("2026-10-30-b3-lean-switches-plan.zh.md", "不是第二个门槛")])
def test_the_b3_plan_says_the_edge_is_not_a_second_threshold(name, words):
    assert words in (ROOT / "docs" / "research" / name).read_text(encoding="utf-8")


# 4. each run keeps its evidence in a folder of its own

def test_each_run_gets_its_own_artifacts_folder(tmp_path):
    out = tmp_path / "pg1-results.jsonl"
    run, d = r5.run_artifacts_dir(out, stamp="20261031-040000")
    assert run == "20261031-040000" and d == tmp_path / "pg1-results-artifacts" / run
    d.mkdir(parents=True)                                       # an aborted run left its folder there
    run2, d2 = r5.run_artifacts_dir(out, stamp="20261031-040000")
    assert run2 == "20261031-040000-2" and d2 != d and d2.parent == d.parent
    run3, _ = r5.run_artifacts_dir(out)
    assert len(run3) == 15 and run3[8] == "-"                   # the start time, to the second


# 5. the sub-agents' requests per unit

def _ledger(tmp_path, rows):
    hub = tmp_path / "hub"
    led = hub / "ccx" / "ledger.jsonl"
    led.parent.mkdir(parents=True)
    led.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return hub


def test_sub_usage_sums_the_requests_the_ledger_records(tmp_path):
    hub = _ledger(tmp_path, [
        {"run_id": "r1", "label": "eval:x", "usage": {"input": 1}, "requests": 5},
        {"run_id": "r2", "label": "eval:x", "usage": {"input": 1}, "requests": 3},
        {"run_id": "r3", "label": "eval:x", "usage": {"input": 1}},                       # an older row: not said
        {"run_id": "r4", "label": "review:r1", "usage": {"input": 1}, "requests": 2},
        {"run_id": "r5", "label": "eval:x", "usage": {"input": 1}, "requests": "7"},      # not a count: left out
        {"type": "verdict", "run_id": "r1", "requests": 99}])
    got = r5.sub_usage(hub)
    assert got["runs"] == 4 and got["requests"] == 8 and got["requests_runs"] == 2
    assert got["review_requests"] == 2 and got["review_requests_runs"] == 1


def test_sub_usage_requests_are_none_when_no_row_says(tmp_path):
    got = r5.sub_usage(_ledger(tmp_path, [{"run_id": "r1", "label": "eval:x", "usage": {"input": 1}}]))
    assert got["requests"] is None and got["requests_runs"] == 0 and got["review_requests"] is None


# 6. --wait-quiet waits for a quiet machine instead of forcing past a busy one

class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_wait_quiet_returns_once_the_machine_is_quiet(capsys):
    c = Clock()
    seen = iter([["pid 1 python: pytest"], ["pid 1 python: pytest"], []])
    assert r5.wait_quiet(10, sleep=c.sleep, now=c.now, busy=lambda: next(seen)) is True
    assert c.t == 2 * r5.QUIET_POLL_S
    out = capsys.readouterr().out
    assert "waiting up to 10 min" in out and "quiet: starting" in out


def test_wait_quiet_gives_up_after_its_minutes(capsys):
    c = Clock()
    assert r5.wait_quiet(1.5, sleep=c.sleep, now=c.now, busy=lambda: ["pid 1 python: pytest"]) is False
    assert c.t == 90 and "still busy after 1.5 min" in capsys.readouterr().out


def test_wait_quiet_does_not_wait_on_a_quiet_machine():
    c = Clock()
    assert r5.wait_quiet(10, sleep=c.sleep, now=c.now, busy=lambda: []) is True and c.t == 0


def test_run_waits_before_the_checks_and_still_refuses_a_busy_machine(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(r5, "wait_quiet", lambda m: calls.append(("wait", m)) or False)

    def checks(o):
        calls.append(("checks",))
        return {"ok": False, "problems": ["busy: pid 1 python: pytest"]}
    monkeypatch.setattr(r5.PF, "run_checks", checks)
    rc = r5.main(["run", "--rounds", "1", "--tasks", r5.IDS[0], "--arms", "self", "--wait-quiet", "5",
                  "--out", str(tmp_path / "r.jsonl"), "--workdir", str(tmp_path / "w"), "--no-canary"])
    assert rc == 3 and calls == [("wait", 5.0), ("checks",)]
    assert "preflight failed: not starting" in capsys.readouterr().out
    assert not (tmp_path / "r-artifacts").exists()
