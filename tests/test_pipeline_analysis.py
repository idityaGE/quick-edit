from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from quickedit import pipeline
from quickedit.analyze.transcribe import TranscriptionResult
from quickedit.pipeline import PipelineConfig, PipelineResult


def _patch_analysis(
    monkeypatch: pytest.MonkeyPatch,
    transcript: TranscriptionResult | None = None,
) -> None:
    monkeypatch.setattr(pipeline.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(
        pipeline,
        "get_video_info",
        lambda path: {
            "fps": 1.0,
            "duration": 4.0,
            "total_frames": 4,
            "width": 1280,
            "height": 720,
            "has_audio": True,
        },
    )
    monkeypatch.setattr(
        pipeline,
        "_run_vad_cached",
        lambda *args, **kwargs: np.ones(4, dtype=bool),
    )
    if transcript is not None:
        monkeypatch.setattr(
            pipeline,
            "_run_transcription_cached",
            lambda *args, **kwargs: transcript,
        )


def test_detection_names_in_expr() -> None:
    assert pipeline._detection_names_in_expr("speech") == {"speech"}
    assert pipeline._detection_names_in_expr("or:speech,motion") == {
        "speech",
        "motion",
    }
    assert pipeline._detection_names_in_expr(["or", "speech", ["not", "words"]]) == {
        "speech",
        "words",
    }


def test_pipeline_skips_motion_when_combine_uses_only_speech(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    calls: list[str] = []

    monkeypatch.setattr(pipeline.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(
        pipeline,
        "get_video_info",
        lambda path: {
            "fps": 1.0,
            "duration": 4.0,
            "total_frames": 4,
            "width": 1280,
            "height": 720,
            "has_audio": True,
        },
    )

    def fake_vad(*args, **kwargs):
        calls.append("vad")
        return np.array([True, True, False, False], dtype=bool)

    def fake_motion(*args, **kwargs):
        calls.append("motion")
        return np.array([False, False, True, True], dtype=bool)

    monkeypatch.setattr(pipeline, "_run_vad_cached", fake_vad)
    monkeypatch.setattr(pipeline, "_run_motion_cached", fake_motion)

    result = pipeline.run_pipeline(
        PipelineConfig(
            input_path=str(input_path),
            output_path=str(output_path),
            combine_expr="speech",
            subtitle_style="none",
            dry_run=True,
            use_cache=False,
        )
    )

    assert calls == ["vad"]
    assert result.timeline.output_duration == 2.0


def test_silent_activity_uses_active_frame_ratio_boundary() -> None:
    speech_frames = np.zeros(4, dtype=bool)
    motion_frames = np.array([True, True, False, False], dtype=bool)

    at_boundary = pipeline._classify_silent_segments(
        keep_frames=np.ones(4, dtype=bool),
        speech_frames=speech_frames,
        motion_frames=motion_frames,
        fps=1.0,
        active_frame_ratio_threshold=0.5,
        min_duration=0.0,
    )
    above_boundary = pipeline._classify_silent_segments(
        keep_frames=np.ones(4, dtype=bool),
        speech_frames=speech_frames,
        motion_frames=motion_frames,
        fps=1.0,
        active_frame_ratio_threshold=0.5001,
        min_duration=0.0,
    )

    assert at_boundary[0].motion_score == 0.5
    assert at_boundary[0].has_visual_activity is True
    assert above_boundary[0].has_visual_activity is False
    assert PipelineConfig().silent_segment_active_frame_ratio_threshold == 0.5


def test_pipeline_wires_silent_ratio_separately_from_motion_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_transcript: TranscriptionResult,
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    _patch_analysis(monkeypatch, sample_transcript)
    monkeypatch.setattr(
        pipeline,
        "_run_motion_cached",
        lambda *args, **kwargs: np.ones(4, dtype=bool),
    )
    observed_thresholds: list[float] = []

    def fake_classify(
        keep_frames,
        speech_frames,
        motion_frames,
        fps,
        active_frame_ratio_threshold,
        min_duration,
    ):
        observed_thresholds.append(active_frame_ratio_threshold)
        return []

    monkeypatch.setattr(pipeline, "_classify_silent_segments", fake_classify)
    monkeypatch.setattr(pipeline, "analyze_with_llm", lambda **kwargs: [])

    pipeline.run_pipeline(
        PipelineConfig(
            input_path=str(input_path),
            output_path=str(output_path),
            combine_expr="speech",
            subtitle_style="none",
            use_llm=True,
            motion_threshold=0.01,
            silent_segment_active_frame_ratio_threshold=0.75,
            dry_run=True,
            use_cache=False,
        )
    )

    assert observed_thresholds == [0.75]


def test_pipeline_stores_wall_clock_total(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    reference_path = tmp_path / "reference.json"
    reference_path.write_text("reference")
    _patch_analysis(monkeypatch)
    wall_times = iter([100.0, 103.25])
    monkeypatch.setattr(pipeline.time, "perf_counter", lambda: next(wall_times))

    result = pipeline.run_pipeline(
        PipelineConfig(
            input_path=str(input_path),
            output_path=str(output_path),
            combine_expr="speech",
            subtitle_style="none",
            dry_run=True,
            use_cache=False,
        )
    )

    assert result.timing["total"] == 3.25
    assert output_path.with_suffix(".timeline.json").exists()
    assert (output_path.with_suffix(".timeline.json").stat().st_mode & 0o777) == (
        reference_path.stat().st_mode & 0o777
    )


def test_pipeline_summary_uses_wall_total_without_double_counting(
    sample_timeline,
) -> None:
    result = PipelineResult(
        output_path="/edited.mp4",
        timeline=sample_timeline,
        transcript=None,
        llm_decisions=[],
        timing={"vad": 8.0, "motion": 9.0, "total": 9.5},
    )

    summary = result.summary()

    assert "  vad: 8.0s" in summary
    assert "  motion: 9.0s" in summary
    assert summary.count("  total:") == 1
    assert "  total: 9.5s" in summary
    assert "26.5s" not in summary


def test_sidecars_publish_only_after_successful_render(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_transcript: TranscriptionResult,
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    timeline_path = output_path.with_suffix(".timeline.json")
    subtitle_path = output_path.with_suffix(".srt")
    timeline_path.write_text("old timeline")
    subtitle_path.write_text("old subtitles")
    timeline_path.chmod(0o640)
    subtitle_path.chmod(0o600)
    _patch_analysis(monkeypatch, sample_transcript)

    def fake_render_video(**kwargs) -> Path:
        temporary_subtitle = Path(kwargs["subtitle_path"])
        assert temporary_subtitle != subtitle_path
        assert temporary_subtitle.suffix == ".srt"
        assert temporary_subtitle.exists()
        assert timeline_path.read_text() == "old timeline"
        assert subtitle_path.read_text() == "old subtitles"
        return output_path

    monkeypatch.setattr(pipeline, "render_video", fake_render_video)

    pipeline.run_pipeline(
        PipelineConfig(
            input_path=str(input_path),
            output_path=str(output_path),
            combine_expr="speech",
            subtitle_style="simple",
            use_cache=False,
        )
    )

    timeline_data = json.loads(timeline_path.read_text())
    assert timeline_data["source"] == str(input_path)
    assert "Hello world" in subtitle_path.read_text()
    assert list(tmp_path.glob(".*.quickedit-*")) == []

    assert (timeline_path.stat().st_mode & 0o777) == 0o640
    assert (subtitle_path.stat().st_mode & 0o777) == 0o600


def test_render_failure_preserves_existing_sidecars_and_cleans_temporaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sample_transcript: TranscriptionResult,
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    timeline_path = output_path.with_suffix(".timeline.json")
    subtitle_path = output_path.with_suffix(".srt")
    timeline_path.write_text("old timeline")
    subtitle_path.write_text("old subtitles")
    _patch_analysis(monkeypatch, sample_transcript)

    def fail_render_video(**kwargs) -> Path:
        temporary_subtitle = Path(kwargs["subtitle_path"])
        assert temporary_subtitle.exists()
        assert temporary_subtitle != subtitle_path
        raise RuntimeError("render failed")

    monkeypatch.setattr(pipeline, "render_video", fail_render_video)

    with pytest.raises(RuntimeError, match="render failed"):
        pipeline.run_pipeline(
            PipelineConfig(
                input_path=str(input_path),
                output_path=str(output_path),
                combine_expr="speech",
                subtitle_style="simple",
                use_cache=False,
            )
        )

    assert timeline_path.read_text() == "old timeline"
    assert subtitle_path.read_text() == "old subtitles"
    assert list(tmp_path.glob(".*.quickedit-*")) == []
