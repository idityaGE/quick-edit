---
title: Install QuickEdit
description: Set up Python, FFmpeg, and QuickEdit.
---

## Requirements

- Python 3.11 or newer.
- FFmpeg and FFprobe available on your `PATH`.
- A local video with at least one video stream and one audio stream.

QuickEdit validates these requirements before processing. It currently rejects
silent videos because speech detection and audio rendering require an audio
stream.

## Install from PyPI

```bash
python -m pip install --upgrade quickedit
quickedit --version
```

For editable development installs, clone the repository and use `uv sync --all-extras`.

## Optional providers

LLM editing is disabled by default. Install only the provider you intend to use:

```bash
python -m pip install 'quickedit[anthropic]'
# or
python -m pip install 'quickedit[gemini]'
```

Set `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `GEMINI_API_KEY` in your shell;
never commit a key or `.env` file.
