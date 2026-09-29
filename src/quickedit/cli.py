"""
CLI entry point for QuickEdit.

Usage:
    quickedit input.mp4
    quickedit input.mp4 -o output.mp4
    quickedit input.mp4 --no-llm --subtitle-style simple
    quickedit input.mp4 --llm --prompt "Remove filler words, keep explanations"
    quickedit input.mp4 --whisper-model small --preset fast
    quickedit input.mp4 --config my_settings.json

Batch processing:
    quickedit video1.mp4 video2.mp4 video3.mp4
    quickedit *.mp4 -o output_dir/

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
import os
from pathlib import Path

import click
import numpy as np

from quickedit import __version__
from quickedit.analyze.combine import DetectionArrays, evaluate_expression
from quickedit.cache import cache
from quickedit.edit.llm import LLMProvider, _detect_provider
from quickedit.pipeline import PipelineConfig, run_pipeline
from quickedit.progress import ProgressReporter


def _load_config_callback(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Eager callback: load JSON config file into Click's default_map."""
    if not value or ctx.resilient_parsing:
        return value
    try:
        with open(value) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise click.BadParameter(f"Cannot load config file: {e}", param=param)

    if not isinstance(data, dict):
        raise click.BadParameter("Config file must contain a JSON object", param=param)

    option_names = {
        option.name
        for option in ctx.command.params
        if isinstance(option, click.Option)
        and option.expose_value
        and option.name is not None
    }
    unknown = sorted(set(data) - option_names)
    if unknown:
        keys = ", ".join(unknown)
        raise click.BadParameter(
            f"Unknown config key(s): {keys}. "
            "Keys must match CLI option parameter names (use underscores).",
            param=param,
        )

    ctx.default_map = ctx.default_map or {}
    ctx.default_map.update(data)
    return value


def _validate_combine_expression(expression: str) -> None:
    """Validate a combine expression using the analysis evaluator."""
    if ":" in expression:
        operation, operand_text = expression.split(":", 1)
        operands = operand_text.split(",")
        normalized_operation = operation.strip().lower()
        if normalized_operation in {"or", "and", "xor"} and len(operands) < 2:
            raise ValueError(f"'{normalized_operation}' takes at least two operands")

    probe = np.zeros(1, dtype=bool)
    detections = DetectionArrays(
        arrays={"speech": probe, "motion": probe, "words": probe},
        fps=1.0,
        total_frames=1,
    )
    try:
        evaluate_expression(expression, detections)
    except (KeyError, TypeError, ValueError) as error:
        message = f"Invalid combine expression {expression!r}: {error}"
        raise ValueError(message) from error


def _output_artifacts(
    output_path: str, *, dry_run: bool, subtitle_style: str
) -> list[Path]:
    """Return every artifact this invocation may generate."""
    output = Path(output_path)
    artifacts = [output.with_suffix(".timeline.json")]
    if not dry_run:
        artifacts.insert(0, output)
    if subtitle_style != "none":
        artifacts.append(
            output.with_suffix(".ass" if subtitle_style == "fancy" else ".srt")
        )
    return artifacts


def _validate_config(
    config: PipelineConfig, *, require_output_directory: bool = True
) -> None:
    """Validate configuration values and raise ValueError on invalid input."""
    errors: list[str] = []

    # Range validations
    if not 0.0 <= config.vad_threshold <= 1.0:
        errors.append(f"vad_threshold must be 0.0-1.0, got {config.vad_threshold}")
    if not 0.0 <= config.motion_threshold <= 1.0:
        errors.append(
            f"motion_threshold must be 0.0-1.0, got {config.motion_threshold}"
        )
    if not 0 <= config.motion_pixel_threshold <= 255:
        errors.append(
            f"motion_pixel_threshold must be 0-255, got {config.motion_pixel_threshold}"
        )
    if config.motion_frame_skip < 1:
        errors.append(f"motion_frame_skip must be >= 1, got {config.motion_frame_skip}")
    if config.motion_backend not in {"opencv", "opencv-parallel", "ffmpeg"}:
        errors.append(
            "motion_backend must be one of: opencv, opencv-parallel, ffmpeg; "
            f"got {config.motion_backend}"
        )
    if config.motion_workers < 1:
        errors.append(f"motion_workers must be >= 1, got {config.motion_workers}")
    if config.start_margin < 0:
        errors.append(f"margin must be >= 0, got {config.start_margin}")
    if config.minclip < 0:
        errors.append(f"minclip must be >= 0, got {config.minclip}")
    if config.mincut < 0:
        errors.append(f"mincut must be >= 0, got {config.mincut}")
    if not 0.0 <= config.llm_confidence_threshold <= 1.0:
        errors.append(
            f"confidence must be 0.0-1.0, got {config.llm_confidence_threshold}"
        )
    if config.silent_segment_min_duration < 0:
        errors.append(
            f"silent_segment_min_duration must be >= 0, got {config.silent_segment_min_duration}"
        )
    if not 0.0 <= config.silent_segment_active_frame_ratio_threshold <= 1.0:
        errors.append(
            "silent_segment_active_frame_ratio must be 0.0-1.0, got "
            f"{config.silent_segment_active_frame_ratio_threshold}"
        )
    if config.subtitle_size < 1:
        errors.append(f"subtitle_size must be >= 1, got {config.subtitle_size}")
    if config.subtitle_silence_gap < 0:
        errors.append(
            f"subtitle_silence_gap must be >= 0, got {config.subtitle_silence_gap}"
        )
    if not 0 <= config.crf <= 51:
        errors.append(f"crf must be 0-51, got {config.crf}")

    # Output path validation
    input_path = Path(config.input_path).resolve()
    output_path = Path(config.output_path).resolve() if config.output_path else None
    if not input_path.is_file():
        errors.append(f"Input path must be a file: {input_path}")
    if output_path and input_path == output_path:
        errors.append("Output path cannot be the same as input path")
    if require_output_directory and output_path and not output_path.parent.is_dir():
        errors.append(f"Output directory does not exist: {output_path.parent}")

    if config.use_llm:
        provider = _detect_provider(config.llm_model)
        api_key_name = (
            "GOOGLE_API_KEY or GEMINI_API_KEY"
            if provider == LLMProvider.GEMINI
            else "ANTHROPIC_API_KEY"
        )
        has_key = (
            bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
            if provider == LLMProvider.GEMINI
            else bool(os.environ.get("ANTHROPIC_API_KEY"))
        )
        if not has_key:
            errors.append(
                f"LLM editing requires {api_key_name}. Disable it with --no-llm "
                "or configure the provider before continuing."
            )

    if errors:
        raise ValueError("Configuration errors:\n  " + "\n  ".join(errors))


@click.version_option(version=__version__, prog_name="quickedit")
@click.command(context_settings={"auto_envvar_prefix": "QUICKEDIT"})
@click.argument(
    "input_paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option(
    "-o",
    "--output",
    "output_path",
    default="",
    help="Output path. For single file: output file path. "
    "For batch: output directory. Default: input_edited.ext",
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
@click.option(
    "--motion-backend",
    default="ffmpeg",
    type=click.Choice(["opencv", "opencv-parallel", "ffmpeg"]),
    help="Motion backend: ffmpeg, opencv, or opencv-parallel. Default: ffmpeg.",
)
@click.option(
    "--motion-workers",
    default=4,
    type=int,
    help="Worker count for --motion-backend opencv-parallel. Default: 4.",
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
@click.option(
    "--llm/--no-llm",
    "use_llm",
    default=False,
    help="Enable optional semantic LLM analysis (sends transcript data to its provider).",
)
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
@click.option(
    "--silent-segment-active-frame-ratio",
    default=0.5,
    type=float,
    help="Min active-frame ratio for silent-segment visual activity (0.0-1.0).",
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
    "--clear-cache",
    is_flag=True,
    help="Clear cached analysis for each input before processing it.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Allow replacing existing generated artifacts.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Analyze and build timeline but skip rendering. Shows what would be cut.",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def main(
    input_paths: tuple[str, ...],
    output_path: str,
    whisper_model: str,
    device: str,
    whisper_compute_type: str | None,
    language: str | None,
    vad_threshold: float,
    motion_threshold: float,
    motion_pixel_threshold: int,
    motion_frame_skip: int,
    motion_backend: str,
    motion_workers: int,
    combine_expr: str,
    margin: float,
    minclip: float,
    mincut: float,
    use_llm: bool,
    llm_model: str,
    custom_prompt: str | None,
    prompt_template: str | None,
    prompt_file: str | None,
    confidence: float,
    silent_segment_min_duration: float,
    silent_segment_active_frame_ratio: float,
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
    clear_cache: bool,
    overwrite: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """
    QuickEdit: AI-powered video editor.

    Automatically trims silence, filler words, false starts, and tangents
    from recorded videos. Adds word-level subtitles.

    INPUT_PATHS is one or more video files to process.
    Supports batch processing: quickedit video1.mp4 video2.mp4 video3.mp4
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
        from quickedit.edit.llm import PROMPT_TEMPLATES

        custom_prompt = PROMPT_TEMPLATES[prompt_template]

    # Resolve whisper compute type: explicit > auto-detect from device
    resolved_compute_type = whisper_compute_type or (
        "float16" if device == "cuda" else "int8"
    )

    batch_mode = len(input_paths) > 1
    output_dir = Path(output_path) if batch_mode and output_path else None

    try:
        _validate_combine_expression(combine_expr)
    except ValueError as error:
        raise click.UsageError(str(error)) from error

    if output_dir is not None and output_dir.exists() and not output_dir.is_dir():
        raise click.UsageError(f"Batch output path is not a directory: {output_dir}")

    destinations: list[tuple[str, str]] = []
    for input_path in input_paths:
        input_file = Path(input_path)
        if output_dir is not None:
            file_output = str(
                output_dir / input_file.with_stem(input_file.stem + "_edited").name
            )
        elif not batch_mode and output_path:
            file_output = output_path
        else:
            file_output = str(input_file.with_stem(input_file.stem + "_edited"))
        destinations.append((input_path, file_output))

    outputs_by_path: dict[Path, list[str]] = {}
    for input_path, file_output in destinations:
        for artifact in _output_artifacts(
            file_output,
            dry_run=False,
            subtitle_style=subtitle_style,
        ):
            normalized_output = artifact.resolve()
            outputs_by_path.setdefault(normalized_output, []).append(input_path)
    duplicate_outputs = {
        path: inputs for path, inputs in outputs_by_path.items() if len(inputs) > 1
    }
    if duplicate_outputs:
        details = "; ".join(
            f"{path} ({', '.join(inputs)})"
            for path, inputs in duplicate_outputs.items()
        )
        raise click.UsageError(
            f"Multiple inputs resolve to the same output destination: {details}"
        )

    resolved_inputs = {
        Path(input_path).resolve(): input_path for input_path in input_paths
    }
    input_overlaps: dict[Path, list[str]] = {}
    for input_path, file_output in destinations:
        for artifact in _output_artifacts(
            file_output,
            dry_run=dry_run,
            subtitle_style=subtitle_style,
        ):
            resolved_artifact = artifact.resolve()
            if resolved_artifact in resolved_inputs:
                input_overlaps.setdefault(resolved_artifact, []).append(input_path)
    if input_overlaps:
        details = "; ".join(
            f"{path} (generated by {', '.join(generators)})"
            for path, generators in input_overlaps.items()
        )
        raise click.UsageError(
            "Generated artifacts overlap batch input files: "
            f"{details}. Choose a different output directory."
        )

    existing_artifacts: list[Path] = []
    if not overwrite:
        for _, file_output in destinations:
            existing_artifacts.extend(
                artifact
                for artifact in _output_artifacts(
                    file_output,
                    dry_run=dry_run,
                    subtitle_style=subtitle_style,
                )
                if artifact.exists()
            )
    if existing_artifacts:
        paths = "\n  ".join(str(path) for path in existing_artifacts)
        raise click.UsageError(
            f"Generated artifact(s) already exist:\n  {paths}\n"
            "Use --overwrite to replace them."
        )

    configs: list[PipelineConfig] = []
    output_directory_will_be_created = (
        output_dir is not None and not output_dir.exists()
    )
    for input_path, file_output in destinations:
        config = PipelineConfig(
            input_path=input_path,
            output_path=file_output,
            whisper_model=whisper_model,
            whisper_device=device,
            whisper_compute_type=resolved_compute_type,
            whisper_language=language,
            vad_threshold=vad_threshold,
            motion_threshold=motion_threshold,
            motion_pixel_threshold=motion_pixel_threshold,
            motion_frame_skip=motion_frame_skip,
            motion_backend=motion_backend,
            motion_workers=motion_workers,
            combine_expr=combine_expr,
            start_margin=margin,
            end_margin=margin,
            minclip=minclip,
            mincut=mincut,
            use_llm=use_llm,
            llm_model=llm_model,
            custom_prompt=custom_prompt,
            llm_confidence_threshold=confidence,
            silent_segment_min_duration=silent_segment_min_duration,
            silent_segment_active_frame_ratio_threshold=(
                silent_segment_active_frame_ratio
            ),
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
        try:
            _validate_config(
                config,
                require_output_directory=not output_directory_will_be_created,
            )
        except ValueError as error:
            click.echo(f"Error: {error}", err=True)
            raise click.exceptions.Exit(1) from error
        configs.append(config)

    if output_directory_will_be_created:
        assert output_dir is not None
        try:
            output_dir.mkdir(parents=True)
        except OSError as error:
            raise click.UsageError(
                f"Cannot create batch output directory {output_dir}: {error}"
            ) from error

    click.echo("QuickEdit - AI Video Editor")
    click.echo("=" * 40)
    if batch_mode:
        click.echo(f"Batch processing {len(input_paths)} files\n")

    all_results = []
    failed: list[tuple[str, str]] = []

    for file_idx, config in enumerate(configs, 1):
        input_path = config.input_path
        if batch_mode:
            click.echo(f"\n{'─' * 40}")
            click.echo(f"[{file_idx}/{len(input_paths)}] {Path(input_path).name}")
            click.echo(f"{'─' * 40}")

        reporter = ProgressReporter()
        config.progress_callback = reporter.callback

        try:
            if clear_cache:
                removed = cache.clear_cache(input_path)
                click.echo(f"Cleared {removed} cached item(s).")
            with reporter:
                result = run_pipeline(config)
            click.echo("\n" + "=" * 40)
            click.echo(result.summary())
            if dry_run:
                click.echo("\nDry run complete; no video was rendered.")
                click.echo(
                    f"Timeline: {Path(result.output_path).with_suffix('.timeline.json')}"
                )
                if subtitle_style != "none" and getattr(result, "transcript", None):
                    subtitle_suffix = ".ass" if subtitle_style == "fancy" else ".srt"
                    click.echo(
                        f"Subtitles: "
                        f"{Path(result.output_path).with_suffix(subtitle_suffix)}"
                    )
            else:
                click.echo(f"\nOutput: {result.output_path}")
            all_results.append(result)
        except KeyboardInterrupt:
            click.echo("\nCancelled.")
            raise click.exceptions.Exit(1)
        except Exception as error:
            logging.error(f"Pipeline failed: {error}", exc_info=verbose)
            if batch_mode:
                failed.append((input_path, str(error)))
                click.echo(f"\nFailed: {error}", err=True)
                continue
            raise click.exceptions.Exit(1) from error

    if batch_mode:
        click.echo(f"\n{'═' * 40}")
        click.echo("Batch Summary")
        click.echo(f"{'═' * 40}")
        click.echo(f"  Processed: {len(all_results)}/{len(input_paths)}")
        if failed:
            click.echo(f"  Failed:    {len(failed)}")
            for path, error in failed:
                click.echo(f"    ✗ {Path(path).name}: {error}")
        for result in all_results:
            if dry_run:
                timeline_name = (
                    Path(result.output_path).with_suffix(".timeline.json").name
                )
                click.echo(f"  ✓ {timeline_name} (dry run; no video rendered)")
            else:
                click.echo(f"  ✓ {Path(result.output_path).name}")
        if failed:
            raise click.exceptions.Exit(1)


if __name__ == "__main__":
    main()
