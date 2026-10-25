"""`--as` (which lead) comes from the adapters: an agent is a possible lead when its adapter says can_lead."""
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ccx import runners  # noqa: E402,F401  (imported first: ccx.agents alone hits an import cycle)
from ccx import agents  # noqa: E402


class TestLeads(unittest.TestCase):
    def test_leads_are_the_adapters_that_can_lead(self):
        self.assertEqual(set(agents.leads()), {a.name for a in agents.all_adapters() if a.can_lead})
        self.assertEqual(set(agents.leads()), {"codex", "claude", "dsh"})   # Gemini: no lead wiring (not tested)

    def test_a_new_lead_needs_only_its_adapter(self):
        gem = replace(agents.get("gemini"), can_lead=True)
        real = agents.get
        with mock.patch.object(agents, "get", lambda n: gem if n == "gemini" else real(n)):
            self.assertIn("gemini", agents.leads())

    def test_as_rejects_an_agent_that_cannot_lead(self):
        for cmd in (["mem", "delta", "--as", "gemini"], ["fresh", "--as", "gemini"], ["lead", "--as", "gemini"]):
            r = subprocess.run([sys.executable, str(ROOT / "ccx.py"), *cmd], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, cmd)                         # argparse: invalid choice
            self.assertIn("invalid choice", r.stderr)


if __name__ == "__main__":
    unittest.main()
