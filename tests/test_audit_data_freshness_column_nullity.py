"""Tests for the column-nullity checks added to scripts/audit_data_freshness.py.

The 2026-06 ^VIX/gamma cascade went undetected for ~4 weeks because no
freshness check looked at column non-NULL rate — rows were writing on
schedule but `vix_close`, `total_gex`, `gamma_balance_price`, `total_vex`
were all NULL after upstream sources stalled. This module's checks close
that gap; these tests pin the contract so a future refactor can't
silently weaken the detection.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest


def _fake_distribution(rows: list[dict]) -> pd.DataFrame:
    """Build the (ticker, total, non_null) DataFrame shape that
    _query_column_nullity expects from query_to_dataframe."""
    return pd.DataFrame(rows)


def _patch_query(monkeypatch, df_or_exc):
    """Install a fake query_to_dataframe — same helper shape the
    existing test_audit_data_freshness suite uses."""
    from scripts import audit_data_freshness as mod

    def fake(sql, params=None):
        if isinstance(df_or_exc, BaseException):
            raise df_or_exc
        if callable(df_or_exc):
            return df_or_exc(sql)
        return df_or_exc.copy() if isinstance(df_or_exc, pd.DataFrame) else df_or_exc

    monkeypatch.setattr(mod, "query_to_dataframe", fake)


def test_healthy_column_emits_no_finding(monkeypatch):
    """When every checked column is at 100% non-NULL the function returns
    an empty list — silent on healthy state, same contract as
    _query_value_sanity."""
    from scripts.audit_data_freshness import _query_column_nullity
    df = _fake_distribution([
        {"ticker": "IWM", "total": 78, "non_null": 78},
        {"ticker": "SPY", "total": 78, "non_null": 78},
        {"ticker": "QQQ", "total": 78, "non_null": 78},
    ])
    _patch_query(monkeypatch, df)
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert out == []


def test_below_threshold_fires_stale(monkeypatch):
    """The cascade-signature shape: vix_close NULL on every bar →
    non-NULL rate is 0/N → MUST flag stale. Pinning this prevents a
    future change to the threshold from silently making the audit
    pass through the original bug."""
    from scripts.audit_data_freshness import _query_column_nullity
    df = _fake_distribution([
        {"ticker": "IWM", "total": 78, "non_null": 0},   # 0% — exactly the bug
    ])
    _patch_query(monkeypatch, df)
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    # One finding for every check x (IWM at 0%) — we have 5 checks declared
    assert len(out) > 0
    # Every finding must be stale, IWM, and carry a writer_job for routing
    for f in out:
        assert f.status == "stale"
        assert f.ticker == "IWM"
        assert f.writer_job in ("fetch-market-data", "strat-engine")
        assert "0/78" in (f.last_row_at or "")


def test_borderline_just_above_threshold_passes(monkeypatch):
    """A column at 95% non-NULL must NOT fire when the threshold is 90%.
    Sparse-but-legitimate columns shouldn't burn the operator with
    every-day pages."""
    from scripts.audit_data_freshness import _query_column_nullity
    df = _fake_distribution([
        {"ticker": "IWM", "total": 100, "non_null": 95},   # 95%
        {"ticker": "SPY", "total": 100, "non_null": 95},
        {"ticker": "QQQ", "total": 100, "non_null": 95},
    ])
    _patch_query(monkeypatch, df)
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert out == []


def test_borderline_just_below_threshold_fires(monkeypatch):
    """A column at 89% non-NULL crosses the 90% threshold — must fire.
    The non-strict comparison is intentional (>= threshold passes)."""
    from scripts.audit_data_freshness import _query_column_nullity
    df = _fake_distribution([
        {"ticker": "IWM", "total": 100, "non_null": 89},   # 89% — just under
    ])
    _patch_query(monkeypatch, df)
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    # 5 checks all fire on this one ticker since the same fake_df returns
    # for every query
    assert all(f.status == "stale" for f in out)
    assert all(f.ticker == "IWM" for f in out)


def test_per_ticker_isolation(monkeypatch):
    """IWM at 0%, SPY at 100% — only IWM fires. Avoids false-paging the
    healthy ticker because a sibling went bad."""
    from scripts.audit_data_freshness import _query_column_nullity
    df = _fake_distribution([
        {"ticker": "IWM", "total": 78, "non_null": 0},      # broken
        {"ticker": "SPY", "total": 78, "non_null": 78},     # healthy
        {"ticker": "QQQ", "total": 78, "non_null": 78},     # healthy
    ])
    _patch_query(monkeypatch, df)
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert len(out) > 0
    for f in out:
        assert f.ticker == "IWM"


def test_missing_table_skips_silently(monkeypatch):
    """Pre-deploy / fresh-instance state: the table doesn't exist yet.
    Must NOT mark stale — that would false-alarm on every fresh deploy.
    `_query_value_sanity` uses the same pattern."""
    from scripts.audit_data_freshness import _query_column_nullity
    _patch_query(monkeypatch, Exception("relation \"strat_features_5m\" does not exist"))
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert out == []


def test_empty_window_skips(monkeypatch):
    """Zero rows for any ticker in the lookback window means the table
    is being written but not for these tickers (or this is a weekend
    with no bars). Row-freshness checks cover the gap; column-nullity
    must NOT add noise on top."""
    from scripts.audit_data_freshness import _query_column_nullity
    _patch_query(monkeypatch, pd.DataFrame())
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert out == []


def test_zero_total_does_not_division_error(monkeypatch):
    """A ticker row with total=0 must be skipped, not crash on
    non_null/total division. Edge case — shouldn't happen given the
    GROUP BY semantics, but defensive."""
    from scripts.audit_data_freshness import _query_column_nullity
    df = _fake_distribution([
        {"ticker": "IWM", "total": 0, "non_null": 0},
    ])
    _patch_query(monkeypatch, df)
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert out == []


def test_writer_job_routes_alert_to_culprit():
    """vix_close maps to fetch-market-data; total_gex maps to
    strat-engine. The operator pages on the actual culprit job rather
    than greping deploy.sh to figure out who to wake up."""
    from scripts.audit_data_freshness import COLUMN_NULLITY_CHECKS
    by_name = {c["name"]: c for c in COLUMN_NULLITY_CHECKS}
    assert by_name["strat_features_5m.vix_close"]["writer_job"] == "fetch-market-data"
    assert by_name["strat_features_5m.total_gex"]["writer_job"] == "strat-engine"
    assert by_name["strat_features_5m.gamma_balance_price"]["writer_job"] == "strat-engine"
    assert by_name["strat_features_5m.total_vex"]["writer_job"] == "strat-engine"
    assert by_name["strat_features_levels_5m.orb_5m_high"]["writer_job"] == "strat-engine"


def test_checks_cover_the_2026_06_cascade_columns():
    """Pin that the four columns that silently NULLed during the
    2026-05-22 → 06-19 cascade are all in the check list. A future
    refactor that drops one would reintroduce the exact gap this
    PR exists to close."""
    from scripts.audit_data_freshness import COLUMN_NULLITY_CHECKS
    names = {c["name"] for c in COLUMN_NULLITY_CHECKS}
    cascade_columns = {
        "strat_features_5m.vix_close",
        "strat_features_5m.total_gex",
        "strat_features_5m.gamma_balance_price",
        "strat_features_5m.total_vex",
    }
    missing = cascade_columns - names
    assert not missing, (
        f"COLUMN_NULLITY_CHECKS missing {missing} — the cascade columns "
        f"that silently NULLed for 4 weeks must stay covered"
    )


def test_audit_all_wires_in_column_nullity(monkeypatch):
    """The audit_all() public entry point MUST call _query_column_nullity
    and merge its findings into the report. Without this wiring the
    column-nullity checks would be dead code and the cascade gap would
    still be open."""
    from scripts import audit_data_freshness as mod

    # Stub the other queries to no-op so we test only the wiring.
    monkeypatch.setattr(mod, "CHECKS", [])
    monkeypatch.setattr(mod, "_query_value_sanity",
                        lambda *_args, **_kw: [])

    sentinel = mod.FreshnessRow(
        table="sentinel.col", ticker="IWM",
        last_row_at="sentinel", expected_latest="",
        lag_hours=None, expected_max_hours=0, status="stale",
    )
    called = {"n": 0}

    def fake_column_nullity(_now):
        called["n"] += 1
        return [sentinel]

    monkeypatch.setattr(mod, "_query_column_nullity", fake_column_nullity)
    report = mod.audit_all(now_utc=datetime(2026, 6, 21, 14, 0))
    assert called["n"] == 1, "_query_column_nullity must be called from audit_all"
    assert sentinel in report.rows, "findings must be merged into the report"
