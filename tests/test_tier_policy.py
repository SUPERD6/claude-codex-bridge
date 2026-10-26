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
        self.assertTrue(tr.size_band("x", 60, 1)["uncertain"])                            # large vs small: disagree

    def test_uncertain_and_hard_tasks(self):
        self.assertEqual(tr.tier_plan("balanced", "big thing")["mode"], "self")          # uncertain -> self
        self.assertEqual(tr.tier_plan("save", "big thing")["mode"], "ccx2")              # uncertain -> ccx2
        hard = tr.tier_plan("balanced", "add resume after a kill to the queue state machine", 90, 5)
        self.assertEqual(hard["mode"], "self")
        self.assertIn("resume", hard["hard"])
        self.assertEqual(tr.tier_plan("balanced", "续跑时恢复状态", 90, 5)["mode"], "self")

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
    def test_no_tier_keeps_the_offer_first_rule(self):
        out = self.j("propose", "--minutes", "60", "--files", "4", "--to", "codex", "--lead", "claude:opus:high",
                     "--lead-ctx", "0", "rework the parser")
        self.assertNotIn("authorized", out)
        self.assertEqual(out["worth_offering"], out["recommend"] == "delegate")
        self.assertFalse(out["tier"]["explicit"])
        self.assertEqual(out["tier"]["tier"], "save")                     # the shipped default, shown only
        self.assertIn("informational", out["tier"]["note"])

    def test_explicit_tier_preauthorises_its_delegation(self):
        big = self.j("propose", "--tradeoff", "balanced", "--minutes", "60", "--files", "4", "--to", "codex",
                     "--lead", "claude:opus:high", "--lead-ctx", "0", "rework the parser")
        self.assertEqual((big["recommend"], big["authorized"], big["worth_offering"]), ("ccx2", True, False))
        self.assertIn("--tradeoff save", big["next"])                       # delegated part: save's model pick
        self.assertIn(f"--proposal {big['proposal']}", big["next"])
        self.assertNotIn("say", big)
        small = self.j("propose", "--tradeoff", "balanced", "--minutes", "5", "--files", "1", "--to", "codex",
                       "--lead", "claude:opus:high", "--lead-ctx", "0", "rename a flag")
        self.assertEqual((small["recommend"], small["authorized"]), ("self", False))
        cheap = self.j("propose", "--tradeoff", "cheapest", "--minutes", "5", "--files", "1", "--to", "codex",
                       "--lead", "claude:opus:high", "--lead-ctx", "0", "rename a flag")
        self.assertEqual((cheap["recommend"], cheap["may_be_wrong"]), ("direct", True))
        self.assertIn("may-be-wrong", cheap["next"])
        rows = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        prop = next(r for r in rows if r.get("proposal") == big["proposal"] and r.get("type") == "proposal")
        self.assertEqual((prop["policy_tier"], prop["band"], prop["planned_mode"], prop["tier_explicit"],
                          prop["estimate_minutes"], prop["estimate_files"]), ("balanced", "large", "ccx2", True, 60, 4))
        self.j("propose", "--no", small["proposal"])
        rows = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["actual_mode"], "self")

    def test_run_ledger_row_carries_the_tier(self):
        out = self.j("run", "--from", "claude", "--to", "codex", "--tradeoff", "cheapest", "--minutes", "30",
                     "--files", "2", "--kind", "code", "add a parser")
        self.assertEqual(out["status"], "done", out)
        rows = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        row = next(r for r in rows if r.get("run_id") == out["run_id"] and not r.get("type"))
        self.assertEqual((row["policy_tier"], row["band"], row["planned_mode"], row["tier_explicit"],
                          row["estimate_minutes"], row["actual_mode"]), ("cheapest", "medium", "direct", True, 30, "ccx2"))

    def test_explicit_tier_skips_the_ab_self_run(self):
        env = {"CCX_AB_RATE": "1"}
        sampled = self.ccx("run", "--from", "claude", "--to", "codex", "--b", "4", "--kind", "code", "add x", env=env)
        self.assertIn("ab-sample", sampled.stdout + sampled.stderr)            # unchanged without a tier
        out = self.j("run", "--from", "claude", "--to", "codex", "--b", "4", "--kind", "code", "--tradeoff", "save",
                     "add x", env=env)
        self.assertEqual(out["status"], "done", out)

    def test_tradeoff_help_is_current(self):
        r = self.ccx("run", "-h")
        self.assertNotIn("initially balanced", r.stdout)
        self.assertIn("cheapest", r.stdout)


class TestResumeChain(AdapterEnv):
    def test_each_resume_adds_one(self):
        out = self.j("run", "--from", "claude", "--to", "gemini", "--tier", "T2", "--mode", "read", "review x")
        self.assertEqual(self.rec(out["run_id"])["resume_chain"], 0)
        r2 = self.j("resume", out["run_id"], "one more thing")
        r3 = self.j("resume", r2["run_id"], "and another")
        self.assertEqual((self.rec(r2["run_id"])["resume_chain"], self.rec(r3["run_id"])["resume_chain"]), (1, 2))
        rows = [json.loads(x) for x in (self.hub / "ccx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(next(r for r in rows if r.get("run_id") == r3["run_id"])["resume_chain"], 2)


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


if __name__ == "__main__":
    unittest.main()
