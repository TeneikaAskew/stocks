"""Tests for ``gcp.fetchers.fetch_economic_events``.

The fetcher pulls economic-release calendars from ForexFactory and the
FRED API, then writes to the ``economic_events`` Cloud SQL table.
Mainly tests the canonical-time lookup that fills in release times for
FRED rows (since FRED's public API returns no time field).
"""

from __future__ import annotations

from datetime import time as dt_time

import pytest


# ── lookup_canonical_release_time ───────────────────────────────────────────


class TestLookupCanonicalReleaseTime:
    """The lookup is the heart of the FRED-time fix.

    FRED's /releases/dates endpoint returns no time. We map known
    release names to their published ET times so the brief shows
    08:30 / 14:00 / etc. instead of TBD for the most-watched releases.
    """

    def test_cpi_at_830(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Consumer Price Index') == dt_time(8, 30)

    def test_nfp_at_830(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Employment Situation') == dt_time(8, 30)

    def test_gdp_at_830(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Gross Domestic Product') == dt_time(8, 30)

    def test_pce_at_830(self):
        """Personal Income and Outlays = PCE deflator."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Personal Income and Outlays') == dt_time(8, 30)

    def test_jobless_claims_at_830(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time(
            'Unemployment Insurance Weekly Claims Report'
        ) == dt_time(8, 30)

    def test_housing_starts_at_830(self):
        """Census Bureau publishes Housing Starts (= New Residential Construction) at 08:30."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('New Residential Construction') == dt_time(8, 30)

    def test_industrial_production_at_915(self):
        """Fed's Industrial Production releases at 09:15 ET."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Industrial Production') == dt_time(9, 15)

    def test_ism_pmi_at_1000(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('ISM Manufacturing PMI') == dt_time(10, 0)

    def test_consumer_sentiment_at_1000(self):
        """Univ. of Michigan Consumer Sentiment at 10:00 ET."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Consumer Sentiment') == dt_time(10, 0)

    def test_fomc_at_1400(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time(
            'FOMC Statement of Economic Projections'
        ) == dt_time(14, 0)

    def test_treasury_international_at_1600(self):
        """TIC report releases at 4 PM ET — afternoon, not morning."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time(
            'Treasury International Capital'
        ) == dt_time(16, 0)

    def test_unknown_release_returns_none(self):
        """Long-tail / unrecognised releases stay TBD until added."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('Quarterly Sock Index') is None

    def test_empty_string_returns_none(self):
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('') is None
        assert lookup_canonical_release_time(None) is None

    def test_substring_match_is_case_insensitive(self):
        """The match should fire on partial-name + any case combination."""
        from gcp.fetchers.fetch_economic_events import lookup_canonical_release_time
        assert lookup_canonical_release_time('CPI - All Urban Consumers') is None  # 'CPI' not in keyword list
        assert lookup_canonical_release_time(
            'consumer price index for june 2026'
        ) == dt_time(8, 30)


# ── Sanity: the JSON loader is gone ─────────────────────────────────────────


def test_load_events_from_json_removed():
    """Regression: the JSON loader was removed when we deleted the
    static market_events.csv. Importing it should now fail — the
    fetcher relies on FRED + ForexFactory only."""
    from gcp.fetchers import fetch_economic_events
    assert not hasattr(fetch_economic_events, 'load_events_from_json')
