"""Tests for lib/broker_import.py — broker CSV import core (Task 2 of the
2026-07-11 journal one-stop-shop program; see
.superpowers/sdd/task-2-brief.md).

Covers: exact-header-set broker detection, Robinhood Description parsing,
Webull OCC-symbol parsing, FIFO round-trip pairing with partial closes,
percent-unit return_pct, and full skip-reason coverage (every dropped row
must land in ImportPreview.skipped with {raw_index, reason} — CLAUDE.md
Rule 3.7, no silent drops).
"""
from pathlib import Path

import pytest

from lib.broker_import import (
    NormalizedOrder,
    detect_broker,
    pair_orders,
    parse_csv,
)

FIXTURES = Path(__file__).parent / "fixtures" / "broker_csv"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# detect_broker
# ---------------------------------------------------------------------------

def test_detect_broker_robinhood():
    header = _read("robinhood_sample.csv").splitlines()[0]
    assert detect_broker(header) == "robinhood"


def test_detect_broker_webull():
    header = _read("webull_sample.csv").splitlines()[0]
    assert detect_broker(header) == "webull"


def test_detect_broker_none_for_random_header():
    assert detect_broker("Date,Ticker,Notes,Whatever") is None


# ---------------------------------------------------------------------------
# Robinhood Description parsing (parse_csv)
# ---------------------------------------------------------------------------

def test_robinhood_parses_open_and_close_rows():
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    # raw_index 0: BTO IWM 6/19/2026 Call $224.00, qty 2, price 1.42
    o0 = next(o for o in orders if o.raw_index == 0)
    assert o0.ticker == "IWM"
    assert o0.direction == "CALL"
    assert o0.action == "open"
    assert o0.ts == "2026-06-01 00:00"
    assert o0.price == pytest.approx(1.42)
    assert o0.quantity == 2

    # raw_index 1: STC same contract, qty 2, price 1.71
    o1 = next(o for o in orders if o.raw_index == 1)
    assert o1.ticker == "IWM"
    assert o1.direction == "CALL"
    assert o1.action == "close"
    assert o1.ts == "2026-06-03 00:00"
    assert o1.price == pytest.approx(1.71)

    # raw_index 2: BTO SPY Put
    o2 = next(o for o in orders if o.raw_index == 2)
    assert o2.ticker == "SPY"
    assert o2.direction == "PUT"
    assert o2.action == "open"


def test_robinhood_no_fill_time_uses_midnight():
    """Robinhood activity CSVs carry no fill time -> ts is '<date> 00:00'."""
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    for o in orders:
        if o.action in ("open", "close"):
            assert o.ts.endswith(" 00:00")


# ---------------------------------------------------------------------------
# Webull OCC parsing (parse_csv)
# ---------------------------------------------------------------------------

def test_webull_parses_occ_symbol_and_side():
    orders = parse_csv(_read("webull_sample.csv"), "webull")
    o0 = next(o for o in orders if o.raw_index == 0)
    assert o0.ticker == "IWM"
    assert o0.direction == "CALL"
    assert o0.action == "open"
    assert o0.ts == "2026-06-01 09:40"
    assert o0.price == pytest.approx(1.42)
    assert o0.quantity == 2

    o1 = next(o for o in orders if o.raw_index == 1)
    assert o1.action == "close"
    assert o1.ts == "2026-06-03 10:15"

    o2 = next(o for o in orders if o.raw_index == 2)
    assert o2.ticker == "SPY"
    assert o2.direction == "PUT"
    assert o2.action == "open"


# ---------------------------------------------------------------------------
# Skip coverage — every dropped row lands in skipped with a reason
# ---------------------------------------------------------------------------

def test_robinhood_short_option_and_equity_rows_are_skipped():
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    preview = pair_orders(orders)
    reasons = {s["reason"] for s in preview.skipped}
    assert "short options not supported" in reasons
    assert "shares — options only in v1" in reasons
    # raw_index 5 is the equity row, raw_index 6 is the short-option row
    by_index = {s["raw_index"]: s["reason"] for s in preview.skipped}
    assert by_index[5] == "shares — options only in v1"
    assert by_index[6] == "short options not supported"


def test_webull_short_option_and_equity_rows_are_skipped():
    orders = parse_csv(_read("webull_sample.csv"), "webull")
    preview = pair_orders(orders)
    by_index = {s["raw_index"]: s["reason"] for s in preview.skipped}
    assert by_index[5] == "shares — options only in v1"
    assert by_index[6] == "short options not supported"


def test_close_without_matching_open_is_skipped():
    orders = [
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="close",
            ts="2026-06-01 00:00", price=1.50, quantity=1, raw_index=0,
        ),
    ]
    preview = pair_orders(orders)
    assert preview.trades == []
    assert preview.skipped == [{"raw_index": 0, "reason": "close without matching open"}]


def test_every_skip_reason_present_across_full_pipeline():
    """Full RH pipeline exercises all three parse/pairing skip reasons."""
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    # Force a "close without matching open" by adding an extra close for a
    # ticker/direction that never had an open in this fixture.
    orders = orders + [
        NormalizedOrder(
            ticker="TSLA", direction="CALL", action="close",
            ts="2026-06-10 00:00", price=1.0, quantity=1, raw_index=99,
        )
    ]
    preview = pair_orders(orders)
    reasons = {s["reason"] for s in preview.skipped}
    assert reasons == {
        "shares — options only in v1",
        "short options not supported",
        "close without matching open",
    }


# ---------------------------------------------------------------------------
# FIFO pairing with partial closes (pair_orders — pure, synthetic orders)
# ---------------------------------------------------------------------------

def test_fifo_pairing_two_lots_one_close_leaves_one_active():
    """2 lots opened, 1 closed -> 1 closed + 1 active."""
    orders = [
        NormalizedOrder("IWM", "CALL", "open", "2026-06-01 00:00", 1.42, 1, 0),
        NormalizedOrder("IWM", "CALL", "open", "2026-06-02 00:00", 1.50, 1, 1),
        NormalizedOrder("IWM", "CALL", "close", "2026-06-03 00:00", 1.71, 1, 2),
    ]
    preview = pair_orders(orders)
    assert preview.skipped == []
    assert len(preview.trades) == 2
    closed = [t for t in preview.trades if t.status == "closed"]
    active = [t for t in preview.trades if t.status == "active"]
    assert len(closed) == 1 and len(active) == 1
    # FIFO: the FIRST lot opened (1.42) is the one that closes.
    assert closed[0].entry_price == pytest.approx(1.42)
    assert active[0].entry_price == pytest.approx(1.50)
    assert active[0].exit_ts is None
    assert active[0].exit_price is None
    assert active[0].return_pct is None
    assert active[0].quantity == 1


def test_fifo_pairing_close_spans_multiple_lots():
    """Open qty1 + open qty1, then one close qty2 -> both lots close."""
    orders = [
        NormalizedOrder("SPY", "PUT", "open", "2026-06-01 00:00", 3.00, 1, 0),
        NormalizedOrder("SPY", "PUT", "open", "2026-06-02 00:00", 3.20, 1, 1),
        NormalizedOrder("SPY", "PUT", "close", "2026-06-03 00:00", 2.90, 2, 2),
    ]
    preview = pair_orders(orders)
    assert preview.skipped == []
    assert len(preview.trades) == 2
    assert all(t.status == "closed" for t in preview.trades)
    entry_prices = sorted(t.entry_price for t in preview.trades)
    assert entry_prices == [pytest.approx(3.00), pytest.approx(3.20)]


def test_partial_close_leaves_remainder_of_same_lot_active():
    """Open qty2 in one lot, close qty1 -> 1 closed(qty1) + 1 active(qty1)."""
    orders = [
        NormalizedOrder("QQQ", "CALL", "open", "2026-06-01 00:00", 5.00, 2, 0),
        NormalizedOrder("QQQ", "CALL", "close", "2026-06-02 00:00", 6.00, 1, 1),
    ]
    preview = pair_orders(orders)
    assert preview.skipped == []
    closed = [t for t in preview.trades if t.status == "closed"]
    active = [t for t in preview.trades if t.status == "active"]
    assert len(closed) == 1 and closed[0].quantity == 1
    assert len(active) == 1 and active[0].quantity == 1


# ---------------------------------------------------------------------------
# return_pct — TRUE PERCENT units
# ---------------------------------------------------------------------------

def test_return_pct_is_true_percent_not_decimal_fraction():
    orders = [
        NormalizedOrder("IWM", "CALL", "open", "2026-06-01 00:00", 1.42, 1, 0),
        NormalizedOrder("IWM", "CALL", "close", "2026-06-03 00:00", 1.71, 1, 1),
    ]
    preview = pair_orders(orders)
    assert len(preview.trades) == 1
    trade = preview.trades[0]
    assert trade.return_pct == pytest.approx(20.42, abs=0.01)


def test_return_pct_none_when_trade_still_active():
    orders = [
        NormalizedOrder("IWM", "CALL", "open", "2026-06-01 00:00", 1.42, 1, 0),
    ]
    preview = pair_orders(orders)
    assert preview.trades[0].return_pct is None
    assert preview.trades[0].status == "active"


# ---------------------------------------------------------------------------
# pair_orders purity / determinism
# ---------------------------------------------------------------------------

def test_pair_orders_is_pure_and_deterministic():
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    preview1 = pair_orders(orders)
    preview2 = pair_orders(orders)
    assert preview1.trades == preview2.trades
    assert preview1.skipped == preview2.skipped


def test_pair_orders_does_not_set_broker():
    """pair_orders has no broker info (NormalizedOrder doesn't carry it);
    the caller (Task 3) is responsible for assigning .broker post-hoc."""
    preview = pair_orders([])
    assert preview.broker == ""


# ---------------------------------------------------------------------------
# Generic mapping-based parsing
# ---------------------------------------------------------------------------

def test_generic_mapping_parses_and_skips_missing_columns():
    text = (
        "sym,dir,act,when,px,qty\n"
        "IWM,CALL,open,2026-06-01 09:30,1.42,1\n"
        "IWM,CALL,close,2026-06-03 09:30,1.71,1\n"
        "IWM,WEIRD,open,2026-06-04 09:30,1.00,1\n"
    )
    mapping = {
        "ticker": "sym", "direction": "dir", "action": "act",
        "ts": "when", "price": "px", "quantity": "qty",
    }
    orders = parse_csv(text, "generic", mapping=mapping)
    good = [o for o in orders if o.raw_index in (0, 1)]
    assert good[0].ticker == "IWM" and good[0].action == "open"
    preview = pair_orders(orders)
    by_index = {s["raw_index"]: s["reason"] for s in preview.skipped}
    assert 2 in by_index  # unrecognized direction "WEIRD"
