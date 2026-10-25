"""Core 6 ("more accurate with use") without wrong signals: which runs are evaluations (fake CLIs only)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import ledger  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestIsEval(unittest.TestCase):
    def test_labels_no_ab_and_probes(self):
        self.assertTrue(ledger.is_eval({"label": "eval-7c:r1:x"}))
        self.assertTrue(ledger.is_eval({"label": "selftest-claude"}))
        self.assertTrue(ledger.is_eval({"label": "quota-probe"}))
        self.assertTrue(ledger.is_eval({"label": "fix x", "no_ab": True}))
        self.assertFalse(ledger.is_eval({"label": "fix eval-ish thing"}))
        self.assertFalse(ledger.is_eval({"label": None}))
        self.assertFalse(ledger.is_eval({}))

    def test_verdict_rows_follow_their_run(self):
        rows = [{"run_id": "a", "label": "eval-x"}, {"run_id": "b", "label": "real"},
                {"run_id": "c", "label": "real", "no_ab": True},
                {"type": "verify", "run_id": "a"}, {"type": "verify", "run_id": "b"},
                {"type": "verify", "run_id": "c"}, {"type": "verify", "run_id": "gone"}]
        runs = ledger.runs_by_id(rows)
        self.assertEqual(sorted(runs), ["a", "b", "c"])
        self.assertEqual([ledger.is_eval(r, runs) for r in rows[3:]], [True, False, True, False])
        self.assertFalse(ledger.is_eval(rows[3]))          # without the runs a verdict row has no label


class TestNoAbInLedger(Env):
    def test_no_ab_run_is_marked(self):
        for extra in ([], ["--no-ab"]):
            r = self.ccx("run", "--to", "codex", "--b", "2", "--mode", "read", "--kind", "read", "--review", "off",
                         *extra, "look at x")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        led = self.hub / "ccx" / "ledger.jsonl"
        runs = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines()]
        runs = [x for x in runs if not x.get("type")]
        self.assertEqual([ledger.is_eval(x) for x in runs], [False, True])


class TestCheckTrust(unittest.TestCase):
    def test_key_is_command_and_place(self):
        k = lambda cmd, cwd: ledger.check_key(cmd, cwd)[0]  # noqa: E731
        self.assertEqual(k("pytest  -q", "/t/x/review-1-inv"), k("pytest -q", "C:\\T\\y\\review-2-inv"))
        self.assertNotEqual(k("pytest -q", "/t/review-1-inv"), k("pytest -q", "/t/review-1-lru"))
        self.assertNotEqual(k("pytest -q", "/t/app"), k("pytest -q tests/a.py", "/t/app"))
        self.assertEqual(ledger.check_key("x", "/w/.ccx-worktrees/app/20261024-abc")[2], "app")

    def test_rate_and_threshold(self):
        def run(rid, place, passed=True):
            return {"run_id": rid, "cwd": f"/t/{place}", "check": {"key": ledger.check_key("t", f"/t/{place}")[0],
                                                                    "cmd": "t", "passed": passed}}
        v = lambda rid, ok, soft=False: {"type": "verify", "run_id": rid, "ok": ok, "soft": soft}  # noqa: E731
        rows = [run("a", "inv"), run("b", "inv"), run("c", "inv"), run("d", "lru"), run("e", "lru"),
                run("f", "inv", passed=False), run("g", "lru"),
                v("a", True), v("a", False), v("b", False), v("c", True), v("f", False),   # the last verdict wins
                v("d", False), v("e", True), v("g", False, soft=True)]                    # probable ones don't count
        t = {g["place"]: g for g in ledger.check_trust(rows).values()}
        self.assertEqual((t["inv"]["judged"], t["inv"]["wrong"], t["inv"]["weak"]), (3, 2, True))
        self.assertEqual(sorted(t["inv"]["runs"]), ["a", "b"])
        self.assertEqual((t["lru"]["judged"], t["lru"]["wrong"], t["lru"]["weak"]), (2, 1, False))   # too few


class TestWeakCheck(Env):
    def setUp(self):
        super().setUp()
        import subprocess
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def run_ccx(self, *args):
        r = self.ccx(*args)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return json.loads(r.stdout)

    def test_a_check_that_let_wrong_work_through_is_no_evidence(self):
        go = lambda: self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write",  # noqa: E731
                                  "--review", "off", "--check", "exit 0", "change x")
        for _ in range(2):
            self.run_ccx("verify", go()["run_id"], "--ok", "0", "--reason", "wrong")
        out = go()
        self.assertNotIn("weak", out["check"])                       # 2 judged: too few to tell
        self.run_ccx("verify", out["run_id"], "--ok", "0", "--reason", "wrong")
        out = go()
        self.assertEqual(out["check"]["weak"], "3/3 passed but judged wrong")
        self.assertIn("let wrong work through", out["check"]["note"])
        self.assertEqual(self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"], [])   # waits for a person
        from ccx import accuracy
        from ccx.config import Paths
        weak = accuracy.summary(Paths(self.hub))["checks"]["weak"]
        self.assertEqual([(w["cmd"], w["wrong"], w["judged"]) for w in weak], [("exit 0", 3, 3)])


if __name__ == "__main__":
    unittest.main()
