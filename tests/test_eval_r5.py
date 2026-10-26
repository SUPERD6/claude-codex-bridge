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


def test_summary_of_rows():
    rows = [{"task": "a", "round": 1, "arm": arm, "ok": arm != "self", "usd": usd, "lead_only_usd": usd,
             "lead_tokens": 10, "lead_requests": 3, "wall_s": 5}
            for arm, usd in (("self", 0.3), ("builtin", 0.3), ("ccx", 0.2), ("direct", 0.04))]
    s = r5.summarize(rows)
    assert s["arms"]["self"]["cps"] is None and s["arms"]["direct"]["cps"] == 0.04
