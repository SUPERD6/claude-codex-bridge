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
    text = cli.build_parser(full=True).format_help()
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
    text = cli.build_parser(full=True).format_help()
    for n in _commands():
        assert f" {n}" in text, n
    assert "DeepSeek" in text and "Claude Code <-> Codex bridge" not in text
    assert "cost-saving" not in text            # not an unconditional promise; docs/measured.md has the numbers
    assert text.startswith("usage: ccx [-h] [--version] <command> ...")


def test_default_help_is_the_persons_commands_and_all_lists_the_rest(capsys):
    """`ccx -h`: the person's groups; the agent-facing board commands left Everyday but stay listed under --all and
    callable; `ccx -h --all` (either order) prints every group."""
    short = cli.build_parser().format_help()
    every = _section(short, "Everyday")
    for n in ("peek", "board", "say", "reply"):
        assert NL + "  " + n + " " not in NL + every, n
    for t in cli.SHORT:
        assert NL + t + ":" + NL in short
    for t in ("Between agents", "Advanced", "Maintenance", "Developer"):
        assert NL + t + ":" + NL not in short
    assert "`ccx -h --all` lists" in short and "between agents (peek, board, say, reply)" in short
    for argv in (["-h", "--all"], ["--all", "-h"], ["--help", "--all"]):
        with pytest.raises(SystemExit) as e:
            cli.parse(argv)
        assert e.value.code == 0
        out = capsys.readouterr().out
        for t, _ in cli.GROUPS:
            assert NL + t + ":" + NL in out, t
        agents = _section(out, "Between agents")
        for n in ("peek", "board", "say", "reply"):
            assert "  " + n + " " in agents, n
    for n in ("peek", "board", "say", "reply"):
        with pytest.raises(SystemExit) as e:
            cli.parse([n, "-h"])
        assert e.value.code == 0


def test_run_help_puts_rubric_and_coordinator_flags_under_advanced():
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        cli.parse(["run", "-h"])
    text = buf.getvalue()
    head, adv = text.split(NL + "advanced (", 1)
    for o in ("--coupling", "--clarity", "--risk", "--novelty", "--b ", "--minutes", "--seat", "--autonomy",
              "--proposal", "--namecheck", "--quota", "--provider", "--from"):
        assert NL + "  " + o.strip() + " " in adv and NL + "  " + o.strip() + " " not in head, o
    for o in ("--to", "--mode", "--check", "--review", "--worktree", "--bg", "--model", "--effort", "--tradeoff",
              "--context"):
        assert NL + "  " + o in head, o
    a = cli.parse(["run", "--coupling", "cross", "--risk", "low", "--seat", "r", "--to", "codex", "x"])   # parses as before
    assert (a.coupling, a.risk, a.seat, a.to, a.brief) == ("cross", "low", "r", "codex", ["x"])


@pytest.mark.parametrize("argv", [["q", "--cwd", "D", "done", "q1", "--ok", "1"], ["q", "done", "q1", "--ok", "1", "--cwd", "D"],
                                  ["q", "ls", "--cwd", "D"], ["q", "--cwd", "D", "ls"], ["q", "tree", "--cwd", "D"],
                                  ["q", "run", "--cwd", "D"], ["q", "resume", "--cwd", "D"], ["q", "accept", "q1", "--cwd", "D"],
                                  ["q", "--cwd", "D", "accept", "q1"], ["q", "budget", "1", "--cwd", "D"]])
def test_q_takes_cwd_before_or_after_the_subcommand(argv):
    assert cli.parse(argv).cwd == "D"


def test_handoff_takes_deepseek_for_dsh_and_run_keeps_the_provider():
    a = cli.parse(["handoff", "--to", "deepseek", "--by", "DeepSeek"])
    assert (a.to, a.by) == ("dsh", "dsh")
    assert cli.parse(["handoff", "--to", "dsh"]).to == "dsh"
    assert cli.parse(["run", "--to", "deepseek", "x"]).to == "deepseek"        # the provider, unchanged


def test_help_text_for_verify_ok_and_reply_id(capsys):
    for argv, want in ((["verify", "-h"], "1 = right, 0 = wrong"), (["reply", "-h"], "board message number"),
                       (["reply", "-h"], "--from AGENT"), (["demo", "-h"], "made-up projects")):
        with pytest.raises(SystemExit):
            cli.parse(argv)
        assert want in capsys.readouterr().out, (argv, want)


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
