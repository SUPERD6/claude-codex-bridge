"""The queue lock on Windows: creating a lock file that was just unlinked is denied (PermissionError, the file is
"delete pending"), not FileExistsError. That used to escape `_lock`, so a `q run` item came back as an error row
without its run (tests/test_lanes.py::test_queue_default_is_unchanged, KeyError: 'run' on Windows CI)."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccx import queue as wq
from ccx.commands import workqueue


class TestLockRetries(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.lock = wq.qdir(self.root) / "queue.lock"

    def flaky_open(self, fails, exc=PermissionError):
        real, n = os.open, {"left": fails}

        def fake(path, *a, **k):
            if Path(path) == self.lock and n["left"] > 0:
                n["left"] -= 1
                raise exc(13, "Permission denied", str(path))
            return real(path, *a, **k)
        return fake

    def test_denied_create_is_retried(self):
        with mock.patch("ccx.queue.os.open", self.flaky_open(3)):
            wq.update(self.root, "q1", status="doing")
        self.assertEqual(len(wq.load(self.root)["order"]), 0)          # an update of no item: written, ignored
        self.assertIn('"status": "doing"', (wq.qdir(self.root) / "queue.jsonl").read_text(encoding="utf-8"))
        self.assertFalse(self.lock.exists())

    def test_lasting_denial_raises(self):
        with mock.patch("ccx.queue.os.open", self.flaky_open(10 ** 6)), \
                mock.patch("ccx.queue.time.sleep", lambda s: None):
            with self.assertRaises(PermissionError):
                with wq._lock(self.root, timeout=0.05):
                    pass

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
        with wq._lock(self.root, timeout=0.05):                        # left behind: taken over after the timeout
            pass

    def test_threads_never_lose_a_write(self):
        errs, n, t = [], 150, 6

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
            row = workqueue._one(it, Path(tempfile.mkdtemp()), "claude", SimpleNamespace(), {})
        self.assertEqual(row["status"], "failed")
        self.assertIn("RuntimeError: boom", row["error"])
        self.assertIn("PermissionError", row["not_recorded"])


if __name__ == "__main__":
    unittest.main()
