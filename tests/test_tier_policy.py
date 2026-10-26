"""Whole-workflow tiers (save / balanced / fast / cheapest on --tradeoff): task-routing's tier_plan, how ccx propose
applies an explicitly picked tier, the ledger fields, the resume-chain count, and the turn hook's UTF-8 stdin."""
import argparse
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from test_adapters import AdapterEnv
from test_report import ReportEnv

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("tr_tiers", ROOT / "skills/task-routing/scripts/task_routing.py")
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)


class TestTierPlan(unittest.TestCase):
    def test_tiers_decide_who_does_each_size(self):
        large = dict(brief="rework the store", minutes=60, files=4)
        small = dict(brief="rename a flag", minutes=5, files=1)
        self.assertEqual(tr.tier_plan("save", **small)["mode"], "ccx2")
        self.assertEqual(tr.tier_plan("save", **large)["mode"], "ccx2")
        self.assertEqual(tr.tier_plan("balanced", **small)["mode"], "self")
        self.assertEqual(tr.tier_plan("balanced", **large)["mode"], "ccx2")
        self.assertEqual(tr.tier_plan("fast", **large)["mode"], "self")
        cheap = tr.tier_plan("cheapest", **small)
        self.assertEqual((cheap["mode"], cheap["may_be_wrong"], cheap["rung_tradeoff"]), ("direct", True, "save"))
        self.assertEqual(tr.tier_plan("balanced", **large)["rung_tradeoff"], "save")   # delegated part: save rung
        self.assertNotIn("rung_tradeoff", tr.tier_plan("fast", **small))

    def test_bands_from_minutes_files_and_brief(self):
        self.assertEqual(tr.size_band("x", 45, 1)["band"], "large")
        self.assertEqual(tr.size_band("x", 10, 3)["band"], "large")
        self.assertEqual(tr.size_band("x", 20, 1)["band"], "medium")
        self.assertEqual(tr.size_band("x", 5, 1)["band"], "small")
        self.assertEqual(tr.size_band("word " * 200, 5, 1)["band"], "large")             # a long brief
        self.assertEqual(tr.brief_words("修好解析器"), 2.0)                                 # 5 CJK chars / 2.5
        self.assertTrue(tr.size_band("x")["uncertain"])                                   # no --minutes / --files
        self.assertFalse(tr.size_band("x", 5)["uncertain"])
        one = tr.size_band("x", 60, 1)                     # any one signal is enough: a 60-minute one-file task
        self.assertEqual((one["band"], one["uncertain"]), ("large", False))
        self.assertEqual(tr.tier_plan("balanced", "x", 60, 1)["mode"], "ccx2")

    def test_uncertain_and_hard_tasks(self):
        self.assertEqual(tr.tier_plan("balanced", "big thing")["mode"], "self")          # uncertain -> self
        self.assertEqual(tr.tier_plan("save", "big thing")["mode"], "ccx2")              # uncertain -> ccx2
        hard = tr.tier_plan("balanced", "add resume after a kill to the queue state machine", 90, 5)
        self.assertEqual(hard["mode"], "self")
        self.assertIn("resume", hard["hard"])
        self.assertEqual(tr.tier_plan("balanced", "续跑时恢复状态", 90, 5)["mode"], "self")
        # whole words: "skill" does not name "kill", "traceback" not "race"
        for brief in ("Update the agent-delegate skill text", "Fix the traceback in report.py", "which skill ran"):
            plan = tr.tier_plan("balanced", brief, 60, 5)
            self.assertEqual((plan["hard"], plan["mode"]), ([], "ccx2"), brief)
        self.assertEqual(tr.tier_plan("balanced", "ccx resume, then Kill it", 60, 5)["hard"], ["resume", "kill"])
        # plain endings still count; a longer word does not
        for brief, word in (("the run resumed twice", "resume"), ("it crashes", "crash"), ("killing it", "kill"),
                            ("racing writers", "race"), ("two state machines", "state machine")):
            self.assertIn(word, tr.size_band(brief, 60, 5)["hard"], brief)
        for brief in ("list the skills", "add tracebacks", "the restarter tool", "a crashpad"):
            self.assertEqual(tr.size_band(brief, 60, 5)["hard"], [], brief)

    def test_big_lead_context_sends_medium_out_in_balanced(self):
        self.assertEqual(tr.tier_plan("balanced", "x", 20, 2)["mode"], "self")
        self.assertEqual(tr.tier_plan("balanced", "x", 20, 2, lead_ctx=200000)["mode"], "ccx2")

    def test_knob_and_config_override(self):
        self.assertEqual(tr.tier_name(0.1), "save")
        self.assertEqual(tr.tier_name("0.5"), "balanced")
        self.assertEqual(tr.tier_name(0.9), "fast")
        with self.assertRaises(ValueError):
            tr.tier_name("turbo")
        pol = {"bands": {"large_minutes": 30}, "balanced": {"medium": "ccx2"}}
        self.assertEqual(tr.tier_plan("balanced", "x", 35, 1, policy=pol)["band"], "large")
        self.assertEqual(tr.tier_plan("balanced", "x", 20, 1, policy=pol)["mode"], "ccx2")
        with self.assertRaises(ValueError):
            tr.tier_plan("fast", "x", 5, 1, policy={"fast": {"small": "teleport"}})

    def test_cheapest_picks_models_like_save(self):
        pri = tr.load_priors()
        self.assertEqual(tr.tradeoff_params(pri, "cheapest"), tr.tradeoff_params(pri, "save"))

    def test_shipped_config_matches_the_script_defaults(self):
        import tomllib
        cfg = tomllib.loads((ROOT / "config/tiers.toml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["defaults"]["tradeoff"], "save")         # default tier unchanged until confirmed
        for tier in tr.TIERS:
            self.assertEqual(cfg["policy"][tier], tr.DEFAULT_POLICY[tier], tier)
        self.assertEqual(cfg["policy"]["bands"], tr.DEFAULT_POLICY["bands"])


class TestProposeTiers(ReportEnv):
    LEAD = ("--to", "codex", "--lead", "claude:opus:high", "--lead-ctx", "0")

    def pick(self, tier):
        """What only the person does: pick a tier in their hub settings."""
        self.j("config", "set", "policy.picked", tier)

    def rows(self):
        return [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]

    def run_row(self, run_id):
        return next(r for r in self.rows() if r.get("run_id") == run_id and not r.get("type"))

    def test_no_tier_keeps_the_offer_first_rule(self):
        out = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        self.assertNotIn("authorized", out)
        self.assertEqual(out["worth_offering"], out["recommend"] == "delegate")
        self.assertFalse(out["tier"]["explicit"])
        self.assertEqual(out["tier"]["tier"], "save")                     # the shipped default, shown only
        self.assertIn("informational", out["tier"]["note"])

    def test_tradeoff_from_the_lead_authorises_nothing(self):
        # project-manager passes --tradeoff save on every dispatch; a lead may pass any tier: none of it is a pick
        for tier in ("save", "balanced", "cheapest"):
            out = self.j("propose", "--tradeoff", tier, "--minutes", "60", "--files", "4", *self.LEAD, "rework it")
            self.assertNotIn("authorized", out, tier)
            self.assertEqual(out["worth_offering"], out["recommend"] == "delegate")
            self.assertFalse(out["tier"]["explicit"])
        r = self.ccx("propose", "--tier-picked", "--minutes", "60", "--lead", "claude:opus:high", "x")
        self.assertNotEqual(r.returncode, 0)                  # no flag a lead could add to authorise itself
        self.pick("balanced")
        other = self.j("propose", "--tradeoff", "save", "--minutes", "60", "--files", "4", *self.LEAD, "rework it")
        self.assertNotIn("authorized", other)                 # a different tier than the person picked
        self.assertFalse(other["tier"]["explicit"])

    def test_picked_tier_setting_is_checked(self):
        r = self.ccx("config", "set", "policy.picked", "turbo")
        self.assertNotEqual(r.returncode, 0)
        self.pick("cheapest")
        self.pick("none")
        out = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        self.assertNotIn("authorized", out)                   # none = off again

    def test_bad_policy_falls_back_to_offer_first_and_doctor_says_so(self):
        (self.hub / "ccx").mkdir(parents=True, exist_ok=True)
        with open(self.hub / "ccx" / "tiers.toml", "a", encoding="utf-8") as fh:      # the hand-edited overrides
            fh.write('\n[policy.balanced]\nlarge = "teleport"\n')
        self.pick("balanced")
        out = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        self.assertNotIn("authorized", out)
        self.assertIn("teleport", out["tier"]["error"])
        self.assertIn("offer-first", out["tier"]["note"])
        from ccx import doctor, proposals
        from ccx.config import paths
        state, detail = doctor.tier_policy_check(paths())
        self.assertEqual(state, "WARN")
        self.assertIn("teleport", detail)
        self.assertEqual(proposals.stats(paths())["proposals"]["proposed"], 1)   # it fell back: still an offer

    def test_doctor_names_the_picked_tier(self):
        from ccx import doctor
        from ccx.config import paths
        self.assertEqual(doctor.tier_policy_check(paths()), ("ok", "no tier picked: offer first (policy.picked)"))
        self.pick("balanced")
        state, detail = doctor.tier_policy_check(paths())
        self.assertEqual(state, "ok")
        self.assertIn("balanced", detail)

    def test_picked_tier_preauthorises_its_delegation(self):
        self.pick("balanced")
        big = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        # worth_offering and authorized agree: never "false" next to "authorized: true"
        self.assertEqual((big["recommend"], big["authorized"], big["worth_offering"]), ("ccx2", True, True))
        self.assertIn("balanced", big["say"])
        self.assertIn("--tradeoff save", big["next"])                       # delegated part: save's model pick
        self.assertIn(f"--proposal {big['proposal']}", big["next"])
        same = self.j("propose", "--tradeoff", "balanced", "--minutes", "60", "--files", "4", *self.LEAD, "rework")
        self.assertTrue(same["authorized"])                                 # the same tier given again
        small = self.j("propose", "--minutes", "5", "--files", "1", *self.LEAD, "rename a flag")
        self.assertEqual((small["recommend"], small["authorized"], small["worth_offering"]), ("self", False, False))
        self.pick("cheapest")
        cheap = self.j("propose", "--minutes", "5", "--files", "1", *self.LEAD, "rename a flag")
        self.assertEqual((cheap["recommend"], cheap["may_be_wrong"], cheap["worth_offering"]), ("direct", True, True))
        self.assertIn("may be wrong", cheap["next"])
        self.assertIn("--review off", cheap["next"])
        self.assertIn("still paid", cheap["next"])                          # through a lead, its cost stays
        prop = next(r for r in self.rows() if r.get("proposal") == big["proposal"] and r.get("type") == "proposal")
        self.assertEqual((prop["policy_tier"], prop["band"], prop["planned_mode"], prop["tier_explicit"],
                          prop["estimate_minutes"], prop["estimate_files"], prop["preauthorized"]),
                         ("balanced", "large", "ccx2", True, 60, 4, True))
        self.j("propose", "--no", small["proposal"])
        self.assertEqual(self.rows()[-1]["actual_mode"], "self")

    def test_run_ledger_row_carries_the_tier(self):
        self.pick("cheapest")
        out = self.j("run", "--from", "claude", "--to", "codex", "--minutes", "30", "--files", "2", "--kind", "code",
                     "add a parser")
        self.assertEqual(out["status"], "done", out)
        row = self.run_row(out["run_id"])
        # not a pre-authorised proposal: the lead started it and accepts it, whatever the tier planned
        self.assertEqual((row["policy_tier"], row["band"], row["planned_mode"], row["tier_explicit"],
                          row["estimate_minutes"], row["actual_mode"]),
                         ("cheapest", "medium", "direct", True, 30, "ccx2"))
        out = self.j("run", "--from", "claude", "--to", "codex", "--tradeoff", "fast", "--minutes", "30",
                     "--files", "2", "--kind", "code", "add a parser")
        row = self.run_row(out["run_id"])
        # the tier said self, the run went out anyway: planned and actual differ, which is what both are for
        self.assertEqual((row["planned_mode"], row["tier_explicit"], row["actual_mode"]), ("self", False, "ccx2"))

    def test_preauthorised_run_keeps_the_tier_and_is_not_a_yes(self):
        self.pick("cheapest")
        cheap = self.j("propose", "--minutes", "30", "--files", "2", *self.LEAD, "add a parser")
        out = self.j("run", "--from", "claude", "--to", "codex", "--tradeoff", "save", "--review", "off",
                     "--proposal", cheap["proposal"], "--minutes", "30", "--files", "2", "--kind", "code",
                     "add a parser", env={**self.env, "CCX_AB_RATE": "1"})
        self.assertEqual(out["status"], "done", out)                  # no A/B self-run for the tier's proposal
        row = self.run_row(out["run_id"])
        self.assertEqual((row["policy_tier"], row["planned_mode"], row["actual_mode"], row["proposal"]),
                         ("cheapest", "direct", "direct", cheap["proposal"]))
        ans = next(r for r in self.rows() if r.get("type") == "proposal_answer" and r["proposal"] == cheap["proposal"])
        self.assertEqual((ans["source"], ans["actual_mode"]), ("tier", "direct"))
        self.pick("none")
        offered = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        self.j("propose", "--no", offered["proposal"])
        from ccx import proposals
        from ccx.config import paths
        st = proposals.stats(paths())["proposals"]
        # the H12 chain counts only the offer the person answered; the tier-decided one is counted apart
        self.assertEqual((st["proposed"], st["agreed"], st["declined"], st["unanswered"], st["tier_decided"]),
                         (1, 0, 1, 0, 1))

    def test_preauthorisation_lapses_when_the_setting_changes(self):
        self.pick("save")
        big = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        self.assertTrue(big["authorized"])
        self.pick("none")
        r = self.ccx("run", "--from", "claude", "--to", "codex", "--proposal", big["proposal"], "--b", "4",
                     "rework the parser")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("policy.picked", r.stdout + r.stderr)
        self.assertFalse(any(r.get("type") == "proposal_answer" for r in self.rows()))   # nothing recorded as a yes

    def test_preauthorisation_does_not_pass_the_autonomy_gate(self):
        self.pick("save")
        big = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        self.assertTrue(big["authorized"])
        for level in ("L0", "L1"):
            out = self.j("run", "--from", "claude", "--to", "codex", "--tradeoff", "save", "--autonomy", level,
                         "--mode", "write", "--proposal", big["proposal"], "--b", "4", "rework the parser")
            self.assertIs(out["delegated"], False, level)
            self.assertIn(level, out["why"])
        self.pick("none")
        offered = self.j("propose", "--minutes", "60", "--files", "4", *self.LEAD, "rework the parser")
        out = self.j("run", "--from", "claude", "--to", "codex", "--autonomy", "L1", "--mode", "write",
                     "--proposal", offered["proposal"], "--b", "4", "rework the parser")
        self.assertIn("run_id", out, out)                             # a person's yes still approves, as before

    def test_ab_and_trial_sampling_stay_for_plain_runs(self):
        env = {**self.env, "CCX_AB_RATE": "1"}
        base = ("run", "--from", "claude", "--to", "codex", "--b", "4", "--kind", "code")
        sampled = self.ccx(*base, "add x", env=env)
        self.assertIn("ab-sample", sampled.stdout + sampled.stderr)            # unchanged without a tier
        plain = self.ccx(*base, "--tradeoff", "save", "add x", env=env)
        self.assertIn("ab-sample", plain.stdout + plain.stderr)                # --tradeoff: A/B as before
        self.pick("save")
        picked = self.ccx(*base, "add x", env=env)
        self.assertIn("ab-sample", picked.stdout + picked.stderr)              # not a tier's proposal: as before
        from ccx.commands import common
        from ccx.config import load_config, paths
        with mock.patch("ccx.trial.active", return_value={"id": "h11", "rate": 0.5}) as act, \
                mock.patch("ccx.trial.assign", return_value="self"), mock.patch("ccx.trial.bucket", return_value="b"):
            kw, route = common.resolve({"b": 4, "tradeoff": "save", "kind": "code", "to": "codex"}, "claude",
                                       paths(), load_config(paths()))
        self.assertTrue(act.called)                                            # the H11 trial still assigns
        self.assertEqual((kw, route.get("trial")), (None, "h11"))

    def test_tradeoff_help_is_current(self):
        r = self.ccx("run", "-h")
        self.assertNotIn("initially balanced", r.stdout)
        self.assertIn("cheapest", r.stdout)
        self.assertNotIn("--tier-picked", r.stdout)


class TestResumeChain(AdapterEnv):
    def test_each_resume_adds_one(self):
        out = self.j("run", "--from", "claude", "--to", "gemini", "--tier", "T2", "--mode", "read", "review x")
        self.assertEqual(self.rec(out["run_id"])["resume_chain"], 0)
        r2 = self.j("resume", out["run_id"], "one more thing")
        r3 = self.j("resume", r2["run_id"], "and another")
        self.assertEqual((self.rec(r2["run_id"])["resume_chain"], self.rec(r3["run_id"])["resume_chain"]), (1, 2))
        rows = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(next(r for r in rows if r.get("run_id") == r3["run_id"])["resume_chain"], 2)

    def test_a_board_message_into_the_session_is_not_a_follow_up(self):
        import os
        from ccx.config import Paths
        from ccx.delegate import Request, run
        out = self.j("run", "--from", "claude", "--to", "gemini", "--tier", "T2", "--mode", "read", "review x")
        with mock.patch.dict(os.environ, self.env):
            r = run(Request(to="gemini", brief="a question from the board", resume_run=out["run_id"],
                            caller="claude", escalate=False, mode="read", cwd=self.work, side_message=True),
                    Paths(self.hub))
        self.assertEqual(self.rec(r["run_id"])["resume_chain"], 0)


class TestReviewFailedHint(unittest.TestCase):
    def test_the_lead_fixes_it_itself(self):
        from ccx.prompts import REVIEW_FAILED
        txt = REVIEW_FAILED.format(run_id="r1")
        self.assertIn("fix the real ones yourself", txt)
        self.assertIn("last resort", txt)


class TestTurnStdinUtf8(unittest.TestCase):
    def test_reads_utf8_bytes_whatever_the_console_code_page(self):
        from ccx.commands import board as bcmd
        payload = json.dumps({"prompt": "修好续跑的状态机", "session_id": "s1"}, ensure_ascii=False).encode("utf-8")
        fake = io.TextIOWrapper(io.BytesIO(payload), encoding="gbk")     # what a Chinese Windows console gives
        seen = {}

        def capture(vendor, data, threshold):
            seen.update(data)
            return ""
        with mock.patch.object(bcmd.sys, "stdin", fake), mock.patch.object(bcmd, "turn_output", capture):
            self.assertEqual(bcmd.cmd_turn(argparse.Namespace(as_="claude", threshold=None)), 0)
        self.assertEqual(seen.get("prompt"), "修好续跑的状态机")
        seen.clear()
        fake = io.TextIOWrapper(io.BytesIO(b"\xef\xbb\xbf" + payload), encoding="gbk")   # with a UTF-8 BOM
        with mock.patch.object(bcmd.sys, "stdin", fake), mock.patch.object(bcmd, "turn_output", capture):
            self.assertEqual(bcmd.cmd_turn(argparse.Namespace(as_="claude", threshold=None)), 0)
        self.assertEqual(seen.get("prompt"), "修好续跑的状态机")


class TestSkillsAgree(unittest.TestCase):
    def test_both_skills_teach_the_picked_tier(self):
        for name in ("SKILL.md", "README.zh.md"):
            for skill in ("agent-delegate", "task-routing"):
                txt = (ROOT / "skills" / skill / name).read_text(encoding="utf-8")
                self.assertIn("authorized: true", txt, (skill, name))
                self.assertIn("worth_offering: true", txt, (skill, name))     # what ccx propose returns with it
                self.assertIn("policy.picked", txt, (skill, name))            # only the person's setting
                self.assertNotIn("--tier-picked", txt, (skill, name))


if __name__ == "__main__":
    unittest.main()
