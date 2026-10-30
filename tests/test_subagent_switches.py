"""[subagent] switches (B3 item 3, 4, 6; config/tiers.toml): experimental, each at today's behaviour by default.
Off: what a sub-agent is started with is byte-for-byte what it was before the switches existed (the golden file was
captured from the commit before them with tests/b3_capture.py). On: exactly the intended flags, env and prompt line."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b3_capture as B  # noqa: E402

from ccx import delegate  # noqa: E402
from ccx.agents.codex import ISOLATE_SETTINGS, LEAN_TOOLS, LEAN_TOOLS_NATIVE, MEMORIES_OFF  # noqa: E402
from ccx.config import SUBAGENT_SWITCHES, subagent_switches  # noqa: E402
from ccx.prompts import CLEAN_LANG  # noqa: E402

GOLDEN = json.loads((Path(__file__).resolve().parent / "data" / "b3_golden.json").read_text(encoding="utf-8"))
CASES = {name: (to, mode, par) for name, to, mode, par in B.CASES}
CLEAN_HOME = "<TMP>/hub/ccx/agent-home"


def cap(name: str, **kw) -> dict:
    to, mode, par = CASES[name]
    return B.capture(to, mode, par, **kw)


def without(argv: list[str], seq) -> list[str]:
    """argv with the contiguous run `seq` taken out; it must be there exactly once."""
    seq = list(seq)
    hits = [i for i in range(len(argv) - len(seq) + 1) if argv[i:i + len(seq)] == seq]
    assert len(hits) == 1, (seq, argv)
    return argv[:hits[0]] + argv[hits[0] + len(seq):]


def no_agent_tool(argv: list[str]) -> list[str]:
    i = argv.index("--tools") + 1
    return argv[:i] + [",".join(t for t in argv[i].split(",") if t != "Agent")] + argv[i + 1:]


@pytest.mark.parametrize("name", sorted(CASES))
def test_off_is_what_it_was_before(name):
    got = cap(name)
    assert {k: got[k] for k in ("argv", "prompt", "env")} == GOLDEN[name]
    assert got["record"]["subagent_switches"] == SUBAGENT_SWITCHES       # recorded in run.json all the same
    assert got["record"]["ledger"] == [None]                            # the ledger row only names a changed one


@pytest.mark.parametrize("name", sorted(CASES))
def test_defaults_written_out_change_nothing(name):
    got = cap(name, subagent=dict(SUBAGENT_SWITCHES))
    assert {k: got[k] for k in ("argv", "prompt", "env")} == GOLDEN[name]


def test_switch_values_other_than_booleans_fall_back_to_the_default():
    assert subagent_switches({"subagent": {"clean": "yes", "codex_memories": 0}}) == SUBAGENT_SWITCHES
    assert subagent_switches({})["codex_memories"] is True


@pytest.mark.parametrize("name", ["codex-write", "codex-read"])
def test_codex_memories_off_adds_only_the_three_memory_settings(name):
    got = cap(name, subagent={"codex_memories": False})
    g = GOLDEN[name]
    assert without(got["argv"], MEMORIES_OFF) == g["argv"]
    assert got["prompt"] == g["prompt"] and got["env"] == g["env"]
    assert "--ignore-rules" not in got["argv"] and "features.plugins=false" not in got["argv"]
    assert got["record"]["subagent_switches"]["codex_memories"] is False
    assert got["record"]["ledger"] == [["codex_memories"]]


def test_codex_memories_off_does_not_repeat_the_isolation_settings():
    got = cap("codex-write", subagent={"codex_memories": False}, env_extra={"CCX_CODEX_ISOLATE": "1"})
    base = cap("codex-write", env_extra={"CCX_CODEX_ISOLATE": "1"})
    assert got["argv"] == base["argv"] and without(got["argv"], ISOLATE_SETTINGS)


@pytest.mark.parametrize("name", ["claude-write", "claude-read"])
def test_codex_memories_off_leaves_claude_alone(name):
    got = cap(name, subagent={"codex_memories": False})
    assert {k: got[k] for k in ("argv", "prompt", "env")} == GOLDEN[name]


def test_clean_codex_gets_an_empty_home_and_the_language_line():
    got = cap("codex-write", subagent={"clean": True})
    g = GOLDEN["codex-write"]
    assert got["argv"] == g["argv"]
    assert got["env"] == {**g["env"], "HOME": CLEAN_HOME, "USERPROFILE": CLEAN_HOME}   # CODEX_HOME stays as it was
    assert got["prompt"].count(CLEAN_LANG) == 1 and got["prompt"].replace(CLEAN_LANG, "", 1) == g["prompt"]
    assert got["record"]["ledger"] == [["clean"]]


def test_clean_claude_write_no_skills_no_user_settings_no_agent_tool():
    got = cap("claude-write", subagent={"clean": True})
    g = GOLDEN["claude-write"]
    assert "Agent" in g["argv"][g["argv"].index("--tools") + 1].split(",")
    rest = without(got["argv"], ["--setting-sources", "project,local"])
    assert rest == no_agent_tool(g["argv"]) and rest.count("--disable-slash-commands") == 1   # (T2 haiku is lean)
    assert got["env"] == g["env"]                      # a Claude sub-agent's HOME is untouched
    assert got["prompt"].replace(CLEAN_LANG, "", 1) == g["prompt"] and CLEAN_LANG in got["prompt"]


def test_clean_claude_keeps_the_agent_tool_with_parallel():
    got = cap("claude-write-parallel", subagent={"clean": True})
    g = GOLDEN["claude-write-parallel"]
    rest = without(got["argv"], ["--setting-sources", "project,local"])
    assert rest == g["argv"] and "Agent" in rest[rest.index("--tools") + 1].split(",")


def test_clean_claude_on_a_full_rung_turns_skills_off(tmp_path, monkeypatch):
    from ccx.agents.claude import claude_invocation
    for k in ("CCX_CLAUDE_NO_SKILLS", "CCX_CLAUDE_SETTING_SOURCES", "CCX_CLAUDE_SETTINGS"):
        monkeypatch.delenv(k, raising=False)
    kw = dict(model="sonnet", effort="medium", perm=[], cwd=tmp_path, prompt="x", run_dir=tmp_path)
    off, on = claude_invocation(**kw).argv, claude_invocation(**kw, clean=True).argv
    assert "--disable-slash-commands" not in off and "--setting-sources" not in off
    assert without(without(without(on, ["--disable-slash-commands"]), ["--strict-mcp-config"]),
                   ["--setting-sources", "project,local"]) == off


def test_clean_setting_sources_win_over_an_evaluation_daily_setting():
    got = cap("claude-write", subagent={"clean": True}, env_extra={"CCX_CLAUDE_SETTING_SOURCES": "user,project,local"})
    i = got["argv"].index("--setting-sources")
    assert got["argv"][i + 1] == "project,local" and got["argv"].count("--setting-sources") == 1


def test_clean_home_keeps_the_logins_where_they_were(tmp_path, monkeypatch):
    home = tmp_path / "me"
    home.mkdir()
    (home / ".gitconfig").write_text("[user]\n\tname = x\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for k in ("CODEX_HOME", "DSH_HOME", "GIT_CONFIG_GLOBAL", "CCX_AGENT_HOME"):
        monkeypatch.delenv(k, raising=False)
    env = delegate._child_env("codex", "r1", {}, clean_home=tmp_path / "empty")
    assert env["HOME"] == env["USERPROFILE"] == str(tmp_path / "empty")
    assert env["CODEX_HOME"] == str(home / ".codex") and env["DSH_HOME"] == str(home / ".dsh")
    assert env["GIT_CONFIG_GLOBAL"] == str(home / ".gitconfig")
    monkeypatch.setenv("CCX_AGENT_HOME", str(tmp_path / "eval-home"))       # clean wins over an eval's own home
    assert delegate._child_env("codex", "r1", {}, clean_home=tmp_path / "empty")["HOME"] == str(tmp_path / "empty")
    claude = delegate._child_env("claude", "r1", {}, clean_home=tmp_path / "empty")
    assert claude["HOME"] == str(home) and "GIT_CONFIG_GLOBAL" not in claude
    off = delegate._child_env("codex", "r1", {})
    assert off["HOME"] == str(tmp_path / "eval-home") and "GIT_CONFIG_GLOBAL" not in off


def test_lean_tools_on_a_write_piece():
    got = cap("codex-write", subagent={"codex_lean_tools": True})
    g = GOLDEN["codex-write"]
    assert without(got["argv"], [*LEAN_TOOLS, *LEAN_TOOLS_NATIVE]) == g["argv"]
    assert got["prompt"] == g["prompt"] and got["env"] == g["env"]
    assert 'web_search="disabled"' in got["argv"] and got["record"]["ledger"] == [["codex_lean_tools"]]


def test_lean_tools_keep_web_in_read_mode():
    got = cap("codex-read", subagent={"codex_lean_tools": True})
    assert {k: got[k] for k in ("argv", "prompt", "env")} == GOLDEN["codex-read"]


def test_lean_tools_leave_claude_alone():
    got = cap("claude-write", subagent={"codex_lean_tools": True})
    assert {k: got[k] for k in ("argv", "prompt", "env")} == GOLDEN["claude-write"]


def test_shipped_config_has_every_switch_at_its_default():
    from ccx.config import load_config
    assert subagent_switches(load_config()) == SUBAGENT_SWITCHES
    assert SUBAGENT_SWITCHES == {"codex_memories": True, "clean": False, "codex_lean_tools": False}
