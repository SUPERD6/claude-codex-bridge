"""Per-PR notes in changes/ fold into CHANGELOG.md, and the repo's own notes are well formed."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("collect_changes", ROOT / "scripts" / "collect_changes.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

LOG = "# Changelog\n\n## Unreleased\n- old entry\n\n## 0.4.0 — 2026-10-24 (x)\n- released\n"


class TestCollectChanges(unittest.TestCase):
    def repo(self, d, notes, eol="\n"):
        root = Path(d)
        (root / "changes").mkdir()
        (root / "changes" / "README.md").write_text("not a note\n", encoding="utf-8")
        for name, text in notes.items():
            (root / "changes" / name).write_text(text, encoding="utf-8")
        (root / "CHANGELOG.md").write_bytes(LOG.replace("\n", eol).encode("utf-8"))
        return root

    def test_repo_notes_are_well_formed(self):
        self.assertEqual(cc.main(["--root", str(ROOT), "--check"]), 0)

    def test_unreleased_in_pr_order(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.repo(d, {"22.md": "- twenty-two\n", "9.md": "- nine\n  more\n", "a-branch.md": "- branch\n"})
            self.assertEqual(cc.main(["--root", str(root), "--apply"]), 0)
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## Unreleased\n- old entry\n- nine\n  more\n- twenty-two\n- branch\n\n## 0.4.0", text)
            self.assertEqual([p.name for p in (root / "changes").iterdir()], ["README.md"])

    def test_release_heading_and_line_endings(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.repo(d, {"21.md": "- new\n"}, eol="\r\n")
            cc.main(["--root", str(root), "--version", "0.5.0", "--title", "t", "--date", "2026-11-01", "--apply"])
            raw = (root / "CHANGELOG.md").read_bytes().decode("utf-8")
            self.assertNotIn("\n", raw.replace("\r\n", ""))
            self.assertIn("## Unreleased\r\n\r\n## 0.5.0 — 2026-11-01 (t)\r\n- old entry\r\n- new\r\n\r\n## 0.4.0",
                          raw)

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.repo(d, {"21.md": "- new\n"})
            cc.main(["--root", str(root)])
            self.assertEqual((root / "CHANGELOG.md").read_text(encoding="utf-8"), LOG)
            self.assertTrue((root / "changes" / "21.md").exists())

    def test_bad_note_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.repo(d, {"21.md": "no bullet\n"})
            self.assertEqual(cc.main(["--root", str(root), "--apply"]), 1)
            self.assertEqual((root / "CHANGELOG.md").read_text(encoding="utf-8"), LOG)


if __name__ == "__main__":
    unittest.main()
