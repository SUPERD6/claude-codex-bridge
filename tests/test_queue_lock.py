"""The queue lock on Windows: creating a lock file that was just unlinked is denied (PermissionError, the file is
"delete pending"), not FileExistsError. That used to escape `_lock`, so a `q run` item came back as an error row
without its run (tests/test_lanes.py::test_queue_default_is_unchanged, KeyError: 'run' on Windows CI; the likely
cause, not reproduced locally). Also: the lock never waits forever, a lasting denial fails at once, a fresh lock is
never taken over, a release removes only its own lock, and a `q run` row that fails after its run keeps the run."""
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccx import queue as wq
from ccx.commands import workqueue


def _tmp(case: unittest.TestCase) -> Path:
    d = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, d, ignore_errors=True)
    return d


class TestLockRetries(unittest.TestCase):
    def setUp(self):
        self.root = _tmp(self)
        self.lock = wq.qdir(self.root) / "queue.lock"

    def flaky_open(self, fails, only_lock=True):
        real, n = os.open, {"left": fails}

        def fake(path, *a, **k):
            mine = Path(path) == self.lock if only_lock else Path(path).parent == wq.qdir(self.root)
            if mine and n["left"] > 0:
                n["left"] -= 1
                raise PermissionError(13, "Permission denied", str(path))
            return real(path, *a, **k)
        return fake

    def in_thread(self, fn, wait=5.0):
        out = {}

        def go():
            try:
                fn()
                out["ok"] = True
            except Exception as e:  # noqa: BLE001
                out["err"] = e
        th = threading.Thread(target=go, daemon=True)
        th.start()
        th.join(wait)
        self.assertFalse(th.is_alive(), "the lock kept waiting")
        return out

    def test_denied_create_is_retried_on_windows(self):
        with mock.patch.object(wq, "_WINDOWS", True), mock.patch("ccx.queue.os.open", self.flaky_open(3)):
            wq.update(self.root, "q1", status="doing")
        self.assertEqual(len(wq.load(self.root)["order"]), 0)          # an update of no item: written, ignored
        self.assertIn('"status": "doing"', (wq.qdir(self.root) / "queue.jsonl").read_text(encoding="utf-8"))
        self.assertFalse(self.lock.exists())

    def test_denied_create_raises_at_once_elsewhere(self):
        t = time.time()
        with mock.patch.object(wq, "_WINDOWS", False), mock.patch("ccx.queue.os.open", self.flaky_open(10 ** 6)):
            with self.assertRaises(PermissionError):
                with wq._lock(self.root, timeout=10):
                    pass
        self.assertLess(time.time() - t, 2)

    def test_folder_not_writable_raises_at_once_on_windows(self):
        t = time.time()                    # the default timeout: no 2 * 10 s stall when no file can be created at all
        with mock.patch.object(wq, "_WINDOWS", True), \
                mock.patch("ccx.queue.os.open", self.flaky_open(10 ** 6, only_lock=False)):
            with self.assertRaises(PermissionError):
                with wq._lock(self.root):
                    pass
        self.assertLess(time.time() - t, 2)

    def test_lasting_denial_of_the_lock_raises_after_the_deadline(self):
        t = time.time()
        with mock.patch.object(wq, "_WINDOWS", True), mock.patch("ccx.queue.os.open", self.flaky_open(10 ** 6)):
            with self.assertRaises(PermissionError):
                with wq._lock(self.root, timeout=0.2):
                    pass
        self.assertGreaterEqual(time.time() - t, 0.4)

    def test_lock_that_cannot_be_taken_over_does_not_hang(self):
        wq.qdir(self.root).mkdir(parents=True)
        self.lock.write_bytes(b"crashed")
        old = time.time() - 100
        os.utime(self.lock, (old, old))
        real = Path.unlink

        def unlink(p, *a, **k):            # held open by a hung writer (Windows): the takeover is denied
            if p == self.lock:
                raise PermissionError(13, "Permission denied", str(p))
            return real(p, *a, **k)
        with mock.patch.object(Path, "unlink", unlink):
            out = self.in_thread(lambda: wq._lock(self.root, timeout=0.2).__enter__())
        self.assertIsInstance(out.get("err"), PermissionError)

    @unittest.skipUnless(os.name == "nt", "a handle blocks deleting the file only on Windows")
    def test_real_open_handle_does_not_hang(self):
        wq.qdir(self.root).mkdir(parents=True)
        with open(self.lock, "w"):
            old = time.time() - 100
            os.utime(self.lock, (old, old))
            out = self.in_thread(lambda: wq._lock(self.root, timeout=0.2).__enter__())
        self.assertIn("err", out)

    def test_fresh_lock_is_never_taken_over(self):
        wq.qdir(self.root).mkdir(parents=True)
        self.lock.write_bytes(b"another writer")
        new = time.time() + 30             # taken just now, every time this waiter looks (fresh writers, contention)
        os.utime(self.lock, (new, new))
        with self.assertRaises(RuntimeError):     # waited past timeout, but the lock is not old: no takeover
            with wq._lock(self.root, timeout=0.2):
                pass
        self.assertEqual(self.lock.read_bytes(), b"another writer")

    def test_stale_lock_is_taken_over_at_once(self):
        wq.qdir(self.root).mkdir(parents=True)
        self.lock.write_bytes(b"crashed")
        old = time.time() - 100
        os.utime(self.lock, (old, old))
        t = time.time()
        with wq._lock(self.root, timeout=5):
            pass
        self.assertLess(time.time() - t, 2)
        self.assertFalse(self.lock.exists())

    def test_release_leaves_a_lock_that_is_no_longer_ours(self):
        with wq._lock(self.root, timeout=5):
            self.lock.write_bytes(b"the writer that took it over")
        self.assertEqual(self.lock.read_bytes(), b"the writer that took it over")

    def test_denied_release_is_retried_and_never_fails_the_write(self):
        real, n = Path.unlink, {"left": 2}

        def unlink(p, *a, **k):
            if p == self.lock and n["left"] > 0:
                n["left"] -= 1
                raise PermissionError(13, "Permission denied", str(p))
            return real(p, *a, **k)
        with mock.patch.object(Path, "unlink", unlink):
            wq.update(self.root, "q1", status="doing")
        self.assertFalse(self.lock.exists())
        with mock.patch.object(Path, "unlink", lambda p, *a, **k: (_ for _ in ()).throw(PermissionError(13, "x"))):
            wq.update(self.root, "q1", status="done")                  # the release keeps failing: still no raise
        self.assertTrue(self.lock.exists())
        old = time.time() - 100
        os.utime(self.lock, (old, old))
        with wq._lock(self.root, timeout=0.2):                         # left behind: taken over once stale
            pass

    def test_threads_never_lose_a_write(self):
        errs, n, t = [], 150, 6            # exercises the delete-pending race on Windows; plain contention elsewhere

        def work():
            for _ in range(n):
                try:
                    wq.update(self.root, "q1", status="doing")
                except Exception as e:  # noqa: BLE001
                    errs.append(repr(e))
        ts = [threading.Thread(target=work) for _ in range(t)]
        for th in ts:
            th.start()
        for th in ts:
            th.join()
        self.assertEqual(errs, [])
        lines = (wq.qdir(self.root) / "queue.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), n * t)


class TestFailedRow(unittest.TestCase):
    def test_error_row_says_status_and_why_even_if_the_write_back_fails(self):
        it = {"id": "q1", "brief": "look", "to": "codex", "mode": "read"}
        with mock.patch.object(workqueue, "resolve", side_effect=RuntimeError("boom")), \
                mock.patch.object(workqueue.wq, "update", side_effect=PermissionError(13, "denied")):
            row = workqueue._one(it, _tmp(self), "claude", SimpleNamespace(), {})
        self.assertEqual(row["status"], "failed")
        self.assertIn("RuntimeError: boom", row["error"])
        self.assertIn("PermissionError", row["not_recorded"])
        self.assertNotIn("run", row)                                   # nothing ran

    def test_failure_after_the_run_keeps_the_run_and_its_cost(self):
        root = _tmp(self)
        it = wq.add(root, "x", "look at x", to="codex", mode="read", minutes=5)
        it["cost_usd"] = 0.25
        rec = {"run_id": "r-1", "to": "codex", "ok": True, "result": "done"}
        with mock.patch.object(workqueue, "resolve", return_value=({"to": "codex"}, {})), \
                mock.patch.object(workqueue, "run", return_value=rec), \
                mock.patch.object(workqueue, "compact", return_value={"status": "done"}), \
                mock.patch.object(workqueue, "_cost", return_value=0.5), \
                mock.patch.object(workqueue, "_tree_fields", side_effect=RuntimeError("after the run")):
            row = workqueue._one(it, root, "claude", SimpleNamespace(), {})
        self.assertEqual((row["status"], row["run"]), ("failed", "r-1"))
        self.assertIn("after the run", row["error"])
        got = wq.load(root)["items"][it["id"]]
        self.assertEqual((got["status"], got["run"], got["agent"]), ("failed", "r-1", "codex"))
        self.assertAlmostEqual(got["cost_usd"], 0.75)
        self.assertAlmostEqual(wq.spent(wq.load(root)), 0.75)


if __name__ == "__main__":
    unittest.main()
