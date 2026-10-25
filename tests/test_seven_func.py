"""scripts/eval/seven_func.py: the undo check's verdict against a fake `ccx` that does (or fails to do) the undo,
and the helpers (no real CLIs, no model calls)."""
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


if __name__ == "__main__":
    unittest.main()
