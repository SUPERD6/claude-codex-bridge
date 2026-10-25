"""scripts/eval/r3.py and l5_memory.py without real CLIs: the schedule, the L8 read-share estimate, the summary
statistics, the L5 cases (start fails, solution passes) and the export's scrubbing."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))

import common  # noqa: E402
import l5_memory  # noqa: E402
import r3  # noqa: E402

HAS_PYTEST = subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0


def _ev(**kw) -> str:
    return json.dumps(kw)


class TestSchedule(unittest.TestCase):
    def test_fixed_by_seed_every_task_every_arm_each_round(self):
        a, b = r3.schedule(2, 27), r3.schedule(2, 27)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 10 * 3 * 2)
        for rd in (1, 2):
            for t in r3.TASKS:
                self.assertEqual(sorted(u["arm"] for u in a if u["round"] == rd and u["task"] == t), sorted(r3.ARMS))

    def test_lead_prompts_differ_only_in_how(self):
        task = r3.by_id("coupon")
        ps = {arm: r3.lead_prompt(task, arm, "eval-r3:t:1:coupon:" + arm) for arm in r3.ARMS}
        for p in ps.values():
            self.assertIn(task["brief"], p)
        self.assertIn("--tradeoff save --review on --context auto", ps["ccx"])
        self.assertIn("subagent_type `worker`", ps["builtin"])
        self.assertIn("--agents", r3.lead_argv("builtin", 0.5))
        self.assertNotIn("--no-session-persistence", r3.lead_argv("ccx", 0.5))   # --context reads it


class TestReadShare(unittest.TestCase):
    def test_read_commands(self):
        self.assertTrue(r3.is_read_cmd("cd x && cat a.py | head -5"))
        self.assertTrue(r3.is_read_cmd(["bash", "-lc", "sed -n 1,20p x.py"]))
        self.assertTrue(r3.is_read_cmd("git show HEAD:a.py"))
        self.assertFalse(r3.is_read_cmd("sed -i s/a/b/ x.py"))
        self.assertFalse(r3.is_read_cmd("python -m pytest -q"))
        self.assertFalse(r3.is_read_cmd("cat a.py && python b.py"))
        ps = '"C:\\\\WINDOWS\\\\powershell.exe" -Command \'rg -n "a|b" .; Get-Content -Raw x.md\''
        self.assertTrue(r3.is_read_cmd(ps))                      # Codex's shell wrapper; | inside quotes
        self.assertFalse(r3.is_read_cmd('"powershell.exe" -Command "python -m pytest -q"'))

    def test_claude_stream_counts_reads_again_in_later_requests(self):
        def asst(mid, ctx, out, tools=(), ptu=None):
            return _ev(type="assistant", parent_tool_use_id=ptu, message={
                "id": mid, "usage": {"input_tokens": 0, "cache_read_input_tokens": ctx, "output_tokens": out},
                "content": [{"type": "tool_use", "id": i, "name": n, "input": inp} for i, n, inp in tools]})

        def res(tid, chars, ptu=None):
            return _ev(type="user", parent_tool_use_id=ptu,
                       message={"content": [{"type": "tool_result", "tool_use_id": tid, "content": "x" * chars}]})
        s = "\n".join([asst("m1", 1000, 0, [("t1", "Read", {})], "P"), res("t1", 4000, "P"),
                       asst("m2", 2000, 0, [("t2", "Bash", {"command": "python -m pytest"})], "P"),
                       res("t2", 400, "P"), asst("m3", 2100, 0, (), "P"),
                       asst("lead", 500, 10)])
        sub = r3.read_share_claude(s, True)
        # read 1000 tokens, in the context of m2 and m3: 2000 of 1000 + 2000 + 2100 = 5100
        self.assertEqual((sub["requests"], sub["read_tokens"], sub["tokens"]), (3, 2000, 5100))
        self.assertAlmostEqual(sub["read_share"], round(2000 / 5100, 4))
        self.assertEqual((sub["read_calls"], sub["other_calls"]), (1, 1))
        lead = r3.read_share_claude(s, None)
        self.assertEqual((lead["requests"], lead["tokens"], lead["read_tokens"]), (1, 510, 0))

    def test_codex_json_is_an_approximation(self):
        s = "\n".join([_ev(type="thread.started", thread_id="x"),
                       _ev(type="item.completed", item={"type": "command_execution", "command": "cat a.py",
                                                        "aggregated_output": "y" * 400}),
                       _ev(type="item.completed", item={"type": "file_change"}),
                       _ev(type="turn.completed", usage={"input_tokens": 900, "output_tokens": 100})])
        r = r3.read_share_codex(s)
        # 100 tokens read, then two more calls (the edit and the answer): 200 of 1000
        self.assertEqual((r["requests"], r["read_tokens"], r["read_share"], r["approx"]), (3, 200, 0.2, True))


class TestSummary(unittest.TestCase):
    def test_pairs_cps_holm_and_l8(self):
        rows = []
        for t, oks in {"a": (1, 0, 1), "b": (1, 1, 1), "c": (0, 0, 1)}.items():
            for rd in (1, 2):
                for arm, ok, usd in zip(r3.ARMS, oks, (0.10, 0.05, 0.04)):
                    rows.append({"tag": "t", "round": rd, "task": t, "arm": arm, "ok": bool(ok), "usd": usd,
                                 "wall_s": 10.0, "lead_tokens": 100, "lead_only_usd": usd / 2, "sub_usd": usd / 2,
                                 "rework": 1 if arm == "builtin" else 0, "delegated": arm != "self",
                                 "l8": [{"read_share": 0.6, "read_tokens": 6, "tokens": 10}] if arm != "self" else [],
                                 "l8_lead": {"read_share": 0.3}})
        s = r3.summarize(rows)
        self.assertEqual(s["per_arm"]["ccx"]["ok"], 6)
        self.assertEqual(s["per_arm"]["builtin"]["cps"], round(0.05 * 6 / 2, 5))
        c = s["builtin->ccx"]
        self.assertEqual((c["pairs"], c["discordant"]), (6, {"only_builtin": 0, "only_ccx": 4}))
        self.assertAlmostEqual(c["mcnemar_p"], 0.125)
        self.assertEqual(set(s["ok_holm"]), {"builtin->ccx", "self->builtin", "self->ccx"})
        self.assertEqual((s["l8"]["sub_runs"], s["l8"]["over_half"], s["l8"]["pooled_share"]), (12, 12, 0.6))
        self.assertEqual(s["per_task"]["c"], {"self": "0/2", "builtin": "0/2", "ccx": "2/2"})

    def test_scrub_drops_paths_and_ids(self):
        o = r3.scrub({"bash": [f'python "{r3.ROOT.as_posix()}/ccx.py" run x'], "hub": {"a": 1}, "ok": True})
        self.assertEqual(o, {"bash": ['python "<repo>/ccx.py" run x'], "ok": True})


class TestL5(unittest.TestCase):
    def test_schedule_both_directions_both_arms(self):
        s = l5_memory.schedule(2, 27)
        self.assertEqual(len(s), len(l5_memory.CASES) * 2 * 2 * 2)
        self.assertEqual(s, l5_memory.schedule(2, 27))

    def test_summary_pairs_off_and_on(self):
        rows = [{"tag": "t", "round": 1, "task": "mem-json", "dir": "claude->codex", "arm": "off", "ok": False,
                 "usd": 0.01, "note_in_prompt": False},
                {"tag": "t", "round": 1, "task": "mem-json", "dir": "claude->codex", "arm": "on", "ok": True,
                 "usd": 0.01, "note_in_prompt": True}]
        s = l5_memory.summarize(rows)
        self.assertEqual(s["paired"], {"pairs": 1, "only_off": 0, "only_on": 1, "mcnemar_p": 1.0})
        self.assertEqual(s["arms"]["on"]["note_in_prompt"], 1)

    @unittest.skipUnless(HAS_PYTEST, "pytest is needed to run the cases' tests")
    def test_cases_start_fails_solution_passes(self):
        tmp = Path(tempfile.mkdtemp())
        for c in l5_memory.CASES[3:]:                     # the first three are checked in test_eval_tasks
            with self.subTest(case=c["id"]):
                repo = common.make_repo(c, tmp / c["id"])
                self.assertFalse(common.score(repo, c)["ok"])
                for name, text in c["solution"].items():
                    (repo / name).write_text(text, encoding="utf-8")
                self.assertTrue(common.score(repo, c)["ok"], common.score(repo, c)["pytest"])


if __name__ == "__main__":
    unittest.main()
