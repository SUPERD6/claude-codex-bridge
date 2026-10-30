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
    assert lo <= p["ratio_of_medians"] <= hi and p["boot"] == {"n": r5.B3_BOOT_N, "seed": r5.B3_BOOT_SEED}
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
    assert "snapshot_mismatch" not in r5.b3_rule(_pairs([100] * 4, [70] * 4), "ccx2daily_nomem")


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
