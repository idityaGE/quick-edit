"""
Main pipeline orchestrator.

Ties together all modules into a single processing pipeline:
1. Analyze (VAD + motion + transcription) -- cached
2. Combine detection arrays
3. Apply margin + smoothing
4. LLM semantic pass (optional)
5. Build timeline
6. Render final video with subtitles
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from quickedit.analyze.combine import DetectionArrays, evaluate_expression
from quickedit.analyze.motion import analyze_motion
from quickedit.analyze.transcribe import (
    TranscriptionResult,
    transcribe,
    words_to_frame_array,
)
from quickedit.analyze.vad import analyze_vad, get_video_info
from quickedit.cache import cache
from quickedit.edit.edl import EditDecision, filter_by_confidence
from quickedit.edit.llm import SilentSegmentInfo, analyze_with_llm
from quickedit.edit.margin import apply_margin_seconds
from quickedit.edit.smoothing import smooth_seconds
from quickedit.render.subtitle import (
    SubtitleStyle,
    generate_ass_subtitles,
    generate_srt_subtitles,
)
from quickedit.render.video import render_video
from quickedit.timeline.timeline import (
    CutSegment,
    Timeline,
    frames_to_timeline,
    merge_timelines,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the full processing pipeline."""

    # Input / Output
    input_path: str = ""
    output_path: str = ""

    # Analysis
    whisper_model: str = "base"  # tiny, base, small, medium, large-v3
    whisper_device: str = "cpu"  # cpu or cuda
    whisper_compute_type: str = "int8"  # int8 for cpu, float16 for cuda
    whisper_language: str | None = None  # auto-detect if None
    vad_threshold: float = 0.5  # Silero VAD threshold
    motion_threshold: float = 0.02  # fraction of pixels changed
    motion_scale_width: int = 400  # downscale for motion analysis
    motion_blur_sigma: int = 9  # Gaussian blur for noise reduction

    # Detection combination
    combine_expr: str = "or:speech,motion"  # how to combine detectors

    # Edit parameters
    start_margin: float = 0.2  # seconds to expand before keep regions
    end_margin: float = 0.2  # seconds to expand after keep regions
    minclip: float = 0.1  # minimum keep segment duration (seconds)
    mincut: float = 0.2  # minimum cut gap duration (seconds)

    # LLM
    use_llm: bool = False  # explicit opt-in: transcript leaves the machine
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: str | None = None  # reads ANTHROPIC_API_KEY if None
    custom_prompt: str | None = None  # custom editing instructions
    llm_confidence_threshold: float = 0.7  # min confidence to apply LLM cuts

    # Subtitles
    subtitle_style: str = "fancy"  # "fancy" (word highlight) or "simple" (SRT)
    subtitle_font: str = "Arial"
    subtitle_size: int = 20
    subtitle_color: str = "&H00FFFFFF"
    subtitle_highlight: str = "&H0000FFFF"

    # Rendering
    video_codec: str = "libx264"
    crf: int = 18
    preset: str = "medium"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"

    # Caching
    use_cache: bool = True

    # Advanced: Motion detection (detailed)
    motion_pixel_threshold: int = 10  # pixel change threshold for binary diff

    # Advanced: Subtitles (detailed)
    subtitle_silence_gap: float = 0.7  # gap between subtitle groups (seconds)

    # Advanced: Cache
    cache_hash_length: int = 32  # characters of hash for cache key

    # Advanced: Silent segment classification
    silent_segment_min_duration: float = 0.5  # minimum duration to classify

    # Advanced: Motion detection performance
    motion_frame_skip: int = 1  # 1 = all frames, 2 = every other, etc.
    motion_backend: str = "opencv"  # "opencv", "opencv-parallel", or "ffmpeg"
    motion_workers: int = 4  # workers for opencv-parallel backend

    # Progress reporting
    progress_callback: Callable[[str, float, str], None] | None = None
    # Signature: (step: str, progress: float 0-1, message: str) -> None

    # Misc
    verbose: bool = False
    dry_run: bool = False  # if True, analyze + build timeline but skip render


@dataclass
class PipelineResult:
    """Result of running the pipeline."""

    output_path: str
    timeline: Timeline
    transcript: TranscriptionResult | None
    llm_decisions: list[EditDecision]
    timing: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [self.timeline.summary()]
        if self.timing:
            lines.append("\nTiming:")
            for step, elapsed in self.timing.items():
                lines.append(f"  {step}: {elapsed:.1f}s")
            total = sum(self.timing.values())
            lines.append(f"  total: {total:.1f}s")
        return "\n".join(lines)


def _validate_video_info(info: dict, input_path: Path) -> None:
    """Validate video has expected properties for processing."""
    if info.get("fps", 0) <= 0:
        raise ValueError(f"Invalid FPS ({info.get('fps')}) for video: {input_path}")
    if info.get("total_frames", 0) <= 0:
        raise ValueError(f"Invalid frame count for video: {input_path}")
    if not info.get("has_audio", False):
        raise ValueError(
            f"Video has no audio track: {input_path}. QuickEdit requires audio "
            "for speech detection and rendering."
        )


def _report_progress(
    config: PipelineConfig,
    step: str,
    progress: float,
    message: str = "",
) -> None:
    """Report progress if callback is set."""
    if config.progress_callback:
        config.progress_callback(step, progress, message)


def _detection_names_in_expr(expr: str | list) -> set[str]:
    """Return detection array names referenced by a combine expression."""
    operations = {"or", "and", "not", "xor"}

    if isinstance(expr, str):
        if ":" in expr:
            op, operands = expr.split(":", 1)
            names = {op.strip()} if op.strip().lower() not in operations else set()
            names.update(
                operand.strip()
                for operand in operands.split(",")
                if operand.strip() and operand.strip().lower() not in operations
            )
            return names
        stripped = expr.strip()
        return {stripped} if stripped else set()

    if isinstance(expr, list):
        names: set[str] = set()
        if not expr:
            return names
        for index, item in enumerate(expr):
            if isinstance(item, list):
                names.update(_detection_names_in_expr(item))
            elif isinstance(item, str):
                if index == 0 and item.lower() in operations:
                    continue
                names.add(item)
        return names

    return set()


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """
    Run the full video processing pipeline.

    Steps:
    1. Get video info
    2. Run VAD analysis (cached)
    3. Run motion analysis (cached)
    4. Run transcription (cached)
    5. Combine detection arrays
    6. Apply margin + smoothing
    7. Optionally run LLM pass
    8. Build timeline
    9. Generate subtitles
    10. Render final video

    Returns PipelineResult with output path, timeline, and timing info.
    """
    input_path = Path(config.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    for command in ("ffmpeg", "ffprobe"):
        if shutil.which(command) is None:
            raise RuntimeError(
                f"Required dependency '{command}' was not found on PATH. "
                "Install FFmpeg and try again."
            )

    output_path = config.output_path
    if not output_path:
        output_path = str(input_path.with_stem(input_path.stem + "_edited"))

    timing: dict[str, float] = {}

    # --- Step 1: Video info ---
    logger.info("Getting video info...")
    info = get_video_info(input_path)
    _validate_video_info(info, input_path)
    fps = info["fps"]
    duration = info["duration"]
    total_frames = info["total_frames"]
    logger.info(
        f"Video: {fps:.2f}fps, {duration:.1f}s, {total_frames} frames, "
        f"{info['width']}x{info['height']}"
    )

    # --- Steps 2-4: Parallel analysis (VAD + Motion + Transcription) ---
    # These three analyses are independent and can run concurrently.
    # VAD reads audio, motion reads video frames, transcription reads audio
    # through whisper. Running in parallel gives 2-3x speedup.
    detection_names = _detection_names_in_expr(config.combine_expr)
    needs_vad = "speech" in detection_names or config.use_llm
    needs_motion = "motion" in detection_names or config.use_llm
    needs_transcription = (
        config.use_llm or config.subtitle_style != "none" or "words" in detection_names
    )
    transcript = None
    analysis_t0 = time.time()

    def _vad_task():
        t0 = time.time()
        _report_progress(config, "vad", 0.0, "Starting voice activity detection")
        logger.info("Running voice activity detection...")
        result = _run_vad_cached(config, input_path, fps, total_frames)
        elapsed = time.time() - t0
        pct = np.mean(result) * 100
        logger.info(f"VAD: {pct:.1f}% speech detected")
        _report_progress(config, "vad", 1.0, f"{pct:.1f}% speech — {elapsed:.1f}s")
        return result, elapsed

    def _motion_task():
        t0 = time.time()
        _report_progress(config, "motion", 0.0, "Starting motion detection")
        logger.info("Running motion detection...")
        result = _run_motion_cached(config, input_path, fps, total_frames)
        elapsed = time.time() - t0
        pct = np.mean(result) * 100
        logger.info(f"Motion: {pct:.1f}% visual activity detected")
        _report_progress(config, "motion", 1.0, f"{pct:.1f}% activity — {elapsed:.1f}s")
        return result, elapsed

    def _transcription_task():
        t0 = time.time()
        _report_progress(config, "transcription", 0.0, "Starting transcription")
        logger.info(f"Transcribing with whisper model '{config.whisper_model}'...")
        result = _run_transcription_cached(config, input_path)
        elapsed = time.time() - t0
        logger.info(
            f"Transcription: {len(result.words)} words, language={result.language}"
        )
        _report_progress(
            config, "transcription", 1.0, f"{len(result.words)} words — {elapsed:.1f}s"
        )
        return result, elapsed

    max_workers = max(1, sum([needs_vad, needs_motion, needs_transcription]))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_vad = executor.submit(_vad_task) if needs_vad else None
        future_motion = executor.submit(_motion_task) if needs_motion else None
        future_transcription = (
            executor.submit(_transcription_task) if needs_transcription else None
        )

        # Collect results (raises if any task failed)
        speech_frames = None
        motion_frames = None
        if future_vad is not None:
            speech_frames, timing["vad"] = future_vad.result()
        if future_motion is not None:
            motion_frames, timing["motion"] = future_motion.result()
        if future_transcription is not None:
            transcript, timing["transcription"] = future_transcription.result()

    analysis_wall = time.time() - analysis_t0
    analysis_sum = sum(
        timing.get(key, 0) for key in ("vad", "motion", "transcription")
    )
    if analysis_sum > 0:
        logger.info(
            f"Parallel analysis: {analysis_wall:.1f}s wall time "
            f"(vs {analysis_sum:.1f}s sequential — "
            f"{analysis_sum / analysis_wall:.1f}x speedup)"
        )

    # --- Step 5: Combine detection arrays ---
    t0 = time.time()
    _report_progress(config, "combine", 0.0, "Combining detection arrays")
    logger.info(f"Combining detectors: {config.combine_expr}")
    detection_arrays: dict[str, np.ndarray] = {}
    if speech_frames is not None:
        detection_arrays["speech"] = speech_frames
    if motion_frames is not None:
        detection_arrays["motion"] = motion_frames
    detections = DetectionArrays(arrays=detection_arrays, fps=fps, total_frames=total_frames)

    # If we have transcription, add word-based detection too
    if transcript:
        word_frames = words_to_frame_array(transcript.words, fps, total_frames)
        detections.add("words", word_frames)

    _report_progress(config, "combine", 0.5, "Evaluating expression")
    keep_frames = evaluate_expression(config.combine_expr, detections)
    timing["combine"] = time.time() - t0
    _report_progress(config, "combine", 1.0, f"Done — {timing['combine']:.1f}s")

    # --- Step 6: Margin + Smoothing ---
    t0 = time.time()
    logger.info("Applying margin and smoothing...")
    keep_frames = apply_margin_seconds(
        keep_frames,
        fps,
        start_margin_sec=config.start_margin,
        end_margin_sec=config.end_margin,
    )
    keep_frames = smooth_seconds(
        keep_frames,
        fps,
        minclip_sec=config.minclip,
        mincut_sec=config.mincut,
    )
    timing["margin_smooth"] = time.time() - t0
    keep_pct = np.mean(keep_frames) * 100
    logger.info(f"After margin+smoothing: keeping {keep_pct:.1f}% of frames")

    # --- Step 7: Build initial timeline ---
    timeline = frames_to_timeline(
        keep_frames=keep_frames,
        source=str(input_path),
        fps=fps,
        duration=duration,
        width=info["width"],
        height=info["height"],
    )

    # --- Step 8: LLM pass (optional) ---
    llm_decisions: list[EditDecision] = []
    if config.use_llm and transcript:
        if speech_frames is None or motion_frames is None:
            raise RuntimeError("LLM analysis requires speech and motion detection")
        t0 = time.time()
        _report_progress(config, "llm", 0.0, "Starting LLM analysis")
        logger.info("Running LLM semantic analysis...")

        # Classify silent segments for the LLM
        _report_progress(config, "llm", 0.1, "Classifying silent segments")
        silent_info = _classify_silent_segments(
            keep_frames,
            speech_frames,
            motion_frames,
            fps,
            config.motion_threshold,
            min_duration=config.silent_segment_min_duration,
        )

        _report_progress(config, "llm", 0.2, "Sending to LLM...")
        llm_decisions = analyze_with_llm(
            transcript=transcript,
            silent_segments=silent_info,
            custom_prompt=config.custom_prompt,
            api_key=config.llm_api_key,
            model=config.llm_model,
        )

        _report_progress(config, "llm", 0.8, "Filtering by confidence")
        # Filter by confidence
        llm_decisions = filter_by_confidence(
            llm_decisions,
            config.llm_confidence_threshold,
        )

        timing["llm"] = time.time() - t0
        logger.info(f"LLM suggested {len(llm_decisions)} cuts")
        _report_progress(
            config, "llm", 1.0, f"{len(llm_decisions)} cuts — {timing['llm']:.1f}s"
        )

        # Apply LLM cuts to timeline
        if llm_decisions:
            llm_cuts = [
                CutSegment(
                    src_start=d.start,
                    src_end=d.end,
                    reason=f"{d.reason.value}: {d.note}",
                )
                for d in llm_decisions
            ]
            timeline = merge_timelines(timeline, llm_cuts)

    logger.info(f"\n{timeline.summary()}")

    # --- Step 9: Generate subtitles ---
    subtitle_path = None
    if transcript and config.subtitle_style != "none":
        t0 = time.time()
        _report_progress(config, "subtitles", 0.0, "Generating subtitles")
        logger.info("Generating subtitles...")

        if config.subtitle_style == "fancy":
            sub_ext = ".ass"
            subtitle_path = Path(output_path).with_suffix(sub_ext)
            style = SubtitleStyle(
                font_name=config.subtitle_font,
                font_size=config.subtitle_size,
                primary_color=config.subtitle_color,
                highlight_color=config.subtitle_highlight,
            )
            _report_progress(config, "subtitles", 0.3, "Writing ASS subtitles")
            generate_ass_subtitles(
                transcript.words,
                timeline,
                subtitle_path,
                style,
                silence_gap=config.subtitle_silence_gap,
            )
        else:
            sub_ext = ".srt"
            subtitle_path = Path(output_path).with_suffix(sub_ext)
            _report_progress(config, "subtitles", 0.3, "Writing SRT subtitles")
            generate_srt_subtitles(
                transcript.words,
                timeline,
                subtitle_path,
                silence_gap=config.subtitle_silence_gap,
            )

        timing["subtitles"] = time.time() - t0
        logger.info(f"Subtitles written to {subtitle_path}")
        _report_progress(
            config, "subtitles", 1.0, f"Written — {timing['subtitles']:.1f}s"
        )

    # Save timeline JSON alongside output
    timeline_path = Path(output_path).with_suffix(".timeline.json")
    timeline.to_json(timeline_path)
    logger.info(f"Timeline saved to {timeline_path}")

    # --- Step 10: Render ---
    if config.dry_run:
        logger.info("Dry run -- skipping render. Timeline and subtitles generated.")
        # Print detailed cut list
        for i, cut in enumerate(timeline.cuts):
            text = ""
            if transcript:
                text = transcript.get_text_in_range(cut.src_start, cut.src_end)
                if text:
                    text = f' "{text[:60]}"'
            reason = f" ({cut.reason})" if cut.reason else ""
            logger.info(
                f"  CUT {i + 1}: {cut.src_start:.2f}s - {cut.src_end:.2f}s"
                f"{reason}{text}"
            )
    else:
        t0 = time.time()
        _report_progress(config, "render", 0.0, "Starting FFmpeg render")
        logger.info("Rendering final video...")
        render_video(
            timeline=timeline,
            output_path=output_path,
            subtitle_path=subtitle_path,
            codec=config.video_codec,
            crf=config.crf,
            preset=config.preset,
            audio_codec=config.audio_codec,
            audio_bitrate=config.audio_bitrate,
        )
        timing["render"] = time.time() - t0
        logger.info(f"Output written to {output_path}")
        _report_progress(config, "render", 1.0, f"Done — {timing['render']:.1f}s")

    return PipelineResult(
        output_path=output_path,
        timeline=timeline,
        transcript=transcript,
        llm_decisions=llm_decisions,
        timing=timing,
    )


# --- Cached analysis wrappers ---


def _run_vad_cached(
    config: PipelineConfig,
    input_path: Path,
    fps: float,
    total_frames: int,
) -> np.ndarray:
    """Run VAD with caching."""
    params = {"threshold": config.vad_threshold, "fps": round(fps, 4)}

    if config.use_cache:
        cached = cache.load_array(input_path, "vad", params)
        if cached is not None:
            logger.info("Using cached VAD result")
            return cached

    result = analyze_vad(input_path, threshold=config.vad_threshold)
    speech_frames = result.speech_frames

    # Ensure correct length
    if len(speech_frames) != total_frames:
        logger.warning(
            f"VAD returned {len(speech_frames)} frames, expected {total_frames}. "
            f"Difference: {abs(len(speech_frames) - total_frames)} frames. "
            f"Video may have variable frame rate."
        )
        padded = np.zeros(total_frames, dtype=bool)
        n = min(len(speech_frames), total_frames)
        padded[:n] = speech_frames[:n]
        speech_frames = padded

    if config.use_cache:
        cache.save_array(input_path, "vad", params, speech_frames)

    return speech_frames


def _run_motion_cached(
    config: PipelineConfig,
    input_path: Path,
    fps: float,
    total_frames: int,
) -> np.ndarray:
    """Run motion detection with caching."""
    params = {
        "threshold": config.motion_threshold,
        "scale_width": config.motion_scale_width,
        "blur_sigma": config.motion_blur_sigma,
        "pixel_threshold": config.motion_pixel_threshold,
        "frame_skip": config.motion_frame_skip,
        "backend": config.motion_backend,
        "fps": round(fps, 4),
    }

    if config.use_cache:
        cached = cache.load_array(input_path, "motion", params)
        if cached is not None:
            logger.info("Using cached motion result")
            return cached

    result = analyze_motion(
        input_path,
        threshold=config.motion_threshold,
        scale_width=config.motion_scale_width,
        blur_sigma=config.motion_blur_sigma,
        frame_skip=config.motion_frame_skip,
        pixel_threshold=config.motion_pixel_threshold,
        backend=config.motion_backend,
        workers=config.motion_workers,
        progress_callback=lambda p: _report_progress(
            config, "motion", p * 0.9, f"Analyzing frames... {p * 100:.0f}%"
        ),
    )
    motion_frames = result.activity_frames

    if len(motion_frames) != total_frames:
        logger.warning(
            f"Motion detection returned {len(motion_frames)} frames, expected {total_frames}. "
            f"Difference: {abs(len(motion_frames) - total_frames)} frames. "
            f"Video may have variable frame rate."
        )
        padded = np.zeros(total_frames, dtype=bool)
        n = min(len(motion_frames), total_frames)
        padded[:n] = motion_frames[:n]
        motion_frames = padded

    if config.use_cache:
        cache.save_array(input_path, "motion", params, motion_frames)

    return motion_frames


def _run_transcription_cached(
    config: PipelineConfig,
    input_path: Path,
) -> TranscriptionResult:
    """Run transcription with caching."""
    params = {
        "model": config.whisper_model,
        "language": config.whisper_language,
    }

    if config.use_cache:
        cached = cache.load_json(input_path, "transcription", params)
        if cached is not None:
            logger.info("Using cached transcription")
            return _json_to_transcription(cached)

    result = transcribe(
        input_path,
        model_size=config.whisper_model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        language=config.whisper_language,
        progress_callback=lambda step, prog, msg: _report_progress(
            config, step, prog, msg
        ),
    )

    if config.use_cache:
        cache.save_json(
            input_path, "transcription", params, _transcription_to_json(result)
        )

    return result


def _transcription_to_json(t: TranscriptionResult) -> dict:
    """Serialize transcription result for caching."""
    return {
        "language": t.language,
        "language_probability": t.language_probability,
        "duration": t.duration,
        "text": t.text,
        "words": [
            {
                "text": w.text,
                "start": w.start,
                "end": w.end,
                "probability": w.probability,
            }
            for w in t.words
        ],
        "segments": [
            {
                "text": s.text,
                "start": s.start,
                "end": s.end,
                "words": [
                    {
                        "text": w.text,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.probability,
                    }
                    for w in s.words
                ],
            }
            for s in t.segments
        ],
    }


def _json_to_transcription(data: dict) -> TranscriptionResult:
    """Deserialize transcription result from cache."""
    from quickedit.analyze.transcribe import Segment, Word

    words = [
        Word(
            text=w["text"],
            start=w["start"],
            end=w["end"],
            probability=w["probability"],
        )
        for w in data["words"]
    ]

    segments = [
        Segment(
            text=s["text"],
            start=s["start"],
            end=s["end"],
            words=[
                Word(
                    text=w["text"],
                    start=w["start"],
                    end=w["end"],
                    probability=w["probability"],
                )
                for w in s.get("words", [])
            ],
        )
        for s in data["segments"]
    ]

    return TranscriptionResult(
        segments=segments,
        words=words,
        language=data["language"],
        language_probability=data["language_probability"],
        duration=data["duration"],
        text=data["text"],
    )


def _classify_silent_segments(
    keep_frames: np.ndarray,
    speech_frames: np.ndarray,
    motion_frames: np.ndarray,
    fps: float,
    motion_threshold: float,
    min_duration: float = 0.5,
) -> list[SilentSegmentInfo]:
    """
    Classify silent segments as having visual activity or being dead air.

    This info is sent to the LLM so it knows not to cut segments where
    the creator is writing/coding on screen.
    """
    # Find non-speech segments
    padded = np.concatenate([[True], speech_frames, [True]])
    silence_starts = np.where(np.diff(padded.astype(int)) == -1)[0]
    silence_ends = np.where(np.diff(padded.astype(int)) == 1)[0]

    segments = []
    for start_frame, end_frame in zip(silence_starts, silence_ends):
        # Only classify segments longer than min_duration
        duration = (end_frame - start_frame) / fps
        if duration < min_duration:
            continue

        # Check motion in this range
        motion_slice = motion_frames[start_frame:end_frame]
        motion_score = float(np.mean(motion_slice)) if len(motion_slice) > 0 else 0.0
        has_activity = motion_score >= motion_threshold

        segments.append(
            SilentSegmentInfo(
                start=start_frame / fps,
                end=end_frame / fps,
                has_visual_activity=has_activity,
                motion_score=motion_score,
            )
        )

    return segments
