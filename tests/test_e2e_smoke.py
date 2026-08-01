"""End-to-end smoke tests using generated media and the real CLI pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and FFprobe are required for media smoke tests",
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


@pytest.fixture
def generated_video(tmp_path: Path) -> Path:
    video_path = tmp_path / "quickedit-smoke.mp4"
    result = _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=10:duration=1.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video_path),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert video_path.exists()
    return video_path


def test_quickedit_dry_run_speech_only_writes_timeline(
    generated_video: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "dry-run-output.mp4"
    result = _run(
        [
            sys.executable,
            "-m",
            "quickedit.cli",
            str(generated_video),
            "--dry-run",
            "--combine",
            "speech",
            "--subtitle-style",
            "none",
            "--no-cache",
            "-o",
            str(output_path),
        ]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not output_path.exists()

    timeline_path = output_path.with_suffix(".timeline.json")
    assert timeline_path.exists()
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert timeline["source"] == str(generated_video)
    assert timeline["duration"] > 0
    assert "clips" in timeline
    assert "cuts" in timeline
    assert not output_path.with_suffix(".srt").exists()
    assert not output_path.with_suffix(".ass").exists()


def test_quickedit_renders_generated_motion_video(
    generated_video: Path, tmp_path: Path
) -> None:
    output_path = tmp_path / "render-output.mp4"
    result = _run(
        [
            sys.executable,
            "-m",
            "quickedit.cli",
            str(generated_video),
            "--combine",
            "motion",
            "--subtitle-style",
            "none",
            "--no-cache",
            "--motion-threshold",
            "0.001",
            "-o",
            str(output_path),
        ]
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.with_suffix(".timeline.json").exists()

    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(output_path),
        ]
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "video"
