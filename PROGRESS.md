# QuickEdit - Progress Tracker

## Project: AI-Powered Video Editor for Content Creators

Automatically trims silence, filler words, false starts, tangents from recorded
videos. Adds word-level subtitles. Driven by custom LLM prompts.

---

## Architecture

```
Input Video
    |
[1] Analyze (parallel, cached)
    |- VAD: Silero VAD -> bool[] (speech per frame)
    |- Motion: OpenCV frame diff -> float[] (visual activity per frame)
    |- Transcription: faster-whisper -> word-level timestamps
    |
[2] Combine Detection Arrays
    Default: (or speech visual_activity)
    |
[3] Margin + Smoothing
    |- Expand keep regions by 0.2s
    |- Remove micro-clips, fill micro-gaps
    |
[4] LLM Semantic Pass (Claude API)
    |- Input: transcript + classifications + custom prompt
    |- Output: refined EDL
    |
[5] Build Timeline (Clip abstraction)
    |
[6] Render
    |- FFmpeg trim + concat
    |- ASS subtitles with word highlighting
    |
Final Video + SRT
```

---

## Modules

| Module | File | Status |
|---|---|---|
| VAD (Voice Activity Detection) | `src/analyze/vad.py` | done |
| Motion Detection | `src/analyze/motion.py` | done |
| Transcription | `src/analyze/transcribe.py` | done |
| Detection Combiner | `src/analyze/combine.py` | done |
| Margin Expansion | `src/edit/margin.py` | done |
| Smoothing | `src/edit/smoothing.py` | done |
| LLM Analysis | `src/edit/llm.py` | done |
| Edit Decision List | `src/edit/edl.py` | done |
| Timeline / Clips | `src/timeline/timeline.py` | done |
| Video Render | `src/render/video.py` | done |
| Subtitle Render | `src/render/subtitle.py` | done |
| Cache Layer | `src/cache/cache.py` | done |
| CLI Entry Point | `src/cli.py` | done |
| Pipeline Orchestrator | `src/pipeline.py` | done |
| Project Setup | `pyproject.toml` | done |

---

## Setup

Requires: Python 3.11+, FFmpeg, uv

```bash
cd quickedit
uv venv .venv
source .venv/bin/activate
uv pip install faster-whisper opencv-python-headless numpy anthropic click
```

For LLM-based editing, set your API key:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Usage

```bash
# Basic (silence + visual activity removal, no LLM)
python -m src.cli video.mp4 --no-llm

# DSA teaching video with LLM analysis
python -m src.cli video.mp4 --prompt-template dsa

# Custom prompt
python -m src.cli video.mp4 --prompt "Remove filler words. Keep code walkthroughs."

# Preview cuts without rendering
python -m src.cli video.mp4 --dry-run --no-llm

# Full options
python -m src.cli --help
```

---

## Tech Stack

- Python 3.11+, venv managed with uv
- faster-whisper (transcription + bundled Silero VAD)
- OpenCV (motion/visual activity detection)
- FFmpeg (video processing, subtitle burn-in)
- Anthropic Claude API (semantic transcript analysis)
- click (CLI framework)

---

## Changelog

- **Session 1**: Research phase. Decided on architecture, tech stack, pipeline.
  Studied auto-editor codebase for patterns (margin, smoothing, bool arrays,
  clip abstraction, caching, combinable detection).
- **Session 1 (continued)**: Built all core modules. Full pipeline implemented:
  - analyze: vad.py, motion.py, transcribe.py, combine.py
  - edit: margin.py, smoothing.py, llm.py, edl.py
  - timeline: timeline.py (clips, cuts, merge, JSON export)
  - render: video.py (FFmpeg concat), subtitle.py (ASS word highlight + SRT)
  - cache: cache.py (numpy + JSON caching)
  - pipeline.py: full 10-step orchestrator
  - cli.py: click-based CLI with all options

- **Session 2**: Testing, bug fixes, and polish.
  - Installed all deps (faster-whisper, opencv, anthropic, click)
  - Verified FFmpeg 7.1.2 + Python 3.14 available
  - Fixed FFmpeg concat filter ordering bug (interleaved [v0][a0] not [v0][v1])
  - All core logic unit tests pass (margin, smoothing, combine, timeline, JSON roundtrip)
  - Full pipeline tested end-to-end with synthesized speech video (espeak-ng)
  - VAD correctly detected 78.9% speech, found and cut 2.2s silence gap
  - Transcription + subtitle generation working (ASS word-highlight format)
  - Added --dry-run flag (analyze without rendering, shows cut list)
  - Added --prompt-template flag with built-in templates: dsa, tutorial, lecture
  - Added progress logging to motion analysis
  - CLI fully functional with all options

## Next Steps

- [x] Install dependencies and test with a real video
- [x] Fine-tune LLM prompt for DSA teaching videos
- [x] Add progress logging for long operations
- [x] Test subtitle word-highlighting rendering
- [x] Add --dry-run flag to preview EDL without rendering
- [ ] Test with a real-world recording (not synthesized)
- [ ] Test LLM pass with real ANTHROPIC_API_KEY
- [ ] Add support for multiple input files (batch processing)
- [ ] Add audio normalization (EBU R128)
- [ ] Add --export-timeline flag (export to Premiere/DaVinci XML)
