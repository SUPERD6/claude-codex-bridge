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
        # round 5: [must] only with a basis in the task or a broken existing behaviour; the rest is a note
        self.assertIn('`[must] file:line — "task words" — what is wrong` is only for', b)
        self.assertIn("quoting the task sentence it rests on", b)
        self.assertIn("existing tests, or crashes on inputs the task itself names", b)
        self.assertIn("A [must] without such a basis is treated as a note", b)
        self.assertIn("hardening, extra validation, edge cases or robustness the task did not ask for", b)

    def test_out_of_scope_must_is_a_note(self):
        for item in ("[must] (out of scope) run.json may be missing", "[must] Hardening: corrupt JSON crashes load()",
                     "[must] — not asked for: make it idempotent", "[MUST] [beyond the task] retry on EOF",
                     "  [must] robustness — no guard for empty files"):
            v = review.verdict({"summary": "REVIEW: issues", "open_questions": [item]})
            self.assertEqual((v["verdict"], v["issues"]), ("pass", []), item)
            self.assertTrue(v["notes"][0].startswith("[note]"), v)
        # a real [must] next to an out-of-scope one still triggers the fix round, with only the real one
        v = review.verdict({"summary": "REVIEW: issues", "open_questions": [
            "[must] (out of scope) no lock", '[must] a.py:3 — "return the SKUs" — returns Item objects']})
        self.assertEqual((v["verdict"], len(v["issues"])), ("issues", 1))
        self.assertIn("SKUs", v["issues"][0])
        # words like "robustness" later in a real item do not demote it
        v = review.verdict({"summary": "REVIEW: issues", "open_questions": [
            '[must] a.py:3 — "raise ValueError for n < 1" — no robustness check, n=0 passes']})
        self.assertEqual(v["verdict"], "issues")

    def test_at_most_one_fix_round(self):
        self.assertEqual([review.fix_rounds({"fix_rounds": n}) for n in (0, 1, 2, 5, "x")], [0, 1, 1, 1, 1])
        self.assertEqual(review.fix_rounds({}), 1)

    def test_fix_round_is_reviewed_against_the_first_task(self):
        import tempfile
        from ccx.config import Paths
        from ccx.delegate import Request
        with tempfile.TemporaryDirectory() as d:
            p = Paths(Path(d))
            (p.runs / "r0").mkdir(parents=True)
            (p.runs / "r0" / "brief.md").write_text("change x to 2", encoding="utf-8")
            (p.runs / "r1").mkdir()                                 # a resume of r0: no brief.md of its own
            (p.runs / "r1" / "run.json").write_text(json.dumps({"resumed_from": "r0"}), encoding="utf-8")
            fix = Request(to="codex", brief="An independent review found ...", resume_run="r1", review_round=1)
            self.assertEqual(review.task_for_review(p, fix), "change x to 2")
            plain = Request(to="codex", brief="follow-up", resume_run="r1")      # not a fix round: its own brief
            self.assertEqual(review.task_for_review(p, plain), "follow-up")
            lost = Request(to="codex", brief="issues", resume_run="gone", review_round=1)
            self.assertEqual(review.task_for_review(p, lost), "issues")

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

    def test_verdict_without_the_review_line(self):
        # round 2 of the seven-cores A/B: haiku wrote its summary in Chinese and named the real bug as [must]
        zh = review.verdict({"summary": "检查了三项要求：low_stock 返回的是 Item 对象", "open_questions":
                             ["[must] inventory/report.py:1-3 — returns Item objects, the task asks for SKUs",
                              "[note] no test for remove_stock"]})
        self.assertEqual((zh["verdict"], zh["format"], len(zh["issues"])), ("issues", "lenient", 1))
        ok = review.verdict({"summary": "都符合要求", "open_questions": ["[note] style"]})
        self.assertEqual((ok["verdict"], ok["format"]), ("pass", "lenient"))
        self.assertEqual(review.verdict({"summary": "**REVIEW：issues** x", "open_questions": ["[must] a"]})["verdict"],
                         "issues")
        self.assertEqual(review.verdict({"summary": "`REVIEW: pass`"})["verdict"], "pass")
        self.assertEqual(review.verdict({"summary": "no idea", "open_questions": ["something"]})["verdict"], "unclear")
        self.assertEqual(review.verdict({"summary": "REVIEW: passing thoughts"})["verdict"], "unclear")

    def test_brief_rubric_traces_the_normal_path(self):
        b = review.brief("r1", "task", "did it", "+x", 100)
        self.assertIn("fails on its normal path, even silently", b)
        self.assertIn("a name used but not defined or imported in that scope", b)
        self.assertIn("`except Exception: pass`", b)
        self.assertIn("only works\nfrom the repo directory", b)
        self.assertIn("trace the entry point the task names", b)
        self.assertNotIn("Existing tests edited", b)

    def test_edited_tests(self):
        diff = ("diff --git a/tests/test_old.py b/tests/test_old.py\n--- a/tests/test_old.py\n+++ b/tests/test_old.py\n"
                "@@ -1,2 +1,2 @@\n def test_x():\n-    assert f() == 1\n+    assert f() == 2\n"
                "--- a/tests/test_more.py\n+++ b/tests/test_more.py\n@@ -3,0 +4,2 @@\n+def test_y():\n+    pass\n"
                "--- /dev/null\n+++ b/tests/test_new.py\n@@ -0,0 +1 @@\n+def test_z(): pass\n"
                "--- a/src/lib.py\n+++ b/src/lib.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
                "--- a/test_gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-def test_g(): pass\n")
        self.assertEqual(review.edited_tests(diff), ["tests/test_old.py", "test_gone.py"])
        self.assertEqual(review.edited_tests(""), [])
        b = review.brief("r1", "task", "did it", diff, 100_000)
        self.assertIn("Existing tests edited: tests/test_old.py, test_gone.py — check the task requires it", b)

    def test_edited_tests_are_weak_evidence_past_the_cap(self):
        from ccx.config import Paths
        import tempfile
        p = Paths(Path(tempfile.mkdtemp()))
        rec = {"run_id": "r", "check": {"cmd": "python -m pytest", "passed": True}}
        rc = {"weak_daily": 0}
        self.assertEqual(review.weak_reason(p, rc, rec, edited=["tests/test_a.py"]),
                         "existing tests edited: tests/test_a.py")
        self.assertIsNone(review.weak_reason(p, {"weak": False}, rec, edited=["tests/test_a.py"]))

    def test_brief_says_what_ccx_ran(self):
        b = review.brief("r1", "task", "did it", "+x", 100, {"cmd": "make test", "passed": True, "exit": 0})
        self.assertIn("`make test` after the change: passed", b)
        self.assertIn("cannot run commands", b)


STORE = "class Store:\n    def get(self, k):\n        return 1\n\n    def remove(self, k, n):\n        return n\n"


class TestCheckGap(unittest.TestCase):
    """H13 without history: is a passed acceptance command evidence for *this* change?"""
    START = {"inv/__init__.py": "", "inv/store.py": STORE, "inv/report.py": "def summary(s):\n    return {}\n",
             "tests/test_inv.py": "from inv.report import summary\n\n\ndef test_s():\n    assert summary(None) == {}\n"}

    def change(self, files: dict) -> tuple[Path, list[str], str]:
        import tempfile
        d = Path(tempfile.mkdtemp())
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        for f, c in self.START.items():
            (d / f).parent.mkdir(parents=True, exist_ok=True)
            (d / f).write_text(c, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run([*g, "commit", "-qm", "i"], cwd=d, check=True)
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        for f, c in files.items():
            (d / f).write_text(c, encoding="utf-8")
        actual, diff = review.changes(d, {"base": base, "untracked": [], "repo": str(d)})
        return d, actual, diff

    def test_commands_that_run_no_tests(self):
        for cmd in ("exit 0", "ruff check .", 'python -c "import inv"', "flake8", "mypy ."):
            self.assertIn("runs no tests", review.check_gap(cmd, Path("."), ["a.py"], ""), cmd)
        for cmd in ("python -m pytest -q", "npm test", "go test ./...", "cargo test", "python -m unittest",
                    "python tests/test_inv.py", "make check", "pnpm run test"):
            self.assertIsNotNone(review._TEST_CMD.search(cmd), cmd)

    def test_tests_that_miss_the_change(self):
        # like r2's inventory: the visible test imports the package but never calls what changed
        d, actual, diff = self.change({"inv/store.py": STORE.replace("        return n\n",
                                                                     "        if n < 1:\n            raise ValueError(n)\n"
                                                                     "        return n\n")})
        self.assertEqual(review.check_gap("python -m pytest -q", d, actual, diff),
                         "the tests it runs don't touch inv/store.py (never named)")
        d, actual, diff = self.change({"inv/report.py": "def summary(s):\n    return {}\n\n\ndef low(s):\n    return []\n"})
        self.assertEqual(review.check_gap("python -m pytest -q", d, actual, diff),
                         "the tests it runs don't touch inv/report.py: low")

    def test_tests_that_reach_the_change_are_strong(self):
        test = "from inv.report import summary\n\n\ndef test_s():\n    assert summary(None) == {'n': 0}\n"
        d, actual, diff = self.change({"inv/report.py": "def summary(s):\n    return {'n': 0}\n",
                                       "tests/test_inv.py": test})
        self.assertIsNone(review.check_gap("python -m pytest -q", d, actual, diff))
        self.assertIsNone(review.check_gap("python -m pytest -q", d, ["README.md"], ""))   # no code changed

    def test_only_the_named_tests_count(self):
        d, actual, diff = self.change({"inv/report.py": "def summary(s):\n    return {'n': 0}\n"})
        (d / "tests" / "test_other.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        self.assertIn("report.py", review.check_gap("python -m pytest tests/test_other.py", d, actual, diff))
        self.assertIsNone(review.check_gap("python -m pytest tests/test_inv.py", d, actual, diff))

    def test_changed_symbols(self):
        src = ("class A:\n    def f(self):\n        x = 1\n\n        return x\n\n    def _g(self):\n        pass\n"
               "\n\ndef h():\n    pass\nY = 2\n")
        self.assertEqual(review.changed_symbols(src, [3]), ["f"])
        self.assertEqual(review.changed_symbols(src, [8]), [])                 # a private helper: not asked for
        self.assertEqual(review.changed_symbols(src, [11, 12, 13]), ["h"])     # Y = 2 is module level
        self.assertEqual(review.changed_symbols(src, [1]), ["A"])


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

    def test_strong_check_not_reviewed(self):
        # a passed acceptance command that runs a test naming the changed file: strong evidence, no review
        (self.work / "test_a.py").write_text("import a\nassert a.x == 2\n", encoding="utf-8")
        out = self.go("--check", f'"{sys.executable}" test_a.py')
        self.assertTrue(out["check"]["passed"], out)
        self.assertNotIn("review", out)
        self.assertEqual(self.reviews(), [])

    def test_edited_existing_test_forces_a_review(self):
        # round 5: the builder rewrote an existing test's assertion; the check then passed and nothing was reviewed
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        (self.work / "test_a.py").write_text("import a\nassert a.x == 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "test_a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "test"], cwd=self.work, check=True)
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n;{self.work / 'test_a.py'}=import a\nassert a.x == 2\n",
               "FAKE_REVIEW": "pass"}
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", "--check", f'"{sys.executable}" test_a.py', "change x to 2 in a.py", env=env)
        out = json.loads(r.stdout)
        self.assertTrue(out["check"]["passed"], out)
        self.assertEqual(out["review"]["reason"], "existing tests edited: test_a.py")
        # kept in run.json; the run's printed summary shows it once delegate.py passes the field through
        from ccx.config import Paths
        rec = json.loads((Paths(self.hub).runs / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["review"]["edited_tests"], ["test_a.py"])
        self.assertIn("Existing tests edited: test_a.py", self.reviews()[0]["prompt"])

    def test_check_without_tests_is_reviewed_with_no_history(self):
        # seven-cores r2: `--review auto` never fired in 36 runs because weak evidence needed history; a fresh hub
        # and a check that runs no tests now get one review, on the other vendor's cheapest rung only
        out = self.go("--check", "exit 0")
        self.assertEqual((out["review"]["reason"], out["review"]["by"]),
                         ("the acceptance command `exit 0` runs no tests", "claude:haiku:low"))
        self.assertEqual(len(self.reviews()), 1)

    def test_read_only_run_not_reviewed(self):
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "read",
                     "--no-fallback", "look at a.py", env={"FAKE_REVIEW": "pass"})
        self.assertNotIn("review", json.loads(r.stdout))
        self.assertEqual(self.reviews(), [])

    def test_weak_evidence_gets_one_cheap_review(self):
        # H13: no acceptance command, only the sub-agent's own check -> one review by the cheapest other-vendor rung
        out = self.go()
        self.assertEqual((out["review"]["verdict"], out["review"]["reason"], out["review"]["by"]),
                         ("pass", "only the sub-agent's own check", "claude:haiku:low"))
        self.assertEqual(len(self.reviews()), 1)
        self.assertNotIn("review", self.go("--review", "off"))           # --review off still means off

    def test_weak_check_is_reviewed(self):
        reset = lambda: (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")  # noqa: E731
        for _ in range(3):                                                # the same check passed wrong work 3 times
            rid = self.go("--check", "exit 0")["run_id"]
            self.assertEqual(self.ccx("verify", rid, "--ok", "0").returncode, 0)
            reset()
        out = self.go("--check", "exit 0")
        self.assertEqual(out["check"]["weak"], "3/3 passed but judged wrong")
        self.assertTrue(out["review"]["reason"].startswith("weak check"))

    def test_weak_reviews_are_capped_and_can_be_switched_off(self):
        from ccx.config import Paths
        p = Paths(self.hub)
        rec = {"run_id": "r", "result": {"verification": "ran pytest"}}
        self.assertEqual(review.weak_reason(p, {"weak": False}, rec), None)
        self.assertEqual(review.weak_reason(p, {"weak": False}, {"run_id": "r"}), None)
        self.assertEqual(review.weak_reason(p, {}, {"run_id": "r", "result": {"verification": "not-run"}}),
                         "no acceptance command")
        self.assertEqual(review.weak_reason(p, {}, {**rec, "check": {"passed": True}}), None)   # nothing to judge with
        rc = {"weak_daily": 3}                                   # the "no acceptance command" one above counts
        self.assertEqual([review.weak_reason(p, rc, rec) is not None for _ in range(3)], [True, True, False])

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
        self.assertIn("did not ask for", fix[-1]["prompt"])
        # the fix is judged against the task, not against the issue list it was handed
        task = rv[1]["prompt"].split("## The task it was given", 1)[1].split("## What it says it did", 1)[0]
        self.assertIn("change x to 2 in a.py", task)
        self.assertNotIn("off by one", task)

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
