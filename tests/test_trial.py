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
        self.assertIn("deferred, no conclusion", s["note"])
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
        self.assertNotEqual(self.ccx("trial", "tag", "--session", "x").returncode, 0)

    def test_native_tag_reads_helpers_and_workflow_agents(self):
        from test_report import iso
        t = self.j("trial", "start", "--days", "7")
        now = time.time()
        self.claude_transcript("nat-1", n=2, ts=now)
        base = self.home_claude / "projects" / "-work" / "nat-1" / "subagents"
        for rel, mid in (("agent-h.jsonl", "h1"), ("workflows/wf_ab12/agent-a1.jsonl", "w1"),
                         ("workflows/wf_ab12/agent-a2.jsonl", "w2")):
            f = base / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({
                "type": "assistant", "isSidechain": True, "sessionId": "nat-1", "timestamp": iso(now + 1),
                "message": {"id": mid, "model": "claude-sonnet-5-5",
                            "usage": {"input_tokens": 100, "cache_read_input_tokens": 5000, "output_tokens": 200}}}),
                encoding="utf-8")
        self.claude_transcript("unrelated", n=3, ts=now)                       # another conversation: not read
        row = self.j("trial", "tag", "--arm", "native", "--session", "nat-1", "--kind", "code", "--b", "4",
                     "--ok", "1")
        self.assertEqual((row["trial"], row["arm"], row["bucket"]), (t["id"], "native", "code:b4"))
        self.assertEqual((row["turns"], row["helper_turns"], row["helpers"], row["workflows"]), (2, 3, 3, 1))
        self.assertEqual(row["sub_tokens"], 3 * 5300)
        self.assertGreater(row["sub_usd"], 0)
        self.assertGreater(row["lead_usd"], 0)
        self.assertNotEqual(self.ccx("trial", "tag", "--session", "nat-1").returncode, 0)   # counted once
        self.assertNotEqual(self.ccx("trial", "tag", "--session", "missing").returncode, 0)
        s = self.j("trial", "report")
        self.assertEqual(s["arms"]["native"]["n"], 1)
        self.assertEqual(s["arms"]["native"]["ok_rate"], 1.0)
        self.assertAlmostEqual(s["arms"]["native"]["total_usd_mean"], row["lead_usd"] + row["sub_usd"], places=4)
        self.assertIn("deferred, no conclusion", s["compare"]["native"]["note"])
        md = self.ccx("trial", "report", "--markdown").stdout
        self.assertIn("Claude Code's own helpers / workflow", md)
        self.assertIn("deferred, no conclusion", md)
        # the usage reader ties workflow agents to their conversation too (window_usage for self-runs)
        from ccx import usage
        evs = [e for e in usage.claude_events(now - 60, set()) if e.get("workflow")]
        self.assertEqual({(e["parent"], e["workflow"]) for e in evs}, {("nat-1", "wf_ab12")})


def _s(arm, bucket, usd):
    return {"arm": arm, "bucket": bucket, "lead_usd": usd, "sub_usd": 0.0}


class TestBalanced(unittest.TestCase):
    def test_compares_within_buckets_only(self):
        ss = ([_s("self", "a", 1.0)] * 3 + [_s("delegated", "a", 0.5)]
              + [_s("self", "b", 2.0)] + [_s("delegated", "b", 1.5)] * 3 + [_s("native", "c", 0.1)])
        d = trial.balanced(ss, "delegated")
        # pooled means would say 1.25 vs 1.25 (no saving); within each bucket it saves 0.5
        self.assertAlmostEqual(d["saving_per_task_usd"], 0.5)
        self.assertEqual((d["n_base"], d["n_arm"], d["left_out"]), (4, 4, 0))
        self.assertFalse(d["enough"])
        self.assertIn("deferred, no conclusion", d["note"])
        n = trial.balanced(ss, "native")
        self.assertIsNone(n["saving_per_task_usd"])            # no bucket shared with the lead's own runs
        self.assertEqual(n["left_out"], 5)

    def test_interval_once_enough(self):
        rng = random.Random(5)
        ss = ([_s("self", "a", 1.0 + rng.uniform(-0.2, 0.2)) for _ in range(12)]
              + [_s("native", "a", 0.6 + rng.uniform(-0.2, 0.2)) for _ in range(12)])
        n = trial.balanced(ss, "native")
        self.assertTrue(n["enough"])
        self.assertNotIn("note", n)
        lo, hi = n["saving_ci95"]
        self.assertLess(lo, n["saving_per_task_usd"])
        self.assertLess(n["saving_per_task_usd"], hi)
        self.assertLess(lo, 0.4)
        self.assertGreater(hi, 0.4)
        self.assertGreater(lo, 0)


class TestNoUltracodeInSubRuns(unittest.TestCase):
    def test_settings_flag_and_effort_env(self):
        import os
        from pathlib import Path
        from ccx.agents.claude import claude_invocation
        from ccx.delegate import _child_env
        inv = claude_invocation(model="m", effort="low", perm=[], cwd=Path("."), prompt="ultracode please",
                                run_dir=Path("."))
        settings = json.loads(inv.argv[inv.argv.index("--settings") + 1])
        self.assertEqual(settings, {"ultracode": False, "workflowKeywordTriggerEnabled": False})
        old = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL")
        os.environ["CLAUDE_CODE_EFFORT_LEVEL"] = "ultracode"
        try:
            self.assertNotIn("CLAUDE_CODE_EFFORT_LEVEL", _child_env("claude", "r1"))
        finally:
            if old is None:
                os.environ.pop("CLAUDE_CODE_EFFORT_LEVEL")
            else:
                os.environ["CLAUDE_CODE_EFFORT_LEVEL"] = old


if __name__ == "__main__":
    unittest.main()
