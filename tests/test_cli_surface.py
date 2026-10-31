"""No command or option is ever removed: tests/data/cli_surface.json froze every command path, option and
positional of `ccx` before the help was regrouped (B2). Each must still be there and still parse; `ccx advanced`
lists every group and `ccx dev <command>` runs a developer command as `ccx <command>` does."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

from ccx import cli

FROZEN = json.loads((Path(__file__).parent / "data" / "cli_surface.json").read_text(encoding="utf-8"))
NL = "\n"


def _shape(a: argparse.Action) -> list:
    """What an option parses to: dest, kind, nargs, choices, default, type (as JSON-comparable values)."""
    return [a.dest, type(a).__name__, a.nargs if not isinstance(a.nargs, int) else int(a.nargs),
            sorted(map(str, a.choices)) if a.choices else None, a.default if isinstance(
                a.default, (str, int, float, bool, type(None))) else repr(a.default),
            getattr(a.type, "__name__", None)]


def _surface() -> dict[str, dict]:
    out: dict[str, dict] = {}

    def walk(p: argparse.ArgumentParser, path: list[str]) -> None:
        out[" ".join(path)] = {
            "options": {o for a in p._actions for o in a.option_strings},
            "actions": {o: _shape(a) for a in p._actions for o in a.option_strings},
            "positionals": [a.dest for a in p._actions
                            if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]}
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                for n, sp in a.choices.items():
                    walk(sp, path + [n])
    walk(cli.build_parser(), [])
    return out


def test_every_frozen_command_option_and_positional_is_still_there():
    now = _surface()
    missing = {k for k in FROZEN if k not in now}
    assert not missing, f"commands gone: {sorted(missing)}"
    for k, v in FROZEN.items():
        gone = set(v["options"]) - now[k]["options"]
        assert not gone, f"`ccx {k}` lost {sorted(gone)}"
        for o, shape in v.get("actions", {}).items():          # moving an option to a help group changes none of it
            assert now[k]["actions"][o] == shape, (k, o)
        assert v["positionals"] == now[k]["positionals"][:len(v["positionals"])], k


# `plan` passes everything after it to task-split (add_help=False), so `ccx plan -h` is not argparse's help
OWN_HELP = {"plan"}


@pytest.mark.parametrize("path", sorted(k for k in FROZEN if k and k not in OWN_HELP))
def test_every_frozen_command_still_parses_its_help(path, capsys):
    argv = path.split() + ["-h"]
    with pytest.raises(SystemExit) as e:
        cli.parse(argv)
    assert e.value.code == 0, (argv, capsys.readouterr().err)


def test_plan_still_passes_its_words_on():
    assert cli.parse(["plan", "size", "x"]).args == ["size", "x"]


@pytest.mark.parametrize("name", cli.DEV)
def test_dev_runs_a_developer_command_as_its_own_name(name, capsys):
    for argv in (["dev", name, "-h"], [name, "-h"]):
        with pytest.raises(SystemExit) as e:
            cli.parse(argv)
        assert e.value.code == 0
    a, b = capsys.readouterr().out.split(f"usage: ccx {name}")[1:]
    assert a == b


def test_dev_keeps_the_options_of_the_command():
    a, b = cli.parse(["dev", "namecheck", "--base", "HEAD~1", "--json"]), cli.parse(["namecheck", "--base", "HEAD~1",
                                                                                      "--json"])
    assert (a.cmd, a.base, a.json, a.fn) == (b.cmd, b.base, b.json, b.fn) == ("namecheck", "HEAD~1", True, b.fn)


def test_dev_alone_lists_the_developer_commands_and_a_wrong_name_exits_2(capsys):
    assert cli.main(["dev"]) == 0
    out = capsys.readouterr().out
    for n in cli.DEV:
        assert NL + "  " + n + " " in out, n
    with pytest.raises(SystemExit) as e:
        cli.parse(["dev", "bogus"])
    assert e.value.code == 2


def test_advanced_prints_every_group_like_help_all(capsys):
    assert cli.main(["advanced"]) == 0
    out = capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.parse(["-h", "--all"])
    assert out.strip() == capsys.readouterr().out.strip()
    for t, _ in cli.GROUPS:
        assert NL + t + ":" + NL in out, t


def test_short_help_is_the_everyday_commands_only():
    short = cli.build_parser().format_help()
    every = short.split(NL + "Everyday:" + NL, 1)[1].split(NL + NL, 1)[0]
    for n in ("run", "show", "verify", "q", "ui", "mem", "setup", "doctor", "lead"):
        assert NL + "  " + n + " " in NL + every, n
    for t, _ in cli.GROUPS[1:]:
        assert NL + t + ":" + NL not in short, t
    assert "`ccx dev`" in short and "`ccx advanced`" in short
    assert "cheapest" not in short and "cost-saving" not in short


@pytest.mark.parametrize("cmd, group", [("verify", "advanced (hooks"), ("resume", "advanced (routing"),
                                        ("lead", "advanced (for hooks")])
def test_rare_options_sit_under_advanced_and_still_parse(cmd, group, capsys):
    with pytest.raises(SystemExit):
        cli.parse([cmd, "-h"])
    head, adv = capsys.readouterr().out.split(NL + group, 1)
    rare = {"verify": ("--sweep", "--sample", "--builtin", "--agent-id"), "resume": ("--tier", "--from", "--budget"),
            "lead": ("--hint", "--as")}[cmd]
    for o in rare:
        at = re.compile(r"\n  " + re.escape(o) + r"(\s|$)")         # a narrow terminal wraps right after it
        assert at.search(adv) and not at.search(head), o
    if cmd == "verify":
        a = cli.parse(["verify", "--sweep", "--after-h", "3", "--builtin", "claude-builtin:haiku:low", "--b", "2"])
        assert (a.sweep, a.after_h, a.builtin, a.b) == (True, 3.0, "claude-builtin:haiku:low", 2.0)
    elif cmd == "resume":
        a = cli.parse(["resume", "R", "--tier", "T1", "--from", "claude", "--budget", "1", "--no-escalate", "go"])
        assert (a.tier, a.caller, a.budget, a.no_escalate, a.brief) == ("T1", "claude", 1.0, True, ["go"])
    else:
        a = cli.parse(["lead", "--hint", "--as", "codex", "--threshold", "5"])
        assert (a.hint, a.as_, a.threshold) == (True, "codex", 5)
