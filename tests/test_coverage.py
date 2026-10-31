"""P1-10: a passed check says which tests it ran and whether the run changed or wrote them (display only)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import coverage as cv  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestTargets(unittest.TestCase):
    def test_pytest_paths_options_and_chains(self):
        self.assertEqual(cv.targets("python -m pytest -q tests/test_a.py tests/test_b.py::T::test_x -k foo"),
                         ["tests/test_a.py", "tests/test_b.py"])
        self.assertEqual(cv.targets("pytest -q"), ["."])                       # no path: the whole folder
        self.assertEqual(cv.targets('"C:\\py\\python.exe" -m pytest tests\\test_a.py -p no:cacheprovider'),
                         ["tests/test_a.py"])
        self.assertEqual(cv.targets("ruff check . && python -m pytest -q tests/x_test.py --maxfail 1"),
                         ["tests/x_test.py"])
        self.assertEqual(cv.targets("uv run pytest --deselect tests/test_c.py::t tests"), ["tests"])

    def test_unittest(self):
        self.assertEqual(cv.targets("python -m unittest -q"), ["."])
        self.assertEqual(cv.targets("python -m unittest discover -s tests"), ["tests"])
        self.assertEqual(cv.targets("python -m unittest tests.test_a.T.test_x"), ["tests/test_a/T/test_x"])

    def test_other_commands_are_unknown(self):
        for cmd in ("npm test", "make test", "go test ./...", ""):
            self.assertIsNone(cv.targets(cmd), cmd)
        self.assertEqual(cv.summarize("npm test", Path("."), Path("."), [], [])["unknown"][:9], "not a pyt")


class TestSummarize(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for f in ("tests/test_a.py", "tests/test_b.py", "tests/helpers.py", "src/m.py", "tests/sub/test_c.py"):
            (self.root / f).parent.mkdir(parents=True, exist_ok=True)
            (self.root / f).write_text("", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_files_and_folders(self):
        c = cv.summarize("pytest tests/test_a.py", self.root, self.root, [], [])
        self.assertEqual((c["files"], c["n_files"]), (["tests/test_a.py"], 1))
        c = cv.summarize("pytest tests", self.root, self.root, [], [])
        self.assertEqual(c["files"], ["tests/test_a.py", "tests/test_b.py", "tests/sub/test_c.py"])
        self.assertEqual(c["dirs"], ["tests/"])
        # a dotted unittest name: the longest prefix that is a file
        c = cv.summarize("python -m unittest tests.test_a.T.test_x", self.root, self.root, [], [])
        self.assertEqual(c["files"], ["tests/test_a.py"])

    def test_check_in_a_subfolder_gives_repo_paths(self):
        c = cv.summarize("pytest test_a.py", self.root / "tests", self.root, ["tests/test_a.py"], [])
        self.assertEqual((c["files"], c["edited"], c["basis_changed"]), (["tests/test_a.py"], ["tests/test_a.py"], True))

    def test_basis_changed_and_written(self):
        c = cv.summarize("pytest tests", self.root, self.root, ["tests/test_a.py", "other/test_z.py"],
                         ["tests/sub/test_c.py"])
        self.assertEqual(c["edited"], ["tests/test_a.py"])          # one outside what the check ran is not listed
        self.assertTrue(c["basis_changed"])
        self.assertEqual(c["written"], ["tests/sub/test_c.py"])
        self.assertNotIn("own_tests_only", c)
        t = cv.text(c)
        self.assertIn("covers: tests/test_a.py, tests/test_b.py, tests/sub/test_c.py;", t)
        self.assertEqual(cv.text(c, limit=2)[:31], "covers: tests/ (3 test files); ")
        self.assertIn("basis changed: tests/test_a.py edited by the sub-agent", t)
        self.assertIn("written by the sub-agent: tests/sub/test_c.py", t)

    def test_only_its_own_tests(self):
        c = cv.summarize("pytest tests/sub/test_c.py", self.root, self.root, [], ["tests/sub/test_c.py"])
        self.assertTrue(c["own_tests_only"])
        self.assertNotIn("basis_changed", c)
        self.assertIn("only tests the sub-agent wrote", cv.text(c))

    def test_untouched_check_says_nothing_more(self):
        c = cv.summarize("pytest tests/test_b.py", self.root, self.root, ["tests/test_a.py"], ["tests/x/test_n.py"])
        self.assertEqual(set(c), {"files", "n_files"})
        self.assertEqual(cv.text(c), "covers: tests/test_b.py")

    def test_new_tests_from_a_diff(self):
        diff = ("--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@\n-x\n+y\n"
                "--- /dev/null\n+++ b/tests/test_new.py\n@@\n+def test_z(): pass\n"
                "--- /dev/null\n+++ b/src/new.py\n@@\n+x = 1\n")
        self.assertEqual(cv.new_tests(diff), ["tests/test_new.py"])


class TestReceipt(Env):
    """End to end with the fake Codex: the receipt, the recap line and the ledger row."""

    def setUp(self):
        super().setUp()
        self.g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.work / "test_a.py").write_text("import a\n\n\ndef test_x():\n    assert a.x in (1, 2)\n",
                                               encoding="utf-8")
        subprocess.run([*self.g, "add", "."], cwd=self.work, check=True)
        subprocess.run([*self.g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def go(self, writes, check):
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", "--review", "off", "--check", check, "change x to 2 in a.py",
                     env={"FAKE_WRITE": writes})
        self.assertIn(r.returncode, (0, 2), r.stderr)
        return json.loads(r.stdout), r

    def ledger_check(self):
        rows = [json.loads(ln) for ln in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                if ln.strip()]
        return [r for r in rows if not r.get("type")][-1]["check"]

    def test_check_on_an_edited_test_is_flagged(self):
        py = sys.executable.replace("\\", "/")
        out, r = self.go(f"{self.work / 'a.py'}=x = 2\n;{self.work / 'test_a.py'}=import a\ndef test_x():\n    assert a.x == 2\n",
                         f'"{py}" -m pytest -q -p no:cacheprovider test_a.py')
        self.assertTrue(out["check"]["passed"], out)
        self.assertEqual(out["check"]["basis_changed"], ["test_a.py"])
        self.assertIn("covers: test_a.py; basis changed: test_a.py edited by the sub-agent", out["check"]["covers"])
        self.assertTrue(out["ok"])                                  # the verdict itself is unchanged
        self.assertIn("check=passed (covers: test_a.py; basis changed", r.stdout + r.stderr)
        lc = self.ledger_check()
        self.assertEqual((lc["covers_n"], lc.get("basis_changed")), (1, True))

    def test_check_on_untouched_tests(self):
        py = sys.executable.replace("\\", "/")
        out, _ = self.go(f"{self.work / 'a.py'}=x = 2\n", f'"{py}" -m pytest -q -p no:cacheprovider test_a.py')
        self.assertEqual(out["check"]["covers"], "covers: test_a.py")
        self.assertNotIn("basis_changed", out["check"])
        self.assertNotIn("basis_changed", self.ledger_check())


if __name__ == "__main__":
    unittest.main()
