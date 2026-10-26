"""Regression tests for the review of the `ccx q` batch fixes: uncommitted work and worktrees, task-split pieces'
mode, stuck dependencies, split parents and shared files waiting for a merge, read-only `q ls`, resume of a
worktree piece, a queue in a repo subfolder (fakes only)."""
import json
import subprocess
import time
import unittest

from ccx import queue as wq
from test_queue_pipeline import QEnv

MAKE_A = 'python -c "open(\'a_done.txt\', \'w\').write(\'x\')"'
NEED_A = 'python -c "import os, sys; sys.exit(0 if os.path.exists(\'a_done.txt\') else 1)"'


def _q(*items):
    return {"items": {it["id"]: {"deps": [], **it} for it in items}, "order": [it["id"] for it in items],
            "budget_usd": None, "meta": {}}


class TestUncommittedWork(QEnv):
    def test_writers_after_a_lone_writer_see_its_uncommitted_work(self):
        # a ran alone in the project folder and left a_done.txt uncommitted; b and c (two writers) used to get
        # worktrees made from HEAD, without it, and failed. Now they share the folder, as before this change
        self.git_init()
        a = self.q("add", "a", "--brief", "write a", "--minutes", "5", "--mode", "write", "--to", "codex",
                   "--check", MAKE_A)
        b = self.q("add", "b", "--brief", "write b", "--minutes", "5", "--mode", "write", "--to", "codex",
                   "--dep", a["id"], "--check", NEED_A)
        c = self.q("add", "c", "--brief", "write c", "--minutes", "5", "--mode", "write", "--to", "codex",
                   "--dep", a["id"], "--check", NEED_A)
        out = self.q("run")
        res = {r["id"]: r for r in out["results"]}
        self.assertEqual({i: res[i]["status"] for i in res}, {a["id"]: "done", b["id"]: "done", c["id"]: "done"})
        self.assertTrue(all("worktree" not in r for r in out["results"]))
        self.assertEqual(out["shared_folder"]["ids"], [b["id"], c["id"]])

    def test_queue_files_alone_do_not_count_as_uncommitted(self):
        from ccx.commands.workqueue import _clean
        self.git_init()
        self.q("add", "x", "--brief", "look at x", "--minutes", "5")      # writes .ccx/queue/ in the project
        self.assertTrue(_clean(self.work))
        (self.work / "notes.txt").write_text("x", encoding="utf-8")
        self.assertFalse(_clean(self.work))


class TestPlanPieces(QEnv):
    def test_title_only_pieces_run_as_writers_with_a_fuller_brief(self):
        # "Disk backend" + SPLIT_HINT ("... a JSON list ...") used to read as analysis: the piece ran read-only
        self.git_init()
        out = self.plan({"title": "Add caching layer", "pieces": [
            {"id": "disk", "title": "Disk backend", "minutes": 5, "files": ["d.py"], "to": "codex"},
            {"id": "mem", "title": "Memory backend", "minutes": 5, "files": ["m.py"], "to": "codex"}]})
        self.assertIn("warnings", out)
        brief = self.items()[out["ids"]["disk"]]["brief"]
        self.assertIn("Add caching layer", brief)
        self.assertIn("d.py", brief)
        r = self.q("run")
        recs = [self.rec(x["run"]) for x in r["results"] if x.get("run")]
        self.assertEqual([x["mode"] for x in recs], ["write", "write"])

    def test_a_brief_keeps_its_own_words_and_no_warning(self):
        out = self.plan({"tasks": [{"id": "a", "brief": "look at a", "minutes": 5}]})
        self.assertNotIn("warnings", out)
        self.assertEqual(self.items()[out["added"][0]]["brief"], "look at a")

    def test_plan_id_equal_to_a_queue_id_warns(self):
        self.q("add", "x", "--brief", "look at x", "--minutes", "5")         # q1
        out = self.plan({"tasks": [{"id": "q1", "brief": "look at p", "minutes": 5},
                                   {"id": "b", "brief": "look at b", "deps": ["q1"], "minutes": 5}]})
        self.assertTrue(any("q1" in w for w in out["warnings"]))
        self.assertEqual(self.items()[out["ids"]["b"]]["deps"], [out["ids"]["q1"]])

    def test_inferred_modes_count_writers_as_they_run(self):
        self.git_init()
        self.q("add", "w", "--brief", "fix the parser", "--minutes", "5", "--to", "codex")
        self.q("add", "r", "--brief", "review the docs", "--minutes", "5", "--to", "codex")
        out = self.q("run")
        self.assertTrue(all("worktree" not in r for r in out["results"]))


class TestStuckDependency(QEnv):
    def test_a_blocked_dependency_is_reported(self):
        a = self.q("add", "a", "--brief", "look at a", "--minutes", "5", "--budget", "0")
        b = self.q("add", "b", "--brief", "look at b", "--minutes", "5", "--dep", a["id"])
        out = self.q("run")
        self.assertEqual(out["results"][0]["status"], "blocked")
        self.assertEqual(out["dep_blocked"], {b["id"]: [a["id"]]})

    def test_q_ls_shows_but_does_not_write(self):
        a = self.q("add", "a", "--brief", "look at a", "--minutes", "5")
        b = self.q("add", "b", "--brief", "look at b", "--minutes", "5", "--dep", a["id"])
        wq.update(self.work, a["id"], status="failed")                      # nothing has propagated it yet
        log = self.work / ".ccx" / "queue" / "queue.jsonl"
        before = log.read_text(encoding="utf-8")
        items = self.items()
        self.assertEqual(items[b["id"]]["status"], "dep_blocked")
        self.assertIn("fix " + a["id"], "\n".join(self.ccx("q", "tree").stdout.splitlines()))
        self.assertEqual(log.read_text(encoding="utf-8"), before)

    def test_summary_is_kept(self):
        q = _q({"id": "a", "status": "failed"}, {"id": "b", "status": "todo", "deps": ["a"], "summary": "earlier"})
        self.assertEqual(wq.view(q)["items"]["b"]["summary"], "earlier")
        self.assertEqual(wq.view(q)["items"]["b"]["status"], "dep_blocked")


class TestAcceptance(unittest.TestCase):
    def test_split_parent_waits_for_its_parts_in_worktrees(self):
        q = _q({"id": "p", "status": "done"},
               {"id": "k1", "status": "done", "parent": "p", "worktree": "/x/.ccx-worktrees/r/1"},
               {"id": "k2", "status": "done", "parent": "p"},
               {"id": "d", "status": "todo", "deps": ["p"]})
        self.assertEqual(wq.ready(q), [])
        self.assertEqual(wq.waiting(q), [{"id": "d", "on": ["k1"], "worktrees": {"k1": "/x/.ccx-worktrees/r/1"}}])
        q["items"]["k1"]["verdict"] = True
        self.assertEqual([x["id"] for x in wq.ready(q)], ["d"])

    def test_shared_file_waits_for_the_other_pieces_merge(self):
        q = _q({"id": "x", "status": "done", "files": ["a.py"], "worktree": "/w/x"},
               {"id": "y", "status": "todo", "files": ["./a.py"]},
               {"id": "z", "status": "todo", "files": ["b.py"]})
        self.assertEqual([i["id"] for i in wq.ready(q)], ["z"])
        self.assertEqual(wq.waiting(q)[0]["on"], ["x"])
        q["items"]["x"]["verdict"] = True
        self.assertEqual([i["id"] for i in wq.ready(q)], ["y", "z"])

    def test_shared_file_waits_for_an_earlier_todo_piece(self):
        q = _q({"id": "w", "status": "doing"},
               {"id": "x", "status": "todo", "deps": ["w"], "files": ["a.py"]},
               {"id": "y", "status": "todo", "files": ["a.py"]})
        self.assertEqual(wq.ready(q), [])            # y waits for x, which comes first, not side by side later

    def test_a_rerun_in_the_project_clears_the_old_worktree(self):
        from ccx.commands.workqueue import _tree_fields
        fields, sha = _tree_fields({"cwd": "/p/proj", "mode": "write"})
        self.assertEqual(fields, {"worktree": None, "branch": None, "verdict": None})
        self.assertIsNone(sha)


class TestWorktreeBranches(QEnv):
    def test_unmerged_branches_nothing_waits_on_are_listed(self):
        self.git_init()
        for i in range(2):
            self.q("add", f"w{i}", "--brief", f"write piece {i}", "--minutes", "5", "--mode", "write", "--to",
                   "codex", "--check", 'python -c "open(\'n.txt\', \'w\').write(\'x\')"')
        out = self.q("run")
        self.assertEqual(len(out["unmerged"]), 2)
        self.assertTrue(all(u["branch"].startswith("ccx/") for u in out["unmerged"]))
        self.assertIn("unmerged", self.ccx("q", "tree").stdout)

    def test_ls_gate(self):
        a = self.q("add", "a", "--brief", "look at a", "--minutes", "5")
        b = self.q("add", "b", "--brief", "look at b", "--minutes", "5", "--dep", a["id"])
        self.q("run", "--gate")
        self.assertEqual(self.q("ls", "--gate")["ready"], [])
        self.assertEqual(self.q("ls")["ready"], [b["id"]])

    def test_resume_of_a_finished_worktree_piece_keeps_its_branch(self):
        self.git_init()
        a = self.q("add", "a", "--brief", "write a", "--minutes", "5", "--mode", "write", "--to", "codex")
        b = self.q("add", "b", "--brief", "write b", "--minutes", "5", "--mode", "write", "--to", "codex",
                   "--dep", a["id"])
        wq.update(self.work, a["id"], status="doing")
        rid = time.strftime("%Y%m%d-%H%M%S") + "-wtre"
        wt = self.work.parent / ".ccx-worktrees" / self.work.name / rid
        subprocess.run(["git", "worktree", "add", "-q", "-b", f"ccx/{rid}", str(wt)], cwd=self.work, check=True,
                       capture_output=True)
        (wt / "made.txt").write_text("x", encoding="utf-8")
        d = self.hub / "ccx" / "runs" / rid
        d.mkdir(parents=True)
        (d / "run.json").write_text(json.dumps({
            "run_id": rid, "label": f"q:{a['id']}", "cwd": str(wt), "ok": True, "state": "finished", "kind": "ok",
            "mode": "write", "to": "codex", "attempts": [], "result": {"status": "done", "summary": "made it"}}),
            encoding="utf-8")
        out = self.q("resume")
        row = out["results"][0]
        self.assertEqual((row["id"], row["restored"], row["branch"]), (a["id"], "finished", f"ccx/{rid}"))
        self.assertIn("commit", row)
        self.assertEqual(out["waiting"][0]["id"], b["id"])          # b did not start without a's merge
        self.assertEqual(self.items()[b["id"]]["status"], "todo")

    def test_resume_finds_a_run_when_the_queue_is_in_a_subfolder(self):
        from ccx.commands.workqueue import _here
        self.git_init()
        sub = self.work / "pkg"
        sub.mkdir()
        wt = self.work.parent / ".ccx-worktrees" / self.work.name / "20261026-000000-abcd"
        self.assertTrue(_here(wt, sub))
        self.assertFalse(_here(self.work.parent / ".ccx-worktrees" / "other" / "x", sub))
