"""A read run that comes back with an empty answer is not ok (2026-10-31 install walkthrough: README's first example
on T1 returned nothing 4/4 and the receipt said ok)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_ccx import Env  # noqa: E402


class TestNoAnswer(Env):
    def go(self, summary, mode="read"):
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", mode,
                     "--no-fallback", "--no-escalate", "--review", "off", "Summarise README.md in three lines",
                     env={"FAKE_SUMMARY": summary})
        return json.loads(r.stdout), r

    def test_empty_answer(self):
        for summary in (" ", "\n\t", "ok."):
            out, r = self.go(summary)
            self.assertEqual((out["ok"], out.get("kind"), r.returncode), (False, "no_answer", 2), summary)
            self.assertTrue(out["needs_lead"].startswith("no_answer"))
            self.assertIn("--tier T2", out["hint"])
            self.assertIn("ok=false", out["recap"])

    def test_a_real_answer_stays_ok(self):
        out, r = self.go("README says ccx delegates work between Claude Code and Codex.")
        self.assertTrue(out["ok"], out)
        self.assertNotIn("kind", out)
        self.assertEqual(r.returncode, 0)

    def test_write_runs_are_not_judged_by_their_summary(self):
        out, _ = self.go(" ", mode="write")
        self.assertNotEqual(out.get("kind"), "no_answer")


if __name__ == "__main__":
    unittest.main()
