"""scripts/eval/seven_func.py: the undo and resume checks' verdicts against a fake `ccx`, each check's own hub (never
the person's), and the helpers (no real CLIs, no model calls)."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

EVAL = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(EVAL))

import seven_func  # noqa: E402

HAS_PYTEST = subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0

# `run` changes textutil.py and prints a run id; `undo <id> --apply` puts it back with git (or not, when BROKEN).
FAKE_CCX = textwrap.dedent('''
    import json, subprocess, sys
    from pathlib import Path
    broken, args = sys.argv[1] == "1", sys.argv[2:]
    if args[0] == "run":
        Path("textutil.py").write_text("def slugify(text):\\n    return text\\n", encoding="utf-8")
        print(json.dumps({"run_id": "r1", "ok": True}))
    elif args[0] == "undo":
        if "--apply" in args and not broken:
            subprocess.run(["git", "checkout", "--", "textutil.py"], check=True)
        print(json.dumps({"run_id": args[1], "applied": "--apply" in args}))
''')


# A fake ccx for the resume check. argv[1]: a JSON file of the files the "sub-agent" writes when resumed. `run` leaves
# the record a killed run leaves (session id, no ledger row) and hangs until killed; `task status` is slow, as scoring
# and a real status are; `task resume` continues the same session with what it inherited and writes the files.
FAKE_RESUME_CCX = textwrap.dedent('''
    import json, os, sys, time
    from pathlib import Path
    files, args = sys.argv[1], sys.argv[2:]
    runs = Path(os.environ["CCX_HUB"]) / "ccx" / "runs"
    with open(Path(os.environ["CCX_HUB"]).parent / "hubs-seen.txt", "a", encoding="utf-8") as fh:
        fh.write(os.environ["CCX_HUB"] + "\\n")
    def opt(name):
        return args[args.index(name) + 1]
    def save(rec):
        (runs / rec["run_id"]).mkdir(parents=True, exist_ok=True)
        (runs / rec["run_id"] / "run.json").write_text(json.dumps(rec), encoding="utf-8")
    if args[0] == "run":
        save({"run_id": "r-killed", "task": opt("--task"), "step": 1, "label": opt("--label"),
              "check_cmd": opt("--check"), "review_mode": opt("--review"), "session_id": "th-1", "ok": False,
              "state": "running", "ts": time.time()})
        time.sleep(120)
    elif args[:2] == ["task", "status"]:
        time.sleep(4)
        print("step 1 doing")
    elif args[:2] == ["task", "resume"]:
        prev = json.loads((runs / "r-killed" / "run.json").read_text(encoding="utf-8"))
        save({**prev, "run_id": "r-resumed", "resumed_from": "r-killed", "ok": True, "state": "done",
              "ts": time.time()})
        for name, text in json.loads(Path(files).read_text(encoding="utf-8")).items():
            Path(name).write_text(text, encoding="utf-8")
        print(json.dumps({"resumed": "r-killed", "run_id": "r-resumed", "ok": True, "status": "done"}))
''')

class TestHelpers(unittest.TestCase):
    def test_last_json_and_tree_hash(self):
        self.assertEqual(seven_func.last_json('noise\n{"a": 1}\n'), {"a": 1})
        self.assertEqual(seven_func.last_json("no json"), {})
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.py").write_text("x", encoding="utf-8")
        (tmp / ".ccx").mkdir()
        (tmp / ".ccx" / "runs.json").write_text("{}", encoding="utf-8")
        (tmp / "__pycache__").mkdir()
        (tmp / "__pycache__" / "a.pyc").write_bytes(b"\0")
        self.assertEqual(list(seven_func.tree_hash(tmp)), ["a.py"])          # .ccx and caches don't count


@unittest.skipUnless(HAS_PYTEST, "pytest is needed to score the task")
class TestUndoCheck(unittest.TestCase):
    def check(self, broken: bool) -> dict:
        tmp = Path(tempfile.mkdtemp())
        fake = tmp / "fake_ccx.py"
        fake.write_text(FAKE_CCX, encoding="utf-8")
        with mock.patch.object(seven_func, "CCX", [sys.executable, str(fake), "1" if broken else "0"]):
            return seven_func.check_undo(SimpleNamespace(), tmp / "work")

    def test_undo_restores(self):
        r = self.check(broken=False)
        self.assertEqual((r["ok"], r["changed_by_run"], r["left_different"]), (True, ["textutil.py"], []))

    def test_undo_that_leaves_changes_fails(self):
        r = self.check(broken=True)
        self.assertEqual((r["ok"], r["left_different"]), (False, ["textutil.py"]))


class TestIsolation(unittest.TestCase):
    def test_check_env_has_its_own_hub(self):
        work = Path(tempfile.mkdtemp())
        base = {"PATH": os.environ.get("PATH", ""), "CCX_HUB": str(Path.home() / ".ccx-hub"),
                "TASK_ROUTING_HOME": str(Path.home() / "x"), "TASK_SPLIT_HOME": str(Path.home() / "y")}
        env = seven_func.check_env(work, base)
        hub = Path(env["CCX_HUB"]).resolve()
        self.assertTrue(hub.is_relative_to(work.resolve()))
        self.assertNotIn(hub, seven_func.default_hubs())
        self.assertNotIn(hub, seven_func.default_hubs(base))
        self.assertFalse(any(k in env for k in seven_func.STATE_VARS))
        self.assertEqual(env["CCX_NO_QUOTA_PROBE"], "1")

    def test_guard_refuses_the_default_hub(self):
        work = Path(tempfile.mkdtemp())
        mine = Path(tempfile.mkdtemp())                     # the person's hub, as this shell's CCX_HUB names it
        cfg = Path(tempfile.mkdtemp()) / "config.toml"      # ... or as their ccx config does
        named = Path(tempfile.mkdtemp())
        cfg.write_text(f"hub = '{named.as_posix()}'\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"CCX_HUB": str(mine), "CCX_CONFIG": str(cfg)}):
            for env in ({}, {"CCX_HUB": ""}, {"CCX_HUB": str(Path.home() / ".ccx-hub")}, {"CCX_HUB": str(mine)},
                        {"CCX_HUB": str(named)}, {"CCX_HUB": str(work / "hub"), "TASK_ROUTING_HOME": str(mine)}):
                with self.assertRaises(seven_func.HubLeak, msg=env):
                    seven_func.guard(env, work)
            with self.assertRaises(seven_func.HubLeak):              # a hub somewhere else than this check's work dir
                seven_func.guard({"CCX_HUB": str(Path(tempfile.mkdtemp()) / "hub")}, work)
            env = seven_func.check_env(work)
            self.assertEqual(seven_func.guard(env, work), (work / "hub").resolve())
            with self.assertRaises(seven_func.HubLeak):              # sh never runs anything against the default hub
                seven_func.sh([sys.executable, "-c", "pass"], work, env={"PATH": os.environ.get("PATH", "")})

    def test_rows_come_from_the_check_hub_and_its_task(self):
        hub = Path(tempfile.mkdtemp()) / "hub"
        (hub / "ccx").mkdir(parents=True)
        rows = [{"run_id": "old", "label": "eval-7c:func:resume", "task": "t-old", "ts": 100},
                {"run_id": "other", "label": "eval-x", "task": "t-other", "ts": 1000},
                {"run_id": "mine", "label": "eval-7c:func:resume", "task": "t-mine", "ts": 1000},
                {"run_id": "b-old", "label": "eval-7c:func:budget:claude", "ts": 100},
                {"run_id": "b-new", "label": "eval-7c:func:budget:claude", "ts": 1000}]
        (hub / "ccx" / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        self.assertEqual([r["run_id"] for r in seven_func.task_rows(hub, "t-mine")], ["mine"])
        self.assertEqual([r["run_id"] for r in seven_func.label_rows(hub, "eval-7c:func:budget:claude", 999)],
                         ["b-new"])


@unittest.skipUnless(HAS_PYTEST, "pytest is needed to score the task")
class TestResumeCheck(unittest.TestCase):
    def check(self, files: dict) -> tuple[dict, Path]:
        tmp = Path(tempfile.mkdtemp())
        fake, sol = tmp / "fake_ccx.py", tmp / "files.json"
        fake.write_text(FAKE_RESUME_CCX, encoding="utf-8")
        sol.write_text(json.dumps(files), encoding="utf-8")
        with mock.patch.object(seven_func, "CCX", [sys.executable, str(fake), str(sol)]):
            return seven_func.check_resume(SimpleNamespace(kill_after=2.0), tmp / "work"), tmp / "work"

    def test_resume_mechanism_and_task(self):
        r, work = self.check(seven_func.by_id("inventory")["solution"])
        self.assertEqual((r["ok"], r["mechanism_ok"], r["task_ok"]), (True, True, True), r)
        self.assertEqual((r["killed_run"], r["resumed_run"], r["same_session"]), ("r-killed", "r-resumed", True))
        self.assertEqual(r["inherited"], {"label": True, "check": True, "review": True})
        self.assertLess(r["killed_after_s"], 4)                  # the kill alone, not the slow status and resume too
        self.assertIsInstance(r["resume_s"], float)
        seen = set((work / "hubs-seen.txt").read_text(encoding="utf-8").split())
        self.assertEqual({Path(h).resolve() for h in seen}, {(work / "hub").resolve()})

    def test_wrong_code_fails_the_task_not_the_mechanism(self):
        sol = dict(seven_func.by_id("inventory")["solution"])
        # what the hidden test catches and the visible one does not: remove_stock never refuses
        sol["inventory/store.py"] = sol["inventory/store.py"].replace("if n < 1 or item.qty - n < 0", "if False")
        r, _ = self.check(sol)
        self.assertEqual((r["ok"], r["mechanism_ok"], r["task_ok"]), (True, True, False), r)

    def test_visible_test_covers_low_stock(self):
        sol = dict(seven_func.by_id("inventory")["solution"])
        sol["inventory/report.py"] = sol["inventory/report.py"].replace("[i.sku for i in sorted(", "list(sorted(")
        repo = seven_func.make_repo({**seven_func.by_id("inventory"), "visible": seven_func.RESUME_VISIBLE},
                                    Path(tempfile.mkdtemp()) / "repo")
        for name, text in sol.items():
            (repo / name).write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_task.py"],
                           cwd=repo, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, r.stdout)          # low_stock returning items fails ccx's own check

if __name__ == "__main__":
    unittest.main()
