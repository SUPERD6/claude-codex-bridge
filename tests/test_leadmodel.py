"""Lead model by task (opt-in lead.model_by_task): where ccx starts or recommends a NEW lead conversation, its model
follows the task's difficulty; with the setting off (shipped) nothing changes. Fake CLIs only."""
import json
import re
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccx import leadmodel  # noqa: E402
from test_report import ReportEnv  # noqa: E402
from test_transcript import _w, claude_events  # noqa: E402

CFG = {"lead": {"claude": "opus", "codex": "gpt-6.1-sol", "model_by_task": True},
       "lead_by_task": {"easy_max_b": 4.0, "hard_risk": "critical", "easy": {"claude": "sonnet"}}}


class TestRule(unittest.TestCase):
    def test_off_never_picks(self):
        off = {**CFG, "lead": {**CFG["lead"], "model_by_task": False}}
        self.assertIsNone(leadmodel.pick(off, "claude", 1.0))
        with open(Path(__file__).resolve().parent.parent / "config" / "tiers.toml", "rb") as fh:
            self.assertFalse(leadmodel.enabled(tomllib.load(fh)))                       # shipped off
        self.assertEqual(leadmodel.pick(off, "claude", 1.0, force=True)["model"], "sonnet")  # the eval's auto

    def test_easy_hard_and_risk(self):
        self.assertEqual(leadmodel.pick(CFG, "claude", 3.0)["model"], "sonnet")
        self.assertEqual(leadmodel.pick(CFG, "claude", 4.0)["band"], "easy")          # the threshold is inclusive
        hard = leadmodel.pick(CFG, "claude", 5.5)
        self.assertEqual((hard["model"], hard["band"]), ("opus", "hard"))
        self.assertEqual(leadmodel.pick(CFG, "claude", 1.0, "critical")["model"], "opus")
        self.assertIsNone(leadmodel.pick(CFG, "claude", None))                          # no difficulty: no pick
        self.assertEqual(leadmodel.pick(CFG, "codex", 1.0)["model"], "gpt-6.1-sol")     # no easy model configured
        self.assertIsNone(leadmodel.pick(CFG, "gemini", 1.0))                           # no lead model known

    def test_flags(self):
        self.assertEqual(leadmodel.model_argv("claude", "sonnet"), ["--model", "sonnet"])
        self.assertEqual(leadmodel.model_argv("codex", "gpt-6.1-sol"), ["--model", "gpt-6.1-sol"])
        self.assertEqual(leadmodel.model_argv("gemini", "pro"), [])
        self.assertEqual(leadmodel.builtin_model(leadmodel.pick(CFG, "claude", 2.0)), "sonnet")
        self.assertIsNone(leadmodel.builtin_model(leadmodel.pick(CFG, "claude", 6.0)))   # hard: inherit the lead's
        self.assertIsNone(leadmodel.builtin_model(leadmodel.pick(CFG, "codex", 2.0)))
        self.assertIsNone(leadmodel.builtin_model({"agent": "claude", "model": "claude-opus-5-5", "band": "easy"}))
        # only the easy band passes a model; the hard band keeps the tool's own (e.g. a long-context variant)
        self.assertEqual(leadmodel.start_argv(leadmodel.pick(CFG, "claude", 2.0)), ["--model", "sonnet"])
        self.assertEqual(leadmodel.start_argv(leadmodel.pick(CFG, "claude", 6.0)), [])
        self.assertEqual(leadmodel.start_argv(leadmodel.pick(CFG, "codex", 2.0)), [])     # easy == strong
        self.assertEqual(leadmodel.start_argv(None), [])

    def test_route_choice_wins_over_builtin_model(self):
        from types import SimpleNamespace
        from ccx.commands import delegation
        a = SimpleNamespace(lead="claude:opus:high", risk=None)
        route = {"b": 2.0, "choice": {"recommend": "builtin", "rung": "claude:haiku:low",
                                      "how": "use your Agent tool with model haiku ..."}}
        delegation._lead_by_task(CFG, route, a)
        self.assertEqual(route["new_lead"]["model"], "sonnet")
        self.assertNotIn("builtin_model", route)          # one source: the calibrated choice's `how`
        route = {"b": 2.0, "choice": {"recommend": "delegate", "rung": "codex:gpt-6-luna:low"}}
        delegation._lead_by_task(CFG, route, a)
        self.assertEqual(route["builtin_model"], "sonnet")  # fallback when no built-in sub-agent was recommended

    def test_difficulty_estimator_and_old_skill(self):
        from unittest import mock
        from ccx import learn
        seen = []
        with mock.patch.object(learn, "combine_difficulty", lambda p, br, m, lead: seen.append(lead) or {"b": 3.0}):
            ns = type("A", (), {"minutes": 8, "b": None, "risk": None})()
            with mock.patch.object(leadmodel, "record", lambda *x, **k: None):
                ch = leadmodel.for_new_lead(None, CFG, "codex", ns, "handoff", estimator="claude")
        self.assertEqual((ch["agent"], seen), ("codex", ["claude"]))   # the estimator's bias, the incoming tool's model

        def old(*_):
            raise ValueError("this task-routing copy needs the rubric (no --minutes support)")
        with mock.patch.object(learn, "combine_difficulty", old):
            self.assertIsNone(leadmodel.difficulty(None, 8))           # no pick, never a crash

    def test_handoff_keeps_by_abbreviation(self):
        import argparse
        from ccx.commands import memory
        ap = argparse.ArgumentParser()
        memory.register(ap.add_subparsers())
        a = ap.parse_args(["handoff", "--b", "claude", "--to", "codex", "x"])
        self.assertEqual((a.by, a.b), ("claude", None))
        self.assertEqual(ap.parse_args(["handoff", "--to", "codex", "--difficulty", "6", "x"]).b, 6.0)
        self.assertEqual(ap.parse_args(["fresh", "--b", "2"]).b, 2.0)


class TestCommands(ReportEnv):
    def events(self):
        from ccx.config import Paths
        f = Paths(self.hub).ledger
        rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []
        return [r for r in rows if r.get("type") == "lead_model"]

    def turn_on(self):
        self.j("config", "set", "lead.model_by_task", "on")

    def test_route_and_propose(self):
        off = self.j("route", "--minutes", "5", "--to", "codex", "--lead", "claude:opus:high", "rename a var")
        self.assertNotIn("new_lead", off)
        self.assertNotIn("builtin_model", off)
        self.turn_on()
        easy = self.j("route", "--b", "2", "--to", "codex", "--lead", "claude:opus:high", "rename a var")
        self.assertEqual((easy["new_lead"]["model"], easy["builtin_model"]), ("sonnet", "sonnet"))
        hard = self.j("route", "--b", "6", "--to", "codex", "--lead", "claude:opus:high", "redesign the queue")
        self.assertEqual((hard["new_lead"]["model"], hard["new_lead"]["band"]), ("opus", "hard"))
        self.assertNotIn("builtin_model", hard)                     # hard: the sub-agent inherits the lead's model
        self.assertEqual(self.events(), [])                         # route is a question: nothing recorded
        out = self.j("propose", "--b", "2", "--to", "codex", "--lead", "claude:opus:high", "rename a var")
        self.assertEqual(out["new_lead"]["model"], "sonnet")
        ev = self.events()
        self.assertEqual((len(ev), ev[0]["where"], ev[0]["proposal"]), (1, "propose", out["proposal"]))

    def test_fresh_and_handoff(self):
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.work.resolve()))
        _w(self.home_claude / "projects" / slug / "abc.jsonl", claude_events())
        off = self.j("fresh", "--as", "claude", "--no-model", "--minutes", "5")
        self.assertNotIn("--model", off["next"])
        self.assertNotIn("lead_model", off)
        self.turn_on()
        plain = self.j("fresh", "--as", "claude", "--no-model")              # on, but no difficulty given
        self.assertNotIn("--model", plain["next"])
        easy = self.j("fresh", "--as", "claude", "--no-model", "--minutes", "5")
        self.assertIn('claude --model sonnet "Continue the work', easy["next"])
        hard = self.j("fresh", "--as", "claude", "--no-model", "--minutes", "5", "--risk", "critical")
        self.assertNotIn("--model", hard["next"])                   # hard: the tool keeps its own model
        self.assertEqual(hard["lead_model"]["band"], "hard")
        ho = self.j("handoff", "--to", "codex", "--by", "claude", "--difficulty", "7", "done: x; next: y")
        self.assertEqual(ho["lead_model"]["model"], "gpt-6.1-sol")
        self.assertIn("normally runs on", ho["start"])
        self.assertEqual([e["where"] for e in self.events()], ["fresh", "fresh", "handoff"])


if __name__ == "__main__":
    unittest.main()
