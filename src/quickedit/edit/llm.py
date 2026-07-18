"""
LLM-based semantic analysis of video transcripts.

Uses Claude or Gemini API to analyze the transcript and identify segments to remove:
filler words, false starts, repetitions, tangents, etc.

Supports custom prompts for domain-specific editing (e.g., DSA tutorials,
cooking videos, vlogs).

Supported providers:
- Anthropic (Claude): models starting with "claude-"
- Google (Gemini): models starting with "gemini-"
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import cast

from quickedit.analyze.transcribe import TranscriptionResult
from quickedit.edit.edl import CutReason, EditDecision

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


def _detect_provider(model: str) -> LLMProvider:
    """Detect the LLM provider based on model name."""
    model_lower = model.lower()
    if model_lower.startswith("gemini"):
        return LLMProvider.GEMINI
    # Default to Anthropic for claude-* models or unknown models
    return LLMProvider.ANTHROPIC


# Maximum words to send per LLM chunk to stay within context limits
CHUNK_SIZE_WORDS = 3000
CHUNK_OVERLAP_WORDS = 200

SYSTEM_PROMPT = """\
You are a professional video editor AI. You analyze transcripts from recorded \
videos and identify segments that should be removed to create a clean, \
polished final cut.

You will receive a transcript with word-level timestamps. Your job is to \
identify segments to REMOVE. Be conservative -- it's better to keep something \
questionable than to cut important content.

You also receive "silent segment classifications" that tell you whether silent \
parts of the video have visual activity (screen changes, typing, drawing) or are \
truly dead air. NEVER remove silent segments marked as "visual_activity" -- the \
creator is doing something important on screen.

Return ONLY valid JSON. No markdown, no explanation outside the JSON."""

DEFAULT_EDIT_PROMPT = """\
Analyze this transcript and identify segments to remove. Apply these rules:

1. REMOVE filler words: "um", "uh", "like" (when used as filler, not comparison), \
"you know", "basically", "actually" (when meaningless), "right" (when used as \
verbal tic), "so" (at sentence starts when meaningless)
2. REMOVE false starts: where the speaker begins a sentence, stops, and restarts. \
Keep the better/complete version.
3. REMOVE repeated explanations: if the same concept is explained twice, keep the \
clearer/more complete explanation.
4. REMOVE off-topic tangents that don't serve the main content.
5. REMOVE verbal fumbling, stuttering, or confused segments where the speaker is \
clearly lost.
6. KEEP all substantive content, even if imperfect.
7. KEEP intentional pauses for emphasis.
8. KEEP segments where the speaker announces they will write/code/draw something \
and the following silence has visual activity.
9. Add 0.15s margin around cuts for smooth transitions.

For each segment to remove, provide:
- start_time (seconds, from word timestamps)
- end_time (seconds)
- reason: "filler_word" | "false_start" | "repetition" | "tangent" | "dead_air" | "custom"
- confidence: 0.0-1.0 (how confident you are this should be removed)
- transcript: the text being removed
- note: brief explanation"""


# Pre-built prompt templates for common use cases
PROMPT_TEMPLATES = {
    "dsa": """\
Analyze this transcript from a DSA (Data Structures & Algorithms) teaching video.

REMOVE:
1. Filler words: "um", "uh", "like", "you know", "basically", "so" (at starts)
2. False starts where I begin explaining an algorithm/concept, get confused, and \
restart. Keep the clearer/more complete attempt.
3. Moments where I verbally fumble through code logic or lose my train of thought.
4. Repeated explanations of the same concept -- keep the one that is more concise \
and correct.
5. Off-topic tangents unrelated to the current algorithm/problem.

KEEP (critical):
6. ALL code walkthroughs, even if slow -- the viewer needs to follow along.
7. ALL complexity analysis (time/space). Even partial explanations are valuable.
8. ALL segments where I say "let me write/code/trace this" -- the following silence \
has visual activity (I am coding/writing on screen).
9. Comparisons between approaches (e.g., brute force vs optimized).
10. Edge case discussions.
11. Intuition building ("think of it like...", "the key insight is...")

Be conservative with code explanations. When in doubt, KEEP it.""",
    "tutorial": """\
Analyze this transcript from a programming tutorial video.

REMOVE:
1. Filler words and verbal tics.
2. Moments where I troubleshoot a typo or syntax error that isn't educational.
3. Repeated attempts at explaining the same setup step.
4. "Let me think..." pauses where nothing productive happens.

KEEP:
5. ALL step-by-step instructions, even if slightly fumbled.
6. Debugging moments that are educational (teaching how to debug).
7. All screen activity segments (coding, configuring, running commands).""",
    "lecture": """\
Analyze this transcript from an educational lecture.

REMOVE:
1. Filler words and verbal tics.
2. Administrative tangents (scheduling, announcements) unless brief.
3. False starts on explanations -- keep the better version.
4. Long pauses with no visual activity.

KEEP:
5. ALL conceptual explanations, proofs, and derivations.
6. Questions and answers (even if the question seems basic).
7. Examples and analogies.
8. Transitions between topics ("Now let's move on to...").""",
}


@dataclass
class SilentSegmentInfo:
    """Classification of a silent segment for LLM context."""

    start: float
    end: float
    has_visual_activity: bool
    motion_score: float  # average motion in the segment


async def analyze_with_llm_async(
    transcript: TranscriptionResult,
    silent_segments: list[SilentSegmentInfo] | None = None,
    custom_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    max_concurrent: int = 3,
) -> list[EditDecision]:
    """
    Async version with parallel chunk processing.

    Args:
        transcript: Word-level transcription.
        silent_segments: Classifications of silent periods (visual activity or not).
        custom_prompt: Custom editing instructions. If None, uses DEFAULT_EDIT_PROMPT.
        api_key: API key for the provider. If None, reads from env var
                 (ANTHROPIC_API_KEY or GOOGLE_API_KEY based on model).
        model: Model to use. Prefix determines provider:
               - "claude-*": Anthropic
               - "gemini-*": Google Gemini
        max_concurrent: Maximum concurrent API calls (rate limit).

    Returns:
        List of EditDecision objects for segments to remove.
    """
    import asyncio

    provider = _detect_provider(model)
    edit_prompt = custom_prompt or DEFAULT_EDIT_PROMPT

    words_data = transcript.to_transcript_with_timestamps()
    silent_info = _build_silent_info(silent_segments)
    chunks = _chunk_words(words_data, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS)

    if not chunks or not chunks[0]:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    if provider == LLMProvider.GEMINI:
        process_chunk = await _create_gemini_chunk_processor(
            model, api_key, edit_prompt, silent_info, chunks, semaphore
        )
    else:
        process_chunk = await _create_anthropic_chunk_processor(
            model, api_key, edit_prompt, silent_info, chunks, semaphore
        )

    tasks = [process_chunk(i, chunk) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)

    all_decisions: list[EditDecision] = []
    for decisions in results:
        all_decisions.extend(decisions)

    return _deduplicate_decisions(all_decisions)


LLM_PROVIDER_TIMEOUT_SECONDS = 300  # 5 minutes per API call


async def _create_anthropic_chunk_processor(
    model: str,
    api_key: str | None,
    edit_prompt: str,
    silent_info: str,
    chunks: list[list[dict]],
    semaphore,
):
    """Create an async chunk processor for Anthropic."""
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic support is not installed. Install it with "
            "`pip install 'quickedit[anthropic]'`."
        ) from exc

    client = AsyncAnthropic(api_key=api_key, timeout=LLM_PROVIDER_TIMEOUT_SECONDS)

    async def process_chunk(i: int, chunk: list[dict]) -> list[EditDecision]:
        async with semaphore:
            logger.info(
                f"Processing LLM chunk {i + 1}/{len(chunks)} "
                f"({len(chunk)} words, "
                f"{chunk[0]['start']:.1f}s - {chunk[-1]['end']:.1f}s) [Anthropic]"
            )
            user_message = _build_user_message(chunk, edit_prompt, silent_info)
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            response_text = cast(str, getattr(response.content[0], "text", ""))
            return _parse_llm_response(response_text)

    return process_chunk


async def _create_gemini_chunk_processor(
    model: str,
    api_key: str | None,
    edit_prompt: str,
    silent_info: str,
    chunks: list[list[dict]],
    semaphore,
):
    """Create an async chunk processor for Gemini."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Gemini support is not installed. Install it with "
            "`pip install 'quickedit[gemini]'`."
        ) from exc

    # Configure API key
    api_key = (
        api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    )
    if not api_key:
        raise ValueError(
            "Gemini API key not found. Set GOOGLE_API_KEY or GEMINI_API_KEY env var, "
            "or pass api_key parameter."
        )
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1"})

    async def process_chunk(i: int, chunk: list[dict]) -> list[EditDecision]:
        async with semaphore:
            logger.info(
                f"Processing LLM chunk {i + 1}/{len(chunks)} "
                f"({len(chunk)} words, "
                f"{chunk[0]['start']:.1f}s - {chunk[-1]['end']:.1f}s) [Gemini]"
            )
            user_message = _build_user_message(chunk, edit_prompt, silent_info)
            response = await client.aio.models.generate_content(
                model=model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )
            return _parse_llm_response(response.text or "")

    return process_chunk


def _build_silent_info(silent_segments: list[SilentSegmentInfo] | None) -> str:
    """Build silent segment info string for LLM prompt."""
    if not silent_segments:
        return ""
    silent_lines = []
    for seg in silent_segments:
        label = "visual_activity (KEEP)" if seg.has_visual_activity else "dead_air"
        silent_lines.append(
            f"  [{seg.start:.1f}s - {seg.end:.1f}s] {label} "
            f"(motion: {seg.motion_score:.3f})"
        )
    return "Silent segment classifications:\n" + "\n".join(silent_lines)


def _get_running_loop():
    """Return the running asyncio event loop, or None if there isn't one.

    This replaces the fragile try/except RuntimeError pattern that breaks
    in Jupyter and catches unrelated RuntimeErrors.
    """
    import asyncio

    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def analyze_with_llm(
    transcript: TranscriptionResult,
    silent_segments: list[SilentSegmentInfo] | None = None,
    custom_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[EditDecision]:
    """
    Send transcript to LLM for semantic analysis.

    Args:
        transcript: Word-level transcription.
        silent_segments: Classifications of silent periods (visual activity or not).
        custom_prompt: Custom editing instructions. If None, uses DEFAULT_EDIT_PROMPT.
        api_key: API key for the provider. If None, reads from env var.
        model: Model to use. Prefix determines provider:
               - "claude-*": Anthropic (uses ANTHROPIC_API_KEY)
               - "gemini-*": Google Gemini (uses GOOGLE_API_KEY or GEMINI_API_KEY)

    Returns:
        List of EditDecision objects for segments to remove.
    """
    import asyncio
    import concurrent.futures

    # Detect running event loop without fragile try/except RuntimeError.
    # asyncio.get_running_loop() raises RuntimeError when no loop exists,
    # but we isolate that to a narrow, purpose-built helper.
    running_loop = _get_running_loop()

    if running_loop is not None:
        # Inside an async context (e.g., Jupyter notebook).
        # Run in a separate thread so we get our own event loop and keep
        # the parallel chunk processing that analyze_with_llm_async provides.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                analyze_with_llm_async(
                    transcript, silent_segments, custom_prompt, api_key, model
                ),
            )
            return future.result()
    else:
        return asyncio.run(
            analyze_with_llm_async(
                transcript, silent_segments, custom_prompt, api_key, model
            )
        )


def _analyze_with_llm_sync(
    transcript: TranscriptionResult,
    silent_segments: list[SilentSegmentInfo] | None = None,
    custom_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[EditDecision]:
    """Synchronous version for when async isn't available."""
    provider = _detect_provider(model)
    edit_prompt = custom_prompt or DEFAULT_EDIT_PROMPT

    # Build word list with timestamps
    words_data = transcript.to_transcript_with_timestamps()

    # Build silent segment info
    silent_info = _build_silent_info(silent_segments)

    # Process in chunks if transcript is long
    all_decisions: list[EditDecision] = []
    chunks = _chunk_words(words_data, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS)

    # Create provider-specific client
    if provider == LLMProvider.GEMINI:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Gemini support is not installed. Install it with "
                "`pip install 'quickedit[gemini]'`."
            ) from exc

        api_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "Gemini API key not found. Set GOOGLE_API_KEY or GEMINI_API_KEY env var, "
                "or pass api_key parameter."
            )
        gemini_client = genai.Client(
            api_key=api_key, http_options={"api_version": "v1"}
        )
    else:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic support is not installed. Install it with "
                "`pip install 'quickedit[anthropic]'`."
            ) from exc

        client = Anthropic(api_key=api_key, timeout=LLM_PROVIDER_TIMEOUT_SECONDS)

    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        provider_name = "Gemini" if provider == LLMProvider.GEMINI else "Anthropic"
        logger.info(
            f"Processing LLM chunk {i + 1}/{len(chunks)} "
            f"({len(chunk)} words, "
            f"{chunk[0]['start']:.1f}s - {chunk[-1]['end']:.1f}s) [{provider_name}]"
        )

        user_message = _build_user_message(chunk, edit_prompt, silent_info)

        if provider == LLMProvider.GEMINI:
            response = gemini_client.models.generate_content(
                model=model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )
            response_text = response.text or ""
        else:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            response_text = cast(str, getattr(response.content[0], "text", ""))

        # Parse response
        decisions = _parse_llm_response(response_text)
        all_decisions.extend(decisions)

    # Deduplicate overlapping decisions (from chunk overlaps)
    all_decisions = _deduplicate_decisions(all_decisions)

    return all_decisions


def _build_user_message(
    words_data: list[dict],
    edit_prompt: str,
    silent_info: str,
) -> str:
    """Build the user message for the LLM."""
    # Format transcript for readability
    transcript_lines = []
    for w in words_data:
        transcript_lines.append(f"[{w['start']:.2f}-{w['end']:.2f}] {w['word']}")

    transcript_text = "\n".join(transcript_lines)

    message = f"""{edit_prompt}

{silent_info}

Transcript (with word-level timestamps):
{transcript_text}

Respond with a JSON object in this exact format:
{{
  "decisions": [
    {{
      "start_time": 12.3,
      "end_time": 15.7,
      "reason": "false_start",
      "confidence": 0.9,
      "transcript": "so um wait let me",
      "note": "Speaker restarts explanation of binary search"
    }}
  ]
}}

If nothing should be removed, return: {{"decisions": []}}"""

    return message


def _chunk_words(
    words: list[dict],
    chunk_size: int,
    overlap: int,
) -> list[list[dict]]:
    """Split words into overlapping chunks for processing."""
    if len(words) <= chunk_size:
        return [words]

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(words[start:end])
        if end >= len(words):
            break
        start = end - overlap

    return chunks


# Maximum response size to prevent memory issues
MAX_RESPONSE_SIZE = 100_000  # 100KB limit


def _parse_llm_response(response_text: str) -> list[EditDecision]:
    """Parse the LLM's JSON response into EditDecision objects."""
    # Check response size
    if len(response_text) > MAX_RESPONSE_SIZE:
        logger.warning(
            f"LLM response too large ({len(response_text)} bytes), truncating"
        )
        response_text = response_text[:MAX_RESPONSE_SIZE]

    # Try to extract JSON from the response
    text = response_text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM response as JSON: {text[:200]}...")
        return []

    decisions = []
    for item in data.get("decisions", []):
        decision = _parse_decision_item(item)
        if decision is not None:
            decisions.append(decision)

    return decisions


def _parse_decision_item(item: dict) -> EditDecision | None:
    """Parse and validate a single decision item from LLM response."""
    try:
        start_time = float(item.get("start_time", 0))
        end_time = float(item.get("end_time", 0))
        confidence = float(item.get("confidence", 0.8))

        # Validate
        if start_time < 0:
            logger.warning(
                f"Invalid LLM decision: start_time must be >= 0, got {start_time}"
            )
            return None
        if end_time <= start_time:
            logger.warning(
                f"Invalid LLM decision: end_time ({end_time}) must be > start_time ({start_time})"
            )
            return None
        if not 0 <= confidence <= 1:
            logger.warning(
                f"Invalid LLM decision: confidence must be 0-1, got {confidence}"
            )
            confidence = max(0, min(1, confidence))  # Clamp instead of reject

        reason_str = item.get("reason", "custom")
        try:
            reason = CutReason(reason_str)
        except ValueError:
            reason = CutReason.CUSTOM

        return EditDecision(
            start=start_time,
            end=end_time,
            action="remove",
            reason=reason,
            confidence=confidence,
            transcript=str(item.get("transcript", "")),
            note=str(item.get("note", "")),
        )
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid LLM decision item: {e}")
        return None


def _deduplicate_decisions(
    decisions: list[EditDecision],
    overlap_threshold: float = 0.5,
) -> list[EditDecision]:
    """
    Remove duplicate decisions that come from chunk overlaps.

    If two decisions overlap by more than overlap_threshold of the
    shorter one's duration, keep the one with higher confidence.
    """
    if len(decisions) <= 1:
        return decisions

    decisions.sort(key=lambda d: d.start)
    result: list[EditDecision] = []

    for d in decisions:
        merged = False
        for i, existing in enumerate(result):
            overlap_start = max(d.start, existing.start)
            overlap_end = min(d.end, existing.end)
            overlap_dur = max(0, overlap_end - overlap_start)

            shorter_dur = min(d.end - d.start, existing.end - existing.start)
            if shorter_dur > 0 and overlap_dur / shorter_dur > overlap_threshold:
                # These overlap significantly; keep the higher confidence one
                if d.confidence > existing.confidence:
                    result[i] = d
                merged = True
                break

        if not merged:
            result.append(d)

    return result
