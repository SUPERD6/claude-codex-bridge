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
        self.assertGreater(out["usd_max_est"], out["usd_min_est"])   # modelled: no discuss turns recorded yet
        self.assertEqual(out["models"]["claude"], "sonnet medium")    # auto, no quota readings: T2
        self.assertEqual(set(out["tier_why"]), {"codex", "claude", "gemini"})
        t1 = self.j("discuss", "--with", "codex,claude", "--tier", "T1", "--dry-run", "x?")
        self.assertEqual(t1["models"], {"codex": "gpt-6-luna low", "claude": "haiku low"})
        self.assertNotIn("tier_why", t1)
        self.assertFalse(any("[ccx discuss" in (c.get("prompt") or "") for c in self.calls()))

    def test_a_lead_needs_the_persons_yes(self):
        for env in ({"CLAUDECODE": "1"}, {"CODEX_THREAD_ID": "t"}, {"CCX_DEPTH": "1"}):
            out = self.j("discuss", "--with", "codex,claude", "--from", "user", "x?", env={**self.env, **env})
            self.assertFalse(out["ran"], env)                     # --from user does not count as the person
            self.assertIn("--confirmed", out["next"])
            self.assertIsNotNone(out["usd_max_est"])
        self.assertEqual(self.discuss_prompts(), [])
        out = self.j("discuss", "--with", "codex,claude", "--rounds", "1", "--confirmed", "x?",
                     env={**self.env, "CLAUDECODE": "1"})
        self.assertEqual(out["state"], "done")
        self.assertEqual(self.j("discuss", "--with", "codex,claude", "--rounds", "1", "x?")["state"], "done")  # person

    def test_bg_runs_detached_and_show_follows_it(self):
        import time
        out = self.j("discuss", "--bg", "--with", "codex,claude", "--rounds", "1", "which lock?",
                     env={**self.env, "CLAUDECODE": "1"})
        self.assertFalse(out["ran"])                              # without --confirmed: only the estimate
        self.assertNotIn("id", out)
        out = self.j("discuss", "--bg", "--confirmed", "--with", "codex,claude", "--rounds", "1", "which lock?",
                     env={**self.env, "CLAUDECODE": "1"})
        self.assertEqual(out["state"], "started")
        self.assertIn(self.j("discuss", "--show", out["id"])["state"], ("starting", "running", "done"))
        for _ in range(400):                 # up to 40 s: the detached process starts slowly under full-suite load
            try:
                if discuss.load(Paths(self.hub), out["id"])["state"] == "done":
                    break
            except (ValueError, OSError):    # caught mid-replace (Windows): look again
                pass
            time.sleep(0.1)
        log = Path(out["log"])
        shown = self.j("discuss", "--show", out["id"])
        self.assertEqual(shown["state"], "done", log.read_text() if log.exists() else "no log")
        self.assertEqual(shown["question"], "which lock?")
        self.assertEqual([t["role"] for t in shown["turns"]], ["proposer", "critic", "judge"])

    def discuss_prompts(self):
        return [c for c in self.calls() if "[ccx discuss" in (c.get("prompt") or "")]

    def test_format_reminder_in_the_same_session_fixes_it(self):
        out = self.j("discuss", "--with", "codex,claude,gemini", "x?",
                     env={**self.env, "FAKE_DISCUSS": "unparsed-once", "FAKE_DISCUSS_JUDGE": "unparsed-once"})
        crit, judge = out["turns"][1], out["turns"][2]
        self.assertEqual(crit["verdict"], "agree")
        self.assertTrue(crit["format_retry"] and judge["format_retry"])
        self.assertNotIn("unparsed", crit)
        self.assertTrue(out["agreed"])
        self.assertEqual(out["result"]["recommendation"], "one queue file with a lock")
        self.assertNotIn("unparsed", out["result"])
        calls = self.discuss_prompts()
        again = [c for c in calls if "format-again]" in c["prompt"]]
        self.assertEqual(len(again), 2)
        self.assertIn("CRITIQUE: agree", again[0]["prompt"])
        self.assertTrue(all("--resume" in c["argv"] for c in again))          # the same session, asked once more
        self.assertFalse(any("--no-session-persistence" in c["argv"] for c in calls))   # so it can be resumed
        from ccx.archive import finished_runs                     # ... and auto-archive tidies those sessions
        self.assertIn(crit["run_id"], finished_runs(Paths(self.hub)))

    def test_still_unparsed_is_said_and_does_not_end_the_talk(self):
        out = self.j("discuss", "--with", "codex,claude,gemini", "--rounds", "2", "x?",
                     env={**self.env, "FAKE_DISCUSS": "unparsed", "FAKE_DISCUSS_JUDGE": "unparsed"})
        self.assertEqual(out["state"], "done")
        self.assertFalse(out["agreed"])
        self.assertEqual([t["role"] for t in out["turns"]], ["proposer", "critic"] * 2 + ["judge"])
        self.assertEqual({t.get("verdict") for t in out["turns"] if t["role"] == "critic"}, {"unparsed"})
        self.assertEqual(out["result"]["unparsed_turns"], ["critic r1", "critic r2", "judge r2"])
        self.assertIn("RECOMMEND", out["result"]["unparsed"])
        self.assertEqual(out["result"]["recommendation"], "Use one queue file with a lock.")
        self.assertEqual(len([c for c in self.discuss_prompts() if "format-again]" in c["prompt"]]), 3)

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
        c = discuss.critique
        self.assertEqual(c({"summary": "critique:  AGREE. fine", "points": []}), "agree")
        self.assertEqual(c({"summary": "looks risky", "points": ["[must] broken"]}), "objections")
        self.assertEqual(c({"summary": "looks fine to me", "points": ["minor"]}), "unparsed")
        self.assertEqual(discuss.judge_missing({"summary": "RECOMMEND: A", "points": ["[reason] r"]}), [])
        self.assertEqual(len(discuss.judge_missing({"summary": "A", "points": ["r"]})), 2)

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


# discuss-r1 (2026-10-24, docs/research/2026-10-24-seven-cores-ab.md): codex proposed and judged, claude criticised,
# T2, 3 rounds allowed, agreed in round 2 after 5 turns; it cost $0.283 while the old estimate said $0.036.
R1_QUESTION = ("A Python function receives prices as strings like \"12.34\" and must return their total as an integer "
               "number of cents. Which conversion should we use, and why?\n(A) int(float(p) * 100)\n"
               "(B) round(float(p) * 100)\n(C) int(Decimal(p) * 100)\n(D) split the string at \".\" and parse the "
               "integer and fractional parts\nConsider at least \"0.29\", \"1.005\", \"-3.10\" and inputs with "
               "more than two decimals. Give one recommendation and what to do with inputs that have more than two "
               "decimals.")
R1_TURNS = [("codex", "gpt-6.1-sol:medium", 0.065827), ("claude", "sonnet:medium", 0.047316),
            ("codex", "gpt-6.1-sol:medium", 0.059653), ("claude", "sonnet:medium", 0.050003),
            ("codex", "gpt-6.1-sol:medium", 0.06023)]
R1_USD = 0.283029


class TestEstimate(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Paths(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_replay_r1_within_two_times(self):
        e = discuss.estimate(self.p, ["codex", "claude"], 3, tier="T2", question=R1_QUESTION)
        self.assertEqual(e["calls_max"], 7)
        self.assertEqual(e["models"], {"codex": "gpt-6.1-sol medium", "claude": "sonnet medium"})
        self.assertTrue(all(v.startswith("modelled") for v in e["basis"].values()))
        self.assertLessEqual(e["usd_min_est"], R1_USD)
        for est in (e["usd_max_est"], e["usd_min_est"]):
            self.assertTrue(0.5 <= R1_USD / est <= 2, (est, R1_USD))

    def test_measured_turns_on_the_same_rung_win(self):
        self.p.state.mkdir(parents=True)
        with open(self.p.ledger, "w", encoding="utf-8") as f:
            for i, (a, rung, usd) in enumerate(R1_TURNS):
                f.write(json.dumps({"run_id": f"r{i}", "label": f"discuss:x:{i}", "to": a, "mode": "read",
                                    "rungs": [f"{a}:{rung}"], "ae_usd": usd}) + "\n")
            # cheap read runs elsewhere (the old basis) and another rung do not count
            f.write(json.dumps({"run_id": "o", "label": "fix x", "to": "codex", "mode": "read",
                                "rungs": ["codex:gpt-6.1-sol:medium"], "ae_usd": 0.001}) + "\n")
        e = discuss.estimate(self.p, ["codex", "claude"], 3, tier="T2", question=R1_QUESTION)
        self.assertIn("measured: mean of 3", e["basis"]["codex"])
        codex, claude = (sum(u for a, _, u in R1_TURNS if a == n) / k for n, k in (("codex", 3), ("claude", 2)))
        self.assertAlmostEqual(e["usd_max_est"], 4 * codex + 3 * claude, places=3)
        self.assertTrue(0.5 <= R1_USD / e["usd_max_est"] <= 2)
        t1 = discuss.estimate(self.p, ["codex", "claude"], 3, tier="T1", question=R1_QUESTION)
        self.assertTrue(all(v.startswith("modelled") for v in t1["basis"].values()))
        self.assertEqual(t1["models"], {"codex": "gpt-6-luna low", "claude": "haiku low"})
        self.assertLess(t1["usd_max_est"], e["usd_max_est"] / 5)

    def test_auto_tier_steps_down_the_agent_that_would_run_out(self):
        t, why = discuss.tiers(self.p, ["codex", "claude", "deepseek"], "auto",
                               quota={"codex": 0.4, "claude": 1.3})
        self.assertEqual(t, {"codex": "T2", "claude": "T1", "deepseek": "T2"})
        self.assertIn("130%", why["claude"])
        self.assertIn("no quota reading", why["deepseek"])
        e = discuss.estimate(self.p, ["codex", "claude"], 2, tier=t)
        self.assertEqual(e["models"], {"codex": "gpt-6.1-sol medium", "claude": "haiku low"})
        self.assertEqual(e["tier"], {"codex": "T2", "claude": "T1"})
        self.assertEqual(discuss.tiers(self.p, ["codex"], "T1"), ({"codex": "T1"}, {}))

    def test_provider_has_its_own_model_and_unknown_price_is_said(self):
        from ccx.config import load_config
        cfg = load_config(self.p)
        self.assertEqual(discuss.rung(cfg, "deepseek", "T1"), ("deepseek-flash", "low"))
        e = discuss.estimate(self.p, ["codex", "claude", "kimi"], 1, tier="T1", cfg=cfg)
        self.assertIsNone(e["usd_max_est"])                       # kimi has no price in the defaults
        self.assertIn("kimi", e["basis"]["unknown"])
        with self.assertRaises(ValueError):
            discuss.rung(cfg, "nobody", "T1")


if __name__ == "__main__":
    unittest.main()
