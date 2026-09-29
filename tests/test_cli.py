"""Public CLI behavior tests that do not require media models or FFmpeg."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from quickedit import cli


def _result(output_path: str) -> SimpleNamespace:
    return SimpleNamespace(output_path=output_path, summary=lambda: "processed")


def test_cli_is_local_first(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    captured = {}

    def fake_run_pipeline(config):
        captured["config"] = config
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main, [str(input_path), "--dry-run", "--subtitle-style", "none"]
    )

    assert result.exit_code == 0, result.output
    assert captured["config"].use_llm is False


def test_cli_requires_credentials_before_llm_processing(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = CliRunner().invoke(
        cli.main, [str(input_path), "--llm", "--dry-run", "--subtitle-style", "none"]
    )

    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_cli_refuses_existing_output_without_overwrite(tmp_path: Path) -> None:
    input_path = tmp_path / "recording.mp4"
    output_path = tmp_path / "edited.mp4"
    input_path.touch()
    output_path.touch()

    result = CliRunner().invoke(cli.main, [str(input_path), "-o", str(output_path)])

    assert result.exit_code == 2
    assert "--overwrite" in result.output


def test_cli_clears_cache_before_processing(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    cleared = []

    monkeypatch.setattr(
        cli.cache, "clear_cache", lambda path: cleared.append(path) or 3
    )
    monkeypatch.setattr(cli, "run_pipeline", lambda config: _result(config.output_path))

    result = CliRunner().invoke(
        cli.main,
        [str(input_path), "--clear-cache", "--dry-run", "--subtitle-style", "none"],
    )

    assert result.exit_code == 0, result.output
    assert cleared == [str(input_path)]
    assert "Cleared 3 cached item(s)." in result.output


def test_cli_passes_motion_backend_options(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    captured = {}

    def fake_run_pipeline(config):
        captured["config"] = config
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main,
        [
            str(input_path),
            "--dry-run",
            "--subtitle-style",
            "none",
            "--motion-backend",
            "opencv-parallel",
            "--motion-workers",
            "4",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["config"].motion_backend == "opencv-parallel"
    assert captured["config"].motion_workers == 4


def test_cli_defaults_to_ffmpeg_motion_backend(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    captured = {}

    def fake_run_pipeline(config):
        captured["config"] = config
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main, [str(input_path), "--dry-run", "--subtitle-style", "none"]
    )

    assert result.exit_code == 0, result.output
    assert captured["config"].motion_backend == "ffmpeg"


def test_cli_passes_silent_segment_active_frame_ratio(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    captured = {}

    def fake_run_pipeline(config):
        captured["config"] = config
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main,
        [
            str(input_path),
            "--silent-segment-active-frame-ratio",
            "0.75",
            "--dry-run",
            "--subtitle-style",
            "none",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["config"].silent_segment_active_frame_ratio_threshold == 0.75


@pytest.mark.parametrize("ratio", ["-0.01", "1.01"])
def test_cli_rejects_out_of_range_silent_segment_active_frame_ratio(
    monkeypatch, tmp_path: Path, ratio: str
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    attempted = []
    monkeypatch.setattr(
        cli, "run_pipeline", lambda config: attempted.append(config.input_path)
    )

    result = CliRunner().invoke(
        cli.main,
        [
            str(input_path),
            "--silent-segment-active-frame-ratio",
            ratio,
            "--dry-run",
            "--subtitle-style",
            "none",
        ],
    )

    assert result.exit_code == 1
    assert "silent_segment_active_frame_ratio must be 0.0-1.0" in result.output
    assert attempted == []


@pytest.mark.parametrize(
    ("failing_names", "processed"),
    [
        ({"first.mp4"}, 1),
        ({"first.mp4", "second.mp4"}, 0),
    ],
)
def test_batch_attempts_every_input_and_exits_nonzero_after_summary(
    monkeypatch,
    tmp_path: Path,
    failing_names: set[str],
    processed: int,
) -> None:
    input_paths = [tmp_path / "first.mp4", tmp_path / "second.mp4"]
    for input_path in input_paths:
        input_path.touch()
    attempted = []

    def fake_run_pipeline(config):
        attempted.append(Path(config.input_path).name)
        if Path(config.input_path).name in failing_names:
            raise RuntimeError("expected failure")
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main,
        [
            *(str(path) for path in input_paths),
            "--dry-run",
            "--subtitle-style",
            "none",
        ],
    )

    assert result.exit_code == 1
    assert attempted == ["first.mp4", "second.mp4"]
    assert "Batch Summary" in result.output
    assert f"Processed: {processed}/2" in result.output
    assert f"Failed:    {2 - processed}" in result.output


def test_batch_rejects_duplicate_outputs_before_work(
    monkeypatch, tmp_path: Path
) -> None:
    input_paths = [
        tmp_path / "one" / "recording.mp4",
        tmp_path / "two" / "recording.mp4",
    ]
    for input_path in input_paths:
        input_path.parent.mkdir()
        input_path.touch()
    output_dir = tmp_path / "new-output"
    attempted = []
    monkeypatch.setattr(
        cli, "run_pipeline", lambda config: attempted.append(config.input_path)
    )

    result = CliRunner().invoke(
        cli.main,
        [
            *(str(path) for path in input_paths),
            "--output",
            str(output_dir),
            "--dry-run",
            "--subtitle-style",
            "none",
        ],
    )

    assert result.exit_code == 2
    assert "same output destination" in result.output
    assert attempted == []
    assert not output_dir.exists()


def test_batch_rejects_outputs_that_overlap_later_inputs(
    monkeypatch, tmp_path: Path
) -> None:
    input_paths = [
        tmp_path / "recording.mp4",
        tmp_path / "recording_edited.mp4",
    ]
    for input_path in input_paths:
        input_path.touch()
    attempted = []
    monkeypatch.setattr(
        cli, "run_pipeline", lambda config: attempted.append(config.input_path)
    )

    result = CliRunner().invoke(
        cli.main,
        [
            *(str(path) for path in input_paths),
            "--overwrite",
            "--subtitle-style",
            "none",
        ],
    )

    assert result.exit_code == 2
    assert "overlap batch input files" in result.output
    assert attempted == []


def test_cli_rejects_unknown_config_keys_before_work(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"motion_workres": 4}))
    attempted = []
    monkeypatch.setattr(
        cli, "run_pipeline", lambda config: attempted.append(config.input_path)
    )

    result = CliRunner().invoke(
        cli.main, [str(input_path), "--config", str(config_path)]
    )

    assert result.exit_code == 2
    assert "Unknown config key(s): motion_workres" in result.output
    assert attempted == []


def test_cli_config_uses_exposed_option_parameter_names(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "combine_expr": "speech",
                "dry_run": True,
                "subtitle_style": "none",
            }
        )
    )
    captured = {}

    def fake_run_pipeline(config):
        captured["config"] = config
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main, [str(input_path), "--config", str(config_path)]
    )

    assert result.exit_code == 0, result.output
    assert captured["config"].combine_expr == "speech"
    assert captured["config"].dry_run is True


@pytest.mark.parametrize(
    "expression",
    [
        "or:speech",
        "or:speech,",
        "not:speech,motion",
        "nand:speech,motion",
        "or:speech,captions",
    ],
)
def test_cli_rejects_malformed_combine_before_work(
    monkeypatch, tmp_path: Path, expression: str
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    attempted = []
    monkeypatch.setattr(
        cli, "run_pipeline", lambda config: attempted.append(config.input_path)
    )

    result = CliRunner().invoke(
        cli.main,
        [
            str(input_path),
            "--combine",
            expression,
            "--dry-run",
            "--subtitle-style",
            "none",
        ],
    )

    assert result.exit_code == 2
    assert "combine expression" in result.output.lower() or "operands" in result.output
    assert attempted == []


@pytest.mark.parametrize(
    ("subtitle_style", "artifact_suffix"),
    [
        ("none", ".timeline.json"),
        ("fancy", ".ass"),
        ("simple", ".srt"),
    ],
)
def test_dry_run_refuses_existing_artifacts_before_work(
    monkeypatch,
    tmp_path: Path,
    subtitle_style: str,
    artifact_suffix: str,
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    output_path.with_suffix(artifact_suffix).touch()
    attempted = []
    monkeypatch.setattr(
        cli, "run_pipeline", lambda config: attempted.append(config.input_path)
    )

    result = CliRunner().invoke(
        cli.main,
        [
            str(input_path),
            "--output",
            str(output_path),
            "--dry-run",
            "--subtitle-style",
            subtitle_style,
        ],
    )

    assert result.exit_code == 2
    assert "--overwrite" in result.output
    assert attempted == []


def test_dry_run_overwrite_allows_existing_sidecar_and_does_not_claim_video(
    monkeypatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "recording.mp4"
    input_path.touch()
    output_path = tmp_path / "edited.mp4"
    output_path.with_suffix(".ass").touch()
    attempted = []

    def fake_run_pipeline(config):
        attempted.append(config.input_path)
        return _result(config.output_path)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    result = CliRunner().invoke(
        cli.main,
        [
            str(input_path),
            "--output",
            str(output_path),
            "--dry-run",
            "--subtitle-style",
            "fancy",
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert attempted == [str(input_path)]
    assert "Output:" not in result.output
    assert "no video was rendered" in result.output
    assert str(output_path.with_suffix(".timeline.json")) in result.output
    assert not output_path.exists()


def test_input_argument_rejects_directories(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli.main, [str(tmp_path)])

    assert result.exit_code == 2
    assert "File" in result.output
