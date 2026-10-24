"""H11: a formal week-long comparison — balanced halves, both measured the same way (fake CLIs and transcripts)."""
import json
import random
import time
import unittest

from ccx import trial
from ccx.config import Paths
from test_report import ReportEnv


class TestAssign(unittest.TestCase):
    def test_keeps_each_bucket_near_the_split(self):
        t = {"id": "t", "rate": 0.5}
        counts = {"self": 0, "delegated": 0}
        orig = trial._counts
        trial._counts = lambda p, t: {trial.bucket("code", 4): dict(counts)}
        try:
            rng = random.Random(3)
            for _ in range(40):
                counts[trial.assign(None, t, "code", 4, rng)] += 1
                self.assertLessEqual(abs(counts["self"] - counts["delegated"]), 1)
        finally:
            trial._counts = orig
        self.assertEqual(counts["self"] + counts["delegated"], 40)


class TestTrial(ReportEnv):
    def test_start_route_both_halves_and_report(self):
        p = Paths(self.hub)
        t = self.j("trial", "start", "--days", "7", "--note", "first week")
        self.assertEqual(t["rate"], 0.5)
        self.assertEqual(self.ccx("trial", "start").returncode != 0, True)          # one at a time
        env = {"CLAUDE_CODE_SESSION_ID": "lead-1"}
        arms = {"self": 0, "delegated": 0}
        for i in range(6):
            out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "--kind", "code",
                         f"implement thing {i}", env=env)
            if out.get("delegated") is False:
                arms["self"] += 1
                self.assertIn("trial-", out["advice"])
                self.claude_transcript("lead-1", ts=time.time())
                self.claude_transcript("other-lead", ts=time.time())        # another conversation: not counted
                row = self.j("ab", "done", out["route"]["ab"], "--ok", "1", env=env)
                self.assertEqual(row["trial"], t["id"])
                self.assertEqual(row["messages"], 2)
            else:
                arms["delegated"] += 1
                self.assertEqual(out["route"]["trial"], t["id"])
        self.assertEqual(arms, {"self": 3, "delegated": 3})                 # balanced within the bucket
        # the lead's own built-in helper counts with its conversation (usage events carry the parent)
        from ccx import usage
        sub = self.home_claude / "projects" / "-work" / "lead-1" / "subagents"
        sub.mkdir(parents=True)
        from test_report import iso
        (sub / "agent-x.jsonl").write_text(json.dumps({
            "type": "assistant", "isSidechain": True, "sessionId": "lead-1", "timestamp": iso(time.time()),
            "message": {"id": "h1", "model": "claude-haiku-5-5", "usage": {"input_tokens": 7, "output_tokens": 3}}}),
            encoding="utf-8")
        w = usage.window_usage("claude", time.time() - 60, time.time() + 5, set(), "lead-1")
        self.assertEqual(w["messages"], 3, usage.claude_events(time.time() - 60, set()))  # lead-1 (2 messages) + its helper
        self.assertTrue(any(e.get("parent") == "lead-1" for e in usage.claude_events(time.time() - 60, set())))
        s = self.j("trial", "report")
        self.assertEqual(s["arms"]["self"]["n"], 3)
        self.assertEqual(s["arms"]["delegated"]["n"], 3)
        self.assertGreater(s["arms"]["self"]["lead_usd_mean"], 0)
        self.assertGreater(s["arms"]["delegated"]["sub_usd_mean"], 0)
        self.assertFalse(s["enough"])
        self.assertIn("not a result yet", s["note"])
        md = self.ccx("trial", "report", "--markdown").stdout
        self.assertIn("| Lead spend per task |", md)
        self.j("report", "--no-lead")
        summ = json.loads((self.hub / "ccx" / "report" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summ["trial"]["arms"]["self"]["n"], 3)
        html = (self.hub / "ccx" / "report" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Formal comparison", html)
        self.assertIsNotNone(self.j("trial", "stop")["stopped"])
        self.assertIsNone(trial.active(p))
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "after", env=env)
        self.assertNotIn("trial", out.get("route", {}))                     # stopped: back to normal

    def test_no_trial(self):
        self.assertIsNone(self.j("trial", "report")["trial"])


if __name__ == "__main__":
    unittest.main()
