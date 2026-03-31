# Coding Conventions

**Analysis Date:** 2026-04-01

## Naming Patterns

**Files:**
- snake_case for all Python modules: `transcribe.py`, `timeline.py`, `cache.py`
- Descriptive single-word or compound names: `vad.py`, `edl.py`, `smoothing.py`

**Functions:**
- snake_case: `analyze_vad()`, `run_pipeline()`, `frames_to_timeline()`
- Private helpers prefixed with underscore: `_run_ffmpeg()`, `_remap_words_to_output()`, `_cache_key()`
- Verb-first naming: `apply_margin()`, `generate_ass_subtitles()`, `filter_by_confidence()`

**Variables:**
- snake_case: `speech_frames`, `total_frames`, `output_path`
- Descriptive names over abbreviations: `transcript` not `tx`, `confidence` not `conf`
- Loop indices use standard `i`, `j` or descriptive names: `frame_idx`, `cut_idx`

**Classes:**
- PascalCase: `Timeline`, `Clip`, `EditDecision`, `VADResult`
- Dataclass naming reflects the data structure: `PipelineConfig`, `TranscriptionResult`, `SubtitleStyle`

**Constants:**
- UPPER_SNAKE_CASE: `CHUNK_SIZE_WORDS`, `CACHE_DIR_NAME`, `SYSTEM_PROMPT`
- Multi-line string constants for prompts: `DEFAULT_EDIT_PROMPT`, `PROMPT_TEMPLATES`

**Types:**
- PascalCase for type aliases and enums: `CutReason`, `CombineOp`

## Code Style

**Formatting:**
- Tool: ruff (listed in pyproject.toml dev dependencies)
- No explicit ruff config detected - using ruff defaults
- 4-space indentation (Python standard)
- Double quotes for docstrings, single quotes appear for some strings

**Line Length:**
- No explicit limit configured
- Most lines under 88 characters (ruff default)
- Long strings broken with backslash continuation

**Linting:**
- Tool: ruff (covers both linting and formatting)
- No explicit rule configuration - uses ruff defaults

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first when used)
2. Standard library: `logging`, `json`, `subprocess`, `tempfile`, `pathlib`
3. Third-party: `numpy`, `cv2`, `click`, `anthropic`
4. Local imports: `from src.analyze.vad import ...`, `from src.timeline.timeline import ...`

**Import Style:**
- Prefer explicit imports over wildcards
- Multi-item imports: one line when few items, multi-line for many
- Pattern in `src/pipeline.py`:
```python
from src.analyze.vad import analyze_vad, get_video_info
from src.analyze.motion import analyze_motion
from src.analyze.transcribe import transcribe, TranscriptionResult, words_to_frame_array
```

**Path Aliases:**
- None configured. Uses full relative paths: `from src.analyze.transcribe import ...`

## Type Annotations

**Approach:**
- `from __future__ import annotations` used consistently for forward references
- Full type hints on function signatures:
```python
def transcribe(
    video_path: str | Path,
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = None,
    vad_filter: bool = True,
    beam_size: int = 5,
) -> TranscriptionResult:
```

**Union Types:**
- Modern union syntax: `str | Path`, `str | None`
- Not `Union[str, Path]` or `Optional[str]`

**Return Types:**
- Always specified on public functions
- `-> None` explicit on void functions

## Dataclasses

**Pattern:**
- `@dataclass` decorator for all data structures
- Default values with `field(default_factory=...)` for mutable defaults:
```python
@dataclass
class PipelineResult:
    output_path: str
    timeline: Timeline
    transcript: TranscriptionResult | None
    llm_decisions: list[EditDecision]
    timing: dict[str, float] = field(default_factory=dict)
```

**Properties:**
- Computed properties use `@property` decorator:
```python
@property
def output_duration(self) -> float:
    """Total duration of the output video."""
```

## Error Handling

**Patterns:**
- Explicit exception raising with descriptive messages:
```python
if not input_path.exists():
    raise FileNotFoundError(f"Input video not found: {input_path}")
```

- RuntimeError for external tool failures:
```python
if result.returncode != 0:
    raise RuntimeError(f"FFmpeg failed (exit {result.returncode}): {result.stderr[-500:]}")
```

- Try/except for recoverable operations:
```python
try:
    data = json.loads(text)
except json.JSONDecodeError:
    logger.warning(f"Failed to parse LLM response as JSON: {text[:200]}...")
    return []
```

- Fallback patterns for optional dependencies:
```python
except ImportError:
    # Fallback: use faster-whisper's built-in VAD
    return _detect_speech_faster_whisper_vad(audio_samples, sample_rate, threshold)
```

**Validation:**
- Input validation at function entry
- Assertions for internal invariants: `assert wf.getnchannels() == 1, "Expected mono audio"`

## Logging

**Framework:** Standard library `logging`

**Setup:**
```python
logger = logging.getLogger(__name__)
```

**Patterns:**
- Module-level logger creation
- Info for user-facing progress: `logger.info(f"Running LLM chunk {i + 1}/{len(chunks)}")`
- Debug for cache operations: `logger.debug(f"Loaded cached {method} from {cache_file}")`
- Warning for recoverable issues: `logger.warning(f"Failed to load cache {cache_file}: {e}")`
- Error for failures: `logger.error(f"FFmpeg failed:\n{result.stderr[-1000:]}")`

**Log Format (CLI):**
```python
logging.basicConfig(
    level=level,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
```

## Docstrings

**Style:** Google-style with Args/Returns sections

**Pattern:**
```python
def transcribe(
    video_path: str | Path,
    model_size: str = "base",
    ...
) -> TranscriptionResult:
    """
    Transcribe a video file using faster-whisper.

    Args:
        video_path: Path to video or audio file.
        model_size: Whisper model size. Options:
            "tiny", "base", "small", "medium", "large-v3", "turbo"
            For CPU, "base" or "small" recommended.
        device: "cpu" or "cuda".
        ...

    Returns:
        TranscriptionResult with word-level timestamps.
    """
```

**Module Docstrings:**
- Present at top of every module
- Describes purpose, key concepts, and sometimes usage:
```python
"""
Timeline and Clip abstractions for the edit decision list.

Converts a per-frame bool array into a list of Clips (segments to keep),
which are then used by the render module to produce the final video.

Inspired by auto-editor's v3 timeline model.
"""
```

## Function Design

**Size:**
- Functions are focused, typically under 50 lines
- Complex pipelines broken into helper functions: `_run_vad_cached()`, `_run_motion_cached()`

**Parameters:**
- Sensible defaults for most parameters
- Group related parameters (e.g., all margin params, all codec params)
- Use `| None` pattern for optional parameters with None meaning "auto/default"

**Return Values:**
- Single return type (not `str | int | dict`)
- Complex results use dataclasses: `VADResult`, `MotionResult`, `TranscriptionResult`
- Lists for multiple items of same type

## Module Design

**Exports:**
- `__init__.py` files are empty (no barrel exports)
- Import directly from specific modules: `from src.cache.cache import ...`

**Internal Functions:**
- Private helpers prefixed with `_`
- Public API is clear from non-prefixed functions

**Cross-Module Dependencies:**
- `pipeline.py` imports from all other modules (orchestrator pattern)
- Other modules import selectively as needed
- Avoid circular imports through careful structuring

## CLI Design

**Framework:** Click

**Pattern:**
```python
@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", default="", help="...")
@click.option("--whisper-model", default="base", help="...")
def main(...) -> None:
    """Docstring becomes --help text."""
```

**Conventions:**
- Long options use kebab-case: `--whisper-model`, `--no-llm`
- Boolean flags use `is_flag=True`: `--no-cache`, `--dry-run`, `--verbose`
- Choices validated with `type=click.Choice([...])`
- Paths validated with `type=click.Path(exists=True)`

## Constants and Configuration

**Pattern:**
- Module-level constants for tunable values
- Dataclass for configuration: `PipelineConfig`
- Dict for prompt templates: `PROMPT_TEMPLATES = {...}`

**Location:**
- Configuration in the module that uses it
- Shared constants could go in a constants module (not present yet)

---

*Convention analysis: 2026-04-01*
