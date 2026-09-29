"""
Video rendering using FFmpeg.

Takes a Timeline (list of clips) and produces the final video by:
1. Extracting each clip segment from the source
2. Concatenating them into a single output
3. Optionally burning in subtitles

Uses FFmpeg's concat demuxer for efficient joining without re-encoding
when possible, or filter_complex concat for cases requiring re-encoding.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from quickedit.timeline.timeline import Clip, Timeline

logger = logging.getLogger(__name__)

# Threshold for switching render strategies
CLIP_THRESHOLD_FOR_SEGMENT_RENDER = 50
RENDER_STRATEGIES = frozenset({"auto", "filter_complex", "segments"})
FFMPEG_TIMEOUT_SECONDS = 3600
DIAGNOSTIC_LIMIT = 2000


def render_video(
    timeline: Timeline,
    output_path: str | Path,
    subtitle_path: str | Path | None = None,
    codec: str = "libx264",
    crf: int = 18,
    preset: str = "medium",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    render_strategy: str = "auto",
) -> Path:
    """
    Render a Timeline to a video file using FFmpeg.

    Args:
        timeline: Timeline with clips to render.
        output_path: Output video file path.
        subtitle_path: Optional ASS/SRT subtitle file to burn in.
        codec: Video codec (default h264).
        crf: Constant rate factor (quality, lower = better, 18 = visually lossless).
        preset: Encoding speed preset.
        audio_codec: Audio codec.
        audio_bitrate: Audio bitrate.
        render_strategy: "auto" (default) - picks best strategy based on clip count
                        "filter_complex" - single ffmpeg with filter_complex
                        "segments" - concat demuxer optimized for many clips

    Returns:
        Path to the output file.
    """
    output_path = Path(output_path)
    if render_strategy not in RENDER_STRATEGIES:
        choices = ", ".join(sorted(RENDER_STRATEGIES))
        raise ValueError(
            f"Unknown render strategy {render_strategy!r}; expected one of: {choices}"
        )

    if not output_path.parent.exists():
        raise ValueError(f"Output directory does not exist: {output_path.parent}")

    if not timeline.clips:
        raise ValueError("Timeline has no clips to render")

    temporary_output = output_path.with_name(
        f".{output_path.stem}.quickedit-{uuid.uuid4().hex}{output_path.suffix}"
    )

    try:
        if len(timeline.clips) == 1:
            _render_single_clip(
                timeline.clips[0],
                temporary_output,
                subtitle_path,
                codec,
                crf,
                preset,
                audio_codec,
                audio_bitrate,
            )
        else:
            # Determine strategy
            if render_strategy == "auto":
                render_strategy = (
                    "segments"
                    if len(timeline.clips) > CLIP_THRESHOLD_FOR_SEGMENT_RENDER
                    else "filter_complex"
                )

            if render_strategy == "segments":
                render_segments_then_concat(
                    timeline,
                    temporary_output,
                    subtitle_path,
                    codec,
                    crf,
                    preset,
                    audio_codec,
                    audio_bitrate,
                )
            else:
                _render_concat(
                    timeline,
                    temporary_output,
                    subtitle_path,
                    codec,
                    crf,
                    preset,
                    audio_codec,
                    audio_bitrate,
                )
        os.replace(temporary_output, output_path)
        return output_path
    except Exception:
        temporary_output.unlink(missing_ok=True)
        raise


def _render_single_clip(
    clip: Clip,
    output_path: Path,
    subtitle_path: str | Path | None,
    codec: str,
    crf: int,
    preset: str,
    audio_codec: str,
    audio_bitrate: str,
) -> Path:
    """Render a single clip (simple trim)."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(clip.src_start),
        "-to",
        str(clip.src_end),
        "-i",
        clip.source,
    ]

    vf_filters = []
    if subtitle_path:
        # Burn in subtitles
        sub_path = _escape_subtitle_path(str(subtitle_path))
        vf_filters.append(f"subtitles='{sub_path}'")

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    cmd.extend(
        [
            "-c:v",
            codec,
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-c:a",
            audio_codec,
            "-b:a",
            audio_bitrate,
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    _run_ffmpeg(cmd)
    return output_path


def _render_concat(
    timeline: Timeline,
    output_path: Path,
    subtitle_path: str | Path | None,
    codec: str,
    crf: int,
    preset: str,
    audio_codec: str,
    audio_bitrate: str,
) -> Path:
    """Render multiple clips using FFmpeg's filter_complex concat."""
    n = len(timeline.clips)
    source = timeline.source

    # Build the filter_complex string
    # First, create trim+setpts for each clip
    filter_parts = []
    for i, clip in enumerate(timeline.clips):
        # Video: trim and reset timestamps
        filter_parts.append(
            f"[0:v]trim=start={clip.src_start:.6f}:end={clip.src_end:.6f},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
        # Audio: trim and reset timestamps
        filter_parts.append(
            f"[0:a]atrim=start={clip.src_start:.6f}:end={clip.src_end:.6f},"
            f"asetpts=PTS-STARTPTS[a{i}]"
        )

    # Concat all clips — must interleave: [v0][a0][v1][a1]...
    interleaved = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{interleaved}concat=n={n}:v=1:a=1[outv][outa]")

    filter_complex = ";".join(filter_parts)

    # Build command
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        source,
        "-filter_complex",
        filter_complex,
    ]

    # Map outputs
    output_maps = ["[outv]", "[outa]"]

    # Add subtitle burn-in as a second pass if needed
    if subtitle_path:
        # We need to apply subtitles after concat
        # Modify the last filter to pipe through subtitles
        sub_path = _escape_subtitle_path(str(subtitle_path))
        # Replace [outv] with subtitle filter
        filter_complex = filter_complex.replace(
            f"concat=n={n}:v=1:a=1[outv][outa]",
            f"concat=n={n}:v=1:a=1[concatv][outa];"
            f"[concatv]subtitles='{sub_path}'[outv]",
        )
        cmd[cmd.index("-filter_complex") + 1] = filter_complex

    cmd.extend(
        [
            "-map",
            output_maps[0],
            "-map",
            output_maps[1],
            "-c:v",
            codec,
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-c:a",
            audio_codec,
            "-b:a",
            audio_bitrate,
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    _run_ffmpeg(cmd)
    return output_path


def render_segments_then_concat(
    timeline: Timeline,
    output_path: str | Path,
    subtitle_path: str | Path | None = None,
    codec: str = "libx264",
    crf: int = 18,
    preset: str = "medium",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
) -> Path:
    """Render many clips with the concat demuxer and one final encode.

    The demuxer references source ranges directly, avoiding codec-dependent
    MPEG-TS intermediates. Video (including optional subtitles) and audio are
    each encoded exactly once into the requested output container.
    """
    output_path = Path(output_path)

    with tempfile.TemporaryDirectory(prefix="quickedit_") as tmpdir:
        concat_path = Path(tmpdir) / "clips.ffconcat"
        concat_lines = ["ffconcat version 1.0"]
        for clip in timeline.clips:
            source = str(Path(clip.source).resolve())
            if "\n" in source or "\r" in source:
                raise ValueError(
                    "Source paths containing line breaks cannot be represented "
                    f"in an FFconcat file: {clip.source!r}"
                )
            source = source.replace("'", "'\\''")
            concat_lines.extend(
                [
                    f"file '{source}'",
                    f"inpoint {clip.src_start:.6f}",
                    f"outpoint {clip.src_end:.6f}",
                    f"duration {clip.src_duration:.6f}",
                ]
            )
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        video_filters = ["select=concatdec_select", "setpts=PTS-STARTPTS"]
        if subtitle_path:
            sub_path = _escape_subtitle_path(str(subtitle_path))
            video_filters.append(f"subtitles='{sub_path}'")

        cmd = [
            "ffmpeg",
            "-y",
            "-copyts",
            "-segment_time_metadata",
            "1",
            "-vsync",
            "0",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-vf",
            ",".join(video_filters),
            "-af",
            "aselect=concatdec_select,asetpts=PTS-STARTPTS",
            "-c:v",
            codec,
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-c:a",
            audio_codec,
            "-b:a",
            audio_bitrate,
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        _run_ffmpeg(cmd)

    return output_path


def _escape_subtitle_path(path: str) -> str:
    """Escape a file path for FFmpeg's subtitles filter.

    FFmpeg subtitles filter uses ':' as option separator, so colons in paths
    (e.g. Windows drive letters) must be escaped as '\\:'. Single quotes
    in paths are also escaped.
    """
    path = path.replace("\\", "/")
    path = path.replace(":", "\\:")
    path = path.replace("'", "'\\\\''")
    return path


def _run_ffmpeg(cmd: list[str], quiet: bool = False) -> subprocess.CompletedProcess:
    """Run an FFmpeg command with bounded execution and diagnostics."""
    if not quiet:
        logger.info(f"Running: {' '.join(cmd[:6])}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        detail = stderr.strip()[-DIAGNOSTIC_LIMIT:]
        message = f"FFmpeg timed out after {FFMPEG_TIMEOUT_SECONDS} seconds"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc

    if result.returncode != 0:
        stderr = result.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        detail = stderr.strip()[-DIAGNOSTIC_LIMIT:]
        logger.error(f"FFmpeg failed:\n{detail}")
        message = f"FFmpeg failed (exit {result.returncode})"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)

    return result
