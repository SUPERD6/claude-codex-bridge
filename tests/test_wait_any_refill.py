"""Pipelining: `ccx show ID... --any [--wait]` hands back every finished run among several; `ccx q run` refills a
slot as soon as a run finishes (not wave by wave), stops starting new work when a run hit quota/rate/auth, and runs
detached with --bg. Fake CLIs or an in-process stand-in for one item's run; never a real CLI."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_adapters  # noqa: E402
from test_ccx import Env  # noqa: E402
from test_show_wait import _rec  # noqa: E402

from ccx import queue as wq  # noqa: E402
from ccx.commands import workqueue  # noqa: E402


class TestShowAny(Env):
    # tests/test_show_wait.py keeps every single-id `show --wait` test as it was; they pass unchanged
    def put(self, rec: dict) -> None:
        d = self.hub / "ccx" / "runs" / rec["run_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.json").write_text(json.dumps(rec), encoding="utf-8")

    def test_single_id_without_any_is_unchanged(self):
        rid = "20991231-140000-aaaa"
        self.put(_rec(rid))
        out = json.loads(self.ccx("show", rid).stdout)
        self.assertEqual((out["run_id"], out["status"]), (rid, "done"))
        self.assertNotIn("finished", out)
        w = json.loads(self.ccx("show", rid, "--wait", "5").stdout)
        self.assertEqual((w["run_id"], w["status"]), (rid, "done"))
        self.assertNotIn("finished", w)

    def test_any_returns_every_finished_run_and_the_running_ones(self):
        a, b, c = "20991231-150000-aaaa", "20991231-150001-bbbb", "20991231-150002-cccc"
        self.put(_rec(a))
        self.put(_rec(b, ok=False, kind="error", error="boom"))
        self.put(_rec(c, state="running", result=None, kind=None, ok=False, pid=None))
        (self.hub / "ccx" / "runs" / c / "beat").write_text(str(time.time()), encoding="utf-8")
        r = self.ccx("show", a, b, c, "--any", "--wait", "5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(sorted(x["run_id"] for x in out["finished"]), [a, b])
        self.assertTrue(all("recap" in x for x in out["finished"]))
        self.assertEqual(out["running"], [c])
        self.assertEqual(out["next"], f"ccx show {c} --any --wait")

    def test_any_waits_until_one_finishes(self):
        a, b = "20991231-160000-aaaa", "20991231-160001-bbbb"
        for rid in (a, b):
            self.put(_rec(rid, state="running", result=None, kind=None, ok=False, pid=None))
            (self.hub / "ccx" / "runs" / rid / "beat").write_text(str(time.time()), encoding="utf-8")
        t = threading.Timer(1.5, lambda: self.put(_rec(b)))
        t.start()
        try:
            out = json.loads(self.ccx("show", a, b, "--any", "--wait", "20").stdout)
        finally:
            t.join()
        self.assertEqual([x["run_id"] for x in out["finished"]], [b])
        self.assertEqual(out["running"], [a])
        self.assertGreater(out["waited_s"], 0.5)

    def test_any_without_wait_does_not_block(self):
        a = "20991231-170000-aaaa"
        self.put(_rec(a, state="running", result=None, kind=None, ok=False, pid=None))
        (self.hub / "ccx" / "runs" / a / "beat").write_text(str(time.time()), encoding="utf-8")
        out = json.loads(self.ccx("show", a, "--any").stdout)
        self.assertEqual((out["finished"], out["running"]), ([], [a]))
        self.assertLess(out["waited_s"], 1)                             # one look, no polling

    def test_running_lists_the_asked_id_while_its_fix_round_runs(self):
        first, fix = "20991231-171000-aaaa", "20991231-171500-bbbb"
        self.put(_rec(first, kind="review_issues", ok=False, review={"verdict": "issues", "issues": ["a.py:1"]}))
        self.put(_rec(fix, state="running", result=None, kind=None, ok=False, pid=None, resumed_from=first,
                      review_of=first))
        (self.hub / "ccx" / "runs" / fix / "beat").write_text(str(time.time()), encoding="utf-8")
        out = json.loads(self.ccx("show", first, "--any").stdout)
        self.assertEqual((out["finished"], out["running"]), ([], [first]))
        self.assertEqual(out["next"], f"ccx show {first} --any --wait")
        w = json.loads(self.ccx("show", first, "--wait", "0").stdout)  # single id: still names the fix round
        self.assertEqual((w["run_id"], w["status"]), (fix, "running"))

    def test_any_follows_a_review_fix_round(self):
        first, fix = "20991231-180000-aaaa", "20991231-180500-bbbb"
        self.put(_rec(first, kind="review_issues", ok=False, review={"verdict": "issues", "issues": ["a.py:1"]}))
        self.put(_rec(fix, resumed_from=first, review_of=first, review={"verdict": "pass"}))
        out = json.loads(self.ccx("show", first, "--any", "--wait", "5").stdout)
        self.assertEqual(out["finished"][0]["run_id"], fix)
        self.assertEqual(out["finished"][0]["chain"], f"{first} -> {fix}")

    def test_several_ids_without_any_fail(self):
        a, b = "20991231-190000-aaaa", "20991231-190001-bbbb"
        self.put(_rec(a))
        self.put(_rec(b))
        self.assertNotEqual(self.ccx("show", a, b).returncode, 0)


def _args(**kw):
    return SimpleNamespace(**{"once": False, **kw})


class TestRefill(unittest.TestCase):
    """The executor loop alone, with a stand-in for one item's run (how long it takes is in its brief)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.events: list[tuple[str, str, float]] = []
        self.lock = threading.Lock()
        self.kinds: dict[str, list] = {}
        self.ended: dict[str, threading.Event] = {}
        self.hold: dict[str, str] = {}               # item id -> id it waits for (ends only after that one ended)
        self.orig = workqueue._one
        workqueue._one = self.fake_one

    def tearDown(self):
        workqueue._one = self.orig
        self.tmp.cleanup()

    def _ended(self, i):
        with self.lock:
            return self.ended.setdefault(i, threading.Event())

    def fake_one(self, it, root, caller, p, cfg, warm=None, got=None):
        with self.lock:
            self.events.append(("start", it["id"], time.time()))
        wq.update(root, it["id"], status="doing")
        time.sleep(float(it["brief"]))
        if it["id"] in self.hold:                    # an order, not a timing guess (slow CI runners start late)
            self._ended(self.hold[it["id"]]).wait(10)
        rec = {"run_id": "r-" + it["id"], "attempts": [{"kind": k} for k in self.kinds.get(it["id"], [])]}
        if got is not None:
            got["rec"] = rec
        wq.update(root, it["id"], status="done", cost_usd=0.01)
        with self.lock:
            self.events.append(("end", it["id"], time.time()))
        self._ended(it["id"]).set()
        return {"id": it["id"], "status": "done", "run": rec["run_id"]}

    def add(self, sec, deps=()):
        return wq.add(self.root, "t", str(sec), deps=list(deps))["id"]

    def starts(self):
        return [i for e, i, _ in self.events if e == "start"]

    def test_a_free_slot_is_refilled_before_the_slow_run_ends(self):
        slow, fast = self.add(0.3), self.add(0.1)
        third = self.add(0.1)
        self.hold[slow] = third                      # slow ends only after the refilled third one ended
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done)
        self.assertIsNone(stop)
        t = {(e, i): ts for e, i, ts in self.events}
        self.assertLess(t[("start", third)], t[("end", slow)])          # waves would start it only after slow
        self.assertEqual(sorted(r["id"] for r in done), sorted([slow, fast, third]))
        self.assertEqual(done[-1]["id"], slow)                          # results in the order they finished

    def test_never_more_than_width_at_once(self):
        ids = [self.add(0.2) for _ in range(5)]
        workqueue._refill(_args(), self.root, "claude", None, {}, 2, [])
        live = peak = 0
        for e, _, _ in sorted(self.events, key=lambda x: (x[2], x[0] == "start")):
            live += 1 if e == "start" else -1
            peak = max(peak, live)
        self.assertLessEqual(peak, 2)
        self.assertEqual(sorted(self.starts()), sorted(ids))

    def test_a_dependent_starts_when_its_dependency_is_done(self):
        a = self.add(0.1)
        b = self.add(0.1, deps=[a])
        slow = self.add(1.0)
        workqueue._refill(_args(), self.root, "claude", None, {}, 2, [])
        t = {(e, i): ts for e, i, ts in self.events}
        self.assertLess(t[("start", b)], t[("end", slow)])

    def test_once_runs_only_what_was_ready_at_the_start(self):
        a = self.add(0.1)
        b = self.add(0.1, deps=[a])
        c, d = self.add(0.1), self.add(0.1)
        workqueue._refill(_args(once=True), self.root, "claude", None, {}, 2, [])
        self.assertEqual(sorted(self.starts()), sorted([a, c]))         # as before: ready[:width], no refill
        self.assertNotIn(b, self.starts())
        self.assertNotIn(d, self.starts())

    def test_quota_in_any_attempt_stops_new_submissions(self):
        hit = self.add(0.1)
        other = self.add(0.6)
        later = [self.add(0.1) for _ in range(3)]
        self.kinds[hit] = ["quota", "ok"]                               # fell back to another agent and succeeded
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done)
        self.assertEqual((stop["stopped"], stop["kind"], stop["run"]), ("backpressure", "quota", "r-" + hit))
        self.assertEqual(sorted(r["id"] for r in done), sorted([hit, other]))   # the run in flight finished
        self.assertTrue(all(i not in self.starts() for i in later))

    def test_several_runs_hitting_quota_at_once_stop_once(self):
        a, b = self.add(0.3), self.add(0.3)
        later = [self.add(0.1) for _ in range(3)]
        self.kinds[a] = self.kinds[b] = ["quota"]
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done)
        self.assertEqual(stop["stopped"], "backpressure")
        self.assertIn(stop["run"], ("r-" + a, "r-" + b))                 # the first one seen, not overwritten
        self.assertEqual(sorted(r["id"] for r in done), sorted([a, b]))
        self.assertTrue(all(i not in self.starts() for i in later))

    def test_backpressure_with_nothing_left_is_a_normal_finish(self):
        only = self.add(0.1)
        self.kinds[only] = ["quota", "ok"]                              # fell back and finished the last item
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done)
        out, code = workqueue._finish(self.root, done, stop)
        self.assertEqual(code, 0)
        self.assertNotIn("stopped", out)
        self.assertEqual((out["open"], out["backpressure"]["kind"]), ([], "quota"))

    def test_backpressure_with_work_left_reports_the_summary_too(self):
        hit = self.add(0.1)
        rest = self.add(0.1, deps=[hit])
        self.kinds[hit] = ["quota"]
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done)
        out, code = workqueue._finish(self.root, done, stop)
        self.assertEqual((code, out["stopped"]), (2, "backpressure"))
        self.assertEqual(out["open"], [rest])
        self.assertEqual(out["spent_usd"], 0.01)                        # counted after the run in flight finished

    def test_budget_spent_is_counted_after_the_runs_in_flight(self):
        self.add(0.1)
        wq.set_budget(self.root, 0.0)
        out, code = workqueue._finish(self.root, [], {"stopped": "budget reached", "spent_usd": -1,
                                                       "budget_usd": 0.0, "ask": "x"})
        self.assertEqual((code, out["stopped"], out["spent_usd"]), (2, "budget reached", 0.0))

    def test_lanes_try_a_skipped_item_once_too(self):
        a = self.add(0.1)

        def skip(it, root, *x, **k):
            self.events.append(("start", it["id"], time.time()))
            return {"id": it["id"], "skipped": "ask first"}
        workqueue._one = skip
        workqueue._waves(_args(), self.root, "claude", None, {}, 2, 2, [])
        self.assertEqual(self.starts(), [a])

    def test_budget_stops_before_submitting(self):
        self.add(0.1)
        wq.set_budget(self.root, 0)
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, [])
        self.assertEqual(stop["stopped"], "budget reached")
        self.assertEqual(self.starts(), [])

    def test_an_item_routing_skipped_is_not_retried_forever(self):
        a = self.add(0.1)

        def skip(it, root, *x, **k):
            self.events.append(("start", it["id"], time.time()))
            return {"id": it["id"], "skipped": "ask first"}                # stays todo, so it is still ready
        workqueue._one = skip
        workqueue._refill(_args(), self.root, "claude", None, {}, 2, [])
        self.assertEqual(self.starts(), [a])


class TestRefillWithBatchRules(unittest.TestCase):
    """Refill and lanes keep the batch rules: dep_blocked, worktrees for writers side by side, quota stops lanes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = (workqueue._one, workqueue._in_git, workqueue._clean)
        self.trees: dict[str, bool] = {}
        self.fail: set[str] = set()
        self.kinds: dict[str, list] = {}
        workqueue._one = self.fake_one

    def tearDown(self):
        workqueue._one, workqueue._in_git, workqueue._clean = self.saved
        self.tmp.cleanup()

    def fake_one(self, it, root, caller, p, cfg, warm=None, got=None, worktree=False):
        self.trees[it["id"]] = worktree
        wq.update(root, it["id"], status="doing")
        time.sleep(float(it["brief"]))
        rec = {"run_id": "r-" + it["id"], "attempts": [{"kind": k} for k in self.kinds.get(it["id"], [])]}
        if got is not None:
            got["rec"] = rec
        status = "failed" if it["id"] in self.fail else "done"
        wq.update(root, it["id"], status=status)
        return {"id": it["id"], "status": status, "run": rec["run_id"]}

    def add(self, sec, mode="read", deps=()):
        return wq.add(self.root, "t", str(sec), deps=list(deps), mode=mode)["id"]

    def test_dependents_of_a_failed_item_are_dep_blocked_not_started(self):
        a = self.add(0.1)
        b = self.add(0.1, deps=[a])
        self.fail.add(a)
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done)
        self.assertNotIn(b, self.trees)
        out, code = workqueue._finish(self.root, done, stop)
        self.assertEqual((code, out["dep_blocked"]), (0, {b: [a]}))

    def test_a_writer_started_beside_a_running_writer_gets_a_worktree(self):
        workqueue._in_git = lambda root: True
        workqueue._clean = lambda root: True
        w1 = self.add(0.8, "write")
        r = self.add(0.1, "read")
        w2 = self.add(0.1, "write")
        workqueue._refill(_args(), self.root, "claude", None, {}, 2, [])
        self.assertEqual(self.trees, {w1: False, r: False, w2: True})     # w1 started alone, w2 beside it

    def test_writers_beside_each_other_share_the_folder_when_it_is_dirty(self):
        workqueue._in_git = lambda root: True
        workqueue._clean = lambda root: False
        w1, w2 = self.add(0.2, "write"), self.add(0.2, "write")
        shared: list = []
        done: list = []
        stop = workqueue._refill(_args(), self.root, "claude", None, {}, 2, done, shared)
        self.assertEqual(self.trees, {w1: False, w2: False})
        out, _ = workqueue._finish(self.root, done, stop, False, shared)
        self.assertEqual(out["shared_folder"]["ids"], [w1, w2])

    def test_quota_stops_a_lane_before_its_next_item(self):
        a, b = self.add(0.1), self.add(0.1)
        self.kinds[a] = ["quota"]
        done: list = []
        stop = workqueue._waves(_args(), self.root, "claude", None, {}, 1, 1, done)
        self.assertEqual((stop["stopped"], stop["run"]), ("backpressure", "r-" + a))
        self.assertNotIn(b, self.trees)
        self.assertEqual(wq.load(self.root)["items"][b]["status"], "todo")


class TestRunnerLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_second_runner_is_refused_and_a_dead_ones_lock_taken_over(self):
        import io
        from contextlib import redirect_stdout
        self.assertIsNone(workqueue._claim(self.root))
        self.assertEqual(workqueue.runner(self.root)["pid"], os.getpid())
        self.assertEqual(workqueue._claim(self.root)["pid"], os.getpid())     # held by a live process
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = workqueue._run(SimpleNamespace(bg=False, q_cmd="resume"), self.root)
        self.assertEqual((code, json.loads(buf.getvalue())["stopped"]), (2, "already running"))
        workqueue._release(self.root)
        self.assertIsNone(workqueue.runner(self.root))
        (wq.qdir(self.root) / workqueue.RUNNER).write_text(json.dumps({"pid": 0}), encoding="utf-8")
        self.assertIsNone(workqueue._claim(self.root))                         # a killed runner's lock
        workqueue._release(self.root)


class TestLiveRunId(unittest.TestCase):
    """_one names the run before it starts, so `q ls` shows it (`live`) while it runs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = (workqueue.resolve, workqueue.run, workqueue.compact)

    def tearDown(self):
        workqueue.resolve, workqueue.run, workqueue.compact = self.saved
        self.tmp.cleanup()

    def test_live_id_is_the_run_id_and_cleared_after(self):
        it = wq.add(self.root, "t", "do t", minutes=5)
        seen = {}

        def fake_run(req, p):
            seen["live"] = wq.load(self.root)["items"][it["id"]].get("live")
            seen["req"] = req.run_id
            return {"run_id": req.run_id, "to": "codex", "ok": True, "attempts": []}
        workqueue.resolve = lambda spec, caller, p, cfg: ({"to": "codex"}, {})
        workqueue.run = fake_run
        workqueue.compact = lambda rec: {"status": "done", "summary": "ok"}
        res = workqueue._one(wq.load(self.root)["items"][it["id"]], self.root, "claude", None, {})
        self.assertTrue(seen["live"])
        self.assertEqual(seen["live"], seen["req"])
        self.assertEqual(res["run"], seen["live"])
        after = wq.load(self.root)["items"][it["id"]]
        self.assertEqual((after["status"], after["live"], after["run"]), ("done", None, seen["live"]))


class TestQueueBackground(test_adapters.AdapterEnv):
    def test_q_run_bg_returns_at_once_and_finishes_detached(self):
        a = self.j("q", "add", "x", "--brief", "do x", "--minutes", "5")
        out = self.j("q", "run", "--bg")
        self.assertEqual(out["state"], "started")
        self.assertTrue(out["log"].endswith(".log"))
        deadline = time.time() + 90
        status = None
        while time.time() < deadline:
            status = {i["id"]: i for i in self.j("q", "ls", "--long")["items"]}[a["id"]]["status"]
            if status in ("done", "failed"):
                break
            time.sleep(0.5)
        self.assertEqual(status, "done", Path(out["log"]).read_text(encoding="utf-8", errors="replace")
                         if Path(out["log"]).exists() else "no log")
        ls = self.j("q", "ls", "--long")
        while time.time() < deadline and ("runner" in ls or "last_run" not in ls):
            time.sleep(0.5)                 # let the detached runner finish writing before the folder is removed
            ls = self.j("q", "ls", "--long")
        self.assertNotIn("runner", ls)
        self.assertEqual(ls["last_run"]["code"], 0)
        self.assertIsNone(ls["items"][0]["live"])


if __name__ == "__main__":
    unittest.main()
