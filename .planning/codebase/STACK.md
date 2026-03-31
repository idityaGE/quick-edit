# Technology Stack

**Analysis Date:** 2026-04-01

## Languages

**Primary:**
- Python 3.11+ - Core application language (all modules)

**Secondary:**
- None detected

## Runtime

**Environment:**
- Python 3.11+ (specified in `pyproject.toml` as `requires-python = ">=3.11"`)

**Package Manager:**
- pip with setuptools
- Lockfile: Not present (no `requirements.txt` or lock file)

## Frameworks

**Core:**
- Click 8.1.0+ - CLI framework (`src/cli.py`)
- NumPy 1.26.0+ - Array operations and frame-level analysis

**AI/ML:**
- faster-whisper 1.1.0+ - Speech transcription with word-level timestamps
- Anthropic SDK 0.40.0+ - Claude API for semantic analysis
- Silero VAD (via PyTorch or faster-whisper) - Voice activity detection

**Computer Vision:**
- OpenCV (opencv-python-headless) 4.9.0+ - Motion detection, frame processing

**Testing:**
- pytest 8.0.0+ (dev dependency)

**Linting:**
- ruff 0.5.0+ (dev dependency)

## Key Dependencies

**Critical:**
- `faster-whisper` - Powers transcription with word-level timestamps for subtitles and LLM analysis
- `anthropic` - Claude API client for semantic editing (filler word removal, tangent detection)
- `opencv-python-headless` - Frame differencing for visual activity detection
- `numpy` - Per-frame boolean array operations throughout pipeline

**External Tools (not in pyproject.toml but required):**
- FFmpeg - Video/audio extraction, rendering, subtitle burning (called via subprocess)
- FFprobe - Video metadata extraction (called via subprocess)

## Configuration

**Environment:**
- `ANTHROPIC_API_KEY` - Required for LLM semantic analysis (read automatically by Anthropic SDK)
- No `.env` file present; environment variables expected to be set externally

**Build:**
- `pyproject.toml` - Package configuration, dependencies, entry point
- Build backend: setuptools 68.0+

## Entry Point

**CLI Command:**
```bash
quickedit input.mp4 [options]
```

Defined in `pyproject.toml`:
```toml
[project.scripts]
quickedit = "src.cli:main"
```

## Model Configuration

**Whisper Models (configurable via `--whisper-model`):**
- `tiny` - Fastest, lowest accuracy
- `base` - Default, good balance
- `small` - Better accuracy
- `medium` - High accuracy
- `large-v3` - Best accuracy, slowest

**Claude Models (configurable via `--llm-model`):**
- Default: `claude-sonnet-4-20250514`

**Compute Types:**
- `int8` - CPU inference (default)
- `float16` - CUDA inference

## Platform Requirements

**Development:**
- Python 3.11+
- FFmpeg installed and in PATH
- Optional: CUDA for GPU-accelerated transcription

**Production:**
- Same as development
- Sufficient disk space for video processing
- ANTHROPIC_API_KEY for LLM features

---

*Stack analysis: 2026-04-01*
