"""Round-5 evaluation script: task list and scheduling only (no git history, no real CLI)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import r5  # noqa: E402
import tasks_r5  # noqa: E402


def test_tasks_are_complete():
    assert len(tasks_r5.IDS) == len(set(tasks_r5.IDS)) == 10
    for t in tasks_r5.T:
        assert t["brief"] and t["tests"] and len(t["commit"]) >= 7
        assert all(x.startswith("tests/") and x.endswith(".py") for x in t["tests"])


def test_schedule_covers_every_task_arm_round():
    us = r5.schedule(2, 53, tasks_r5.IDS, list(r5.ARMS))
    assert len(us) == 2 * 10 * len(r5.ARMS)
    assert us == r5.schedule(2, 53, tasks_r5.IDS, list(r5.ARMS))


def test_ccx2_is_opt_in():
    assert "ccx2" not in r5.ARMS and "ccx2" in r5.OPT_IN_ARMS
    us = r5.schedule(1, 53, tasks_r5.IDS[:2], ["ccx", "ccx2"])
    assert sorted(u["arm"] for u in us) == ["ccx", "ccx", "ccx2", "ccx2"]


def test_ccx2_lead_instruction_follows_the_skill():
    old, new = r5.lead_how("ccx", "L"), r5.lead_how("ccx2", "L")
    assert "--review on" in old and old == r5.HOW_CCX.format(ccx=r5.r3.CCX_CMD, label="L")   # old arm unchanged
    assert "--review" not in new and "--bg" in new and "show <run_id> --wait" in new
    assert "verbatim" in new and "do not ask the sub-agent to commit" in new and "tail" in new


def test_unknown_arm_is_refused(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        r5.main(["run", "--arms", "nope", "--out", str(tmp_path / "r.jsonl"), "--workdir", str(tmp_path), "--dry-run"])


def test_summary_of_rows():
    rows = [{"task": "a", "round": 1, "arm": arm, "ok": arm != "self", "usd": usd, "lead_only_usd": usd,
             "lead_tokens": 10, "lead_requests": 3, "wall_s": 5}
            for arm, usd in (("self", 0.3), ("builtin", 0.3), ("ccx", 0.2), ("direct", 0.04), ("ccx2", 0.1))]
    s = r5.summarize(rows)
    assert s["arms"]["self"]["cps"] is None and s["arms"]["direct"]["cps"] == 0.04
    assert s["arms"]["ccx2"]["cps"] == 0.1 and s["arms"]["ccx2"]["n"] == 1


def test_builtin2_is_builtin_with_ccx2_acceptance():
    assert "builtin2" not in r5.ARMS and "builtin2" in r5.OPT_IN_ARMS
    b2, c2, b1 = r5.lead_how("builtin2", "L"), r5.lead_how("ccx2", "L"), r5.lead_how("builtin", "L")
    assert b1 == r5.r3.HOW["builtin"]                                                    # old arm unchanged
    assert "Agent tool" in b2 and "`worker`" in b2 and "ccx" not in b2
    assert "run the tests" not in b2 and "read the diff" not in b2                       # builtin's re-check is gone
    assert "accept it without re-running the tests or reading the full diff" in b2
    assert r5.LEAN_BRIEF in b2 and r5.LEAN_BRIEF in c2                                   # shared, not copied
    head, tail = r5.LEAN_ACCEPT.split("{send_back}")
    assert head in b2 and tail in b2 and head in c2 and tail in c2
    assert r5.lead_flags_arm("builtin2") == "builtin" and r5.lead_flags_arm("ccx2") == "ccx"
    us = r5.schedule(1, 53, tasks_r5.IDS[:2], ["ccx2", "builtin2"])
    assert sorted(u["arm"] for u in us) == ["builtin2", "builtin2", "ccx2", "ccx2"]
    s = r5.summarize([{"task": "a", "round": 1, "arm": "builtin2", "ok": True, "usd": 0.2, "lead_only_usd": 0.1,
                       "lead_tokens": 1, "lead_requests": 1, "wall_s": 1}])
    assert s["arms"]["builtin2"]["n"] == 1
