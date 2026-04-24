"""
CLI entry point for QuickEdit.

Usage:
    quickedit input.mp4
    quickedit input.mp4 -o output.mp4
    quickedit input.mp4 --prompt "Remove all filler words, keep code explanations"
    quickedit input.mp4 --no-llm --subtitle-style simple
    quickedit input.mp4 --model small --preset fast
    quickedit input.mp4 --config my_settings.json

Environment variables:
    All flags are available as QUICKEDIT_<FLAG_NAME> env vars.
    Example: QUICKEDIT_VAD_THRESHOLD=0.3 QUICKEDIT_WHISPER_MODEL=small quickedit input.mp4

Config file (JSON):
    Keys match CLI flag names with underscores instead of hyphens.
    Example: {"vad_threshold": 0.3, "whisper_model": "small", "codec": "libx265"}
    Priority: CLI flags > env vars > config file > built-in defaults.
"""

from __future__ import annotations

import json
import logging
import sys

import click

from src.pipeline import PipelineConfig, run_pipeline


def _load_config_callback(ctx: click.Context, param: click.Parameter, value: str | None) -> str | None:
    """Eager callback: load JSON config file into Click's default_map before other options resolve."""
    if not value or ctx.resilient_parsing:
        return value
    try:
        with open(value) as f:
            data = json.load(f)
        ctx.default_map = ctx.default_map or {}
        ctx.default_map.update(data)
    except (OSError, json.JSONDecodeError) as e:
        raise click.BadParameter(f"Cannot load config file: {e}", param=param)
    return value


@click.command(context_settings={"auto_envvar_prefix": "QUICKEDIT"})
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    "output_path",
    default="",
    help="Output file path. Default: input_edited.mp4",
)
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    is_eager=True,
    expose_value=False,
    callback=_load_config_callback,
    help="JSON config file. Keys match CLI flag names (use underscores). "
         "Priority: flags > env vars > file > defaults.",
)
# Analysis options
@click.option(
    "--whisper-model",
    default="base",
    help="Whisper model size: tiny, base, small, medium, large-v3",
)
@click.option("--device", default="cpu", help="Device for whisper: cpu or cuda")
@click.option(
    "--whisper-compute-type",
    default=None,
    type=click.Choice(["int8", "float16", "float32", "int8_float16"]),
    help="Whisper compute type. Default: int8 (cpu) or float16 (cuda).",
)
@click.option(
    "--language",
    default=None,
    help="Language code (e.g., 'en'). Auto-detect if not set.",
)
@click.option(
    "--vad-threshold",
    default=0.5,
    type=float,
    help="VAD sensitivity (0.0-1.0, lower = more sensitive)",
)
@click.option(
    "--motion-threshold",
    default=0.02,
    type=float,
    help="Motion detection threshold (0.0-1.0)",
)
@click.option(
    "--motion-pixel-threshold",
    default=10,
    type=int,
    help="Pixel change magnitude (0-255) to count as motion. Default: 10.",
)
@click.option(
    "--motion-frame-skip",
    default=1,
    type=int,
    help="Analyze every Nth frame for motion. 1=all, 2=every other. Default: 1.",
)
# Edit options
@click.option(
    "--combine",
    "combine_expr",
    default="or:speech,motion",
    help="How to combine detectors. E.g., 'or:speech,motion' or 'and:speech,motion'",
)
@click.option(
    "--margin", default=0.2, type=float, help="Margin around keep regions (seconds)"
)
@click.option(
    "--minclip", default=0.1, type=float, help="Minimum keep segment duration (seconds)"
)
@click.option(
    "--mincut", default=0.2, type=float, help="Minimum cut gap duration (seconds)"
)
# LLM options
@click.option("--no-llm", is_flag=True, help="Disable LLM semantic analysis")
@click.option(
    "--llm-model",
    default="claude-sonnet-4-20250514",
    help="LLM model to use. Supports: claude-* (Anthropic), gemini-* (Google)",
)
@click.option(
    "--prompt",
    "custom_prompt",
    default=None,
    help="Custom editing instructions for the LLM",
)
@click.option(
    "--prompt-template",
    type=click.Choice(["dsa", "tutorial", "lecture"]),
    default=None,
    help="Use a built-in prompt template: dsa, tutorial, lecture",
)
@click.option(
    "--prompt-file",
    default=None,
    type=click.Path(exists=True),
    help="Read custom prompt from a file",
)
@click.option(
    "--confidence",
    default=0.7,
    type=float,
    help="Min confidence for LLM cuts (0.0-1.0)",
)
@click.option(
    "--silent-segment-min-duration",
    default=0.5,
    type=float,
    help="Min silence duration (seconds) for LLM classification. Default: 0.5.",
)
# Subtitle options
@click.option(
    "--subtitle-style",
    type=click.Choice(["fancy", "simple", "none"]),
    default="fancy",
    help="Subtitle style: fancy (word highlight), simple (SRT), none",
)
@click.option("--subtitle-font", default="Arial", help="Subtitle font name")
@click.option("--subtitle-size", default=20, type=int, help="Subtitle font size")
@click.option(
    "--subtitle-silence-gap",
    default=0.7,
    type=float,
    help="Silence gap (seconds) that starts a new subtitle group. Default: 0.7.",
)
# Render options
@click.option("--codec", default="libx264", help="Video codec")
@click.option(
    "--crf",
    default=18,
    type=int,
    help="Quality (0-51, lower=better, 18=visually lossless)",
)
@click.option(
    "--preset",
    default="medium",
    type=click.Choice(
        [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]
    ),
    help="Encoding speed preset",
)
@click.option("--audio-codec", default="aac", help="Audio codec. Default: aac.")
@click.option(
    "--audio-bitrate",
    default="192k",
    help="Audio bitrate. Default: 192k.",
)
# Misc
@click.option("--no-cache", is_flag=True, help="Disable caching of analysis results")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Analyze and build timeline but skip rendering. Shows what would be cut.",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def main(
    input_path: str,
    output_path: str,
    whisper_model: str,
    device: str,
    whisper_compute_type: str | None,
    language: str | None,
    vad_threshold: float,
    motion_threshold: float,
    motion_pixel_threshold: int,
    motion_frame_skip: int,
    combine_expr: str,
    margin: float,
    minclip: float,
    mincut: float,
    no_llm: bool,
    llm_model: str,
    custom_prompt: str | None,
    prompt_template: str | None,
    prompt_file: str | None,
    confidence: float,
    silent_segment_min_duration: float,
    subtitle_style: str,
    subtitle_font: str,
    subtitle_size: int,
    subtitle_silence_gap: float,
    codec: str,
    crf: int,
    preset: str,
    audio_codec: str,
    audio_bitrate: str,
    no_cache: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """
    QuickEdit: AI-powered video editor.

    Automatically trims silence, filler words, false starts, and tangents
    from recorded videos. Adds word-level subtitles.

    INPUT_PATH is the video file to process.
    """
    # Setup logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve prompt: explicit > file > template > default
    if prompt_file and not custom_prompt:
        with open(prompt_file) as f:
            custom_prompt = f.read().strip()
    if prompt_template and not custom_prompt:
        from src.edit.llm import PROMPT_TEMPLATES

        custom_prompt = PROMPT_TEMPLATES[prompt_template]

    # Resolve whisper compute type: explicit > auto-detect from device
    resolved_compute_type = whisper_compute_type or (
        "float16" if device == "cuda" else "int8"
    )

    # Build config
    config = PipelineConfig(
        input_path=input_path,
        output_path=output_path,
        whisper_model=whisper_model,
        whisper_device=device,
        whisper_compute_type=resolved_compute_type,
        whisper_language=language,
        vad_threshold=vad_threshold,
        motion_threshold=motion_threshold,
        motion_pixel_threshold=motion_pixel_threshold,
        motion_frame_skip=motion_frame_skip,
        combine_expr=combine_expr,
        start_margin=margin,
        end_margin=margin,
        minclip=minclip,
        mincut=mincut,
        use_llm=not no_llm,
        llm_model=llm_model,
        custom_prompt=custom_prompt,
        llm_confidence_threshold=confidence,
        silent_segment_min_duration=silent_segment_min_duration,
        subtitle_style=subtitle_style,
        subtitle_font=subtitle_font,
        subtitle_size=subtitle_size,
        subtitle_silence_gap=subtitle_silence_gap,
        video_codec=codec,
        crf=crf,
        preset=preset,
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        use_cache=not no_cache,
        dry_run=dry_run,
        verbose=verbose,
    )

    # Run
    click.echo("QuickEdit - AI Video Editor")
    click.echo("=" * 40)

    try:
        result = run_pipeline(config)
        click.echo("\n" + "=" * 40)
        click.echo(result.summary())
        click.echo(f"\nOutput: {result.output_path}")
    except KeyboardInterrupt:
        click.echo("\nCancelled.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Pipeline failed: {e}", exc_info=verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
