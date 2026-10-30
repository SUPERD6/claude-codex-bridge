"""The B3 eval harness's paired evidence (scripts/eval/r5.py): the registered rule's true median, report-only paired
token statistics, combined results files, snapshot-split pairs, run-level switches, the frozen daily snapshot,
balanced arm order, kept artifacts of failed units and postflight ledger attribution. Fake rows and homes only."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import pytest  # noqa: E402
import r5  # noqa: E402


def _row(arm, rd, task, ok, prompt, tag="b3", clean=True, sha="s1"):
    return {"tag": tag, "round": rd, "task": task, "arm": arm, "ok": ok, "env_clean": clean,
            "sub_usage": {"prompt": prompt}, "daily": {"sha256": sha}}


def _pairs(base_prompts, arm_prompts, arm="ccx2daily_nomem", tag="b3"):
    rows = []
    for i, (a, b) in enumerate(zip(base_prompts, arm_prompts)):
        rows += [_row("ccx2daily", 1, f"t{i}", True, a, tag), _row(arm, 1, f"t{i}", True, b, tag)]
    return rows


def test_registered_median_is_the_true_median():
    assert r5.b3_median([1, 2, 3, 4]) == 2.5 and r5.b3_median([3, 1, 2]) == 2 and r5.b3_median([]) is None
    # an even count where the upper middle passes and the true median does not: 4 pairs
    base = [100, 100, 100, 100]
    arm = [70, 80, 90, 100]               # true median 85 (= 0.85 * 100: passes); upper middle 90 (would fail)
    br = r5.b3_rule(_pairs(base, arm), "ccx2daily_nomem")
    assert br["conditions"]["input"]["value"] == [85.0, 100.0] and br["conditions"]["input"]["result"] == "pass"
    arm2 = [80, 84, 88, 100]              # true median 86 > 85: fails (upper middle 88 fails too)
    assert r5.b3_rule(_pairs(base, arm2), "ccx2daily_nomem")["conditions"]["input"]["result"] == "fail"


def test_paired_statistics_are_report_only_and_deterministic():
    base = [100_000] * 10
    arm = [60_000] * 4 + [130_000] * 6     # median ratio passes the rule, but most pairs are higher and the total too
    rows = _pairs(base, arm)
    br = r5.b3_rule(rows, "ccx2daily_nomem")
    p = br["paired"]
    assert p["pairs"] == 10 and p["share_lower"] == 0.4 and p["total_ratio"] == 1.02
    assert p["ratio_median"] == 1.3 and p["ratio_of_medians"] == 1.3
    assert br["token_effect"] == "not shown"
    assert r5.b3_rule(rows, "ccx2daily_nomem")["paired"]["ratio_of_medians_ci"] == p["ratio_of_medians_ci"]
    lo, hi = p["ratio_of_medians_ci"]
    assert lo <= p["ratio_of_medians"] <= hi
    assert p["boot"] == {"n": r5.B3_BOOT_N, "seed": r5.B3_BOOT_SEED, "dropped": 0, "task_n": r5.B3_BOOT_N,
                         "task_dropped": 0}
    good = r5.b3_rule(_pairs(base, [70_000] * 8 + [110_000] * 2), "ccx2daily_nomem")
    assert good["result"] == "pass" and good["paired"]["share_lower"] == 0.8 and good["paired"]["total_ratio"] == 0.78
    assert good["token_effect"] == "consistent"
    # the rule passes on the median, but the total is above 0.85: the effect is not shown, the result stays pass
    mixed = r5.b3_rule(_pairs(base, [80_000] * 6 + [140_000] * 4), "ccx2daily_nomem")
    assert mixed["result"] == "pass" and mixed["paired"]["total_ratio"] == 1.04 and mixed["token_effect"] == "not shown"


def test_pairs_on_different_daily_snapshots_are_left_out():
    rows = _pairs([100] * 4, [70] * 4)
    rows[1] = {**rows[1], "daily": {"sha256": "other"}}             # t0's arm unit ran on another snapshot
    rows[2] = {**rows[2], "daily": {}}                              # a side that does not say: kept
    br = r5.b3_rule(rows, "ccx2daily_nomem")
    assert br["units"] == 3 and br["snapshot_mismatch"]["pairs"] == 1
    assert br["snapshot_mismatch"]["units"][0]["task"] == "t0" and br["paired"]["pairs"] == 3
    assert br["result"] == "unknown"                                 # the other 3 pairs pass: conservative
    clean = r5.b3_rule(_pairs([100] * 4, [70] * 4), "ccx2daily_nomem")
    assert "snapshot_mismatch" not in clean and clean["result"] == "pass"


def test_a_split_lost_pair_cannot_turn_a_fail_into_a_pass():
    rows = []
    for i in range(6):          # t0-t2: round 1 lost (base right, arm wrong); t3-t5: round 1 only the arm right
        lost = i < 3
        rows += [_row("ccx2daily", 1, f"t{i}", lost, 100), _row("ccx2daily_nomem", 1, f"t{i}", not lost, 70),
                 _row("ccx2daily", 2, f"t{i}", True, 100), _row("ccx2daily_nomem", 2, f"t{i}", True, 70)]
    br = r5.b3_rule(rows, "ccx2daily_nomem")
    assert br["result"] == "fail" and br["conditions"]["lost_pairs"]["value"] == 3      # only the lost pairs fail
    rows[1] = {**rows[1], "daily": {"sha256": "other"}}  # one lost pair ran on two snapshots: lost would drop to 2
    br = r5.b3_rule(rows, "ccx2daily_nomem")
    assert br["conditions"]["lost_pairs"]["value"] == 2 and br["result"] == "unknown"   # not a pass
    every = [{**r, "daily": {"sha256": "b" if r["arm"] == "ccx2daily" else "a"}} for r in rows]
    allsplit = r5.b3_rule(every, "ccx2daily_nomem")      # every pair split: reported, not dropped silently
    assert allsplit["units"] == 0 and allsplit["result"] == "unknown" and allsplit["snapshot_mismatch"]["pairs"] == 12
    assert "ccx2daily vs ccx2daily_nomem" in r5.b3_rules(every)
    assert any("left out" in ln for ln in r5.b3_rule_lines("x", allsplit))


def test_the_task_cluster_interval_resamples_tasks_and_counts_dropped_resamples():
    rows = []
    for rd in (1, 2):                                     # 5 tasks x 2 rounds: a task's rounds go together
        for i in range(5):
            rows += [_row("ccx2daily", rd, f"t{i}", True, 100 + i), _row("ccx2daily_nomem", rd, f"t{i}", True,
                                                                         60 + 10 * i + rd)]
    p = r5.b3_rule(rows, "ccx2daily_nomem")["paired"]
    assert p["pairs"] == 10 and p["tasks"] == 5
    lo, hi = p["ratio_of_medians_task_ci"]
    assert lo <= p["ratio_of_medians"] <= hi and p["boot"]["task_n"] == r5.B3_BOOT_N
    assert r5.b3_rule(rows, "ccx2daily_nomem")["paired"]["ratio_of_medians_task_ci"] == [lo, hi]
    one = r5.b3_paired([100.0, 90.0], [70.0, 60.0], tasks=["t0", "t0"])
    assert one["ratio_of_medians_task_ci"] is None and one["ratio_of_medians_ci"]   # one task: no task interval
    zero = r5.b3_paired([0.0, 0.0, 100.0], [1.0, 1.0, 50.0])  # resamples with a base median of 0 are counted
    assert zero["boot"]["dropped"] > 0


def test_summary_reads_several_results_files_and_tags(tmp_path, capsys):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    half1 = _pairs([100] * 3, [70] * 3, tag="m1h2")
    half2 = _pairs([100] * 2, [70] * 2, tag="m1r5") + [_row("ccx2daily", 1, "x", True, 1, tag="other")]
    a.write_text("".join(json.dumps(r) + "\n" for r in half1), encoding="utf-8")
    b.write_text("".join(json.dumps(r) + "\n" for r in half2), encoding="utf-8")
    assert r5.main(["summary", "--results", str(a), str(b), str(a), "--tag", "m1h2", "--tag", "m1r5"]) == 0
    cap = capsys.readouterr()
    res = json.loads(cap.out)
    assert res["tags"] == ["m1h2", "m1r5"]
    br = res["b3_rules"]["ccx2daily vs ccx2daily_nomem"]
    assert br["units"] == 5 and br["result"] == "pass" and br["token_effect"] == "consistent"
    assert "b3 rule ccx2daily vs ccx2daily_nomem: pass on 5 pairs" in cap.err
    ns = argparse.Namespace(results=[str(a)], tag=["m1h2"], taskset="r5")
    assert len(r5.summary_rows(ns)) == 6
    assert r5.tagged(half2, "m1r5") == half2[:4]                    # one tag as a string still works


def _rec(hub, rid, **kw):
    d = hub / "ccx" / "runs" / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps({"run_id": rid, **kw}), encoding="utf-8")


def test_switches_applied_reads_each_run_record(tmp_path):
    from ccx.config import SUBAGENT_SWITCHES
    hub = tmp_path / "h"
    on = {**SUBAGENT_SWITCHES, "codex_memories": False, "codex_lean_tools": True}
    _rec(hub, "w1", label="L", mode="write", subagent_switches=on, attempts=[{"agent": "codex"}])
    _rec(hub, "v1", label="review:w1", mode="read", subagent_switches=on, attempts=[{"agent": "codex"}])
    _rec(hub, "c1", label="L", mode="write", subagent_switches=on, attempts=[{"agent": "claude"}])
    _rec(hub, "old", label="L", mode="write", attempts=[{"agent": "codex"}])          # before the field
    got = r5.switches_applied(hub, ["w1", "v1", "c1", "old", "gone"], {"codex_memories": False,
                                                                       "codex_lean_tools": True})
    runs = {r["run"]: r for r in got["runs"]}
    assert got["argv_recorded"] is False and got["match"] is True and "derived" in got["note"]
    w = runs["w1"]["codex_flags"]
    assert w["memories_off"].startswith("-c features.memories=false") and w["web_search_off"] and w["apps_plugins_off"]
    v = runs["v1"]["codex_flags"]
    assert runs["v1"]["review"] and v["memories_off"] and not v["web_search_off"]      # read runs keep web search
    assert "codex_flags" not in runs["c1"] and runs["old"]["subagent_switches"] is None
    assert runs["gone"] == {"run": "gone", "record": "missing"}
    assert r5.switches_applied(hub, ["w1"], {})["match"] is False                      # the baseline wanted none
    assert "match" not in r5.switches_applied(hub, ["w1"])


@pytest.fixture
def daily_homes(tmp_path):
    me = tmp_path / "me"
    codex, agents, ev = me / ".codex", me / ".agents", tmp_path / "eval-codex"
    files = {codex / "memories" / "notes.md": "remember: tabs", codex / "AGENTS.md": "# my rules\n",
             codex / "auth.json": "PERSON-SECRET", codex / "sessions" / "s.jsonl": "PERSON-SECRET",
             codex / "config.toml": ('[windows]\nsandbox = "elevated"\n[features]\nmemories = true\n[memories]\n'
                                     'use_memories = true\n[hooks]\nx = "PERSON-SECRET"\n'),
             codex / "skills" / "mine" / "SKILL.md": "---\nname: mine\n---\n",
             agents / "skills" / "shared" / "SKILL.md": "---\nname: shared\n---\n",
             ev / "auth.json": "EVAL-LOGIN"}
    for f, text in files.items():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return {"codex": codex, "agents": agents, "eval": ev, "tmp": tmp_path}


def test_daily_snapshot_is_frozen_once_per_run(daily_homes):
    import daily_home as DH
    import preflight as PF
    h = daily_homes
    a = argparse.Namespace(daily_codex_source=str(h["codex"]), daily_agents_source=str(h["agents"]))
    snap = r5.freeze_daily(a, h["tmp"] / "w" / r5.DAILY_SNAPSHOT)
    frozen = Path(snap["codex"])
    assert (frozen / "memories" / "notes.md").exists() and not (frozen / "auth.json").exists()
    assert "PERSON-SECRET" not in "".join(p.read_text(encoding="utf-8") for p in frozen.rglob("*") if p.is_file())
    assert PF.codex_kept_toml(frozen) == PF.codex_kept_toml(h["codex"])            # reads back the same settings
    assert DH.memory_settings(frozen) == DH.memory_settings(h["codex"])
    assert r5.daily_sources(a) == (frozen, Path(snap["agents"]))
    shas = []
    for i, arm in enumerate(("ccx2daily", "ccx2daily_nomem")):
        hub = h["tmp"] / f"h{i}"
        r5.r3.make_hub(hub)
        u = PF.Unit(key=f"{i}-t-{arm}", work=h["tmp"], repo=h["tmp"] / f"repo{i}", hub=hub, codex_home=h["eval"])
        info, _env = r5.set_daily(u, hub, {}, arm, a)
        assert info["snapshot"]["frozen"] and info["snapshot"]["sha256"] == snap["sha256"]
        shas.append(info["sha256"])
        # the person's real memories are rewritten between the two units of the pair
        (h["codex"] / "memories" / "notes.md").write_text("rewritten mid-run", encoding="utf-8")
    assert shas[0] == shas[1]
    fresh = argparse.Namespace(daily_codex_source=str(h["codex"]), daily_agents_source=str(h["agents"]))
    hub = h["tmp"] / "h9"
    r5.r3.make_hub(hub)
    u = PF.Unit(key="9-t-ccx2daily", work=h["tmp"], repo=h["tmp"] / "repo9", hub=hub, codex_home=h["eval"])
    info, _env = r5.set_daily(u, hub, {}, "ccx2daily", fresh)                      # not frozen: the real, new setup
    assert info["sha256"] != shas[0] and info["snapshot"] == {"frozen": False}


def _old_schedule(rounds, seed, tasks, arms):
    import random
    out = []
    for rd in range(1, rounds + 1):
        rnd = random.Random(f"{seed}:r5:{rd}")
        ts = list(tasks)
        rnd.shuffle(ts)
        for t in ts:
            arm_list = list(arms)
            rnd.shuffle(arm_list)
            out += [{"exp": "r5", "round": rd, "task": t, "arm": arm} for arm in arm_list]
    return out


DAILY4 = ["ccx2daily", "ccx2daily_nomem", "ccx2daily_clean", "ccx2daily_leantools"]


def test_shuffle_schedule_is_unchanged():
    tasks = list(r5.IDS)
    for seed in (53, 7):
        assert r5.schedule(2, seed, tasks, DAILY4) == _old_schedule(2, seed, tasks, DAILY4)
        assert r5.schedule(3, seed, tasks, ["self", "ccx"], "shuffle") == _old_schedule(3, seed, tasks, ["self", "ccx"])


def test_balanced_arm_order_rotates_over_task_and_round():
    from collections import Counter
    tasks = [f"t{i}" for i in range(10)]
    s = r5.schedule(2, 53, tasks, DAILY4, "balanced")
    assert s == r5.schedule(2, 53, tasks, DAILY4, "balanced") and len(s) == 80
    assert [u["task"] for u in s[::4]] == [u["task"] for u in _old_schedule(2, 53, tasks, DAILY4)[::4]]
    groups = [s[i:i + 4] for i in range(0, 80, 4)]
    assert all(sorted(u["arm"] for u in g) == sorted(DAILY4) and [u["arm_pos"] for u in g] == [0, 1, 2, 3]
               for g in groups)
    first = Counter(g[0]["arm"] for g in groups)
    assert set(first) == set(DAILY4) and max(first.values()) - min(first.values()) <= 2
    for pos in range(4):                                       # every place, not only the first, is spread out
        c = Counter(g[pos]["arm"] for g in groups)
        assert max(c.values()) - min(c.values()) <= 2
    by_task = {}
    for g in groups:
        by_task.setdefault(g[0]["task"], []).append(g[0]["arm"])
    assert all(len(set(v)) == 2 for v in by_task.values())    # a task's two rounds start with different arms
    s2 = r5.schedule(4, 53, tasks[:4], DAILY4, "balanced")     # 4 tasks x 4 rounds: an exact Latin square
    assert Counter(s2[i]["arm"] for i in range(0, 64, 4)) == Counter({a: 4 for a in DAILY4})
    starts = {}
    for i in range(0, 64, 4):                                   # tasks a multiple of the rows: rounds still shift
        starts.setdefault(s2[i]["task"], set()).add(s2[i]["arm"])
    assert all(len(v) == 4 for v in starts.values())
    with pytest.raises(ValueError):
        r5.schedule(1, 1, tasks, DAILY4, "random")


def test_run_takes_the_arm_order_and_rows_record_it(tmp_path, capsys):
    rc = r5.main(["run", "--dry-run", "--rounds", "1", "--tasks", ",".join(r5.IDS[:2]), "--arms",
                  "ccx2daily,ccx2daily_nomem", "--arm-order", "balanced", "--out", str(tmp_path / "r.jsonl"),
                  "--workdir", str(tmp_path / "w")])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "[dry] run order vs ccx2daily (base first / pairs): ccx2daily_nomem 1/2" in printed
    labels = [ln.split()[1] for ln in printed.splitlines() if ln.startswith("[dry] eval-r5:")]
    firsts = [labels[0], labels[2]]
    assert len(labels) == 4 and firsts[0].rsplit(":", 1)[1] != firsts[1].rsplit(":", 1)[1]


def test_williams_design_balances_every_arm_against_every_other():
    for n in range(1, 7):
        rows = r5.williams(n)
        assert len(rows) == (2 * n if n % 2 else n) and all(sorted(r) == list(range(n)) for r in rows)
        for a in range(n):
            for b in range(n):
                if a != b:
                    assert sum(r.index(a) < r.index(b) for r in rows) * 2 == len(rows)


def test_balanced_order_puts_the_baseline_first_in_half_of_each_arms_pairs():
    tasks = [f"t{i}" for i in range(10)]
    for seed in (1, 30, 7):                               # the seeds the review found up to 16:4 with a plain rotation
        ob = r5.order_balance(r5.schedule(2, seed, tasks, DAILY4, "balanced"), "ccx2daily")
        assert ob == {a: [10, 20] for a in DAILY4 if a != "ccx2daily"}
    assert set(r5.order_balance(r5.schedule(2, 1, tasks, DAILY4), "ccx2daily")) == set(DAILY4) - {"ccx2daily"}
