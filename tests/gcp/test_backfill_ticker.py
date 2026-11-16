"""Unit tests for gcp/backfill_ticker.py.

Lightweight suite — most of the file calls AlphaVantage and Cloud SQL,
which we don't mock for unit tests. The tests here lock down:

  * ``_parse_dates`` — env-var date parsing edge cases
  * ``add_to_watchlist`` — uses the actual schema column names
    (``user_id`` / ``ticker`` / ``added_at`` / ``removed_at``,
    composite PK on (user_id, ticker)). This is a regression
    test for the ``column "created_at" does not exist`` failure
    caught on the first NVDA smoke run.
  * ``av_news_to_rows`` — explosion + sentiment mapping
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── Date parsing ──────────────────────────────────────────────────────────


def test_parse_dates_default_returns_7_weekdays():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates(None)
    assert len(out) == 7
    # All weekdays
    assert all(d.weekday() < 5 for d in out)
    # Sorted ascending
    assert out == sorted(out)


def test_parse_dates_comma_separated():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("2026-04-23,2026-04-24")
    assert out == [date(2026, 4, 23), date(2026, 4, 24)]


def test_parse_dates_semicolon_separated():
    """Semicolon support — gcloud --update-env-vars uses comma as its
    own delimiter, so multi-date BACKFILL_DATES values must use
    semicolons to pass through cleanly."""
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("2026-04-23;2026-04-24;2026-04-22")
    assert out == [date(2026, 4, 22), date(2026, 4, 23), date(2026, 4, 24)]


def test_parse_dates_whitespace():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("  2026-04-23   2026-04-24  ")
    assert out == [date(2026, 4, 23), date(2026, 4, 24)]


def test_parse_dates_dedupes():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("2026-04-23,2026-04-23,2026-04-23")
    assert out == [date(2026, 4, 23)]


# ── add_to_watchlist schema regression ───────────────────────────────────


def test_add_to_watchlist_uses_correct_columns():
    """Regression for the live failure on backfill-ticker-kddj4
    (NVDA smoke run): the INSERT used a non-existent ``created_at``
    column. The actual schema has ``added_at`` (defaulted) and
    ``removed_at`` (for soft delete), with composite PK
    (user_id, ticker). This test pins the SQL shape so future edits
    don't drift back to the wrong columns."""
    from gcp import backfill_ticker

    captured_sql: list[str] = []
    captured_params: list[dict] = []

    fake_conn = MagicMock()

    def fake_execute(stmt, params=None):
        captured_sql.append(str(stmt))
        if params is not None:
            captured_params.append(dict(params))
        return MagicMock()

    fake_conn.execute.side_effect = fake_execute
    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        backfill_ticker.add_to_watchlist("AMD")

    assert len(captured_sql) == 1
    sql = captured_sql[0]

    # Real column names from gcp/schema.sql watchlists table
    assert "user_id" in sql
    assert "ticker" in sql
    assert "removed_at" in sql
    # Wrong column name caught in production
    assert "created_at" not in sql
    # Composite-PK conflict target
    assert "ON CONFLICT (user_id, ticker)" in sql
    # Param has the upper-cased ticker
    assert captured_params[0]["t"] == "AMD"


def test_add_to_watchlist_uppercases_ticker():
    """Lowercase input must be normalised to upper before hitting SQL."""
    from gcp import backfill_ticker

    captured_params: list[dict] = []
    fake_conn = MagicMock()
    fake_conn.execute.side_effect = lambda stmt, params=None: (
        captured_params.append(dict(params)) if params else None
    )
    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        backfill_ticker.add_to_watchlist("nvda")

    assert captured_params[0]["t"] == "NVDA"


# ── av_news_to_rows ──────────────────────────────────────────────────────


def test_av_news_to_rows_explodes_per_ticker_sentiment():
    from gcp.backfill_ticker import av_news_to_rows
    feed = [
        {
            "time_published": "20260423T130000",
            "title": "AMD/Google deal closes",
            "url": "https://example.com/news",
            "summary": "AMD GOOGL announce deal",
            "source": "TestWire",
            "overall_sentiment_score": 0.45,
            "overall_sentiment_label": "Bullish",
            "topics": [{"topic": "Mergers & Acquisitions",
                        "relevance_score": "0.8"}],
            "ticker_sentiment": [
                {"ticker": "AMD", "ticker_sentiment_score": "0.5",
                 "relevance_score": "0.9"},
                {"ticker": "GOOGL", "ticker_sentiment_score": "0.3",
                 "relevance_score": "0.7"},
            ],
        },
    ]
    rows = av_news_to_rows(feed)
    # 1 article × 2 tickers → 2 rows
    assert len(rows) == 2
    by_ticker = {r["ticker"]: r for r in rows}
    assert "AMD" in by_ticker and "GOOGL" in by_ticker
    assert by_ticker["AMD"]["sentiment_score"] == 0.5
    assert by_ticker["GOOGL"]["sentiment_score"] == 0.3
    # Both share the same overall sentiment + topics
    assert by_ticker["AMD"]["overall_sentiment_score"] == 0.45
    assert by_ticker["AMD"]["topics"] == ["Mergers & Acquisitions"]


def test_av_news_to_rows_skips_unparseable_timestamp_and_says_so(caplog):
    """An article the vendor stamps unparseably is dropped (EXTERNAL data),
    never silently: the skip is logged with the raw value and the count."""
    import logging
    from gcp.backfill_ticker import av_news_to_rows
    feed = [{"time_published": "garbage", "ticker_sentiment": [
        {"ticker": "AMD"}
    ]}]
    with caplog.at_level(logging.WARNING, logger="gcp.backfill_ticker"):
        assert av_news_to_rows(feed) == []
    assert "garbage" in caplog.text and "1 " in caplog.text and "skipped" in caplog.text.lower()


def test_ftfc_is_never_fabricated_by_the_daily_writers():
    """`float(ftfc_score) if ftfc_score is not None else 0.0` and
    `ftfc_dir or 'mixed'` wrote a neutral reading where there was none
    (CLAUDE.md 3.7 pattern 4), in both daily writers."""
    import re
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    for rel in ("gcp/backfill_ticker.py", "gcp/fetchers/fetch_market_data.py"):
        src = (repo / rel).read_text()
        assert not re.search(r"ftfc_score\) if ftfc_score is not None else 0\.0", src), rel
        assert not re.search(r"ftfc_dir or ['\"]mixed['\"]", src), rel
        assert not re.search(r"abs\(ftfc_score or 0\.0\)", src), rel


def test_av_news_to_rows_tagged_data_source():
    from gcp.backfill_ticker import av_news_to_rows
    feed = [{
        "time_published": "20260423T130000",
        "ticker_sentiment": [{"ticker": "AMD",
                              "ticker_sentiment_score": "0.2",
                              "relevance_score": "0.5"}],
    }]
    rows = av_news_to_rows(feed)
    assert rows[0]["data_source"] == "alphavantage"
    assert rows[0]["match_method"] == "av_ticker_sentiment"


# ── Watchlist opt-in (Codex on #1022; FEAT-INSIGHT-001 stage A) ──────────
#
# run() once unconditionally called add_to_watchlist(), which inserts the
# ticker into the shared `default` watchlist or clears removed_at on a
# deliberately removed one. #1022 made BACKFILL_ADD_TO_WATCHLIST=false the
# opt-out for scripts/backfill_and_replay.py's historical-test tickers, with
# the default still true. Since the default list is exactly SPY, QQQ and IWM
# (owner's decision 1, 2026-11-13), a Discord /replay on a ticker with no
# daily data must not undo a removal one ticker at a time, so the default is
# now false (owner's decision 2) and an operator opts in with "true" on one
# execution. The comparison stays `.lower() == "true"`: TRUE opts in, yes
# does not (Review Focus 5 of the stage A plan).


@pytest.fixture
def stubbed_run(monkeypatch):
    """Stub every network/DB touch in run() and return the add_to_watchlist mock."""
    import pandas as pd
    import gcp.backfill_ticker as mod

    monkeypatch.setenv("BACKFILL_TICKER", "amd")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("BACKFILL_DATES", "2026-04-24")
    monkeypatch.setenv("BACKFILL_INCLUDE_NEWS", "false")
    daily = pd.DataFrame({
        "date": [date(2026, 4, 23), date(2026, 4, 24)],
        "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
        "close": [1.0, 1.0], "adjusted_close": [1.0, 1.0], "volume": [1, 1],
    })
    watch = MagicMock()
    with patch.object(mod, "av_daily_full", return_value=daily), \
         patch.object(mod, "compute_indicators_for_full_range", return_value=0), \
         patch.object(mod, "compute_indicators_for_dates"), \
         patch.object(mod, "add_to_watchlist", watch), \
         patch("gcp.database.upsert_dataframe"):
        yield mod, watch


def test_watchlist_add_is_off_by_default(stubbed_run, monkeypatch, caplog):
    """With the variable unset a backfill leaves watchlists untouched and says so."""
    import logging

    mod, watch = stubbed_run
    monkeypatch.delenv("BACKFILL_ADD_TO_WATCHLIST", raising=False)
    # The module logs under "backfill-ticker" (gcp/backfill_ticker.py:69), not its dotted path.
    with caplog.at_level(logging.INFO, logger="backfill-ticker"):
        assert mod.run() == 0
    watch.assert_not_called()
    assert "BACKFILL_ADD_TO_WATCHLIST=false" in caplog.text


def test_watchlist_add_can_be_opted_in(stubbed_run, monkeypatch):
    mod, watch = stubbed_run
    monkeypatch.setenv("BACKFILL_ADD_TO_WATCHLIST", "true")
    assert mod.run() == 0
    watch.assert_called_once_with("AMD")


@pytest.mark.parametrize("value, opted_in", [
    ("TRUE", True), ("True", True), ("false", False), ("yes", False), ("1", False),
])
def test_watchlist_add_opt_in_is_case_insensitive(stubbed_run, monkeypatch, value, opted_in):
    """`.lower() == "true"`: any spelling of true opts in; yes and 1 do not."""
    mod, watch = stubbed_run
    monkeypatch.setenv("BACKFILL_ADD_TO_WATCHLIST", value)
    assert mod.run() == 0
    assert watch.call_count == (1 if opted_in else 0), (value, watch.call_args_list)


# ── The job fetches and writes no 1-minute bars (FEAT-DATA-001) ──────────
#
# Owner's rule, 2026-11-13: 1-minute bars reach market_data_intraday only
# through the two fetcher modules. This job used to pull a whole month of
# them from AlphaVantage per month touched and upsert about 20,000 rows; it
# now reads the bars the table already holds for its premarket step and
# says so once per run.

NO_BAR_FETCH_LINE = (
    "1-min bars are not fetched by this job; premarket context reads market_data_intraday")


def test_run_fetches_and_writes_no_one_minute_bars(monkeypatch, caplog):
    """run() sends the daily request (and the news request when asked) and
    nothing else, and upserts market_data_daily and nothing else. The vendor
    is answered for TIME_SERIES_INTRADAY too, so code that still asked for
    bars would run to its end and fail here on what it sent and wrote, not
    on a vendor error."""
    import logging

    import gcp.backfill_ticker as mod

    monkeypatch.setenv("BACKFILL_TICKER", "amd")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("BACKFILL_DATES", "2026-04-24")
    monkeypatch.setenv("BACKFILL_ADD_TO_WATCHLIST", "false")

    def daily_bar(close):
        return {"1. open": "100.0", "2. high": "101.0", "3. low": "99.0",
                "4. close": str(close), "5. adjusted close": str(close),
                "6. volume": "1000"}

    answers = {
        "TIME_SERIES_DAILY_ADJUSTED": {"Time Series (Daily)": {
            "2026-04-23": daily_bar(100.5), "2026-04-24": daily_bar(100.7)}},
        "NEWS_SENTIMENT": {"feed": []},
        "TIME_SERIES_INTRADAY": {"Time Series (1min)": {"2026-04-24 09:30:00": {
            "1. open": "100.0", "2. high": "100.1", "3. low": "99.9",
            "4. close": "100.05", "5. volume": "500"}}},
    }

    def refuse_watchlist(ticker):
        raise AssertionError(f"add_to_watchlist({ticker!r}) called with the variable set to false")

    for include_news, expected in (
            ("false", ["TIME_SERIES_DAILY_ADJUSTED"]),
            ("true", ["TIME_SERIES_DAILY_ADJUSTED", "NEWS_SENTIMENT"])):
        monkeypatch.setenv("BACKFILL_INCLUDE_NEWS", include_news)
        caplog.clear()
        seen: list[str] = []
        written: list[tuple] = []

        def fake_get(url, params=None, **kw):
            seen.append(params["function"])
            response = MagicMock()
            response.json.return_value = answers[params["function"]]
            return response

        full_range, per_date = MagicMock(return_value=0), MagicMock()
        with patch.object(mod.requests, "get", side_effect=fake_get), \
             patch("gcp.database.upsert_dataframe",
                   side_effect=lambda frame, table, *a, **k: written.append((table, frame))), \
             patch.object(mod, "add_to_watchlist", refuse_watchlist), \
             patch.object(mod, "compute_indicators_for_full_range", full_range), \
             patch.object(mod, "compute_indicators_for_dates", per_date), \
             caplog.at_level(logging.INFO, logger="backfill-ticker"):
            assert mod.run() == 0

        tables = [table for table, _frame in written]
        assert seen == expected, (include_news, seen, tables)
        assert "TIME_SERIES_INTRADAY" not in seen
        assert tables == ["market_data_daily"], (include_news, tables)
        daily = written[0][1]
        assert list(daily["date"]) == [date(2026, 4, 23), date(2026, 4, 24)]
        assert list(daily["ticker"]) == ["AMD", "AMD"]
        assert list(daily["data_source"]) == ["alphavantage", "alphavantage"]
        said = [r for r in caplog.records
                if r.levelno == logging.INFO and r.getMessage() == NO_BAR_FETCH_LINE]
        assert len(said) == 1, [r.getMessage() for r in caplog.records]
        full_range.assert_called_once_with("AMD")
        # the date and its prior weekday
        per_date.assert_called_once_with("AMD", [date(2026, 4, 23), date(2026, 4, 24)])

    assert not hasattr(mod, "av_intraday_month")


def test_a_non_string_vendor_timestamp_is_dropped_not_raised(caplog):
    """`time_published` is vendor JSON, so its TYPE is not ours to assume.
    A number or a list made `pub_raw[:15]` raise TypeError, which this path
    did not catch: the exception left av_news_to_rows(), failed the whole
    backfill-ticker run, and took the indicator and options steps down with
    it (Codex on #1022). A malformed article is EXTERNAL data: drop it,
    count it, keep going."""
    import logging

    from gcp.backfill_ticker import av_news_to_rows

    feed = [
        {"time_published": 20260908, "ticker_sentiment": [{"ticker": "AMD"}]},
        {"time_published": ["20260908T120000"], "ticker_sentiment": [{"ticker": "AMD"}]},
        {"time_published": {"t": 1}, "ticker_sentiment": [{"ticker": "AMD"}]},
        {"time_published": "20260908T120000", "title": "kept",
         "ticker_sentiment": [{"ticker": "AMD"}]},
    ]
    with caplog.at_level(logging.WARNING, logger="gcp.backfill_ticker"):
        rows = av_news_to_rows(feed)
    assert [r["ticker"] for r in rows] == ["AMD"], "the well-formed article must survive"
    # The dict case is the one that made the exception type interpreter-
    # dependent: `{"t": 1}[:15]` is a TypeError on 3.11 and a KeyError on
    # 3.12, where slices became hashable. The parser checks the type instead
    # of listing what slicing a wrong one throws, so neither is reachable.
    assert "isinstance(pub_raw, str)" in __import__("inspect").getsource(
        __import__("gcp.backfill_ticker", fromlist=["av_news_to_rows"])), \
        "the guard must be a type check, not an except clause"
    assert "3" in caplog.text and "skipped" in caplog.text.lower()
    assert "20260908" in caplog.text, "the skip log must name what was dropped"


def test_a_non_list_vendor_collection_is_dropped_not_raised(caplog):
    """The scalar fields were type-checked but the CONTAINERS were not:
    `(art.get("topics") or [])` keeps a truthy non-list, so a vendor
    `topics: 42` or `ticker_sentiment: 42` raised TypeError out of
    av_news_to_rows and failed the whole backfill run (Codex on #1022)."""
    import logging

    from gcp.backfill_ticker import av_news_to_rows

    feed = [
        {"time_published": "20260908T120000", "topics": 42,
         "ticker_sentiment": [{"ticker": "AMD"}]},
        {"time_published": "20260908T120100", "ticker_sentiment": 42},
        {"time_published": "20260908T120200", "ticker_sentiment": "AMD"},
        {"time_published": "20260908T120300", "title": "kept",
         "ticker_sentiment": [{"ticker": "NVDA"}]},
    ]
    with caplog.at_level(logging.WARNING, logger="gcp.backfill_ticker"):
        rows = av_news_to_rows(feed)
    assert sorted(r["ticker"] for r in rows) == ["AMD", "NVDA"]
    assert "topics" in caplog.text and "ticker_sentiment" in caplog.text


def test_a_non_mapping_feed_entry_is_dropped_not_raised():
    """Field-level validation cannot save a malformed CONTAINER.

    `for art in feed: art.get(...)` raises AttributeError on a feed entry
    that is None, a number, a string or a list, and that aborts the whole
    backfill-ticker execution — indicators and every remaining step with
    it. One bad article must be dropped and counted, not stop the run
    (EXTERNAL data, CLAUDE.md 3.7; Codex on #1022, round 23)."""
    from gcp.backfill_ticker import av_news_to_rows

    good = {
        "time_published": "20260902T130000",
        "title": "t", "url": "u", "source": "s",
        "overall_sentiment_score": 0.5,
        "topics": [{"topic": "Earnings"}],
        "ticker_sentiment": [
            {"ticker": "AMD", "relevance_score": "0.9",
             "ticker_sentiment_score": "0.4", "ticker_sentiment_label": "Bullish"},
        ],
    }
    feed = [None, 42, "AMD", ["AMD"], good]
    rows = av_news_to_rows(feed)
    assert [r["ticker"] for r in rows] == ["AMD"], rows


# ── Premarket filter reads the prior session's ATR (no look-ahead) ──────


def _backfill_premarket_row(monkeypatch, target_high: float, target_low: float) -> dict:
    """Run compute_indicators_for_dates for one date on stubbed reads and
    return the row it upserts. Only the target date's daily high and low
    vary between calls."""
    import pandas as pd
    import gcp.database as db
    from gcp import backfill_ticker as mod

    fd = date(2026, 11, 6)
    days = pd.bdate_range(end=pd.Timestamp(fd), periods=60)
    rows = []
    for i, d in enumerate(days):
        base = 100.0 + 0.01 * i
        hi, lo = (target_high, target_low) if d.date() == fd else (base + 0.5, base - 0.5)
        rows.append({"date": d.date(), "Open": base, "High": hi, "Low": lo,
                     "Close": base, "Volume": 1_000_000})
    daily_asc = pd.DataFrame(rows)
    daily_desc = daily_asc.iloc[::-1].reset_index(drop=True)

    # 08:00 to 08:29 ET premarket bars near the prior close, one of which
    # wicks 1.5 above its body: past half the prior ATR (about 1.0), inside
    # half of an ATR the target day's own wide range inflates.
    start = pd.Timestamp("2026-11-06 08:00", tz="America/New_York").tz_convert("UTC")
    ts = pd.Series([start + pd.Timedelta(minutes=m) for m in range(30)])
    o = pd.Series([100.6] * 30)
    c = pd.Series([100.62] * 30)
    h = pd.Series([100.65] * 30)
    lw = pd.Series([100.55] * 30)
    h.iloc[15] = 102.2
    ibars = pd.DataFrame({"ts": ts, "open": o, "high": h, "low": lw,
                          "close": c, "volume": [1000] * 30})

    def fake_query(sql, params=None):
        # The daily read only: the bar read is strict (FEAT-DATA-001).
        assert "market_data_daily" in sql, f"not the daily read: {sql}"
        return daily_desc.copy()

    def fake_strict(sql, params=None, timeout_s=None):
        assert "market_data_intraday" in sql, f"not the premarket bar read: {sql}"
        return ibars.copy()

    written = []
    monkeypatch.setattr(db, "query_to_dataframe", fake_query)
    # Set before install_level_params, which passes every strict query but
    # its own to the reader already in place.
    monkeypatch.setattr(db, "query_to_dataframe_strict", fake_strict)
    monkeypatch.setattr(db, "upsert_dataframe", lambda frame, *a, **k: written.append(frame))
    # SPY's print thresholds in force on fd (per-ticker parameters,
    # 2026-11-08), here at the #1753 values.
    from tests.lib.level_params_fixtures import install_level_params
    install_level_params(monkeypatch, ["SPY"])
    mod.compute_indicators_for_dates("SPY", [fd])
    assert len(written) == 1
    return written[0].iloc[0].to_dict()


def test_backfill_premarket_ignores_the_target_sessions_own_range(monkeypatch):
    """stocks#1753 review: the backfill passed the target date's completed
    ATR(14) to the premarket filter, so that session's regular-hours range
    decided which premarket prints survived. With the prior session's ATR,
    the persisted premarket extremes and VWAP do not depend on it."""
    calm = _backfill_premarket_row(monkeypatch, 100.6 + 0.5, 100.6 - 0.5)
    wild = _backfill_premarket_row(monkeypatch, 100.6 + 40.0, 100.6 - 40.0)
    for key in ("pre_high", "pre_low", "pre_vwap"):
        assert calm.get(key) == wild.get(key), key
    # The 102.2 wick is a spike under the prior ATR, so it never sets pre_high.
    assert calm["pre_high"] < 101.0


def test_backfill_premarket_passes_the_prior_session_inputs(monkeypatch):
    import lib.indicators as ind

    seen = {}
    real = ind.calculate_premarket_context

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(ind, "calculate_premarket_context", spy)
    _backfill_premarket_row(monkeypatch, 100.6 + 40.0, 100.6 - 40.0)
    # The prior session: open and close 100.58, a one-point range, so its
    # ATR(14) is about 1.0, far below the target day's 80-point bar.
    assert seen["prev_close"] == pytest.approx(100.58)
    assert seen["prev_open"] == pytest.approx(100.58)
    assert seen["atr"] == pytest.approx(1.0, abs=0.05)
    assert seen["stale_print_atr"] == 0.1 and seen["spike_atr"] == 0.5


# ── The premarket bar read is strict (FEAT-DATA-001) ─────────────────────
#
# The read went through gcp.database.query_to_dataframe, which answers an
# outage with an empty frame, inside a try whose except only logged. So
# "the table holds no premarket bars for this date" and "the database is
# down" both wrote the day's row without premarket fields and said nothing
# about the table. Now the read is gcp.database.query_to_dataframe_strict
# outside that try: zero rows is a logged fact, a failed read ends the run.

D4, D5, D6 = date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)


def _premarket_reads(monkeypatch, bar_answer):
    """Stub every read and write of compute_indicators_for_dates.

    ``bar_answer(day, bars)`` answers the premarket bar read of ``day`` with a
    frame, or raises; ``bars(day)`` is 30 one-minute bars from 08:00 Eastern
    of that day. Returns a namespace with

      written              (table, frame) of every upsert, in call order
      bar_reads            the bar reads asked of the strict reader, by date
      swallowed_bar_reads  the same reads asked of the swallowing reader
    """
    import types

    import pandas as pd
    import gcp.database as db
    from tests.lib.level_params_fixtures import install_level_params

    days = pd.bdate_range(end=pd.Timestamp(D6), periods=60)
    daily_asc = pd.DataFrame([
        {"date": d.date(), "Open": 100.0 + 0.01 * i, "High": 100.0 + 0.01 * i + 0.5,
         "Low": 100.0 + 0.01 * i - 0.5, "Close": 100.0 + 0.01 * i, "Volume": 1_000_000}
        for i, d in enumerate(days)
    ])

    def bars(day):
        start = pd.Timestamp(f"{day.isoformat()} 08:00", tz="America/New_York").tz_convert("UTC")
        return pd.DataFrame({
            "ts": [start + pd.Timedelta(minutes=m) for m in range(30)],
            "open": [100.6] * 30, "high": [100.65] * 30, "low": [100.55] * 30,
            "close": [100.62] * 30, "volume": [1000] * 30,
        })

    out = types.SimpleNamespace(written=[], bar_reads=[], swallowed_bar_reads=[])

    def bar_read(recorded, params):
        day = pd.Timestamp(params["start"]).tz_convert("America/New_York").date()
        recorded.append(day)
        return bar_answer(day, bars)

    def swallowing(sql, params=None):
        if "market_data_intraday" in sql:
            return bar_read(out.swallowed_bar_reads, params)
        assert "market_data_daily" in sql, f"not a read this job makes: {sql}"
        upto = date.fromisoformat(params["fd"])
        kept = daily_asc[daily_asc["date"] <= upto]
        return kept.iloc[::-1].reset_index(drop=True)

    def strict(sql, params=None, timeout_s=None):
        assert "market_data_intraday" in sql, f"not the premarket bar read: {sql}"
        return bar_read(out.bar_reads, params)

    monkeypatch.setattr(db, "query_to_dataframe", swallowing)
    monkeypatch.setattr(db, "query_to_dataframe_strict", strict)
    install_level_params(monkeypatch, ["SPY", "AMD"])
    monkeypatch.setattr(
        db, "upsert_dataframe", lambda frame, table, *a, **k: out.written.append((table, frame)))
    return out


def _job_warnings(caplog):
    import logging
    return [r.getMessage() for r in caplog.records
            if r.name == "backfill-ticker" and r.levelno == logging.WARNING]


def test_premarket_absent_bars_says_so(monkeypatch, caplog):
    """Zero premarket rows is a fact about the table, and the log now says
    it: the row is written without premarket fields, as before, and one
    warning names the table, the ticker and the date."""
    import logging

    from gcp import backfill_ticker as mod

    reads = _premarket_reads(monkeypatch, lambda day, bars: __import__("pandas").DataFrame())
    with caplog.at_level(logging.INFO, logger="backfill-ticker"):
        mod.compute_indicators_for_dates("SPY", [D6])

    assert [table for table, _frame in reads.written] == ["market_data_daily"]
    frame = reads.written[0][1]
    assert len(frame) == 1 and frame["date"].iloc[0] == D6
    assert [c for c in frame.columns if c.startswith("pre_")] == []
    assert "gap_pct" not in frame.columns
    assert [m for m in _job_warnings(caplog) if "market_data_intraday" in m] == [
        "no 1-min bars in market_data_intraday for SPY premarket 2026-11-06; pre_* not written"]
    assert reads.bar_reads == [D6]
    assert reads.swallowed_bar_reads == []


def test_premarket_read_failure_fails_the_run(monkeypatch):
    """A failed bar read ends the run with the exception as raised, outage
    or defect alike: neither is turned into "no bars". The rows of the dates
    before it stay, the failing date and the later dates get no row, no read
    is made for a later date, and under run() the watchlist row is not
    written."""
    import pandas as pd

    from gcp import backfill_ticker as mod
    from lib.infra_errors import is_infrastructure_error

    outage, defect = ConnectionError("connection refused"), KeyError("close")
    assert is_infrastructure_error(outage) is True
    assert is_infrastructure_error(defect) is False

    for exc in (outage, defect):
        def fail_on_d5(day, bars, exc=exc):
            if day == D5:
                raise exc
            return bars(day)

        reads = _premarket_reads(monkeypatch, fail_on_d5)
        with pytest.raises(type(exc)) as excinfo:
            mod.compute_indicators_for_dates("SPY", [D4, D5, D6])
        assert excinfo.value is exc
        assert [table for table, _frame in reads.written] == ["market_data_daily"]
        kept = reads.written[0][1]
        assert list(kept["date"]) == [D4]
        assert {"pre_high", "pre_low", "pre_vwap", "pre_volume"} <= set(kept.columns)
        assert reads.bar_reads == [D4, D5]
        assert reads.swallowed_bar_reads == []

        # The same failure under run(): 2026-11-05 and 2026-11-06 make the
        # target dates 2026-11-04 to 2026-11-06.
        monkeypatch.setenv("BACKFILL_TICKER", "amd")
        monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
        monkeypatch.setenv("BACKFILL_DATES", "2026-11-05,2026-11-06")
        monkeypatch.setenv("BACKFILL_INCLUDE_NEWS", "false")
        monkeypatch.setenv("BACKFILL_ADD_TO_WATCHLIST", "true")
        daily = pd.DataFrame({
            "date": [D5, D6], "open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0],
            "close": [1.0, 1.0], "adjusted_close": [1.0, 1.0], "volume": [1, 1],
        })
        watch = MagicMock()
        reads = _premarket_reads(monkeypatch, fail_on_d5)
        with patch.object(mod, "av_daily_full", return_value=daily), \
             patch.object(mod, "compute_indicators_for_full_range", return_value=0), \
             patch.object(mod, "add_to_watchlist", watch), \
             pytest.raises(type(exc)) as excinfo:
            mod.run()
        assert excinfo.value is exc
        assert watch.call_count == 0
        assert len(reads.written[0][1]) == 2, "step 1's daily rows come first"
        after_step_one = reads.written[1:]
        assert [table for table, _frame in after_step_one] == ["market_data_daily"]
        assert list(after_step_one[0][1]["date"]) == [D4]
        assert reads.bar_reads == [D4, D5]


def test_premarket_compute_defect_is_still_a_warning(monkeypatch, caplog):
    """Only the READ became strict. A defect in the premarket computation is
    still caught where it was and logged, and the row is still written
    without premarket fields: this pins that the except did not widen or
    narrow with the change."""
    import logging

    import lib.indicators as ind
    from gcp import backfill_ticker as mod

    def broken(*args, **kwargs):
        raise KeyError("close")

    monkeypatch.setattr(ind, "calculate_premarket_context", broken)
    reads = _premarket_reads(monkeypatch, lambda day, bars: bars(day))
    with caplog.at_level(logging.INFO, logger="backfill-ticker"):
        mod.compute_indicators_for_dates("SPY", [D6])

    assert [table for table, _frame in reads.written] == ["market_data_daily"]
    frame = reads.written[0][1]
    assert list(frame["date"]) == [D6]
    assert [c for c in frame.columns if c.startswith("pre_")] == []
    warnings_ = _job_warnings(caplog)
    assert len(warnings_) == 1, warnings_
    assert warnings_[0].startswith("pre-market compute failed"), warnings_


def test_premarket_absent_bars_warns_once_per_date_in_upper_case(monkeypatch, caplog):
    """Several dates with no bars and a lower-case ticker: one line per
    date, each naming the ticker in upper case, and every date's row is
    still upserted."""
    import logging

    import pandas as pd

    from gcp import backfill_ticker as mod

    reads = _premarket_reads(monkeypatch, lambda day, bars: pd.DataFrame())
    with caplog.at_level(logging.INFO, logger="backfill-ticker"):
        mod.compute_indicators_for_dates("spy", [D5, D6])

    assert [list(frame["date"]) for _table, frame in reads.written] == [[D5], [D6]]
    assert [m for m in _job_warnings(caplog) if "market_data_intraday" in m] == [
        "no 1-min bars in market_data_intraday for SPY premarket 2026-11-05; pre_* not written",
        "no 1-min bars in market_data_intraday for SPY premarket 2026-11-06; pre_* not written",
    ]


def test_bars_that_all_fail_the_print_filter_log_no_absent_warning(monkeypatch, caplog):
    """The table did hold bars; every one of them failed the print filter
    (bar_count 0). The row is written without premarket fields and the
    "no 1-min bars" line is NOT logged, because it would be false."""
    import logging

    import lib.indicators as ind
    from gcp import backfill_ticker as mod

    monkeypatch.setattr(ind, "calculate_premarket_context", lambda *a, **k: {"bar_count": 0})
    reads = _premarket_reads(monkeypatch, lambda day, bars: bars(day))
    with caplog.at_level(logging.INFO, logger="backfill-ticker"):
        mod.compute_indicators_for_dates("SPY", [D6])

    assert [list(frame["date"]) for _table, frame in reads.written] == [[D6]]
    assert [c for c in reads.written[0][1].columns if c.startswith("pre_")] == []
    assert [r.getMessage() for r in caplog.records if "no 1-min bars" in r.getMessage()] == []
