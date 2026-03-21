"""
LLM-based semantic analysis of video transcripts.

Uses Claude API to analyze the transcript and identify segments to remove:
filler words, false starts, repetitions, tangents, etc.

Supports custom prompts for domain-specific editing (e.g., DSA tutorials,
cooking videos, vlogs).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic

from src.analyze.transcribe import TranscriptionResult, Word
from src.edit.edl import EditDecision, CutReason

logger = logging.getLogger(__name__)

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


def analyze_with_llm(
    transcript: TranscriptionResult,
    silent_segments: list[SilentSegmentInfo] | None = None,
    custom_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[EditDecision]:
    """
    Send transcript to Claude for semantic analysis.

    Args:
        transcript: Word-level transcription.
        silent_segments: Classifications of silent periods (visual activity or not).
        custom_prompt: Custom editing instructions. If None, uses DEFAULT_EDIT_PROMPT.
        api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        model: Claude model to use.

    Returns:
        List of EditDecision objects for segments to remove.
    """
    client = Anthropic(api_key=api_key)
    edit_prompt = custom_prompt or DEFAULT_EDIT_PROMPT

    # Build word list with timestamps
    words_data = transcript.to_transcript_with_timestamps()

    # Build silent segment info
    silent_info = ""
    if silent_segments:
        silent_lines = []
        for seg in silent_segments:
            label = "visual_activity (KEEP)" if seg.has_visual_activity else "dead_air"
            silent_lines.append(
                f"  [{seg.start:.1f}s - {seg.end:.1f}s] {label} "
                f"(motion: {seg.motion_score:.3f})"
            )
        silent_info = "Silent segment classifications:\n" + "\n".join(silent_lines)

    # Process in chunks if transcript is long
    all_decisions: list[EditDecision] = []
    chunks = _chunk_words(words_data, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS)

    for i, chunk in enumerate(chunks):
        logger.info(
            f"Processing LLM chunk {i + 1}/{len(chunks)} "
            f"({len(chunk)} words, "
            f"{chunk[0]['start']:.1f}s - {chunk[-1]['end']:.1f}s)"
        )

        user_message = _build_user_message(chunk, edit_prompt, silent_info)

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        # Parse response
        response_text = response.content[0].text
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


def _parse_llm_response(response_text: str) -> list[EditDecision]:
    """Parse the LLM's JSON response into EditDecision objects."""
    # Try to extract JSON from the response
    text = response_text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM response as JSON: {text[:200]}...")
        return []

    decisions = []
    for item in data.get("decisions", []):
        reason_str = item.get("reason", "custom")
        try:
            reason = CutReason(reason_str)
        except ValueError:
            reason = CutReason.CUSTOM

        decision = EditDecision(
            start=float(item["start_time"]),
            end=float(item["end_time"]),
            action="remove",
            reason=reason,
            confidence=float(item.get("confidence", 0.8)),
            transcript=item.get("transcript", ""),
            note=item.get("note", ""),
        )
        decisions.append(decision)

    return decisions


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
