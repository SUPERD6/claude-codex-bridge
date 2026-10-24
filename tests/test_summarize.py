"""J3: long command output cut down by code before the lead reads it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import summarize  # noqa: E402
from test_ccx import Env  # noqa: E402

UNITTEST = """test_a (t.T.test_a) ... ok
""" + "noise line\n" * 300 + """======================================================================
FAIL: test_b (t.T.test_b)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/r/lib.py", line 10, in helper
    x = compute()
  File "/r/t.py", line 42, in test_b
    self.assertEqual(f(2), 5)
AssertionError: 4 != 5

----------------------------------------------------------------------
Ran 2 tests in 0.010s

FAILED (failures=1)
"""

DIFF = """diff --git a/x.py b/x.py
index 1..2 100644
--- a/x.py
+++ b/x.py
@@ -1,2 +1,3 @@
-old
+new
+more
diff --git a/y.md b/y.md
--- a/y.md
+++ b/y.md
@@ -5 +5 @@
-a
+b
"""


class TestCut(unittest.TestCase):
    def test_tests_keep_failure_frame_and_summary(self):
        out, kind = summarize.cut(UNITTEST, ["python", "-m", "unittest"])
        self.assertEqual(kind, "test")
        self.assertIn("FAIL: test_b", out)
        self.assertIn('File "/r/t.py", line 42', out)               # the last frame, not the first
        self.assertNotIn("/r/lib.py", out)
        self.assertIn("AssertionError: 4 != 5", out)
        self.assertIn("FAILED (failures=1)", out)
        self.assertNotIn("noise line", out)

    def test_diff_per_file(self):
        out, kind = summarize.cut(DIFF, ["git", "diff"])
        self.assertEqual(kind, "diff")
        self.assertTrue(out.startswith("2 files changed, +3 −2"))
        self.assertIn("  x.py  +2 −1", out)

    def test_log_errors_with_context_and_repeats_folded(self):
        text = "\n".join(["start"] + ["retrying"] * 50 + ["step 3", "ERROR disk full", "after"] + ["idle"] * 40)
        out, kind = summarize.cut(text, ["./build.sh"])
        self.assertEqual(kind, "log")
        self.assertIn("step 3\nERROR disk full\nafter", out)
        self.assertIn("idle   [×", out)
        self.assertLess(len(out), 400)

    def test_cap(self):
        out, _ = summarize.cut("ERROR x\n" * 0 + "\n".join(f"error {i}" for i in range(2000)), ["x"], max_chars=500)
        self.assertLess(len(out), 600)
        self.assertIn("cut: more in the full log", out)


class TestCli(Env):
    def test_runs_keeps_full_log_and_exit_code(self):
        r = self.ccx("sum", "--", sys.executable, "-c", "import sys; print('x\\n' * 400); print('Error: bad'); sys.exit(3)")
        self.assertEqual(r.returncode, 3)
        self.assertIn("exit 3", r.stdout)
        self.assertIn("Error: bad", r.stdout)
        logs = list((self.work / ".ccx" / "sum").glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertGreater(len(logs[0].read_text(encoding="utf-8")), 800)
        self.assertEqual((self.work / ".ccx" / "sum" / ".gitignore").read_text(encoding="utf-8"), "*\n")


if __name__ == "__main__":
    unittest.main()
