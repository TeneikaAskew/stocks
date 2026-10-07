"""Immutable contract for the isolated EXPLOSIVE-vs-rest experiment."""
from __future__ import annotations
from dataclasses import dataclass

BINARY_LABEL = "is_explosive"
RESEARCH_ARTIFACT_ROOT = "magnitude-binary-research/v1"

@dataclass(frozen=True)
class Utility:
    """Pre-declared value of an alert, in arbitrary utility units."""
    true_positive: float = 5.0
    false_positive: float = -1.0
    false_negative: float = 0.0
    true_negative: float = 0.0

UTILITY = Utility()
VALIDATION_FRACTION = 0.20
TEST_FRACTION = 0.20
MIN_PARTITION_ROWS = 20
WEIGHT_CAP = 8.0
FOCAL_GAMMA = 2.0
RANDOM_STATE = 42
