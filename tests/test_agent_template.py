"""I8: the adapter template and its fake run end to end, and `ccx doctor` warns on version drift."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx import doctor  # noqa: E402
from ccx.agents import NAMES, _template  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fakes" / "fake_template.py"


class TestTemplate(unittest.TestCase):
    def run_fake(self, status="done", resume=None):
        os.environ["CCX_EXAMPLE_BIN"] = str(FAKE)
        try:
            with tempfile.TemporaryDirectory() as d:
                inv = _template.ADAPTER.build(model="m1", effort="low", perm=[], cwd=Path(d), prompt="do x",
                                              run_dir=Path(d), resume_id=resume)
                r = subprocess.run(inv.argv, input=inv.stdin, capture_output=True, text=True, cwd=inv.cwd,
                                   env={**os.environ, "FAKE_STATUS": status, "FAKE_LOG": ""})
                return inv, _template.ADAPTER.parse(r.stdout, r.stderr, r.returncode, None)
        finally:
            os.environ.pop("CCX_EXAMPLE_BIN", None)

    def test_not_registered(self):
        self.assertNotIn("example", NAMES)
        self.assertEqual(_template.ADAPTER.support, "community")

    def test_build_and_parse_round_trip(self):
        inv, out = self.run_fake()
        self.assertTrue(out.ok, out.error)
        self.assertEqual(out.result["status"], "done")
        self.assertTrue(out.session_id)
        self.assertIn("JSON schema", inv.stdin)
        self.assertEqual(sum(out.usage.values()) > 0, True)
        inv, out = self.run_fake(resume="abc")
        self.assertIn("--resume", inv.argv)
        self.assertEqual(out.session_id, "abc")

    def test_quota_is_classified(self):
        _, out = self.run_fake("quota")
        self.assertFalse(out.ok)
        self.assertEqual(out.kind, "quota")


class TestVersionDrift(unittest.TestCase):
    def test_same_major_minor_is_fine(self):
        self.assertIsNone(doctor.version_drift("codex-cli 0.164.3", "0.164.0", True))
        self.assertIsNone(doctor.version_drift("2.1.309 (Claude Code)", "2.1.309", True))

    def test_official_asks_for_the_release_check(self):
        state, detail = doctor.version_drift("codex-cli 0.170.0", "0.164.0", True)
        self.assertEqual(state, "WARN")
        self.assertIn("H15", detail)
        self.assertIn("0.170", detail)

    def test_community_says_not_verified(self):
        state, detail = doctor.version_drift("0.70.1", "0.65.0", False)
        self.assertEqual(state, "WARN")
        self.assertIn("not verified", detail)

    def test_unreadable(self):
        self.assertEqual(doctor.version_drift("no idea", "0.65.0", False)[0], "Unknown")


class TestCodexPlugin(unittest.TestCase):
    def home(self, installed=False, enabled=False, ours=1):
        import json
        d = Path(self.tmp.name)
        (d / "plugins").mkdir(exist_ok=True)
        if installed:
            (d / "plugins" / "installed_plugins.json").write_text(json.dumps(
                {"version": 2, "plugins": {"codex@openai-codex": [{"scope": "user"}]}}), encoding="utf-8")
        hook = {"hooks": [{"type": "command", "command": "ccx mem delta --as claude"}]}
        st = {"hooks": {"SessionStart": [hook] * ours}}
        if enabled:
            st["enabledPlugins"] = {"codex@openai-codex": True}
        (d / "settings.json").write_text(json.dumps(st), encoding="utf-8")
        return d

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_says_nothing(self):
        self.assertIsNone(doctor.codex_plugin(self.home()))

    def test_enabled_is_info_and_says_untested(self):
        state, detail = doctor.codex_plugin(self.home(installed=True, enabled=True))
        self.assertEqual(state, "info")
        self.assertIn("once", detail)
        self.assertIn("not tested", detail)

    def test_our_hook_twice_warns(self):
        state, detail = doctor.codex_plugin(self.home(installed=True, ours=2))
        self.assertEqual(state, "WARN")
        self.assertIn("2 times", detail)
        self.assertIn("installed (not enabled)", detail)


if __name__ == "__main__":
    unittest.main()
