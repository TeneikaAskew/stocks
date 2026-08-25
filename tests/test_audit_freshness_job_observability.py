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
    from gcp import database

    def fake(sql, params=None):
        return df.copy()

    monkeypatch.setattr(database, "query_to_dataframe_strict", fake)


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
        {"job_name": "backfill-daily-indicators",
         "latest_s": 2100.0, "median_prior_s": 1900.0, "n_runs": 14},
    ]))
    assert _query_job_duration_regression(datetime(2026, 8, 25, 14, 0)) == []


def test_duration_regression_fires_warn(monkeypatch):
    """The #751 shape: a job that used to take ~35 min suddenly runs
    3h+. latest > 2x median AND above the floor → warn naming the job."""
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    _patch_strict(monkeypatch, pd.DataFrame([
        {"job_name": "backfill-daily-indicators",
         "latest_s": 11340.0, "median_prior_s": 2100.0, "n_runs": 14},
    ]))
    out = _query_job_duration_regression(datetime(2026, 8, 25, 14, 0))
    assert len(out) == 1
    assert out[0].status == "warn"
    assert out[0].writer_job == "backfill-daily-indicators"


def test_duration_regression_ignores_fast_jobs(monkeypatch):
    """A 40s job jumping to 90s trips the 2x factor but not the floor —
    sub-5-minute jitter must not page."""
    from gcp import database
    from scripts.audit_data_freshness import _query_job_duration_regression
    monkeypatch.setattr(database, "table_exists", lambda t: True)
    _patch_strict(monkeypatch, pd.DataFrame([
        {"job_name": "fetch-fred-rates",
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
