"""F1: independent review of a write run's diff by another vendor's cheap model (fake CLIs only)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import review  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestReason(unittest.TestCase):
    def test_when(self):
        ok = {"open_questions": []}
        self.assertIsNone(review.reason("auto", "low", ok, ["a.py"], ["a.py"]))
        self.assertIsNone(review.reason("on", None, ok, [], []))                     # nothing changed
        self.assertIsNone(review.reason("off", "critical", ok, [], ["a.py"]))
        self.assertEqual(review.reason("on", None, ok, ["a.py"], ["a.py"]), "asked")
        self.assertEqual(review.reason("auto", "visible", ok, ["a.py"], ["a.py"]), "risk visible")
        self.assertIn("unsure", review.reason("auto", None, {"open_questions": ["x?"]}, ["a.py"], ["a.py"]))
        self.assertIn("don't match", review.reason("auto", None, ok, ["b.py"], ["src/a.py"]))
        self.assertIsNotNone(review.reason("auto", None, ok, [], ["a.py"]))
        self.assertIsNone(review.reason("auto", None, ok, ["./src\\a.py"], ["src/a.py"]))
        self.assertIn("60 changed code lines", review.reason("auto", None, ok, ["a.py"], ["a.py"], 60))
        self.assertIsNone(review.reason("auto", None, ok, ["a.py"], ["a.py"], 60, min_lines=0))
        d = "+++ b/a.py\n" + "+x\n" * 3 + "-y\n" + "+++ b/README.md\n" + "+doc\n" * 9
        self.assertEqual(review.code_lines(d), 4)

    def test_reviewer_is_another_vendor(self):
        cfg = {"review": {"by": {"codex": "claude:haiku:low", "claude": "codex:gpt-6-luna:low"}}}
        self.assertEqual(review.reviewers(cfg, "codex", lambda a: True), [("claude", "haiku", "low")])
        self.assertEqual(review.reviewers(cfg, "claude", lambda a: True)[0], ("codex", "gpt-6-luna", "low"))
        self.assertEqual(review.reviewers(cfg, "codex", lambda a: a == "codex"), [])
        cfg["review"]["by"]["deepseek"] = "codex:gpt-6-luna:low"
        self.assertEqual(review.reviewers(cfg, "gemini", lambda a: True),
                         [("claude", "haiku", "low"), ("codex", "gpt-6-luna", "low")])

    def test_vendor_not_cli_decides_who_is_another(self):
        cfg = {"review": {"by": {}}, "providers": {"deepseek": {"agent": "claude"}}}
        # DeepSeek runs through the Claude CLI but is its own vendor: Claude may review it (I3)
        self.assertEqual(review.reviewers({**cfg, "review": {"also": ["claude:haiku:low"]}}, "deepseek",
                                          lambda a: True), [("claude", "haiku", "low")])
        self.assertEqual(review.reviewers({**cfg, "review": {"also": ["claude:haiku:low"]}}, "claude",
                                          lambda a: True), [])
        from ccx import agents
        self.assertTrue(agents.same_vendor("claude", "claude"))
        self.assertFalse(agents.same_vendor("claude", "deepseek", cfg))
        cfg["providers"]["deepseek"]["vendor"] = "anthropic"          # a provider can say it is the same vendor
        self.assertTrue(agents.same_vendor("claude", "deepseek", cfg))

    def test_cheapest_rung_before_routing_and_fallback(self):
        cfg = {"review": {"also": ["claude:sonnet:medium"]},
               "tiers": {"T1": {"claude": {"model": "haiku", "effort": "low"},
                                "codex": {"model": "gpt-6-luna", "effort": "low"}}}}
        got = review.reviewers(cfg, "codex", lambda a: a in ("codex", "claude"))
        self.assertEqual(got, [("claude", "haiku", "low"), ("claude", "sonnet", "medium")])   # sonnet only after
        self.assertEqual(review.reviewers(cfg, "claude", lambda a: a in ("codex", "claude"))[0],
                         ("codex", "gpt-6-luna", "low"))

    def test_brief_asks_for_requirements_not_tests(self):
        b = review.brief("r1", "task", "did it", "+x", 100)
        self.assertIn("requirement by requirement", b)
        self.assertIn("Missing tests, inputs the task doesn't cover, typing or docs taste and style are `[note]", b)

    def test_reviewers_from_routing_data(self):
        import tempfile
        from pathlib import Path
        from ccx.config import Paths
        with tempfile.TemporaryDirectory() as d:
            got = review.reviewers({"review": {}}, "claude", lambda a: a in ("codex", "claude"), Paths(Path(d)))
        self.assertTrue(got and all(a == "codex" for a, _, _ in got))     # routing's cheapest codex read rung

    def test_verdict(self):
        self.assertEqual(review.verdict({"summary": "REVIEW: issues", "open_questions": ["a"]})["verdict"], "issues")
        self.assertEqual(review.verdict({"summary": "review: pass — fine"})["verdict"], "pass")
        self.assertEqual(review.verdict({"summary": "looks ok"})["verdict"], "unclear")
        mixed = review.verdict({"summary": "REVIEW: issues", "open_questions": ["[note] style", "[must] a.py:1 — bug"]})
        self.assertEqual((mixed["verdict"], mixed["issues"]), ("issues", ["[must] a.py:1 — bug"]))
        notes = review.verdict({"summary": "REVIEW: issues", "open_questions": ["[note] Unicode names"]})
        self.assertEqual((notes["verdict"], notes["issues"], notes["notes"]), ("pass", [], ["[note] Unicode names"]))

    def test_brief_says_what_ccx_ran(self):
        b = review.brief("r1", "task", "did it", "+x", 100, {"cmd": "make test", "passed": True, "exit": 0})
        self.assertIn("`make test` after the change: passed", b)
        self.assertIn("cannot run commands", b)


class TestReviewRun(Env):
    def setUp(self):
        super().setUp()
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def go(self, *extra, review_seq="pass"):
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n", "FAKE_REVIEW": review_seq}
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", *extra, "change x to 2 in a.py", env=env)
        self.assertEqual(r.returncode in (0, 2), True, r.stderr)
        return json.loads(r.stdout)

    def reviews(self):
        return [c for c in self.calls() if c["agent"] == "claude" and "[ccx review" in c["prompt"]]

    def test_low_risk_matching_claims_not_reviewed(self):
        out = self.go()
        self.assertNotIn("review", out)
        self.assertEqual(self.reviews(), [])

    def test_issues_fixed_then_pass(self):
        out = self.go("--risk", "visible", review_seq="issues,pass")
        self.assertEqual(out["review"]["verdict"], "pass")
        self.assertEqual(out["review"]["first_round"]["verdict"], "issues")
        self.assertIn("fixed_after_review_of", out)
        rv = self.reviews()
        self.assertEqual(len(rv), 2)
        self.assertIn("x = 2", rv[0]["prompt"])                          # the reviewer saw the diff
        fix = [c for c in self.calls() if c["agent"] == "codex" and c["argv"][:2] == ["exec", "resume"]]
        self.assertTrue(fix and "off by one" in fix[-1]["prompt"])           # the issues went back to the worker

    def test_still_failing_after_fix(self):
        out = self.go("--review", "on", review_seq="issues")
        self.assertEqual(out["kind"], "review_failed")
        self.assertIn("independent review", out["hint"])
        self.assertEqual(len(self.reviews()), 2)

    def test_claude_worker_may_run_the_check(self):
        r = self.ccx("run", "--to", "claude", "--model", "haiku", "--effort", "low", "--mode", "write", "--review",
                     "off", "--check", '"C:\\py\\python.exe" -m unittest -q', "change x")
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = [c["argv"] for c in self.calls() if c["agent"] == "claude"][-1]
        self.assertIn('Bash("C:\\py\\python.exe" -m unittest -q)', argv[argv.index("--allowed-tools") + 1])

    def test_off(self):
        out = self.go("--review", "off", "--risk", "critical")
        self.assertNotIn("review", out)


if __name__ == "__main__":
    unittest.main()
