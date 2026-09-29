from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quickedit.render import video
from quickedit.timeline.timeline import Clip, Timeline


def _timeline(source: Path, clip_count: int = 2) -> Timeline:
    timeline = Timeline(source=str(source), fps=30.0, duration=float(clip_count))
    timeline.clips = [
        Clip(
            source=str(source),
            src_start=float(index),
            src_end=float(index) + 0.5,
            dst_start=float(index) * 0.5,
            duration=0.5,
        )
        for index in range(clip_count)
    ]
    return timeline


def test_render_video_rejects_unknown_strategy_before_ffmpeg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("FFmpeg must not be called")

    monkeypatch.setattr(video, "_run_ffmpeg", fail_if_called)

    with pytest.raises(ValueError, match="Unknown render strategy"):
        video.render_video(
            _timeline(tmp_path / "input.mp4", clip_count=1),
            tmp_path / "output.mp4",
            render_strategy="not-a-strategy",
        )

    assert not called


def test_segment_strategy_uses_one_final_encode_for_arbitrary_codec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    concat_contents: list[str] = []

    def capture_command(cmd: list[str], quiet: bool = False):
        commands.append(cmd)
        concat_path = Path(cmd[cmd.index("-i") + 1])
        concat_contents.append(concat_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(video, "_run_ffmpeg", capture_command)

    video.render_segments_then_concat(
        _timeline(tmp_path / "source's clip.mov"),
        tmp_path / "output.mov",
        subtitle_path=tmp_path / "captions.srt",
        codec="prores_ks",
        audio_codec="pcm_s16le",
    )

    assert len(commands) == 1
    command = commands[0]
    assert command[command.index("-f") + 1] == "concat"
    assert command[command.index("-c:v") + 1] == "prores_ks"
    assert command[command.index("-c:a") + 1] == "pcm_s16le"
    assert "mpegts" not in command
    assert "subtitles=" in command[command.index("-vf") + 1]
    assert concat_contents[0].count("file '") == 2
    assert "source'\\''s clip.mov" in concat_contents[0]


def test_segment_strategy_rejects_source_paths_with_line_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("FFmpeg must not be called")

    monkeypatch.setattr(video, "_run_ffmpeg", fail_if_called)

    with pytest.raises(ValueError, match="line breaks"):
        video.render_segments_then_concat(
            _timeline(tmp_path / "source\ninjected.mov"),
            tmp_path / "output.mp4",
        )

    assert not called


def test_segment_strategy_preserves_default_output_codecs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def capture_command(cmd: list[str], quiet: bool = False):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(video, "_run_ffmpeg", capture_command)

    video.render_segments_then_concat(
        _timeline(tmp_path / "source.mp4"),
        tmp_path / "output.mp4",
    )

    command = commands[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"


def test_run_ffmpeg_translates_timeout_and_bounds_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0],
            kwargs["timeout"],
            stderr="x" * (video.DIAGNOSTIC_LIMIT + 500),
        )

    monkeypatch.setattr(video.subprocess, "run", time_out)

    with pytest.raises(RuntimeError, match="FFmpeg timed out") as exc_info:
        video._run_ffmpeg(["ffmpeg", "-version"])

    assert len(str(exc_info.value)) < video.DIAGNOSTIC_LIMIT + 100
