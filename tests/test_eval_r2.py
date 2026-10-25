"""scripts/eval/r2.py without real CLIs: the schedule, picking the 4-B tasks, the summary statistics."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))

import r2  # noqa: E402


class TestR2(unittest.TestCase):
    def test_schedule_is_fixed_by_the_seed_and_learn_runs_phase1_first(self):
        a, b = r2.schedule(["review", "learn"], 26), r2.schedule(["review", "learn"], 26)
        self.assertEqual(a, b)
        learn = [u["arm"] for u in a if u["exp"] == "learn"]
        self.assertEqual(learn, ["phase1"] * 12 + ["phase2"] * 12)
        self.assertEqual(sum(u["exp"] == "review" for u in a), 12 * 3 * 3)

    def test_coop_tasks_takes_the_most_failed_and_at_least_seven(self):
        rows = [{"exp": "screen2", "task": t, "ok": t not in ("cache", "tags")} for t in r2.TRAP2_IDS]
        rows += [{"exp": "screen2", "task": "tags", "ok": False}, {"exp": "screen", "task": "rank", "ok": False}]
        picked = r2.coop_tasks(rows)
        self.assertEqual(picked[:2], ["tags", "cache"])
        self.assertEqual(len(picked), 7)

    def test_summary_pairs_arms_and_brier(self):
        def row(exp, arm, task, ok, usd, p=None):
            return {"tag": "t", "exp": exp, "round": 1, "task": task, "arm": arm, "ok": ok, "usd": usd,
                    "tokens": 10, "wall_s": 1.0, "route_p": p}
        rows = [row("coop", "single", "a", False, 0.01), row("coop", "way", "a", True, 0.1),
                row("coop", "single", "b", True, 0.01), row("coop", "way", "b", True, 0.1),
                row("route", "warm", "a", True, 0.02, 0.5), row("learn", "phase1", "a", True, 0.02, 0.5),
                row("learn", "phase2", "a", True, 0.02, 0.9)]
        s = r2.summarize(rows)
        c = s["coop:single->way"]
        self.assertEqual((c["pairs"], c["ok"], c["discordant"]["only_way"]), (2, {"single": 1, "way": 2}, 1))
        self.assertEqual(c["spend_ratio"], 10.0)
        self.assertAlmostEqual(s["learn"]["brier_phase2_learning"], 0.01)
        self.assertAlmostEqual(s["learn"]["brier_frozen(route:warm)"], 0.25)
        self.assertEqual(s["spend_usd"], 0.28)


if __name__ == "__main__":
    unittest.main()
