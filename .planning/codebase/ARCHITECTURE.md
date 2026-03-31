# Architecture

**Analysis Date:** 2026-04-01

## Pattern Overview

**Overall:** Pipeline Architecture with Layered Modules

**Key Characteristics:**
- Single-pass orchestrator (`pipeline.py`) coordinates all processing stages
- Functional modules with clear input/output contracts (numpy arrays, dataclasses)
- Per-frame boolean arrays as the universal representation for keep/cut decisions
- Configurable composition via expression-based detection combinator
- LLM-enhanced semantic analysis layered on top of audio/visual detection

## Layers

**CLI Layer:**
- Purpose: Parse command-line arguments, configure pipeline, handle user I/O
- Location: `src/cli.py`
- Contains: Click command definition, argument parsing, logging setup
- Depends on: `src/pipeline`
- Used by: Entry point (`quickedit` command)

**Pipeline Orchestrator:**
- Purpose: Coordinate the 10-step processing pipeline from input to output
- Location: `src/pipeline.py`
- Contains: `PipelineConfig` dataclass, `run_pipeline()` function, cached analysis wrappers
- Depends on: All other modules (`analyze`, `edit`, `timeline`, `render`, `cache`)
- Used by: CLI layer

**Analysis Layer:**
- Purpose: Extract detection signals from video (speech, motion, transcription)
- Location: `src/analyze/`
- Contains: VAD detection, motion analysis, whisper transcription, combinator logic
- Depends on: External tools (FFmpeg, Silero VAD, faster-whisper, OpenCV)
- Used by: Pipeline orchestrator

**Edit Layer:**
- Purpose: Transform detection arrays into edit decisions
- Location: `src/edit/`
- Contains: Margin expansion, smoothing, LLM semantic analysis, EDL types
- Depends on: Analysis outputs, Anthropic API for LLM
- Used by: Pipeline orchestrator

**Timeline Layer:**
- Purpose: Convert frame arrays into Clip/Cut data structures for rendering
- Location: `src/timeline/`
- Contains: `Timeline`, `Clip`, `CutSegment` dataclasses, frame-to-timeline conversion
- Depends on: Edit layer outputs
- Used by: Pipeline orchestrator, Render layer

**Render Layer:**
- Purpose: Produce final video output with subtitles
- Location: `src/render/`
- Contains: FFmpeg video rendering, ASS/SRT subtitle generation
- Depends on: Timeline, FFmpeg
- Used by: Pipeline orchestrator

**Cache Layer:**
- Purpose: Persist expensive analysis results to avoid recomputation
- Location: `src/cache/`
- Contains: Disk-based caching for numpy arrays and JSON data
- Depends on: Filesystem
- Used by: Pipeline orchestrator

## Data Flow

**Main Pipeline Flow:**

1. CLI parses args → `PipelineConfig` dataclass
2. Pipeline extracts video metadata via `ffprobe` → `VideoInfo`
3. VAD analysis → `np.ndarray[bool]` (speech frames)
4. Motion analysis → `np.ndarray[bool]` (activity frames)
5. Transcription → `TranscriptionResult` (words with timestamps)
6. Combine detectors → `np.ndarray[bool]` (keep frames)
7. Apply margin + smoothing → `np.ndarray[bool]` (refined keep frames)
8. LLM semantic pass → `list[EditDecision]` (additional cuts)
9. Build timeline → `Timeline` (clips + cuts)
10. Generate subtitles → `.ass` or `.srt` file
11. Render video → final output file

**State Management:**
- Configuration is immutable (`PipelineConfig` dataclass)
- Frame arrays are transformed through functional composition
- `Timeline` is the final edit decision list before rendering
- Cache layer provides memoization without affecting data flow

## Key Abstractions

**Per-Frame Boolean Array:**
- Purpose: Universal representation for keep/cut decisions at frame level
- Examples: `speech_frames`, `motion_frames`, `keep_frames` in `src/pipeline.py`
- Pattern: `np.ndarray[bool]` where `True` = keep, `False` = cut

**DetectionArrays:**
- Purpose: Named collection of detection arrays for combinator evaluation
- Examples: `src/analyze/combine.py:DetectionArrays`
- Pattern: Dict-like container with typed accessor methods

**Timeline/Clip/CutSegment:**
- Purpose: Edit decision list in time-domain (seconds), ready for FFmpeg
- Examples: `src/timeline/timeline.py`
- Pattern: Dataclasses with JSON serialization for inspection/persistence

**TranscriptionResult/Word/Segment:**
- Purpose: Word-level transcript with timestamps for LLM and subtitles
- Examples: `src/analyze/transcribe.py`
- Pattern: Nested dataclasses with helper methods for export/query

**EditDecision:**
- Purpose: LLM-suggested cut with reason, confidence, and transcript
- Examples: `src/edit/edl.py`
- Pattern: Dataclass with enum-based reason classification

## Entry Points

**CLI Entry Point:**
- Location: `src/cli.py:main()`
- Triggers: `quickedit` command (defined in `pyproject.toml`)
- Responsibilities: Parse args, build `PipelineConfig`, call `run_pipeline()`, display results

**Pipeline Entry Point:**
- Location: `src/pipeline.py:run_pipeline()`
- Triggers: Called by CLI with `PipelineConfig`
- Responsibilities: Orchestrate 10-step pipeline, return `PipelineResult`

**Programmatic Usage:**
- Location: Direct import of `src.pipeline.run_pipeline`
- Triggers: Python code importing the module
- Responsibilities: Same as CLI but without argument parsing

## Error Handling

**Strategy:** Fail-fast with informative exceptions

**Patterns:**
- `FileNotFoundError` for missing input files
- `RuntimeError` for FFmpeg/external tool failures
- Try/except at CLI level with `--verbose` for full tracebacks
- Graceful fallback: Silero VAD falls back to faster-whisper VAD if torch unavailable

## Cross-Cutting Concerns

**Logging:** Standard library `logging` module with configurable level via `--verbose`

**Validation:** Minimal upfront validation; errors surface during processing

**Authentication:** Anthropic API key read from `ANTHROPIC_API_KEY` env var or passed via config

**Caching:** File-based cache in `.quickedit_cache/` directory next to video; keyed by file identity + parameters

---

*Architecture analysis: 2026-04-01*
