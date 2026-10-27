"""Decode literal test inputs, never compute expected normalization results."""
import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd


CASES = json.loads(
    (Path(__file__).parent / "fixtures/catalyst_finite_nullable_numbers.json")
    .read_text(encoding="utf-8")
)


def input_value(case):
    kind = case["kind"]
    if kind == "null":
        return None
    if kind == "pandas_missing":
        return pd.NA
    if kind == "pandas_nat":
        return pd.NaT
    conversions = {
        "float_text": float,
        "decimal": Decimal,
        "numpy_boolean": np.bool_,
        "numpy_integer": np.int64,
        "numpy_float": np.float64,
    }
    if kind in conversions:
        return conversions[kind](case["value"])
    if kind in {"string", "boolean", "float", "list", "object"}:
        return case["value"]
    raise AssertionError("Unknown test-vector kind")
