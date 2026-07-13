"""Hermetic tests for the hourly most-active snapshot mode
(`--intraday-snapshot`) on gcp/fetchers/fetch_top_movers.py.

The daily TOP_GAINERS_LOSERS path (`fetch_top_movers` / `main()` default
mode / `top_movers_daily`) must stay byte-identical — see
tests/test_phase2_fetchers.py::test_top_movers_parses_three_categories
for the pinned daily-path regression test.

Covers (per .superpowers/sdd/task-1-brief.md):
  - fixture AV response (20 valid most_actively_traded rows, incl. a
    negative-change row modeled on the confirmed wire sample) parses to
    exactly 20 rows with correct float/int coercion; one malformed row
    (garbage volume) is skipped, never fabricated
  - a single snapshot_ts is shared across the whole batch, tz-aware
  - snapshot_date is the ET calendar date of snapshot_ts, for both an
    evening-UTC run (20:30 UTC = 16:30 ET) and a midday-UTC run
    (13:30 UTC = 09:30 ET)
  - AV failure (Information payload / missing key / request exception)
    raises — no silent empty-success (Rule 3.7)
  - --dry-run parses/prints but never calls upsert_dataframe
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gcp.fetchers import fetch_top_movers as ftm


def _make_item(ticker, price, change_amount, change_percentage, volume):
    return {
        "ticker": ticker,
        "price": price,
        "change_amount": change_amount,
        "change_percentage": change_percentage,
        "volume": volume,
    }


def _build_fixture():
    """19 synthetic valid rows + the confirmed user wire sample (BURU,
    a positive-change row) = 20 valid rows, plus 1 malformed row with a
    garbage volume field that must be skipped (never fabricated as 0)."""
    items = []
    for i in range(1, 20):
        sign = "-" if i % 5 == 0 else ""  # every 5th row is a negative mover
        items.append(_make_item(
            f"TCK{i}",
            f"{10 + i}.{i:02d}",
            f"{sign}{i}.{i:02d}",
            f"{sign}{i}.{i:02d}%",
            str(1000000 * i),
        ))
    # confirmed user sample — exact wire shape, all-strings, positive change
    items.append(_make_item("BURU", "0.1516", "0.0104", "7.3654%", "72424171"))
    # malformed row: unparseable volume — must be skipped with a warning,
    # never fabricated as 0
    items.append({
        "ticker": "BADROW",
        "price": "1.23",
        "change_amount": "0.01",
        "change_percentage": "1.00%",
        "volume": "not-a-number",
    })
    return {
        "metadata": "Top gainers, losers, and most actively traded US tickers",
        "last_updated": "2026-07-12",
        "top_gainers": [],
        "top_losers": [],
        "most_actively_traded": items,
    }


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _make_fake_datetime(fake_now_utc):
    """Subclass datetime so `datetime.now(timezone.utc)` returns a fixed
    instant while everything else (constructors, isoformat, etc.) keeps
    working normally."""

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now_utc.replace(tzinfo=None)
            return fake_now_utc.astimezone(tz)

    return FakeDatetime


# ──────────────────────────────────────────────────────────────────────
# parsing
# ──────────────────────────────────────────────────────────────────────


def test_intraday_snapshot_parses_20_rows_with_correct_types():
    fixture = _build_fixture()
    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)):
        df = ftm.fetch_intraday_snapshot("fake-key")

    assert len(df) == 20
    assert "BADROW" not in set(df["ticker"])

    buru = df[df["ticker"] == "BURU"].iloc[0]
    assert buru["price"] == pytest.approx(0.1516)
    assert buru["change_amount"] == pytest.approx(0.0104)
    assert buru["change_pct"] == pytest.approx(7.3654)
    assert buru["volume"] == 72424171
    # Pandas widens the "volume" column to numpy int64 in the returned
    # DataFrame; the parser itself hands back a plain Python int per row
    # (see _parse_intraday_row) — assert the column's dtype is integral,
    # never float (a float volume would mean a fabricated/coerced value).
    import numpy as np
    assert np.issubdtype(df["volume"].dtype, np.integer)

    negative_row = df[df["ticker"] == "TCK5"].iloc[0]
    assert negative_row["change_pct"] == pytest.approx(-5.05)
    assert negative_row["change_amount"] == pytest.approx(-5.05)
    assert isinstance(negative_row["price"], float)


def test_intraday_snapshot_skips_malformed_row_with_warning(caplog):
    fixture = _build_fixture()
    with caplog.at_level("WARNING"):
        with patch("gcp.fetchers.fetch_top_movers.requests.get",
                   return_value=FakeResp(fixture)):
            df = ftm.fetch_intraday_snapshot("fake-key")

    assert "BADROW" not in set(df["ticker"])
    assert any("BADROW" in rec.message or "malformed" in rec.message.lower()
               for rec in caplog.records)


def test_intraday_snapshot_dedupes_repeated_tickers_keep_first(caplog):
    """When AlphaVantage returns the same ticker twice (different ranks),
    keep only the first occurrence (lower rank) and drop the second.
    A warning is logged so the dropped rows are visible (Rule 3.7).

    This protects against Postgres 21000 ("cannot affect row a second time")
    in the ON CONFLICT DO UPDATE when snapshot_ts is constant per batch.
    """
    fixture = _build_fixture()
    # Inject a duplicate: BURU appears again AFTER the original in the list.
    # The original BURU is at the end of _build_fixture (before BADROW).
    # We append the duplicate after BADROW so it gets a higher rank.
    fixture["most_actively_traded"].append(_make_item("BURU", "0.1520", "0.0108", "7.50%", "72500000"))

    # Manually confirm fixture has two BURU entries before calling the function
    buru_count_before = sum(1 for item in fixture["most_actively_traded"] if item.get("ticker") == "BURU")
    assert buru_count_before == 2, f"Setup: expected 2 BURU entries, got {buru_count_before}"

    with caplog.at_level("WARNING"):
        with patch("gcp.fetchers.fetch_top_movers.requests.get",
                   return_value=FakeResp(fixture)):
            df = ftm.fetch_intraday_snapshot("fake-key")

    # After dedup, only 1 BURU row should remain (the first/lowest-rank occurrence)
    buru_rows = df[df["ticker"] == "BURU"]
    assert len(buru_rows) == 1, f"Expected 1 BURU row after dedup, got {len(buru_rows)}"

    # The kept row should be the first occurrence (original BURU with original price)
    buru = buru_rows.iloc[0]
    assert buru["price"] == pytest.approx(0.1516), "Kept row should have original BURU price (first occurrence)"

    # Should have logged a warning about the duplicate
    assert any("deduplicated" in rec.message.lower() or ("duplicate" in rec.message.lower() and "repeated" in rec.message.lower())
               for rec in caplog.records), \
        f"Expected a warning about deduplication, got: {[r.message for r in caplog.records]}"


# ──────────────────────────────────────────────────────────────────────
# single snapshot_ts / ET snapshot_date
# ──────────────────────────────────────────────────────────────────────


def test_intraday_snapshot_single_ts_across_batch():
    fixture = _build_fixture()
    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)):
        df = ftm.fetch_intraday_snapshot("fake-key")

    assert df["snapshot_ts"].nunique() == 1
    ts = df["snapshot_ts"].iloc[0]
    assert ts.tzinfo is not None, "snapshot_ts must be tz-aware (UTC)"


def test_intraday_snapshot_et_date_evening_utc_run():
    """20:30 UTC = 16:30 ET on the same calendar day."""
    fixture = _build_fixture()
    fake_now = datetime(2026, 7, 10, 20, 30, tzinfo=timezone.utc)
    FakeDatetime = _make_fake_datetime(fake_now)

    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)), \
         patch("gcp.fetchers.fetch_top_movers.datetime", FakeDatetime):
        df = ftm.fetch_intraday_snapshot("fake-key")

    assert df["snapshot_date"].iloc[0].isoformat() == "2026-07-10"


def test_intraday_snapshot_et_date_midday_utc_run():
    """13:30 UTC = 09:30 ET on the same calendar day."""
    fixture = _build_fixture()
    fake_now = datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc)
    FakeDatetime = _make_fake_datetime(fake_now)

    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)), \
         patch("gcp.fetchers.fetch_top_movers.datetime", FakeDatetime):
        df = ftm.fetch_intraday_snapshot("fake-key")

    assert df["snapshot_date"].iloc[0].isoformat() == "2026-07-10"


def test_intraday_snapshot_et_date_crosses_midnight_boundary():
    """02:30 UTC = 22:30 ET the PRIOR calendar day — the case that would
    break under a naive UTC-date assumption."""
    fixture = _build_fixture()
    fake_now = datetime(2026, 7, 11, 2, 30, tzinfo=timezone.utc)
    FakeDatetime = _make_fake_datetime(fake_now)

    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)), \
         patch("gcp.fetchers.fetch_top_movers.datetime", FakeDatetime):
        df = ftm.fetch_intraday_snapshot("fake-key")

    assert df["snapshot_date"].iloc[0].isoformat() == "2026-07-10"


# ──────────────────────────────────────────────────────────────────────
# AV failure → raise, never a silent empty success
# ──────────────────────────────────────────────────────────────────────


def test_intraday_snapshot_raises_on_information_payload():
    fixture = {"Information": "rate limit hit"}
    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)):
        with pytest.raises(Exception):
            ftm.fetch_intraday_snapshot("fake-key")


def test_intraday_snapshot_raises_on_missing_key():
    fixture = {"top_gainers": [], "top_losers": []}  # no most_actively_traded
    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)):
        with pytest.raises(Exception):
            ftm.fetch_intraday_snapshot("fake-key")


def test_intraday_snapshot_raises_on_request_exception():
    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               side_effect=ConnectionError("boom")):
        with pytest.raises(Exception):
            ftm.fetch_intraday_snapshot("fake-key")


# ──────────────────────────────────────────────────────────────────────
# --dry-run writes nothing
# ──────────────────────────────────────────────────────────────────────


def test_intraday_dry_run_writes_nothing(monkeypatch, capsys):
    fixture = _build_fixture()
    monkeypatch.setenv("AV_API_KEY", "fake-key")

    captured_upsert = {"called": False}

    def fake_upsert(*a, **kw):
        captured_upsert["called"] = True
        return 999  # would prove the guard failed if this leaked through

    monkeypatch.setattr(ftm, "upsert_dataframe", fake_upsert)
    monkeypatch.setattr(ftm, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(sys, "argv",
                         ["fetch_top_movers.py", "--intraday-snapshot", "--dry-run"])

    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp(fixture)):
        ftm.main()

    assert captured_upsert["called"] is False
    out = capsys.readouterr().out
    assert "dry-run" in out
