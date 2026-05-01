"""Unit + integration tests for gcp/fetchers/fetch_earnings_history.py

Covers Phase 1 fixes:
- _safe_float NaN guard (NaN values should return None, not leak through)
- _safe_str normalization (handles None / 'None' / 'null' / 'NaN' / empty)
- fetch_history_for_ticker captures `reportTime` from AV response into
  the new `report_time` column
"""
import math
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from gcp.fetchers.fetch_earnings_history import (
    _safe_float,
    _safe_str,
    _yahoo_timing_from_event_dt,
    _earnings_history_tickers,
    fetch_history_for_ticker,
)


# ────────────────────────────────────────────────────────────
# _earnings_history_tickers — self-heal source
# ────────────────────────────────────────────────────────────

class TestEarningsHistorySelfHealSource:
    def test_returns_distinct_tickers_from_db(self, monkeypatch):
        """The self-heal source queries earnings_history for every ticker
        we've ever pulled. Verify it normalizes to upper-case and
        returns a list of strings."""
        from gcp.fetchers import fetch_earnings_history as feh

        def fake_query_to_dataframe(sql, params=None):
            sql_upper = sql.upper()
            assert "DISTINCT TICKER" in sql_upper
            assert "EARNINGS_HISTORY" in sql_upper
            return pd.DataFrame({"ticker": ["amzn", "msft", "AVGO"]})

        monkeypatch.setattr(
            "gcp.database.query_to_dataframe", fake_query_to_dataframe
        )
        result = _earnings_history_tickers()
        assert result == ["AMZN", "MSFT", "AVGO"]

    def test_empty_db_returns_empty_list(self, monkeypatch):
        from gcp.fetchers import fetch_earnings_history as feh
        monkeypatch.setattr(
            "gcp.database.query_to_dataframe",
            lambda sql, params=None: pd.DataFrame(),
        )
        assert _earnings_history_tickers() == []

    def test_db_error_returns_empty_list(self, monkeypatch):
        """If Cloud SQL is unreachable, return empty (don't crash the
        fetcher) — caller falls back to other sources."""
        from gcp.fetchers import fetch_earnings_history as feh
        def boom(sql, params=None):
            raise RuntimeError("connection refused")
        monkeypatch.setattr("gcp.database.query_to_dataframe", boom)
        assert _earnings_history_tickers() == []


# ────────────────────────────────────────────────────────────
# _safe_float — NaN guard (Phase 1 fix)
# ────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_string_none_returns_none(self):
        assert _safe_float("None") is None

    def test_empty_string_returns_none(self):
        assert _safe_float("") is None

    def test_valid_int_string(self):
        assert _safe_float("5") == 5.0

    def test_valid_decimal_string(self):
        assert _safe_float("2.05") == 2.05

    def test_negative_value(self):
        assert _safe_float("-1.5") == -1.5

    def test_zero(self):
        assert _safe_float("0") == 0.0

    def test_unparseable_string(self):
        assert _safe_float("abc") is None

    def test_nan_string_returns_none(self):
        """AV sometimes returns 'NaN' as a string for upcoming reports.
        Must not leak through as a float NaN — that breaks the
        `reported_eps IS NOT NULL` filter downstream."""
        assert _safe_float("NaN") is None

    def test_python_nan_returns_none(self):
        """Direct float NaN must also be filtered."""
        assert _safe_float(float("nan")) is None

    def test_numpy_nan_returns_none(self):
        """Numpy NaN behaves like float NaN."""
        import numpy as np
        assert _safe_float(np.nan) is None


# ────────────────────────────────────────────────────────────
# _safe_str — string normalization
# ────────────────────────────────────────────────────────────

class TestSafeStr:
    def test_none_returns_none(self):
        assert _safe_str(None) is None

    def test_empty_string_returns_none(self):
        assert _safe_str("") is None

    def test_whitespace_only_returns_none(self):
        assert _safe_str("   ") is None

    def test_string_none_case_insensitive(self):
        assert _safe_str("None") is None
        assert _safe_str("NONE") is None
        assert _safe_str("none") is None

    def test_string_null(self):
        assert _safe_str("null") is None
        assert _safe_str("NULL") is None

    def test_string_nan(self):
        assert _safe_str("NaN") is None
        assert _safe_str("nan") is None

    def test_valid_string_preserved(self):
        assert _safe_str("pre-market") == "pre-market"
        assert _safe_str("post-market") == "post-market"

    def test_strips_whitespace(self):
        assert _safe_str("  pre-market  ") == "pre-market"


# ────────────────────────────────────────────────────────────
# fetch_history_for_ticker — captures report_time
# ────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────
# _yahoo_timing_from_event_dt — derive timing from Yahoo timestamp
# ────────────────────────────────────────────────────────────

class TestYahooTimingFromEventDt:
    def test_post_market_hours(self):
        # 16:31 ET on 2026-02-25 (NVDA's actual report time)
        ts = pd.Timestamp('2026-02-25 16:31:25', tz='US/Eastern')
        assert _yahoo_timing_from_event_dt(ts) == 'post-market'

    def test_after_hours_evening(self):
        # 20:00 ET — still AMC
        ts = pd.Timestamp('2026-02-25 20:00:00', tz='US/Eastern')
        assert _yahoo_timing_from_event_dt(ts) == 'post-market'

    def test_pre_market_early(self):
        # 06:30 ET — BMO
        ts = pd.Timestamp('2026-02-04 06:30:00', tz='US/Eastern')
        assert _yahoo_timing_from_event_dt(ts) == 'pre-market'

    def test_pre_market_at_open(self):
        # 09:30 ET (market open) — boundary, treat as BMO
        ts = pd.Timestamp('2026-02-04 09:30:00', tz='US/Eastern')
        assert _yahoo_timing_from_event_dt(ts) == 'pre-market'

    def test_intraday_returns_none(self):
        # 12:00 ET — neither BMO nor AMC, return None
        ts = pd.Timestamp('2026-02-04 12:00:00', tz='US/Eastern')
        assert _yahoo_timing_from_event_dt(ts) is None

    def test_utc_input_converted(self):
        # 21:31 UTC = 16:31 ET — should resolve to AMC
        ts = pd.Timestamp('2026-02-25 21:31:25+00:00')
        assert _yahoo_timing_from_event_dt(ts) == 'post-market'

    def test_naive_timestamp_treated_as_et(self):
        # No tzinfo — assume already-ET
        ts = pd.Timestamp('2026-02-25 16:31:25')
        assert _yahoo_timing_from_event_dt(ts) == 'post-market'

    def test_none_returns_none(self):
        assert _yahoo_timing_from_event_dt(None) is None

    def test_nat_returns_none(self):
        assert _yahoo_timing_from_event_dt(pd.NaT) is None

    def test_at_4pm_boundary(self):
        # 16:00:00 ET exactly — boundary, treat as AMC
        ts = pd.Timestamp('2026-02-25 16:00:00', tz='US/Eastern')
        assert _yahoo_timing_from_event_dt(ts) == 'post-market'


class TestFetchHistory:
    def _mock_av_response(self, quarterly):
        """Build a fake `requests.Response` mocking AV's EARNINGS reply."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "symbol": "TEST",
            "annualEarnings": [],
            "quarterlyEarnings": quarterly,
        }
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_captures_report_time(self, mock_get):
        """AV's `reportTime` field must be carried into the
        `report_time` column on every row."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-01-31",
                "reportedDate": "2026-03-04",
                "reportedEPS": "2.05",
                "estimatedEPS": "2.02",
                "surprise": "0.03",
                "surprisePercentage": "1.4851",
                "reportTime": "post-market",
            },
            {
                "fiscalDateEnding": "2025-10-31",
                "reportedDate": "2025-12-11",
                "reportedEPS": "1.95",
                "estimatedEPS": "1.87",
                "surprise": "0.08",
                "surprisePercentage": "4.28",
                "reportTime": "pre-market",
            },
        ])

        df = fetch_history_for_ticker("TEST", "fake-key")
        assert len(df) == 2
        assert "report_time" in df.columns
        # Sorted by however AV returned (most recent first)
        report_times = df["report_time"].tolist()
        assert "post-market" in report_times
        assert "pre-market" in report_times

    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_missing_report_time_becomes_none(self, mock_get):
        """If AV omits reportTime, the column should be None — not a
        bad string that breaks downstream consumers."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-01-31",
                "reportedDate": "2026-03-04",
                "reportedEPS": "2.05",
                # No reportTime field
            }
        ])
        df = fetch_history_for_ticker("TEST", "fake-key")
        assert len(df) == 1
        assert df.iloc[0]["report_time"] is None

    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_empty_report_time_becomes_none(self, mock_get):
        """Empty string from AV → None."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-01-31",
                "reportedDate": "2026-03-04",
                "reportedEPS": "2.05",
                "reportTime": "",
            }
        ])
        df = fetch_history_for_ticker("TEST", "fake-key")
        assert df.iloc[0]["report_time"] is None

    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_nan_eps_filtered(self, mock_get):
        """The classic Phase 0.5 bug: AV returns 'NaN' for upcoming
        reports' reportedEPS. _safe_float must return None so the value
        is null-equivalent (pd.isna) — even though pandas re-coerces
        None to np.nan when building the float column, what matters is
        that pd.isna() returns True so the persist-time scrub catches
        it and writes PostgreSQL NULL."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-04-30",
                "reportedDate": "2026-04-30",
                "reportedEPS": "NaN",     # <-- the bug case
                "estimatedEPS": "7.25",
                "reportTime": "pre-market",
            },
            {
                "fiscalDateEnding": "2025-12-31",
                "reportedDate": "2026-02-04",
                "reportedEPS": "7.54",
                "estimatedEPS": "7.17",
                "surprise": "0.37",
                "surprisePercentage": "5.16",
                "reportTime": "pre-market",
            },
        ])
        df = fetch_history_for_ticker("LLY", "fake-key")
        assert len(df) == 2

        upcoming = df[df["fiscal_date_ending"].astype(str) == "2026-04-30"].iloc[0]
        assert pd.isna(upcoming["reported_eps"]), \
            f"NaN reportedEPS should be null-equivalent, got {upcoming['reported_eps']}"

        valid = df[df["fiscal_date_ending"].astype(str) == "2025-12-31"].iloc[0]
        assert valid["reported_eps"] == 7.54

    def test_persist_scrub_replaces_nan_with_none(self):
        """The persist-time scrub in main() must convert pandas-NaN to
        Python None so PostgreSQL stores NULL, not 'NaN'::numeric.
        Verifies the .replace + .where pattern actually round-trips."""
        import numpy as np
        df = pd.DataFrame({
            "ticker": ["LLY", "LLY"],
            "fiscal_date_ending": [pd.Timestamp("2026-04-30").date(),
                                   pd.Timestamp("2025-12-31").date()],
            "reported_eps": [float("nan"), 7.54],
            "report_time": ["pre-market", "pre-market"],
        })
        # Mirror the scrub logic from main()
        scrubbed = df.replace({np.nan: None}).where(df.notna(), None)

        assert scrubbed.iloc[0]["reported_eps"] is None
        assert scrubbed.iloc[1]["reported_eps"] == 7.54
        assert scrubbed.iloc[0]["report_time"] == "pre-market"

    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_no_quarterly_returns_empty(self, mock_get):
        mock_get.return_value = self._mock_av_response([])
        df = fetch_history_for_ticker("TEST", "fake-key")
        assert df.empty

    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_av_rate_limit_returns_empty(self, mock_get):
        """When AV returns an Information envelope (rate limit / bad key),
        we should get an empty DataFrame, not crash."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "Information": "Thank you for using Alpha Vantage! ..."
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        df = fetch_history_for_ticker("TEST", "fake-key", enrich_with_yahoo=False)
        assert df.empty

    @patch("gcp.fetchers.fetch_earnings_history.fetch_yahoo_timing_for_ticker")
    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_yahoo_merge_overrides_av_disagreement(self, mock_get, mock_yahoo):
        """When Yahoo says post-market but AV reportTime says pre-market,
        the row stores both — yahoo_report_time is the override.
        compute_earnings_reactions resolves precedence at query time."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-01-31",
                "reportedDate": "2026-02-25",
                "reportedEPS": "1.62",
                "estimatedEPS": "1.52",
                "surprise": "0.10",
                "surprisePercentage": "6.58",
                "reportTime": "pre-market",   # AV's wrong value
            }
        ])
        mock_yahoo.return_value = {
            pd.to_datetime("2026-02-25").date(): "post-market"  # Yahoo's correct value
        }

        df = fetch_history_for_ticker("NVDA", "fake-key", enrich_with_yahoo=True)
        assert len(df) == 1
        assert df.iloc[0]["report_time"] == "pre-market"          # AV preserved
        assert df.iloc[0]["yahoo_report_time"] == "post-market"   # Yahoo override

    @patch("gcp.fetchers.fetch_earnings_history.fetch_yahoo_timing_for_ticker")
    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_yahoo_merge_no_data_leaves_yahoo_null(self, mock_get, mock_yahoo):
        """When Yahoo has no row for a particular reported_date, the
        yahoo_report_time column is NULL; AV reportTime stands alone."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-01-31",
                "reportedDate": "2026-03-04",
                "reportedEPS": "2.05",
                "estimatedEPS": "2.02",
                "surprise": "0.03",
                "surprisePercentage": "1.49",
                "reportTime": "post-market",
            }
        ])
        mock_yahoo.return_value = {}  # No Yahoo data

        df = fetch_history_for_ticker("AVGO", "fake-key", enrich_with_yahoo=True)
        assert df.iloc[0]["report_time"] == "post-market"
        assert df.iloc[0]["yahoo_report_time"] is None

    @patch("gcp.fetchers.fetch_earnings_history.fetch_yahoo_timing_for_ticker")
    @patch("gcp.fetchers.fetch_earnings_history.requests.get")
    def test_yahoo_merge_when_av_missing(self, mock_get, mock_yahoo):
        """When AV reportTime is None but Yahoo has data, yahoo_report_time
        carries the only timing signal."""
        mock_get.return_value = self._mock_av_response([
            {
                "fiscalDateEnding": "2026-01-31",
                "reportedDate": "2026-02-25",
                "reportedEPS": "1.62",
                # no reportTime
            }
        ])
        mock_yahoo.return_value = {
            pd.to_datetime("2026-02-25").date(): "post-market"
        }

        df = fetch_history_for_ticker("NVDA", "fake-key", enrich_with_yahoo=True)
        assert df.iloc[0]["report_time"] is None
        assert df.iloc[0]["yahoo_report_time"] == "post-market"
