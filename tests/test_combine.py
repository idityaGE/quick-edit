"""
Tests for src/analyze/combine.py
"""

from __future__ import annotations

import numpy as np
import pytest

from quickedit.analyze.combine import (
    DetectionArrays,
    combine_and,
    combine_not,
    combine_or,
    combine_xor,
    evaluate_expression,
)


class TestCombineOr:
    """Tests for the combine_or() function."""

    def test_combine_or_basic(self):
        """OR of two arrays."""
        a = np.array([True, False, True, False], dtype=bool)
        b = np.array([False, True, True, False], dtype=bool)

        result = combine_or(a, b)

        expected = np.array([True, True, True, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_or_multiple_arrays(self):
        """OR of more than two arrays."""
        a = np.array([True, False, False, False], dtype=bool)
        b = np.array([False, True, False, False], dtype=bool)
        c = np.array([False, False, True, False], dtype=bool)

        result = combine_or(a, b, c)

        expected = np.array([True, True, True, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_or_all_false(self):
        """OR of all-False arrays."""
        a = np.zeros(5, dtype=bool)
        b = np.zeros(5, dtype=bool)

        result = combine_or(a, b)

        np.testing.assert_array_equal(result, np.zeros(5, dtype=bool))

    def test_combine_or_all_true(self):
        """OR with all-True array."""
        a = np.ones(5, dtype=bool)
        b = np.zeros(5, dtype=bool)

        result = combine_or(a, b)

        np.testing.assert_array_equal(result, np.ones(5, dtype=bool))


class TestCombineAnd:
    """Tests for the combine_and() function."""

    def test_combine_and_basic(self):
        """AND of two arrays."""
        a = np.array([True, False, True, False], dtype=bool)
        b = np.array([True, True, False, False], dtype=bool)

        result = combine_and(a, b)

        expected = np.array([True, False, False, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_and_multiple_arrays(self):
        """AND of more than two arrays."""
        a = np.array([True, True, True, True], dtype=bool)
        b = np.array([True, True, False, False], dtype=bool)
        c = np.array([True, False, True, False], dtype=bool)

        result = combine_and(a, b, c)

        expected = np.array([True, False, False, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_and_with_false(self):
        """AND with all-False array returns all False."""
        a = np.ones(5, dtype=bool)
        b = np.zeros(5, dtype=bool)

        result = combine_and(a, b)

        np.testing.assert_array_equal(result, np.zeros(5, dtype=bool))


class TestCombineNot:
    """Tests for the combine_not() function."""

    def test_combine_not_basic(self):
        """NOT inverts array."""
        a = np.array([True, False, True, False], dtype=bool)

        result = combine_not(a)

        expected = np.array([False, True, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_not_all_true(self):
        """NOT of all-True array."""
        a = np.ones(5, dtype=bool)

        result = combine_not(a)

        np.testing.assert_array_equal(result, np.zeros(5, dtype=bool))

    def test_combine_not_all_false(self):
        """NOT of all-False array."""
        a = np.zeros(5, dtype=bool)

        result = combine_not(a)

        np.testing.assert_array_equal(result, np.ones(5, dtype=bool))


class TestCombineXor:
    """Tests for the combine_xor() function."""

    def test_combine_xor_basic(self):
        """XOR of two arrays."""
        a = np.array([True, False, True, False], dtype=bool)
        b = np.array([True, True, False, False], dtype=bool)

        result = combine_xor(a, b)

        # XOR: True^True=False, False^True=True, True^False=True, False^False=False
        expected = np.array([False, True, True, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_xor_multiple_arrays(self):
        """XOR of more than two arrays."""
        a = np.array([True, False, True, False], dtype=bool)
        b = np.array([True, True, False, False], dtype=bool)
        c = np.array([False, True, True, False], dtype=bool)

        result = combine_xor(a, b, c)

        # (a ^ b) ^ c
        # a^b = [False, True, True, False]
        # (a^b)^c = [False^False, True^True, True^True, False^False] = [False, False, False, False]
        expected = np.array([False, False, False, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)


class TestDifferentLengths:
    """Tests for handling arrays of different lengths."""

    def test_combine_different_lengths_or(self):
        """Arrays of different lengths handled correctly (uses min length)."""
        a = np.array([True, False, True, False, True], dtype=bool)
        b = np.array([False, True, True], dtype=bool)

        result = combine_or(a, b)

        # Should use length 3 (shorter array)
        expected = np.array([True, True, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_combine_different_lengths_and(self):
        """AND with different lengths uses min length."""
        a = np.array([True, True, True, False, True], dtype=bool)
        b = np.array([True, False, True], dtype=bool)

        result = combine_and(a, b)

        expected = np.array([True, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)


class TestEvaluateExpression:
    """Tests for the evaluate_expression() function."""

    @pytest.fixture
    def detections(self):
        """Sample detection arrays."""
        return DetectionArrays(
            arrays={
                "speech": np.array([True, True, False, False, True], dtype=bool),
                "motion": np.array([False, True, True, False, False], dtype=bool),
            },
            fps=30.0,
            total_frames=5,
        )

    def test_evaluate_expression_simple(self, detections):
        """Direct array name lookup."""
        result = evaluate_expression("speech", detections)

        expected = np.array([True, True, False, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_simple_with_whitespace(self, detections):
        """Array name with whitespace is stripped."""
        result = evaluate_expression("  speech  ", detections)

        expected = np.array([True, True, False, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_colon_format_or(self, detections):
        """'or:speech,motion' format."""
        result = evaluate_expression("or:speech,motion", detections)

        expected = np.array([True, True, True, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_colon_format_and(self, detections):
        """'and:speech,motion' format."""
        result = evaluate_expression("and:speech,motion", detections)

        expected = np.array([False, True, False, False, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_colon_format_xor(self, detections):
        """'xor:speech,motion' format."""
        result = evaluate_expression("xor:speech,motion", detections)

        # speech ^ motion = [True^False, True^True, False^True, False^False, True^False]
        #                 = [True, False, True, False, True]
        expected = np.array([True, False, True, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_colon_format_not(self, detections):
        """'not:speech' format."""
        result = evaluate_expression("not:speech", detections)

        expected = np.array([False, False, True, True, False], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_list_format(self, detections):
        """['or', 'speech', 'motion'] format."""
        result = evaluate_expression(["or", "speech", "motion"], detections)

        expected = np.array([True, True, True, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_nested(self, detections):
        """Nested expressions like ['or', 'speech', ['not', 'motion']]."""
        result = evaluate_expression(["or", "speech", ["not", "motion"]], detections)

        # speech OR (NOT motion)
        # speech = [True, True, False, False, True]
        # motion = [False, True, True, False, False]
        # NOT motion = [True, False, False, True, True]
        # speech OR (NOT motion) = [True, True, False, True, True]
        expected = np.array([True, True, False, True, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_complex_nested(self, detections):
        """Complex nested expression."""
        # ['and', ['or', 'speech', 'motion'], ['not', 'motion']]
        result = evaluate_expression(
            ["and", ["or", "speech", "motion"], ["not", "motion"]], detections
        )

        # (speech OR motion) AND (NOT motion)
        # speech OR motion = [True, True, True, False, True]
        # NOT motion = [True, False, False, True, True]
        # AND = [True, False, False, False, True]
        expected = np.array([True, False, False, False, True], dtype=bool)
        np.testing.assert_array_equal(result, expected)

    def test_evaluate_expression_unknown_array(self, detections):
        """Raises KeyError for unknown array name."""
        with pytest.raises(KeyError, match="Unknown detection array 'unknown'"):
            evaluate_expression("unknown", detections)

    def test_evaluate_expression_unknown_op(self, detections):
        """Raises ValueError for unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation: nand"):
            evaluate_expression("nand:speech,motion", detections)

    def test_evaluate_expression_not_wrong_operands(self, detections):
        """NOT with multiple operands raises ValueError."""
        with pytest.raises(ValueError, match="'not' takes exactly one operand"):
            evaluate_expression("not:speech,motion", detections)

    def test_evaluate_expression_empty_list(self, detections):
        """Empty list raises ValueError."""
        with pytest.raises(ValueError, match="Empty expression"):
            evaluate_expression([], detections)

    def test_evaluate_expression_invalid_type(self, detections):
        """Invalid expression type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid expression type"):
            evaluate_expression(123, detections)


class TestDetectionArrays:
    """Tests for the DetectionArrays class."""

    def test_get_existing_array(self):
        """Get returns existing array."""
        arrays = DetectionArrays(
            arrays={"speech": np.array([True, False], dtype=bool)},
            fps=30.0,
            total_frames=2,
        )

        result = arrays.get("speech")

        np.testing.assert_array_equal(result, [True, False])

    def test_get_unknown_array(self):
        """Get raises KeyError for unknown array."""
        arrays = DetectionArrays(
            arrays={"speech": np.array([True, False], dtype=bool)},
            fps=30.0,
            total_frames=2,
        )

        with pytest.raises(KeyError, match="Unknown detection array 'motion'"):
            arrays.get("motion")

    def test_add_same_length(self):
        """Add array with same length."""
        arrays = DetectionArrays(
            arrays={},
            fps=30.0,
            total_frames=3,
        )

        arrays.add("speech", np.array([True, False, True], dtype=bool))

        np.testing.assert_array_equal(arrays.get("speech"), [True, False, True])

    def test_add_shorter_array_pads(self):
        """Add shorter array pads with False."""
        arrays = DetectionArrays(
            arrays={},
            fps=30.0,
            total_frames=5,
        )

        arrays.add("speech", np.array([True, True], dtype=bool))

        expected = np.array([True, True, False, False, False], dtype=bool)
        np.testing.assert_array_equal(arrays.get("speech"), expected)

    def test_add_longer_array_truncates(self):
        """Add longer array truncates."""
        arrays = DetectionArrays(
            arrays={},
            fps=30.0,
            total_frames=3,
        )

        arrays.add("speech", np.array([True, True, True, True, True], dtype=bool))

        expected = np.array([True, True, True], dtype=bool)
        np.testing.assert_array_equal(arrays.get("speech"), expected)
