"""Public CLI behavior tests that do not require media models or FFmpeg."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
