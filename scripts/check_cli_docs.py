"""Fail when the CLI reference drifts from ``quickedit --help``."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from click.testing import CliRunner

from quickedit.cli import main

DOC_PATH = Path("website/src/content/docs/reference/cli.md")
FLAG_RE = re.compile(r"--[a-z0-9][a-z0-9-]*")


def _extract_flags(text: str) -> set[str]:
    """Return long option flags mentioned in text."""
    return set(FLAG_RE.findall(text))


def check() -> list[str]:
    """Return drift messages between documented flags and ``quickedit --help``."""
    content = DOC_PATH.read_text(encoding="utf-8")
    documented_flags = _extract_flags(content)

    result = CliRunner().invoke(main, ["--help"])
    if result.exit_code != 0:
        return [f"Could not run quickedit --help: {result.output}"]
    help_flags = _extract_flags(result.output)

    errors = []
    stale = sorted(documented_flags - help_flags)
    if stale:
        errors.append(
            "Documented flags missing from quickedit --help: " + ", ".join(stale)
        )

    undocumented = sorted(help_flags - documented_flags)
    if undocumented:
        errors.append(
            "quickedit --help flags missing from CLI reference: "
            + ", ".join(undocumented)
        )

    return errors


if __name__ == "__main__":
    failures = check()
    if failures:
        print("\n".join(failures))
        sys.exit(1)
