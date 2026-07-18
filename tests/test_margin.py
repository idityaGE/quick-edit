"""
Tests for src/edit/margin.py
"""

from __future__ import annotations

import numpy as np

from quickedit.edit.margin import apply_margin, apply_margin_seconds


class TestApplyMargin:
    """Tests for the apply_margin() function."""

    def test_margin_noop_when_zero(self):
        """Returns copy when start_margin=0 and end_margin=0."""
        frames = np.array([False, True, True, True, False], dtype=bool)
        result = apply_margin(frames, start_margin=0, end_margin=0)

        np.testing.assert_array_equal(result, frames)
        # Ensure it's a copy, not the same array
        assert result is not frames

    def test_margin_expands_start(self):
        """Positive start_margin expands before True regions."""
        # Pattern: 5 False, 5 True, 5 False
        frames = np.array(
            [False] * 5 + [True] * 5 + [False] * 5,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=2, end_margin=0)

        # True region should start 2 frames earlier
        expected = np.array(
            [False] * 3 + [True] * 7 + [False] * 5,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_expands_end(self):
        """Positive end_margin expands after True regions."""
        # Pattern: 5 False, 5 True, 5 False
        frames = np.array(
            [False] * 5 + [True] * 5 + [False] * 5,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=0, end_margin=2)

        # True region should end 2 frames later
        expected = np.array(
            [False] * 5 + [True] * 7 + [False] * 3,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_expands_both_sides(self):
        """Positive margins expand on both sides."""
        # Pattern: 5 False, 5 True, 5 False
        frames = np.array(
            [False] * 5 + [True] * 5 + [False] * 5,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=2, end_margin=3)

        # True region should expand 2 before and 3 after
        expected = np.array(
            [False] * 3 + [True] * 10 + [False] * 2,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_shrinks_start(self):
        """Negative start_margin shrinks from start."""
        # Pattern: 3 False, 8 True, 3 False
        frames = np.array(
            [False] * 3 + [True] * 8 + [False] * 3,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=-2, end_margin=0)

        # True region should start 2 frames later
        expected = np.array(
            [False] * 5 + [True] * 6 + [False] * 3,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_shrinks_end(self):
        """Negative end_margin shrinks from end."""
        # Pattern: 3 False, 8 True, 3 False
        frames = np.array(
            [False] * 3 + [True] * 8 + [False] * 3,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=0, end_margin=-2)

        # True region should end 2 frames earlier
        expected = np.array(
            [False] * 3 + [True] * 6 + [False] * 5,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_respects_start_boundary(self):
        """Doesn't expand beyond array start."""
        # Pattern: 2 False, 5 True, 3 False
        frames = np.array(
            [False] * 2 + [True] * 5 + [False] * 3,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=5, end_margin=0)

        # Can only expand 2 frames before (to array start)
        expected = np.array(
            [True] * 7 + [False] * 3,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_respects_end_boundary(self):
        """Doesn't expand beyond array end."""
        # Pattern: 3 False, 5 True, 2 False
        frames = np.array(
            [False] * 3 + [True] * 5 + [False] * 2,
            dtype=bool,
        )

        result = apply_margin(frames, start_margin=0, end_margin=5)

        # Can only expand 2 frames after (to array end)
        expected = np.array(
            [False] * 3 + [True] * 7,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_merges_adjacent_regions(self):
        """Expanding regions that become adjacent merge."""
        # Pattern: 3 False, 3 True, 3 False, 3 True, 3 False (15 total)
        frames = np.array(
            [False] * 3 + [True] * 3 + [False] * 3 + [True] * 3 + [False] * 3,
            dtype=bool,
        )

        # Expand by 2 on each end
        result = apply_margin(frames, start_margin=2, end_margin=2)

        # First region [3-6) expands to [1-8)
        # Second region [9-12) expands to [7-14)
        # They overlap at [7-8), so they merge: [1-14)
        # Final: 1 False, 13 True, 1 False
        expected = np.array(
            [False] * 1 + [True] * 13 + [False] * 1,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_multiple_regions(self, sample_frames):
        """Works correctly with multiple True regions."""
        # sample_frames: 10 False, 20 True, 5 False, 15 True, 10 False
        result = apply_margin(sample_frames, start_margin=3, end_margin=2)

        # First region: starts at 10, expands to 7; ends at 30, expands to 32
        # Second region: starts at 35, expands to 32 (overlaps with first!); ends at 50, expands to 52
        # Since they overlap, they merge: [7, 52]
        expected = np.array(
            [False] * 7 + [True] * 45 + [False] * 8,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_shrink_eliminates_small_region(self):
        """Shrinking can eliminate a small region entirely."""
        # Pattern: 5 False, 3 True, 5 False
        frames = np.array(
            [False] * 5 + [True] * 3 + [False] * 5,
            dtype=bool,
        )

        # Shrink by 2 on each side (total 4, but region is only 3)
        result = apply_margin(frames, start_margin=-2, end_margin=-2)

        # Region should be eliminated
        expected = np.zeros(13, dtype=bool)
        np.testing.assert_array_equal(result, expected)


class TestApplyMarginSeconds:
    """Tests for the apply_margin_seconds() function."""

    def test_margin_seconds_conversion(self):
        """Converts seconds to frames correctly."""
        fps = 30.0
        # 0.1s at 30fps = 3 frames
        frames = np.array(
            [False] * 10 + [True] * 5 + [False] * 10,
            dtype=bool,
        )

        result = apply_margin_seconds(
            frames, fps, start_margin_sec=0.1, end_margin_sec=0.1
        )

        # Should expand 3 frames on each side
        expected = np.array(
            [False] * 7 + [True] * 11 + [False] * 7,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_seconds_default_values(self):
        """Default margins (0.2s) work correctly."""
        fps = 30.0
        # 0.2s at 30fps = 6 frames
        frames = np.array(
            [False] * 15 + [True] * 10 + [False] * 15,
            dtype=bool,
        )

        result = apply_margin_seconds(frames, fps)  # Uses default 0.2s

        # Should expand 6 frames on each side
        expected = np.array(
            [False] * 9 + [True] * 22 + [False] * 9,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_margin_seconds_fractional_conversion(self):
        """Fractional frame counts are converted to int correctly."""
        fps = 24.0
        # 0.15s at 24fps = 3.6 -> 3 frames (int truncation)
        frames = np.array(
            [False] * 10 + [True] * 5 + [False] * 10,
            dtype=bool,
        )

        result = apply_margin_seconds(
            frames, fps, start_margin_sec=0.15, end_margin_sec=0.15
        )

        # Should expand 3 frames on each side
        expected = np.array(
            [False] * 7 + [True] * 11 + [False] * 7,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)
