"""scripts/eval: every task's start code fails its hidden test and the reference solution passes it; the
summary statistics of the H11 comparison (no real CLIs, no model calls)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EVAL = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(EVAL))

import common  # noqa: E402
import h11_compare  # noqa: E402
from tasks import PARALLEL_TASK, TASKS  # noqa: E402

HAS_PYTEST = subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0


@unittest.skipUnless(HAS_PYTEST, "pytest is needed to run the tasks' tests")
class TestTaskBank(unittest.TestCase):
    def test_start_fails_solution_passes(self):
        tmp = Path(tempfile.mkdtemp())
        for t in [*TASKS, PARALLEL_TASK]:
            with self.subTest(task=t["id"]):
                repo = common.make_repo(t, tmp / t["id"])
                self.assertFalse(common.score(repo, t)["ok"], "the hidden test must be able to fail")
                for name, text in t["solution"].items():
                    (repo / name).write_text(text, encoding="utf-8")
                self.assertTrue(common.score(repo, t)["ok"], common.score(repo, t)["pytest"])
                self.assertFalse((repo / common.HIDDEN).exists())          # the hidden test is removed again


class TestStats(unittest.TestCase):
    def test_sign_test_and_bootstrap(self):
        self.assertAlmostEqual(common.sign_test([-1] * 6), 0.03125)
        self.assertEqual(common.sign_test([1, -1]), 1.0)
        self.assertIsNone(common.sign_test([0, 0]))
        lo, hi = common.boot_ci([1.0, 2.0, 3.0, 4.0])
        self.assertLessEqual(lo, hi)

    def test_parse_stream_dedupes_messages(self):
        ev = ['{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":5,"cache_read_input_tokens":100},'
              '"content":[{"type":"tool_use","name":"Bash","input":{"command":"pytest"}}]}}',
              '{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":5,"cache_read_input_tokens":100},'
              '"content":[{"type":"text","text":"x"}]}}',
              '{"type":"result","total_cost_usd":0.01,"num_turns":2,"usage":{"output_tokens":7},"result":"DONE"}']
        r = common.parse_stream("\n".join(ev))
        self.assertEqual((r["requests"], r["context_tokens"], r["tools"], r["bash"]), (1, 105, {"Bash": 1}, ["pytest"]))
        self.assertEqual(r["cost_usd"], 0.01)

    def test_summary_pairs(self):
        def row(task, arm, req, usd, sub=None):
            return {"tag": "t", "task": task, "arm": arm, "ok": True,
                    "lead": {"cost_usd": usd, "requests": req, "context_tokens": req * 10, "output_tokens": 1,
                             "wall_s": 1.0}, **({"sub_ae_usd": sub, "delegated": True, "sub_ok": [True]} if sub else {})}
        rows = [row("a", "self", 3, 0.03), row("a", "delegate", 2, 0.02, 0.003), row("b", "self", 3, 0.03)]
        s = h11_compare.summarize(rows, lead_context=1000)
        self.assertEqual(s["pairs"], 1)                                     # b has no delegate arm yet
        self.assertEqual(s["metrics"]["lead_requests"]["diff_median"], -1)
        self.assertEqual(s["metrics"]["lead_tokens_at_real_context"]["diff_median"], -1000)
        self.assertEqual(s["rework"]["did_not_delegate"], 0)


if __name__ == "__main__":
    unittest.main()
