# QuickEdit

QuickEdit is a local-first video editing CLI. It removes silence and inactive
sections using speech and motion analysis, then can generate animated or SRT
subtitles. Optional semantic cuts use an LLM only when you explicitly enable
them.

## Install

QuickEdit is installed from source code. It requires Python 3.11+, Git, FFmpeg,
and FFprobe.

```bash
curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | bash
~/.local/bin/quickedit myvideo.mp4 --dry-run
```

Add `~/.local/bin` to your `PATH` to run `quickedit` directly.

Manual source setup:

```bash
git clone https://github.com/idityaGE/quick-edit.git
cd quick-edit
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
quickedit --version
```

Enable semantic LLM editing only when you are ready to send transcript data to
your selected provider:

```bash
curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | QUICKEDIT_EXTRAS=anthropic bash
export ANTHROPIC_API_KEY='...'
~/.local/bin/quickedit myvideo.mp4 --llm
```

## Documentation and support

- [Documentation](https://idityaGE.github.io/quick-edit/)
- [Report a bug](https://github.com/idityaGE/quick-edit/issues/new/choose)
- [Ask a question or share an idea](https://github.com/idityaGE/quick-edit/discussions)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

[MIT](LICENSE)
