"""ccx q for a batch of pieces: plans with forward dependencies, failed dependencies, the --gate, worktrees for
parallel writers, file clashes, and `ccx run --bg` refused by routing (fakes only)."""
import json
import subprocess
import time

from test_adapters import AdapterEnv

NEW_FILE = 'python -c "import uuid; open(uuid.uuid4().hex + \'.txt\', \'w\').write(\'x\')"'
FAIL = 'python -c "import sys; sys.exit(1)"'


class QEnv(AdapterEnv):
    def q(self, *args, env=None, code=0):
        return self.j("q", *args, env=env, code=code)

    def plan(self, plan, code=0):
        f = self.work / "plan.json"
        f.write_text(json.dumps(plan), encoding="utf-8")
        if code:
            r = self.ccx("q", "add", "--plan", str(f))
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
            return r.stdout + r.stderr
        return self.q("add", "--plan", str(f))

    def items(self):
        return {i["id"]: i for i in self.q("ls")["items"]}

    def git_init(self):
        for args in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                                     "-m", "init"]):
            subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True)


class TestPlan(QEnv):
    def test_task_split_pieces_with_a_forward_dependency(self):
        # "wire" names "disk", which comes later in the file: it used to be dropped, so wire ran first
        out = self.plan({"pieces": [
            {"id": "wire", "title": "wire it in", "minutes": 5, "depends_on": ["disk"], "files": ["loader.py"]},
            {"id": "api", "title": "define the api", "minutes": 5, "files": ["cache/api.py"]},
            {"id": "disk", "title": "disk backend", "minutes": 5, "depends_on": ["api"], "files": ["cache/disk.py"]}]})
        ids = out["ids"]
        self.assertEqual(out["added"], [ids["wire"], ids["api"], ids["disk"]])      # plan order
        items = self.items()
        self.assertEqual(items[ids["wire"]]["deps"], [ids["disk"]])
        self.assertEqual(items[ids["disk"]]["deps"], [ids["api"]])
        self.assertEqual(items[ids["wire"]]["files"], ["loader.py"])
        self.assertTrue(items[ids["api"]]["brief"].startswith("define the api."))  # built from the title
        self.assertIn("cache/api.py", items[ids["api"]]["brief"])
        self.assertEqual(self.q("ls")["ready"], [ids["api"]])
        res = self.q("run")["results"]
        self.assertEqual([r["id"] for r in res], [ids["api"], ids["disk"], ids["wire"]])

    def test_old_tasks_format_still_works(self):
        out = self.plan({"tasks": [{"id": "a", "brief": "look at a", "minutes": 5},
                                   {"id": "b", "brief": "look at b", "deps": ["a"], "minutes": 5}]})
        self.assertEqual(len(out["added"]), 2)
        self.assertEqual(self.items()[out["added"][1]]["deps"], [out["added"][0]])

    def test_unknown_dependency_is_an_error_and_adds_nothing(self):
        msg = self.plan({"tasks": [{"id": "a", "brief": "x", "deps": ["nope"]}]}, code=3)
        self.assertIn("a -> nope", msg)
        self.assertEqual(self.q("ls")["items"], [])

    def test_cycle_is_an_error(self):
        msg = self.plan({"pieces": [{"id": "a", "title": "a", "depends_on": ["b"]},
                                    {"id": "b", "title": "b", "depends_on": ["a"]}]}, code=3)
        self.assertIn("cycle", msg)
        self.assertEqual(self.q("ls")["items"], [])

    def test_a_plan_may_wait_on_an_item_already_queued(self):
        first = self.q("add", "x", "--brief", "look at x", "--minutes", "5")
        out = self.plan({"tasks": [{"id": "y", "brief": "look at y", "deps": [first["id"]]}]})
        self.assertEqual(self.items()[out["added"][0]]["deps"], [first["id"]])


class TestFailedDependency(QEnv):
    def test_dependents_are_dep_blocked_then_released(self):
        a = self.q("add", "a", "--brief", "look at a", "--minutes", "5", "--check", FAIL)
        b = self.q("add", "b", "--brief", "look at b", "--minutes", "5", "--dep", a["id"])
        c = self.q("add", "c", "--brief", "look at c", "--minutes", "5", "--dep", b["id"])
        out = self.q("run")
        self.assertEqual(out["results"][0]["status"], "failed")
        # transitively, and each names the piece that failed (b never ran: accepting it would be wrong)
        self.assertEqual(out["dep_blocked"], {b["id"]: [a["id"]], c["id"]: [a["id"]]})
        self.assertIn("settle", out)
        items = self.items()
        self.assertEqual((items[b["id"]]["status"], items[c["id"]]["status"]), ("dep_blocked", "dep_blocked"))
        # the lead fixes a itself and accepts it: the rest goes back to todo and runs
        done = self.q("done", a["id"], "--ok", "1")
        self.assertEqual(sorted(done["unblocked"]), sorted([b["id"], c["id"]]))
        out = self.q("run")
        self.assertEqual([r["id"] for r in out["results"]], [b["id"], c["id"]])
        self.assertNotIn("dep_blocked", out)

    def test_no_failure_no_new_keys(self):
        self.q("add", "a", "--brief", "look at a", "--minutes", "5")
        out = self.q("run")
        self.assertEqual(set(out), {"results", "open", "spent_usd", "tree"})       # output as before


class TestGate(QEnv):
    def test_gate_waits_for_the_verdict(self):
        a = self.q("add", "a", "--brief", "look at a", "--minutes", "5")
        b = self.q("add", "b", "--brief", "look at b", "--minutes", "5", "--dep", a["id"])
        out = self.q("run", "--gate")
        self.assertEqual([r["id"] for r in out["results"]], [a["id"]])
        self.assertEqual(out["waiting"], [{"id": b["id"], "on": [a["id"]]}])
        self.q("done", a["id"], "--ok", "1")
        out = self.q("run", "--gate")
        self.assertEqual([r["id"] for r in out["results"]], [b["id"]])

    def test_without_gate_dependents_run_at_once(self):
        a = self.q("add", "a", "--brief", "look at a", "--minutes", "5")
        b = self.q("add", "b", "--brief", "look at b", "--minutes", "5", "--dep", a["id"])
        out = self.q("run")
        self.assertEqual([r["id"] for r in out["results"]], [a["id"], b["id"]])


class TestWorktrees(QEnv):
    def test_parallel_writers_get_worktrees_and_dependents_wait(self):
        self.git_init()
        w = [self.q("add", f"w{i}", "--brief", f"write piece {i}", "--minutes", "5", "--mode", "write", "--to",
                    "codex", "--check", NEW_FILE)["id"] for i in range(2)]
        after = self.q("add", "after", "--brief", "write the glue", "--minutes", "5", "--mode", "write",
                       "--to", "codex", "--dep", w[0], "--dep", w[1])
        out = self.q("run")
        res = {r["id"]: r for r in out["results"]}
        self.assertEqual(set(res), set(w))                          # the dependent did not start on stale code
        trees = {res[i]["worktree"] for i in w}
        self.assertEqual(len(trees), 2)
        self.assertTrue(all("/.ccx-worktrees/" in t.replace("\\", "/") for t in trees))
        for i in w:
            log = subprocess.run(["git", "log", "--format=%s", "-1", res[i]["branch"]], cwd=self.work,
                                 capture_output=True, text=True).stdout
            self.assertIn(res[i]["run"], log)                       # one commit on its branch
        self.assertEqual(out["waiting"][0]["id"], after["id"])
        self.assertEqual(set(out["waiting"][0]["worktrees"]), set(w))
        for i in w:
            self.q("done", i, "--ok", "1")                          # merged by the lead, then accepted
        out = self.q("run")
        self.assertEqual([r["id"] for r in out["results"]], [after["id"]])
        self.assertNotIn("worktree", out["results"][0])             # a lone writer works in the project, as before

    def test_one_writer_and_readers_stay_in_the_project(self):
        self.git_init()
        self.q("add", "w", "--brief", "write piece", "--minutes", "5", "--mode", "write", "--to", "codex")
        self.q("add", "r", "--brief", "look at it", "--minutes", "5", "--mode", "read", "--to", "codex")
        out = self.q("run")
        self.assertTrue(all("worktree" not in r for r in out["results"]))

    def test_outside_git_writers_share_the_folder(self):
        for i in range(2):
            self.q("add", f"w{i}", "--brief", f"write piece {i}", "--minutes", "5", "--mode", "write")
        out = self.q("run")
        self.assertTrue(all(r["status"] == "done" and "worktree" not in r for r in out["results"]))

    def test_resume_finds_a_run_in_a_worktree(self):
        from ccx.commands.workqueue import _here
        root = self.work
        wt = root.parent / ".ccx-worktrees" / root.name / "20261026-000000-abcd"
        self.assertTrue(_here(root, root))
        self.assertTrue(_here(wt, root))
        self.assertFalse(_here(root.parent / "elsewhere", root))


class TestFiles(QEnv):
    def test_pieces_sharing_a_file_never_run_side_by_side(self):
        out = self.plan({"pieces": [{"id": "a", "title": "look at a", "minutes": 5, "files": ["x.py"]},
                                    {"id": "b", "title": "look at b", "minutes": 5, "files": ["./x.py"]},
                                    {"id": "c", "title": "look at c", "minutes": 5, "files": ["y.py"]}]})
        ids = out["ids"]
        first = self.q("run", "--once")
        self.assertEqual({r["id"] for r in first["results"]}, {ids["a"], ids["c"]})
        second = self.q("run", "--once")
        self.assertEqual([r["id"] for r in second["results"]], [ids["b"]])


class TestBackgroundRefused(QEnv):
    def test_bg_refused_by_routing_still_ends(self):
        out = self.j("run", "--bg", "--from", "claude", "fix typo")
        self.assertEqual(out["state"], "started")
        t0 = time.time()
        got = self.j("show", out["run_id"], "--wait", "90")
        log = self.hub / "ccx" / "runs" / out["run_id"] / "bg.log"
        self.assertEqual(got["status"], "not_delegated", log.read_text(encoding="utf-8", errors="replace")[-2000:])
        self.assertFalse(got["ok"])
        self.assertEqual(got["kind"], "not_delegated")
        self.assertLess(time.time() - t0, 85)
        self.assertEqual(self.calls(), [])                          # nobody was paid
        self.assertIn("not_delegated", self.j("show", out["run_id"])["status"])

    def test_foreground_refusal_is_unchanged(self):
        before = set((self.hub / "ccx" / "runs").glob("*")) if (self.hub / "ccx" / "runs").exists() else set()
        out = self.j("run", "--from", "claude", "fix typo")
        self.assertFalse(out["delegated"])
        after = set((self.hub / "ccx" / "runs").glob("*")) if (self.hub / "ccx" / "runs").exists() else set()
        self.assertEqual(after, before)                             # no record for a refusal in the foreground
