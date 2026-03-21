"""
Margin expansion for keep/remove arrays.

Borrowed from auto-editor's mutMargin pattern. Expands "keep" (True) regions
by N frames on each side to prevent jarring cuts that start or end mid-syllable.

Negative margins shrink "keep" regions (trim from edges).
"""

from __future__ import annotations

import numpy as np


def apply_margin(
    frames: np.ndarray,
    start_margin: int,
    end_margin: int,
) -> np.ndarray:
    """
    Expand True regions by start_margin frames before and end_margin frames after.

    Args:
        frames: bool array where True = keep, False = cut.
        start_margin: Number of frames to expand before each True region.
                      Positive = expand, negative = shrink.
        end_margin: Number of frames to expand after each True region.
                    Positive = expand, negative = shrink.

    Returns:
        New bool array with expanded regions.
    """
    if start_margin == 0 and end_margin == 0:
        return frames.copy()

    result = frames.copy()
    n = len(frames)

    # Find transition points (edges of True regions)
    # Pad with False to detect edges at boundaries
    padded = np.concatenate([[False], frames, [False]])
    # Rising edges: False -> True
    rising = np.where(np.diff(padded.astype(int)) == 1)[0]
    # Falling edges: True -> False
    falling = np.where(np.diff(padded.astype(int)) == -1)[0]

    if start_margin > 0 or end_margin > 0:
        # Expand: set extra frames to True around each region
        for start, end in zip(rising, falling):
            new_start = max(0, start - start_margin)
            new_end = min(n, end + end_margin)
            result[new_start:new_end] = True

    elif start_margin < 0 or end_margin < 0:
        # Shrink: start fresh from all False, then fill reduced regions
        result = np.zeros(n, dtype=bool)
        for start, end in zip(rising, falling):
            new_start = min(start - start_margin, n)  # -start_margin is positive
            new_end = max(end + end_margin, 0)  # +end_margin is negative
            if new_start < new_end:
                result[new_start:new_end] = True

    return result


def apply_margin_seconds(
    frames: np.ndarray,
    fps: float,
    start_margin_sec: float = 0.2,
    end_margin_sec: float = 0.2,
) -> np.ndarray:
    """
    Convenience wrapper that accepts margin in seconds.

    Default: 0.2s on each side (matches auto-editor's default).
    """
    start_frames = int(start_margin_sec * fps)
    end_frames = int(end_margin_sec * fps)
    return apply_margin(frames, start_frames, end_frames)
