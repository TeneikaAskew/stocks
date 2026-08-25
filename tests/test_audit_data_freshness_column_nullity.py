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
    """Install a fake query_to_dataframe_strict — the column-nullity
    check uses the strict variant (so SQL errors propagate rather than
    being swallowed into a silent-fallback false-pass, per Codex P2)."""
    from gcp import database

    def fake(sql, params=None, timeout_s=None):
        if isinstance(df_or_exc, BaseException):
            raise df_or_exc
        if callable(df_or_exc):
            return df_or_exc(sql, params)
        return df_or_exc.copy() if isinstance(df_or_exc, pd.DataFrame) else df_or_exc

    monkeypatch.setattr(database, "query_to_dataframe_strict", fake)


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


def test_real_sql_error_surfaces_unknown_not_silent_pass(monkeypatch):
    """Codex P2 #644: a real SQL error (e.g. column dropped in a
    schema regression) MUST surface, not silently pass. Pre-fix the
    audit used query_to_dataframe which swallows exceptions and returns
    empty df → df.empty → silent pass — the exact CLAUDE.md §3.7
    silent-fallback pattern. After fix, the function emits an
    `unknown`-status row so the operator sees it."""
    from scripts.audit_data_freshness import _query_column_nullity
    _patch_query(monkeypatch, Exception("column \"orb_5m_high\" does not exist"))
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert len(out) > 0, (
        "a schema regression must surface as a finding — silent pass "
        "is the CLAUDE.md §3.7 violation the strict-query switch fixes"
    )
    # Every emitted finding is `unknown` status (we can't tell from a
    # SQL failure whether the column is degraded or just missing).
    for f in out:
        assert f.status == "unknown"
        assert "query failed" in (f.last_row_at or "")


def test_empty_window_skips(monkeypatch):
    """Zero rows for any ticker in the lookback window means the table
    is being written but not for these tickers (or this is a weekend
    with no bars). Row-freshness checks cover the gap; column-nullity
    must NOT add noise on top."""
    from scripts.audit_data_freshness import _query_column_nullity
    _patch_query(monkeypatch, pd.DataFrame())
    out = _query_column_nullity(datetime(2026, 6, 21, 14, 0))
    assert out == []


def test_window_anchors_to_settled_trading_day_not_wallclock(monkeypatch):
    """Codex P2 #644: with a wall-clock `NOW() - INTERVAL '1 day'`
    cutoff, a Saturday-afternoon audit (~23:30 UTC) would put the
    cutoff at Friday 23:30 UTC — AFTER Friday RTH close (~20:00 UTC).
    Friday's bars would fall OUTSIDE the window, df would be empty,
    and the cascade-signature check would silently pass over the
    weekend.

    The fix anchors to the most recent SETTLED trading day. This test
    pins that contract: a Saturday-afternoon audit MUST include
    Friday's bars in the window (so a NULL `vix_close` on Friday's
    bars still fires)."""
    from scripts.audit_data_freshness import _query_column_nullity

    # Capture the params the SQL is invoked with so we can assert the
    # window covers Friday 2026-06-19.
    captured = {}
    def capturing(sql, params=None, timeout_s=None):
        captured["params"] = params or {}
        # Return the "broken" shape: 0/78 non-NULL on Friday
        return _fake_distribution([
            {"ticker": "IWM", "total": 78, "non_null": 0},
        ])

    _patch_query(monkeypatch, capturing)
    # Saturday 2026-06-13 23:30 UTC = Saturday 19:30 ET. Avoids
    # Juneteenth (Fri 2026-06-19) — picking a regular weekend so the
    # "most recent settled trading day" is unambiguously Friday 06-12.
    saturday_late = datetime(2026, 6, 13, 23, 30, 0)
    out = _query_column_nullity(saturday_late)

    # The window must START on or before Friday 2026-06-12 00:00 UTC
    # (so all of Friday's RTH bars are included) and END no earlier
    # than Saturday 00:00 UTC (one day after Friday).
    ws = captured["params"]["window_start"]
    we = captured["params"]["window_end"]
    assert ws <= datetime(2026, 6, 12, 0, 0, 0), (
        f"window_start={ws} must be on or before Fri 2026-06-12 00:00 "
        f"UTC so Friday's bars are included on a weekend audit"
    )
    assert we >= datetime(2026, 6, 13, 0, 0, 0), (
        f"window_end={we} must be on or after Sat 2026-06-13 00:00 "
        f"UTC so Friday's full session is captured"
    )
    # And the broken-Friday data MUST fire (not silently pass)
    assert len(out) > 0, (
        "a 0% non-NULL Friday bar must fire even on a Saturday audit — "
        "this is the bug Codex P2 caught"
    )


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
    monkeypatch.setattr(mod, "_query_enrichment_coverage",
                        lambda *_args, **_kw: [])
    monkeypatch.setattr(mod, "_query_job_duration_regression",
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


# ── sparse-aware calibration for gamma_balance_price (#744) ──────────────────
#
# gamma_balance is populated only on sessions where cumulative net gamma
# has a zero-crossing — lib/gamma.py documents ~half of days by design,
# and 2026-08 production measured IWM ~40%, SPY/QQQ ~50-60%. The original
# single-session 90% check therefore flapped on every crossing-less day
# (watchdog failed Sun 2026-08-23, passed Mon 08-24; the notifier opened
# and auto-closed #744 on the flap). The calibrated check widens to five
# sessions at >=20% so design sparsity passes while the #744 July
# signature (0% for 3+ weeks) still pages.


def _df_by_column(mapping):
    """Fake query keyed on which column the SQL counts, so different
    checks in the same run can see different data shapes."""
    def fake(sql, params=None, timeout_s=None):
        for col, rows in mapping.items():
            if f"COUNT({col})" in sql:
                return pd.DataFrame(rows)
        return pd.DataFrame()
    return fake


def test_gamma_balance_partial_coverage_fires_post_median(monkeypatch):
    """IWM at 40% must PAGE now — deliberately inverting the old
    sparse-tolerance test. Under the zero-crossing definition 40% was
    by-design sparsity; under the gamma-median redefinition
    (GAMMA_BALANCE_AUDIT R5, never-null directive) the value is always
    defined, so 40% coverage means the pipeline genuinely failed on 60%
    of the session's rows."""
    from scripts.audit_data_freshness import _query_column_nullity
    _patch_query(monkeypatch, _df_by_column({
        "gamma_balance_price": [
            {"ticker": "IWM", "total": 78, "non_null": 31},   # 40% of 1 session
        ],
    }))
    out = _query_column_nullity(datetime(2026, 8, 25, 14, 0))
    assert len(out) == 1 and out[0].status == "stale" and out[0].ticker == "IWM"


def test_gamma_balance_full_stop_still_fires(monkeypatch):
    """The real #744 signature — 0% for the session — must page."""
    from scripts.audit_data_freshness import _query_column_nullity
    _patch_query(monkeypatch, _df_by_column({
        "gamma_balance_price": [
            {"ticker": "IWM", "total": 78, "non_null": 0},
        ],
    }))
    out = _query_column_nullity(datetime(2026, 8, 25, 14, 0))
    assert len(out) == 1
    assert out[0].status == "stale"
    assert out[0].ticker == "IWM"
    assert out[0].writer_job == "strat-engine"


def test_gamma_checks_are_dense_calibrated():
    """Pin all three gamma checks at the strict dense shape (90%/1-day).

    History matters here: the balance check was calibrated twice against
    the OLD zero-crossing metric (#644 at 90%/1d, #762 at 20%/5d) and
    failed both times, because that metric's fill rate tracked market
    regime, not pipeline health. The gamma-median redefinition makes the
    value always defined, so the strict shape is now CORRECT — loosening
    it again would hide real pipeline bugs, and re-sparsifying it without
    re-litigating GAMMA_BALANCE_AUDIT_2026-08-25 §7 is a regression.
    gamma_flip is pinned too: it is the traded level (gamma_proximity)
    and was entirely unmonitored before (audit C-04)."""
    from scripts.audit_data_freshness import COLUMN_NULLITY_CHECKS
    by_name = {c["name"]: c for c in COLUMN_NULLITY_CHECKS}
    for name in ("strat_features_5m.gamma_balance_price",
                 "strat_features_5m.gamma_flip",
                 "strat_features_5m.total_gex"):
        check = by_name[name]
        assert check["lookback_days"] == 1, name
        assert check["min_non_null_rate"] == 0.90, name
        assert check["writer_job"] == "strat-engine", name


def test_lookback_counts_trading_sessions_not_calendar_days(monkeypatch):
    """Codex P1 #762: calendar-day subtraction turned a 5-session window
    into 3 sessions across a weekend (Tuesday anchor - 4 calendar days =
    Friday). The window must span the five most recent TRADING sessions:
    for a Tuesday 2026-08-25 audit that is Wed 08-19 .. Tue 08-25.

    The gamma checks are all 1-session now, so this pins the machinery
    through a synthetic 5-session check — the trading-session semantics
    must hold for ANY future multi-session entry."""
    import scripts.audit_data_freshness as adf
    from scripts.audit_data_freshness import _query_column_nullity

    monkeypatch.setattr(adf, "COLUMN_NULLITY_CHECKS", [{
        "name": "synthetic.multi_session_col",
        "table": "synthetic",
        "column": "multi_session_col",
        "tickers": ("IWM",),
        "lookback_days": 5,
        "min_non_null_rate": 0.20,
        "writer_job": "strat-engine",
        "rationale": "test vehicle for trading-session window semantics",
    }])

    windows = {}

    def capturing(sql, params=None, timeout_s=None):
        if "COUNT(multi_session_col)" in sql:
            windows["start"] = params["window_start"]
            windows["end"] = params["window_end"]
        return pd.DataFrame()

    _patch_query(monkeypatch, capturing)
    # Tuesday 2026-08-25 14:00 UTC (10:00 ET, past the 02:00 ET settle)
    _query_column_nullity(datetime(2026, 8, 25, 14, 0))
    assert windows["start"] == datetime(2026, 8, 19, 0, 0), (
        f"5-session window must start Wed 08-19, got {windows['start']} — "
        f"calendar-day subtraction shrinks the window across weekends"
    )
    assert windows["end"] == datetime(2026, 8, 26, 0, 0)
