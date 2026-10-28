"""H13: verdicts without asking — probable verdicts from the evidence, reasons, undo only with --wrong as 'wrong' (fake CLIs only)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_ccx import Env  # noqa: E402


class TestVerdicts(Env):
    def setUp(self):
        super().setUp()
        self.env["FAKE_TOUCH"] = "1"        # each write run changes something (else it is kind no_changes)
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def run_ccx(self, *args, env=None):
        r = self.ccx(*args, env=env)
        self.assertIn(r.returncode, (0, 2), r.stderr + r.stdout)
        return json.loads(r.stdout)

    def events(self):
        led = self.hub / "ccx" / "ledger.jsonl"
        return [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if '"type": "verify"' in x]

    def test_probable_then_overridden(self):
        run = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write", "--review", "off",
                           "--check", "exit 0", "change x")["run_id"]
        self.assertEqual(self.run_ccx("verify", "--sweep")["recorded"], [])          # too recent (12 h)
        got = self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"]
        self.assertEqual([(g["run_id"], g["ok"]) for g in got], [(run, True)])
        self.assertIn("check passed", got[0]["why"])
        self.assertEqual(self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"], [])   # once only
        out = self.run_ccx("verify", run, "--ok", "0", "--reason", "wrong", "--note", "off by one")
        self.assertEqual((out["verdict"], out["reason"]), (False, "wrong"))
        ev = self.events()
        self.assertEqual([(e.get("soft", False), e["ok"]) for e in ev], [(True, True), (False, False)])
        rec = json.loads((self.hub / "ccx" / "runs" / run / "run.json").read_text(encoding="utf-8"))
        self.assertFalse(rec["verdict"].get("soft"))
        summary = self.run_ccx("stats", "--summary")["totals"]
        self.assertEqual((summary["verified"], summary["soft_verified"], summary["reasons"]), (1, 0, {"wrong": 1}))

    def test_dismissed_counts_neither_way_and_is_never_learned(self):
        from unittest import mock
        from ccx import ledger, learn, ui, ways
        from ccx.config import Paths
        p = Paths(self.hub)
        run = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write", "--review", "off",
                           "--check", "exit 0", "--label", "two-way-x2c", "change x")["run_id"]
        real = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write", "--review", "off",
                            "--check", "exit 0", "change y")["run_id"]
        self.assertEqual(ui.waiting(p), 1)                       # a probe label: only the real run waits
        bad = self.ccx("verify", real, "--dismiss", "--ok", "1")
        self.assertNotEqual(bad.returncode, 0)
        out = self.run_ccx("verify", real, "--dismiss", "--note", "a leftover of a test")
        self.assertTrue(out["dismissed"])
        self.assertEqual(ui.waiting(p), 0)
        with mock.patch.object(learn, "record_outcomes") as rec_out:
            from ccx.verdicts import soft_verdicts
            self.assertEqual(soft_verdicts(p, 0), [])            # the sweep skips it: no probable verdict
            rec_out.assert_not_called()
        self.assertEqual(self.events(), [])                      # no verify row: not right, not wrong
        row = ledger.runs_by_id(ledger.rows(p))[real]
        self.assertTrue(row["dismissed"] and ledger.is_eval(row))
        self.assertNotIn(real, [x["run_id"] for x in ways.pieces(p)])
        d = ui.collect(p, quota_wait=False)
        pc = [x for pr in d["projects"] for t in pr["tasks"] for x in ui._walk(t["pieces"]) if x["run_id"] == real][0]
        self.assertTrue(pc["test"] and pc["act"] is None)
        self.run_ccx("verify", real, "--ok", "1")                 # a real verdict later: it counts again
        self.assertFalse(ledger.runs_by_id(ledger.rows(p))[real].get("dismissed"))
        again = self.ccx("verify", real, "--dismiss")             # judged by a person: not dismissed over it
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already has a verdict", again.stdout + again.stderr)
        self.assertTrue(run)

    def test_no_evidence_waits_for_a_person(self):
        self.run_ccx("run", "--to", "claude", "--model", "haiku", "--effort", "low", "--mode", "write",
                     "--review", "off", "change x")              # the fake reports verification: not-run, no --check
        self.assertEqual(self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"], [])

    def test_undo_is_not_a_verdict_unless_wrong(self):
        # A/B question 8: undoing is not a verdict by itself; routing and its samples stay as they were
        state = self.hub / "ccx" / "routing-state.json"
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n"}
        run = self.run_ccx("run", "--to", "codex", "--b", "3", "--mode", "write", "--review", "off",
                           "--check", "exit 0", "change x", env=env)["run_id"]
        before = state.read_bytes()
        out = self.run_ccx("undo", run, "--apply")
        self.assertTrue(out["verdict"].startswith("none"))
        self.assertEqual((self.work / "a.py").read_text(encoding="utf-8"), "x = 1\n")
        self.assertEqual(state.read_bytes(), before)
        self.assertEqual(self.events(), [])
        led = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(e["type"], e["reason"], e["wrong"]) for e in led if e.get("type") == "undo"],
                         [("undo", "undone", False)])
        self.assertEqual(self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"], [])   # waits for a person
        self.assertEqual(state.read_bytes(), before)

        run2 = self.run_ccx("run", "--to", "codex", "--b", "3", "--mode", "write", "--review", "off",
                            "--check", "exit 0", "change x", env=env)["run_id"]
        before = state.read_bytes()
        out = self.run_ccx("undo", run2, "--apply", "--wrong")
        self.assertEqual(out["verdict"], "recorded as wrong (undo --wrong)")
        self.assertNotEqual(state.read_bytes(), before)
        ev = self.events()[-1]
        self.assertEqual((ev["run_id"], ev["ok"], ev.get("soft"), ev["reason"]), (run2, False, None, "wrong"))

    def test_bad_reason(self):
        run = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "read", "look")["run_id"]
        r = self.ccx("verify", run, "--ok", "0", "--reason", "sloppy")
        self.assertNotEqual(r.returncode, 0)

    def test_trust_in_probable_verdicts(self):
        # J7: share of probable verdicts later judged the other way; above 20% of 5+ they stop teaching routing
        from ccx import ledger
        soft = lambda rid, ok=True: {"type": "verify", "run_id": rid, "ok": ok, "soft": True}  # noqa: E731
        hard = lambda rid, ok: {"type": "verify", "run_id": rid, "ok": ok}  # noqa: E731
        rows = [soft("a"), hard("a", True), soft("b"), hard("b", False), soft("c"), {"type": "verify", "run_id": "d",
                "ok": False}, hard("d", True)]
        self.assertEqual(ledger.soft_trust(rows), {"soft": 3, "rechecked": 2, "overturned": 1,
                                                   "overturn_rate": 0.5, "learn": True})   # too few rechecked yet
        many = [x for i in range(5) for x in (soft(f"r{i}"), hard(f"r{i}", i == 0))]
        self.assertFalse(ledger.soft_trust(many)["learn"])                                 # 4 of 5 overturned
        self.assertTrue(ledger.soft_trust(many[:2] * 5)["learn"])                         # all confirmed

    def test_overturned_probable_verdicts_stop_teaching(self):
        import os
        from unittest import mock
        from ccx import delegate, ledger
        from ccx.config import paths
        with mock.patch.dict(os.environ, self.env):
            p = paths()
            for i in range(5):
                ledger.append_event(p, {"type": "verify", "run_id": f"old{i}", "ok": True, "soft": True})
                ledger.append_event(p, {"type": "verify", "run_id": f"old{i}", "ok": False})
            rec = {"run_id": "new1", "ok": True, "result": {"status": "done"}, "route": {"b": 3}}
            (p.runs / "new1").mkdir(parents=True)
            with mock.patch.object(delegate.learn, "record_outcomes") as learned:
                delegate._soft_verdict(p, rec, True, "", "auto")
                learned.assert_not_called()
                self.assertNotEqual(rec.get("learned"), "soft")
                ledger.append_event(p, {"type": "verify", "run_id": "x", "ok": True})   # unrelated: no change
                with mock.patch.object(ledger, "soft_trust", return_value={"learn": True}):
                    delegate._soft_verdict(p, dict(rec, run_id="new1"), True, "", "auto")
                learned.assert_called_once()
        summary = self.run_ccx("stats", "--summary")["totals"]["soft_trust"]
        self.assertEqual((summary["rechecked"], summary["overturned"], summary["learn"]), (5, 5, False))


if __name__ == "__main__":
    unittest.main()
