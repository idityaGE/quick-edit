"""
Timeline and Clip abstractions for the edit decision list.

Converts a per-frame bool array into a list of Clips (segments to keep),
which are then used by the render module to produce the final video.

Inspired by auto-editor's v3 timeline model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np


@dataclass
class Clip:
    """A segment of source video to include in the output."""

    source: str  # source file path
    src_start: float  # start time in source (seconds)
    src_end: float  # end time in source (seconds)
    dst_start: float  # position on output timeline (seconds)
    duration: float  # duration in output (seconds)
    speed: float = 1.0  # playback speed (1.0 = normal)

    @property
    def src_duration(self) -> float:
        return self.src_end - self.src_start


@dataclass
class CutSegment:
    """A segment that was removed from the source."""

    src_start: float  # start in source (seconds)
    src_end: float  # end in source (seconds)
    reason: str = ""  # why it was cut (silence, filler, tangent, etc.)


@dataclass
class Timeline:
    """
    Complete edit decision list.

    Contains clips to keep and segments that were cut, plus metadata.
    """

    source: str
    fps: float
    duration: float  # source duration
    width: int = 0
    height: int = 0

    clips: list[Clip] = field(default_factory=list)
    cuts: list[CutSegment] = field(default_factory=list)

    @property
    def output_duration(self) -> float:
        """Total duration of the output video."""
        if not self.clips:
            return 0.0
        last = self.clips[-1]
        return last.dst_start + last.duration

    @property
    def time_saved(self) -> float:
        """Seconds removed from the original."""
        return self.duration - self.output_duration

    @property
    def time_saved_pct(self) -> float:
        """Percentage of time removed."""
        if self.duration == 0:
            return 0.0
        return (self.time_saved / self.duration) * 100

    def summary(self) -> str:
        """Human-readable summary of the edit."""
        lines = [
            f"Source: {self.source}",
            f"Original duration: {_fmt_time(self.duration)}",
            f"Output duration:   {_fmt_time(self.output_duration)}",
            f"Time saved:        {_fmt_time(self.time_saved)} ({self.time_saved_pct:.1f}%)",
            f"Clips: {len(self.clips)}",
            f"Cuts:  {len(self.cuts)}",
        ]
        return "\n".join(lines)

    def to_json(self, path: str | Path | None = None) -> str:
        """Export as JSON."""
        data = {
            "version": 1,
            "source": self.source,
            "fps": self.fps,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "output_duration": self.output_duration,
            "clips": [asdict(c) for c in self.clips],
            "cuts": [asdict(c) for c in self.cuts],
        }
        json_str = json.dumps(data, indent=2)
        if path:
            Path(path).write_text(json_str)
        return json_str

    @classmethod
    def from_json(cls, path: str | Path) -> Timeline:
        """Load from JSON file."""
        data = json.loads(Path(path).read_text())
        tl = cls(
            source=data["source"],
            fps=data["fps"],
            duration=data["duration"],
            width=data.get("width", 0),
            height=data.get("height", 0),
        )
        tl.clips = [Clip(**c) for c in data["clips"]]
        tl.cuts = [CutSegment(**c) for c in data["cuts"]]
        return tl


def frames_to_timeline(
    keep_frames: np.ndarray,
    source: str,
    fps: float,
    duration: float,
    width: int = 0,
    height: int = 0,
) -> Timeline:
    """
    Convert a per-frame bool array into a Timeline with clips and cuts.

    True frames become Clips (kept), False frames become CutSegments (removed).

    Args:
        keep_frames: bool array, True = keep this frame.
        source: Source file path.
        fps: Video frame rate.
        duration: Source video duration in seconds.
        width: Video width.
        height: Video height.

    Returns:
        Timeline with clips and cuts populated.
    """
    tl = Timeline(
        source=source,
        fps=fps,
        duration=duration,
        width=width,
        height=height,
    )

    n = len(keep_frames)
    if n == 0:
        return tl

    # Find contiguous regions
    # Pad to detect edges at boundaries
    padded = np.concatenate([[False], keep_frames, [False]])

    # Keep regions (True runs)
    keep_starts = np.where(np.diff(padded.astype(int)) == 1)[0]
    keep_ends = np.where(np.diff(padded.astype(int)) == -1)[0]

    # Build clips
    dst_cursor = 0.0
    for start_frame, end_frame in zip(keep_starts, keep_ends):
        src_start = start_frame / fps
        src_end = min(end_frame / fps, duration)
        clip_duration = src_end - src_start

        if clip_duration <= 0:
            continue

        clip = Clip(
            source=source,
            src_start=src_start,
            src_end=src_end,
            dst_start=dst_cursor,
            duration=clip_duration,
        )
        tl.clips.append(clip)
        dst_cursor += clip_duration

    # Build cuts (inverse regions)
    cut_padded = np.concatenate([[False], ~keep_frames, [False]])
    cut_starts = np.where(np.diff(cut_padded.astype(int)) == 1)[0]
    cut_ends = np.where(np.diff(cut_padded.astype(int)) == -1)[0]

    for start_frame, end_frame in zip(cut_starts, cut_ends):
        src_start = start_frame / fps
        src_end = min(end_frame / fps, duration)

        if src_end - src_start <= 0:
            continue

        cut = CutSegment(
            src_start=src_start,
            src_end=src_end,
        )
        tl.cuts.append(cut)

    return tl


def merge_timelines(base: Timeline, llm_cuts: list[CutSegment]) -> Timeline:
    """
    Apply additional LLM-suggested cuts to an existing timeline.

    The LLM pass may identify filler words, tangents, etc. within
    segments that the audio/visual pass decided to keep. This function
    splits existing clips at those cut points.

    Args:
        base: Timeline from the initial audio/visual pass.
        llm_cuts: Additional cuts from LLM analysis (in source time).

    Returns:
        New Timeline with the additional cuts applied.
    """
    if not llm_cuts:
        return base

    # Sort LLM cuts by start time
    llm_cuts = sorted(llm_cuts, key=lambda c: c.src_start)

    new_clips: list[Clip] = []

    for clip in base.clips:
        # Collect all LLM cuts that overlap with this clip.
        # We scan from the beginning each time since a cut can span
        # multiple clips, and a per-clip scan is fast for typical counts.
        relevant_cuts = [
            cut
            for cut in llm_cuts
            if cut.src_end > clip.src_start and cut.src_start < clip.src_end
        ]

        if not relevant_cuts:
            new_clips.append(clip)
            continue

        # Split this clip around the LLM cuts
        cursor = clip.src_start
        for cut in relevant_cuts:
            # Clamp cut to clip boundaries
            cut_start = max(cut.src_start, clip.src_start)
            cut_end = min(cut.src_end, clip.src_end)

            # Keep the part before the cut
            if cut_start > cursor:
                new_clips.append(
                    Clip(
                        source=clip.source,
                        src_start=cursor,
                        src_end=cut_start,
                        dst_start=0,  # will be recalculated
                        duration=cut_start - cursor,
                        speed=clip.speed,
                    )
                )

            cursor = cut_end

        # Keep the part after the last cut
        if cursor < clip.src_end:
            new_clips.append(
                Clip(
                    source=clip.source,
                    src_start=cursor,
                    src_end=clip.src_end,
                    dst_start=0,  # will be recalculated
                    duration=clip.src_end - cursor,
                    speed=clip.speed,
                )
            )

    # Recalculate dst_start for all clips
    dst_cursor = 0.0
    for clip in new_clips:
        clip.dst_start = dst_cursor
        dst_cursor += clip.duration

    # Rebuild the cuts list
    all_cuts = list(base.cuts) + llm_cuts
    all_cuts.sort(key=lambda c: c.src_start)

    result = Timeline(
        source=base.source,
        fps=base.fps,
        duration=base.duration,
        width=base.width,
        height=base.height,
        clips=new_clips,
        cuts=all_cuts,
    )

    return result


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.s"""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:05.2f}"
