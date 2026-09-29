from __future__ import annotations

import io
import threading

import cv2
import numpy as np

from quickedit.analyze import motion
from quickedit.analyze.motion import MotionResult


class _FakeCapture:
    def __init__(self, frames: list[np.ndarray] | None = None) -> None:
        self.frames = iter(frames or [])
        self.released = False

    def isOpened(self) -> bool:
        return True

    def get(self, prop: int) -> float:
        values = {
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_COUNT: 1.0,
            cv2.CAP_PROP_FRAME_WIDTH: 2.0,
            cv2.CAP_PROP_FRAME_HEIGHT: 2.0,
        }
        return values[prop]

    def read(self) -> tuple[bool, np.ndarray | None]:
        try:
            return True, next(self.frames)
        except StopIteration:
            return False, None

    def release(self) -> None:
        self.released = True


class _FakeProcess:
    def __init__(self, stdout) -> None:
        self.stdout = stdout
        self.stderr = io.BytesIO(b"decoder detail")
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


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


def test_ffmpeg_partial_frame_terminates_waits_and_closes_pipes(monkeypatch) -> None:
    capture = _FakeCapture()
    process = _FakeProcess(io.BytesIO(b"x"))
    monkeypatch.setattr(motion.cv2, "VideoCapture", lambda path: capture)
    monkeypatch.setattr(motion.subprocess, "Popen", lambda *args, **kwargs: process)

    with np.testing.assert_raises_regex(RuntimeError, "partial raw video frame"):
        motion._analyze_motion_ffmpeg("video.mp4", scale_width=2, blur_sigma=0)

    assert capture.released
    assert process.terminate_calls == 1
    assert process.returncode is not None
    assert process.stdout.closed
    assert process.stderr.closed


def test_ffmpeg_motion_timeout_terminates_and_reaps_process(monkeypatch) -> None:
    stopped = threading.Event()

    class BlockingPipe:
        closed = False

        def read(self, size: int = -1) -> bytes:
            stopped.wait(timeout=1)
            return b""

        def close(self) -> None:
            self.closed = True

    class BlockingProcess(_FakeProcess):
        def terminate(self) -> None:
            super().terminate()
            stopped.set()

    capture = _FakeCapture()
    process = BlockingProcess(BlockingPipe())
    monkeypatch.setattr(motion.cv2, "VideoCapture", lambda path: capture)
    monkeypatch.setattr(motion.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(motion, "FFMPEG_MOTION_TIMEOUT_SECONDS", 0.01)

    with np.testing.assert_raises_regex(RuntimeError, "motion decode timed out"):
        motion._analyze_motion_ffmpeg("video.mp4", scale_width=2, blur_sigma=0)

    assert process.terminate_calls == 1
    assert process.returncode == -15
    assert process.stdout.closed
    assert process.stderr.closed


def test_opencv_capture_released_when_preprocessing_fails(monkeypatch) -> None:
    capture = _FakeCapture([np.zeros((2, 2, 3), dtype=np.uint8)])
    monkeypatch.setattr(motion.cv2, "VideoCapture", lambda path: capture)

    def fail_preprocessing(*args, **kwargs):
        raise ValueError("bad frame")

    monkeypatch.setattr(motion, "_preprocess_frame", fail_preprocessing)

    with np.testing.assert_raises_regex(ValueError, "bad frame"):
        motion._analyze_motion_opencv("video.mp4")

    assert capture.released
