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
        self.env["FAKE_TOUCH"] = "1"        # each write run changes something (else it is kind no_changes)
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


class TestWeekly(unittest.TestCase):
    """H14: where it was wrong, this week next to last week."""
    NOW = 1_800_000_000.0

    def piece(self, days_ago, ok, tier="luna:low", kind="code", p=None, attempts=1, rework=False, judged=True):
        return {"agent": "codex", "tier": tier, "kind": kind, "judged": judged, "ok": ok, "rework": rework or not ok,
                "p": p, "attempts": attempts, "ts": self.NOW - days_ago * 86400}

    def test_tiers_by_week(self):
        from ccx import accuracy
        pcs = [self.piece(1, True), self.piece(2, False), self.piece(3, True, rework=True), self.piece(9, False),
               self.piece(1, True, tier="gpt-6:high"), self.piece(1, True, judged=False), self.piece(20, False)]
        t = {(x["tier"], x["kind"]): x for x in accuracy.tiers(pcs, self.NOW)}
        self.assertEqual(t[("luna:low", "code")]["this"], {"judged": 3, "wrong": 0.333, "rework": 0.667})
        self.assertEqual(t[("luna:low", "code")]["last"], {"judged": 1, "wrong": 1.0, "rework": 1.0})
        self.assertEqual(t[("gpt-6:high", "code")]["last"], {"judged": 0, "wrong": None, "rework": None})

    def test_brier_and_bins(self):
        from ccx import accuracy
        pcs = [self.piece(1, True, p=0.9), self.piece(1, False, p=0.6), self.piece(1, True, p=0.6, attempts=2),
               self.piece(8, True, p=0.99), self.piece(1, True)]                 # no p: not counted
        c = accuracy.calibration(pcs, self.NOW)
        # this week: (0.9-1)^2 + (0.6-0)^2 + (0.6-0)^2 (escalated: the picked rung did not do it) over 3
        self.assertEqual((c["this"]["n"], c["this"]["brier"]), (3, round((0.01 + 0.36 + 0.36) / 3, 4)))
        self.assertEqual([(b["bin"], b["n"], b["actual"]) for b in c["this"]["bins"]],
                         [("0.50-0.70", 2, 0.0), ("0.85-0.95", 1, 1.0)])
        self.assertEqual((c["last"]["n"], c["last"]["bins"][0]["bin"]), (1, "0.95-1.00"))

    def test_soft_overturned_by_week_without_evals(self):
        from ccx import accuracy
        ts = lambda d: self.NOW - d * 86400  # noqa: E731
        rows = [{"run_id": "a", "label": "x"}, {"run_id": "b", "label": "x"}, {"run_id": "e", "label": "eval-1"},
                {"type": "verify", "run_id": "a", "ok": True, "soft": True, "ts": ts(3)},
                {"type": "verify", "run_id": "a", "ok": False, "ts": ts(2)},
                {"type": "verify", "run_id": "b", "ok": True, "soft": True, "ts": ts(10)},
                {"type": "verify", "run_id": "b", "ok": True, "ts": ts(9)},
                {"type": "verify", "run_id": "e", "ok": True, "soft": True, "ts": ts(3)},
                {"type": "verify", "run_id": "e", "ok": False, "ts": ts(2)}]
        o = accuracy.overturned(rows, self.NOW)
        self.assertEqual(o["this"], {"rechecked": 1, "overturned": 1, "rate": 1.0})
        self.assertEqual(o["last"], {"rechecked": 1, "overturned": 0, "rate": 0.0})
        self.assertEqual(accuracy.overturned(rows, self.NOW, include_evals=True)["this"]["rechecked"], 2)

    def test_card(self):
        from ccx import accuracy
        acc = {"tiers": accuracy.tiers([self.piece(1, False)], self.NOW),
               "calibration": accuracy.calibration([self.piece(1, True, p=0.8)], self.NOW),
               "soft": {"this": {"rechecked": 0, "overturned": 0, "rate": None},
                        "last": {"rechecked": 0, "overturned": 0, "rate": None}},
               "checks": {"judged": 0, "wrong": 0, "weak": []}, "evals": False}
        h = accuracy.card_html(acc)
        self.assertIn("this week vs last week", h)
        self.assertIn("luna:low", h)
        self.assertIn("Brier", h)
        self.assertIn("--include-evals", h)


class TestDoctorPrior(Env):
    def test_doctor_names_where_routing_starts(self):
        line = lambda: next(x for x in self.ccx("doctor").stdout.splitlines() if x.startswith("routing prior"))  # noqa: E731
        first = line()
        self.assertIn("seven-cores A/B round 1", first)
        self.assertIn("codex:gpt-6-luna:low +", first)
        self.assertNotIn("learned here since", first)
        (self.hub / "ccx").mkdir(exist_ok=True)
        (self.hub / "ccx" / "routing-state.json").write_text(json.dumps(
            {"offsets": {"codex:gpt-6-luna:low": 0.1}, "counts": {"codex:gpt-6-luna:low": 1}, "outcomes": []}),
            encoding="utf-8")
        self.assertRegex(line(), r"codex:gpt-6-luna:low \+[0-9.]+ \(learned here since\)")


if __name__ == "__main__":
    unittest.main()
