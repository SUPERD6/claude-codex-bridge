"""namecheck: the static undefined-name check of the functions a write run changed (stdlib ast + symtable).
True positives are the two round-5 bugs (r5c `cmd_mem`, r5g `_brief_notes`), rebuilt as small fixtures; the false
positives are the ones the design review found in the first prototype. Runs use fakes only."""
import builtins
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import Env  # noqa: E402

from ccx import namecheck  # noqa: E402
from ccx.config import Paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def names(src, changed=None, removed=frozenset()):
    hits, why = namecheck.check_source(textwrap.dedent(src), "m.py", changed, removed)
    return [(h["line"], h["func"], h["name"]) for h in hits], why


# r5c 2-projects-refresh: `cmd_mem` called load_config without importing it, inside `except Exception`, so the
# tests passed; two other functions import it locally (the prototype flagged those too: 2 of its 3 hits were wrong)
R5C = """\
from __future__ import annotations
import os
from ..config import paths
from .common import _caller


def _handoff_by_model(p, root, agent, f):
    from ..config import load_config
    return load_config(p)


def cmd_mem(a):
    if a.as_ == "claude":
        try:
            p = paths()
            refresh(p, load_config(p))
        except Exception:  # noqa: BLE001
            pass
    return 0


def _lead_as(tool: str) -> str:
    from ..config import load_config
    return load_config().get("x") or tool


def refresh(p, cfg):
    return os.getpid()
"""

# r5g 1-mem-report round 1: `_caller` used in delegate.py, which never imported it (a private name, so a review
# helper that skips `_names` would have missed it)
R5G = """\
from pathlib import Path
from . import memory


def _brief_notes(p, cfg, to, brief, cwd: Path, caller: str = "unknown") -> str:
    notes = memory.for_brief(p, brief, project=cwd.name)
    if not notes:
        return ""
    memory.mark_used(p, [e["seq"] for e in notes], by=_caller(None), project=cwd.name, via="brief")
    return "notes"


def other():
    return 1
"""


class TestTruePositives(unittest.TestCase):
    def test_r5c_only_the_function_without_the_import(self):
        hits, why = names(R5C)
        self.assertIsNone(why)
        self.assertEqual(hits, [(16, "cmd_mem", "load_config")])

    def test_r5g_private_helper(self):
        self.assertEqual(names(R5G)[0], [(9, "_brief_notes", "_caller")])

    def test_only_changed_functions_count(self):
        self.assertEqual(names(R5G, changed={9})[0], [(9, "_brief_notes", "_caller")])
        self.assertEqual(names(R5G, changed={5})[0], [(9, "_brief_notes", "_caller")])   # its def line
        self.assertEqual(names(R5G, changed={14})[0], [])                                 # only other() changed

    def test_removed_module_name_counts_in_unchanged_functions(self):
        src = """\
        import os


        def f():
            return json.dumps(os.sep)
        """
        self.assertEqual(names(src, changed={1})[0], [])
        self.assertEqual(names(src, changed={1}, removed={"json"})[0], [(5, "f", "json")])

    def test_scan_finds_the_removed_import(self):
        # the change takes `import json` out of the top; f() is untouched but now raises NameError
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            w = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=w, check=True)
            (w / "m.py").write_text("import json\nimport os\n\n\ndef f():\n    return json.dumps(os.sep)\n",
                                    encoding="utf-8")
            subprocess.run([*g, "add", "m.py"], cwd=w, check=True)
            subprocess.run([*g, "commit", "-qm", "init"], cwd=w, check=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=w, capture_output=True, text=True).stdout.strip()
            (w / "m.py").write_text("import os\n\n\ndef f():\n    return json.dumps(os.sep)\n", encoding="utf-8")
            (w / "new.py").write_text("def g():\n    return undefined_here\n", encoding="utf-8")
            res = namecheck.scan(w, {"repo": str(w), "base": head, "untracked": []})
        got = sorted((h["file"], h["func"], h["name"]) for h in res["hits"])
        self.assertEqual(got, [("m.py", "f", "json"), ("new.py", "g", "undefined_here")])
        self.assertEqual(res["files"], 2)


class TestNoFalsePositives(unittest.TestCase):
    def test_candidates_are_per_function(self):
        src = """\
        def f():
            return foo


        def g():
            foo = 1
            return foo


        def outer():
            def inner():
                y = 1
                return y
            return y


        class K:
            def m(self):
                return [bar for bar in range(3)]


        def h():
            return bar
        """
        self.assertEqual(names(src)[0], [(2, "f", "foo"), (14, "outer", "y"), (23, "h", "bar")])

    def test_local_variable_annotations_are_never_evaluated(self):
        src = """\
        def f():
            y: OnlyForTypes = 1
            z: AlsoOnlyForTypes
            return y


        def g(x: "Quoted") -> "Quoted2":
            return x
        """
        self.assertEqual(names(src)[0], [])

    def test_builtins_do_not_depend_on_the_python_running_ccx(self):
        src = """\
        def f():
            return WindowsError, PythonFinalizationError, _IncompleteInputError, ExceptionGroup, aiter
        """
        self.assertEqual(names(src)[0], [])

    def test_fixed_builtins_cover_this_interpreter(self):
        # the fixed set is what keeps verdicts the same on 3.11-3.13 (CI runs each); a new one belongs in it
        if sys.version_info < (3, 15):
            self.assertEqual(set(dir(builtins)) - namecheck._BUILTINS_FIXED, set())

    def test_injected_and_guarded_names(self):
        src = """\
        import gettext
        gettext.install("app")


        def f():
            return _("hello"), get_ipython


        def g():
            try:
                return unicode
            except NameError:
                return str
        """
        self.assertEqual(names(src)[0], [])

    def test_class_body_inside_a_function(self):
        src = """\
        class K:
            def m(self):
                class Inner:
                    y = 2
                    z = y
                return Inner


        def e():
            return y
        """
        self.assertEqual(names(src)[0], [(10, "e", "y")])

    def test_method_named_top(self):
        # symtable takes any table named "top" for the module and calls its parameters global (stdlib poplib)
        src = """\
        class POP3:
            def top(self, which, howmuch):
                return self._longcmd(which, howmuch)
        """
        self.assertEqual(names(src)[0], [])

    def test_bom_is_read_like_python(self):
        hits, why = namecheck.check_source("﻿def f():\n    return undef3\n".encode("utf-8"), "b.py")
        self.assertIsNone(why)
        self.assertEqual([h["name"] for h in hits], ["undef3"])

    def test_unparsed_file_is_reported_not_failed(self):
        hits, why = names("def f(:\n    pass\n")
        self.assertEqual(hits, [])
        self.assertTrue(why.startswith("unparsed"), why)

    def test_dynamic_files_are_skipped(self):
        for src, why in [("from os import *\ndef f():\n    return path\n", "star import"),
                         ("def f():\n    globals()['late'] = 1\n    return late\n", "writes globals()"),
                         ("mod = globals()\nmod['X'] = 1\ndef f():\n    return X\n", "globals"),
                         ("exec('Y = 1')\ndef f():\n    return Y\n", "exec"),
                         ("import builtins\nbuiltins.Z = 1\ndef f():\n    return Z\n", "writes builtins"),
                         ("import cython\ndef f():\n    return lib\n", "Cython source")]:
            hits, got = names(src)
            self.assertEqual((hits, got), ([], why), src)


class TestScopes(unittest.TestCase):
    def test_future_annotations_type_checking_and_conditional_imports(self):
        src = """\
        from __future__ import annotations
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from pathlib import Path
        try:
            import tomllib
        except ImportError:
            tomllib = None


        def f(x: Path, y: NotImported) -> AlsoNot:
            global H
            H = 2
            return tomllib, Path, H
        """
        self.assertEqual(names(src)[0], [])

    def test_comprehensions_walrus_match_lambda(self):
        src = """\
        def f(x, items):
            if (n := len(items)) > 0:
                pass
            z = [i for i in items if i]
            d = {k: v for k, v in items}
            g = list(j * n for j in z)
            nested = [a for row in items for a in row]
            fn = lambda q: q + n
            match x:
                case {"k": v2}:
                    return v2, z, d, g, nested, fn
                case Point(a=b):
                    return b
            return [undef1 for _ in items], (lambda: undef2)()
        """
        self.assertEqual(names(src)[0], [(12, "f", "Point"), (14, "f", "undef1"), (14, "f", "undef2")])

    def test_comprehension_iterable_is_the_enclosing_scope(self):
        src = """\
        def f():
            return [x for x in source]
        """
        self.assertEqual(names(src)[0], [(2, "f", "source")])

    def test_nonlocal_and_method_reading_class_attribute(self):
        src = """\
        def f():
            z = 1
            def inner():
                nonlocal z
                z += 1
                return z
            class C:
                attr = 1
                def m(self):
                    return attr
            return inner, C
        """
        self.assertEqual(names(src)[0], [(10, "m", "attr")])


class TestMode(unittest.TestCase):
    def test_flag_then_config_then_warn(self):
        self.assertEqual(namecheck.mode(SimpleNamespace(namecheck=None), {}), "warn")
        self.assertEqual(namecheck.mode(SimpleNamespace(namecheck=None), {"defaults": {"namecheck": "fail"}}), "fail")
        self.assertEqual(namecheck.mode(SimpleNamespace(namecheck="off"), {"defaults": {"namecheck": "fail"}}), "off")
        self.assertEqual(namecheck.mode(SimpleNamespace(namecheck=None), {"defaults": {"namecheck": "nope"}}), "warn")

    def test_shipped_default_is_warn(self):
        from ccx.config import load_config
        self.assertEqual(load_config(Paths(ROOT / "no-hub-here")).get("defaults", {}).get("namecheck"), "warn")


class TestThisRepo(unittest.TestCase):
    def test_no_hits_on_ccx_and_tests(self):
        # the measured false-positive rate on this repo, whole files (stricter than a run, which sees changes only)
        hits = []
        for d in ("ccx", "tests"):
            for f in sorted((ROOT / d).rglob("*.py")):
                hits += namecheck.check_source(f.read_bytes(), str(f.relative_to(ROOT)))[0]
        self.assertEqual([namecheck.line(h) for h in hits], [])


class TestRuns(Env):
    BAD = "def f():\n    return helper_never_imported()\n"

    def setUp(self):
        super().setUp()
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q"], cwd=self.work, check=True)
        (self.work / "a.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*g, "add", "a.py"], cwd=self.work, check=True)
        subprocess.run([*g, "commit", "-qm", "init"], cwd=self.work, check=True)

    def go(self, content, *extra):
        env = {"FAKE_WRITE": f"{self.work / 'a.py'}={content}", "FAKE_REVIEW": "pass"}
        r = self.ccx("run", "--to", "codex", "--model", "gpt-6-luna", "--effort", "low", "--mode", "write",
                     "--no-fallback", *extra, "add f to a.py", env=env)
        self.assertIn(r.returncode, (0, 2), r.stderr)
        out = json.loads(r.stdout)
        rec = json.loads((Paths(self.hub).runs / out["run_id"] / "run.json").read_text(encoding="utf-8"))
        return out, rec

    def test_warn_by_default_shows_the_hit_and_tells_the_reviewer(self):
        out, rec = self.go(self.BAD, "--review", "on")
        self.assertEqual(rec["namecheck"]["mode"], "warn")
        self.assertEqual(out["namecheck"], ["a.py:2 f() uses undefined name 'helper_never_imported'"])
        self.assertTrue(out["ok"], out)
        self.assertNotEqual(rec.get("kind"), "check_failed")
        rev = [c for c in self.calls() if c["agent"] == "claude" and "[ccx review" in c["prompt"]]
        self.assertIn("ccx namecheck", rev[0]["prompt"])
        self.assertIn("helper_never_imported", rev[0]["prompt"])

    def test_fail_mode_fails_like_a_check_and_skips_the_command(self):
        marker = self.hub / "check-ran"
        check = f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').close()"'
        out, rec = self.go(self.BAD, "--namecheck", "fail", "--check", check)
        self.assertEqual(rec["kind"], "check_failed")
        self.assertEqual(out["check"]["cmd"], "ccx namecheck")
        self.assertFalse(out["check"]["passed"])
        self.assertEqual(rec["check"]["reason"], "namecheck")
        self.assertFalse(marker.exists())
        self.assertIn("hint", out)

    def test_clean_change_and_off(self):
        _, rec = self.go("def f():\n    return 2\n")
        self.assertEqual(rec["namecheck"]["hits"], [])
        self.assertEqual(rec["namecheck"]["files"], 1)
        out, rec = self.go(self.BAD, "--namecheck", "off")
        self.assertNotIn("namecheck", rec)
        self.assertNotIn("namecheck", out)


if __name__ == "__main__":
    unittest.main()
