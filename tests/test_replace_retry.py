"""Windows refuses to replace (or open) a file another process has open for that moment; ccx's state files wait
instead of failing (run records, discussions, the board). Simulated: os.replace / read refused a few times."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccx import board, discuss, ledger
from ccx.config import Paths


def refuse(times, real):
    left = [times]

    def f(*a, **k):
        if left[0]:
            left[0] -= 1
            raise PermissionError(13, "Access is denied")
        return real(*a, **k)
    return f


class TestReplaceRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_replace_waits_for_a_reader(self):
        import os
        t, f = self.d / "x.tmp", self.d / "x.json"
        t.write_text("1", encoding="utf-8")
        with mock.patch("ccx.ledger.os.replace", refuse(3, os.replace)):
            ledger.replace(t, f)
        self.assertEqual(f.read_text(encoding="utf-8"), "1")

    def test_replace_gives_up_after_three_seconds(self):
        t = self.d / "x.tmp"
        t.write_text("1", encoding="utf-8")
        with mock.patch("ccx.ledger.os.replace", refuse(1000, None)), mock.patch("ccx.ledger.time.sleep"):
            with self.assertRaises(PermissionError):
                ledger.replace(t, self.d / "x.json")

    def test_discussion_state_is_saved_and_read_while_refused(self):
        import os
        p = Paths(self.d / "hub")
        d = {"id": "d1", "state": "running", "turns": []}
        with mock.patch("ccx.ledger.os.replace", refuse(2, os.replace)):
            discuss.save(p, d)                          # a background discussion's state (CI failure, PR #67)
        real = Path.read_text
        with mock.patch.object(Path, "read_text", refuse(2, real)):
            self.assertEqual(discuss.load(p, "d1")["state"], "running")

    def test_board_save_waits_too(self):
        import os
        f = self.d / "board" / "cursors.json"
        with mock.patch("ccx.ledger.os.replace", refuse(2, os.replace)):
            board._save(f, {"a": 1})
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), {"a": 1})
