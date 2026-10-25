"""Core 6 ("more accurate with use") without wrong signals: which runs are evaluations (fake CLIs only)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import ledger  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestIsEval(unittest.TestCase):
    def test_labels_no_ab_and_probes(self):
        self.assertTrue(ledger.is_eval({"label": "eval-7c:r1:x"}))
        self.assertTrue(ledger.is_eval({"label": "selftest-claude"}))
        self.assertTrue(ledger.is_eval({"label": "quota-probe"}))
        self.assertTrue(ledger.is_eval({"label": "fix x", "no_ab": True}))
        self.assertFalse(ledger.is_eval({"label": "fix eval-ish thing"}))
        self.assertFalse(ledger.is_eval({"label": None}))
        self.assertFalse(ledger.is_eval({}))

    def test_verdict_rows_follow_their_run(self):
        rows = [{"run_id": "a", "label": "eval-x"}, {"run_id": "b", "label": "real"},
                {"run_id": "c", "label": "real", "no_ab": True},
                {"type": "verify", "run_id": "a"}, {"type": "verify", "run_id": "b"},
                {"type": "verify", "run_id": "c"}, {"type": "verify", "run_id": "gone"}]
        runs = ledger.runs_by_id(rows)
        self.assertEqual(sorted(runs), ["a", "b", "c"])
        self.assertEqual([ledger.is_eval(r, runs) for r in rows[3:]], [True, False, True, False])
        self.assertFalse(ledger.is_eval(rows[3]))          # without the runs a verdict row has no label


class TestNoAbInLedger(Env):
    def test_no_ab_run_is_marked(self):
        for extra in ([], ["--no-ab"]):
            r = self.ccx("run", "--to", "codex", "--b", "2", "--mode", "read", "--kind", "read", "--review", "off",
                         *extra, "look at x")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        led = self.hub / "ccx" / "ledger.jsonl"
        runs = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines()]
        runs = [x for x in runs if not x.get("type")]
        self.assertEqual([ledger.is_eval(x) for x in runs], [False, True])


if __name__ == "__main__":
    unittest.main()
