"""Fix-round re-review replay (scripts/eval/rereview_replay.py): matching [must] items and the summary, from
hand-written result files. No real CLI, no model call."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "eval"))
import rereview_replay as R  # noqa: E402


class TestMatching(unittest.TestCase):
    def test_same_problem_needs_the_same_file_and_a_shared_identifier(self):
        rec = "[must] ccx/memory.py:351 — `use_report` skips notes that `compact` removed"
        self.assertTrue(R.same_problem(rec, "[must] memory.py:360 `use_report` still drops them"))
        self.assertFalse(R.same_problem(rec, "[must] ccx/board.py:12 `use_report` is wrong"))      # other file
        self.assertFalse(R.same_problem(rec, "[must] ccx/memory.py:9 `entries` is slow"))          # other names
        self.assertTrue(R.same_problem("[must] a.py:3 — off by one", "[must] a.py:4 still off"))  # no names quoted


class TestSummary(unittest.TestCase):
    def test_pairs_rescues_and_missed_musts(self):
        d = Path(tempfile.mkdtemp())
        cases = [{"id": "r5x/1-t-ccx2/F1", "recorded": {"verdict": "issues", "issues": ["[must] a.py:3 `f` wrong"]}},
                 {"id": "r5x/2-t-ccx2/F2", "recorded": {"verdict": "pass", "issues": []}}]
        res = [{"case": "r5x/1-t-ccx2/F1", "variant": "full", "ok": True, "seconds": 60, "verdict": "issues",
                "issues": ["[must] a.py:5 `f` still wrong"], "usd": 0.02},
               {"case": "r5x/1-t-ccx2/F1", "variant": "focus", "ok": True, "seconds": 40, "verdict": "pass",
                "issues": [], "usd": 0.01},
               {"case": "r5x/2-t-ccx2/F2", "variant": "full", "ok": True, "seconds": 50, "verdict": "pass",
                "issues": [], "usd": 0.01},
               {"case": "r5x/2-t-ccx2/F2", "variant": "focus", "ok": True, "seconds": 30, "verdict": "pass",
                "issues": [], "usd": 0.01},
               {"case": "r5x/3-t-ccx2/F3", "variant": "full", "skipped": "budget"}]
        out = d / "out.json"
        out.write_text(json.dumps({"spent": 0.05, "cases": cases, "results": res}), encoding="utf-8")
        rows = d / "rows.json"
        rows.write_text(json.dumps({"rows": [
            {"workdir": "r5x", "unit": "2-t-ccx2", "fix": "F2", "outcome": "fail->pass", "by": "auto"},
            {"workdir": "r5x", "unit": "9-t-ccx2", "fix": "F9", "outcome": "fail->pass", "by": "lead"}]}),
            encoding="utf-8")
        s = R.summary(out, rows=rows)
        self.assertEqual(s["pairs"], 2)
        self.assertEqual(s["median_saving_s"], 20)
        self.assertEqual(s["recorded_musts"], 1)
        self.assertEqual(s["missed"], {"full": 0, "focus": 1})
        self.assertEqual(s["rescues_kept"], 1)
        self.assertEqual([r["case"] for r in s["rescues"]], ["r5x/2-t-ccx2/F2"])
        self.assertEqual(s["verdict_table"]["issues->pass"], 1)


if __name__ == "__main__":
    unittest.main()
