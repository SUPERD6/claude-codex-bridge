"""`ccx doctor` says whether a Codex lead's sandbox lets it run `ccx run` (hub writable, network on)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccx.doctor import codex_lead_sandbox  # noqa: E402


class TestCodexLeadSandbox(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.hub = Path(self.d.name) / "hub"
        self.hub.mkdir()

    def tearDown(self):
        self.d.cleanup()

    def test_full_access_is_fine(self):
        self.assertEqual(codex_lead_sandbox('sandbox_mode = "danger-full-access"\n', self.hub)[0], "ok")

    def test_workspace_write_needs_the_hub_and_network(self):
        state, detail = codex_lead_sandbox('sandbox_mode = "workspace-write"\n', self.hub, windows=False)
        self.assertEqual(state, "WARN")
        self.assertIn("not a writable root", detail)
        self.assertIn("network_access is off", detail)
        self.assertIn(self.hub.as_posix(), detail)                   # the exact lines to add

    def test_configured_workspace_write_is_fine(self):
        cfg = (f'sandbox_mode = "workspace-write"\n[sandbox_workspace_write]\n'
               f'writable_roots = ["{self.hub.parent.as_posix()}"]\nnetwork_access = true\n')
        self.assertEqual(codex_lead_sandbox(cfg, self.hub, windows=False)[0], "ok")       # a parent of the hub counts

    def test_unset_and_read_only(self):
        state, detail = codex_lead_sandbox("", self.hub, windows=False)
        self.assertEqual(state, "WARN")
        self.assertIn("not set", detail)
        self.assertEqual(codex_lead_sandbox('sandbox_mode = "read-only"\n', self.hub, windows=False)[0], "WARN")

    def test_windows_needs_full_access(self):
        cfg = (f'sandbox_mode = "workspace-write"\n[sandbox_workspace_write]\n'
               f'writable_roots = ["{self.hub.as_posix()}"]\nnetwork_access = true\n')
        state, detail = codex_lead_sandbox(cfg, self.hub, windows=True)        # roots alone did not work there
        self.assertEqual(state, "WARN")
        self.assertIn("danger-full-access", detail)
        self.assertEqual(codex_lead_sandbox('sandbox_mode = "danger-full-access"\n', self.hub, windows=True)[0], "ok")

    def test_full_access_carries_the_safety_note(self):
        detail = codex_lead_sandbox('sandbox_mode = "danger-full-access"\n', self.hub)[1]
        self.assertIn("unsandboxed", detail)
        self.assertIn("--codex-rule", detail)

    def test_a_rule_letting_ccx_out_is_unknown_not_ok(self):
        state, detail = codex_lead_sandbox('sandbox_mode = "workspace-write"\n', self.hub, windows=True, rule=True)
        self.assertEqual(state, "Unknown")                          # docs say it works; no real run yet
        self.assertIn("not been checked on a real run", detail)
        self.assertEqual(codex_lead_sandbox('sandbox_mode = "read-only"\n', self.hub, rule=True)[0], "WARN")
        self.assertIn("--codex-rule", codex_lead_sandbox("", self.hub, windows=True)[1])

    def test_the_rule_names_this_ccx_exactly(self):
        from ccx.doctor import codex_lead_rule, codex_rule_allows
        argv = ["C:\\Py\\python.exe", "D:\\x\\ccx.py"]
        text = codex_lead_rule(argv)
        self.assertIn('pattern = ["C:\\\\Py\\\\python.exe", "D:\\\\x\\\\ccx.py", ["run", "ask", "resume", "discuss"]]', text)
        self.assertIn('decision = "allow"', text)
        rules = Path(self.d.name) / "rules"
        self.assertFalse(codex_rule_allows(rules, argv, check=lambda f, a: "allow"))      # no rules folder
        rules.mkdir()
        (rules / "ccx.rules").write_text(text, encoding="utf-8")
        seen = []
        self.assertTrue(codex_rule_allows(rules, argv, check=lambda f, a: seen.append(a) or "allow"))
        self.assertEqual(seen[0][:3], [*argv, "run"])                # asked with the lead's exact command
        self.assertFalse(codex_rule_allows(rules, argv, check=lambda f, a: None))

    def test_bad_toml_is_unknown(self):
        self.assertEqual(codex_lead_sandbox("sandbox_mode = \n", self.hub)[0], "Unknown")


if __name__ == "__main__":
    unittest.main()
