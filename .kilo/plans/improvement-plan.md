# QuickEdit Improvement Plan

**Created:** 2026-04-01
**Focus Areas:** Testing, Performance, Robustness
**Estimated Duration:** 1-2 weeks (depending on scope)

---

## Overview

This plan addresses improvements across three focus areas:

| Phase | Focus | Tasks | Effort |
|-------|-------|-------|--------|
| 1 | Testing Foundation | Test infrastructure + high-value unit tests | 3-4 days |
| 2 | Robustness | Bug fixes, validation, error handling | 2-3 days |
| 3 | Performance | Async LLM, motion detection, render optimization | 3-4 days |

---

## Phase 1: Testing Foundation

### Goal
Establish test infrastructure and cover core pure functions that are easy to test and high-value.

### Tasks

#### 1.1 Create Test Infrastructure
**Files to create:**
- `tests/__init__.py`
- `tests/conftest.py` - Shared fixtures

**conftest.py fixtures needed:**
```python
@pytest.fixture
def sample_frames() -> np.ndarray:
    """Boolean frame array for testing smoothing/margin."""
    return np.array([False]*10 + [True]*20 + [False]*5 + [True]*15 + [False]*10)

@pytest.fixture
def sample_timeline() -> Timeline:
    """Timeline with test clips for rendering tests."""

@pytest.fixture
def sample_transcript() -> TranscriptionResult:
    """Word-level transcript for LLM/subtitle tests."""

@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for LLM tests."""
```

**Effort:** 1-2 hours

---

#### 1.2 Test `src/edit/smoothing.py`
**File:** `tests/test_smoothing.py`

**Test cases:**
| Test | Description |
|------|-------------|
| `test_smooth_noop_when_disabled` | Returns copy when minclip=0 and mincut=0 |
| `test_smooth_removes_short_clips` | Short True segments below minclip are removed |
| `test_smooth_fills_short_gaps` | Short False gaps below mincut are filled |
| `test_smooth_preserves_long_clips` | Clips >= minclip are preserved |
| `test_smooth_preserves_long_gaps` | Gaps >= mincut are preserved |
| `test_smooth_iterates_until_stable` | Complex arrays converge correctly |
| `test_smooth_edge_cases` | Empty array, all True, all False, single element |
| `test_smooth_seconds_conversion` | Converts seconds to frames correctly |

**Effort:** 2-3 hours

---

#### 1.3 Test `src/edit/margin.py`
**File:** `tests/test_margin.py`

**Test cases:**
| Test | Description |
|------|-------------|
| `test_margin_noop_when_zero` | Returns copy when start_margin=0 and end_margin=0 |
| `test_margin_expands_start` | Positive start_margin expands before True regions |
| `test_margin_expands_end` | Positive end_margin expands after True regions |
| `test_margin_shrinks_start` | Negative start_margin shrinks from start |
| `test_margin_shrinks_end` | Negative end_margin shrinks from end |
| `test_margin_respects_boundaries` | Doesn't expand beyond array bounds |
| `test_margin_merges_adjacent_regions` | Expanding regions that become adjacent merge |
| `test_margin_seconds_conversion` | Converts seconds to frames correctly |

**Effort:** 2-3 hours

---

#### 1.4 Test `src/analyze/combine.py`
**File:** `tests/test_combine.py`

**Test cases:**
| Test | Description |
|------|-------------|
| `test_combine_or_basic` | OR of two arrays |
| `test_combine_and_basic` | AND of two arrays |
| `test_combine_not_basic` | NOT inverts array |
| `test_combine_xor_basic` | XOR of two arrays |
| `test_combine_different_lengths` | Arrays of different lengths handled correctly |
| `test_evaluate_expression_simple` | Direct array name lookup |
| `test_evaluate_expression_colon_format` | "or:speech,motion" format |
| `test_evaluate_expression_list_format` | ["or", "speech", "motion"] format |
| `test_evaluate_expression_nested` | Nested expressions like ["or", "speech", ["not", "motion"]] |
| `test_evaluate_expression_unknown_array` | Raises KeyError for unknown array name |
| `test_evaluate_expression_unknown_op` | Raises ValueError for unknown operation |

**Effort:** 2-3 hours

---

#### 1.5 Test `src/timeline/timeline.py`
**File:** `tests/test_timeline.py`

**Test cases:**
| Test | Description |
|------|-------------|
| `test_frames_to_timeline_basic` | Converts bool array to clips |
| `test_frames_to_timeline_all_keep` | Single clip for all-True array |
| `test_frames_to_timeline_all_cut` | Empty clips for all-False array |
| `test_frames_to_timeline_alternating` | Multiple clips for alternating pattern |
| `test_timeline_summary` | Summary string is correct |
| `test_timeline_json_roundtrip` | to_json/from_json preserves data |
| `test_merge_timelines_no_cuts` | Empty cuts list returns original |
| `test_merge_timelines_with_cuts` | Cuts are applied correctly |
| `test_merge_timelines_overlapping_cuts` | Overlapping cuts handled correctly |

**Effort:** 3-4 hours

---

#### 1.6 Test `src/edit/llm.py` (Response Parsing)
**File:** `tests/test_llm.py`

**Test cases:**
| Test | Description |
|------|-------------|
| `test_parse_llm_response_valid_json` | Parses valid JSON response |
| `test_parse_llm_response_markdown_block` | Extracts JSON from ```json block |
| `test_parse_llm_response_empty_decisions` | Handles empty decisions array |
| `test_parse_llm_response_invalid_json` | Returns empty list on parse failure |
| `test_parse_llm_response_unknown_reason` | Falls back to CutReason.CUSTOM |
| `test_deduplicate_decisions_no_overlap` | Non-overlapping decisions kept |
| `test_deduplicate_decisions_overlap` | Overlapping decisions merged by confidence |
| `test_chunk_words_small_transcript` | Single chunk for short transcripts |
| `test_chunk_words_large_transcript` | Multiple overlapping chunks |

**Effort:** 2-3 hours

---

#### 1.7 Add pytest-cov and Configuration
**Files to update:**
- `pyproject.toml` - Add pytest-cov, configure pytest

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.5.0",
]
```

**Effort:** 30 minutes

---

### Phase 1 Summary
**Total Effort:** 2-3 days
**Output:** 
- Test infrastructure with fixtures
- ~50 unit tests covering core pure functions
- Coverage reporting enabled

---

## Phase 2: Robustness

### Goal
Fix known bugs, improve error handling, and extract magic numbers to configuration.

### Tasks

#### 2.1 Fix Frame Count Mismatch Warning
**File:** `src/pipeline.py` (lines 382-387, 422-426)

**Current behavior:** Silently pads/truncates arrays when VAD/motion frame counts don't match video metadata.

**Fix:**
```python
def _run_vad_cached(...) -> np.ndarray:
    # ... existing code ...
    
    # Replace silent padding with warning
    if len(speech_frames) != total_frames:
        logger.warning(
            f"VAD returned {len(speech_frames)} frames, expected {total_frames}. "
            f"Difference: {abs(len(speech_frames) - total_frames)} frames. "
            f"Video may have variable frame rate."
        )
        padded = np.zeros(total_frames, dtype=bool)
        n = min(len(speech_frames), total_frames)
        padded[:n] = speech_frames[:n]
        speech_frames = padded
```

**Effort:** 30 minutes

---

#### 2.2 Extract Magic Numbers to PipelineConfig
**Files:** `src/pipeline.py`, `src/analyze/motion.py`, `src/render/subtitle.py`

**Magic numbers to extract:**

| Value | Current Location | New Config Field |
|-------|-----------------|------------------|
| `10` (pixel threshold) | `motion.py:111` | `motion_pixel_threshold: int = 10` |
| `0.7` (subtitle silence gap) | `subtitle.py:193` | `subtitle_silence_gap: float = 0.7` |
| `16` (cache key hash length) | `cache.py:57` | `cache_hash_length: int = 32` (increase) |
| `0.5` (silent segment min duration) | `pipeline.py:566` | `silent_segment_min_duration: float = 0.5` |

**Implementation:**

1. Add fields to `PipelineConfig`:
```python
@dataclass
class PipelineConfig:
    # ... existing fields ...
    
    # Motion detection (detailed)
    motion_pixel_threshold: int = 10  # pixel change threshold for binary diff
    
    # Subtitles (detailed)
    subtitle_silence_gap: float = 0.7  # gap between subtitle groups (seconds)
    
    # Cache
    cache_hash_length: int = 32  # characters of hash for cache key
    
    # Silent segment classification
    silent_segment_min_duration: float = 0.5  # minimum duration to classify
```

2. Pass through to relevant functions.

**Effort:** 1-2 hours

---

#### 2.3 Replace Assertions with Explicit Validation
**File:** `src/analyze/vad.py` (lines 132-133)

**Current:**
```python
assert wf.getnchannels() == 1, "Expected mono audio"
assert wf.getsampwidth() == 2, "Expected 16-bit audio"
```

**Fix:**
```python
if wf.getnchannels() != 1:
    raise ValueError(f"Expected mono audio, got {wf.getnchannels()} channels")
if wf.getsampwidth() != 2:
    raise ValueError(f"Expected 16-bit audio, got {wf.getsampwidth() * 8}-bit")
```

**Effort:** 15 minutes

---

#### 2.4 Add Video Format Validation
**File:** `src/pipeline.py`

**Add after line 154:**
```python
def _validate_video(info: dict, input_path: Path) -> None:
    """Validate video has expected properties for processing."""
    if info.get("fps", 0) <= 0:
        raise ValueError(f"Invalid FPS ({info['fps']}) for video: {input_path}")
    if info.get("total_frames", 0) <= 0:
        raise ValueError(f"Invalid frame count for video: {input_path}")
    if not info.get("has_audio", True):  # Default True for backwards compat
        logger.warning(f"Video has no audio track: {input_path}. VAD will return empty.")
```

**Effort:** 30 minutes

---

#### 2.5 Add JSON Schema Validation for LLM Responses
**File:** `src/edit/llm.py`

**Add validation using dataclass:**
```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class LLMDecisionSchema:
    start_time: float
    end_time: float
    reason: str
    confidence: float
    transcript: str
    note: str = ""
    
    def __post_init__(self):
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")
        if self.start_time >= self.end_time:
            raise ValueError(f"start_time must be < end_time")
        if self.start_time < 0:
            raise ValueError(f"start_time must be >= 0")

def _parse_decision_item(item: dict) -> EditDecision | None:
    """Parse single decision with validation."""
    try:
        schema = LLMDecisionSchema(
            start_time=float(item.get("start_time", 0)),
            end_time=float(item.get("end_time", 0)),
            reason=str(item.get("reason", "custom")),
            confidence=float(item.get("confidence", 0.8)),
            transcript=str(item.get("transcript", "")),
            note=str(item.get("note", "")),
        )
        # ... convert to EditDecision ...
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid LLM decision item: {e}")
        return None
```

**Effort:** 1 hour

---

#### 2.6 Add Response Size Limit for LLM
**File:** `src/edit/llm.py`

**Add before JSON parsing:**
```python
MAX_RESPONSE_SIZE = 100_000  # 100KB limit

def _parse_llm_response(response_text: str) -> list[EditDecision]:
    if len(response_text) > MAX_RESPONSE_SIZE:
        logger.warning(
            f"LLM response too large ({len(response_text)} bytes), truncating"
        )
        response_text = response_text[:MAX_RESPONSE_SIZE]
    # ... existing parsing code ...
```

**Effort:** 15 minutes

---

### Phase 2 Summary
**Total Effort:** 1-2 days
**Output:**
- Frame count mismatch warnings
- Configurable magic numbers
- Explicit validation (no assertions)
- Video format validation
- LLM response validation

---

## Phase 3: Performance

### Goal
Improve processing speed for long videos and transcripts.

### Tasks

#### 3.1 Async LLM Calls with Parallel Chunk Processing
**File:** `src/edit/llm.py`

**New async implementation:**
```python
import asyncio
from anthropic import AsyncAnthropic

async def analyze_with_llm_async(
    transcript: TranscriptionResult,
    silent_segments: list[SilentSegmentInfo] | None = None,
    custom_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    max_concurrent: int = 3,  # Rate limit
) -> list[EditDecision]:
    """Async version with parallel chunk processing."""
    client = AsyncAnthropic(api_key=api_key)
    edit_prompt = custom_prompt or DEFAULT_EDIT_PROMPT
    
    words_data = transcript.to_transcript_with_timestamps()
    silent_info = _build_silent_info(silent_segments)
    chunks = _chunk_words(words_data, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS)
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_chunk(i: int, chunk: list[dict]) -> list[EditDecision]:
        async with semaphore:
            logger.info(f"Processing LLM chunk {i + 1}/{len(chunks)}")
            user_message = _build_user_message(chunk, edit_prompt, silent_info)
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return _parse_llm_response(response.content[0].text)
    
    tasks = [process_chunk(i, chunk) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)
    
    all_decisions = []
    for decisions in results:
        all_decisions.extend(decisions)
    
    return _deduplicate_decisions(all_decisions)

# Sync wrapper for backwards compatibility
def analyze_with_llm(
    transcript: TranscriptionResult,
    silent_segments: list[SilentSegmentInfo] | None = None,
    custom_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[EditDecision]:
    """Sync wrapper around async implementation."""
    return asyncio.run(analyze_with_llm_async(
        transcript, silent_segments, custom_prompt, api_key, model
    ))
```

**Benefits:**
- 10 chunks processed in ~1/3 the time (with max_concurrent=3)
- Rate limiting via semaphore

**Effort:** 2-3 hours

---

#### 3.2 Add Frame Skip Option for Motion Detection
**File:** `src/analyze/motion.py`

**Modify `analyze_motion` signature:**
```python
def analyze_motion(
    video_path: str | Path,
    threshold: float = 0.02,
    scale_width: int = 400,
    blur_sigma: int = 9,
    frame_skip: int = 1,  # NEW: analyze every Nth frame
) -> MotionResult:
    """
    ...
    Args:
        frame_skip: Analyze every Nth frame. Default 1 (all frames).
                    Set to 2-3 for faster processing on long videos.
                    Intermediate frames are interpolated.
    """
    # ... setup code ...
    
    frame_idx = 0
    analyzed_frames = []
    
    while True:
        ret, frame = cap.read()
        if not ret or frame_idx >= total_frames:
            break
        
        # Only analyze every Nth frame
        if frame_idx % frame_skip == 0:
            # ... existing motion analysis code ...
            analyzed_frames.append((frame_idx, motion_value))
        
        frame_idx += 1
    
    # Interpolate skipped frames
    motion_values = _interpolate_motion_values(
        analyzed_frames, total_frames, frame_skip
    )
    
    # ... rest of function ...

def _interpolate_motion_values(
    analyzed: list[tuple[int, float]],
    total_frames: int,
    frame_skip: int,
) -> np.ndarray:
    """Interpolate motion values for skipped frames."""
    motion_values = np.zeros(total_frames, dtype=np.float32)
    
    for i, (frame_idx, value) in enumerate(analyzed):
        motion_values[frame_idx] = value
        
        # Linear interpolation to next analyzed frame
        if i < len(analyzed) - 1:
            next_idx, next_value = analyzed[i + 1]
            for j in range(frame_idx + 1, next_idx):
                t = (j - frame_idx) / (next_idx - frame_idx)
                motion_values[j] = value + t * (next_value - value)
    
    return motion_values
```

**Add to PipelineConfig:**
```python
motion_frame_skip: int = 1  # 1 = all frames, 2 = every other, etc.
```

**Benefits:**
- `frame_skip=2`: ~2x faster motion analysis
- `frame_skip=3`: ~3x faster with minimal quality loss

**Effort:** 2-3 hours

---

#### 3.3 Auto-Select Render Strategy Based on Clip Count
**File:** `src/render/video.py`

**Add automatic strategy selection:**
```python
CLIP_THRESHOLD_FOR_SEGMENT_RENDER = 50

def render_video(
    timeline: Timeline,
    output_path: str | Path,
    subtitle_path: str | Path | None = None,
    codec: str = "libx264",
    crf: int = 18,
    preset: str = "medium",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    render_strategy: str = "auto",  # NEW: "auto", "filter_complex", "segments"
) -> None:
    """
    ...
    Args:
        render_strategy: "auto" (default) - picks best strategy based on clip count
                        "filter_complex" - single ffmpeg with filter_complex
                        "segments" - render segments then concat
    """
    if render_strategy == "auto":
        if len(timeline.clips) > CLIP_THRESHOLD_FOR_SEGMENT_RENDER:
            logger.info(
                f"Timeline has {len(timeline.clips)} clips (>{CLIP_THRESHOLD_FOR_SEGMENT_RENDER}), "
                f"using segment-then-concat strategy"
            )
            render_strategy = "segments"
        else:
            render_strategy = "filter_complex"
    
    if render_strategy == "segments":
        return render_segments_then_concat(
            timeline, output_path, subtitle_path,
            codec, crf, preset, audio_codec, audio_bitrate
        )
    else:
        return _render_filter_complex(
            timeline, output_path, subtitle_path,
            codec, crf, preset, audio_codec, audio_bitrate
        )
```

**Effort:** 1 hour

---

#### 3.4 Add Progress Callbacks
**File:** `src/pipeline.py`

**Add to PipelineConfig:**
```python
from typing import Callable

@dataclass
class PipelineConfig:
    # ... existing fields ...
    
    # Progress reporting
    progress_callback: Callable[[str, float, str], None] | None = None
    # Signature: (step: str, progress: float 0-1, message: str) -> None
```

**Add helper function:**
```python
def _report_progress(
    config: PipelineConfig,
    step: str,
    progress: float,
    message: str = "",
) -> None:
    """Report progress if callback is set."""
    if config.progress_callback:
        config.progress_callback(step, progress, message)
```

**Usage in pipeline:**
```python
def run_pipeline(config: PipelineConfig) -> PipelineResult:
    # ... existing code ...
    
    _report_progress(config, "vad", 0.0, "Starting voice activity detection")
    speech_frames = _run_vad_cached(config, input_path, fps, total_frames)
    _report_progress(config, "vad", 1.0, f"{speech_pct:.1f}% speech detected")
    
    _report_progress(config, "motion", 0.0, "Starting motion detection")
    # ... etc ...
```

**For motion detection (fine-grained progress):**
```python
def analyze_motion(
    video_path: str | Path,
    # ... existing args ...
    progress_callback: Callable[[float], None] | None = None,
) -> MotionResult:
    # ... in frame loop ...
    if progress_callback and frame_idx % log_interval == 0:
        progress_callback(frame_idx / total_frames)
```

**Effort:** 2 hours

---

### Phase 3 Summary
**Total Effort:** 2-3 days
**Output:**
- Async LLM calls (~3x faster for long transcripts)
- Frame skip option for motion detection (~2-3x faster)
- Auto-select render strategy
- Progress callbacks for GUI/CLI integration

---

## Implementation Order

```
Phase 1.1 (Test Infrastructure)
    ↓
Phase 1.2-1.6 (Unit Tests) ← Can run in parallel
    ↓
Phase 2.1-2.6 (Robustness) ← Tests catch regressions
    ↓
Phase 3.1-3.4 (Performance) ← Tests verify behavior unchanged
```

---

## Verification Checklist

After implementation:

- [ ] All tests pass: `pytest -v`
- [ ] Coverage >80% on core modules: `pytest --cov=src --cov-report=html`
- [ ] No ruff errors: `ruff check src tests`
- [ ] Existing CLI still works: `quickedit sample.mp4 --dry-run`
- [ ] Performance improvement measured on long video

---

## Files Changed Summary

### New Files
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_smoothing.py`
- `tests/test_margin.py`
- `tests/test_combine.py`
- `tests/test_timeline.py`
- `tests/test_llm.py`

### Modified Files
- `pyproject.toml` - pytest config, pytest-cov
- `src/pipeline.py` - config fields, validation, progress callbacks
- `src/edit/llm.py` - async, validation, response limits
- `src/analyze/motion.py` - frame skip, progress callback
- `src/analyze/vad.py` - explicit validation
- `src/render/video.py` - auto strategy selection
- `src/cache/cache.py` - configurable hash length

---

*Plan created: 2026-04-01*
