"""r5 --lead-model auto: each task's lead model by ccx's lead.model_by_task rule, as its own arm (no real CLIs)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import r5  # noqa: E402


def test_band_minutes_and_difficulty():
    m = r5.band_minutes({"bands": {"medium_minutes": 15, "large_minutes": 45}})
    assert m["small"] == 7.5 and round(m["medium"], 1) == 26.0 and m["large"] == 90
    assert r5.task_difficulty({"id": "t", "minutes": 8}) == (3.0, "minutes")


def test_auto_picks_by_the_ccx_rule(monkeypatch):
    monkeypatch.setattr(r5, "ref_size", lambda t: {"band": t["band"]} if t.get("band") else None)
    easy, hard = r5.auto_lead({"id": "e", "band": "small"}), r5.auto_lead({"id": "h", "band": "large"})
    assert (easy["lead_model"], easy["lead_band"]) == ("sonnet", "easy")
    assert (hard["lead_model"], hard["lead_band"]) == ("opus", "hard")
    assert r5.auto_lead({"id": "c", "band": "small", "risk": "critical"})["lead_model"] == "opus"
    unknown = r5.auto_lead({"id": "u"})                    # no difficulty: the strong lead, never a cheaper one
    assert (unknown["lead_model"], unknown["lead_band"], unknown["lead_b"]) == ("opus", "unknown", None)


def test_auto_is_its_own_arm():
    base = {"tag": "t", "round": 1, "task": "x", "arm": "ccx2", "lead_effort": "medium"}
    auto_s = {**base, "lead_model": "sonnet", "lead_pick": "auto"}
    auto_o = {**base, "lead_model": "opus", "lead_pick": "auto"}
    fixed_s, fixed_o = {**base, "lead_model": "sonnet"}, {**base, "lead_model": "opus"}
    assert r5.arm_of(auto_s) == r5.arm_of(auto_o) == "ccx2@auto-medium"
    assert r5.arm_of(fixed_s) == "ccx2" and r5.arm_of(fixed_o) == "ccx2@opus-medium"
    assert len({r5.done_key(x) for x in (auto_s, fixed_s, auto_o, fixed_o)}) == 4
    assert r5.lead_of(auto_o) == ("opus", "medium")         # the lead actually runs on the picked model
    direct = {**base, "arm": "direct", "lead_model": "opus", "lead_pick": "auto"}
    assert r5.arm_of(direct) == "direct"                    # no lead: auto changes nothing


def test_dry_run_shows_picks_and_cost(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(r5, "ref_size", lambda t: {"band": "small", "lines": 5, "files": 1})
    a = r5.parser().parse_args(["run", "--tag", "t", "--rounds", "1", "--tasks", r5.IDS[0], "--arms", "ccx2",
                                "--lead-model", "auto", "--out", str(tmp_path / "res.jsonl"), "--dry-run",
                                "--workdir", str(tmp_path / "w")])
    assert r5.cmd_run(a) == 0
    out = capsys.readouterr().out
    assert ":ccx2@auto-medium" in out and "lead sonnet (easy" in out and "lead auto picks: sonnet x1" in out
    assert "[estimate] total ~$" in out
