# QuickEdit

AI-powered video editor that automatically trims silence, filler words, false starts, and tangents from recorded videos. Adds word-level animated subtitles.

## Quick Start

```bash
pip install -e .
quickedit myvideo.mp4
```

## Documentation

- **USER_GUIDE.md** — Simple explanations of all settings and flags
- **REFERENCE.md** — Complete technical CLI reference

## Key Features

- **Automatic editing** — Removes dead air, filler words, mistakes, and off-topic tangents using AI
- **Speech + motion detection** — Keeps content when you talk or the screen changes
- **Smart AI brain (optional)** — LLM analyzes transcripts to make semantic editing decisions
- **Animated subtitles** — Word-by-word highlight style (TikTok/Instagram) or plain SRT
- **Fast caching** — Analysis results cached so re-runs with different settings skip redundant work

## License

MIT
