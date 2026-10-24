"""H13: verdicts without asking — probable verdicts from the evidence, reasons, undo as 'wrong' (fake CLIs only)."""
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

    def test_no_evidence_waits_for_a_person(self):
        self.run_ccx("run", "--to", "claude", "--model", "haiku", "--effort", "low", "--mode", "write",
                     "--review", "off", "change x")              # the fake reports verification: not-run, no --check
        self.assertEqual(self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"], [])

    def test_undo_counts_as_wrong(self):
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n"}
        run = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write", "--review", "off",
                           "change x", env=env)["run_id"]
        out = self.run_ccx("undo", run, "--apply")
        self.assertEqual(out.get("verdict"), "recorded as wrong (undone)")
        self.assertEqual((self.work / "a.py").read_text(encoding="utf-8"), "x = 1\n")
        ev = self.events()[-1]
        self.assertEqual((ev["ok"], ev["soft"], ev["reason"]), (False, True, "undone"))

    def test_bad_reason(self):
        run = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "read", "look")["run_id"]
        r = self.ccx("verify", run, "--ok", "0", "--reason", "sloppy")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
