"""
Visual activity / motion detection using OpenCV frame differencing.

Produces a float array (one value per video frame) representing the
fraction of pixels that changed between consecutive frames. High values
indicate visual activity (typing, drawing, scrolling). Low values indicate
a static screen (stuck, frozen, idle).

Technique borrowed from auto-editor, enhanced with configurable preprocessing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MotionResult:
    """Result of motion/visual activity detection."""

    motion_values: np.ndarray  # float32 array, one per frame (0.0 - 1.0)
    activity_frames: np.ndarray  # bool array after threshold
    fps: float
    total_frames: int


def analyze_motion(
    video_path: str | Path,
    threshold: float = 0.02,
    scale_width: int = 400,
    blur_sigma: int = 9,
    frame_skip: int = 1,
    progress_callback: callable | None = None,
) -> MotionResult:
    """
    Detect visual activity in a video using frame differencing.

    Pipeline (per frame):
    1. Resize to scale_width (preserve aspect ratio)
    2. Convert to grayscale
    3. Apply Gaussian blur (reduce noise)
    4. Binary diff against previous frame
    5. motion_value = changed_pixels / total_pixels

    Args:
        video_path: Path to video file.
        threshold: Minimum motion fraction to count as "active" (default 2%).
        scale_width: Resize frames to this width before analysis.
        blur_sigma: Gaussian blur sigma for noise reduction.
        frame_skip: Analyze every Nth frame. Default 1 (all frames).
                    Set to 2-3 for faster processing on long videos.
                    Intermediate frames are interpolated.
        progress_callback: Optional callback(progress: float) called periodically.

    Returns:
        MotionResult with per-frame motion values and bool array.
    """
    video_path = str(video_path)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Gaussian kernel size must be odd
    ksize = blur_sigma * 2 + 1 if blur_sigma > 0 else 0

    log_interval = max(1, total_frames // 10)  # log every 10%

    # Collect analyzed frames if using frame_skip
    analyzed_frames: list[tuple[int, float]] = []
    prev_gray = None

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx >= total_frames:
            break

        # Skip frames if frame_skip > 1
        if frame_skip > 1 and frame_idx % frame_skip != 0:
            frame_idx += 1
            continue

        if frame_idx > 0 and frame_idx % log_interval == 0:
            pct = (frame_idx / total_frames) * 100
            logger.info(
                f"  Motion analysis: {pct:.0f}% ({frame_idx}/{total_frames} frames)"
            )
            if progress_callback:
                progress_callback(frame_idx / total_frames)

        # 1. Resize (preserve aspect ratio)
        h, w = frame.shape[:2]
        if w > scale_width:
            scale = scale_width / w
            new_w = scale_width
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # 2. Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 3. Apply Gaussian blur
        if blur_sigma > 0:
            gray = cv2.GaussianBlur(gray, (ksize, ksize), blur_sigma)

        # 4. Binary diff against previous frame
        if prev_gray is not None:
            # Absolute difference
            diff = cv2.absdiff(gray, prev_gray)
            # Threshold: any pixel change > 10 counts as "changed"
            _, binary_diff = cv2.threshold(diff, 10, 255, cv2.THRESH_BINARY)
            # Fraction of pixels that changed
            changed = np.count_nonzero(binary_diff)
            total = binary_diff.size
            motion_value = changed / total
        else:
            # First frame: no previous frame to compare
            motion_value = 0.0

        analyzed_frames.append((frame_idx, motion_value))
        prev_gray = gray
        frame_idx += 1

    cap.release()

    actual_total = frame_idx

    # Interpolate if we skipped frames
    if frame_skip > 1:
        motion_values = _interpolate_motion_values(analyzed_frames, actual_total)
    else:
        motion_values = np.zeros(actual_total, dtype=np.float32)
        for idx, val in analyzed_frames:
            if idx < actual_total:
                motion_values[idx] = val

    # Apply threshold to get bool array
    activity_frames = motion_values >= threshold

    return MotionResult(
        motion_values=motion_values,
        activity_frames=activity_frames,
        fps=fps,
        total_frames=actual_total,
    )


def _interpolate_motion_values(
    analyzed: list[tuple[int, float]],
    total_frames: int,
) -> np.ndarray:
    """Interpolate motion values for skipped frames."""
    motion_values = np.zeros(total_frames, dtype=np.float32)

    if not analyzed:
        return motion_values

    for i, (frame_idx, value) in enumerate(analyzed):
        if frame_idx < total_frames:
            motion_values[frame_idx] = value

        # Linear interpolation to next analyzed frame
        if i < len(analyzed) - 1:
            next_idx, next_value = analyzed[i + 1]
            for j in range(frame_idx + 1, min(next_idx, total_frames)):
                t = (j - frame_idx) / (next_idx - frame_idx)
                motion_values[j] = value + t * (next_value - value)

    # Fill remaining frames after last analyzed frame with last value
    if analyzed:
        last_idx, last_value = analyzed[-1]
        for j in range(last_idx + 1, total_frames):
            motion_values[j] = last_value

    return motion_values


def analyze_motion_region(
    video_path: str | Path,
    region: tuple[int, int, int, int] | None = None,
    threshold: float = 0.02,
    scale_width: int = 400,
    blur_sigma: int = 9,
) -> MotionResult:
    """
    Detect motion in a specific region of the video.

    Useful for screen recordings where only part of the screen has
    the code editor / drawing area.

    Args:
        region: (x, y, w, h) crop region in original video coordinates.
                None means full frame.
        Other args same as analyze_motion.
    """
    if region is None:
        return analyze_motion(video_path, threshold, scale_width, blur_sigma)

    rx, ry, rw, rh = region
    video_path = str(video_path)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    motion_values = np.zeros(total_frames, dtype=np.float32)
    prev_gray = None
    ksize = blur_sigma * 2 + 1 if blur_sigma > 0 else 0

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret or frame_idx >= total_frames:
            break

        # Crop to region
        cropped = frame[ry : ry + rh, rx : rx + rw]
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)

        if blur_sigma > 0:
            gray = cv2.GaussianBlur(gray, (ksize, ksize), blur_sigma)

        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            _, binary_diff = cv2.threshold(diff, 10, 255, cv2.THRESH_BINARY)
            changed = np.count_nonzero(binary_diff)
            total = binary_diff.size
            motion_values[frame_idx] = changed / total

        prev_gray = gray
        frame_idx += 1

    cap.release()

    motion_values = motion_values[:frame_idx]
    activity_frames = motion_values >= threshold

    return MotionResult(
        motion_values=motion_values,
        activity_frames=activity_frames,
        fps=fps,
        total_frames=frame_idx,
    )
