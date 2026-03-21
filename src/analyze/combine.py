"""
Combine multiple detection arrays using boolean logic.

Inspired by auto-editor's S-expression combinator system.
Supports: or, and, not, xor operations on per-frame bool arrays.

Example expressions:
    "(or speech motion)"          -- keep if speech OR visual activity
    "(and speech motion)"         -- keep only if both
    "(or speech (not motion))"    -- keep speech, also keep when screen is static
                                     (useful for facecam where motion = distracting)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np


class CombineOp(Enum):
    OR = "or"
    AND = "and"
    NOT = "not"
    XOR = "xor"


@dataclass
class DetectionArrays:
    """Collection of named detection arrays."""

    arrays: dict[str, np.ndarray]  # name -> bool array
    fps: float
    total_frames: int

    def get(self, name: str) -> np.ndarray:
        if name not in self.arrays:
            available = ", ".join(self.arrays.keys())
            raise KeyError(f"Unknown detection array '{name}'. Available: {available}")
        return self.arrays[name]

    def add(self, name: str, array: np.ndarray) -> None:
        # Ensure consistent length
        if len(array) != self.total_frames:
            # Resize to match (pad with False or truncate)
            if len(array) < self.total_frames:
                padded = np.zeros(self.total_frames, dtype=bool)
                padded[: len(array)] = array
                array = padded
            else:
                array = array[: self.total_frames]
        self.arrays[name] = array


def combine_or(*arrays: np.ndarray) -> np.ndarray:
    """Logical OR across arrays. Keep frame if ANY detector says keep."""
    min_len = min(len(a) for a in arrays)
    result = np.zeros(min_len, dtype=bool)
    for a in arrays:
        result |= a[:min_len]
    return result


def combine_and(*arrays: np.ndarray) -> np.ndarray:
    """Logical AND across arrays. Keep frame only if ALL detectors agree."""
    min_len = min(len(a) for a in arrays)
    result = np.ones(min_len, dtype=bool)
    for a in arrays:
        result &= a[:min_len]
    return result


def combine_not(array: np.ndarray) -> np.ndarray:
    """Invert detection array."""
    return ~array


def combine_xor(*arrays: np.ndarray) -> np.ndarray:
    """Logical XOR across arrays."""
    min_len = min(len(a) for a in arrays)
    result = np.zeros(min_len, dtype=bool)
    for a in arrays:
        result ^= a[:min_len]
    return result


def evaluate_expression(
    expr: str | list,
    detections: DetectionArrays,
) -> np.ndarray:
    """
    Evaluate a combination expression.

    Supports two formats:
    1. Simple string: "speech" -- returns the named array directly
    2. S-expression list: ["or", "speech", "motion"]
       or nested: ["or", "speech", ["not", "motion"]]

    For convenience, also accepts string expressions:
        "speech"                    -> direct lookup
        "or:speech,motion"          -> OR of speech and motion
        "and:speech,motion"         -> AND
    """
    if isinstance(expr, str):
        # Simple colon-separated format
        if ":" in expr:
            parts = expr.split(":", 1)
            op = parts[0].strip().lower()
            operands = [o.strip() for o in parts[1].split(",")]
            return _eval_op(op, operands, detections)
        else:
            return detections.get(expr.strip())

    if isinstance(expr, list):
        return _eval_list(expr, detections)

    raise ValueError(f"Invalid expression type: {type(expr)}")


def _eval_op(op: str, operands: list[str], detections: DetectionArrays) -> np.ndarray:
    """Evaluate a simple operation."""
    arrays = [detections.get(name) for name in operands]

    if op == "or":
        return combine_or(*arrays)
    elif op == "and":
        return combine_and(*arrays)
    elif op == "not":
        if len(arrays) != 1:
            raise ValueError("'not' takes exactly one operand")
        return combine_not(arrays[0])
    elif op == "xor":
        return combine_xor(*arrays)
    else:
        raise ValueError(f"Unknown operation: {op}")


def _eval_list(expr: list, detections: DetectionArrays) -> np.ndarray:
    """Evaluate a nested list expression."""
    if not expr:
        raise ValueError("Empty expression")

    op = expr[0]
    if not isinstance(op, str):
        raise ValueError(f"First element must be operation name, got: {type(op)}")

    operands = expr[1:]
    resolved = []
    for operand in operands:
        if isinstance(operand, str):
            resolved.append(detections.get(operand))
        elif isinstance(operand, list):
            resolved.append(_eval_list(operand, detections))
        else:
            raise ValueError(f"Invalid operand type: {type(operand)}")

    op = op.lower()
    if op == "or":
        return combine_or(*resolved)
    elif op == "and":
        return combine_and(*resolved)
    elif op == "not":
        if len(resolved) != 1:
            raise ValueError("'not' takes exactly one operand")
        return combine_not(resolved[0])
    elif op == "xor":
        return combine_xor(*resolved)
    else:
        raise ValueError(f"Unknown operation: {op}")


def default_combine(
    speech: np.ndarray,
    motion: np.ndarray,
) -> np.ndarray:
    """
    Default combination: keep frame if there's speech OR visual activity.

    This is the most common case for screen recordings where you want
    to keep both talking segments AND silent coding/writing segments.
    """
    return combine_or(speech, motion)
