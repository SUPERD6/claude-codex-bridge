"""Round 5c: a check that cannot test anything (missing file, nothing collected, an unexpanded glob on Windows) is
told apart from a failed one; a review that still fails is not reported as plainly ok."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import Env  # noqa: E402

from ccx.delegate import compact, recap  # noqa: E402
from ccx.workspace import _expand_globs, missing_test_paths, run_check  # noqa: E402


def _tree() -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "tests").mkdir()
    for n in ("test_memory_e7.py", "test_memory_rank.py", "test_board.py"):
        (d / "tests" / n).write_text("def test_x():\n    pass\n", encoding="utf-8")
    (d / "tests" / "test_empty.py").write_text("X = 1\n", encoding="utf-8")
    return d


class TestCheckHelpers(unittest.TestCase):
    def test_globs_expand_relative_to_cwd(self):
        d = _tree()
        out = _expand_globs("python -m pytest -q tests/test_memory_*.py", d)
        self.assertEqual(out, "python -m pytest -q tests/test_memory_e7.py tests/test_memory_rank.py")
        self.assertEqual(_expand_globs('python -c "print(1*2)" tests/nomatch_*.py', d),
                         'python -c "print(1*2)" tests/nomatch_*.py')       # quoted and unmatched stay as they are

    def test_missing_test_paths_lists_close_matches(self):
        d = _tree()
        miss = missing_test_paths("python -m pytest -q tests/test_memory.py tests/test_board.py::test_x", d)
        self.assertEqual([m["path"] for m in miss], ["tests/test_memory.py"])
        self.assertIn("tests/test_memory_e7.py", miss[0]["close"])
        self.assertEqual(missing_test_paths("python -m pytest -q tests/test_*.py", d), [])

    def test_check_with_one_close_match_is_fixed_else_lists_existing_files(self):
        import contextlib, io
        from ccx.commands.delegation import _check_names_real_tests
        d = _tree()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = _check_names_real_tests("python -m pytest -q tests/test_bord.py::test_x -x", d)
        self.assertEqual(out, "python -m pytest -q tests/test_board.py::test_x -x")
        self.assertIn("using tests/test_board.py", err.getvalue())
        self.assertEqual(len(err.getvalue().splitlines()), 1)
        with self.assertRaises(ValueError) as e:                     # close, but a guessed suffix: stop
            _check_names_real_tests("python -m pytest -q tests/test_memory.py", d)
        self.assertIn("Existing test files: tests/test_board.py, tests/test_empty.py", str(e.exception))
        with self.assertRaises(ValueError) as e:
            _check_names_real_tests("python -m pytest -q tests/x.py", d)
        self.assertIn("tests/x.py", str(e.exception))
        self.assertIn("tests/test_memory_rank.py", str(e.exception))

    def test_pytest_usage_error_and_no_tests_are_broken_not_failed(self):
        d = _tree()
        for target, code in (("tests/test_nope.py", 4), ("tests/test_empty.py", 5)):
            c = run_check(f"{sys.executable} -m pytest -q -p no:cacheprovider {target}", d)
            self.assertEqual((c["exit"], c.get("status")), (code, "check_broken"), c)
            self.assertFalse(c["passed"])
            self.assertIn("fix the check", c["broken"])
        ok = run_check(f"{sys.executable} -c pass", d)
        self.assertTrue(ok["passed"])
        self.assertNotIn("broken", ok)


def _record(**kw) -> dict:
    rec = {"run_id": "r1", "to": "codex", "tier": "T1", "attempts": [{"model": "m", "effort": "low"}],
           "result": {"status": "done", "summary": "did it"}, "ok": True, "state": "finished", "cwd": "/w"}
    rec.update(kw)
    return rec


class TestCompactNeedsLead(unittest.TestCase):
    def test_review_failed_is_not_plainly_ok(self):
        rec = _record(kind="review_failed", review={"verdict": "issues", "by": "claude:x:low",
                                                     "issues": ["[must] a.py:3 - NameError under except", "[must] b"],
                                                     "edited_tests": ["tests/test_a.py"]})
        res = compact(rec)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "done")                       # the sub-agent's own status stays readable
        self.assertEqual(res["needs_lead"], "review_failed: [must] a.py:3 - NameError under except")
        self.assertEqual(res["edited_tests"], ["tests/test_a.py"])
        line = recap(rec, res)
        self.assertIn("ok=false", line)
        self.assertIn("needs_lead=review_failed", line)

    def test_check_broken_needs_the_lead(self):
        rec = _record(kind="check_broken", check={"cmd": "pytest x", "exit": 4, "passed": False,
                                                  "broken": "pytest usage error (exit 4); fix the check"})
        res = compact(rec)
        self.assertFalse(res["ok"])
        self.assertEqual(res["check"]["status"], "check_broken")
        self.assertTrue(res["needs_lead"].startswith("check_broken: pytest usage error"))
        self.assertIn("check=broken (exit 4)", recap(rec, res))

    def test_plain_success_unchanged(self):
        res = compact(_record(kind="ok"))
        self.assertTrue(res["ok"])
        self.assertNotIn("needs_lead", res)


class TestCheckCli(Env):
    def test_run_stops_early_on_a_missing_test_file(self):
        (self.work / "tests").mkdir()
        (self.work / "tests" / "test_memory_e7.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "write", "--check",
                     "python -m pytest -q tests/test_memory.py", "do it")
        self.assertNotEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertIn("tests/test_memory.py", out["error"])
        self.assertIn("tests/test_memory_e7.py", out["error"])
        self.assertEqual(self.calls(), [])                            # no sub-agent was paid

    def test_broken_check_is_its_own_kind(self):
        (self.work / "tests").mkdir()
        (self.work / "tests" / "test_empty.py").write_text("X = 1\n", encoding="utf-8")
        r = self.ccx("run", "--from", "claude", "--tier", "T1", "--mode", "write", "--review", "off", "--check",
                     f'"{sys.executable}" -m pytest -q -p no:cacheprovider tests/test_empty.py', "do it")
        out = json.loads(r.stdout)
        self.assertEqual(out["kind"], "check_broken", out)
        self.assertFalse(out["ok"])
        self.assertIn("needs_lead", out)
        self.assertEqual(len(self.calls()), 1)                        # a broken check does not climb the ladder

    def test_resume_replaces_the_check(self):
        out = json.loads(self.ccx("run", "--from", "claude", "--tier", "T2", "--review", "off",
                                  "--check", "python -c \"import sys; sys.exit(1)\"", "implement thing").stdout)
        r = self.ccx("resume", "--review", "off", "--check", "python -c pass", out["run_id"], "go on")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        rec = json.loads((self.hub / "ccx" / "runs" / res["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["check_cmd"], "python -c pass")
        self.assertTrue(res["check"]["passed"], res)


if __name__ == "__main__":
    unittest.main()
