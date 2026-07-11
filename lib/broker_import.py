"""Broker CSV import core — parse, detect, FIFO round-trip pairing.

Task 2 of the 2026-07-11 journal one-stop-shop program (see
``.superpowers/sdd/task-2-brief.md``). This module is the pure-Python core;
Task 3 wraps it in FastAPI endpoints (``platform/api/routers/journal.py``)
and owns duplicate detection / DB writes. Nothing here does I/O or touches
the database — ``parse_csv`` operates on an in-memory CSV string and
``pair_orders`` is a pure function of its input list.

v1 scope and known simplifications (documented per CLAUDE.md Rule 3.7 — no
*silent* fallbacks; these are explicit, tested limitations, not concealed
ones):

1. **Long options only.** BTO/"Buy to Open" = open, STC/"Sell to Close" =
   close. Short legs (STO/"Sell to Open", BTC/"Buy to Close") are dropped
   with reason "short options not supported" — v1 cannot represent a short
   leg's P&L correctly (premium received vs. paid inverts the return_pct
   sign), so we refuse to guess rather than silently mis-sign a return.

2. **No fill time on Robinhood.** Robinhood's activity-export CSV has an
   ``Activity Date`` column only (no time-of-day). Rather than fabricate a
   plausible-looking time (e.g. "09:30"), every Robinhood
   ``NormalizedOrder.ts`` is ``"<date> 00:00"``. The journal UI renders this
   honestly as midnight rather than implying a real fill time it doesn't
   have. Webull's ``Filled Time`` column *does* carry a real exchange-local
   (ET) time and is used directly, naive (no tz conversion — it's already
   ET).

3. **FIFO pairing key is (ticker, direction) only.** ``NormalizedOrder``
   does not carry strike/expiry (the brief's dataclass is deliberately
   thin), so a same-ticker, same-direction trade with two different
   strikes/expiries open at once will FIFO-match across them as if they
   were the same contract. This matches how a trader typically closes in
   the order they opened, but is a known coarsening — if strike/expiry
   granularity is needed later, it requires widening ``NormalizedOrder``
   (a Task-2-successor change, not silently patched in here).

4. **Skip-reason threading.** ``parse_csv``'s signature is fixed to
   ``-> list[NormalizedOrder]`` (Task 3/6 depend on this exact shape) but
   ``ImportPreview.skipped`` — where every dropped row must land per Rule
   3.7 — is only produced by ``pair_orders``. To thread a reason through
   the fixed-shape return value without adding a field, rows that
   ``parse_csv`` cannot normalize are represented as a *skip-tagged*
   ``NormalizedOrder`` whose ``action`` is ``"skip:<reason>"`` (all other
   fields are placeholder/empty except ``raw_index``, which is real).
   ``pair_orders`` recognizes this tag via ``_skip_reason()`` and emits
   ``{"raw_index": ..., "reason": ...}`` into ``ImportPreview.skipped``
   instead of attempting to pair it. This keeps ``parse_csv`` total (one
   output entry per input row, valid or not) while honoring the declared
   return type verbatim.

5. **``ImportPreview.broker`` is not set by ``pair_orders``.**
   ``pair_orders`` only receives ``list[NormalizedOrder]``, which does not
   carry a broker tag, so it cannot know which broker produced the orders.
   It returns ``broker=""``; the caller (Task 3, which already knows the
   broker it passed to ``parse_csv``) is expected to assign
   ``preview.broker = broker`` before returning the preview to the client.
"""
from __future__ import annotations

import csv
import io
import re
from collections import deque
from dataclasses import dataclass, field


@dataclass
class NormalizedOrder:
    """One option fill, normalized to a broker-agnostic shape.

    For rows ``parse_csv`` could not turn into a real order (short option,
    equity/shares row, unparseable field, unmapped generic column), this is
    reused as a skip carrier: ``action == "skip:<reason>"`` and all other
    fields except ``raw_index`` are placeholders. See module docstring
    point 4. Use ``_skip_reason()`` to test for this.
    """
    ticker: str             # underlying, e.g. "IWM"
    direction: str          # "CALL" | "PUT"
    action: str             # "open" | "close" (or "skip:<reason>" — see above)
    ts: str                 # naive-ET "YYYY-MM-DD HH:MM"
    price: float            # per-contract premium
    quantity: int
    raw_index: int          # source row for error messages


@dataclass
class PairedTrade:
    ticker: str
    direction: str
    entry_ts: str
    entry_price: float
    exit_ts: str | None
    exit_price: float | None
    return_pct: float | None      # TRUE PERCENT: (exit-entry)/entry*100, None when open
    quantity: int
    status: str                   # "closed" | "active"


@dataclass
class ImportPreview:
    trades: list[PairedTrade] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)   # {raw_index, reason}
    broker: str = ""              # "robinhood" | "webull" | "generic" | "" (see docstring pt. 5)


# ---------------------------------------------------------------------------
# Broker detection
# ---------------------------------------------------------------------------

_ROBINHOOD_REQUIRED_COLUMNS = {"Activity Date", "Trans Code", "Instrument"}
_WEBULL_REQUIRED_COLUMNS = {"Symbol", "Side", "Avg Price", "Filled Time"}


def detect_broker(header_line: str) -> str | None:
    """Exact-header-set match: does the header contain all of a broker's
    distinctive required columns? Returns None if neither broker's required
    columns are all present (caller should fall back to generic + mapping).
    """
    try:
        columns = set(next(csv.reader([header_line])))
    except StopIteration:
        return None
    if _ROBINHOOD_REQUIRED_COLUMNS.issubset(columns):
        return "robinhood"
    if _WEBULL_REQUIRED_COLUMNS.issubset(columns):
        return "webull"
    return None


# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------

_SKIP_PREFIX = "skip:"


def _make_skip(raw_index: int, reason: str) -> NormalizedOrder:
    return NormalizedOrder(
        ticker="", direction="", action=f"{_SKIP_PREFIX}{reason}",
        ts="", price=0.0, quantity=0, raw_index=raw_index,
    )


def _skip_reason(order: NormalizedOrder) -> str | None:
    if order.action.startswith(_SKIP_PREFIX):
        return order.action[len(_SKIP_PREFIX):]
    return None


def _parse_money(raw: str | None) -> float | None:
    """'$1.42' / '($284.00)' / '1.42' -> float. None on missing/unparseable."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").strip()
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _parse_int_qty(raw: str | None) -> int | None:
    if raw is None:
        return None
    s = raw.strip().replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Robinhood
# ---------------------------------------------------------------------------

_RH_TRANS_ACTION = {"BTO": "open", "STC": "close"}
_RH_TRANS_SHORT = {"STO", "BTC"}

_RH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
# e.g. "IWM 6/19/2026 Call $224.00"
_RH_DESC_RE = re.compile(
    r"^([A-Z.]+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$([\d,]+\.\d{2})$"
)


def _rh_date_to_ts(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _RH_DATE_RE.match(raw.strip())
    if not m:
        return None
    mm, dd, yyyy = m.groups()
    return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d} 00:00"


def _parse_robinhood(text: str) -> list[NormalizedOrder]:
    orders: list[NormalizedOrder] = []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader):
        trans = (row.get("Trans Code") or "").strip()

        if trans in _RH_TRANS_SHORT:
            orders.append(_make_skip(i, "short options not supported"))
            continue
        if trans not in _RH_TRANS_ACTION:
            # Anything that isn't a recognized option trans code (Buy, Sell,
            # ACH, CDIV, etc.) is treated as a non-option (shares) row in v1.
            orders.append(_make_skip(i, "shares — options only in v1"))
            continue

        desc = (row.get("Description") or "").strip()
        m = _RH_DESC_RE.match(desc)
        if not m:
            orders.append(_make_skip(i, "could not parse option description"))
            continue
        ticker, _expiry, calput, _strike = m.groups()
        direction = "CALL" if calput == "Call" else "PUT"

        ts = _rh_date_to_ts(row.get("Activity Date"))
        if ts is None:
            orders.append(_make_skip(i, "unparseable Activity Date"))
            continue

        price = _parse_money(row.get("Price"))
        if price is None:
            orders.append(_make_skip(i, "unparseable Price"))
            continue

        qty = _parse_int_qty(row.get("Quantity"))
        if qty is None:
            orders.append(_make_skip(i, "unparseable Quantity"))
            continue

        orders.append(NormalizedOrder(
            ticker=ticker, direction=direction, action=_RH_TRANS_ACTION[trans],
            ts=ts, price=price, quantity=qty, raw_index=i,
        ))
    return orders


# ---------------------------------------------------------------------------
# Webull
# ---------------------------------------------------------------------------

_WEBULL_SIDE_ACTION = {"Buy to Open": "open", "Sell to Close": "close"}
_WEBULL_SIDE_SHORT = {"Sell to Open", "Buy to Close"}

# OCC-style symbol: TICKER + YYMMDD + C/P + 8-digit strike*1000, e.g.
# "IWM250711C00224000".
_OCC_RE = re.compile(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$")

_WEBULL_TIME_RE = re.compile(
    r"^(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):\d{2}\s*[A-Za-z]*$"
)


def _webull_time_to_ts(raw: str | None) -> str | None:
    """'06/01/2026 09:40:00 EDT' -> '2026-06-01 09:40'. Already ET — naive
    passthrough, no timezone conversion."""
    if not raw:
        return None
    m = _WEBULL_TIME_RE.match(raw.strip())
    if not m:
        return None
    mm, dd, yyyy, hh, mi = m.groups()
    return f"{yyyy}-{mm}-{dd} {hh}:{mi}"


def _parse_webull(text: str) -> list[NormalizedOrder]:
    orders: list[NormalizedOrder] = []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader):
        symbol = (row.get("Symbol") or "").strip()
        m = _OCC_RE.match(symbol)
        if not m:
            # Not an OCC option symbol -> plain equity/shares row in v1.
            orders.append(_make_skip(i, "shares — options only in v1"))
            continue
        ticker, _yymmdd, calput, _strike8 = m.groups()
        direction = "CALL" if calput == "C" else "PUT"

        side = (row.get("Side") or "").strip()
        if side in _WEBULL_SIDE_SHORT:
            orders.append(_make_skip(i, "short options not supported"))
            continue
        if side not in _WEBULL_SIDE_ACTION:
            orders.append(_make_skip(i, f"unrecognized side: {side!r}"))
            continue

        ts = _webull_time_to_ts(row.get("Filled Time"))
        if ts is None:
            orders.append(_make_skip(i, "unparseable Filled Time"))
            continue

        price = _parse_money(row.get("Avg Price"))
        if price is None:
            orders.append(_make_skip(i, "unparseable Avg Price"))
            continue

        qty = _parse_int_qty(row.get("Filled Qty") or row.get("Total Qty"))
        if qty is None:
            orders.append(_make_skip(i, "unparseable Filled Qty"))
            continue

        orders.append(NormalizedOrder(
            ticker=ticker, direction=direction, action=_WEBULL_SIDE_ACTION[side],
            ts=ts, price=price, quantity=qty, raw_index=i,
        ))
    return orders


# ---------------------------------------------------------------------------
# Generic (caller-supplied column mapping)
# ---------------------------------------------------------------------------

_GENERIC_REQUIRED_KEYS = ("ticker", "direction", "action", "ts", "price", "quantity")


def _parse_generic(text: str, mapping: dict) -> list[NormalizedOrder]:
    missing_keys = [k for k in _GENERIC_REQUIRED_KEYS if k not in mapping]
    if missing_keys:
        # This is a caller bug (Task 3/6 misconfigured the mapping), not a
        # per-row data problem -> INTERNAL failure, fail loud (Rule 3.7).
        raise ValueError(f"generic mapping missing required keys: {missing_keys}")

    orders: list[NormalizedOrder] = []
    reader = csv.DictReader(io.StringIO(text))
    for i, row in enumerate(reader):
        col_ticker = mapping["ticker"]
        col_direction = mapping["direction"]
        col_action = mapping["action"]
        col_ts = mapping["ts"]
        col_price = mapping["price"]
        col_quantity = mapping["quantity"]

        if any(col not in row for col in
               (col_ticker, col_direction, col_action, col_ts, col_price, col_quantity)):
            orders.append(_make_skip(i, "mapped column missing from row"))
            continue

        ticker = (row[col_ticker] or "").strip()
        direction = (row[col_direction] or "").strip().upper()
        action = (row[col_action] or "").strip().lower()
        ts = (row[col_ts] or "").strip()

        if not ticker:
            orders.append(_make_skip(i, "missing ticker"))
            continue
        if direction not in ("CALL", "PUT"):
            orders.append(_make_skip(i, f"unrecognized direction: {direction!r}"))
            continue
        if action not in ("open", "close"):
            orders.append(_make_skip(i, f"unrecognized action: {action!r}"))
            continue
        if not ts:
            orders.append(_make_skip(i, "missing ts"))
            continue

        price = _parse_money(row[col_price])
        if price is None:
            orders.append(_make_skip(i, "unparseable price"))
            continue
        qty = _parse_int_qty(row[col_quantity])
        if qty is None:
            orders.append(_make_skip(i, "unparseable quantity"))
            continue

        orders.append(NormalizedOrder(
            ticker=ticker, direction=direction, action=action,
            ts=ts, price=price, quantity=qty, raw_index=i,
        ))
    return orders


# ---------------------------------------------------------------------------
# Public parse_csv dispatcher
# ---------------------------------------------------------------------------

def parse_csv(text: str, broker: str, mapping: dict | None = None) -> list[NormalizedOrder]:
    """Parse a broker CSV export into NormalizedOrders (one entry per input
    row — valid rows and skip-tagged rows alike; see module docstring pt.
    4). ``broker`` selects the parser: "robinhood", "webull", or "generic"
    (requires ``mapping``)."""
    if broker == "robinhood":
        return _parse_robinhood(text)
    if broker == "webull":
        return _parse_webull(text)
    if broker == "generic":
        if mapping is None:
            # Caller bug: generic requires a mapping. INTERNAL -> raise.
            raise ValueError("generic broker requires a mapping dict")
        return _parse_generic(text, mapping)
    raise ValueError(f"unknown broker: {broker!r}")


# ---------------------------------------------------------------------------
# FIFO round-trip pairing
# ---------------------------------------------------------------------------

def pair_orders(orders: list[NormalizedOrder]) -> ImportPreview:
    """Pure function: FIFO-pair opens/closes per (ticker, direction) — see
    module docstring pt. 3 for why "contract" collapses to that pair in v1.
    No I/O, no DB. Every skip-tagged input order and every close that can't
    find a matching open lands in ``ImportPreview.skipped``.
    """
    trades: list[PairedTrade] = []
    skipped: list[dict] = []
    lots: dict[tuple[str, str], deque] = {}

    def sort_key(o: NormalizedOrder):
        return (o.ts, o.raw_index)

    for order in sorted(orders, key=sort_key):
        reason = _skip_reason(order)
        if reason is not None:
            skipped.append({"raw_index": order.raw_index, "reason": reason})
            continue

        key = (order.ticker, order.direction)

        if order.action == "open":
            lots.setdefault(key, deque()).append({
                "ts": order.ts, "price": order.price,
                "remaining": order.quantity, "raw_index": order.raw_index,
            })
            continue

        if order.action == "close":
            queue = lots.get(key)
            if not queue:
                skipped.append({"raw_index": order.raw_index, "reason": "close without matching open"})
                continue

            remaining_to_close = order.quantity
            while remaining_to_close > 0 and queue:
                lot = queue[0]
                matched = min(lot["remaining"], remaining_to_close)
                entry_price = lot["price"]
                exit_price = order.price
                return_pct = round((exit_price - entry_price) / entry_price * 100, 2)
                trades.append(PairedTrade(
                    ticker=order.ticker, direction=order.direction,
                    entry_ts=lot["ts"], entry_price=entry_price,
                    exit_ts=order.ts, exit_price=exit_price,
                    return_pct=return_pct, quantity=matched, status="closed",
                ))
                lot["remaining"] -= matched
                remaining_to_close -= matched
                if lot["remaining"] == 0:
                    queue.popleft()

            if remaining_to_close > 0:
                skipped.append({"raw_index": order.raw_index, "reason": "close without matching open"})
            continue

        # Defensive: parse_csv's contract only emits "open"/"close"/"skip:*"
        # actions, so this is unreachable in practice — fail loud rather
        # than silently drop if it ever happens (Rule 3.7).
        skipped.append({"raw_index": order.raw_index, "reason": f"unrecognized action: {order.action!r}"})

    for (ticker, direction), queue in lots.items():
        for lot in queue:
            trades.append(PairedTrade(
                ticker=ticker, direction=direction,
                entry_ts=lot["ts"], entry_price=lot["price"],
                exit_ts=None, exit_price=None, return_pct=None,
                quantity=lot["remaining"], status="active",
            ))

    return ImportPreview(trades=trades, skipped=skipped, broker="")
