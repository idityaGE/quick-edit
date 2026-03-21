"""
Edit Decision List types and utilities.

The EDL is the intermediate format between analysis and rendering.
It can be inspected, modified, and serialized before committing to a render.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CutReason(Enum):
    """Why a segment was removed."""

    SILENCE = "silence"  # No speech or audio
    FILLER_WORD = "filler_word"  # um, uh, like, basically, etc.
    FALSE_START = "false_start"  # Speaker restarts mid-sentence
    REPETITION = "repetition"  # Same concept explained twice
    TANGENT = "tangent"  # Off-topic digression
    DEAD_AIR = "dead_air"  # Long pause with no visual activity
    CUSTOM = "custom"  # User-defined via LLM prompt


@dataclass
class EditDecision:
    """A single edit decision from the LLM analysis."""

    start: float  # start time in source (seconds)
    end: float  # end time in source (seconds)
    action: str  # "remove" or "keep"
    reason: CutReason
    confidence: float = 1.0  # 0.0 - 1.0
    transcript: str = ""  # the text in this segment
    note: str = ""  # explanation from the LLM


def filter_by_confidence(
    decisions: list[EditDecision],
    min_confidence: float = 0.7,
) -> list[EditDecision]:
    """Only apply edit decisions above a confidence threshold."""
    return [d for d in decisions if d.confidence >= min_confidence]


def decisions_to_frame_mask(
    decisions: list[EditDecision],
    fps: float,
    total_frames: int,
) -> dict[str, object]:
    """
    Convert LLM edit decisions into modifications to the frame bool array.

    Returns a dict with:
        - remove_ranges: list of (start_frame, end_frame) to set False
        - keep_ranges: list of (start_frame, end_frame) to force True
    """
    remove_ranges = []
    keep_ranges = []

    for d in decisions:
        start_frame = int(d.start * fps)
        end_frame = min(int(d.end * fps), total_frames)

        if d.action == "remove":
            remove_ranges.append((start_frame, end_frame))
        elif d.action == "keep":
            keep_ranges.append((start_frame, end_frame))

    return {
        "remove_ranges": remove_ranges,
        "keep_ranges": keep_ranges,
    }
