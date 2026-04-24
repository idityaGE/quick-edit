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
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.analyze.vad import analyze_vad, get_video_info
from src.analyze.motion import analyze_motion
from src.analyze.transcribe import transcribe, TranscriptionResult, words_to_frame_array
from src.analyze.combine import DetectionArrays, evaluate_expression
from src.edit.margin import apply_margin_seconds
from src.edit.smoothing import smooth_seconds
from src.edit.llm import analyze_with_llm, SilentSegmentInfo
from src.edit.edl import EditDecision, filter_by_confidence
from src.timeline.timeline import (
    Timeline,
    CutSegment,
    frames_to_timeline,
    merge_timelines,
)
from src.render.video import render_video
from src.render.subtitle import (
    generate_ass_subtitles,
    generate_srt_subtitles,
    SubtitleStyle,
)
from src.cache import cache

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
    use_llm: bool = True  # enable LLM semantic pass
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

    # Progress reporting
    progress_callback: callable | None = None
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
    if not info.get("has_audio", True):  # Default True for backwards compat
        logger.warning(
            f"Video has no audio track: {input_path}. VAD will return empty."
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

    # --- Step 2: VAD ---
    t0 = time.time()
    _report_progress(config, "vad", 0.0, "Starting voice activity detection")
    logger.info("Running voice activity detection...")
    speech_frames = _run_vad_cached(config, input_path, fps, total_frames)
    timing["vad"] = time.time() - t0
    speech_pct = np.mean(speech_frames) * 100
    logger.info(f"VAD: {speech_pct:.1f}% speech detected")
    _report_progress(config, "vad", 1.0, f"{speech_pct:.1f}% speech detected")

    # --- Step 3: Motion detection ---
    t0 = time.time()
    _report_progress(config, "motion", 0.0, "Starting motion detection")
    logger.info("Running motion detection...")
    motion_frames = _run_motion_cached(config, input_path, fps, total_frames)
    timing["motion"] = time.time() - t0
    motion_pct = np.mean(motion_frames) * 100
    logger.info(f"Motion: {motion_pct:.1f}% visual activity detected")
    _report_progress(
        config, "motion", 1.0, f"{motion_pct:.1f}% visual activity detected"
    )

    # --- Step 4: Transcription ---
    t0 = time.time()
    transcript = None
    if config.use_llm or config.subtitle_style != "none":
        _report_progress(config, "transcription", 0.0, "Starting transcription")
        logger.info(f"Transcribing with whisper model '{config.whisper_model}'...")
        transcript = _run_transcription_cached(config, input_path)
        timing["transcription"] = time.time() - t0
        logger.info(
            f"Transcription: {len(transcript.words)} words, "
            f"language={transcript.language}"
        )
        _report_progress(
            config, "transcription", 1.0, f"{len(transcript.words)} words transcribed"
        )

    # --- Step 5: Combine detection arrays ---
    t0 = time.time()
    _report_progress(config, "combine", 0.0, "Combining detection arrays")
    logger.info(f"Combining detectors: {config.combine_expr}")
    detections = DetectionArrays(
        arrays={"speech": speech_frames, "motion": motion_frames},
        fps=fps,
        total_frames=total_frames,
    )

    # If we have transcription, add word-based detection too
    if transcript:
        word_frames = words_to_frame_array(transcript.words, fps, total_frames)
        detections.add("words", word_frames)

    keep_frames = evaluate_expression(config.combine_expr, detections)
    timing["combine"] = time.time() - t0

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
        t0 = time.time()
        logger.info("Running LLM semantic analysis...")

        # Classify silent segments for the LLM
        silent_info = _classify_silent_segments(
            keep_frames,
            speech_frames,
            motion_frames,
            fps,
            config.motion_threshold,
            min_duration=config.silent_segment_min_duration,
        )

        llm_decisions = analyze_with_llm(
            transcript=transcript,
            silent_segments=silent_info,
            custom_prompt=config.custom_prompt,
            api_key=config.llm_api_key,
            model=config.llm_model,
        )

        # Filter by confidence
        llm_decisions = filter_by_confidence(
            llm_decisions,
            config.llm_confidence_threshold,
        )

        timing["llm"] = time.time() - t0
        logger.info(f"LLM suggested {len(llm_decisions)} cuts")

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
            generate_srt_subtitles(
                transcript.words,
                timeline,
                subtitle_path,
                silence_gap=config.subtitle_silence_gap,
            )

        timing["subtitles"] = time.time() - t0
        logger.info(f"Subtitles written to {subtitle_path}")

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
    params = {"threshold": config.vad_threshold}

    if config.use_cache:
        cached = cache.load_array(input_path, "vad", params, config.cache_hash_length)
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
        cache.save_array(input_path, "vad", params, speech_frames, config.cache_hash_length)

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
    }

    if config.use_cache:
        cached = cache.load_array(input_path, "motion", params, config.cache_hash_length)
        if cached is not None:
            logger.info("Using cached motion result")
            return cached

    result = analyze_motion(
        input_path,
        threshold=config.motion_threshold,
        scale_width=config.motion_scale_width,
        blur_sigma=config.motion_blur_sigma,
        frame_skip=config.motion_frame_skip,
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
        cache.save_array(input_path, "motion", params, motion_frames, config.cache_hash_length)

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
        cached = cache.load_json(input_path, "transcription", params, config.cache_hash_length)
        if cached is not None:
            logger.info("Using cached transcription")
            return _json_to_transcription(cached)

    result = transcribe(
        input_path,
        model_size=config.whisper_model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        language=config.whisper_language,
    )

    if config.use_cache:
        cache.save_json(
            input_path, "transcription", params, _transcription_to_json(result),
            config.cache_hash_length,
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
    from src.analyze.transcribe import Word, Segment

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
