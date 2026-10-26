"""Round-4 evaluation script: scheduling and summaries only (it never calls a real CLI here)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import r4  # noqa: E402


def test_calib_schedule_covers_every_task_arm_round():
    us = r4.calib_schedule(2, 41, ["coupon", "inventory"], list(r4.CALIB_ARMS))
    assert len(us) == 2 * 2 * len(r4.CALIB_ARMS)
    assert {(u["round"], u["task"], u["arm"]) for u in us} == {
        (rd, t, a) for rd in (1, 2) for t in ("coupon", "inventory") for a in r4.CALIB_ARMS}
    assert us == r4.calib_schedule(2, 41, ["coupon", "inventory"], list(r4.CALIB_ARMS))     # same seed, same order


def test_every_task_resolves():
    for t in r4.CALIB_TASKS:
        task = r4.by_id(t)
        assert task["brief"] and task["hidden"]


def test_summaries():
    rows = [{"task": "a", "round": 1, "arm": "luna", "ok": False, "usd": 0.002},
            {"task": "a", "round": 1, "arm": "luna_rev", "ok": True, "usd": 0.01},
            {"task": "b", "round": 1, "arm": "luna", "ok": True, "usd": 0.002},
            {"task": "b", "round": 1, "arm": "luna_rev", "ok": True, "usd": 0.008}]
    s = r4.summarize_calib(rows)
    assert s["by_arm"]["luna"]["ok"] == 1 and s["by_arm"]["luna_rev"]["ok"] == 2
    assert s["luna_to_luna_rev_discordant"] == [1, 0] and s["mcnemar_p"] == 1.0
    long = [{"task": t, "arm": a, "ok": True, "usd": u, "lead_tokens": 100, "wall_s": 10, "lead_only_usd": u}
            for t in ("a", "b", "c") for a, u in (("self", 0.5), ("ccx", 0.6), ("builtin", 0.7))]
    ls = r4.summarize_long(long)
    assert ls["arms"]["self"]["cps"] == 0.5
    assert ls["paired"]["self->ccx"]["usd"]["median"] == 0.1
