"""The repo as a plugin marketplace (.claude-plugin/, .codex-plugin/, hooks/claude-hooks.json, bin/ccx), and `ccx sync`
leaving the Claude hooks and the bundled skills to the plugin where it is enabled."""
import json
import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ccx import ROOT, Env  # noqa: E402

import ccx  # noqa: E402
from ccx.config import Paths  # noqa: E402
from ccx.doctor import plugin_ccx  # noqa: E402
from ccx.sync import plugin_tools, sync_all  # noqa: E402


def js(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestManifests(unittest.TestCase):
    def test_versions_and_names_agree(self):
        claude, codex = js(ROOT / ".claude-plugin" / "plugin.json"), js(ROOT / ".codex-plugin" / "plugin.json")
        with open(ROOT / "pyproject.toml", "rb") as f:
            version = tomllib.load(f)["project"]["version"]
        self.assertEqual({claude["version"], codex["version"], version}, {ccx.__version__})
        market = js(ROOT / ".claude-plugin" / "marketplace.json")
        [entry] = market["plugins"]
        self.assertEqual((market["name"], entry["name"], entry["source"]), ("relayline", claude["name"], "./"))
        self.assertEqual(codex["name"], claude["name"])
        self.assertNotIn("hooks", codex)            # Codex's hooks stay with `ccx sync`
        self.assertFalse((ROOT / "hooks" / "hooks.json").exists())   # Codex would find that one by default

    def test_hooks_run_the_bundled_ccx_with_syncs_arguments(self):
        claude = js(ROOT / ".claude-plugin" / "plugin.json")
        hooks = js(ROOT / claude["hooks"])["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit"})
        cmds = {e: g["hooks"][0]["command"] for e, [g] in hooks.items()}
        for event, args in (("SessionStart", "mem delta --as claude"), ("UserPromptSubmit", "turn --as claude")):
            self.assertEqual(cmds[event], f'sh "${{CLAUDE_PLUGIN_ROOT}}/bin/ccx" {args}')

    def test_four_skills(self):
        self.assertEqual(sorted(d.name for d in (ROOT / "skills").iterdir() if (d / "SKILL.md").exists()),
                         ["agent-delegate", "task-checkpoint", "task-routing", "task-split"])

    def test_shim_keeps_lf(self):
        self.assertNotIn(b"\r\n", (ROOT / "bin" / "ccx").read_bytes())    # sh can't run a CRLF script

    @unittest.skipUnless(shutil.which("sh"), "no sh")
    def test_shim_runs_ccx(self):
        r = subprocess.run(["sh", str(ROOT / "bin" / "ccx"), "--version"], capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(ccx.__version__, r.stdout)


class TestSyncWithPlugin(Env):
    def enable_plugin(self):
        sj = self.home_claude / "settings.json"
        data = js(sj)
        data["enabledPlugins"] = {"relayline@relayline": True}
        sj.write_text(json.dumps(data), encoding="utf-8")
        ct = self.home_codex / "config.toml"
        ct.write_text(ct.read_text(encoding="utf-8") + '\n[plugins."relayline@relayline"]\nenabled = true\n',
                      encoding="utf-8")

    def test_plugin_takes_the_claude_hooks_and_bundled_skills(self):
        (self.home_codex / "config.toml").write_text('model = "x"\n', encoding="utf-8")
        (self.home_claude / "settings.json").write_text(json.dumps({"language": "zh"}), encoding="utf-8")
        p = Paths(self.hub)
        sync_all(p, apply=True, parts=["skills", "hooks"])
        self.assertIn("mem delta", (self.home_claude / "settings.json").read_text(encoding="utf-8"))
        self.assertTrue((self.home_claude / "skills" / "agent-delegate").exists())
        self.assertEqual(plugin_tools(), set())

        self.enable_plugin()
        self.assertEqual(plugin_tools(), {"claude", "codex"})
        plan = sync_all(p, apply=True, parts=["skills", "hooks"])
        self.assertTrue(any("the relayline plugin runs them" in a for a in plan.actions), plan.actions)
        self.assertEqual(js(self.home_claude / "settings.json"),
                         {"language": "zh", "enabledPlugins": {"relayline@relayline": True}})
        for home in (self.home_claude, self.home_codex):
            self.assertFalse((home / "skills" / "agent-delegate").exists())
        self.assertIn("ccx:begin hooks", (self.home_codex / "config.toml").read_text(encoding="utf-8"))

        plan = sync_all(p, apply=True, parts=["skills", "hooks"])           # nothing comes back
        self.assertIn("(skip) Claude hooks: the relayline plugin runs them", plan.actions)
        self.assertNotIn("hooks", js(self.home_claude / "settings.json"))
        self.assertFalse((self.home_claude / "skills" / "agent-delegate").exists())

    def test_disabled_plugin_changes_nothing(self):
        (self.home_claude / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"relayline@relayline": False}}), encoding="utf-8")
        self.assertEqual(plugin_tools(), set())
        sync_all(Paths(self.hub), apply=True, parts=["hooks"])
        self.assertIn("mem delta", (self.home_claude / "settings.json").read_text(encoding="utf-8"))


class TestDoctorPluginRow(Env):
    def test_ccx_installed_on_its_own_or_not(self):
        inside = str(self.home_claude / "plugins" / "cache" / "relayline" / "bin" / "ccx")
        self.assertEqual(plugin_ccx(["claude"], which=lambda _: None)[0], "WARN")
        self.assertEqual(plugin_ccx(["claude"], which=lambda _: inside)[0], "WARN")
        state, detail = plugin_ccx(["claude"], which=lambda _: "/usr/local/bin/ccx")
        self.assertEqual(state, "ok")
        self.assertIn("pipx install", plugin_ccx(["claude"], which=lambda _: None)[1])


if __name__ == "__main__":
    unittest.main()
