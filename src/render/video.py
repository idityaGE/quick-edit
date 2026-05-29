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
import subprocess
import tempfile
from pathlib import Path

from src.timeline.timeline import Timeline, Clip

logger = logging.getLogger(__name__)

# Threshold for switching render strategies
CLIP_THRESHOLD_FOR_SEGMENT_RENDER = 50


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
                        "segments" - render segments then concat

    Returns:
        Path to the output file.
    """
    output_path = Path(output_path)

    if not timeline.clips:
        raise ValueError("Timeline has no clips to render")

    if len(timeline.clips) == 1:
        # Single clip: simple trim
        return _render_single_clip(
            timeline.clips[0],
            output_path,
            subtitle_path,
            codec,
            crf,
            preset,
            audio_codec,
            audio_bitrate,
        )

    # Determine strategy
    if render_strategy == "auto":
        if len(timeline.clips) > CLIP_THRESHOLD_FOR_SEGMENT_RENDER:
            logger.info(
                f"Timeline has {len(timeline.clips)} clips (>{CLIP_THRESHOLD_FOR_SEGMENT_RENDER}), "
                f"using segment-then-concat strategy"
            )
            render_strategy = "segments"
        else:
            render_strategy = "filter_complex"

    if render_strategy == "segments":
        return render_segments_then_concat(
            timeline,
            output_path,
            subtitle_path,
            codec,
            crf,
            preset,
            audio_codec,
            audio_bitrate,
        )

    # Default: filter_complex
    return _render_concat(
        timeline,
        output_path,
        subtitle_path,
        codec,
        crf,
        preset,
        audio_codec,
        audio_bitrate,
    )


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
    """
    Alternative rendering strategy: extract each segment separately,
    then concat with the concat demuxer. Better for very long videos
    with many clips, as it avoids huge filter_complex strings.

    1. Extract each clip as a separate file (stream copy when possible)
    2. Write a concat list file
    3. Concat all segments
    4. Optionally burn in subtitles
    """
    output_path = Path(output_path)

    with tempfile.TemporaryDirectory(prefix="quickedit_") as tmpdir:
        tmpdir = Path(tmpdir)
        segment_paths = []

        # Step 1: Extract each clip
        for i, clip in enumerate(timeline.clips):
            seg_path = tmpdir / f"seg_{i:04d}.ts"
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(clip.src_start),
                "-to",
                str(clip.src_end),
                "-i",
                clip.source,
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
                # Use mpegts for seamless concatenation
                "-f",
                "mpegts",
                str(seg_path),
            ]
            _run_ffmpeg(cmd, quiet=True)
            segment_paths.append(seg_path)

            if (i + 1) % 10 == 0:
                logger.info(f"Extracted segment {i + 1}/{len(timeline.clips)}")

        # Step 2: Concat using concat protocol
        concat_input = "|".join(str(p) for p in segment_paths)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            f"concat:{concat_input}",
            "-c",
            "copy",
        ]

        # Step 3: Add subtitles if needed (requires re-encoding video)
        if subtitle_path:
            sub_path = _escape_subtitle_path(str(subtitle_path))
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                f"concat:{concat_input}",
                "-vf",
                f"subtitles='{sub_path}'",
                "-c:v",
                codec,
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-c:a",
                "copy",
            ]

        cmd.extend(
            [
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        _run_ffmpeg(cmd)

    return output_path


FFMPEG_TIMEOUT_SECONDS = 3600  # 1 hour max for long renders


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
    """Run an FFmpeg command and handle errors."""
    if not quiet:
        logger.info(f"Running: {' '.join(cmd[:6])}...")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )

    if result.returncode != 0:
        logger.error(f"FFmpeg failed:\n{result.stderr[-1000:]}")
        raise RuntimeError(
            f"FFmpeg failed (exit {result.returncode}): {result.stderr[-500:]}"
        )

    return result
