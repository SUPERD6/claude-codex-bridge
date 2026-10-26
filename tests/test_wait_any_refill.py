"""Pipelining: `ccx show ID... --any [--wait]` hands back every finished run among several; `ccx q run` refills a
slot as soon as a run finishes (not wave by wave), stops starting new work when a run hit quota/rate/auth, and runs
detached with --bg. Fake CLIs or an in-process stand-in for one item's run; never a real CLI."""
import json
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
        t0 = time.time()
        out = json.loads(self.ccx("show", a, "--any").stdout)
        self.assertEqual((out["finished"], out["running"]), ([], [a]))
        self.assertLess(time.time() - t0, 20)

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
        self.orig = workqueue._one
        workqueue._one = self.fake_one

    def tearDown(self):
        workqueue._one = self.orig
        self.tmp.cleanup()

    def fake_one(self, it, root, caller, p, cfg, warm=None, got=None):
        with self.lock:
            self.events.append(("start", it["id"], time.time()))
        wq.update(root, it["id"], status="doing")
        time.sleep(float(it["brief"]))
        rec = {"run_id": "r-" + it["id"], "attempts": [{"kind": k} for k in self.kinds.get(it["id"], [])]}
        if got is not None:
            got["rec"] = rec
        wq.update(root, it["id"], status="done", cost_usd=0.01)
        with self.lock:
            self.events.append(("end", it["id"], time.time()))
        return {"id": it["id"], "status": "done", "run": rec["run_id"]}

    def add(self, sec, deps=()):
        return wq.add(self.root, "t", str(sec), deps=list(deps))["id"]

    def starts(self):
        return [i for e, i, _ in self.events if e == "start"]

    def test_a_free_slot_is_refilled_before_the_slow_run_ends(self):
        slow, fast = self.add(1.5), self.add(0.1)
        third = self.add(0.1)
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
        self.assertEqual((stop["stopped"], stop["kind"], stop["width"]), ("backpressure", "quota", 1))
        self.assertEqual(sorted(r["id"] for r in done), sorted([hit, other]))   # the run in flight finished
        self.assertTrue(all(i not in self.starts() for i in later))

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


class TestQueueBackground(test_adapters.AdapterEnv):
    def test_q_run_bg_returns_at_once_and_finishes_detached(self):
        a = self.j("q", "add", "x", "--brief", "do x", "--minutes", "5")
        out = self.j("q", "run", "--bg")
        self.assertEqual(out["state"], "started")
        self.assertTrue(out["log"].endswith(".log"))
        deadline = time.time() + 90
        status = None
        while time.time() < deadline:
            status = {i["id"]: i for i in self.j("q", "ls")["items"]}[a["id"]]["status"]
            if status in ("done", "failed"):
                break
            time.sleep(0.5)
        self.assertEqual(status, "done", Path(out["log"]).read_text(encoding="utf-8", errors="replace")
                         if Path(out["log"]).exists() else "no log")


if __name__ == "__main__":
    unittest.main()
