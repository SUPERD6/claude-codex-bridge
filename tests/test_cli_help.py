"""`ccx -h` groups commands by use: every command sits in exactly one group and shows up in the help."""
from __future__ import annotations

import argparse

import pytest

from ccx import cli


def _commands() -> set[str]:
    ap = cli.build_parser()
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


PENDING = {"demo"}        # grouped ahead of its PR: skipped in the help until the command is registered


def test_every_command_is_in_one_group():
    grouped = [n for _, names in cli.GROUPS for n in names]
    assert len(grouped) == len(set(grouped)), "a command is listed in two groups"
    assert set(grouped) - PENDING == _commands() - PENDING, "ungrouped: %s, unknown: %s" % (
        sorted(_commands() - set(grouped)), sorted(set(grouped) - _commands() - PENDING))


def _section(text: str, title: str) -> str:
    return text.split(NL + title + ":" + NL, 1)[1].split(NL + NL, 1)[0]


NL = "\n"


def test_groups_put_everyday_first_and_developer_last():
    text = cli.build_parser().format_help()
    titles = [t for t, _ in cli.GROUPS]
    assert titles[0] == "Everyday" and titles[-1] == "Developer" and "Advanced" in titles
    at = [text.index(NL + t + ":" + NL) for t in titles]
    assert at == sorted(at)
    every = NL + _section(text, "Everyday")
    for n in ("q", "show", "undo", "run", "setup"):
        assert NL + "  " + n + " " in every, n
    dev = _section(text, "Developer")
    assert {x.strip() for x in dev.replace(NL, ",").split(",") if x.strip()} == {
        "trial", "ab", "bench", "improve", "namecheck"}
    adv = _section(text, "Advanced")
    for n in ("where", "projects", "intake", "init", "uninstall", "repair", "agents"):
        assert "  " + n + " " in adv, n
    if "demo" not in _commands():
        assert " demo " not in text                       # not listed before it exists


@pytest.mark.parametrize("name", ["trial", "ab", "bench", "improve", "namecheck", "where", "intake", "agents"])
def test_moved_commands_are_still_callable(name):
    with pytest.raises(SystemExit) as e:
        cli.parse([name, "-h"])
    assert e.value.code == 0


def test_help_shows_every_command_and_the_new_description():
    text = cli.build_parser().format_help()
    for n in _commands():
        assert f" {n}" in text, n
    assert "DeepSeek" in text and "Claude Code <-> Codex bridge" not in text
    assert "cost-saving" not in text            # not an unconditional promise; docs/measured.md has the numbers
    assert text.startswith("usage: ccx [-h] [--version] <command> ...")


# ---- a brief after the options (r5f/r5g: `resume R --check X "fix"` exited 2 with "unrecognized arguments")
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.parametrize("argv, brief", [
    (["resume", "R", "--check", "X", "fix it"], ["fix it"]),
    (["resume", "R", "fix it", "--check", "X"], ["fix it"]),
    (["run", "--check", "pytest", "--to", "codex", "do", "it"], ["do", "it"]),
    (["run", "--check", "pytest -q", "do", "--mode", "read", "it", "now"], ["do", "it", "now"]),
    (["run", "--check=pytest -q", "do", "it"], ["do", "it"]),
    (["ask", "--to", "codex", "why", "--from", "claude", "is it slow"], ["why", "is it slow"]),
])
def test_a_brief_around_the_options_is_kept_in_order(argv, brief):
    a = cli.parse(argv)
    assert a.brief == brief
    if "--check" in argv:
        assert a.check == argv[argv.index("--check") + 1]
    if "--check=pytest -q" in argv:
        assert a.check == "pytest -q"


@pytest.mark.parametrize("argv", [
    ["resume", "R", "--chek", "X", "fix"],        # a mistyped option is still an error
    ["run", "do", "--bogus"],
    ["stats", "extra"],                           # a command without a brief takes no extra words
])
def test_unknown_options_and_stray_words_still_exit_2(argv, capsys):
    with pytest.raises(SystemExit) as e:
        cli.parse(argv)
    assert e.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


@pytest.mark.parametrize("argv, word", [   # a bare word after a free-text value is its 2nd word: never shorten a check
    (["run", "fix it", "--check", "pytest", "tests/test_x.py"], "tests/test_x.py"),
    (["resume", "R", "--check", "make", "test"], "test"),
    (["resume", "R", "fix", "--check", "X", "more"], "more"),
    (["run", "do", "--check", "pytest", "it"], "it"),
    (["run", "--check", "pytest", "tests/x.py"], "tests/x.py"),      # argparse itself would make it the brief
    (["run", "do", "--check=pytest", "it"], "it"),
    (["run", "do", "--label", "a", "b"], "b"),
])
def test_a_bare_word_after_a_one_value_option_exits_2(argv, word, capsys):
    with pytest.raises(SystemExit) as e:
        cli.parse(argv)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert repr(word) in err and "Quote a value of several words" in err


def test_a_mistyped_option_exits_2_as_a_real_process():
    ccx = Path(__file__).resolve().parent.parent / "ccx.py"
    r = subprocess.run([sys.executable, str(ccx), "resume", "R", "--chek", "X", "fix"], capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 2 and "unrecognized arguments: --chek" in r.stderr
