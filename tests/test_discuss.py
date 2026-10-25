"""H3/H4/I7: `ccx discuss` on the fake CLIs — roles by vendor, at most three rounds, only points travel, the outcome
and its place on the `ccx ui` page."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import discuss  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402

FAKES = Path(__file__).resolve().parent / "fakes"


class DiscussEnv(Env):
    def setUp(self):
        super().setUp()
        self.env["CCX_GEMINI_BIN"] = str(FAKES / "fake_gemini.py")

    def j(self, *args, env=None, code=0):
        r = self.ccx(*args, env=env)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)


class TestDiscuss(DiscussEnv):
    def test_three_vendors_two_rounds(self):
        out = self.j("discuss", "--with", "codex,claude,gemini", "one queue file or many?",
                     env={**self.env, "FAKE_DISCUSS": "objections,agree"})
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["roles"], {"proposer": "codex", "critic": "claude", "judge": "gemini"})
        self.assertEqual([(t["round"], t["role"]) for t in out["turns"]],
                         [(1, "proposer"), (1, "critic"), (2, "proposer"), (2, "critic"), (2, "judge")])
        self.assertTrue(out["agreed"])
        self.assertTrue(out["judge_independent"])
        r = out["result"]
        self.assertEqual(r["recommendation"], "one queue file with a lock")
        self.assertEqual(r["consensus"], ["one file is simpler"])
        self.assertEqual(r["disagreements"], ["lock vs append-only log"])
        self.assertTrue(r["reasons"])
        prompts = [c["prompt"] for c in self.calls() if "[ccx discuss" in (c.get("prompt") or "")]
        self.assertEqual(len(prompts), 5)
        # the revision sees the objection as a point, not the critic's whole answer
        self.assertIn("- [must] two writers can lose an update", prompts[2])
        self.assertIn("role=judge round=2/3", prompts[4])
        self.assertTrue(all("do not edit anything" in x for x in prompts))
        saved = discuss.load(Paths(self.hub), out["id"])
        self.assertEqual(len(saved["turns"]), 5)

    def test_stops_after_three_rounds_without_agreement(self):
        out = self.j("discuss", "--with", "codex,claude,gemini", "x?", env={**self.env, "FAKE_DISCUSS": "objections"})
        self.assertFalse(out["agreed"])
        self.assertEqual(max(t["round"] for t in out["turns"]), 3)
        self.assertEqual(len(out["turns"]), 7)                    # 3 x (proposer + critic) + judge

    def test_two_vendors_the_proposer_judges(self):
        out = self.j("discuss", "--with", "codex,claude", "--rounds", "1", "x?")
        self.assertEqual(out["roles"]["judge"], "codex")
        self.assertFalse(out["judge_independent"])
        self.assertIn("proposer also judged", out["result"]["note"])

    def test_same_vendor_refused(self):
        self.env["CCX_CONFIG"] = str(self.hub / "user.toml")
        r = self.ccx("discuss", "--with", "codex,codex", "x?")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("same vendor", r.stdout)

    def test_a_failed_turn_keeps_what_was_said(self):
        out = self.j("discuss", "--with", "codex,claude,gemini", "x?", code=1,
                     env={**self.env, "FAKE_DISCUSS_FAIL": "critic"})
        self.assertEqual(out["state"], "failed")
        self.assertIn("critic (claude)", out["error"])
        self.assertEqual([t["role"] for t in out["turns"]], ["proposer"])
        self.assertTrue(out["result"]["recommendation"])          # the last proposal stands, marked as unjudged

    def test_dry_run_runs_nothing(self):
        out = self.j("discuss", "--with", "codex,claude,gemini", "--rounds", "2", "--dry-run", "x?")
        self.assertEqual(out["calls_max"], 5)
        self.assertIsNone(out["usd_max_est"])                     # no read runs recorded yet
        self.assertFalse(any("[ccx discuss" in (c.get("prompt") or "") for c in self.calls()))

    def test_show_list_and_the_page(self):
        out = self.j("discuss", "--with", "codex,claude", "--rounds", "1", "which lock?")
        self.assertEqual(self.j("discuss", "--show", out["id"])["question"], "which lock?")
        self.assertEqual(self.j("discuss", "--list")["discussions"][0]["id"], out["id"])
        from ccx import ui
        data = ui.collect(Paths(self.hub), quota_wait=False)
        self.assertEqual(data["discussions"][0]["id"], out["id"])
        self.assertEqual(data["discussions"][0]["turns"][0]["role"], "proposer")
        # the turns are internal runs: they do not show up as pieces of work
        self.assertFalse(any(pc.get("title", "").startswith("[ccx discuss") for pr in data["projects"]
                             for t in pr["tasks"] for pc in t["pieces"]))


class TestUnits(unittest.TestCase):
    def test_points_are_cut(self):
        s, pts = discuss.points({"summary": "x" * 900, "open_questions": ["[point] " + "y" * 900] * 20})
        self.assertLessEqual(len(s), discuss.SUMMARY_CHARS)
        self.assertLessEqual(len(pts), discuss.MAX_POINTS + 3)
        self.assertTrue(all(len(x) <= discuss.POINT_CHARS for x in pts))

    def test_agrees(self):
        self.assertTrue(discuss.agrees({"summary": "CRITIQUE: agree", "points": ["[note] fine"]}))
        self.assertFalse(discuss.agrees({"summary": "CRITIQUE: agree", "points": ["[must] broken"]}))
        self.assertFalse(discuss.agrees({"summary": "CRITIQUE: objections", "points": []}))

    def test_runner_injection_and_bad_id(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Paths(Path(d))
            calls = []

            def runner(agent, text, label):
                calls.append(agent)
                role = text.split("role=", 1)[1].split()[0]
                summ = {"proposer": "do A", "critic": "CRITIQUE: agree", "judge": "RECOMMEND: A"}[role]
                return {"ok": True, "run_id": "r", "attempts": [{"ae_usd": 0.01, "model": "m"}],
                        "result": {"status": "done", "summary": summ, "open_questions": []}}
            got = discuss.run(p, "A or B?", ["codex", "claude", "gemini"], runner=runner)
            self.assertEqual(calls, ["codex", "claude", "gemini"])
            self.assertEqual(got["result"]["recommendation"], "A")
            self.assertAlmostEqual(got["usd"], 0.03)
            with self.assertRaises(ValueError):
                discuss.load(p, "../x")


if __name__ == "__main__":
    unittest.main()
