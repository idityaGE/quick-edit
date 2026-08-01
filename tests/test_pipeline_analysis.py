from __future__ import annotations

from pathlib import Path

import numpy as np

from quickedit import pipeline
from quickedit.pipeline import PipelineConfig


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
