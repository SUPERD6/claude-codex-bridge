"""scripts/make_shots.py: a screenshot is not written when the page shows where this machine keeps files."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("make_shots", ROOT / "scripts" / "make_shots.py")
shots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shots)


def test_leaks_finds_user_folders_either_slash_and_the_demo_folder(tmp_path):
    base = tmp_path / "ccx-demo-x"
    for text in (r"run in C:\Users\bob\proj", "run in c:/users/bob/proj", "see /home/bob/x", "see /Users/bob/x",
                 f"folder {base}"):
        assert shots.leaks(text, base), text
    assert shots.leaks("Discount codes for the shop API · $0.0051 · demo-r-ok", base) == []
