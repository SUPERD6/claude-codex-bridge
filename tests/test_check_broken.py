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

    def test_single_quotes_become_double_quotes_for_cmd_exe(self):
        # r5e-h: `-k 'a or b'` reached pytest as three words under cmd.exe (exit 4, check_broken)
        d = _tree()
        self.assertEqual(_expand_globs("python -m pytest -q tests/test_board.py -k 'a or b'", d),
                         'python -m pytest -q tests/test_board.py -k "a or b"')
        for same in ("x && y", "a | b > out.txt 2>&1", "echo 'say \"hi\"'", 'python -c "print(\'x\')"', "don't"):
            self.assertEqual(_expand_globs(same, d), same)            # compound / mixed quotes kept as they are
        self.assertEqual(_expand_globs("pytest -k 'a or b' && echo 'ok' > o.txt", d),
                         'pytest -k "a or b" && echo "ok" > o.txt')    # only the quoted tokens change

    def test_single_quotes_inside_a_double_quoted_argument_are_kept(self):
        # review: a regex tokenizer cut `"..."` at an escaped \" (or swallowed `--opt="a` as one word) and then
        # rewrote the `'...'` inside the double-quoted argument, ending its quoting under cmd.exe
        d = _tree()
        for same in ('python -c "import sys; print(\\"x\\", \'a b\')"',
                     'python -c "import sys; print(sys.argv[1:])" --opt="a \'b c\' d"',
                     '--opt="x" \'a', "-k'a b'"):
            self.assertEqual(_expand_globs(same, d), same)
        self.assertEqual(_expand_globs('python -c "print(\\"x\\")" -k \'a or b\'', d),
                         'python -c "print(\\"x\\")" -k "a or b"')       # a quote state that is closed again
        self.assertEqual(_expand_globs("a  'b c'\t tests/test_memory_*.py", d),
                         'a  "b c"\t tests/test_memory_e7.py tests/test_memory_rank.py')   # spacing kept

    @unittest.skipUnless(sys.platform == "win32", "cmd.exe only")
    def test_run_check_keeps_the_argv_of_a_nested_single_quote(self):
        d = _tree()
        cmd = f'"{sys.executable}" -c "import sys; print(\\"x\\", \'a b\')"'
        c = run_check(cmd, d)
        self.assertTrue(c["passed"], c)
        self.assertNotIn("ran", c)
        cmd = (f'"{sys.executable}" -c "import sys; sys.exit(0 if sys.argv[1:] == [chr(45) + \'-opt=a \' + chr(39) '
               f'+ \'b c\' + chr(39) + \' d\'] else 1)" --opt="a \'b c\' d"')
        c = run_check(cmd, d)
        self.assertTrue(c["passed"], c)

    @unittest.skipUnless(sys.platform == "win32", "cmd.exe only")
    def test_run_check_records_the_rewritten_command(self):
        d = _tree()
        cmd = f'"{sys.executable}" -c "import sys; sys.exit(0 if sys.argv[1:] == [chr(97) + \' or b\'] else 1)" \'a or b\''
        c = run_check(cmd, d)
        self.assertTrue(c["passed"], c)
        self.assertEqual(c["cmd"], cmd)
        self.assertTrue(c["ran"].endswith('"a or b"'), c)

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
        with self.assertRaises(ValueError) as e:                     # close, but neither a typo nor a prefix: stop
            _check_names_real_tests("python -m pytest -q tests/test_memry.py", d)
        self.assertIn("Existing test files: tests/test_board.py, tests/test_empty.py", str(e.exception))
        with self.assertRaises(ValueError) as e:
            _check_names_real_tests("python -m pytest -q tests/x.py", d)
        self.assertIn("tests/x.py", str(e.exception))
        self.assertIn("tests/test_memory_rank.py", str(e.exception))

    def test_guessed_short_name_becomes_the_files_it_prefixes(self):
        # r5g: the lead wrote tests/test_memory.py for tests/test_memory_e7.py (and test_quota.py for test_quota_fast.py)
        import contextlib, io
        from ccx.commands.delegation import _check_names_real_tests
        d = _tree()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = _check_names_real_tests("python -m pytest -q tests/test_memory.py tests/test_board.py -x", d)
        self.assertEqual(out, "python -m pytest -q tests/test_memory_e7.py tests/test_memory_rank.py "
                              "tests/test_board.py -x")                      # an explicit list, no glob
        self.assertEqual(err.getvalue().strip(), "ccx: --check names tests/test_memory.py, which does not exist; "
                         "using tests/test_memory_e7.py tests/test_memory_rank.py")
        (d / "tests" / "test_quota_fast.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(_check_names_real_tests("pytest tests\\test_quota.py", d), "pytest tests/test_quota_fast.py")
        with self.assertRaises(ValueError):                           # a node id cannot be split over several files
            _check_names_real_tests("python -m pytest -q tests/test_memory.py::test_x", d)
        (d / "tests" / "test_a_dir").mkdir()
        (d / "tests" / "test_a_dir" / "test_b.py").write_text("X = 1\n", encoding="utf-8")
        with self.assertRaises(ValueError):                           # only files directly under the named folder
            _check_names_real_tests("pytest tests/test_a.py", d)

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
                     "python -m pytest -q tests/test_memry.py", "do it")
        self.assertNotEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertIn("tests/test_memry.py", out["error"])
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
