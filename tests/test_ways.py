"""H8/H9: `ccx way` picks how to work by risk (fake CLIs only) and learns who is right the first time per kind."""
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import ledger, ways  # noqa: E402
from ccx.config import Paths  # noqa: E402
from test_ccx import Env  # noqa: E402

FAKES = Path(__file__).resolve().parent / "fakes"


class WayEnv(Env):
    def setUp(self):
        super().setUp()
        self.env["CCX_GEMINI_BIN"] = str(FAKES / "fake_gemini.py")
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def j(self, *args, env=None, code=0):
        r = self.ccx(*args, "--cwd", str(self.work), env={**self.env, **(env or {})})
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def prompts(self, agent=None):
        return [c["prompt"] for c in self.calls() if c.get("prompt") and (agent is None or c["agent"] == agent)]


class TestWays(WayEnv):
    def test_low_is_one_agent(self):
        out = self.j("way", "--with", "codex,claude", "change x to 2", env={"FAKE_WRITE": "a.py=x = 2\n"})
        self.assertEqual((out["way"], out["state"]), ("solo", "done"))
        self.assertEqual([s["step"] for s in out["steps"]], ["build"])

    def test_visible_plans_builds_and_accepts_with_one_fix(self):
        out = self.j("way", "--risk", "visible", "--with", "codex,claude", "change x to 2",
                     env={"FAKE_WRITE": "a.py=x = 2\n", "FAKE_REVIEW": "issues,pass"})
        self.assertEqual(out["way"], "plan_build")
        self.assertEqual(out["roles"], {"builder": "codex", "planner": "claude"})
        self.assertEqual([s["step"] for s in out["steps"]], ["plan", "build", "accept", "fix", "accept"])
        self.assertEqual(out["acceptance"]["verdict"], "pass")
        build_prompt = next(x for x in self.prompts("codex") if "change x to 2" in x)
        self.assertIn("## Plan from claude", build_prompt)
        self.assertIn("[step] add helper in util.py", build_prompt)
        accept = [x for x in self.prompts("claude") if "[ccx review" in x]
        self.assertIn("## The plan it was given", accept[0])
        # the fix is a follow-up of the first build: H9 counts that piece as rework
        rec = json.loads((self.hub / "ccx" / "runs" / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["review_of"], out["steps"][1]["run_id"])

    def test_critical_needs_yes_then_two_versions_and_a_pick(self):
        r = self.ccx("way", "--risk", "critical", "--with", "codex,claude,gemini", "--cwd", str(self.work), "x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--yes", r.stdout)
        dry = self.j("way", "--risk", "critical", "--with", "codex,claude,gemini", "--dry-run", "x")
        self.assertTrue(dry["needs_yes"])
        self.assertEqual(dry["roles"], {"builder": "codex", "second": "claude", "judge": "gemini"})
        out = self.j("way", "--risk", "critical", "--with", "codex,claude,gemini", "--yes", "change x to 2",
                     env={"FAKE_WRITE": "a.py=x = 2\n"})
        self.assertEqual(out["way"], "two_versions")
        self.assertEqual(out["pick"]["slot"], "B")
        self.assertEqual(out["run_id"], out["versions"]["B"]["run_id"])
        self.assertIn(".ccx-worktrees", out["versions"]["A"]["worktree"].replace("\\", "/"))
        pick = next(x for x in self.prompts("gemini") if ": pick]" in x)
        self.assertIn("## Version A (codex)", pick)


def _run(p, rid, to, kind="code", **extra):
    d = p.runs / rid
    d.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": rid, "to": to, "mode": "write", "state": "done", "route": {"kind": kind}, "ts": time.time(),
           "attempts": [], **extra}
    (d / "run.json").write_text(json.dumps(rec), encoding="utf-8")


class TestTrack(unittest.TestCase):
    def test_first_right_and_rework(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p = Paths(Path(t))
            p.runs.mkdir(parents=True, exist_ok=True)
            _run(p, "a1", "codex")                                   # right first time
            _run(p, "a2", "codex")                                   # needed a follow-up
            _run(p, "a3", "codex", resumed_from="a2")
            _run(p, "a4", "codex")                                   # judged wrong
            _run(p, "a5", "codex")                                   # never judged: not counted
            _run(p, "b1", "claude", kind="read")
            _run(p, "r1", "claude", label="review:a1", ephemeral=True)  # internal: not a piece
            for rid, ok in (("a1", True), ("a3", True), ("a4", False), ("b1", True)):
                ledger.append_event(p, {"type": "verify", "run_id": rid, "ok": ok, "ts": time.time()})
            tr = ways.track(p)
            c = tr["code"]["codex"]
            self.assertEqual((c["pieces"], c["judged"]), (4, 3))
            self.assertAlmostEqual(c["first_right"], 1 / 3, places=3)
            self.assertAlmostEqual(c["rework"], 2 / 3, places=3)
            self.assertFalse(c["enough"])
            self.assertEqual(tr["read"]["claude"]["first_right"], 1.0)
            self.assertNotIn("r1", [x["run_id"] for x in ways.pieces(p)])

    def test_tiers_apart_and_evals_left_out(self):
        # H9: a cheap tier's misses are seen apart from the strong one's; evaluation runs don't count by default
        import tempfile
        rung = lambda r: [{"rung": r}]  # noqa: E731
        with tempfile.TemporaryDirectory() as t:
            p = Paths(Path(t))
            p.runs.mkdir(parents=True, exist_ok=True)
            _run(p, "c1", "codex", attempts=rung("codex:luna:low"))
            _run(p, "c2", "codex", attempts=[{"rung": "codex:luna:low"}, {"rung": "codex:gpt-6:high"}])
            _run(p, "c3", "codex", attempts=rung("codex:gpt-6:high"))
            _run(p, "e1", "codex", label="eval-7c:r1:x", attempts=rung("codex:luna:low"))
            _run(p, "e2", "codex", route={"kind": "code", "no_ab": True}, attempts=rung("codex:luna:low"))
            for rid, ok in (("c1", False), ("c2", True), ("c3", True), ("e1", False), ("e2", False)):
                ledger.append_event(p, {"type": "verify", "run_id": rid, "ok": ok, "ts": time.time()})
            c = ways.track(p)["code"]["codex"]
            self.assertEqual((c["judged"], c["first_right"]), (3, round(2 / 3, 3)))
            self.assertEqual({k: (v["judged"], v["first_right"]) for k, v in c["tiers"].items()},
                             {"luna:low": (1, 0.0), "gpt-6:high": (2, 1.0)})      # the tier that finished it
            c = ways.track(p, include_evals=True)["code"]["codex"]
            self.assertEqual((c["judged"], c["tiers"]["luna:low"]["judged"]), (5, 3))

    def test_choose_uses_the_record(self):
        good = {"judged": 10, "first_right": 0.9, "rework": 0.1, "enough": True}
        weak = {"judged": 10, "first_right": 0.3, "rework": 0.6, "enough": True}
        c = ways.choose("low", "code", {"code": {"codex": weak, "claude": good}}, ["codex", "claude"])
        self.assertEqual((c["way"], c["roles"]["builder"]), ("solo", "claude"))       # the better one builds
        c = ways.choose("low", "code", {"code": {"codex": weak, "claude": weak}}, ["codex", "claude"])
        self.assertEqual(c["way"], "plan_build")                                       # weak builder gets a planner
        self.assertEqual(c["roles"]["planner"], "claude")
        few = {"judged": 2, "first_right": 1.0, "rework": 0.0, "enough": False}
        c = ways.choose("low", "code", {"code": {"claude": few}}, ["codex", "claude"])
        self.assertEqual(c["roles"]["builder"], "codex")                               # too few: order stays
        c = ways.choose("visible", "code", {}, ["codex"])
        self.assertEqual(c["way"], "solo")                                             # one vendor only


if __name__ == "__main__":
    unittest.main()
