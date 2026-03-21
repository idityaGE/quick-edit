"""
Transcription using faster-whisper.

Produces word-level timestamps for subtitle generation and LLM analysis.
Uses Silero VAD preprocessing (built into faster-whisper) to skip silence
and speed up transcription.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Word:
    """A single transcribed word with timestamps."""

    text: str
    start: float  # seconds
    end: float  # seconds
    probability: float


@dataclass
class Segment:
    """A transcription segment (usually a sentence or phrase)."""

    text: str
    start: float  # seconds
    end: float  # seconds
    words: list[Word] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    """Full transcription of a video/audio file."""

    segments: list[Segment]
    words: list[Word]  # flat list of all words
    language: str
    language_probability: float
    duration: float  # audio duration in seconds
    text: str  # full transcript text

    def to_transcript_with_timestamps(self) -> list[dict]:
        """Export as list of dicts for LLM consumption."""
        return [
            {
                "word": w.text,
                "start": round(w.start, 3),
                "end": round(w.end, 3),
                "probability": round(w.probability, 3),
            }
            for w in self.words
        ]

    def get_text_in_range(self, start: float, end: float) -> str:
        """Get transcript text within a time range."""
        words_in_range = [
            w.text for w in self.words if w.start >= start and w.end <= end
        ]
        return " ".join(words_in_range)


def transcribe(
    video_path: str | Path,
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = None,
    vad_filter: bool = True,
    beam_size: int = 5,
) -> TranscriptionResult:
    """
    Transcribe a video file using faster-whisper.

    Args:
        video_path: Path to video or audio file.
        model_size: Whisper model size. Options:
            "tiny", "base", "small", "medium", "large-v3", "turbo"
            For CPU, "base" or "small" recommended.
        device: "cpu" or "cuda".
        compute_type: "int8" for CPU, "float16" for CUDA.
        language: Language code (e.g., "en"). None for auto-detect.
        vad_filter: Use Silero VAD to skip silence (recommended).
        beam_size: Beam search width.

    Returns:
        TranscriptionResult with word-level timestamps.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
    )

    segments_iter, info = model.transcribe(
        str(video_path),
        beam_size=beam_size,
        word_timestamps=True,
        vad_filter=vad_filter,
        vad_parameters=dict(
            min_silence_duration_ms=300,
            speech_pad_ms=200,
        ),
        language=language,
    )

    segments: list[Segment] = []
    all_words: list[Word] = []
    full_text_parts: list[str] = []

    for seg in segments_iter:
        words: list[Word] = []
        if seg.words:
            for w in seg.words:
                word = Word(
                    text=w.word.strip(),
                    start=w.start,
                    end=w.end,
                    probability=w.probability,
                )
                words.append(word)
                all_words.append(word)

        segment = Segment(
            text=seg.text.strip(),
            start=seg.start,
            end=seg.end,
            words=words,
        )
        segments.append(segment)
        full_text_parts.append(seg.text.strip())

    return TranscriptionResult(
        segments=segments,
        words=all_words,
        language=info.language,
        language_probability=info.language_probability,
        duration=info.duration,
        text=" ".join(full_text_parts),
    )


def words_to_frame_array(
    words: list[Word],
    fps: float,
    total_frames: int,
) -> np.ndarray:
    """
    Convert word timestamps to a per-frame bool array.

    frame[i] = True means a word is being spoken during that frame.
    This is an alternative to VAD -- based on actual transcription
    rather than audio energy.
    """
    frames = np.zeros(total_frames, dtype=bool)

    for word in words:
        start_frame = int(word.start * fps)
        end_frame = min(int(word.end * fps) + 1, total_frames)
        frames[start_frame:end_frame] = True

    return frames
