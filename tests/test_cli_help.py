"""`ccx -h` groups commands by use: every command sits in exactly one group and shows up in the help."""
from __future__ import annotations

import argparse

from ccx import cli


def _commands() -> set[str]:
    ap = cli.build_parser()
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def test_every_command_is_in_one_group():
    grouped = [n for _, names in cli.GROUPS for n in names]
    assert len(grouped) == len(set(grouped)), "a command is listed in two groups"
    assert set(grouped) == _commands(), "ungrouped: %s, unknown: %s" % (
        sorted(_commands() - set(grouped)), sorted(set(grouped) - _commands()))


def test_help_shows_every_command_and_the_new_description():
    text = cli.build_parser().format_help()
    for n in _commands():
        assert f" {n}" in text, n
    assert "DeepSeek" in text and "Claude Code <-> Codex bridge" not in text
    assert text.startswith("usage: ccx [-h] [--version] <command> ...")
