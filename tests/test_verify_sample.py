"""J7 spot checks: `ccx verify --sample N` picks probable verdicts of this week for the person (fake CLIs only)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import ledger, verdicts  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402


class TestVerifySample(Env):
    def setUp(self):
        super().setUp()
        self.env["FAKE_TOUCH"] = "1"        # each write run changes something (else it is kind no_changes)
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def run_ccx(self, *args):
        r = self.ccx(*args)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return json.loads(r.stdout)

    def test_sample_then_answer(self):
        runs = [self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write", "--review", "off",
                             "--check", "exit 0", "--label", label, f"change x {i}")["run_id"]
                for i, label in enumerate(("a", "b", "c", "eval-x"))]
        got = {g["run_id"] for g in self.run_ccx("verify", "--sweep", "--after-h", "0")["recorded"]}
        self.assertEqual(got, set(runs))
        self.run_ccx("verify", runs[0], "--ok", "1")                     # judged by the lead since: not sampled
        p = Paths(self.hub)
        picks = verdicts.sample_soft(p, 5, seed=1)
        self.assertEqual(sorted(x["run_id"] for x in picks), sorted(runs[1:3]))      # no eval run by default
        self.assertEqual(len(verdicts.sample_soft(p, 5, include_evals=True)), 3)
        self.assertEqual(len(verdicts.sample_soft(p, 1)), 1)
        x = picks[0]
        self.assertEqual((x["probable"], x["check"]), ("right", "exit 0: passed"))
        self.assertIn("check passed", x["why"])

        answers = iter(["maybe", "w", "o"])                               # a bad answer is asked again
        shown = []
        done = verdicts.review_sample(p, picks, ask=lambda _: next(answers), show=shown.append)
        self.assertEqual([(d["ok"], d["overturned"]) for d in done], [(False, True), (True, False)])
        self.assertTrue(any(x["run_id"] in s for s in shown))
        self.assertEqual(verdicts.sample_soft(p, 5), [])                  # answered: nothing left this week
        st = ledger.soft_trust(ledger.rows(p))
        self.assertEqual((st["rechecked"], st["overturned"]), (3, 1))     # runs[0] by the lead, two spot checks

    def test_cli_lists_without_a_terminal_and_stops_at_eof(self):
        run = self.run_ccx("run", "--to", "codex", "--tier", "T1", "--mode", "write", "--review", "off",
                           "--check", "exit 0", "change x")["run_id"]
        self.run_ccx("verify", "--sweep", "--after-h", "0")
        out = self.run_ccx("verify", "--sample", "5", "--list")
        self.assertEqual([x["run_id"] for x in out["sample"]], [run])
        self.assertEqual(verdicts.review_sample(Paths(self.hub), out["sample"], ask=lambda _: (_ for _ in ()).throw(
            EOFError()), show=lambda _: None), [])                       # nobody answers: nothing recorded
        self.assertEqual(self.run_ccx("verify", "--sample", "5", "--list")["sample"][0]["run_id"], run)


if __name__ == "__main__":
    unittest.main()
