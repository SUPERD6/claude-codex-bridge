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


# ------------------------------------------------------------------ confirmation-run additions (fake rows only)

def _row(task, rd, arm, ok, usd, wall, **kw):
    return {"tag": "t", "round": rd, "task": task, "arm": arm, "ok": ok, "usd": usd, "wall_s": wall,
            "lead_only_usd": usd, "lead_tokens": 1, "lead_requests": 1, **kw}


def test_builtin2r_worker_carries_ccx_rules_word_for_word():
    from ccx import prompts
    assert "builtin2r" in r5.OPT_IN_ARMS and "builtin2r" not in r5.ARMS
    assert "builtin2r" in r5.BUILTIN_ARMS and "builtin2r" not in r5.PF.CODEX_ARMS
    assert r5.lead_how("builtin2r", "L") == r5.lead_how("builtin2", "L")       # the lead is told the same
    assert r5.lead_flags_arm("builtin2r") == "builtin"
    w = r5.WORKER_RULES["worker"]
    assert prompts.KEEP_TESTS in w["prompt"] and prompts.WIRING.strip() in w["prompt"]
    assert w["prompt"].startswith(r5.r3.WORKER["worker"]["prompt"]) and w["model"] == r5.r3.WORKER_MODEL
    import json
    a2r = r5.r3.lead_argv("builtin", 1, agents=r5.worker_agents("builtin2r"))
    a2 = r5.r3.lead_argv("builtin", 1, agents=r5.worker_agents("builtin2"))
    assert json.loads(a2r[a2r.index("--agents") + 1]) == r5.WORKER_RULES
    assert json.loads(a2[a2.index("--agents") + 1]) == r5.r3.WORKER                 # builtin2 unchanged
    assert r5.unit_models({"arm": "builtin2r"}, {})["worker_rules"]
    assert "worker_rules" not in r5.unit_models({"arm": "builtin2"}, {})


def test_lead_model_defaults_and_keys():
    argv = r5.r3.lead_argv("ccx", 1)
    assert argv[argv.index("--model") + 1] == "sonnet" and argv[argv.index("--effort") + 1] == "medium"
    argv = r5.r3.lead_argv("ccx", 1, "opus", "high")
    assert argv[argv.index("--model") + 1] == "opus" and argv[argv.index("--effort") + 1] == "high"
    old = {"tag": "r5", "round": 1, "task": "x", "arm": "ccx"}                        # a row from before the flag
    new = {**old, "lead_model": "sonnet", "lead_effort": "medium"}
    other = {**old, "lead_model": "opus", "lead_effort": "high"}
    assert r5.done_key(old) == r5.done_key(new) != r5.done_key(other)
    assert r5.arm_of(old) == r5.arm_of(new) == "ccx" and r5.arm_of(other) == "ccx@opus-high"
    assert r5.unit_key(old) == "1-x-ccx" and r5.unit_key(other) == "1-x-ccx@opus-high"
    assert r5.unit_models(other, {})["lead"] == "opus" and r5.unit_models(old, {})["lead_effort"] == "medium"
    s = r5.summarize([_row("a", 1, "ccx", True, 0.1, 10), _row("a", 1, "ccx", False, 0.5, 20, lead_model="opus")])
    assert s["arms"]["ccx"]["n"] == 1 and s["arms"]["ccx@opus-medium"]["n"] == 1   # never pooled
    assert "ccx vs ccx@opus-medium" in s["paired"]


def test_paired_comparison_mcnemar_holm_wilson_rounds():
    rows = []
    for i, t in enumerate("abcdef"):
        for rd in (1, 2):
            rows.append(_row(t, rd, "save", i < 2, 0.10, 100 + i))
            rows.append(_row(t, rd, "balanced", True, 0.12, 50 + i))
            rows.append(_row(t, rd, "self", i < 5, 0.30, 40))
    rows.append(_row("a", 3, "save", True, 0.1, 1))            # no partner: not paired
    s = r5.summarize(rows)
    p = s["paired"]["balanced vs save"]
    assert p["units"] == 12 and p["discordant"] == {"only_balanced": 8, "only_save": 0}
    assert p["mcnemar_p"] == r5.S.mcnemar_p(8, 0)
    assert set(s["paired"]) == {"self vs balanced", "self vs save", "balanced vs save"}
    adj = r5.S.holm({k: v["mcnemar_p"] for k, v in s["paired"].items()})
    assert all(v["mcnemar_p_holm"] == adj[k][1] for k, v in s["paired"].items())
    assert p["diff_is"] == "save - balanced" and p["wall_med_diff"] > 0
    assert p["wall_med_diff_ci"][0] <= p["wall_med_diff"] <= p["wall_med_diff_ci"][1]
    lo, hi = p["cps_diff_ci"]
    assert lo <= p["cps_diff"] <= hi
    assert s["arms"]["save"]["wilson"] == r5.S.wilson(5, 13)
    assert s["arms"]["save"]["ok_by_round"] == {"1": 2, "2": 2, "3": 1}


def test_task_bootstrap_needs_two_tasks():
    ps = [(_row("a", 1, "x", True, 1, 1), _row("a", 1, "y", True, 2, 2))]
    assert r5.task_boot(ps, r5.cps_diff) is None and r5.cps_diff(ps) == 1.0
    assert r5.cps_diff([(_row("a", 1, "x", False, 1, 1), _row("a", 1, "y", True, 2, 2))]) is None


def test_tier_rule_pass_and_fail():
    ok = [r for t in "ab" for r in (_row(t, 1, "save", True, 0.10, 100), _row(t, 1, "balanced", True, 0.14, 60))]
    tr = r5.summarize(ok)["tier_rule"]
    assert tr["result"] == "pass" and all(c["result"] == "pass" for c in tr["conditions"].values())
    bad = [r for t in "ab" for r in (_row(t, 1, "save", True, 0.10, 100), _row(t, 1, "balanced", t == "a", 0.2, 61))]
    c = r5.tier_rule(bad)["conditions"]
    assert c["right"]["result"] == c["wall"]["result"] == c["cps"]["result"] == "fail"
    none = [_row("a", 1, "save", False, 0.1, 100), _row("a", 1, "balanced", True, 0.1, 10)]
    assert r5.tier_rule(none)["conditions"]["cps"]["result"] == "n/a" and r5.tier_rule(none)["result"] == "fail"
    lines = r5.tier_rule_lines(r5.tier_rule(ok))
    assert lines[0].startswith("tier rule (2 shared units): pass") and len(lines) == 4
    assert "tier_rule" not in r5.summarize([_row("a", 1, "save", True, 0.1, 1)])


def _rec(hub, rid, **kw):
    import json
    d = hub / "ccx" / "runs" / rid
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"run_id": rid, **kw}), encoding="utf-8")


def test_phase_wall_from_run_records(tmp_path):
    hub = tmp_path / "h"
    _rec(hub, "r1", label="L", attempts=[{"seconds": 30}, {"seconds": 20}], check={"seconds": 5},
         review={"run_id": "v1"})
    _rec(hub, "v1", label="review:r1", attempts=[{"seconds": 12}])
    _rec(hub, "f1", label="L", review_of="r1", attempts=[{"seconds": 8}], check={"seconds": 4},
         review={"run_id": "v2"})
    _rec(hub, "v2", label="review:f1", attempts=[{"seconds": 6}])
    ph = r5.phase_wall(hub, ["r1", "f1", "gone"], wall_s=100)        # v1 / v2 found through the records
    assert ph == {"sub_s": 50.0, "check_s": 5.0, "review_s": 18.0, "fix_s": 12.0, "n_attempts": 2, "n_reviews": 2,
                  "n_fix_rounds": 1, "missing": 1, "lead_wait_s": 85.0, "lead_active_s": 15.0}
    assert r5.phase_wall(hub, ["r1"], wall_s=10)["lead_wait_s"] == 10.0          # never more than the wall
    assert "lead_wait_s" not in r5.phase_wall(hub, ["r1"])                         # direct: no lead
    rows = [_row("a", 1, "ccx2", True, 0.1, 100, phases=ph),
            _row("b", 1, "ccx2", True, 0.1, 100, phases={**ph, "sub_s": 10.0}), _row("c", 1, "ccx2", True, 0.1, 1)]
    st = r5.summarize(rows)["arms"]["ccx2"]["phases"]
    assert st["sub_s"] == {"med": 50.0, "p75": 50.0, "n": 2} and st["lead_wait_s"]["med"] == 85.0


def test_budget_counts_only_its_tag(tmp_path):
    from common import append_jsonl
    f = tmp_path / "r.jsonl"
    append_jsonl(f, {"tag": "old", "usd": 50.0})
    append_jsonl(f, {"tag": "new", "usd": 1.25})
    assert r5.spent(f) == 51.25 and r5.spent(f, "new") == 1.25
    assert r5.budget_spent(f, "new", 0.5) == 1.75 and r5.budget_spent(f, "none") == 0
    assert r5.spend_line(f, "new", 0.5, 0.25) == "run=$0.250 tag=$1.750 file=$51.250"
