# QuickEdit

QuickEdit is a local-first video editing CLI. It removes silence and inactive
sections using speech and motion analysis, then can generate animated or SRT
subtitles. Optional semantic cuts use an LLM only when you explicitly enable
them.

## Demo

**Before:** `demo.mp4`

https://github.com/user-attachments/assets/e22e5336-6cb6-4203-9d0e-411609a4b312.mp4

```bash
uv run quickedit ./test-videos/demo.mp4 --subtitle-style none --motion-backend ffmpeg --vad-threshold 0.2 --motion-threshold 0.001 --overwrite -o ./test-videos/demo-edited.mp4
```

**After:** `demo-edited.mp4`

https://github.com/user-attachments/assets/5660835c-f146-469c-83ff-f6fd84a98f84.mp4

```text
Source: test-videos/demo.mp4
Original duration: 03:48.77
Output duration:   03:18.52
Time saved:        00:30.25 (13.2%)
Clips: 14
Cuts:  13

Timing:
  vad: 1.4s
  motion: 17.9s
  combine: 0.0s
  margin_smooth: 0.0s
  render: 43.3s
  total: 62.6s

Output: ./test-videos/demo-edited.mp4
```

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
- [Learn the QuickEdit CLI flow](LEARN_QUICKEDIT_CLI_FLOW.md)
- [Report a bug](https://github.com/idityaGE/quick-edit/issues/new/choose)
- [Ask a question or share an idea](https://github.com/idityaGE/quick-edit/discussions)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

[MIT](LICENSE)
