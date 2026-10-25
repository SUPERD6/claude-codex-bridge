"""Every text-mode subprocess call names its encoding. Without it Python decodes with the system code page (GBK on a
Chinese Windows), and git's UTF-8 output for a path like ...\\玩 made `ccx mem delta` crash in the Codex start-up hook
(seen 2026-10-24). CI runs on UTF-8 systems, so the crash itself cannot show there: this checks the source instead."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestSubprocessEncoding(unittest.TestCase):
    def test_text_mode_calls_name_utf8(self):
        missing = []
        for f in [*(ROOT / "ccx").rglob("*.py"), *(ROOT / "skills").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]:
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                kw = {k.arg: k.value for k in n.keywords}
                text = kw.get("text") or kw.get("universal_newlines")
                if isinstance(text, ast.Constant) and text.value is True and "encoding" not in kw:
                    missing.append(f"{f.relative_to(ROOT)}:{n.lineno}")
        self.assertEqual(missing, [], "add encoding=\"utf-8\", errors=\"replace\"")


if __name__ == "__main__":
    unittest.main()
