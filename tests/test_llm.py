"""
Tests for src/edit/llm.py (response parsing only - no API calls)
"""

from __future__ import annotations

import json

from quickedit.edit.edl import CutReason, EditDecision
from quickedit.edit.llm import (
    MAX_RESPONSE_SIZE,
    LLMProvider,
    SilentSegmentInfo,
    _build_user_message,
    _chunk_words,
    _deduplicate_decisions,
    _detect_provider,
    _parse_decision_item,
    _parse_llm_response,
)


class TestParseLLMResponse:
    """Tests for the _parse_llm_response() function."""

    def test_parse_llm_response_valid_json(self):
        """Parses valid JSON response."""
        response = json.dumps(
            {
                "decisions": [
                    {
                        "start_time": 1.0,
                        "end_time": 2.5,
                        "reason": "filler_word",
                        "confidence": 0.95,
                        "transcript": "um uh",
                        "note": "Filler words",
                    }
                ]
            }
        )

        result = _parse_llm_response(response)

        assert len(result) == 1
        assert result[0].start == 1.0
        assert result[0].end == 2.5
        assert result[0].reason == CutReason.FILLER_WORD
        assert result[0].confidence == 0.95
        assert result[0].transcript == "um uh"
        assert result[0].note == "Filler words"

    def test_parse_llm_response_markdown_block(self):
        """Extracts JSON from ```json block when it starts the response."""
        # Note: Current implementation only handles markdown when response STARTS with ```
        response = """```json
{
  "decisions": [
    {
      "start_time": 5.0,
      "end_time": 7.0,
      "reason": "false_start",
      "confidence": 0.8,
      "transcript": "so um wait",
      "note": "Speaker restarts"
    }
  ]
}
```"""

        result = _parse_llm_response(response)

        assert len(result) == 1
        assert result[0].start == 5.0
        assert result[0].reason == CutReason.FALSE_START

    def test_parse_llm_response_empty_decisions(self):
        """Handles empty decisions array."""
        response = json.dumps({"decisions": []})

        result = _parse_llm_response(response)

        assert result == []

    def test_parse_llm_response_invalid_json(self):
        """Returns empty list on parse failure."""
        response = "This is not valid JSON at all"

        result = _parse_llm_response(response)

        assert result == []

    def test_parse_llm_response_unknown_reason(self):
        """Falls back to CutReason.CUSTOM for unknown reasons."""
        response = json.dumps(
            {
                "decisions": [
                    {
                        "start_time": 1.0,
                        "end_time": 2.0,
                        "reason": "some_unknown_reason",
                        "confidence": 0.7,
                        "transcript": "test",
                        "note": "",
                    }
                ]
            }
        )

        result = _parse_llm_response(response)

        assert len(result) == 1
        assert result[0].reason == CutReason.CUSTOM

    def test_parse_llm_response_all_reasons(self):
        """Parses all known reason types."""
        decisions_data = []
        for i, reason in enumerate(
            [
                "silence",
                "filler_word",
                "false_start",
                "repetition",
                "tangent",
                "dead_air",
                "custom",
            ]
        ):
            decisions_data.append(
                {
                    "start_time": float(i),
                    "end_time": float(i + 0.5),
                    "reason": reason,
                    "confidence": 0.9,
                    "transcript": f"test {reason}",
                    "note": "",
                }
            )

        response = json.dumps({"decisions": decisions_data})
        result = _parse_llm_response(response)

        assert len(result) == 7
        assert result[0].reason == CutReason.SILENCE
        assert result[1].reason == CutReason.FILLER_WORD
        assert result[2].reason == CutReason.FALSE_START
        assert result[3].reason == CutReason.REPETITION
        assert result[4].reason == CutReason.TANGENT
        assert result[5].reason == CutReason.DEAD_AIR
        assert result[6].reason == CutReason.CUSTOM

    def test_parse_llm_response_default_values(self):
        """Uses default values for optional fields."""
        response = json.dumps(
            {
                "decisions": [
                    {
                        "start_time": 1.0,
                        "end_time": 2.0,
                        # Missing: reason, confidence, transcript, note
                    }
                ]
            }
        )

        result = _parse_llm_response(response)

        assert len(result) == 1
        assert result[0].reason == CutReason.CUSTOM  # default for empty/missing
        assert result[0].confidence == 0.8  # default
        assert result[0].transcript == ""  # default
        assert result[0].note == ""  # default

    def test_parse_llm_response_multiple_decisions(self):
        """Parses multiple decisions."""
        response = json.dumps(
            {
                "decisions": [
                    {
                        "start_time": 1.0,
                        "end_time": 2.0,
                        "reason": "filler_word",
                        "confidence": 0.9,
                        "transcript": "um",
                        "note": "",
                    },
                    {
                        "start_time": 5.0,
                        "end_time": 6.0,
                        "reason": "false_start",
                        "confidence": 0.8,
                        "transcript": "wait",
                        "note": "",
                    },
                    {
                        "start_time": 10.0,
                        "end_time": 12.0,
                        "reason": "tangent",
                        "confidence": 0.7,
                        "transcript": "anyway",
                        "note": "",
                    },
                ]
            }
        )

        result = _parse_llm_response(response)

        assert len(result) == 3

    def test_parse_llm_response_truncates_large_response(self):
        """Large responses are truncated before parsing."""
        # Create a response larger than MAX_RESPONSE_SIZE
        # The truncation will likely break JSON parsing, so we expect empty list
        large_response = "x" * (MAX_RESPONSE_SIZE + 1000)

        result = _parse_llm_response(large_response)

        # Should return empty (truncated response won't be valid JSON)
        assert result == []


class TestParseDecisionItem:
    """Tests for the _parse_decision_item() validation function."""

    def test_parse_valid_decision(self):
        """Valid decision is parsed correctly."""
        item = {
            "start_time": 1.0,
            "end_time": 2.0,
            "reason": "filler_word",
            "confidence": 0.9,
            "transcript": "um",
            "note": "filler",
        }

        result = _parse_decision_item(item)

        assert result is not None
        assert result.start == 1.0
        assert result.end == 2.0
        assert result.confidence == 0.9

    def test_parse_decision_invalid_start_time(self):
        """Negative start_time returns None."""
        item = {
            "start_time": -1.0,
            "end_time": 2.0,
            "reason": "filler_word",
            "confidence": 0.9,
        }

        result = _parse_decision_item(item)

        assert result is None

    def test_parse_decision_invalid_time_order(self):
        """end_time <= start_time returns None."""
        item = {
            "start_time": 3.0,
            "end_time": 2.0,  # Before start
            "reason": "filler_word",
            "confidence": 0.9,
        }

        result = _parse_decision_item(item)

        assert result is None

    def test_parse_decision_clamps_confidence(self):
        """Out-of-range confidence is clamped."""
        item = {
            "start_time": 1.0,
            "end_time": 2.0,
            "reason": "filler_word",
            "confidence": 1.5,  # Too high
        }

        result = _parse_decision_item(item)

        assert result is not None
        assert result.confidence == 1.0  # Clamped to max

    def test_parse_decision_handles_missing_fields(self):
        """Missing fields use defaults."""
        item = {
            "start_time": 1.0,
            "end_time": 2.0,
        }

        result = _parse_decision_item(item)

        assert result is not None
        assert result.confidence == 0.8  # default
        assert result.transcript == ""
        assert result.note == ""


class TestDeduplicateDecisions:
    """Tests for the _deduplicate_decisions() function."""

    def test_deduplicate_decisions_no_overlap(self):
        """Non-overlapping decisions kept."""
        decisions = [
            EditDecision(
                start=1.0,
                end=2.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.9,
            ),
            EditDecision(
                start=5.0,
                end=6.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.8,
            ),
            EditDecision(
                start=10.0,
                end=11.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.7,
            ),
        ]

        result = _deduplicate_decisions(decisions)

        assert len(result) == 3

    def test_deduplicate_decisions_overlap(self):
        """Overlapping decisions merged by confidence when overlap > 50% of shorter duration."""
        # Decisions with significant overlap (>50% of shorter)
        # First: 1.0-2.0 (1.0s duration)
        # Second: 1.3-2.3 (1.0s duration), overlap = 0.7s = 70% of either
        decisions = [
            EditDecision(
                start=1.0,
                end=2.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.7,
            ),
            EditDecision(
                start=1.3,
                end=2.3,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.9,
            ),
        ]

        result = _deduplicate_decisions(decisions)

        # Should keep the higher confidence one
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_deduplicate_decisions_exact_match(self):
        """Exact same time range keeps higher confidence."""
        decisions = [
            EditDecision(
                start=1.0,
                end=2.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.5,
            ),
            EditDecision(
                start=1.0,
                end=2.0,
                action="remove",
                reason=CutReason.FALSE_START,
                confidence=0.8,
            ),
        ]

        result = _deduplicate_decisions(decisions)

        assert len(result) == 1
        assert result[0].confidence == 0.8

    def test_deduplicate_decisions_partial_overlap_under_threshold(self):
        """Partial overlap under threshold keeps both."""
        # Overlap must be > 50% of shorter duration
        decisions = [
            EditDecision(
                start=1.0,
                end=5.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.9,
            ),  # 4s duration
            EditDecision(
                start=4.5,
                end=6.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.8,
            ),  # 1.5s duration
        ]

        result = _deduplicate_decisions(decisions)

        # Overlap is 0.5s, shorter duration is 1.5s
        # 0.5/1.5 = 0.33, which is < 0.5 threshold
        assert len(result) == 2

    def test_deduplicate_decisions_empty_list(self):
        """Empty list returns empty."""
        result = _deduplicate_decisions([])

        assert result == []

    def test_deduplicate_decisions_single_item(self):
        """Single item returns as-is."""
        decisions = [
            EditDecision(
                start=1.0,
                end=2.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.9,
            ),
        ]

        result = _deduplicate_decisions(decisions)

        assert len(result) == 1

    def test_deduplicate_decisions_sorts_by_start(self):
        """Result is sorted by start time."""
        decisions = [
            EditDecision(
                start=10.0,
                end=11.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.9,
            ),
            EditDecision(
                start=1.0,
                end=2.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.8,
            ),
            EditDecision(
                start=5.0,
                end=6.0,
                action="remove",
                reason=CutReason.FILLER_WORD,
                confidence=0.7,
            ),
        ]

        result = _deduplicate_decisions(decisions)

        assert result[0].start == 1.0
        assert result[1].start == 5.0
        assert result[2].start == 10.0


class TestChunkWords:
    """Tests for the _chunk_words() function."""

    def test_chunk_words_small_transcript(self):
        """Single chunk for short transcripts."""
        words = [
            {"word": f"word{i}", "start": i * 0.1, "end": (i + 1) * 0.1}
            for i in range(10)
        ]

        result = _chunk_words(words, chunk_size=100, overlap=20)

        assert len(result) == 1
        assert len(result[0]) == 10

    def test_chunk_words_large_transcript(self):
        """Multiple overlapping chunks."""
        words = [
            {"word": f"word{i}", "start": i * 0.1, "end": (i + 1) * 0.1}
            for i in range(100)
        ]

        result = _chunk_words(words, chunk_size=30, overlap=10)

        # Should have multiple chunks
        assert len(result) > 1

        # Each chunk should have chunk_size or fewer words
        for chunk in result:
            assert len(chunk) <= 30

    def test_chunk_words_overlap(self):
        """Chunks overlap correctly."""
        words = [{"word": f"w{i}", "start": i, "end": i + 1} for i in range(50)]

        result = _chunk_words(words, chunk_size=20, overlap=5)

        # Verify overlap: end of chunk N should overlap with start of chunk N+1
        if len(result) > 1:
            chunk1_end = result[0][-5:]  # last 5 words of first chunk
            chunk2_start = result[1][:5]  # first 5 words of second chunk

            # These should be the same words
            assert chunk1_end == chunk2_start

    def test_chunk_words_exact_chunk_size(self):
        """Transcript exactly chunk_size returns single chunk."""
        words = [{"word": f"w{i}", "start": i, "end": i + 1} for i in range(30)]

        result = _chunk_words(words, chunk_size=30, overlap=5)

        assert len(result) == 1

    def test_chunk_words_empty(self):
        """Empty word list returns single empty chunk."""
        result = _chunk_words([], chunk_size=30, overlap=5)

        assert len(result) == 1
        assert result[0] == []


class TestBuildUserMessage:
    """Tests for the _build_user_message() function."""

    def test_build_user_message_basic(self):
        """Builds message with transcript."""
        words_data = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
        ]

        result = _build_user_message(words_data, "Test prompt", "")

        assert "Test prompt" in result
        assert "[0.00-0.50] Hello" in result
        assert "[0.50-1.00] world" in result
        assert '"decisions"' in result  # JSON format instruction

    def test_build_user_message_with_silent_info(self):
        """Includes silent segment info."""
        words_data = [
            {"word": "test", "start": 0.0, "end": 0.5},
        ]
        silent_info = (
            "Silent segment classifications:\n  [1.0s - 2.0s] visual_activity (KEEP)"
        )

        result = _build_user_message(words_data, "Test prompt", silent_info)

        assert "Silent segment classifications" in result
        assert "visual_activity (KEEP)" in result

    def test_build_user_message_empty_transcript(self):
        """Handles empty transcript."""
        result = _build_user_message([], "Test prompt", "")

        assert "Test prompt" in result
        assert "Transcript (with word-level timestamps):" in result


class TestSilentSegmentInfo:
    """Tests for the SilentSegmentInfo dataclass."""

    def test_silent_segment_info_creation(self):
        """Creates segment info correctly."""
        seg = SilentSegmentInfo(
            start=5.0,
            end=10.0,
            has_visual_activity=True,
            motion_score=0.15,
        )

        assert seg.start == 5.0
        assert seg.end == 10.0
        assert seg.has_visual_activity is True
        assert seg.motion_score == 0.15


class TestDetectProvider:
    """Tests for _detect_provider() function."""

    def test_detect_provider_anthropic_claude(self):
        """Detects Anthropic for claude-* models."""
        assert _detect_provider("claude-sonnet-4-20250514") == LLMProvider.ANTHROPIC
        assert _detect_provider("claude-3-opus-20240229") == LLMProvider.ANTHROPIC
        assert _detect_provider("claude-3-haiku-20240307") == LLMProvider.ANTHROPIC

    def test_detect_provider_gemini(self):
        """Detects Gemini for gemini-* models."""
        assert _detect_provider("gemini-2.0-flash") == LLMProvider.GEMINI
        assert _detect_provider("gemini-1.5-pro") == LLMProvider.GEMINI
        assert _detect_provider("gemini-1.5-flash") == LLMProvider.GEMINI

    def test_detect_provider_case_insensitive(self):
        """Provider detection is case insensitive."""
        assert _detect_provider("GEMINI-2.0-flash") == LLMProvider.GEMINI
        assert _detect_provider("Gemini-1.5-pro") == LLMProvider.GEMINI
        assert _detect_provider("CLAUDE-sonnet-4") == LLMProvider.ANTHROPIC

    def test_detect_provider_default_anthropic(self):
        """Unknown models default to Anthropic."""
        assert _detect_provider("unknown-model") == LLMProvider.ANTHROPIC
        assert _detect_provider("gpt-4") == LLMProvider.ANTHROPIC
