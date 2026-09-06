"""Pure-helper tests for scripts.analysis.verify_brief_bias.

Target: confirm the verdict synthesis (PASS / FAIL) reads the
brief_bias coverage signal correctly. DB pull is exercised at
integration runtime — these tests inject DataFrames directly.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scripts.analysis.verify_brief_bias import compute_coverage, render_report


def _alerts(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_compute_coverage_empty():
    out = compute_coverage(_alerts([]))
    assert out["n_buckets"] == 0
    assert out["n_alerts"] == 0
    assert out["buckets_with_null"] == []


def test_compute_coverage_all_populated():
    df = _alerts([
        {"alert_date": date(2026, 5, 12), "ticker": "SPY", "brief_bias": "bullish"},
        {"alert_date": date(2026, 5, 12), "ticker": "SPY", "brief_bias": "bullish"},
        {"alert_date": date(2026, 5, 12), "ticker": "IWM", "brief_bias": "mixed"},
        {"alert_date": date(2026, 5, 13), "ticker": "QQQ", "brief_bias": "bearish"},
    ])
    out = compute_coverage(df)
    assert out["n_buckets"] == 3  # (5/12,SPY), (5/12,IWM), (5/13,QQQ)
    assert out["n_buckets_complete"] == 3
    assert out["n_buckets_with_null"] == 0
    assert out["buckets_with_null"] == []
    assert out["n_alerts"] == 4
    assert out["n_alerts_with_bias"] == 4


def test_compute_coverage_with_nulls_flags_buckets():
    df = _alerts([
        {"alert_date": date(2026, 5, 12), "ticker": "SPY", "brief_bias": "bullish"},
        {"alert_date": date(2026, 5, 12), "ticker": "SPY", "brief_bias": None},
        {"alert_date": date(2026, 5, 12), "ticker": "IWM", "brief_bias": None},
        {"alert_date": date(2026, 5, 13), "ticker": "QQQ", "brief_bias": "bearish"},
    ])
    out = compute_coverage(df)
    assert out["n_buckets"] == 3
    assert out["n_buckets_complete"] == 1  # only (5/13,QQQ)
    assert out["n_buckets_with_null"] == 2
    null_buckets = {(b["date"], b["ticker"]) for b in out["buckets_with_null"]}
    assert ("2026-05-12", "SPY") in null_buckets
    assert ("2026-05-12", "IWM") in null_buckets


def test_render_report_pass():
    df = _alerts([
        {"alert_date": date(2026, 5, 12), "ticker": "SPY", "brief_bias": "bullish"},
        {"alert_date": date(2026, 5, 12), "ticker": "IWM", "brief_bias": "mixed"},
    ])
    out = compute_coverage(df)
    report = render_report(
        out, since=date(2026, 5, 12), tickers=["SPY", "IWM", "QQQ"]
    )
    assert "Verdict — ✅ PASS" in report
    assert "Buckets with NULL" not in report


def test_render_report_fail_lists_offenders():
    df = _alerts([
        {"alert_date": date(2026, 5, 12), "ticker": "SPY", "brief_bias": None},
    ])
    out = compute_coverage(df)
    report = render_report(
        out, since=date(2026, 5, 12), tickers=["SPY"]
    )
    assert "Verdict — ❌ FAIL" in report
    assert "2026-05-12" in report
    assert "| SPY |" in report


def test_render_report_empty_window():
    out = compute_coverage(_alerts([]))
    report = render_report(
        out, since=date(2026, 5, 12), tickers=["SPY"]
    )
    assert "No alerts found in window" in report
