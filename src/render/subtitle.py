"""
Subtitle generation with fancy word-by-word highlighting.

Generates ASS (Advanced SubStation Alpha) subtitles with:
- Word-by-word highlight effect (Instagram/TikTok style)
- Configurable colors, fonts, positioning
- Timing synced to word-level timestamps

Also supports simple SRT output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.analyze.transcribe import Word
from src.timeline.timeline import Timeline


@dataclass
class SubtitleStyle:
    """Configuration for subtitle appearance."""

    font_name: str = "Arial"
    font_size: int = 20
    primary_color: str = "&H00FFFFFF"  # white (ASS format: &HAABBGGRR)
    highlight_color: str = "&H0000FFFF"  # yellow highlight
    outline_color: str = "&H00000000"  # black outline
    back_color: str = "&H80000000"  # semi-transparent black background
    outline_width: int = 2
    shadow_depth: int = 1
    alignment: int = 2  # bottom center
    margin_v: int = 40  # vertical margin from bottom
    bold: bool = True
    max_words_per_line: int = 8  # wrap after N words


def generate_ass_subtitles(
    words: list[Word],
    timeline: Timeline,
    output_path: str | Path,
    style: SubtitleStyle | None = None,
) -> Path:
    """
    Generate ASS subtitles with word-by-word highlighting.

    The highlight effect works by showing each word group as a subtitle event,
    with the currently spoken word in a different color using ASS override tags.

    Words are grouped into lines of max_words_per_line, and each word within
    a group gets its own timing for the highlight effect.

    Args:
        words: Word-level timestamps from transcription.
        timeline: The edit timeline (used to remap source timestamps to output timestamps).
        output_path: Where to write the .ass file.
        style: Subtitle styling configuration.

    Returns:
        Path to the generated .ass file.
    """
    style = style or SubtitleStyle()
    output_path = Path(output_path)

    # Remap word timestamps from source time to output time
    remapped_words = _remap_words_to_output(words, timeline)

    if not remapped_words:
        # No words survived the edit; write empty subtitle file
        _write_ass_file(output_path, style, [])
        return output_path

    # Group words into lines
    groups = _group_words(remapped_words, style.max_words_per_line)

    # Generate ASS dialogue events with highlight
    events = []
    for group in groups:
        group_events = _create_highlight_events(group, style)
        events.extend(group_events)

    _write_ass_file(output_path, style, events)
    return output_path


def generate_srt_subtitles(
    words: list[Word],
    timeline: Timeline,
    output_path: str | Path,
    max_words_per_line: int = 10,
) -> Path:
    """
    Generate simple SRT subtitles.

    Args:
        words: Word-level timestamps.
        timeline: Edit timeline for timestamp remapping.
        output_path: Where to write the .srt file.
        max_words_per_line: Words per subtitle entry.

    Returns:
        Path to the generated .srt file.
    """
    output_path = Path(output_path)
    remapped_words = _remap_words_to_output(words, timeline)

    if not remapped_words:
        output_path.write_text("")
        return output_path

    groups = _group_words(remapped_words, max_words_per_line)

    lines = []
    for i, group in enumerate(groups, 1):
        start = _srt_timestamp(group[0].start)
        end = _srt_timestamp(group[-1].end)
        text = " ".join(w.text for w in group)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    output_path.write_text("\n".join(lines))
    return output_path


# --- Internal helpers ---


@dataclass
class _RemappedWord:
    """A word with timestamps adjusted for the output timeline."""

    text: str
    start: float  # output time
    end: float  # output time
    probability: float


def _remap_words_to_output(
    words: list[Word],
    timeline: Timeline,
) -> list[_RemappedWord]:
    """
    Remap word timestamps from source video time to output video time.

    Words that fall within cut segments are excluded.
    Words within kept clips have their timestamps adjusted based on
    the clip's position on the output timeline.
    """
    remapped = []

    for word in words:
        # Find which clip (if any) contains this word
        for clip in timeline.clips:
            if clip.src_start <= word.start and word.end <= clip.src_end:
                # Word is within this clip
                # Calculate offset within the clip
                offset = word.start - clip.src_start
                new_start = clip.dst_start + offset
                new_end = new_start + (word.end - word.start)

                remapped.append(
                    _RemappedWord(
                        text=word.text,
                        start=new_start,
                        end=new_end,
                        probability=word.probability,
                    )
                )
                break
        # If word doesn't fall in any clip, it was cut -- skip it

    return remapped


def _group_words(
    words: list[_RemappedWord],
    max_per_group: int,
    silence_gap: float = 0.7,
) -> list[list[_RemappedWord]]:
    """Group words into subtitle lines, respecting natural pauses."""
    if not words:
        return []

    groups = []
    current_group: list[_RemappedWord] = []

    for word in words:
        if current_group:
            # Check for a natural break (gap > silence_gap between words)
            gap = word.start - current_group[-1].end
            if gap > silence_gap or len(current_group) >= max_per_group:
                groups.append(current_group)
                current_group = []

        current_group.append(word)

    if current_group:
        groups.append(current_group)

    return groups


def _create_highlight_events(
    group: list[_RemappedWord],
    style: SubtitleStyle,
) -> list[str]:
    """
    Create ASS dialogue events with word-by-word highlighting.

    For each word in the group, generate a subtitle event that shows
    the entire group text but highlights the current word in a different color.
    """
    events = []

    for i, word in enumerate(group):
        # Build the line with the current word highlighted
        parts = []
        for j, w in enumerate(group):
            if j == i:
                # Highlighted word
                parts.append(
                    f"{{\\c{style.highlight_color}\\b1}}"
                    f"{w.text}"
                    f"{{\\c{style.primary_color}\\b0}}"
                )
            else:
                parts.append(w.text)

        text = " ".join(parts)

        # Timing: from this word's start to next word's start (or group end)
        start_time = word.start
        if i + 1 < len(group):
            end_time = group[i + 1].start
        else:
            end_time = word.end

        # Ensure minimum display time
        if end_time - start_time < 0.05:
            end_time = start_time + 0.05

        start_ts = _ass_timestamp(start_time)
        end_ts = _ass_timestamp(end_time)

        event = f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}"
        events.append(event)

    return events


def _write_ass_file(
    path: Path,
    style: SubtitleStyle,
    events: list[str],
) -> None:
    """Write a complete ASS subtitle file."""
    header = f"""[Script Info]
Title: QuickEdit Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{style.primary_color},{style.highlight_color},{style.outline_color},{style.back_color},{int(style.bold)},0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow_depth},{style.alignment},10,10,{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    content = header + "\n".join(events) + "\n"
    path.write_text(content)


def _ass_timestamp(seconds: float) -> str:
    """Convert seconds to ASS timestamp format: H:MM:SS.CC"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
