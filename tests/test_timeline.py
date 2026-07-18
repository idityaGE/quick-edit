"""
Tests for src/timeline/timeline.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from quickedit.timeline.timeline import (
    Clip,
    CutSegment,
    Timeline,
    _fmt_time,
    frames_to_timeline,
    merge_timelines,
)


class TestClip:
    """Tests for the Clip dataclass."""

    def test_clip_src_duration(self):
        """src_duration property calculates correctly."""
        clip = Clip(
            source="/test.mp4",
            src_start=10.0,
            src_end=25.0,
            dst_start=0.0,
            duration=15.0,
        )

        assert clip.src_duration == 15.0

    def test_clip_with_speed(self):
        """Clip with non-1.0 speed."""
        clip = Clip(
            source="/test.mp4",
            src_start=0.0,
            src_end=10.0,
            dst_start=0.0,
            duration=5.0,
            speed=2.0,
        )

        assert clip.src_duration == 10.0
        assert clip.duration == 5.0


class TestTimeline:
    """Tests for the Timeline class."""

    def test_output_duration_empty(self):
        """Empty timeline has 0 duration."""
        tl = Timeline(source="/test.mp4", fps=30.0, duration=60.0)

        assert tl.output_duration == 0.0

    def test_output_duration_with_clips(self, sample_timeline):
        """Output duration calculated from clips."""
        # sample_timeline: clips with durations 5, 10, 15
        # Last clip: dst_start=15.0, duration=15.0
        assert sample_timeline.output_duration == 30.0

    def test_time_saved(self, sample_timeline):
        """Time saved calculation."""
        # source duration: 60.0, output: 30.0
        assert sample_timeline.time_saved == 30.0

    def test_time_saved_pct(self, sample_timeline):
        """Time saved percentage."""
        assert sample_timeline.time_saved_pct == 50.0

    def test_time_saved_pct_zero_duration(self):
        """Zero duration doesn't cause division by zero."""
        tl = Timeline(source="/test.mp4", fps=30.0, duration=0.0)

        assert tl.time_saved_pct == 0.0

    def test_summary(self, sample_timeline):
        """Summary string is correct."""
        summary = sample_timeline.summary()

        assert "Original duration:" in summary
        assert "Output duration:" in summary
        assert "Time saved:" in summary
        assert "50.0%" in summary
        assert "Clips: 3" in summary
        assert "Cuts:  3" in summary

    def test_to_json_returns_string(self, sample_timeline):
        """to_json returns valid JSON string."""
        json_str = sample_timeline.to_json()

        data = json.loads(json_str)
        assert data["source"] == "/test/video.mp4"
        assert data["fps"] == 30.0
        assert data["duration"] == 60.0
        assert len(data["clips"]) == 3
        assert len(data["cuts"]) == 3

    def test_to_json_writes_file(self, sample_timeline):
        """to_json writes to file when path provided."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            sample_timeline.to_json(path)

            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert data["source"] == "/test/video.mp4"
        finally:
            Path(path).unlink()

    def test_from_json(self, sample_timeline):
        """from_json loads timeline correctly."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            sample_timeline.to_json(path)
            loaded = Timeline.from_json(path)

            assert loaded.source == sample_timeline.source
            assert loaded.fps == sample_timeline.fps
            assert loaded.duration == sample_timeline.duration
            assert len(loaded.clips) == len(sample_timeline.clips)
            assert len(loaded.cuts) == len(sample_timeline.cuts)
        finally:
            Path(path).unlink()

    def test_json_roundtrip(self, sample_timeline):
        """to_json/from_json preserves data."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            sample_timeline.to_json(path)
            loaded = Timeline.from_json(path)

            # Check clips
            for orig, loaded_clip in zip(sample_timeline.clips, loaded.clips):
                assert orig.source == loaded_clip.source
                assert orig.src_start == loaded_clip.src_start
                assert orig.src_end == loaded_clip.src_end
                assert orig.dst_start == loaded_clip.dst_start
                assert orig.duration == loaded_clip.duration

            # Check cuts
            for orig, loaded_cut in zip(sample_timeline.cuts, loaded.cuts):
                assert orig.src_start == loaded_cut.src_start
                assert orig.src_end == loaded_cut.src_end
                assert orig.reason == loaded_cut.reason
        finally:
            Path(path).unlink()


class TestFramesToTimeline:
    """Tests for the frames_to_timeline() function."""

    def test_frames_to_timeline_basic(self):
        """Converts bool array to clips."""
        # Pattern: 5 False, 10 True, 5 False, 10 True
        frames = np.array(
            [False] * 5 + [True] * 10 + [False] * 5 + [True] * 10,
            dtype=bool,
        )
        fps = 10.0  # 10 frames per second
        duration = 3.0  # 30 frames / 10 fps

        tl = frames_to_timeline(frames, "/test.mp4", fps, duration)

        assert len(tl.clips) == 2
        assert len(tl.cuts) == 2

        # First clip: frames 5-15, time 0.5s-1.5s
        assert tl.clips[0].src_start == 0.5
        assert tl.clips[0].src_end == 1.5
        assert tl.clips[0].dst_start == 0.0
        assert tl.clips[0].duration == 1.0

        # Second clip: frames 20-30, time 2.0s-3.0s
        assert tl.clips[1].src_start == 2.0
        assert tl.clips[1].src_end == 3.0
        assert tl.clips[1].dst_start == 1.0  # after first clip
        assert tl.clips[1].duration == 1.0

    def test_frames_to_timeline_all_keep(self):
        """Single clip for all-True array."""
        frames = np.ones(30, dtype=bool)
        fps = 30.0
        duration = 1.0

        tl = frames_to_timeline(frames, "/test.mp4", fps, duration)

        assert len(tl.clips) == 1
        assert len(tl.cuts) == 0
        assert tl.clips[0].src_start == 0.0
        assert tl.clips[0].src_end == 1.0
        assert tl.output_duration == 1.0

    def test_frames_to_timeline_all_cut(self):
        """Empty clips for all-False array."""
        frames = np.zeros(30, dtype=bool)
        fps = 30.0
        duration = 1.0

        tl = frames_to_timeline(frames, "/test.mp4", fps, duration)

        assert len(tl.clips) == 0
        assert len(tl.cuts) == 1
        assert tl.output_duration == 0.0

    def test_frames_to_timeline_alternating(self):
        """Multiple clips for alternating pattern."""
        # Alternating 3-frame segments
        frames = np.array(
            [True] * 3 + [False] * 3 + [True] * 3 + [False] * 3,
            dtype=bool,
        )
        fps = 3.0  # 3 frames per second
        duration = 4.0

        tl = frames_to_timeline(frames, "/test.mp4", fps, duration)

        assert len(tl.clips) == 2
        assert len(tl.cuts) == 2

    def test_frames_to_timeline_empty(self):
        """Empty array returns empty timeline."""
        frames = np.array([], dtype=bool)
        fps = 30.0
        duration = 0.0

        tl = frames_to_timeline(frames, "/test.mp4", fps, duration)

        assert len(tl.clips) == 0
        assert len(tl.cuts) == 0

    def test_frames_to_timeline_preserves_metadata(self):
        """Metadata is preserved in timeline."""
        frames = np.ones(30, dtype=bool)

        tl = frames_to_timeline(
            frames,
            "/path/to/video.mp4",
            fps=24.0,
            duration=1.25,
            width=1920,
            height=1080,
        )

        assert tl.source == "/path/to/video.mp4"
        assert tl.fps == 24.0
        assert tl.duration == 1.25
        assert tl.width == 1920
        assert tl.height == 1080


class TestMergeTimelines:
    """Tests for the merge_timelines() function."""

    def test_merge_timelines_no_cuts(self, sample_timeline):
        """Empty cuts list returns original."""
        result = merge_timelines(sample_timeline, [])

        assert len(result.clips) == len(sample_timeline.clips)

    def test_merge_timelines_with_cuts(self, sample_timeline):
        """Cuts are applied correctly."""
        # sample_timeline has clips:
        # 0-5s, 10-20s, 30-45s
        # Add a cut in the middle of the second clip (10-20s)
        llm_cuts = [
            CutSegment(src_start=12.0, src_end=15.0, reason="filler"),
        ]

        result = merge_timelines(sample_timeline, llm_cuts)

        # Second clip should be split into two:
        # 10-12s and 15-20s
        assert len(result.clips) == 4  # 1 + 2 (split) + 1

    def test_merge_timelines_cut_at_clip_start(self, sample_timeline):
        """Cut at the start of a clip."""
        # Cut first 2 seconds of second clip (10-20s)
        llm_cuts = [
            CutSegment(src_start=10.0, src_end=12.0, reason="filler"),
        ]

        result = merge_timelines(sample_timeline, llm_cuts)

        # Check that second clip now starts at 12.0
        clip_starts = [c.src_start for c in result.clips]
        assert 12.0 in clip_starts

    def test_merge_timelines_cut_at_clip_end(self, sample_timeline):
        """Cut at the end of a clip."""
        # Cut last 3 seconds of second clip (10-20s)
        llm_cuts = [
            CutSegment(src_start=17.0, src_end=20.0, reason="filler"),
        ]

        result = merge_timelines(sample_timeline, llm_cuts)

        # Find the clip that used to end at 20.0
        clip_ends = [c.src_end for c in result.clips]
        assert 17.0 in clip_ends

    def test_merge_timelines_cut_spans_entire_clip(self, sample_timeline):
        """Cut that spans entire clip removes it."""
        # Cut the entire first clip (0-5s)
        llm_cuts = [
            CutSegment(src_start=0.0, src_end=5.0, reason="filler"),
        ]

        result = merge_timelines(sample_timeline, llm_cuts)

        # First clip should be gone
        assert len(result.clips) == 2
        assert result.clips[0].src_start == 10.0

    def test_merge_timelines_overlapping_cuts(self, sample_timeline):
        """Overlapping cuts handled correctly."""
        # Two overlapping cuts in the second clip (10-20s)
        llm_cuts = [
            CutSegment(src_start=12.0, src_end=15.0, reason="filler"),
            CutSegment(src_start=14.0, src_end=17.0, reason="repetition"),
        ]

        result = merge_timelines(sample_timeline, llm_cuts)

        # After merge, the effective cut should be 12.0-17.0
        # So second clip (10-20) becomes 10-12 and 17-20
        # Total clips: 1 + 2 + 1 = 4
        assert len(result.clips) == 4

    def test_merge_timelines_recalculates_dst_start(self, sample_timeline):
        """dst_start is recalculated after merge."""
        llm_cuts = [
            CutSegment(src_start=12.0, src_end=15.0, reason="filler"),
        ]

        result = merge_timelines(sample_timeline, llm_cuts)

        # Verify dst_start is sequential
        cursor = 0.0
        for clip in result.clips:
            assert clip.dst_start == cursor
            cursor += clip.duration

    def test_merge_timelines_cut_spans_multiple_clips(self):
        """A single LLM cut that spans multiple clips affects all of them."""
        # Build a timeline with two clips separated by a gap
        base = Timeline(
            source="/test.mp4",
            fps=30.0,
            duration=20.0,
            clips=[
                Clip(
                    source="/test.mp4",
                    src_start=0.0,
                    src_end=5.0,
                    dst_start=0.0,
                    duration=5.0,
                ),
                Clip(
                    source="/test.mp4",
                    src_start=10.0,
                    src_end=15.0,
                    dst_start=5.0,
                    duration=5.0,
                ),
            ],
            cuts=[
                CutSegment(src_start=5.0, src_end=10.0, reason="silence"),
            ],
        )

        # LLM cut spans from inside first clip through the gap and into second clip
        llm_cuts = [
            CutSegment(src_start=3.0, src_end=12.0, reason="tangent"),
        ]

        result = merge_timelines(base, llm_cuts)

        # First clip: 0-5s cut by 3-12s → keep 0-3s
        # Second clip: 10-15s cut by 3-12s → keep 12-15s
        assert len(result.clips) == 2
        assert result.clips[0].src_start == 0.0
        assert result.clips[0].src_end == 3.0
        assert result.clips[1].src_start == 12.0
        assert result.clips[1].src_end == 15.0

        # dst_start should be sequential
        assert result.clips[0].dst_start == 0.0
        assert result.clips[1].dst_start == 3.0


class TestFormatTime:
    """Tests for the _fmt_time() helper."""

    def test_fmt_time_seconds_only(self):
        """Format seconds only."""
        assert _fmt_time(30.5) == "00:30.50"

    def test_fmt_time_minutes_and_seconds(self):
        """Format minutes and seconds."""
        assert _fmt_time(90.25) == "01:30.25"

    def test_fmt_time_zero(self):
        """Format zero."""
        assert _fmt_time(0.0) == "00:00.00"

    def test_fmt_time_large(self):
        """Format large time value."""
        assert _fmt_time(3661.5) == "61:01.50"
