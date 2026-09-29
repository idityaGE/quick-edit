"""
Voice Activity Detection using Silero VAD.

Produces a bool array (one value per video frame) indicating whether
speech is present in each frame's time window.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FFMPEG_TIMEOUT_SECONDS = 300
FFPROBE_TIMEOUT_SECONDS = 30
DIAGNOSTIC_LIMIT = 2000


def _diagnostic_tail(value: str | bytes | None) -> str:
    """Return a bounded, readable tail of subprocess diagnostics."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return value.strip()[-DIAGNOSTIC_LIMIT:]


def _run_media_command(
    cmd: list[str],
    *,
    operation: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run a bounded FFmpeg-family command with consistent errors."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        detail = _diagnostic_tail(exc.stderr)
        message = f"{operation} timed out after {timeout} seconds"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc

    if result.returncode != 0:
        detail = _diagnostic_tail(result.stderr)
        message = f"{operation} failed (exit {result.returncode})"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)
    return result


@dataclass
class VADResult:
    """Result of voice activity detection."""

    speech_frames: np.ndarray  # bool array, one per video frame
    fps: float
    total_frames: int
    speech_segments: list[tuple[float, float]]  # (start_sec, end_sec) pairs


def extract_audio(
    video_path: str | Path, output_path: str | Path, sr: int = 16000
) -> Path:
    """Extract audio from video as 16kHz mono WAV using FFmpeg."""
    output_path = Path(output_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",  # no video
        "-acodec",
        "pcm_s16le",  # 16-bit PCM
        "-ar",
        str(sr),  # resample to target rate
        "-ac",
        "1",  # mono
        str(output_path),
    ]
    _run_media_command(
        cmd,
        operation="FFmpeg audio extraction",
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    return output_path


def get_video_info(video_path: str | Path) -> dict:
    """Get video metadata: fps, duration, total_frames, width, height."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate,avg_frame_rate,duration,nb_frames,width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    result = _run_media_command(
        cmd,
        operation="FFprobe video inspection",
        timeout=FFPROBE_TIMEOUT_SECONDS,
    )

    data = json.loads(result.stdout)
    stream = data["streams"][0]

    # Parse r_frame_rate
    r_fps = 0.0
    rate_str = stream.get("r_frame_rate")
    if rate_str:
        try:
            num, den = map(int, rate_str.split("/"))
            if den > 0:
                r_fps = num / den
        except (ValueError, ZeroDivisionError):
            pass

    # Parse avg_frame_rate
    avg_fps = 0.0
    avg_rate_str = stream.get("avg_frame_rate")
    if avg_rate_str:
        try:
            num, den = map(int, avg_rate_str.split("/"))
            if den > 0:
                avg_fps = num / den
        except (ValueError, ZeroDivisionError):
            pass

    # Choose best FPS: prefer avg_fps if r_fps is unusually high (e.g. VFR/timebase) or 0
    if avg_fps > 0:
        if r_fps > 120.0 or r_fps <= 0.0 or abs(r_fps - avg_fps) > 5.0:
            fps = avg_fps
        else:
            fps = r_fps
    else:
        fps = r_fps if r_fps > 0 else 30.0  # fallback to 30 if both invalid

    # Duration from stream or format
    duration = float(stream.get("duration", 0))
    if duration == 0:
        duration = float(data.get("format", {}).get("duration", 0))

    # Total frames: from metadata or calculate
    nb_frames = stream.get("nb_frames")
    if nb_frames and nb_frames != "N/A":
        total_frames = int(nb_frames)
    else:
        total_frames = int(duration * fps)

    return {
        "fps": fps,
        "duration": duration,
        "total_frames": total_frames,
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "has_audio": _has_audio_stream(video_path),
    }


def _has_audio_stream(video_path: str | Path) -> bool:
    """Return whether FFprobe can find at least one audio stream."""
    result = _run_media_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        operation="FFprobe audio stream inspection",
        timeout=FFPROBE_TIMEOUT_SECONDS,
    )
    return bool(result.stdout.strip())


def read_wav_samples(wav_path: str | Path) -> np.ndarray:
    """Read raw PCM samples from a 16-bit mono WAV file."""
    import wave

    with wave.open(str(wav_path), "rb") as wf:
        if wf.getnchannels() != 1:
            raise ValueError(f"Expected mono audio, got {wf.getnchannels()} channels")
        if wf.getsampwidth() != 2:
            raise ValueError(f"Expected 16-bit audio, got {wf.getsampwidth() * 8}-bit")
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    # Convert to float32 normalized to [-1, 1]
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def detect_speech_silero(
    audio_samples: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 100,
    window_size_samples: int = 512,
) -> list[tuple[float, float]]:
    """
    Run the bundled faster-whisper Silero VAD on audio samples.

    Returns list of (start_sec, end_sec) speech segments.
    This avoids fetching and executing a remote Torch Hub repository at runtime.
    """
    del min_speech_duration_ms, min_silence_duration_ms, window_size_samples
    return _detect_speech_faster_whisper_vad(audio_samples, sample_rate, threshold)


def _detect_speech_faster_whisper_vad(
    audio_samples: np.ndarray,
    sample_rate: int = 16000,
    threshold: float = 0.5,
) -> list[tuple[float, float]]:
    """Fallback VAD using faster-whisper's bundled Silero VAD."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    vad_options = VadOptions(
        threshold=threshold,
        min_speech_duration_ms=250,
        min_silence_duration_ms=100,
    )
    speech_timestamps = get_speech_timestamps(audio_samples, vad_options)

    segments = []
    for ts in speech_timestamps:
        start_sec = ts["start"] / sample_rate
        end_sec = ts["end"] / sample_rate
        segments.append((start_sec, end_sec))

    return segments


def speech_segments_to_frame_array(
    segments: list[tuple[float, float]],
    fps: float,
    total_frames: int,
) -> np.ndarray:
    """
    Convert speech segments (start_sec, end_sec) to a per-frame bool array.

    Returns np.ndarray of bool, length = total_frames.
    frame[i] = True means speech is present in that frame's time window.
    """
    frames = np.zeros(total_frames, dtype=bool)

    for start_sec, end_sec in segments:
        start_frame = int(start_sec * fps)
        end_frame = min(int(end_sec * fps) + 1, total_frames)
        frames[start_frame:end_frame] = True

    return frames


def analyze_vad(
    video_path: str | Path,
    threshold: float = 0.5,
) -> VADResult:
    """
    Full VAD analysis pipeline for a video file.

    1. Extract audio from video
    2. Run Silero VAD to get speech segments
    3. Convert to per-frame bool array

    Returns VADResult with speech_frames bool array.
    """
    video_path = Path(video_path)
    info = get_video_info(video_path)
    fps = info["fps"]
    total_frames = info["total_frames"]

    # Extract audio to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        audio_path = extract_audio(video_path, tmp.name, sr=16000)
        samples = read_wav_samples(audio_path)

    # Run VAD
    segments = detect_speech_silero(samples, sample_rate=16000, threshold=threshold)

    # Convert to per-frame bool array
    speech_frames = speech_segments_to_frame_array(segments, fps, total_frames)

    return VADResult(
        speech_frames=speech_frames,
        fps=fps,
        total_frames=total_frames,
        speech_segments=segments,
    )
