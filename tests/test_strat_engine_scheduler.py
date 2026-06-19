"""Regression tests for the strat-engine scheduler + freshness fixes.

Three production gaps closed:
  1. strat-engine had no scheduler entry. Pin via grep on deploy.sh so
     a future refactor can't silently drop the cron back to the broken
     state.
  2. strat-engine's deploy default --args had been hand-edited away
     from `strat_data_builder` to a one-off orchestrator invocation.
     Pin that the deploy stanza dispatches strat_data_builder so
     a bare scheduler dispatch does the incremental write.
  3. strat_features_5m/15m/30m weren't in audit_data_freshness CHECKS.
     Pin their presence so any future stall (missing scheduler, job
     spec drift, writer crash) is caught by the watchdog within one
     hour, not 10 days.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()
AUDIT_PY = (REPO / "scripts/audit_data_freshness.py").read_text()


def test_strat_engine_deploy_uses_strat_data_builder():
    """The deploy stanza must dispatch strat_data_builder (bare = daily
    incremental). A previous regression had the stanza pointing at the
    strat_orchestrator with `--mode=full,--ticker=IWM,--tf=15m`, which
    only ran one cell and never wrote the other tickers/TFs. Pin the
    correct module name."""
    # Find the deploy_strat_engine function body
    m = re.search(r"deploy_strat_engine\(\)\s*\{(.*?)\n\}",
                  DEPLOY_SH, re.DOTALL)
    assert m is not None, "deploy_strat_engine function not found"
    body = m.group(1)
    assert "gcp.research.strat_engine.strat_data_builder" in body, \
        "deploy_strat_engine must dispatch strat_data_builder"
    # Specifically: the default_args local variable must NOT include
    # a baked-in --recompute-cols or --rebuild (those are operator-mode).
    assert re.search(r'default_args=.*--recompute-cols', body) is None, \
        "default_args must NOT bake in --recompute-cols (operator-only)"
    assert re.search(r'default_args=.*--rebuild', body) is None, \
        "default_args must NOT bake in --rebuild (operator-only)"


def test_strat_engine_daily_scheduler_exists():
    """The strat-engine job MUST have a scheduler entry — without one
    the strat_features_<tf> tables silently stale (06-09 → 06-19 gap)."""
    assert re.search(
        r'_schedule\s+"strat-engine-daily"\s+"[^"]+"\s+"strat-engine"',
        DEPLOY_SH,
    ), (
        "deploy.sh must register `_schedule \"strat-engine-daily\" \"<cron>\" "
        "\"strat-engine\"` — the absence of this scheduler caused the "
        "2026-06-09 → 06-19 strat_features_<tf> staleness."
    )


def test_strat_engine_scheduler_fires_after_intraday_settle():
    """The cron must fire AFTER fetch-market-data-daily settles (23:00
    ET cron + 30min buffer = 23:30 ET). Earlier than 23:30 ET risks
    reading stale market_data_intraday rows."""
    m = re.search(
        r'_schedule\s+"strat-engine-daily"\s+"([^"]+)"\s+"strat-engine"',
        DEPLOY_SH,
    )
    assert m is not None
    cron = m.group(1)
    # _schedule uses --time-zone America/New_York, so cron is in ET.
    parts = cron.split()
    # Standard 5-field cron: minute hour dom month dow
    assert len(parts) == 5, f"bad cron: {cron!r}"
    minute, hour = parts[0], parts[1]
    # Allow either 23:30+ or any hour ≥ 23 (we use 23:35 currently)
    assert int(hour) == 23 and int(minute) >= 30, (
        f"strat-engine-daily must fire after 23:30 ET to clear the "
        f"fetch-market-data-daily settle window; got {hour}:{minute}"
    )


def test_audit_freshness_tracks_strat_features_5m():
    """The 06-09 → 06-19 silent staleness happened because
    strat_features_5m wasn't in CHECKS. Pin its presence."""
    assert '"name": "strat_features_5m"' in AUDIT_PY, (
        "audit_data_freshness CHECKS must include strat_features_5m"
    )
    assert '"writer_job": "strat-engine"' in AUDIT_PY, (
        "strat_features_5m CHECK must declare writer_job='strat-engine' "
        "so the alert points at the culprit on next stall"
    )


def test_audit_freshness_tracks_all_three_strat_feature_tables():
    """5m, 15m, 30m are all written by the same job; all three should
    be tracked or a partial fix (only one TF stalling) would slip
    through."""
    for tf in ("5m", "15m", "30m"):
        assert f'"name": "strat_features_{tf}"' in AUDIT_PY, (
            f"audit_data_freshness CHECKS must include strat_features_{tf}"
        )


def test_strat_features_check_fails_promptly_on_one_missed_run():
    """Codex P2 #622: expected_lag_hours alone won't catch a single
    missed daily run because MAX(ts) only advances ~24h per run. The
    min_rows_per_day floor catches the missed partition immediately —
    `today's row_count == 0 < min` flips status to `stale` regardless
    of lag. Pin both fields so a future "simplification" doesn't drop
    the prompt-fail guarantee."""
    from scripts.audit_data_freshness import CHECKS
    for tf, min_floor in (("5m", 70), ("15m", 24), ("30m", 12)):
        entry = next(c for c in CHECKS if c["name"] == f"strat_features_{tf}")
        assert "min_rows_per_day" in entry, (
            f"strat_features_{tf} must declare min_rows_per_day so a single "
            f"missed daily run fails promptly, not after ~3 runs (Codex P2 #622)"
        )
        assert entry["min_rows_per_day"] >= min_floor // 2, (
            f"strat_features_{tf} min_rows_per_day={entry['min_rows_per_day']} "
            f"too low; even a half-session must clear the floor"
        )
        assert "gap_scan_days" in entry and entry["gap_scan_days"] >= 1, (
            f"strat_features_{tf} must declare gap_scan_days for per-day gap "
            f"detection (Codex P2 #622)"
        )
        # expected_lag_hours should also be ≤ 24 — at 30 a single 24h
        # cadence + the watchdog's hourly check window can fail to flip
        # to `stale`.
        assert entry["expected_lag_hours"] <= 24, (
            f"strat_features_{tf} expected_lag_hours must be ≤ 24h to "
            f"prompt-fail on a missed daily run (Codex P2 #622)"
        )


def test_audit_freshness_strat_features_check_loads():
    """The new CHECKS dicts must round-trip through the existing
    FreshnessRow construction (not break the watchdog at startup)."""
    from scripts.audit_data_freshness import CHECKS
    names = [c["name"] for c in CHECKS]
    assert "strat_features_5m" in names
    assert "strat_features_15m" in names
    assert "strat_features_30m" in names
    # Schema-correct entries (catches typos / missing keys)
    for tf in ("5m", "15m", "30m"):
        entry = next(c for c in CHECKS if c["name"] == f"strat_features_{tf}")
        assert entry["ts_column"] == "ts"
        assert entry["ts_is_date"] is False
        assert entry["writer_job"] == "strat-engine"
        assert entry["per_ticker"] is True
        assert "IWM" in entry["tickers"]
