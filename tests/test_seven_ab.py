"""scripts/eval/seven_ab.py: the random paired schedule, the ccx command lines, resuming and the budget stop,
one direct unit against a fake `ccx`, and the summary statistics (no real CLIs, no model calls)."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

EVAL = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(EVAL))

import common  # noqa: E402
import seven_ab  # noqa: E402

HAS_PYTEST = subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0

# A stand-in for `python ccx.py`: `run` writes the task's reference solution into the current folder and prints a
# ccx-like JSON result; `ctx init` + `ctx add` write the project-memory file.
FAKE_CCX = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from tasks import TASKS, MEDIUM, MEMORY
    args = sys.argv[2:]
    if args[0] == "ctx":                      # like ccx: `add` needs `init` first
        f = Path(args[2]) / ".ccx" / "context.md"
        if args[3] == "init":
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("# context\\n", encoding="utf-8")
        elif not f.exists():
            sys.exit("run `ccx ctx init` first")
        else:
            f.write_text(f.read_text(encoding="utf-8") + "- " + args[-1] + "\\n", encoding="utf-8")
        sys.exit(0)
    brief = args[-1]
    for t in [*TASKS, *MEDIUM, *MEMORY]:
        if t["brief"] == brief:
            for name, text in t["solution"].items():
                Path(name).write_text(text, encoding="utf-8")
    print("noise line")
    print(json.dumps({"run_id": "r1", "status": "done", "ok": True, "check": {"ok": True},
                      "review": {"verdict": "pass", "usd": 0.001}}))
''')


def args(**kw):
    a = SimpleNamespace(sub_to="codex", sub_model="gpt-6-luna", sub_effort="low", fixed_to="claude",
                        fixed_model="sonnet", fixed_effort="medium", timeout=60, tag="t", seed=1, budget=1.0,
                        exps="route,review,memory", rounds=1, out="", workdir="", dry_run=False)
    a.__dict__.update(kw)
    return a


class TestSchedule(unittest.TestCase):
    def test_paired_random_and_fixed_by_seed(self):
        s = seven_ab.schedule(list(seven_ab.EXPS), 3, seed=7)
        self.assertEqual(s, seven_ab.schedule(list(seven_ab.EXPS), 3, seed=7))
        self.assertNotEqual(s, seven_ab.schedule(list(seven_ab.EXPS), 3, seed=8))
        n = sum(3 * len(e["tasks"]) * len(e["arms"]) for e in seven_ab.EXPS.values())
        self.assertEqual(len(s), n)
        by = {}
        for u in s:
            by.setdefault((u["exp"], u["round"], u["task"]), []).append(u["arm"])
        self.assertTrue(all(sorted(v) == sorted(seven_ab.EXPS[k[0]]["arms"]) for k, v in by.items()))
        firsts = {v[0] for k, v in by.items() if k[0] == "deleg"}
        self.assertEqual(firsts, {"self", "delegate"})                     # the order really varies
        self.assertEqual([u["round"] for u in s], sorted(u["round"] for u in s))   # rounds first

    def test_ccx_argv(self):
        t = seven_ab.by_id("lru")
        routed = seven_ab.ccx_argv("route", "routed", t, "L", args(), ["ccx"])
        self.assertIn("auto", routed)
        self.assertEqual(routed[routed.index("--minutes") + 1], "15")
        self.assertNotIn("--no-escalate", routed)
        fixed = seven_ab.ccx_argv("route", "fixed", t, "L", args(), ["ccx"])
        self.assertEqual(fixed[fixed.index("--model") + 1], "sonnet")
        self.assertIn("--no-escalate", fixed)
        rv = seven_ab.ccx_argv("review", "review", t, "L", args(), ["ccx"])
        self.assertEqual(rv[rv.index("--review") + 1], "on")
        nr = seven_ab.ccx_argv("review", "noreview", t, "L", args(), ["ccx"])
        self.assertEqual(nr[nr.index("--review") + 1], "off")
        for v in (routed, fixed, rv, nr):
            self.assertEqual(v[-1], t["brief"])
            self.assertIn("--no-ab", v)          # never a sample of the running H11 trial
            self.assertEqual(v[v.index("--check") + 1], seven_ab.ACCEPT)
            self.assertEqual(v[v.index("--minutes") + 1], "15")      # every arm, so routing learns from it


class TestRun(unittest.TestCase):
    def test_resume_and_budget(self):
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "r.jsonl"
        calls = []

        def fake(u, a, work, ccx=None):
            calls.append(u["label"])
            return {**u, "ok": True, "wall_s": 1.0, "lead": None, "sub_ae_usd": 0.3, "review_ae_usd": 0.0}

        a = args(out=str(out), exps="memory", rounds=1, budget=10.0, workdir=str(tmp))
        runners = {"direct": fake, "deleg": fake}
        self.assertEqual(seven_ab.cmd_run(a, ["ccx"], runners), 0)
        self.assertEqual(len(calls), 9)                                      # 3 memory tasks x 3 arms
        calls.clear()
        self.assertEqual(seven_ab.cmd_run(a, ["ccx"], runners), 0)
        self.assertEqual(calls, [])                                          # all done: nothing re-run
        a2 = args(out=str(out), exps="memory", rounds=2, budget=2.0, workdir=str(tmp))
        a2.budget = 2.9
        self.assertEqual(seven_ab.cmd_run(a2, ["ccx"], runners), 2)        # $2.7 spent: one more unit, then stops at $2.9
        self.assertEqual(len(calls), 1)

    @unittest.skipUnless(HAS_PYTEST, "pytest is needed to score the task")
    def test_direct_unit_with_fake_ccx(self):
        tmp = Path(tempfile.mkdtemp())
        fake = tmp / "fake_ccx.py"
        fake.write_text(FAKE_CCX, encoding="utf-8")
        ledger = {"L": [{"run_id": "r1", "rungs": ["codex:gpt-6-luna:low"], "ae_usd": 0.002, "ok": True,
                         "usage": {"input": 10, "cached": 90, "output": 5}, "seconds": 3.0, "kind": "ok"}],
                  "review:r1": [{"run_id": "v1", "ae_usd": 0.001, "usage": {"input": 4, "cached": 0, "output": 1},
                                 "seconds": 1.0}]}
        verdicts = []
        u = {"exp": "memory", "arm": "mem", "round": 1, "task": "mem-money", "slot": 0, "tag": "t", "label": "L"}
        row = seven_ab.run_direct(u, args(), tmp, [sys.executable, str(fake), str(EVAL)],
                                  rows_for=lambda lab: ledger.get(lab, []),
                                  verify=lambda rid, ok, note: verdicts.append((rid, ok)) or "ok")
        self.assertTrue(row["ok"], row["pytest"])
        ctx = (tmp / "memory-1-mem-money-mem" / ".ccx" / "context.md").read_text(encoding="utf-8")
        self.assertIn(seven_ab.by_id("mem-money")["memory"], ctx)
        self.assertEqual((row["sub_ae_usd"], row["review_ae_usd"], row["sub_tokens"]), (0.002, 0.001, 105))
        self.assertEqual(row["ccx_ok"], True)
        self.assertEqual(verdicts, [("r1", True)])
        self.assertAlmostEqual(seven_ab.unit_usd(row), 0.003)


    @unittest.skipUnless(HAS_PYTEST, "pytest is needed to score the task")
    def test_hub_memory_unit_with_real_ccx(self):
        """hubmem: the note goes into a throwaway hub only, and real ccx carries it into the sub-agent's brief."""
        import os
        tmp = Path(tempfile.mkdtemp())
        fakes = Path(__file__).resolve().parent / "fakes"
        env = {"CCX_CODEX_BIN": str(fakes / "fake_codex.py"), "CCX_CLAUDE_BIN": str(fakes / "fake_claude.py"),
               "CODEX_HOME": str(tmp / "codex"), "CLAUDE_CONFIG_DIR": str(tmp / "claude"),
               "CCX_CONFIG": str(tmp / "user-config.toml"), "FAKE_LOG": str(tmp / "calls.jsonl"),
               "CCX_HUB": str(tmp / "persons-hub"), "CCX_AB_RATE": "0", "CCX_NO_BENCH_REFRESH": "1",
               "CCX_NO_QUOTA_PROBE": "1"}
        old = dict(os.environ)
        os.environ.update(env)
        for k in ("CCX_DEPTH", "CCX_ROLE", "CLAUDECODE", "CODEX_THREAD_ID", "CCX_LEAD_SESSION"):
            os.environ.pop(k, None)
        try:
            u = {"exp": "memory", "arm": "hubmem", "round": 1, "task": "mem-money", "slot": 0, "tag": "t",
                 "label": "eval-7c:t:memory:1:mem-money:hubmem"}
            row = seven_ab.run_direct(u, args(timeout=120), tmp / "work", [sys.executable, str(common.ROOT / "ccx.py")])
        finally:
            os.environ.clear()
            os.environ.update(old)
        note = seven_ab.by_id("mem-money")["memory"]
        self.assertTrue(row["note_in_prompt"], row)
        self.assertEqual(len(row["run_ids"]), 1)               # the ledger row was read from the eval hub
        self.assertFalse((tmp / "persons-hub").exists())       # the person's hub was never touched
        self.assertFalse((tmp / "work" / "memory-1-mem-money-hubmem" / ".ccx").exists())   # nothing in the repo
        import json
        calls = [json.loads(x) for x in (tmp / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        prompt = [c for c in calls if c["argv"][:1] == ["exec"]][-1]["prompt"]
        self.assertIn(note, prompt)
        self.assertEqual(calls[-1]["argv"][:1], ["archive"])        # the eval hub's session was archived at the end
        self.assertEqual(row["archived_sessions"], 1)


class TestStats(unittest.TestCase):
    def test_mcnemar_and_wilson(self):
        self.assertAlmostEqual(seven_ab.mcnemar_p(0, 6), 0.03125)
        self.assertEqual(seven_ab.mcnemar_p(1, 1), 1.0)
        self.assertIsNone(seven_ab.mcnemar_p(0, 0))
        lo, hi = seven_ab.wilson(3, 3)
        self.assertTrue(0.4 < lo < 0.5 and hi == 1.0)

    def test_holm(self):
        h = seven_ab.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
        self.assertEqual(h["a"], (0.01, 0.03))
        self.assertEqual(h["c"], (0.03, 0.06))
        self.assertEqual(h["b"], (0.04, 0.06))                              # monotone: never below the one before
        self.assertEqual(h["d"], (None, None))

    def test_summary(self):
        def row(task, rd, arm, ok, usd, ccx_ok=True):
            return {"tag": "t", "exp": "memory", "round": rd, "task": task, "arm": arm, "ok": ok, "wall_s": 10.0,
                    "lead": None, "sub_ae_usd": usd, "review_ae_usd": 0.0, "sub_tokens": 100, "ccx_ok": ccx_ok}
        rows = []
        for task in ("mem-errors", "mem-money"):
            for rd in (1, 2, 3):
                rows += [row(task, rd, "mem", True, 0.004), row(task, rd, "nomem", False, 0.003)]
        rows.append(row("mem-log", 1, "mem", True, 0.004))                   # unpaired: left out
        s = seven_ab.summarize(rows)["memory"]
        self.assertEqual((s["pairs"], s["ok"], s["discordant"]), (6, {"nomem": 0, "mem": 6},
                                                                 {"only_nomem": 0, "only_mem": 6}))
        self.assertAlmostEqual(s["mcnemar_p"], 0.03125)
        self.assertEqual(s["ok_diff"], 1.0)                                  # treatment minus control
        self.assertEqual(s["ccx_said_ok_but_hidden_failed"], 6)               # the nomem arm
        m = s["metrics"]["total_usd"]
        self.assertEqual((m["n_pairs"], m["n_tasks"]), (6, 2))
        self.assertAlmostEqual(m["diff_median"], 0.001)
        self.assertAlmostEqual(m["ratio_median"], 0.004 / 0.003, places=4)
        self.assertEqual(seven_ab.summarize(rows)["units"], 13)
        self.assertAlmostEqual(seven_ab.summarize(rows)["primary_holm"]["memory"]["p_holm"], 0.03125)
        hub = [row("mem-errors", rd, "hubmem", rd != 2, 0.003) | {"note_in_prompt": True} for rd in (1, 2, 3)]
        s2 = seven_ab.summarize(rows + hub)
        h = s2["memory:hubmem"]
        self.assertEqual((h["arms"], h["pairs"], h["ok"]), (["nomem", "hubmem"], 3, {"nomem": 0, "hubmem": 2}))
        self.assertEqual(h["note_in_prompt"], 3)
        self.assertEqual(s2["memory"]["pairs"], 6)                       # the primary comparison is unchanged
        self.assertNotIn("memory:hubmem", s2["primary_holm"])


if __name__ == "__main__":
    unittest.main()
