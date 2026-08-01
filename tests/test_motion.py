from __future__ import annotations

import numpy as np

from quickedit.analyze import motion
from quickedit.analyze.motion import MotionResult


def _motion_result() -> MotionResult:
    values = np.array([0.0, 0.5], dtype=np.float32)
    return MotionResult(
        motion_values=values,
        activity_frames=values >= 0.02,
        fps=30.0,
        total_frames=2,
    )


def test_analyze_motion_routes_to_ffmpeg_backend(monkeypatch) -> None:
    calls = []

    def fake_ffmpeg(*args, **kwargs):
        calls.append(kwargs)
        return _motion_result()

    monkeypatch.setattr(motion, "_analyze_motion_ffmpeg", fake_ffmpeg)

    result = motion.analyze_motion("video.mp4", backend="ffmpeg", frame_skip=3)

    assert result.total_frames == 2
    assert calls[0]["frame_skip"] == 3


def test_analyze_motion_routes_to_parallel_backend(monkeypatch) -> None:
    calls = []

    def fake_opencv(*args, **kwargs):
        calls.append(kwargs)
        return _motion_result()

    monkeypatch.setattr(motion, "_analyze_motion_opencv", fake_opencv)

    result = motion.analyze_motion(
        "video.mp4",
        backend="opencv-parallel",
        workers=4,
    )

    assert result.total_frames == 2
    assert calls[0]["workers"] == 4
