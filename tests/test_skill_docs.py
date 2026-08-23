"""Every runnable ``datagokr`` command shown in a plugin SKILL.md must use flags the CLI
actually defines on that subcommand. A rename that moves a flag in cli.py but not in the
skill's copy-paste block ships a command that dies with an argparse error the moment a user
runs it -- exactly the drift that left customs (--begin -> --start) and midforecast
(--region/--base-time -> --regid/--time-forecast) non-runnable. This greps each SKILL.md's
fenced ``datagokr`` lines and asserts every long flag exists on the matching subparser."""

from __future__ import annotations

import argparse
from pathlib import Path

from pydatagokr.cli import _make_parser

_SKILLS = Path(__file__).resolve().parent.parent / "plugins" / "datagokr" / "skills"


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    """The subcommand action of ``parser``, or ``None`` if it takes no subcommand."""
    return next((action for action in parser._actions
                 if isinstance(action, argparse._SubParsersAction)), None)


def _valid_flags(tokens: list[str]) -> set[str]:
    """The long flags valid for the command path in ``tokens`` -- the option strings of the
    top parser plus each subparser the path descends into. A ``<placeholder>`` where a
    subcommand is expected descends into a representative choice (operations under one service
    share their flag set), so a documented op stands in for the real name."""
    parser = _make_parser()
    flags = {opt for action in parser._actions for opt in action.option_strings}
    subs = _subparsers(parser)
    for token in tokens:
        if subs is None:
            continue
        if token in subs.choices:
            target = subs.choices[token]
        elif token.startswith("<") and token.endswith(">"):
            target = next(iter(subs.choices.values()))
        else:
            continue
        flags |= {opt for action in target._actions for opt in action.option_strings}
        subs = _subparsers(target)
    return flags


def _documented_commands() -> list[tuple[Path, str]]:
    """Every ``datagokr ...`` line inside a SKILL.md, paired with its file for the message."""
    commands = []
    for skill in sorted(_SKILLS.glob("*/SKILL.md")):
        for line in skill.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("datagokr "):
                commands.append((skill, line.strip()))
    return commands


def test_every_skill_command_uses_flags_the_cli_defines():
    commands = _documented_commands()
    assert commands, "no datagokr commands found in any SKILL.md -- glob or layout changed"
    for skill, command in commands:
        # Optional-marker brackets are documentation, not tokens; drop them so [--json] reads
        # as the flag --json. A <placeholder> stays a token so the path can still descend.
        tokens = command.replace("[", "").replace("]", "").split()[1:]
        used = {token for token in tokens if token.startswith("--")}
        valid = _valid_flags(tokens)
        unknown = used - valid
        assert not unknown, (
            f"{skill.relative_to(_SKILLS.parent)} documents {sorted(unknown)} "
            f"which the CLI does not define for `{command}`")
