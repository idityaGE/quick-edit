from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quickedit.analyze import vad


def test_extract_audio_translates_timeout_and_bounds_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0],
            kwargs["timeout"],
            stderr=b"x" * (vad.DIAGNOSTIC_LIMIT + 500),
        )

    monkeypatch.setattr(vad.subprocess, "run", time_out)

    with pytest.raises(RuntimeError, match="audio extraction timed out") as exc_info:
        vad.extract_audio(tmp_path / "input.mp4", tmp_path / "audio.wav")

    assert len(str(exc_info.value)) < vad.DIAGNOSTIC_LIMIT + 100


def test_audio_probe_timeout_is_not_reported_as_no_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(vad.subprocess, "run", time_out)

    with pytest.raises(RuntimeError, match="audio stream inspection timed out"):
        vad._has_audio_stream(tmp_path / "input.mp4")
