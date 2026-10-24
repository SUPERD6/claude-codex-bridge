"""Tests for the standalone task-split skill."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import os
ROOT = Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp()
os.environ["TASK_SPLIT_HOME"] = _TMP          # never write learned state into the repo during tests
SCRIPT = ROOT / "skills" / "task-split" / "scripts" / "split_plan.py"
spec = importlib.util.spec_from_file_location("split_plan", SCRIPT)
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


class TestModel(unittest.TestCase):
    def test_metr_curve(self):
        self.assertAlmostEqual(sp.p_success(120, 120), 0.5)
        # 80% horizon about 5x shorter than the 50% horizon
        self.assertAlmostEqual(sp.max_minutes_for(0.8, 100), 100 / 5, delta=1.5)
        self.assertAlmostEqual(sp.p_success(sp.max_minutes_for(0.8, 100), 100), 0.8, places=3)

    def test_checkable_split_lands_near_80pct_horizon(self):
        r = sp.size(240, "codex:gpt-6.1-sol:medium", 8, True, 3)
        self.assertGreater(r["best"]["pieces"], 1)
        self.assertGreaterEqual(r["best"]["p_piece"], 0.8)
        self.assertGreater(r["best"]["p_task"], sp.evaluate(240, 1, 120, 8, True)["p_task"])

    def test_uncheckable_work_should_not_be_split(self):
        r = sp.size(240, "codex:gpt-6.1-sol:medium", 8, False, 3)
        self.assertEqual(r["best"]["pieces"], 1)
        self.assertTrue(any("not checkable" in a for a in r["advice"]))
        # and the math: more pieces -> lower task success when nothing is checked
        self.assertLess(sp.evaluate(240, 8, 120, 8, False)["p_task"], sp.evaluate(240, 1, 120, 8, False)["p_task"])

    def test_small_task_stays_whole(self):
        r = sp.size(15, "claude:opus:high", 8, True, 3)
        self.assertEqual(r["best"]["pieces"], 1)

    def test_stronger_rung_allows_bigger_pieces(self):
        weak = sp.size(300, "codex:gpt-6.1-sol:medium", 8, True, 3)["best"]["piece_minutes"]
        strong = sp.size(300, "claude:opus:high", 8, True, 3)["best"]["piece_minutes"]
        self.assertGreater(strong, weak)


class TestPlanCheck(unittest.TestCase):
    def test_template_waves_critical_path_and_flags(self):
        r = sp.check(sp.TEMPLATE, 3)
        self.assertEqual(r["waves"], [["api"], ["disk", "mem"], ["wire"], ["docs"]])
        self.assertEqual(r["critical_path"], ["api", "disk", "wire", "docs"])
        self.assertGreaterEqual(r["wall_minutes_upper_bound"], r["wall_minutes_with_lanes"])
        docs = next(p for p in r["pieces_report"] if p["id"] == "docs")
        self.assertTrue(any("no check" in f for f in docs["flags"]))
        self.assertIn("--step", r["checkpoint_init"])

    def test_file_clash_in_same_wave(self):
        plan = {"pieces": [{"id": "a", "minutes": 20, "files": ["x.py"]},
                           {"id": "b", "minutes": 20, "files": ["x.py", "y.py"]}]}
        r = sp.check(plan, 2)
        self.assertEqual(r["file_clashes"][0]["files"], ["x.py"])

    def test_cycle_rejected(self):
        plan = {"pieces": [{"id": "a", "minutes": 20, "depends_on": ["b"]},
                           {"id": "b", "minutes": 20, "depends_on": ["a"]}]}
        with self.assertRaises(SystemExit):
            sp.check(plan, 2)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            t = subprocess.run([sys.executable, str(SCRIPT), "template"], capture_output=True, text=True,
                               encoding="utf-8")
            f = Path(d, "plan.json")
            f.write_text(t.stdout, encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), "check", str(f)], capture_output=True, text=True,
                               encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("critical_path", json.loads(r.stdout))



class TestCalibration(unittest.TestCase):
    def test_failures_shrink_and_successes_grow_the_horizon(self):
        rung = "claude:sonnet:medium"
        h0 = sp.horizon(rung)
        for _ in range(6):
            sp.record(rung, 60, False)
        h_down = sp.horizon(rung)
        self.assertLess(h_down, h0)
        for _ in range(12):
            sp.record(rung, 60, True)
        self.assertGreater(sp.horizon(rung), h_down)
        self.assertIn("learned", sp.size(120, rung, 8, True, 3)["h50_source"])

    def test_validation_messages(self):
        with self.assertRaises(SystemExit):
            sp.check({"pieces": []}, 2)
        with self.assertRaises(SystemExit):
            sp.check({"pieces": [{"id": "a"}]}, 2)
        with self.assertRaises(SystemExit):
            sp.size(0, "claude:sonnet:medium", 8, True, 3)


if __name__ == "__main__":
    unittest.main()
