# Codebase Structure

**Analysis Date:** 2026-04-01

## Directory Layout

```
quickedit/
├── src/                    # All application source code
│   ├── __init__.py         # Package marker (empty)
│   ├── cli.py              # CLI entry point
│   ├── pipeline.py         # Main orchestrator
│   ├── analyze/            # Detection/analysis modules
│   │   ├── __init__.py
│   │   ├── vad.py          # Voice activity detection
│   │   ├── motion.py       # Visual activity detection
│   │   ├── transcribe.py   # Whisper transcription
│   │   └── combine.py      # Detection combinator logic
│   ├── edit/               # Edit decision modules
│   │   ├── __init__.py
│   │   ├── llm.py          # Claude LLM semantic analysis
│   │   ├── edl.py          # Edit Decision List types
│   │   ├── margin.py       # Margin expansion around regions
│   │   └── smoothing.py    # Remove micro-cuts/clips
│   ├── timeline/           # Timeline data structures
│   │   ├── __init__.py
│   │   └── timeline.py     # Clip/Timeline/CutSegment classes
│   ├── render/             # Output generation
│   │   ├── __init__.py
│   │   ├── video.py        # FFmpeg video rendering
│   │   └── subtitle.py     # ASS/SRT subtitle generation
│   └── cache/              # Caching infrastructure
│       ├── __init__.py
│       └── cache.py        # Disk-based result caching
├── .quickedit_cache/       # Generated: cached analysis results
├── pyproject.toml          # Project metadata, dependencies, entry points
├── .gitignore              # Git ignore patterns
├── .venv/                  # Python virtual environment (not committed)
└── PROGRESS.md             # Development progress notes
```

## Directory Purposes

**`src/`:**
- Purpose: All Python source code for the application
- Contains: Modules organized by processing stage
- Key files: `cli.py` (entry), `pipeline.py` (orchestrator)

**`src/analyze/`:**
- Purpose: Signal detection and transcription
- Contains: VAD, motion detection, whisper transcription, combinator
- Key files: `vad.py` (speech), `motion.py` (visual), `transcribe.py` (words)

**`src/edit/`:**
- Purpose: Transform detection signals into edit decisions
- Contains: LLM analysis, margin/smoothing algorithms, EDL types
- Key files: `llm.py` (Claude integration), `edl.py` (data types)

**`src/timeline/`:**
- Purpose: Timeline data structures for edit representation
- Contains: Clip, CutSegment, Timeline dataclasses with serialization
- Key files: `timeline.py` (all timeline logic)

**`src/render/`:**
- Purpose: Final output generation
- Contains: FFmpeg video rendering, subtitle generation
- Key files: `video.py` (FFmpeg calls), `subtitle.py` (ASS/SRT)

**`src/cache/`:**
- Purpose: Disk caching for expensive computations
- Contains: File-based cache keyed by video identity + params
- Key files: `cache.py` (all caching logic)

## Key File Locations

**Entry Points:**
- `src/cli.py`: CLI command definition and main entry
- `src/pipeline.py`: Programmatic entry via `run_pipeline()`

**Configuration:**
- `pyproject.toml`: Package metadata, dependencies, CLI entry point
- No runtime config files; all config via CLI args or `PipelineConfig`

**Core Logic:**
- `src/pipeline.py`: 10-step processing pipeline orchestration
- `src/analyze/combine.py`: Detection array combinator with expression parser
- `src/edit/llm.py`: LLM prompts, API calls, response parsing
- `src/timeline/timeline.py`: Timeline construction and merging

**Testing:**
- No dedicated test files found
- `pyproject.toml` lists pytest in dev dependencies

## Naming Conventions

**Files:**
- Snake_case: `voice_activity.py` style (but current files use single words: `vad.py`, `motion.py`)
- Descriptive names matching module purpose: `transcribe.py`, `subtitle.py`

**Directories:**
- Lowercase, single word: `analyze`, `edit`, `timeline`, `render`, `cache`
- Each directory is a Python package with `__init__.py`

**Classes:**
- PascalCase: `PipelineConfig`, `Timeline`, `CutSegment`, `EditDecision`
- Dataclasses for data containers, no inheritance hierarchy

**Functions:**
- snake_case: `run_pipeline()`, `analyze_vad()`, `frames_to_timeline()`
- Public functions at module level; private helpers prefixed with `_`

**Constants:**
- UPPER_SNAKE_CASE: `CHUNK_SIZE_WORDS`, `CACHE_DIR_NAME`, `SYSTEM_PROMPT`

## Where to Add New Code

**New Detection Method:**
- Primary code: `src/analyze/new_detector.py`
- Register in `src/analyze/combine.py` `DetectionArrays`
- Call from `src/pipeline.py` with caching wrapper
- Tests: `tests/test_new_detector.py` (create `tests/` dir if needed)

**New Edit Algorithm:**
- Implementation: `src/edit/new_algo.py`
- Integration: Call from `src/pipeline.py` between combine and timeline steps

**New Output Format:**
- Implementation: `src/render/new_format.py`
- Integration: Add option in `src/cli.py`, call from `src/pipeline.py`

**New LLM Prompt Template:**
- Add to `PROMPT_TEMPLATES` dict in `src/edit/llm.py`
- Add choice to `--prompt-template` in `src/cli.py`

**Utilities/Helpers:**
- Shared helpers: Create `src/utils.py` or add to relevant module
- Type definitions: Add to the module where used, or create `src/types.py`

## Special Directories

**`.quickedit_cache/`:**
- Purpose: Stores cached analysis results (VAD, motion, transcription)
- Generated: Yes, created automatically next to video files
- Committed: No (in `.gitignore`)

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes, via `python -m venv .venv`
- Committed: No (in `.gitignore`)

**`.planning/`:**
- Purpose: Planning and architecture documentation
- Generated: No (manually created)
- Committed: Yes

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No (in `.gitignore`)

---

*Structure analysis: 2026-04-01*
