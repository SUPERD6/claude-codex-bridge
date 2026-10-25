"""No terminal windows on Windows: a process with no console (like a detached `ccx run --bg` or a hook a desktop
app runs) that imports ccx starts its children without a visible console window (reported 2026-10-25)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROBE = r"""
import ctypes, json, subprocess, sys
sys.path.insert(0, sys.argv[1])
import ccx  # noqa: F401  (installs the no-window rule when there is no console)
from ccx import winproc
child = subprocess.run([sys.executable, "-c",
    "import ctypes;k=ctypes.windll.kernel32;b=(ctypes.c_uint32*1)();"
    "print(k.GetConsoleWindow(), k.GetConsoleProcessList(b,1))"], capture_output=True, text=True)
win, users = child.stdout.split()
open(sys.argv[2], "w").write(json.dumps({"parent_has_console": winproc.has_console(),
                                         "child_window": int(win), "child_console_users": int(users)}))
"""


@unittest.skipUnless(os.name == "nt", "Windows only")
class TestNoConsoleWindows(unittest.TestCase):
    def test_children_of_a_consoleless_process_get_no_window(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            probe = Path(d) / "probe.py"
            probe.write_text(PROBE, encoding="utf-8")
            from ccx.winproc import DETACHED_PROCESS
            subprocess.Popen([sys.executable, str(probe), str(ROOT), str(out)], creationflags=DETACHED_PROCESS,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(200):
                if out.exists() and out.stat().st_size:
                    break
                time.sleep(0.1)
            got = json.loads(out.read_text())
        self.assertFalse(got["parent_has_console"])
        self.assertEqual(got["child_window"], 0)             # no visible window
        self.assertGreater(got["child_console_users"], 0)     # but a (hidden) console, so its output still works

    def test_background_flags_hide_the_console(self):
        from ccx.winproc import BACKGROUND, CREATE_NO_WINDOW, DETACHED_PROCESS
        self.assertTrue(BACKGROUND["creationflags"] & CREATE_NO_WINDOW)
        self.assertFalse(BACKGROUND["creationflags"] & DETACHED_PROCESS)

    def test_with_a_console_nothing_changes(self):
        from ccx import winproc
        self.assertTrue(winproc.has_console())        # the test runner has one
        self.assertFalse(winproc._installed)


if __name__ == "__main__":
    unittest.main()
