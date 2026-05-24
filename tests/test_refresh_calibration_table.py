"""Hermetic tests for scripts.refresh_calibration_table.

No DB. Validates the deterministic markdown render + anchor-based
section replacement. Closes issue #251 doc auto-refresh.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts import refresh_calibration_table as rct


def _row(ticker, **overrides):
    base = {
        "ticker": ticker,
        "calibration_date": date.today(),
        "rsi_p10": 35.0,
        "rsi_p50": 50.5,
        "rsi_p90": 65.0,
        "n_bars_used": 33000,
        "lookback_days": 60,
    }
    base.update(overrides)
    return base


def test_build_markdown_with_three_tickers():
    out = rct._build_markdown([_row("IWM"), _row("QQQ"), _row("SPY")])
    assert "| IWM" in out and "| QQQ" in out and "| SPY" in out
    assert "(35.0, 50.5)" in out  # CALL range
    assert "(50.5, 65.0)" in out  # PUT range
    assert "| A |" in out
    assert "<!-- BEGIN" not in out  # markdown is anchor-free


def test_build_markdown_empty_falls_back_to_universal():
    out = rct._build_markdown([])
    assert "no rows in `ticker_calibration`" in out
    assert "Tier-B universal" in out
    assert str(rct.PUT_RSI_RANGE) in out
    assert str(rct.CALL_RSI_RANGE) in out


def test_build_markdown_marks_stale_rows_as_tier_b():
    stale = _row("OLD", calibration_date=date.today() - timedelta(days=200))
    out = rct._build_markdown([stale])
    assert "B (stale)" in out
    assert "Tier-B fallback" in out


def test_build_markdown_handles_nan_percentile():
    """A NaN value in a percentile should produce a Tier-B fallback for
    that side, mirroring lib.strategies.calibration._is_usable_number."""
    import math
    bad = _row("X", rsi_p50=math.nan)
    out = rct._build_markdown([bad])
    # rsi_p50 is in BOTH ranges, so both fall back
    assert "Tier-B fallback" in out


def test_replace_section_swaps_content_between_anchors():
    doc = (
        "intro\n"
        "<!-- BEGIN ticker_calibration_resolved_values -->\n"
        "stale content\n"
        "<!-- END ticker_calibration_resolved_values -->\n"
        "outro\n"
    )
    new_section = "fresh content\n"
    out = rct._replace_section(doc, new_section)
    assert "intro\n" in out
    assert "outro\n" in out
    assert "stale content" not in out
    assert "fresh content" in out
    # Anchors must be preserved
    assert rct.BEGIN_MARK in out
    assert rct.END_MARK in out


def test_replace_section_raises_on_missing_anchors():
    doc = "no anchors here\n"
    with pytest.raises(SystemExit):
        rct._replace_section(doc, "new")


def test_replace_section_idempotent_on_same_content():
    """Running twice with the same source rows yields the same doc — no
    spurious diff."""
    rows = [_row("SPY")]
    section = rct._build_markdown(rows)
    doc = (
        f"head\n{rct.BEGIN_MARK}\nstale\n{rct.END_MARK}\ntail\n"
    )
    pass1 = rct._replace_section(doc, section)
    pass2 = rct._replace_section(pass1, section)
    assert pass1 == pass2


def test_is_usable_rejects_nan_inf_none():
    import math
    assert rct._is_usable(50.0)
    assert rct._is_usable(0.0)
    assert not rct._is_usable(None)
    assert not rct._is_usable(math.nan)
    assert not rct._is_usable(math.inf)
    assert not rct._is_usable(-math.inf)
    assert not rct._is_usable("hello")
