"""scripts/eval/review_replay.py: the parts that run no CLI (brief parsing, tree rebuild, diff split)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "eval"))

import review_replay as R  # noqa: E402
from ccx import review  # noqa: E402


def _repo(d: Path) -> tuple[Path, str]:
    d.mkdir(parents=True)
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false"]
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    (d / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8", newline="\n")
    subprocess.run([*g, "add", "-A"], cwd=d, check=True)
    subprocess.run([*g, "commit", "-qm", "i"], cwd=d, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
    return d, base


def test_parse_brief_round_trips_review_brief():
    check = {"cmd": "python -m pytest -q tests/test_a.py", "passed": True, "exit": 0}
    text = review.brief("r1", "Make f return 2.", "changed f", "+x\n-y", 12000, check)
    b = R.parse_brief(text)
    assert (b["task"], b["summary"], b["diff"], b["cut"], b["check"]) == ("Make f return 2.", "changed f", "+x\n-y",
                                                                           False, check)
    assert review.brief("r1", b["task"], b["summary"], b["diff"], 12000, b["check"]) == text
    assert R.parse_brief(review.brief("r1", "t", "s", "", 100))["check"] is None
    assert R.parse_brief(review.brief("r1", "t", "s", "+" * 50, 10))["cut"] is True


def test_rebuild_applies_tracked_and_new_files(tmp_path):
    d, base = _repo(tmp_path / "repo")
    (d / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8", newline="\n")
    (d / "b.py").write_text("X = 1\n", encoding="utf-8", newline="\n")
    _names, diff = review.changes(d, {"base": base, "untracked": [], "repo": str(d)})
    tracked, new = R.split_diff(diff)
    assert new == {"b.py": "X = 1\n"} and "b.py" not in tracked
    out = tmp_path / "tree"
    rb = R.rebuild(out, d, base, diff, out)
    assert rb["ok"], rb
    assert (out / "a.py").read_text(encoding="utf-8") == "def f():\n    return 2\n"
    assert (out / "b.py").read_text(encoding="utf-8") == "X = 1\n"
    assert "return 2" in subprocess.run(["git", "diff"], cwd=out, capture_output=True, text=True).stdout


def test_known_finding_tests():
    t = {k: v[3] for k, v in R.KNOWN.items()}
    assert t["check_ok"]('[must] x.py:3 — recap uses check.get("ok") but the key is passed')
    assert t["caller_nameerror"]("[must] by=_caller(None) is the lead")
    assert t["paths_str"]("[must] Paths(str) -> TypeError")
    assert t["bg_path"]("[must] the --bg path has no recap")
    assert not t["bg_path"]("[must] something else")
    assert t["status_done"]("[must] recap treats status == 'done' as finished; it should read get('status')")
    # a check.get('ok') finding that quotes status=done and check_state is not this bug
    assert not t["status_done"]("[must] check.get('ok') is never set (status=done, check_state=passed)")
