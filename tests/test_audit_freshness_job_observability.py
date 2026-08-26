"""Tests for the job-observability checks (issue #751 follow-ups).

Two blind spots let the 2026-08 backfill-daily-indicators loop run for
20 days: nothing watched the enrichment contract (raw bars land nightly;
the 02:30 ET job enriches them — a break surfaced only as somebody
else's timeout), and nothing watched duration trends (the job ran 3h09m
daily against a 3h cap — 19 near-misses with no queryable history).
These tests pin the two freshness-watchdog checks that close those
gaps, plus gcp.database.record_job_run which feeds the second one.
"""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import patch

import pandas as pd


def _patch_strict(monkeypatch, df):
    """Stub query_to_dataframe_strict, recording every call.

    Returns the call log so tests can assert on the SQL that was issued
    and on the timeout each check bound itself to (issue #765).
    """
    from gcp import database
    calls: list[dict] = []

    def fake(sql, params=None, timeout_s=None):
        calls.append({"sql": sql, "params": params, "timeout_s": timeout_s})
        return df.copy()

    monkeypatch.setattr(database, "query_to_dataframe_strict", fake)
    return calls


# ── enrichment coverage ──────────────────────────────────────────────


def test_enrichment_healthy_is_silent(monkeypatch):
    from scripts.audit_data_freshness import _query_enrichment_coverage
    _patch_strict(monkeypatch, pd.DataFrame([{"total": 2400, "non_null": 2390}]))
    assert _query_enrichment_coverage(datetime(2026, 8, 25, 14, 0)) == []


def test_enrichment_degraded_fires_stale(monkeypatch):
    """The #751 signature: raw bars present, half the universe
    unenriched. Must page the enrichment stage's writer job."""
    from scripts.audit_data_freshness import _query_enrichment_coverage
    _patch_strict(monkeypatch, pd.DataFrame([{"total": 2400, "non_null": 1200}]))
    out = _query_enrichment_coverage(datetime(2026, 8, 25, 14, 0))
    assert len(out) == 1
    assert out[0].status == "stale"
    assert out[0].writer_job == "backfill-daily-indicators"
    assert "50.0%" in out[0].last_row_at


def test_enrichment_no_bars_defers_to_freshness_checks(monkeypatch):
    """Zero bars for the settled day is a missing-data failure owned by
    the gap-scan/freshness checks — this check must not double-report."""
    from scripts.audit_data_freshness import _query_enrichment_coverage
    _patch_strict(monkeypatch, pd.DataFrame([{"total": 0, "non_null": 0}]))
    assert _query_enrichment_coverage(datetime(2026, 8, 25, 14, 0)) == []


# ── duration regression ──────────────────────────────────────────────


def test_duration_regression_skips_without_table(monkeypatch):
    """Instances that haven't run the schema migration must log-and-skip
    (narrow, visible), not fail the whole audit."""
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: False)
    assert _query_job_duration_regression(datetime(2026, 8, 25, 14, 0)) == []


def test_duration_regression_healthy_is_silent(monkeypatch):
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    _patch_strict(monkeypatch, pd.DataFrame([
        {"job_name": "backfill-daily-indicators", "variant": "daily",
         "latest_s": 2100.0, "median_prior_s": 1900.0, "n_runs": 14},
    ]))
    assert _query_job_duration_regression(datetime(2026, 8, 25, 14, 0)) == []


def test_duration_regression_fires_stale(monkeypatch):
    """The #751 shape: a job that used to take ~35 min suddenly runs
    3h+. latest > 2x median AND above the floor → STALE naming the job.
    Must be stale, not warn: the deployed watchdog's --strict exit code
    (the only signal the failure-notifier sees) fires solely on stale —
    a warn here would make the detector inert in production (Codex P1,
    PR #759)."""
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    _patch_strict(monkeypatch, pd.DataFrame([
        {"job_name": "backfill-daily-indicators", "variant": "daily",
         "latest_s": 11340.0, "median_prior_s": 2100.0, "n_runs": 14},
    ]))
    out = _query_job_duration_regression(datetime(2026, 8, 25, 14, 0))
    assert len(out) == 1
    assert out[0].status == "stale"
    assert out[0].writer_job == "backfill-daily-indicators"
    assert "[daily]" in out[0].table


def test_duration_regression_partitions_by_variant(monkeypatch):
    """A healthy weekly full sweep (2h vs its own 2h median) must not be
    judged against the daily variant's minutes-scale median (Codex P2,
    PR #759) — the SQL groups by (job_name, variant), and per-group
    rows that are within factor stay silent."""
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    _patch_strict(monkeypatch, pd.DataFrame([
        {"job_name": "backfill-daily-indicators", "variant": "daily",
         "latest_s": 180.0, "median_prior_s": 150.0, "n_runs": 20},
        {"job_name": "backfill-daily-indicators", "variant": "full",
         "latest_s": 7800.0, "median_prior_s": 7200.0, "n_runs": 8},
    ]))
    assert _query_job_duration_regression(datetime(2026, 8, 25, 14, 0)) == []


def test_duration_regression_sql_groups_by_variant(monkeypatch):
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    captured = {}

    def fake(sql, params=None, timeout_s=None):
        captured["sql"] = sql
        return pd.DataFrame()

    monkeypatch.setattr(database, "query_to_dataframe_strict", fake)
    _query_job_duration_regression(datetime(2026, 8, 25, 14, 0))
    assert "PARTITION BY job_name, COALESCE(variant, '')" in captured["sql"]
    assert "GROUP BY job_name, variant" in captured["sql"]


def test_duration_regression_ignores_fast_jobs(monkeypatch):
    """A 40s job jumping to 90s trips the 2x factor but not the floor —
    sub-5-minute jitter must not page."""
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    _patch_strict(monkeypatch, pd.DataFrame([
        {"job_name": "fetch-fred-rates", "variant": None,
         "latest_s": 90.0, "median_prior_s": 40.0, "n_runs": 20},
    ]))
    assert _query_job_duration_regression(datetime(2026, 8, 25, 14, 0)) == []


# ── record_job_run ───────────────────────────────────────────────────


def test_record_job_run_inserts_row():
    from datetime import timedelta, timezone
    from gcp import database
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch.object(database, "execute_sql") as ex:
        ok = database.record_job_run(
            "backfill-daily-indicators",
            started,
            "success",
            items_total=2400, items_processed=2395, items_failed=5,
            rows_written=123456, note="mode=daily workers=4",
        )
    assert ok is True
    ex.assert_called_once()
    sql, params = ex.call_args[0]
    assert "INSERT INTO job_runs" in sql
    assert params["job_name"] == "backfill-daily-indicators"
    assert params["status"] == "success"
    assert params["items_total"] == 2400
    assert params["duration_s"] > 0


def test_record_job_run_never_raises():
    """Telemetry must not fail the job (Rule 3.7 cleanup-path exception:
    the job's outcome is already decided when this runs). A DB blip
    returns False with a logged warning — never an exception."""
    from datetime import timezone
    from gcp import database
    with patch.object(database, "execute_sql",
                      side_effect=RuntimeError("connection reset")):
        ok = database.record_job_run(
            "backfill-daily-indicators",
            datetime(2026, 8, 25, 6, 30, tzinfo=timezone.utc),
            "success",
        )
    assert ok is False


# ── wiring: the backfill job records its runs ────────────────────────


def test_backfill_main_records_job_run(monkeypatch):
    from gcp.fetchers import backfill_daily_indicators as mod
    calls = []
    monkeypatch.setattr(mod, "_tickers_with_gaps", lambda d: ["AAA", "BBB"])
    monkeypatch.setattr(mod, "backfill_ticker",
                        lambda tk, recent_days=None: 7)
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(
        mod, "record_job_run",
        lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.delenv("BACKFILL_TICKERS", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "backfill_daily_indicators", "--mode=daily", "--workers", "2",
    ])
    assert mod.main() == 0
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "backfill-daily-indicators"
    assert args[2] == "success"
    assert kwargs["variant"] == "daily"
    assert kwargs["items_total"] == 2
    assert kwargs["items_failed"] == 0
    assert kwargs["rows_written"] == 14


def test_backfill_main_records_empty_run(monkeypatch):
    from gcp.fetchers import backfill_daily_indicators as mod
    calls = []
    monkeypatch.setattr(mod, "_tickers_with_gaps", lambda d: [])
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(
        mod, "record_job_run",
        lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.delenv("BACKFILL_TICKERS", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "backfill_daily_indicators", "--mode=daily",
    ])
    assert mod.main() == 0
    assert len(calls) == 1
    assert calls[0][1]["items_total"] == 0


# ── #765: the watchdog's 3600s task-timeout ──────────────────────────
#
# freshness-watchdog ran 8-14 min for months, then began hitting its
# 3600s cap the day PR #759 shipped. Cause: #759's enrichment-coverage
# check was the watchdog's first query with NO ticker predicate, and
# market_data_daily carried only ticker-leading indexes -- so a date-only
# WHERE could not be served by an index and degraded to a full sequential
# scan, twice. Every earlier check is per-ticker and rides
# idx_market_data_daily_ticker_date, which is why nothing regressed until
# then. These tests pin all three halves of the fix so it cannot silently
# come back: the index, the query shape, and the per-query bound.


def test_enrichment_sql_is_bounded_to_the_days_tickers(monkeypatch):
    """The 450-day history scan must carry a ticker predicate.

    Without it the planner cannot use (ticker, date DESC) and falls back
    to a full table scan -- the #765 timeout.
    """
    from scripts.audit_data_freshness import _query_enrichment_coverage
    calls = _patch_strict(monkeypatch, pd.DataFrame([{"total": 10, "non_null": 10}]))
    _query_enrichment_coverage(datetime(2026, 8, 25, 14, 0))
    sql = calls[0]["sql"]
    assert "m.ticker = d.ticker" in sql, (
        "the history probe lost its per-ticker correlation — this is the "
        "shape that caused the #765 full-table scan")
    assert "OFFSET 49 LIMIT 1" in sql, (
        "eligibility must be an early-exit EXISTS probe (~50 rows/ticker); "
        "a count()/GROUP BY/HAVING form re-scans the full ~1.1M-row window "
        "and exceeded the 120s per-query bound even on a quiet instance")
    assert "EXISTS" in sql


def test_enrichment_sql_anchors_on_day_not_wall_clock(monkeypatch):
    """An as-of check must not let CURRENT_DATE pick the history window.

    :day falls back a session before 05:00 ET and on holidays; anchoring
    the eligibility window on CURRENT_DATE made the result depend on when
    the job happened to run and let bars dated after :day be counted.
    """
    from scripts.audit_data_freshness import _query_enrichment_coverage
    calls = _patch_strict(monkeypatch, pd.DataFrame([{"total": 10, "non_null": 10}]))
    _query_enrichment_coverage(datetime(2026, 8, 25, 14, 0))
    sql = calls[0]["sql"]
    assert "CURRENT_DATE" not in sql, "history window must be anchored on :day"
    assert "m.date <= CAST(:day AS date)" in sql, "missing as-of upper bound"


def test_both_759_checks_bound_their_query_time(monkeypatch):
    """No single check may spend a meaningful slice of the 3600s budget.

    In #765 the job was killed mid-run and reported nothing at all — not
    even the checks that had already passed. A per-query bound turns that
    into one attributable check failure.
    """
    from gcp import database
    from scripts.audit_data_freshness import (
        _CHECK_QUERY_TIMEOUT_S, _query_enrichment_coverage,
        _query_job_duration_regression,
    )
    assert _CHECK_QUERY_TIMEOUT_S <= 300, (
        "a per-check bound above 5 min defeats its purpose against a "
        "3600s task-timeout")

    calls = _patch_strict(monkeypatch, pd.DataFrame([{"total": 10, "non_null": 10}]))
    _query_enrichment_coverage(datetime(2026, 8, 25, 14, 0))
    assert calls[0]["timeout_s"] == _CHECK_QUERY_TIMEOUT_S

    monkeypatch.setattr(database, "table_exists", lambda t: True)
    calls2 = _patch_strict(monkeypatch, pd.DataFrame())
    _query_job_duration_regression(datetime(2026, 8, 25, 14, 0))
    assert calls2[0]["timeout_s"] == _CHECK_QUERY_TIMEOUT_S


def test_market_data_daily_has_a_date_leading_index():
    """Whole-universe single-day queries need a date-leading index.

    (ticker, date DESC) cannot serve a date-only WHERE. Dropping this
    index silently restores the #765 sequential scan.
    """
    import pathlib
    schema = (pathlib.Path(__file__).resolve().parent.parent
              / "gcp" / "schema.sql").read_text()
    assert "idx_market_data_daily_date" in schema
    assert "ON market_data_daily (date)" in schema


def test_timed_reraises_and_does_not_degrade_the_audit():
    """A failing check fails the audit loudly (Rule 3.7).

    Swallowing it would render the run a partial pass that reads green —
    the silent-failure mode the watchdog exists to prevent.
    """
    import pytest
    from scripts.audit_data_freshness import _timed

    def boom(_now):
        raise RuntimeError("check exploded")

    with pytest.raises(RuntimeError, match="check exploded"):
        _timed("boom", boom, datetime(2026, 8, 25, 14, 0))

    assert _timed("fine", lambda _n: ["row"], datetime(2026, 8, 25, 14, 0)) == ["row"]
