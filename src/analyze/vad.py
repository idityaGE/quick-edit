"""
Voice Activity Detection using Silero VAD.

Produces a bool array (one value per video frame) indicating whether
speech is present in each frame's time window.
"""

from __future__ import annotations

import subprocess
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")
    return output_path


def get_video_fps(video_path: str | Path) -> float:
    """Get the frame rate of a video file."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    rate_str = data["streams"][0]["r_frame_rate"]
    num, den = map(int, rate_str.split("/"))
    return num / den


def get_video_info(video_path: str | Path) -> dict:
    """Get video metadata: fps, duration, total_frames, width, height."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate,duration,nb_frames,width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    stream = data["streams"][0]

    rate_str = stream["r_frame_rate"]
    num, den = map(int, rate_str.split("/"))
    fps = num / den

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
    }


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
    Run Silero VAD on audio samples.

    Returns list of (start_sec, end_sec) speech segments.
    Uses ONNX runtime for CPU inference.
    """
    try:
        import torch

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        get_speech_timestamps = utils[0]

        audio_tensor = torch.from_numpy(audio_samples)
        speech_timestamps = get_speech_timestamps(
            audio_tensor,
            model,
            sampling_rate=sample_rate,
            threshold=threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
            window_size_samples=window_size_samples,
        )

        segments = []
        for ts in speech_timestamps:
            start_sec = ts["start"] / sample_rate
            end_sec = ts["end"] / sample_rate
            segments.append((start_sec, end_sec))

        return segments

    except ImportError:
        # Fallback: use faster-whisper's built-in VAD
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
