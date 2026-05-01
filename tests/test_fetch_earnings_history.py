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
    fetch_history_for_ticker,
)


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

        df = fetch_history_for_ticker("TEST", "fake-key")
        assert df.empty
