"""The independent review runs while ccx runs its own check; a failed or broken check drops the review (fakes only)."""
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import Env  # noqa: E402

from ccx import delegate, lanes, ui  # noqa: E402
from ccx.config import Paths  # noqa: E402

# a check that waits (up to 8 s) for the fake reviewer's call to show up in the calls log, then exits with argv[2]
WAITER = """import sys, time
log, code = sys.argv[1], int(sys.argv[2])
end = time.time() + 8
seen = False
while time.time() < end and not seen:
    try:
        seen = "[ccx review" in open(log, encoding="utf-8").read()
    except OSError:
        pass
    time.sleep(0.1)
print("review-seen" if seen else "review-not-seen")
sys.exit(code)
"""


class TestReviewAlongsideCheck(Env):
    def setUp(self):
        super().setUp()
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)
        self.waiter = self.hub / "waiter.py"           # outside the work tree: not part of the reviewed diff
        self.waiter.write_text(WAITER, encoding="utf-8")

    def go(self, code: int, *extra):
        check = f'"{sys.executable}" "{self.waiter}" "{self.log}" {code}'
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}=x = 2\n", "FAKE_REVIEW": "pass"}
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", "--risk", "visible", "--check", check, *extra, "change x to 2 in a.py", env=env)
        self.assertIn(r.returncode, (0, 2), r.stderr)
        out = json.loads(r.stdout)
        rec = json.loads((Paths(self.hub).runs / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        return out, rec

    def reviews(self):
        return [c for c in self.calls() if c["agent"] == "claude" and "[ccx review" in c["prompt"]]

    def test_review_starts_before_the_check_ends_and_counts_when_it_passes(self):
        out, rec = self.go(0)
        self.assertTrue(out["check"]["passed"], out)
        self.assertIn("review-seen", rec["check"]["tail"])          # the reviewer ran while the check waited
        self.assertEqual(out["review"]["verdict"], "pass")
        self.assertIn("passed", self.reviews()[0]["prompt"])

    def test_failed_check_drops_the_review(self):
        out, rec = self.go(1)
        self.assertFalse(out["check"]["passed"], out)
        self.assertIn("review-seen", rec["check"]["tail"])
        self.assertNotIn("review", out)
        self.assertEqual(rec["kind"], "check_failed")
        self.assertNotIn("review", rec)

    def test_review_off_runs_no_review(self):
        out, rec = self.go(0, "--review", "off")
        self.assertIn("review-not-seen", rec["check"]["tail"])
        self.assertNotIn("review", out)
        self.assertEqual(self.reviews(), [])


class TestFinishReview(unittest.TestCase):
    def test_discarded_review_is_stopped_and_dropped(self):
        hub = Path(tempfile.mkdtemp())
        p = Paths(hub)
        p.runs.mkdir(parents=True, exist_ok=True)
        d = p.runs / "20990101-000000-rev1"
        d.mkdir()
        (d / "run.json").write_text(json.dumps({"run_id": d.name, "label": "review:r1", "state": "running"}),
                                    encoding="utf-8")
        shadow, cancel = {"run_id": "r1"}, threading.Event()

        def reviewer():                       # stands in for a review run: ends once asked to stop
            while not (d / "stop.request").exists():
                time.sleep(0.05)
            shadow["review"] = {"verdict": "issues", "issues": ["x"]}
            shadow["kind"] = "review_issues"

        t = threading.Thread(target=reviewer, daemon=True)
        t.start()
        record = {"run_id": "r1", "kind": "check_failed"}
        delegate._finish_review({"thread": t, "cancel": cancel, "shadow": shadow, "run_id": "r1"}, record, p,
                                keep=False, wait=10)
        self.assertFalse(t.is_alive())
        self.assertTrue(cancel.is_set())
        self.assertEqual(record, {"run_id": "r1", "kind": "check_failed"})

    def test_kept_review_is_merged(self):
        shadow = {"review": {"verdict": "issues"}, "kind": "review_issues", "edited_tests": ["t.py"]}
        t = threading.Thread(target=lambda: None)
        t.start()
        record = {"kind": None}
        delegate._finish_review({"thread": t, "cancel": threading.Event(), "shadow": shadow, "run_id": "r"},
                                record, Paths(Path(tempfile.mkdtemp())), keep=True)
        self.assertEqual(record, {"kind": "review_issues", "review": {"verdict": "issues"},
                                  "edited_tests": ["t.py"]})


class TestCheckBrokenShown(unittest.TestCase):
    def test_check_broken_ends_a_lane_and_has_a_card(self):
        self.assertIn("check_broken", lanes.BAD_KINDS)
        strings = json.loads((Path(ui.__file__).parent / "ui_static" / "strings.json").read_text(encoding="utf-8"))
        langs = [v for v in strings.values() if isinstance(v, dict)] or [strings]
        for s in langs:
            for k in ("a_check_broken", "w_check_broken", "h_check_broken"):
                self.assertIn(k, s)
        rec = {"run_id": "r1", "kind": "check_broken", "state": "finished", "ok": True, "cwd": "/w",
               "result": {"status": "done"}, "check": {"cmd": "pytest x", "exit": 4, "broken": "usage error"}}
        act = ui._act(rec, None, time.time(), None)
        self.assertEqual((act["kind"], act["what"]), ("decide", "a_check_broken"))
        self.assertEqual(act["why"], ["w_check_broken", {"cmd": "pytest x", "why": "usage error"}])


if __name__ == "__main__":
    unittest.main()
