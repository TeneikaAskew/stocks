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
        "unsupported activity type: CDIV",
        "unsupported activity type: ACH",
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


# ---------------------------------------------------------------------------
# CRITICAL fix — FIFO pairing key must include the contract (strike/expiry),
# not just (ticker, direction). Reproduces the reviewer's exact failure:
# BTO IWM 224C, BTO IWM 220C, STC IWM 220C — pre-fix code closed the WRONG
# lot (224C) at a fabricated +69.01%, leaving the 220C (which actually
# closed) active. Truth: the 220C round-trip closes at +17.07%, and the
# 224C lot (never touched by a close) is the one left active.
# ---------------------------------------------------------------------------

def test_fifo_pairing_keys_by_contract_not_just_ticker_direction():
    orders = [
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="open",
            ts="2026-06-01 00:00", price=1.42, quantity=1, raw_index=0,
            strike=224.0, expiry="2026-06-19",
        ),
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="open",
            ts="2026-06-02 00:00", price=2.05, quantity=1, raw_index=1,
            strike=220.0, expiry="2026-06-19",
        ),
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="close",
            ts="2026-06-03 00:00", price=2.40, quantity=1, raw_index=2,
            strike=220.0, expiry="2026-06-19",
        ),
    ]
    preview = pair_orders(orders)
    assert preview.skipped == []
    assert len(preview.trades) == 2

    closed = [t for t in preview.trades if t.status == "closed"]
    active = [t for t in preview.trades if t.status == "active"]
    assert len(closed) == 1 and len(active) == 1

    # The 220C round-trip closed, at +17.07% — NOT the 224C at +69.01%.
    assert closed[0].entry_price == pytest.approx(2.05)
    assert closed[0].exit_price == pytest.approx(2.40)
    assert closed[0].return_pct == pytest.approx(17.07, abs=0.01)

    # The 224C lot (never closed) is the one left active.
    assert active[0].entry_price == pytest.approx(1.42)
    assert active[0].status == "active"


def test_fifo_pairing_excess_close_quantity_skips_remainder():
    """Open qty 1, close qty 3 -> 1 closed trade (qty 1) + the excess 2
    contracts skipped as 'close without matching open' (not fabricated or
    silently dropped)."""
    orders = [
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="open",
            ts="2026-06-01 00:00", price=1.42, quantity=1, raw_index=0,
            strike=224.0, expiry="2026-06-19",
        ),
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="close",
            ts="2026-06-03 00:00", price=1.71, quantity=3, raw_index=1,
            strike=224.0, expiry="2026-06-19",
        ),
    ]
    preview = pair_orders(orders)
    assert len(preview.trades) == 1
    assert preview.trades[0].status == "closed"
    assert preview.trades[0].quantity == 1
    assert preview.skipped == [{"raw_index": 1, "reason": "close without matching open"}]


def test_fifo_pairing_contract_orders_never_cross_match_generic_orders():
    """A contract-bearing order (strike/expiry set) and a generic-mapping
    order (strike/expiry None) that share (ticker, direction) must NOT be
    treated as the same lot — the two keying regimes are disjoint."""
    orders = [
        # Contract-bearing open (from RH/Webull parsing).
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="open",
            ts="2026-06-01 00:00", price=1.42, quantity=1, raw_index=0,
            strike=224.0, expiry="2026-06-19",
        ),
        # Generic-mapping close, same ticker/direction, no contract data.
        NormalizedOrder(
            ticker="IWM", direction="CALL", action="close",
            ts="2026-06-03 00:00", price=1.71, quantity=1, raw_index=1,
        ),
    ]
    preview = pair_orders(orders)
    # The generic close must NOT match the contract-bearing open.
    assert preview.skipped == [{"raw_index": 1, "reason": "close without matching open"}]
    assert len(preview.trades) == 1
    assert preview.trades[0].status == "active"
    assert preview.trades[0].entry_price == pytest.approx(1.42)


# ---------------------------------------------------------------------------
# Strike/expiry threaded from the parsers (both brokers already extract
# these values from Description/OCC symbol — they must be carried onto
# NormalizedOrder, not discarded).
# ---------------------------------------------------------------------------

def test_robinhood_parses_strike_and_expiry():
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    # raw_index 0: IWM 6/19/2026 Call $224.00
    o0 = next(o for o in orders if o.raw_index == 0)
    assert o0.strike == pytest.approx(224.0)
    assert o0.expiry == "2026-06-19"


def test_robinhood_parses_strike_with_cents():
    text = (
        "Activity Date,Process Date,Settle Date,Instrument,Description,Trans Code,Quantity,Price,Amount\n"
        "6/1/2026,6/1/2026,6/3/2026,IWM,IWM 6/19/2026 Call $224.50,BTO,1,$1.42,($142.00)\n"
    )
    orders = parse_csv(text, "robinhood")
    assert orders[0].strike == pytest.approx(224.5)
    assert orders[0].expiry == "2026-06-19"


def test_webull_parses_strike_and_expiry():
    orders = parse_csv(_read("webull_sample.csv"), "webull")
    # raw_index 0: IWM260619C00224000
    o0 = next(o for o in orders if o.raw_index == 0)
    assert o0.strike == pytest.approx(224.0)
    assert o0.expiry == "2026-06-19"


def test_webull_parses_strike_with_cents():
    text = (
        "Name,Symbol,Side,Status,Filled Qty,Total Qty,Price,Avg Price,Time-in-Force,Placed Time,Filled Time\n"
        "IWM Jun 19 2026 224.50 C,IWM260619C00224500,Buy to Open,Filled,1,1,1.42,1.42,DAY,"
        "06/01/2026 09:38:00 EDT,06/01/2026 09:40:00 EDT\n"
    )
    orders = parse_csv(text, "webull")
    assert orders[0].strike == pytest.approx(224.5)
    assert orders[0].expiry == "2026-06-19"


def test_generic_mapping_orders_have_no_strike_expiry():
    """Generic-mapping orders never carry contract data (the mapping dict
    has no strike/expiry keys per the brief) -> both stay None, which is
    the fallback-key sentinel pair_orders relies on."""
    text = (
        "sym,dir,act,when,px,qty\n"
        "IWM,CALL,open,2026-06-01 09:30,1.42,1\n"
    )
    mapping = {
        "ticker": "sym", "direction": "dir", "action": "act",
        "ts": "when", "price": "px", "quantity": "qty",
    }
    orders = parse_csv(text, "generic", mapping=mapping)
    assert orders[0].strike is None
    assert orders[0].expiry is None


# ---------------------------------------------------------------------------
# IMPORTANT fix — skip-reason honesty (Rule 3.7). RH rows whose Trans Code
# isn't a recognized option code AND don't genuinely look like an equity
# trade (dividends, ACH transfers, interest, etc.) must NOT be mislabeled
# "shares — options only in v1" — that's a lie about what the row is.
# ---------------------------------------------------------------------------

def test_robinhood_dividend_and_ach_rows_get_unsupported_activity_reason():
    orders = parse_csv(_read("robinhood_sample.csv"), "robinhood")
    preview = pair_orders(orders)
    by_index = {s["raw_index"]: s["reason"] for s in preview.skipped}
    # raw_index 7: CDIV dividend row (Instrument=AAPL, no Quantity, not a trade).
    assert by_index[7] == "unsupported activity type: CDIV"
    # raw_index 8: ACH transfer row (no Instrument at all).
    assert by_index[8] == "unsupported activity type: ACH"
    # The genuine equity Buy row (raw_index 5) must still say "shares".
    assert by_index[5] == "shares — options only in v1"


# ---------------------------------------------------------------------------
# IMPORTANT fix — same-day Robinhood day trades must pair correctly. RH
# activity CSVs are newest-first and RH rows have date-only ts ("<date>
# 00:00"), so a same-day STC can land at a LOWER raw_index than its BTO.
# Sorting solely on (ts, raw_index) then processes the close before the
# open at identical ts, and the close is dropped as "close without matching
# open" while the open sits as a phantom active lot. The fix breaks ties at
# equal ts by processing opens before closes: (ts, 0 if open else 1,
# raw_index).
# ---------------------------------------------------------------------------

def test_robinhood_same_day_day_trade_pairs_correctly_when_newest_first():
    """Reproduces the reviewer's exact failure: a newest-first RH export
    where the STC row (raw_index 0) precedes the same-day BTO row
    (raw_index 1). Both normalize to the same date-only ts
    ("2026-06-01 00:00"), so without the tie-break the close is processed
    first and dropped as unmatched, leaving the open as a phantom active
    lot instead of a completed +20.42% day trade."""
    text = (
        "Activity Date,Process Date,Settle Date,Instrument,Description,Trans Code,Quantity,Price,Amount\n"
        "6/1/2026,6/1/2026,6/3/2026,IWM,IWM 6/19/2026 Call $224.00,STC,2,$1.71,$342.00\n"
        "6/1/2026,6/1/2026,6/3/2026,IWM,IWM 6/19/2026 Call $224.00,BTO,2,$1.42,($284.00)\n"
    )
    orders = parse_csv(text, "robinhood")
    preview = pair_orders(orders)

    assert preview.skipped == []
    assert len(preview.trades) == 1
    trade = preview.trades[0]
    assert trade.status == "closed"
    assert trade.entry_price == pytest.approx(1.42)
    assert trade.exit_price == pytest.approx(1.71)
    assert trade.return_pct == pytest.approx(20.42, abs=0.01)


def test_fifo_multi_lot_and_reopen_cases_unaffected_by_tie_break():
    """The open-before-close tie-break at equal ts must not disturb FIFO
    ordering across DIFFERENT timestamps: earlier-ts lots still close
    before later-ts lots, and a close/reopen at strictly increasing ts
    still resolves in chronological order."""
    orders = [
        # Two lots at different ts, one close spanning both — same as
        # test_fifo_pairing_close_spans_multiple_lots, tests file-wide
        # invariant isn't broken by the new secondary sort key.
        NormalizedOrder("SPY", "PUT", "open", "2026-06-01 00:00", 3.00, 1, 0),
        NormalizedOrder("SPY", "PUT", "open", "2026-06-02 00:00", 3.20, 1, 1),
        NormalizedOrder("SPY", "PUT", "close", "2026-06-03 00:00", 2.90, 2, 2),
        # Close then reopen the same contract on a LATER date: the reopen
        # must still be a fresh active lot, not accidentally matched to
        # the close that already happened.
        NormalizedOrder("QQQ", "CALL", "open", "2026-06-01 00:00", 5.00, 1, 3),
        NormalizedOrder("QQQ", "CALL", "close", "2026-06-02 00:00", 6.00, 1, 4),
        NormalizedOrder("QQQ", "CALL", "open", "2026-06-05 00:00", 5.50, 1, 5),
    ]
    preview = pair_orders(orders)
    assert preview.skipped == []

    spy_trades = [t for t in preview.trades if t.ticker == "SPY"]
    assert len(spy_trades) == 2
    assert all(t.status == "closed" for t in spy_trades)
    entry_prices = sorted(t.entry_price for t in spy_trades)
    assert entry_prices == [pytest.approx(3.00), pytest.approx(3.20)]

    qqq_trades = [t for t in preview.trades if t.ticker == "QQQ"]
    assert len(qqq_trades) == 2
    closed = [t for t in qqq_trades if t.status == "closed"]
    active = [t for t in qqq_trades if t.status == "active"]
    assert len(closed) == 1 and closed[0].entry_price == pytest.approx(5.00)
    assert len(active) == 1 and active[0].entry_price == pytest.approx(5.50)


# ---------------------------------------------------------------------------
# MINOR fix — entry_price == 0 (or negative) must not raise ZeroDivisionError
# / produce a bogus infinite return; the close is skipped with an honest
# reason instead (Rule 3.7: fail loud / surface, never fabricate or crash).
# ---------------------------------------------------------------------------

def test_zero_entry_price_is_skipped_not_a_zero_division_error():
    text = (
        "sym,dir,act,when,px,qty\n"
        "IWM,CALL,open,2026-06-01 09:30,0,1\n"
        "IWM,CALL,close,2026-06-03 09:30,1.71,1\n"
    )
    mapping = {
        "ticker": "sym", "direction": "dir", "action": "act",
        "ts": "when", "price": "px", "quantity": "qty",
    }
    orders = parse_csv(text, "generic", mapping=mapping)
    preview = pair_orders(orders)  # must not raise ZeroDivisionError

    assert preview.trades == []
    by_index = {s["raw_index"]: s["reason"] for s in preview.skipped}
    assert by_index[1] == "invalid entry price: 0"
