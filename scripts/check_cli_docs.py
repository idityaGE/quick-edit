"""Fail when a documented CLI flag is no longer exposed by Click."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from click.testing import CliRunner

from quickedit.cli import main

DOC_PATH = Path("website/src/content/docs/reference/cli.md")


def check() -> list[str]:
    """Return documentation flags that are absent from ``quickedit --help``."""
    content = DOC_PATH.read_text(encoding="utf-8")
    documented_flags = set(re.findall(r"`(--[a-z0-9-]+)", content))
    help_output = CliRunner().invoke(main, ["--help"]).output
    return sorted(flag for flag in documented_flags if flag not in help_output)


if __name__ == "__main__":
    missing = check()
    if missing:
        print(f"Documented flags missing from quickedit --help: {', '.join(missing)}")
        sys.exit(1)
