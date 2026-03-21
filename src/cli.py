"""
CLI entry point for QuickEdit.

Usage:
    quickedit input.mp4
    quickedit input.mp4 -o output.mp4
    quickedit input.mp4 --prompt "Remove all filler words, keep code explanations"
    quickedit input.mp4 --no-llm --subtitle-style simple
    quickedit input.mp4 --model small --preset fast
"""

from __future__ import annotations

import logging
import sys

import click

from src.pipeline import PipelineConfig, run_pipeline


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    "output_path",
    default="",
    help="Output file path. Default: input_edited.mp4",
)
# Analysis options
@click.option(
    "--whisper-model",
    default="base",
    help="Whisper model size: tiny, base, small, medium, large-v3",
)
@click.option("--device", default="cpu", help="Device for whisper: cpu or cuda")
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
    "--llm-model", default="claude-sonnet-4-20250514", help="Claude model to use"
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
# Subtitle options
@click.option(
    "--subtitle-style",
    type=click.Choice(["fancy", "simple", "none"]),
    default="fancy",
    help="Subtitle style: fancy (word highlight), simple (SRT), none",
)
@click.option("--subtitle-font", default="Arial", help="Subtitle font name")
@click.option("--subtitle-size", default=20, type=int, help="Subtitle font size")
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
    language: str | None,
    vad_threshold: float,
    motion_threshold: float,
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
    subtitle_style: str,
    subtitle_font: str,
    subtitle_size: int,
    codec: str,
    crf: int,
    preset: str,
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

    # Build config
    config = PipelineConfig(
        input_path=input_path,
        output_path=output_path,
        whisper_model=whisper_model,
        whisper_device=device,
        whisper_compute_type="float16" if device == "cuda" else "int8",
        whisper_language=language,
        vad_threshold=vad_threshold,
        motion_threshold=motion_threshold,
        combine_expr=combine_expr,
        start_margin=margin,
        end_margin=margin,
        minclip=minclip,
        mincut=mincut,
        use_llm=not no_llm,
        llm_model=llm_model,
        custom_prompt=custom_prompt,
        llm_confidence_threshold=confidence,
        subtitle_style=subtitle_style,
        subtitle_font=subtitle_font,
        subtitle_size=subtitle_size,
        video_codec=codec,
        crf=crf,
        preset=preset,
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
