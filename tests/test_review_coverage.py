"""P1-10: the reviewer judges test coverage against the task, not against tests the agent wrote or changed."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import review  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestRubric(unittest.TestCase):
    def test_rubric_asks_for_coverage_against_the_task(self):
        b = " ".join(review.brief("r1", "task", "did it", "+x", 100).split())
        self.assertIn("see whether a test the acceptance command (if any) runs really exercises it", b)
        self.assertIn("tests the agent wrote or changed in this change are its own yardstick", b)
        # a missing test stays a note: the review's false alarms already cost reruns (P1-10: 38 of 65)
        self.assertIn("a missing test, or one only the agent wrote, is by itself a [note], not a [must]", b)
        self.assertIn("the acceptance command (if any) runs", b)
        self.assertIn("missing extra tests", b)

    def test_edited_existing_tests_are_named(self):
        diff = "--- a/tests/test_old.py\n+++ b/tests/test_old.py\n@@ -1 +1 @@\n-    assert f() == 1\n+    assert f() == 2\n"
        b = review.brief("r1", "task", "did it", diff, 100_000)
        self.assertIn("Name these files in your answer: a [must] as above for an assertion the task did not ask to change; otherwise one [note] listing them all", b)

    def test_covers_line(self):
        chk = {"cmd": "pytest tests/test_a.py", "passed": True, "exit": 0}
        b = review.brief("r1", "t", "s", "+x", 100, chk, [], covers={"files": ["tests/test_a.py"], "n_files": 1})
        self.assertIn("The test files it runs: tests/test_a.py.", b)
        b = review.brief("r1", "t", "s", "+x", 100, chk, [], covers={
            "files": ["tests/test_a.py", "tests/test_b.py"], "n_files": 2, "written": ["tests/test_b.py"],
            "edited": ["tests/test_a.py"], "basis_changed": True})
        self.assertIn("Written by the agent in this change: tests/test_b.py. Changed by the agent: tests/test_a.py.", b)
        b = review.brief("r1", "t", "s", "+x", 100, chk, [], covers={"files": ["t/test_n.py"], "n_files": 1,
                                                                     "written": ["t/test_n.py"], "own_tests_only": True})
        self.assertIn("Every one of them was written by the agent in this change.", b)
        b = review.brief("r1", "t", "s", "+x", 100, {"cmd": "npm test", "passed": True}, [],
                         covers={"unknown": "x"})
        self.assertIn("Which tests that command runs is not known", b)
        self.assertNotIn("The test files it runs", review.brief("r1", "t", "s", "+x", 100))

    def test_focus_brief_keeps_the_covers_line(self):
        b = review.brief("r1", "t", "s", "+x", 10_000, {"cmd": "pytest", "passed": True}, [],
                         focus={"issues": ["[must] a"], "delta": "+y"}, covers={"files": ["test_a.py"], "n_files": 1})
        self.assertIn("The test files it runs: test_a.py.", b)

    def test_covers_errors_leave_the_brief_alone(self):
        self.assertIsNone(review._covers(None, Path("."), None, [], ""))
        self.assertIsNone(review._covers({"cmd": "x", "reason": "namecheck"}, Path("."), None, [], ""))
        from unittest import mock
        with mock.patch("ccx.coverage.summarize", side_effect=OSError("boom")):
            self.assertIsNone(review._covers({"cmd": "pytest a.py"}, Path("."), None, [], ""))
        b = review.brief("r1", "t", "s", "+x", 100, {"cmd": "pytest a.py", "passed": True}, [],
                         covers={"files": ["a_test.py"], "n_files": 1, "filtered": ["-k doctor"],
                                 "added_to": ["a_test.py"]})
        self.assertIn("Only the tests selected by `-k doctor` ran. Tests added by the agent to: a_test.py.", b)


class TestReviewSeesCoverage(Env):
    def setUp(self):
        super().setUp()
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.work / "test_a.py").write_text("import a\n\n\ndef test_x():\n    assert a.x in (1, 2)\n",
                                             encoding="utf-8")
        subprocess.run([*g, "add", "."], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def test_review_brief_lists_the_tests_the_check_runs(self):
        py = sys.executable.replace("\\", "/")
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n;{self.work / 'test_a.py'}=import a\ndef test_x():\n"
                             f"    assert a.x == 2\n", "FAKE_REVIEW": "pass"}
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", "--review", "on", "--check", f'"{py}" -m pytest -q -p no:cacheprovider test_a.py',
                     "change x to 2 in a.py", env=env)
        self.assertIn(r.returncode, (0, 2), r.stderr)
        out = json.loads(r.stdout)
        prompts = [c["prompt"] for c in self.calls() if c["agent"] == "claude" and "[ccx review" in c["prompt"]]
        self.assertTrue(prompts, out)
        self.assertIn("The test files it runs: test_a.py.", prompts[-1])
        self.assertNotIn("Changed by the agent: test_a.py", prompts[-1])     # named once, under Existing tests
        self.assertIn("Existing tests edited: test_a.py", prompts[-1])


if __name__ == "__main__":
    unittest.main()
