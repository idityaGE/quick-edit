---
title: Install QuickEdit
description: Set up Python, FFmpeg, and QuickEdit.
---

## Requirements

- Python 3.11 or newer.
- Git.
- FFmpeg and FFprobe available on your `PATH`.
- A local video with at least one video stream and one audio stream.

QuickEdit validates these requirements before processing. It currently rejects
silent videos because speech detection and audio rendering require an audio
stream.

## Source installer

```bash
curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | bash
~/.local/bin/quickedit --version
```

The installer checks for Git, Python 3.11+, Python venv support, FFmpeg, and
FFprobe. It clones QuickEdit into `~/.local/share/quick-edit`, creates a virtual
environment there, installs the local checkout, and links `quickedit` into
`~/.local/bin`.

If your shell cannot find `quickedit` after installation, add this to your shell
profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

You can change the install location:

```bash
curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh |
  QUICKEDIT_INSTALL_DIR="$HOME/apps/quick-edit" QUICKEDIT_BIN_DIR="$HOME/bin" bash
```

## Manual source setup

```bash
git clone https://github.com/idityaGE/quick-edit.git
cd quick-edit
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
quickedit --version
```

For contributor installs, use `uv sync --all-extras` instead so development
tools and all optional providers are available.

## Optional providers

LLM editing is disabled by default. Install only the provider dependency group
you intend to use:

```bash
curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | QUICKEDIT_EXTRAS=anthropic bash
# or
curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | QUICKEDIT_EXTRAS=gemini bash
```

Set `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `GEMINI_API_KEY` in your shell;
never commit a key or `.env` file.
