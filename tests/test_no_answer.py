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
        for summary in ("README says ccx delegates work between Claude Code and Codex.", "42", "Yes.", "不会，线程安全。"):
            out, r = self.go(summary)
            self.assertTrue(out["ok"], (summary, out))
            self.assertNotIn("kind", out)
            self.assertEqual(r.returncode, 0)

    def test_the_rule(self):
        from ccx.delegate import no_answer
        self.assertTrue(no_answer({"summary": " Done. "}))
        self.assertTrue(no_answer({"summary": "完成"}))
        self.assertFalse(no_answer({"summary": "", "open_questions": ["which file do you mean?"]}))
        self.assertFalse(no_answer({"summary": "", "next_step": "run the tests"}))

    def test_ccx_ask_says_so_and_exits_2(self):
        r = self.ccx("ask", "--to", "codex", "What does README.md say?", env={"FAKE_SUMMARY": " "})
        out = json.loads(r.stdout)
        self.assertEqual((out["ok"], out["kind"], r.returncode), (False, "no_answer", 2), out)
        self.assertIn("nothing to resume", out["hint"])
        r = self.ccx("ask", "--to", "codex", "What does README.md say?", env={"FAKE_SUMMARY": "It describes ccx."})
        out = json.loads(r.stdout)
        self.assertEqual((out["ok"], r.returncode), (True, 0))
        self.assertNotIn("kind", out)

    def test_write_runs_are_not_judged_by_their_summary(self):
        out, _ = self.go(" ", mode="write")
        self.assertNotEqual(out.get("kind"), "no_answer")


if __name__ == "__main__":
    unittest.main()
