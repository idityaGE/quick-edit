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
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
    pixel_threshold: int = 10,
    backend: str = "opencv",
    workers: int = 1,
    progress_callback: Callable[[float], None] | None = None,
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
        pixel_threshold: Minimum pixel brightness change (0-255) to count as changed.
        backend: Motion backend: "opencv", "opencv-parallel", or "ffmpeg".
        workers: Worker count for the opencv-parallel backend.
        progress_callback: Optional callback(progress: float) called periodically.

    Returns:
        MotionResult with per-frame motion values and bool array.
    """
    if backend == "ffmpeg":
        return _analyze_motion_ffmpeg(
            video_path,
            threshold=threshold,
            scale_width=scale_width,
            blur_sigma=blur_sigma,
            frame_skip=frame_skip,
            pixel_threshold=pixel_threshold,
            progress_callback=progress_callback,
        )
    if backend == "opencv-parallel":
        return _analyze_motion_opencv(
            video_path,
            threshold=threshold,
            scale_width=scale_width,
            blur_sigma=blur_sigma,
            frame_skip=frame_skip,
            pixel_threshold=pixel_threshold,
            workers=workers,
            progress_callback=progress_callback,
        )
    if backend != "opencv":
        raise ValueError(f"Unknown motion backend: {backend}")
    return _analyze_motion_opencv(
        video_path,
        threshold=threshold,
        scale_width=scale_width,
        blur_sigma=blur_sigma,
        frame_skip=frame_skip,
        pixel_threshold=pixel_threshold,
        workers=1,
        progress_callback=progress_callback,
    )


def _analyze_motion_opencv(
    video_path: str | Path,
    threshold: float = 0.02,
    scale_width: int = 400,
    blur_sigma: int = 9,
    frame_skip: int = 1,
    pixel_threshold: int = 10,
    workers: int = 1,
    progress_callback: Callable[[float], None] | None = None,
) -> MotionResult:
    """Detect motion with OpenCV decode and optional parallel preprocessing."""
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

    def process_gray(frame: np.ndarray) -> np.ndarray:
        return _preprocess_frame(frame, scale_width, ksize, blur_sigma)

    def add_motion_value(frame_number: int, gray: np.ndarray) -> None:
        nonlocal prev_gray

        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            _, binary_diff = cv2.threshold(
                diff, pixel_threshold, 255, cv2.THRESH_BINARY
            )
            changed = np.count_nonzero(binary_diff)
            total = binary_diff.size
            motion_value = changed / total
        else:
            motion_value = 0.0

        analyzed_frames.append((frame_number, motion_value))
        prev_gray = gray

    workers = max(1, workers)
    batch_size = max(32, workers * 16)
    pending: list[tuple[int, np.ndarray]] = []

    def flush_pending(
        executor: ThreadPoolExecutor | None,
        batch: list[tuple[int, np.ndarray]],
    ) -> None:
        if not batch:
            return
        if executor is None:
            gray_frames = [process_gray(frame) for _, frame in batch]
        else:
            gray_frames = list(executor.map(process_gray, [frame for _, frame in batch]))
        for (frame_number, _), gray in zip(batch, gray_frames, strict=True):
            add_motion_value(frame_number, gray)

    frame_idx = 0
    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
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
                _report_motion_progress(frame_idx, total_frames, progress_callback)

            pending.append((frame_idx, frame))
            if len(pending) >= batch_size:
                flush_pending(executor, pending)
                pending.clear()

            frame_idx += 1
        flush_pending(executor, pending)
    finally:
        if executor is not None:
            executor.shutdown()

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


def _preprocess_frame(
    frame: np.ndarray,
    scale_width: int,
    ksize: int,
    blur_sigma: int,
) -> np.ndarray:
    """Resize, grayscale, and blur one frame for motion analysis."""
    h, w = frame.shape[:2]
    if w > scale_width:
        scale = scale_width / w
        new_w = scale_width
        new_h = int(h * scale)
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if blur_sigma > 0:
        gray = cv2.GaussianBlur(gray, (ksize, ksize), blur_sigma)

    return gray


def _report_motion_progress(
    frame_idx: int,
    total_frames: int,
    progress_callback: Callable[[float], None] | None,
) -> None:
    pct = (frame_idx / total_frames) * 100
    logger.info(f"  Motion analysis: {pct:.0f}% ({frame_idx}/{total_frames} frames)")
    if progress_callback:
        progress_callback(frame_idx / total_frames)


def _analyze_motion_ffmpeg(
    video_path: str | Path,
    threshold: float = 0.02,
    scale_width: int = 400,
    blur_sigma: int = 9,
    frame_skip: int = 1,
    pixel_threshold: int = 10,
    progress_callback: Callable[[float], None] | None = None,
) -> MotionResult:
    """Decode scaled grayscale frames with FFmpeg, then compute frame diffs."""
    video_path = str(video_path)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if width <= 0 or height <= 0:
        raise RuntimeError(f"Cannot read video dimensions: {video_path}")

    out_w = min(width, scale_width)
    out_h = int(height * (out_w / width)) if width > 0 else height
    out_h = max(1, out_h)
    frame_size = out_w * out_h
    ksize = blur_sigma * 2 + 1 if blur_sigma > 0 else 0
    log_interval = max(1, total_frames // 10)

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        video_path,
        "-an",
        "-vf",
        f"scale={out_w}:{out_h},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.stdout is None:
        raise RuntimeError("FFmpeg stdout pipe was not created")

    analyzed_frames: list[tuple[int, float]] = []
    prev_gray = None
    frame_idx = 0

    while True:
        raw = proc.stdout.read(frame_size)
        if not raw:
            break
        if len(raw) != frame_size:
            proc.kill()
            raise RuntimeError("FFmpeg returned a partial raw video frame")

        if frame_skip <= 1 or frame_idx % frame_skip == 0:
            if frame_idx > 0 and frame_idx % log_interval == 0:
                _report_motion_progress(frame_idx, total_frames, progress_callback)

            gray = np.frombuffer(raw, dtype=np.uint8).reshape((out_h, out_w))
            if blur_sigma > 0:
                gray = cv2.GaussianBlur(gray, (ksize, ksize), blur_sigma)

            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                _, binary_diff = cv2.threshold(
                    diff, pixel_threshold, 255, cv2.THRESH_BINARY
                )
                changed = np.count_nonzero(binary_diff)
                total = binary_diff.size
                motion_value = changed / total
            else:
                motion_value = 0.0

            analyzed_frames.append((frame_idx, motion_value))
            prev_gray = gray

        frame_idx += 1

    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    returncode = proc.wait()
    if returncode != 0:
        raise RuntimeError(f"FFmpeg motion decode failed: {stderr.strip()}")

    actual_total = frame_idx

    if frame_skip > 1:
        motion_values = _interpolate_motion_values(analyzed_frames, actual_total)
    else:
        motion_values = np.zeros(actual_total, dtype=np.float32)
        for idx, val in analyzed_frames:
            if idx < actual_total:
                motion_values[idx] = val

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
        return analyze_motion(
            video_path, threshold, scale_width, blur_sigma, pixel_threshold=10
        )

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
