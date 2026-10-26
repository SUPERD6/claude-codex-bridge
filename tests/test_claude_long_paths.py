"""Claude Code cuts a project folder name longer than 200 characters to 200 plus "-<hash>"; ccx must still find the
sessions in it (round 3 lost the lead's shared context this way in a deep working directory)."""
import os
import re
from pathlib import Path

from ccx import context_share, transcript


def _slug(p: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(p.resolve()))


def _session(home: Path, folder: str, sid: str) -> Path:
    d = transcript.long_path(home / "projects", 300) / folder     # the test folder itself may be deep
    d.mkdir(parents=True)
    f = d / f"{sid}.jsonl"
    f.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n', encoding="utf-8")
    return f


def test_short_root_uses_the_plain_folder(tmp_path):
    home, root = tmp_path / "home", tmp_path / "proj"
    root.mkdir()
    f = _session(home, _slug(root), "s1")
    assert [d.name for d in transcript.claude_project_dirs(root, home)] == [f.parent.name]
    assert transcript.find_session("claude", root, set(), claude_home=home).name == f.name


def test_long_root_matches_the_cut_folder(tmp_path):
    home = tmp_path / "home"
    root = tmp_path / ("a" * 90) / ("b" * 90) / ("c" * 40)       # never created: only its name matters
    slug = _slug(root)
    assert len(slug) > transcript.CLAUDE_SLUG_MAX
    f = _session(home, slug[:transcript.CLAUDE_SLUG_MAX] + "-5epyw6", "s2")
    _session(home, "C--elsewhere", "s3")
    dirs = transcript.claude_project_dirs(root, home)
    assert [d.name for d in dirs] == [f.parent.name]
    found = transcript.find_session("claude", root, set(), claude_home=home)
    assert found is not None and found.name == "s2.jsonl"


def test_session_by_id_in_any_folder(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _session(home, "C--x-" + "y" * 220 + "-abc123", "s4")
    monkeypatch.setattr("ccx.config.claude_home", lambda: home)
    got = transcript.claude_session_file("s4", home)
    assert got is not None and got.name == "s4.jsonl"
    assert context_share.find("claude", tmp_path, "s4").name == "s4.jsonl"
    assert transcript.claude_session_file("nope", home) is None


def test_long_path_leaves_short_paths_alone(tmp_path):
    assert transcript.long_path(tmp_path) == tmp_path
    p = transcript.long_path(tmp_path, 400)
    if os.name == "nt":
        assert str(p).startswith("\\\\?\\")
    else:
        assert p == tmp_path
