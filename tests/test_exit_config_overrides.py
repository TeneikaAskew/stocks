"""Unit tests for lib.strategies.exit_config_overrides (Tier-A resolver).

Mirrors test_strategies_calibration.py — same monkeypatch-the-row
strategy, no DB required. Covers:

  - Tier-A hit (DB row present + usable values)
  - Tier-A miss → Tier-B fallback (no row, NaN, None, infinity, stale)
  - Per-knob resolution (call_target / put_target / call_stop / put_stop /
    call_time_stop / put_time_stop)
  - lru_cache cleared between tests so monkeypatches take effect
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from lib.strategies import exit_config_overrides as eco
from lib.config import ExitConfig

DEFAULTS = ExitConfig()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear lru_cache between tests."""
    eco._latest_overrides.cache_clear()
    yield
    eco._latest_overrides.cache_clear()


# ── Tier-A miss: empty row ────────────────────────────────────────────


def test_no_row_returns_tier_b_call_target():
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_call_target("UNKNOWN") == DEFAULTS.call_target


def test_no_row_returns_tier_b_for_every_knob():
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_call_target("X") == DEFAULTS.call_target
        assert eco.get_put_target("X") == DEFAULTS.put_target
        assert eco.get_call_stop("X") == DEFAULTS.call_stop
        assert eco.get_put_stop("X") == DEFAULTS.put_stop
        assert eco.get_call_time_stop("X") == DEFAULTS.call_time_stop
        assert eco.get_put_time_stop("X") == DEFAULTS.put_time_stop


# ── Tier-A hit ────────────────────────────────────────────────────────


def _row(**overrides) -> dict:
    base = {
        "calibration_date": date.today(),
        "call_target": 0.00301, "put_target": 0.00238,
        "call_stop": 0.00075, "put_stop": 0.00075,
        "call_time_stop": 20, "put_time_stop": 25,
        "disabled_conditions": None,
        "blue_sky_atr_offset": None,
        "notes": "test",
    }
    base.update(overrides)
    return base


def test_tier_a_hit_call_target():
    with patch.object(eco, "_latest_overrides", return_value=_row()):
        assert eco.get_call_target("QQQ") == 0.00301


def test_tier_a_hit_all_knobs():
    with patch.object(eco, "_latest_overrides", return_value=_row()):
        assert eco.get_call_target("QQQ") == 0.00301
        assert eco.get_put_target("QQQ") == 0.00238
        assert eco.get_call_stop("QQQ") == 0.00075
        assert eco.get_put_stop("QQQ") == 0.00075
        assert eco.get_call_time_stop("QQQ") == 20
        assert eco.get_put_time_stop("QQQ") == 25


# ── NaN / None / infinity in row → Tier-B for that knob only ─────────


def test_nan_call_target_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=float('nan'))):
        # NaN call_target → Tier-B; other knobs still Tier-A
        assert eco.get_call_target("QQQ") == DEFAULTS.call_target
        assert eco.get_put_target("QQQ") == 0.00238


def test_none_call_target_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=None)):
        assert eco.get_call_target("QQQ") == DEFAULTS.call_target


def test_infinity_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=float('inf'))):
        assert eco.get_call_target("QQQ") == DEFAULTS.call_target


def test_zero_time_stop_falls_back():
    """0 minute time-stop is nonsense; treat as missing."""
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_time_stop=0)):
        assert eco.get_call_time_stop("QQQ") == DEFAULTS.call_time_stop


def test_negative_time_stop_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(put_time_stop=-5)):
        assert eco.get_put_time_stop("QQQ") == DEFAULTS.put_time_stop


# ── Blue-sky ATR offset (audit G.P1.4 follow-up) ─────────────────────


def test_get_blue_sky_atr_offset_returns_value_when_set():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(blue_sky_atr_offset=0.20)):
        assert eco.get_blue_sky_atr_offset("QQQ") == 0.20


def test_get_blue_sky_atr_offset_returns_none_when_no_row():
    """Missing row → None, lets caller fall back to global default."""
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_blue_sky_atr_offset("UNK") is None


def test_get_blue_sky_atr_offset_returns_none_on_null_column():
    """Row exists but column is NULL → None (unseeded ticker case)."""
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(blue_sky_atr_offset=None)):
        assert eco.get_blue_sky_atr_offset("QQQ") is None


def test_get_blue_sky_atr_offset_returns_none_on_nan():
    """NaN comes through pandas for SQL NULL on DOUBLE PRECISION; treat
    as unset for the same reason every other knob does."""
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(blue_sky_atr_offset=float("nan"))):
        assert eco.get_blue_sky_atr_offset("QQQ") is None


# ── Stale row → Tier-B (handled inside _latest_overrides) ────────────


def test_get_resolution_tier_returns_b_when_no_row():
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_resolution_tier("UNK", "call_target") == "B"


def test_get_resolution_tier_returns_a_when_present():
    with patch.object(eco, "_latest_overrides", return_value=_row()):
        assert eco.get_resolution_tier("QQQ", "call_target") == "A"
        assert eco.get_resolution_tier("QQQ", "put_target") == "A"
        assert eco.get_resolution_tier("QQQ", "call_time_stop") == "A"


def test_get_resolution_tier_returns_b_when_value_nan():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=float('nan'))):
        assert eco.get_resolution_tier("QQQ", "call_target") == "B"
        # Other knobs still A
        assert eco.get_resolution_tier("QQQ", "put_target") == "A"


# ── Helper purity ─────────────────────────────────────────────────────


def test_is_usable_number():
    assert eco._is_usable_number(0.00301)
    assert not eco._is_usable_number(None)
    assert not eco._is_usable_number(float('nan'))
    assert not eco._is_usable_number(float('inf'))
    assert not eco._is_usable_number(float('-inf'))
    assert eco._is_usable_number(0.0)  # zero is a valid value


def test_is_usable_int():
    assert eco._is_usable_int(20)
    assert eco._is_usable_int(20.0)
    assert not eco._is_usable_int(None)
    assert not eco._is_usable_int(float('nan'))
    assert not eco._is_usable_int(0)
    assert not eco._is_usable_int(-5)


# ── Per-column latest-non-NULL merge across multiple rows ────────────


class TestPerColumnMergeAcrossRows:
    """Architectural defense (PR #334 follow-up): when multiple
    calibration jobs write to `exit_config_overrides` on different
    cadences, the resolver merges per-column latest non-NULL across
    all rows within the staleness window. A newer row's NULL in column
    X must NOT mask an older row's calibrated value for column X.

    This is the "blue-sky offset job runs monthly, PR-E7 target/stop
    job runs quarterly, neither should clobber the other" guarantee.
    """

    def _mock_two_rows(self, monkeypatch, rows):
        """Mock the SQL fetch to return a 2-row DataFrame in date-DESC
        order. `rows` is a list of dicts; first dict is the newer row."""
        import pandas as pd
        df = pd.DataFrame(rows)
        monkeypatch.setattr('gcp.database.is_cloud_sql_configured',
                            lambda: True)
        monkeypatch.setattr('gcp.database.get_engine', lambda: object())
        monkeypatch.setattr(pd, 'read_sql', lambda *a, **kw: df)

    def test_newer_row_null_does_not_clobber_older_value(self, monkeypatch):
        """Newer row sets only blue_sky; older row had call_target.
        Resolver must serve BOTH (the older call_target + newer blue_sky)."""
        today = date.today()
        rows = [
            # NEWER row (calibration_date today): blue_sky_atr_offset
            # populated, target/stop columns NULL.
            {"calibration_date": today,
             "call_target": None, "put_target": None,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": 0.20,
             "notes": "blue-sky monthly refresh"},
            # OLDER row (90 days back): full target/stop seed,
            # blue_sky_atr_offset NOT yet populated.
            {"calibration_date": today - timedelta(days=90),
             "call_target": 0.00301, "put_target": 0.00238,
             "call_stop": 0.00075, "put_stop": 0.00075,
             "call_time_stop": 20, "put_time_stop": 25,
             "disabled_conditions": None,
             "blue_sky_atr_offset": None,
             "notes": "audit 2026-05-08 seed"},
        ]
        self._mock_two_rows(monkeypatch, rows)
        merged = eco._latest_overrides("QQQ")
        assert merged is not None
        # NEWER value preserved
        assert merged["blue_sky_atr_offset"] == 0.20
        # OLDER values NOT clobbered by newer row's NULL
        assert merged["call_target"] == 0.00301
        assert merged["put_target"] == 0.00238
        assert merged["call_stop"] == 0.00075
        assert merged["call_time_stop"] == 20
        # `notes` describes the latest action only
        assert merged["notes"] == "blue-sky monthly refresh"

    def test_newer_row_overrides_older_value(self, monkeypatch):
        """When BOTH rows have a value for the same column, the newer
        row wins (rows are sorted DESC, dropna picks first non-NaN)."""
        today = date.today()
        rows = [
            {"calibration_date": today,
             "call_target": 0.00250, "put_target": None,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": None,
             "notes": "Q1 refresh"},
            {"calibration_date": today - timedelta(days=90),
             "call_target": 0.00301, "put_target": 0.00238,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": None,
             "notes": "audit seed"},
        ]
        self._mock_two_rows(monkeypatch, rows)
        merged = eco._latest_overrides("QQQ")
        assert merged["call_target"] == 0.00250  # newer wins
        assert merged["put_target"] == 0.00238   # older preserved

    def test_all_rows_stale_returns_none(self, monkeypatch):
        """Both rows older than _STALE_DAYS → fallback to Tier-B."""
        today = date.today()
        rows = [
            {"calibration_date": today - timedelta(days=200),
             "call_target": 0.00301, "put_target": None,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": None, "notes": "stale"},
            {"calibration_date": today - timedelta(days=300),
             "call_target": None, "put_target": 0.00238,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": None, "notes": "even staler"},
        ]
        self._mock_two_rows(monkeypatch, rows)
        merged = eco._latest_overrides("QQQ")
        assert merged is None

    def test_partial_staleness_still_returns_fresh(self, monkeypatch):
        """One fresh row + one stale row → only fresh row's values count.
        Stale row's calibrated values are NOT carried forward (operator
        decided not to refresh them recently — fall back to Tier-B for
        those columns)."""
        today = date.today()
        rows = [
            # Fresh row, sets only blue_sky_atr_offset
            {"calibration_date": today,
             "call_target": None, "put_target": None,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": 0.20,
             "notes": "fresh"},
            # Stale row, had everything (>180d ago)
            {"calibration_date": today - timedelta(days=200),
             "call_target": 0.00301, "put_target": 0.00238,
             "call_stop": 0.00075, "put_stop": 0.00075,
             "call_time_stop": 20, "put_time_stop": 25,
             "disabled_conditions": None,
             "blue_sky_atr_offset": None,
             "notes": "stale seed"},
        ]
        self._mock_two_rows(monkeypatch, rows)
        merged = eco._latest_overrides("QQQ")
        assert merged is not None
        assert merged["blue_sky_atr_offset"] == 0.20
        # Stale row's targets are excluded — caller falls back to Tier-B
        assert merged.get("call_target") is None
        assert merged.get("put_target") is None

    def test_disabled_conditions_jsonb_carries_forward(self, monkeypatch):
        """`disabled_conditions` is JSONB (a Python list when read).
        pandas would raise on dropna for object dtype — verify the
        special-case handling preserves the list correctly."""
        today = date.today()
        rows = [
            {"calibration_date": today,
             "call_target": None, "put_target": None,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": None,
             "blue_sky_atr_offset": 0.15,
             "notes": "blue-sky only"},
            {"calibration_date": today - timedelta(days=30),
             "call_target": None, "put_target": None,
             "call_stop": None, "put_stop": None,
             "call_time_stop": None, "put_time_stop": None,
             "disabled_conditions": ["stoch_rsi_overbought", "rsi_overbought_zone"],
             "blue_sky_atr_offset": None,
             "notes": "MR PUT condition prune"},
        ]
        self._mock_two_rows(monkeypatch, rows)
        merged = eco._latest_overrides("IWM")
        assert merged is not None
        assert merged["blue_sky_atr_offset"] == 0.15
        assert merged["disabled_conditions"] == [
            "stoch_rsi_overbought", "rsi_overbought_zone"
        ]


# ── Resilience: table-missing / DB-error → Tier-B (PR #327 codex review) ──


class TestLatestOverridesFallsBackOnDbError:
    """If the exit_config_overrides table doesn't exist (PR-E1
    migration not yet applied) or get_engine raises (no GCP creds in
    unit-test env), `_latest_overrides` must return None instead of
    crashing — every resolver call falls back to Tier-B and live
    alerts keep firing with the existing ExitConfig defaults."""

    def test_undefined_table_returns_none(self, monkeypatch):
        eco._latest_overrides.cache_clear()
        monkeypatch.setattr('gcp.database.is_cloud_sql_configured',
                            lambda: True)
        # pd.read_sql raises (e.g. UndefinedTable when PR-E1 migration not yet applied)
        import pandas as pd

        def _boom(*a, **kw):
            raise RuntimeError(
                'UndefinedTable: relation "exit_config_overrides" does not exist'
            )

        monkeypatch.setattr(pd, 'read_sql', _boom)
        # Mock get_engine so it doesn't fail first on creds
        monkeypatch.setattr('gcp.database.get_engine', lambda: object())
        assert eco._latest_overrides('QQQ') is None
        assert eco.get_call_target('QQQ') == DEFAULTS.call_target

    def test_get_engine_credential_error_returns_none(self, monkeypatch):
        eco._latest_overrides.cache_clear()
        monkeypatch.setattr('gcp.database.is_cloud_sql_configured',
                            lambda: True)

        def _no_creds():
            raise Exception('DefaultCredentialsError: no ADC configured')

        monkeypatch.setattr('gcp.database.get_engine', _no_creds)
        assert eco._latest_overrides('SPY') is None
        assert eco.get_put_target('SPY') == DEFAULTS.put_target
