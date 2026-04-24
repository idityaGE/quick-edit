"""
Tests for src/edit/smoothing.py
"""

from __future__ import annotations

import numpy as np

from src.edit.smoothing import smooth, smooth_seconds, _remove_short_segments


class TestSmooth:
    """Tests for the smooth() function."""

    def test_smooth_noop_when_disabled(self):
        """Returns copy when minclip=0 and mincut=0."""
        frames = np.array([True, False, True, True, False, False, True], dtype=bool)
        result = smooth(frames, minclip=0, mincut=0)

        np.testing.assert_array_equal(result, frames)
        # Ensure it's a copy, not the same array
        assert result is not frames

    def test_smooth_removes_short_clips(self):
        """Short True segments below minclip are removed."""
        # Pattern: 5 False, 2 True (short clip), 5 False
        frames = np.array(
            [False] * 5 + [True] * 2 + [False] * 5,
            dtype=bool,
        )
        result = smooth(frames, minclip=3, mincut=0)

        # The 2-frame True clip should be removed (set to False)
        expected = np.zeros(12, dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_smooth_fills_short_gaps(self):
        """Short False gaps below mincut are filled."""
        # Pattern: 5 True, 2 False (short gap), 5 True
        frames = np.array(
            [True] * 5 + [False] * 2 + [True] * 5,
            dtype=bool,
        )
        result = smooth(frames, minclip=0, mincut=3)

        # The 2-frame False gap should be filled (set to True)
        expected = np.ones(12, dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_smooth_preserves_long_clips(self):
        """Clips >= minclip are preserved."""
        # Pattern: 5 False, 5 True (long clip), 5 False
        frames = np.array(
            [False] * 5 + [True] * 5 + [False] * 5,
            dtype=bool,
        )
        result = smooth(frames, minclip=3, mincut=0)

        # The 5-frame True clip should be preserved
        np.testing.assert_array_equal(result, frames)

    def test_smooth_preserves_long_gaps(self):
        """Gaps >= mincut are preserved."""
        # Pattern: 5 True, 5 False (long gap), 5 True
        frames = np.array(
            [True] * 5 + [False] * 5 + [True] * 5,
            dtype=bool,
        )
        result = smooth(frames, minclip=0, mincut=3)

        # The 5-frame False gap should be preserved
        np.testing.assert_array_equal(result, frames)

    def test_smooth_iterates_until_stable(self, sample_frames):
        """Complex arrays converge correctly."""
        # Pattern from fixture: 10 False, 20 True, 5 False, 15 True, 10 False
        # With mincut=6, the 5-frame gap should be filled, merging the two True regions
        result = smooth(sample_frames, minclip=0, mincut=6)

        # Should become: 10 False, 40 True (merged), 10 False
        expected = np.array(
            [False] * 10 + [True] * 40 + [False] * 10,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)

    def test_smooth_edge_cases_empty_array(self):
        """Empty array returns empty array."""
        frames = np.array([], dtype=bool)
        result = smooth(frames, minclip=3, mincut=3)

        assert len(result) == 0

    def test_smooth_edge_cases_all_true(self):
        """All True array stays all True."""
        frames = np.ones(10, dtype=bool)
        result = smooth(frames, minclip=3, mincut=3)

        np.testing.assert_array_equal(result, frames)

    def test_smooth_edge_cases_all_false(self):
        """All False array stays all False."""
        frames = np.zeros(10, dtype=bool)
        result = smooth(frames, minclip=3, mincut=3)

        np.testing.assert_array_equal(result, frames)

    def test_smooth_edge_cases_single_element_true(self):
        """Single True element is removed if minclip > 1."""
        frames = np.array([True], dtype=bool)

        result = smooth(frames, minclip=2, mincut=0)
        np.testing.assert_array_equal(result, [False])

        result = smooth(frames, minclip=1, mincut=0)
        np.testing.assert_array_equal(result, [True])

    def test_smooth_edge_cases_single_element_false(self):
        """Single False element is filled if mincut > 1."""
        frames = np.array([False], dtype=bool)

        result = smooth(frames, minclip=0, mincut=2)
        np.testing.assert_array_equal(result, [True])

        result = smooth(frames, minclip=0, mincut=1)
        np.testing.assert_array_equal(result, [False])

    def test_smooth_both_operations(self):
        """Test minclip and mincut together."""
        # Pattern: 3 True, 2 False, 2 True, 3 False, 5 True
        # minclip=3 should remove the 2-True clip
        # mincut=3 should fill the 2-False gap
        frames = np.array(
            [True] * 3 + [False] * 2 + [True] * 2 + [False] * 3 + [True] * 5,
            dtype=bool,
        )

        result = smooth(frames, minclip=3, mincut=3)

        # After minclip: 3T, 2F, 2F, 3F, 5T -> 3T, 7F, 5T
        # After mincut: 3T, 7F, 5T (7F gap is preserved, >= 3)
        # But we also need to fill the initial 2F gap first iteration
        # The result depends on iteration order. Let's check convergence.
        # First iteration:
        #   minclip removes 2T -> [True]*3 + [False]*7 + [True]*5
        #   mincut doesn't fill 7F gap
        # Converged.
        expected = np.array(
            [True] * 3 + [False] * 7 + [True] * 5,
            dtype=bool,
        )
        np.testing.assert_array_equal(result, expected)


class TestSmoothSeconds:
    """Tests for the smooth_seconds() function."""

    def test_smooth_seconds_conversion(self):
        """Converts seconds to frames correctly."""
        fps = 30.0
        # 0.1s at 30fps = 3 frames
        # 0.2s at 30fps = 6 frames
        frames = np.array(
            [False] * 10 + [True] * 2 + [False] * 10,  # 2-frame clip (< 3 frames)
            dtype=bool,
        )

        result = smooth_seconds(frames, fps, minclip_sec=0.1, mincut_sec=0.0)

        # minclip = 0.1 * 30 = 3 frames, so 2-frame clip should be removed
        expected = np.zeros(22, dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_smooth_seconds_preserves_longer_than_threshold(self):
        """Clips longer than threshold in seconds are preserved."""
        fps = 30.0
        frames = np.array(
            [False] * 10 + [True] * 5 + [False] * 10,  # 5-frame clip (> 3 frames)
            dtype=bool,
        )

        result = smooth_seconds(frames, fps, minclip_sec=0.1, mincut_sec=0.0)

        # 5 frames > 3 frame threshold, so clip is preserved
        np.testing.assert_array_equal(result, frames)


class TestRemoveShortSegments:
    """Tests for the _remove_short_segments helper function."""

    def test_remove_short_true_segments(self):
        """Removes short True segments."""
        frames = np.array(
            [False, True, True, False, True, True, True, True, False], dtype=bool
        )

        # Remove True segments shorter than 3
        result = _remove_short_segments(frames, target=True, min_length=3)

        # First True segment (2 frames) should be removed
        # Second True segment (4 frames) should be preserved
        expected = np.array(
            [False, False, False, False, True, True, True, True, False], dtype=bool
        )
        np.testing.assert_array_equal(result, expected)

    def test_remove_short_false_segments(self):
        """Removes (fills) short False segments."""
        frames = np.array(
            [True, False, False, True, False, False, False, False, True], dtype=bool
        )

        # Remove False segments shorter than 3
        result = _remove_short_segments(frames, target=False, min_length=3)

        # First False segment (2 frames) should be filled
        # Second False segment (4 frames) should be preserved
        expected = np.array(
            [True, True, True, True, False, False, False, False, True], dtype=bool
        )
        np.testing.assert_array_equal(result, expected)
