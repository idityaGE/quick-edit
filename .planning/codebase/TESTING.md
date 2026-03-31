# Testing Patterns

**Analysis Date:** 2026-04-01

## Test Framework

**Runner:**
- pytest >= 8.0.0 (listed in pyproject.toml dev dependencies)
- Config: No pytest.ini, setup.cfg, or pyproject.toml `[tool.pytest]` section detected

**Assertion Library:**
- pytest's built-in assertions (expected)
- No additional assertion libraries detected

**Run Commands:**
```bash
pytest                    # Run all tests
pytest -v                 # Verbose output
pytest --cov=src          # Coverage (requires pytest-cov, not in deps)
```

## Test File Organization

**Location:**
- No test files detected in the main project source
- External tests found in `.opencode/get-shit-done/bin/` (not part of quickedit)

**Expected Pattern (not implemented):**
```
tests/                    # Separate test directory (common pattern)
├── test_vad.py
├── test_motion.py
├── test_transcribe.py
├── test_pipeline.py
└── conftest.py

# OR co-located:
src/
├── analyze/
│   ├── vad.py
│   └── test_vad.py       # Co-located tests
```

**Naming:**
- Expected: `test_*.py` or `*_test.py` (pytest discovery)

## Test Structure

**Expected Suite Organization:**
```python
import pytest
from src.analyze.vad import analyze_vad, VADResult

class TestVAD:
    """Tests for voice activity detection."""

    def test_analyze_vad_returns_result(self, sample_video):
        """VAD returns a VADResult with expected fields."""
        result = analyze_vad(sample_video)
        assert isinstance(result, VADResult)
        assert result.fps > 0
        assert len(result.speech_frames) == result.total_frames

    def test_analyze_vad_threshold(self, sample_video):
        """Lower threshold detects more speech."""
        result_high = analyze_vad(sample_video, threshold=0.9)
        result_low = analyze_vad(sample_video, threshold=0.1)
        # Lower threshold = more frames marked as speech
        assert result_low.speech_frames.sum() >= result_high.speech_frames.sum()
```

**Patterns:**
- Class-based grouping for related tests
- Descriptive test names: `test_<function>_<behavior>`
- Docstrings explain test purpose

## Mocking

**Framework:** unittest.mock (standard library) or pytest-mock

**Expected Patterns:**
```python
from unittest.mock import patch, MagicMock

def test_render_video_calls_ffmpeg(self, timeline):
    """render_video calls FFmpeg with correct arguments."""
    with patch("src.render.video.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        render_video(timeline, "output.mp4")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]

def test_llm_analysis_with_mocked_api(self, transcript):
    """LLM analysis returns edit decisions."""
    with patch("src.edit.llm.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"decisions": []}')])
        decisions = analyze_with_llm(transcript)
        assert isinstance(decisions, list)
```

**What to Mock:**
- External APIs: Anthropic Claude API
- Subprocess calls: FFmpeg, FFprobe
- File system for isolation
- Heavy ML models: Whisper, Silero VAD

**What NOT to Mock:**
- Pure Python logic (dataclasses, numpy operations)
- Small utility functions
- Dataclass construction

## Fixtures and Factories

**Expected Test Data:**
```python
# conftest.py
import pytest
import numpy as np
from pathlib import Path

@pytest.fixture
def sample_video(tmp_path):
    """Create a minimal test video."""
    video_path = tmp_path / "test.mp4"
    # Create with ffmpeg or use a small fixture file
    return video_path

@pytest.fixture
def sample_timeline():
    """Create a Timeline with test clips."""
    from src.timeline.timeline import Timeline, Clip
    return Timeline(
        source="test.mp4",
        fps=30.0,
        duration=10.0,
        clips=[
            Clip(source="test.mp4", src_start=0, src_end=5, dst_start=0, duration=5),
        ],
        cuts=[],
    )

@pytest.fixture
def sample_frames():
    """Boolean frame array for testing smoothing/margin."""
    return np.array([False]*10 + [True]*20 + [False]*5 + [True]*15 + [False]*10)

@pytest.fixture
def sample_transcript():
    """TranscriptionResult for testing LLM analysis."""
    from src.analyze.transcribe import TranscriptionResult, Word, Segment
    return TranscriptionResult(
        segments=[],
        words=[
            Word(text="hello", start=0.0, end=0.5, probability=0.95),
            Word(text="world", start=0.6, end=1.0, probability=0.90),
        ],
        language="en",
        language_probability=0.99,
        duration=2.0,
        text="hello world",
    )
```

**Location:**
- `conftest.py` for shared fixtures
- Test modules for module-specific fixtures

## Coverage

**Requirements:** Not enforced (pytest-cov not in dependencies)

**Recommended Setup:**
```bash
# Add to dev dependencies
pip install pytest-cov

# Run with coverage
pytest --cov=src --cov-report=html

# View coverage
open htmlcov/index.html
```

**Target:** Not specified - recommend 80%+ for core logic

## Test Types

**Unit Tests:**
- Test individual functions in isolation
- Focus on: `src/edit/smoothing.py`, `src/edit/margin.py`, `src/analyze/combine.py`
- These are pure numpy operations, easy to unit test

**Integration Tests:**
- Test module interactions
- Example: pipeline.py coordinating analyze -> edit -> render
- Requires fixtures or mocked dependencies

**E2E Tests:**
- Full pipeline execution on sample video
- Slow but validates complete workflow
- Would test `quickedit input.mp4 --dry-run`

## Recommended Test Priority

**High Priority (easy, valuable):**
1. `src/edit/smoothing.py` - pure functions on numpy arrays
2. `src/edit/margin.py` - pure functions on numpy arrays  
3. `src/analyze/combine.py` - boolean logic on arrays
4. `src/timeline/timeline.py` - dataclass serialization/deserialization

**Medium Priority:**
5. `src/edit/llm.py` - mock API, test parsing
6. `src/render/subtitle.py` - test ASS/SRT generation
7. `src/cache/cache.py` - test caching logic with tmp_path

**Lower Priority (need heavy mocking/fixtures):**
8. `src/analyze/vad.py` - needs audio fixtures
9. `src/analyze/motion.py` - needs video fixtures
10. `src/render/video.py` - needs subprocess mocking

## Common Patterns

**Async Testing:**
- Not applicable - codebase is synchronous

**Error Testing:**
```python
def test_pipeline_raises_on_missing_file():
    """Pipeline raises FileNotFoundError for missing input."""
    config = PipelineConfig(input_path="/nonexistent/video.mp4")
    with pytest.raises(FileNotFoundError, match="Input video not found"):
        run_pipeline(config)

def test_ffmpeg_failure_raises_runtime_error():
    """FFmpeg failure raises RuntimeError with stderr."""
    with patch("src.render.video.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="codec error")
        with pytest.raises(RuntimeError, match="FFmpeg failed"):
            _run_ffmpeg(["ffmpeg", "-invalid"])
```

**Parametrized Tests:**
```python
@pytest.mark.parametrize("threshold,expected_min_speech", [
    (0.1, 50),   # Low threshold = more speech detected
    (0.5, 30),   # Medium threshold
    (0.9, 10),   # High threshold = less speech
])
def test_vad_threshold_affects_detection(threshold, expected_min_speech, sample_audio):
    """VAD threshold controls speech detection sensitivity."""
    result = detect_speech_silero(sample_audio, threshold=threshold)
    assert len(result) >= expected_min_speech
```

## Current Test Gap

**Status:** No tests exist for the quickedit source code.

**Immediate Actions:**
1. Create `tests/` directory
2. Add `conftest.py` with shared fixtures
3. Start with pure function tests in `test_smoothing.py`, `test_margin.py`
4. Add pytest-cov to dev dependencies for coverage tracking

**Example First Test File:**
```python
# tests/test_smoothing.py
import numpy as np
import pytest
from src.edit.smoothing import smooth, smooth_seconds

class TestSmooth:
    def test_smooth_removes_short_clips(self):
        """Short True segments are removed."""
        frames = np.array([False, False, True, True, False, False])
        result = smooth(frames, minclip=3, mincut=0)
        assert not result.any()  # 2-frame clip removed

    def test_smooth_fills_short_gaps(self):
        """Short False gaps are filled."""
        frames = np.array([True, True, False, True, True])
        result = smooth(frames, minclip=0, mincut=2)
        assert result.all()  # 1-frame gap filled

    def test_smooth_seconds_converts_to_frames(self):
        """smooth_seconds converts seconds to frame counts."""
        frames = np.zeros(100, dtype=bool)
        frames[10:20] = True  # 10 frames at 30fps = 0.33s
        result = smooth_seconds(frames, fps=30, minclip_sec=0.5, mincut_sec=0)
        assert not result.any()  # 0.33s clip < 0.5s minclip
```

---

*Testing analysis: 2026-04-01*
