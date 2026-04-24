"""
Shared fixtures for QuickEdit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock
import json

import numpy as np
import pytest

from src.timeline.timeline import Timeline, Clip, CutSegment
from src.analyze.transcribe import TranscriptionResult, Segment, Word


@pytest.fixture
def sample_frames() -> np.ndarray:
    """
    Boolean frame array for testing smoothing/margin.

    Pattern: 10 False, 20 True, 5 False, 15 True, 10 False
    Total: 60 frames
    """
    return np.array(
        [False] * 10 + [True] * 20 + [False] * 5 + [True] * 15 + [False] * 10,
        dtype=bool,
    )


@pytest.fixture
def sample_timeline() -> Timeline:
    """Timeline with test clips for rendering tests."""
    tl = Timeline(
        source="/test/video.mp4",
        fps=30.0,
        duration=60.0,
        width=1920,
        height=1080,
    )
    tl.clips = [
        Clip(
            source="/test/video.mp4",
            src_start=0.0,
            src_end=5.0,
            dst_start=0.0,
            duration=5.0,
        ),
        Clip(
            source="/test/video.mp4",
            src_start=10.0,
            src_end=20.0,
            dst_start=5.0,
            duration=10.0,
        ),
        Clip(
            source="/test/video.mp4",
            src_start=30.0,
            src_end=45.0,
            dst_start=15.0,
            duration=15.0,
        ),
    ]
    tl.cuts = [
        CutSegment(src_start=5.0, src_end=10.0, reason="silence"),
        CutSegment(src_start=20.0, src_end=30.0, reason="filler"),
        CutSegment(src_start=45.0, src_end=60.0, reason="silence"),
    ]
    return tl


@pytest.fixture
def sample_transcript() -> TranscriptionResult:
    """Word-level transcript for LLM/subtitle tests."""
    words = [
        Word(text="Hello", start=0.0, end=0.5, probability=0.95),
        Word(text="world", start=0.5, end=1.0, probability=0.92),
        Word(text="um", start=1.0, end=1.2, probability=0.88),
        Word(text="this", start=1.5, end=1.8, probability=0.91),
        Word(text="is", start=1.8, end=2.0, probability=0.93),
        Word(text="a", start=2.0, end=2.1, probability=0.97),
        Word(text="test", start=2.1, end=2.5, probability=0.94),
        Word(text="basically", start=3.0, end=3.5, probability=0.89),
        Word(text="we", start=3.5, end=3.7, probability=0.90),
        Word(text="are", start=3.7, end=3.9, probability=0.92),
        Word(text="testing", start=3.9, end=4.5, probability=0.91),
    ]

    segments = [
        Segment(
            text="Hello world um this is a test",
            start=0.0,
            end=2.5,
            words=words[:7],
        ),
        Segment(
            text="basically we are testing",
            start=3.0,
            end=4.5,
            words=words[7:],
        ),
    ]

    return TranscriptionResult(
        segments=segments,
        words=words,
        language="en",
        language_probability=0.98,
        duration=5.0,
        text="Hello world um this is a test basically we are testing",
    )


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for LLM tests."""
    mock_client = MagicMock()

    # Default response
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                {
                    "decisions": [
                        {
                            "start_time": 1.0,
                            "end_time": 1.2,
                            "reason": "filler_word",
                            "confidence": 0.9,
                            "transcript": "um",
                            "note": "Filler word",
                        }
                    ]
                }
            )
        )
    ]
    mock_client.messages.create.return_value = mock_response

    return mock_client
