"""
Iterative smoothing to eliminate micro-cuts and micro-clips.

Borrowed from auto-editor's smoothing algorithm.

Two parameters:
- minclip: Any "keep" segment shorter than this -> set to remove
- mincut:  Any "cut" gap shorter than this -> set to keep

Runs iteratively until the array stabilizes. This prevents rapid-fire
micro-cuts that look terrible in the output video.
"""

from __future__ import annotations

import numpy as np


def smooth(
    frames: np.ndarray,
    minclip: int,
    mincut: int,
    max_iterations: int = 100,
) -> np.ndarray:
    """
    Iteratively smooth a bool array by removing short clips and short gaps.

    Args:
        frames: bool array (True = keep, False = cut).
        minclip: Minimum length of a "keep" segment in frames.
                 Shorter segments are set to False (removed).
        mincut: Minimum length of a "cut" segment in frames.
                Shorter gaps are set to True (filled/kept).
        max_iterations: Safety limit to prevent infinite loops.

    Returns:
        Smoothed bool array.
    """
    if minclip <= 0 and mincut <= 0:
        return frames.copy()

    result = frames.copy()

    for _ in range(max_iterations):
        changed = False

        # Pass 1: Remove clips shorter than minclip
        if minclip > 0:
            new_result = _remove_short_segments(result, target=True, min_length=minclip)
            if not np.array_equal(new_result, result):
                changed = True
                result = new_result

        # Pass 2: Fill gaps shorter than mincut
        if mincut > 0:
            new_result = _remove_short_segments(result, target=False, min_length=mincut)
            if not np.array_equal(new_result, result):
                changed = True
                result = new_result

        # Converged
        if not changed:
            break

    return result


def _remove_short_segments(
    frames: np.ndarray,
    target: bool,
    min_length: int,
) -> np.ndarray:
    """
    Find segments of `target` value shorter than `min_length` and flip them.

    If target=True and min_length=5: any run of True shorter than 5 frames
    gets set to False.

    If target=False and min_length=3: any run of False shorter than 3 frames
    gets set to True (filling short gaps).
    """
    result = frames.copy()
    n = len(frames)

    i = 0
    while i < n:
        if result[i] == target:
            # Start of a target segment
            seg_start = i
            while i < n and result[i] == target:
                i += 1
            seg_end = i
            seg_length = seg_end - seg_start

            # If too short, flip it
            if seg_length < min_length:
                result[seg_start:seg_end] = not target
        else:
            i += 1

    return result


def smooth_seconds(
    frames: np.ndarray,
    fps: float,
    minclip_sec: float = 0.1,
    mincut_sec: float = 0.2,
) -> np.ndarray:
    """
    Convenience wrapper that accepts smoothing parameters in seconds.

    Defaults match auto-editor:
    - minclip: 0.1s (remove keep segments shorter than 100ms)
    - mincut: 0.2s (fill cut gaps shorter than 200ms)
    """
    minclip_frames = int(minclip_sec * fps)
    mincut_frames = int(mincut_sec * fps)
    return smooth(frames, minclip_frames, mincut_frames)
