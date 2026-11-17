"""A print isolated from its own minute, in stored 1-minute bars (FEAT-DATA-001).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 1).

``print_geometry`` is the one place a bar's wick is measured against the bars
around it. ``isolated_prints`` calls it, then applies the scale and the
threshold. Pure: pandas and numpy only, no I/O, no clock. Neither changes a
bar or fills a value: a bar that cannot be measured is not judged and holds
NaN, and a NaN price in the input raises.

Every parameter is read from ``PARAMS``. A changed value is a new
``RULE_VERSION``, and the whole history is judged again under it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RULE_VERSION = "isolated-print-v1"
PARAMS = {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0, "floor_bp": 50.0}

_BP = 10_000.0  # basis points in 1

_PRICE_COLUMNS = ("open", "high", "low", "close")
_GEOMETRY_COLUMNS = (
    "ts", "reference_high", "excess_high", "reference_low", "excess_low", "judged",
)
_FLAG_COLUMNS = (
    "ts", "side", "print_kind", "observed", "reference", "bound", "scale", "excess_bp",
)


def _checked_prices(bars: pd.DataFrame) -> dict[str, np.ndarray]:
    """The four price columns as float arrays. Raises ValueError, naming the
    ts, when ts is not strictly increasing or a price is NaN."""
    ts = bars["ts"].reset_index(drop=True)
    step = ts.diff().iloc[1:]
    out_of_order = step <= pd.Timedelta(0)
    if out_of_order.any():
        at = ts[out_of_order.idxmax()]
        raise ValueError(f"ts is not strictly increasing at {at}")
    prices = {
        name: bars[name].to_numpy(dtype=float, na_value=np.nan) for name in _PRICE_COLUMNS
    }
    for name, values in prices.items():
        missing = np.isnan(values)
        if missing.any():
            at = ts[int(np.argmax(missing))]
            raise ValueError(f"{name} is NaN in the bar at {at}")
    return prices


def _shifted(values: np.ndarray, offset: int) -> np.ndarray:
    """values[i + offset] at position i, NaN where that bar is not in the input."""
    out = np.full(len(values), np.nan)
    if offset > 0:
        out[:-offset] = values[offset:]
    else:
        out[-offset:] = values[:offset]
    return out


def print_geometry(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per input bar, in input order: ts, reference_high, excess_high,
    reference_low, excess_low (price units, no threshold) and judged.
    NaN references and excesses where a bar is not judged.

    bars: one ticker's stored 1-minute bars, ts ascending, with open, high,
    low and close.

    Low side: the reference is the lowest open or close of the two bars on
    each side, together with whichever of the bar's own open and close is
    above its low; the excess is the reference minus the low. The high side
    mirrors it. A bar's own open or close is left out only when it is the
    extreme itself. A bar is judged when the input holds two bars on each
    side of it.
    """
    n = len(bars)
    if n == 0:
        out = pd.DataFrame({"ts": bars["ts"].reset_index(drop=True)})
        for name in _GEOMETRY_COLUMNS[1:-1]:
            out[name] = np.array([], dtype=float)
        out["judged"] = np.array([], dtype=bool)
        return out[list(_GEOMETRY_COLUMNS)]

    prices = _checked_prices(bars)
    o, h, lo, c = (prices[name] for name in _PRICE_COLUMNS)
    body_hi = np.maximum(o, c)
    body_lo = np.minimum(o, c)

    neighbours = PARAMS["neighbours"]
    position = np.arange(n)
    judged = (position >= neighbours) & (position < n - neighbours)

    reference_high = np.where(o < h, o, np.nan)
    reference_high = np.fmax(reference_high, np.where(c < h, c, np.nan))
    reference_low = np.where(o > lo, o, np.nan)
    reference_low = np.fmin(reference_low, np.where(c > lo, c, np.nan))
    for distance in range(1, neighbours + 1):
        for offset in (-distance, distance):
            reference_high = np.fmax(reference_high, _shifted(body_hi, offset))
            reference_low = np.fmin(reference_low, _shifted(body_lo, offset))
    reference_high = np.where(judged, reference_high, np.nan)
    reference_low = np.where(judged, reference_low, np.nan)

    return pd.DataFrame({
        "ts": bars["ts"].reset_index(drop=True),
        "reference_high": reference_high,
        "excess_high": h - reference_high,
        "reference_low": reference_low,
        "excess_low": reference_low - lo,
        "judged": judged,
    })


def isolated_prints(bars: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """bars: one ticker's stored 1-minute bars, ts ascending, with open, high,
    low, close. Returns (flags, judged).

    flags: one row per flagged (bar, side), ts ascending and the high side
    before the low side of one bar, with ts, side ('high' or 'low'),
    print_kind ('wick', 'open', 'close' or 'open_and_close'), observed (the
    stored high or low), reference, bound, scale and excess_bp. judged: one
    boolean per input bar, print_geometry's.

    The scale is the median of high - low over the scale_bars stored bars
    centred on the bar, fewer at the two ends of the input. The threshold is
    the larger of scale_multiple times the scale and floor_bp of the
    reference; the bound is the reference minus it (low) or plus it (high);
    a side is flagged when the bar is judged and its low is strictly below,
    or its high strictly above, the bound.
    """
    geometry = print_geometry(bars)
    judged = geometry["judged"].to_numpy(dtype=bool)
    if len(bars) == 0:
        flags = pd.DataFrame({"ts": geometry["ts"]})
        for name in ("side", "print_kind"):
            flags[name] = np.array([], dtype=object)
        for name in _FLAG_COLUMNS[3:]:
            flags[name] = np.array([], dtype=float)
        return flags[list(_FLAG_COLUMNS)], judged

    ts = geometry["ts"]
    o, h, lo, c = (bars[name].to_numpy(dtype=float) for name in _PRICE_COLUMNS)
    scale = (
        pd.Series(h - lo)
        .rolling(PARAMS["scale_bars"], center=True, min_periods=1)
        .median()
        .to_numpy()
    )

    sides = []
    for order, (side, observed, sign) in enumerate((("high", h, 1.0), ("low", lo, -1.0))):
        reference = geometry[f"reference_{side}"].to_numpy()
        excess = geometry[f"excess_{side}"].to_numpy()
        threshold = np.maximum(
            PARAMS["scale_multiple"] * scale, PARAMS["floor_bp"] / _BP * reference
        )
        bound = reference + sign * threshold
        # A bar that is not judged has a NaN bound, and no comparison with NaN holds.
        flagged = judged & (sign * (observed - bound) > 0)
        at_open = o == observed
        at_close = c == observed
        kind = np.select(
            [at_open & at_close, at_open, at_close],
            ["open_and_close", "open", "close"],
            default="wick",
        )
        sides.append(pd.DataFrame({
            "ts": ts[flagged],
            "side": side,
            "print_kind": kind[flagged],
            "observed": observed[flagged],
            "reference": reference[flagged],
            "bound": bound[flagged],
            "scale": scale[flagged],
            "excess_bp": excess[flagged] / reference[flagged] * _BP,
            "_order": order,
        }))
    flags = (
        pd.concat(sides)
        .sort_values(["ts", "_order"], kind="stable")
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    return flags[list(_FLAG_COLUMNS)], judged
