#!/usr/bin/env python3
"""
EW strike verdict evaluator — runs after market close to score how
each Earnings Whispers strike pick played out intraday.

Populates these columns on earnings_calendar (only for rows with
``data_source = 'earnings_whispers'`` and ``strike IS NOT NULL``):
    ew_high_on_day, ew_low_on_day, ew_close_on_day
    ew_strike_verdict   — HIT | MISS | KEPT | ASSIGNED
    ew_strike_move_pct  — signed % move vs strike (high or close depending on strategy)
    ew_minutes_to_hit   — first regular-session minute strike was crossed (NULL if MISS)
    ew_minutes_in_zone  — total regular-session minutes spent on profitable side of strike
    ew_day_change_pct   — open-to-close % move (signed; bullish/bearish bias)

Verdicts depend on the strategy:
    Long Calls / Bull Spreads → HIT if high >= strike, else MISS
    Long Puts  / Bear Spreads → HIT if low <= strike, else MISS
    Covered Calls             → KEPT if close <= strike, else ASSIGNED
    (Strangles / Straddles use a different math — skipped here)

Each pick is scored against the session its news reaches, not the session of
``earnings_date`` (#1151: 1,263 after-close verdicts described the session
BEFORE the news):
    postmarket → the first NYSE session after earnings_date
    premarket  → the first NYSE session on or after earnings_date
    intraday   → the session of earnings_date itself. The news lands inside
                 it; scoring the whole session is the stated choice.
    anything else → skipped and counted, never given a default session
The bar window is that session's calendar open to close, so an early close
(13:00 ET) ends it there and after-hours bars never count. A pick is scored
only once its session has closed; until then it is counted as pending.

Usage:
    python -m gcp.fetchers.evaluate_ew_strikes                  # unscored picks, last 7 days
    python -m gcp.fetchers.evaluate_ew_strikes --start 2026-04-13 --end 2026-04-30
    python -m gcp.fetchers.evaluate_ew_strikes --force --earnings-time postmarket \\
        --start 2026-04-20 --end 2026-09-23                     # re-score; clear what cannot be
    python -m gcp.fetchers.evaluate_ew_strikes --dry-run        # score and log, write nothing

Required env vars:
    ALPHA_VANTAGE_API_KEY (intraday bars)
    CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.eastern_time import ET, ET_NAME  # noqa: E402

log = logging.getLogger(__name__)

# How far back the default nightly run looks for unscored picks. An
# after-close pick is scored the evening after its report; the rest of the
# week absorbs a holiday, a missed run or a vendor gap without anyone
# re-running a date by hand.
DEFAULT_LOOKBACK_DAYS = 7

# Outcome counters, in the order they are logged.
OUTCOMES = ("scored", "pending_session", "unknown_timing", "no_session",
            "no_bars", "no_verdict", "cleared")

# Vendor calls made, and how many returned no bars in the session. The
# outage rule counts calls, not rows: picks on one ticker's session share one.
FETCH_COUNTERS = ("fetches", "empty_fetches")

_TIMINGS = ("premarket", "postmarket", "intraday")


def _timing(value) -> str:
    """earnings_time normalised; '' for NULL, which pandas may return as NaN."""
    return value.strip().lower() if isinstance(value, str) else ""


# ── Verdict math ─────────────────────────────────────────────────────────────

def _compute_verdict(strategy: str, strike: float,
                     reg_bars: pd.DataFrame) -> dict:
    """Return verdict + supporting metrics for one (strategy, strike, day).

    `reg_bars` must be 1-min OHLCV restricted to the scoring session's
    regular hours (calendar open to close), indexed by naive ET timestamp.
    Empty bars → all None.
    """
    out = {
        'verdict': None, 'move_pct': None,
        'minutes_to_hit': None, 'minutes_in_zone': None,
        'high': None, 'low': None, 'close': None,
        'day_change_pct': None,
    }
    if reg_bars is None or reg_bars.empty:
        return out

    high = float(reg_bars['High'].max())
    low  = float(reg_bars['Low'].min())
    close = float(reg_bars['Close'].iloc[-1])
    day_open = float(reg_bars['Open'].iloc[0])
    out['high'], out['low'], out['close'] = high, low, close
    if day_open != 0:
        out['day_change_pct'] = round((close - day_open) / day_open * 100, 4)

    # Per-bar in-zone mask depends on strategy direction
    if strategy in ('Long Calls', 'Bull Spreads'):
        # Profitable when underlying high >= strike
        in_zone_mask = reg_bars['High'] >= strike
        if high >= strike:
            out['verdict'] = 'HIT'
            out['move_pct'] = round((high - strike) / strike * 100, 4)
        else:
            out['verdict'] = 'MISS'
            out['move_pct'] = round(-(strike - high) / strike * 100, 4)

    elif strategy in ('Long Puts', 'Bear Spreads'):
        in_zone_mask = reg_bars['Low'] <= strike
        if low <= strike:
            out['verdict'] = 'HIT'
            out['move_pct'] = round(-(strike - low) / strike * 100, 4)
        else:
            out['verdict'] = 'MISS'
            out['move_pct'] = round((low - strike) / strike * 100, 4)

    elif strategy == 'Covered Calls':
        # Seller wants underlying to STAY BELOW strike at close.
        # In-zone (good for seller) = close-of-bar at/below strike.
        in_zone_mask = reg_bars['Close'] <= strike
        if close <= strike:
            out['verdict'] = 'KEPT'
            out['move_pct'] = round(-(strike - close) / strike * 100, 4)
        else:
            out['verdict'] = 'ASSIGNED'
            out['move_pct'] = round((close - strike) / strike * 100, 4)

    else:
        # Strangles, Straddles, etc. need EM math, not strike-cross
        return out

    # Time-to-hit: first bar that's in-zone in the strategy's direction.
    # For Covered Calls "in-zone" is close <= strike — time-to-hit is the
    # first bar that BREACHES (above strike), which is the opposite mask.
    if strategy == 'Covered Calls':
        breach_mask = ~in_zone_mask
        first_breach = breach_mask[breach_mask].index.min() if breach_mask.any() else None
        out['minutes_to_hit'] = (
            int((first_breach - reg_bars.index.min()).total_seconds() // 60)
            if first_breach is not None else None
        )
        out['minutes_in_zone'] = int(in_zone_mask.sum())
    else:
        first_hit = in_zone_mask[in_zone_mask].index.min() if in_zone_mask.any() else None
        out['minutes_to_hit'] = (
            int((first_hit - reg_bars.index.min()).total_seconds() // 60)
            if first_hit is not None else None
        )
        out['minutes_in_zone'] = int(in_zone_mask.sum())

    return out


# ── The scoring session ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Session:
    """One NYSE regular session. `open_et` / `close_et` are naive ET, the
    index convention of fetch_minute_data; `close_utc` decides whether the
    session is over yet."""
    date: date
    open_et: pd.Timestamp
    close_et: pd.Timestamp
    close_utc: pd.Timestamp


def nyse_sessions(start: date, end: date) -> pd.DataFrame:
    """NYSE sessions in [start, end]: indexed by session date, with UTC
    `market_open` / `market_close` (early closes included).

    `pandas_market_calendars` is a hard dependency (requirements-gcp.txt).
    There is no weekday fallback: a guessed session is the defect #1151
    fixed, so a missing calendar must fail the run.
    """
    import pandas_market_calendars as mcal
    return mcal.get_calendar("NYSE").schedule(start_date=start, end_date=end)


def scoring_session(earnings_date: date, earnings_time: Optional[str],
                    sessions: pd.DataFrame) -> Optional[Session]:
    """The session a pick is scored against, or None to skip it.

    postmarket → first session AFTER earnings_date; premarket → first session
    ON OR AFTER it; intraday → earnings_date's own session. Any other value
    (NULL, 'unknown', a code the writer does not emit) returns None: the
    caller counts it rather than inventing a session.
    """
    timing = _timing(earnings_time)
    if timing not in _TIMINGS:
        return None
    key = pd.Timestamp(earnings_date)
    side = "right" if timing == "postmarket" else "left"
    pos = int(sessions.index.searchsorted(key, side=side))
    if pos >= len(sessions):
        return None
    if timing == "intraday" and sessions.index[pos] != key:
        return None
    row = sessions.iloc[pos]
    return Session(
        date=sessions.index[pos].date(),
        open_et=row["market_open"].tz_convert(ET_NAME).tz_localize(None),
        close_et=row["market_close"].tz_convert(ET_NAME).tz_localize(None),
        close_utc=row["market_close"],
    )


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


class _Throttle:
    """At most one vendor call per `interval` seconds: lib.config's
    AlphaVantage plan limit, the pacing the repo's other AV jobs keep."""

    def __init__(self, interval: float):
        self.interval = interval
        self._last: Optional[float] = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self.interval - (time.monotonic() - self._last)
            if remaining > 0:
                time.sleep(remaining)
        self._last = time.monotonic()


def run_failed(result: dict) -> bool:
    """True when at least two vendor calls came back and none had bars: an
    outage or a rate limit, not a quiet night. One empty call cannot tell an
    outage from a symbol the vendor lacks, and a quiet night's only call is
    often a straggler from the lookback, so it is counted and retried."""
    return result["empty_fetches"] >= 2 and result["empty_fetches"] == result["fetches"]


# ── Main loop ───────────────────────────────────────────────────────────────

_UPDATE_SQL = """
    UPDATE earnings_calendar SET
        ew_high_on_day      = :high,
        ew_low_on_day       = :low,
        ew_close_on_day     = :close,
        ew_strike_verdict   = :verdict,
        ew_strike_move_pct  = :move,
        ew_minutes_to_hit   = :ttl,
        ew_minutes_in_zone  = :iz,
        ew_day_change_pct   = :dchg
     WHERE id = :id
"""

# --force re-scores rows whose stored verdict is not trusted. One that cannot
# be recomputed now is cleared for the nightly run to fill, never left
# holding a verdict computed against the wrong session.
_CLEAR_SQL = """
    UPDATE earnings_calendar SET
        ew_high_on_day      = NULL,
        ew_low_on_day       = NULL,
        ew_close_on_day     = NULL,
        ew_strike_verdict   = NULL,
        ew_strike_move_pct  = NULL,
        ew_minutes_to_hit   = NULL,
        ew_minutes_in_zone  = NULL,
        ew_day_change_pct   = NULL
     WHERE id = :id
"""


def evaluate_range(start: date, end: date, *, force: bool = False,
                   earnings_time: Optional[str] = None,
                   dry_run: bool = False) -> dict[str, int]:
    """Score the EW picks whose earnings_date is in [start, end]: unscored
    ones, or all of them with `force`. Returns a count per OUTCOMES entry.

    One vendor call per (ticker, session), paced by the AV plan limit, and
    one transaction per session date, so a long re-score keeps its progress
    if it stops part way.
    """
    import sqlalchemy
    from gcp.database import get_engine, query_to_dataframe
    from gcp.fetchers.fetch_market_data import fetch_minute_data
    from lib.config import AlphaVantageConfig

    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        raise RuntimeError(
            "ALPHA_VANTAGE_API_KEY not set: no pick can be scored, and a run "
            "that scores nothing must not exit 0")

    result = dict.fromkeys(OUTCOMES + FETCH_COUNTERS, 0)
    clauses = ["data_source = 'earnings_whispers'", "strike IS NOT NULL",
               "earnings_date BETWEEN :s AND :e"]
    params: dict = {'s': start, 'e': end}
    if not force:
        clauses.append("ew_strike_verdict IS NULL")
    if earnings_time:
        clauses.append("earnings_time = :et")
        params['et'] = earnings_time
    df = query_to_dataframe(f"""
        SELECT id, ticker, earnings_date, earnings_time, strategy, strike,
               ew_strike_verdict
          FROM earnings_calendar
         WHERE {' AND '.join(clauses)}
         ORDER BY earnings_date, ticker
    """, params)
    if df.empty:
        log.info("No EW rows to score in [%s, %s]", start, end)
        return result
    log.info("Selected %d EW picks for %s..%s (force=%s, earnings_time=%s, dry_run=%s)",
             len(df), start, end, force, earnings_time or "all", dry_run)

    # A postmarket pick on `end` reacts after it; two weeks covers any gap.
    sessions = nyse_sessions(start, end + timedelta(days=14))
    now = _now_utc()

    def had_verdict(row) -> bool:
        return force and pd.notna(row.ew_strike_verdict)

    # session date -> ticker -> [(row, session)]
    groups: dict[date, dict[str, list]] = {}
    unsessioned_clears: list[dict] = []
    for row in df.itertuples(index=False):
        session = scoring_session(pd.Timestamp(row.earnings_date).date(),
                                  row.earnings_time, sessions)
        if session is None:
            timing = _timing(row.earnings_time)
            result["unknown_timing" if timing not in _TIMINGS else "no_session"] += 1
        elif session.close_utc > now:
            result["pending_session"] += 1
        else:
            groups.setdefault(session.date, {}).setdefault(row.ticker, []).append((row, session))
            continue
        if had_verdict(row):
            unsessioned_clears.append({'id': int(row.id)})

    throttle = _Throttle(AlphaVantageConfig().delay_between_calls)
    eng = None if dry_run else get_engine()
    upd, clr = sqlalchemy.text(_UPDATE_SQL), sqlalchemy.text(_CLEAR_SQL)
    for session_date in sorted(groups):
        updates: list[dict] = []
        clears: list[dict] = []
        for ticker, items in groups[session_date].items():
            session = items[0][1]
            throttle.wait()
            bars = fetch_minute_data(ticker, session_date.isoformat(), api_key,
                                     adjusted=False)
            if not bars.empty:
                bars = bars[(bars.index >= session.open_et)
                            & (bars.index < session.close_et)]
            result["fetches"] += 1
            result["empty_fetches"] += int(bars.empty)
            for row, _ in items:
                if bars.empty:
                    result["no_bars"] += 1
                else:
                    v = _compute_verdict(row.strategy, float(row.strike), bars)
                    if v['verdict'] is not None:
                        result["scored"] += 1
                        updates.append({
                            'id': int(row.id),
                            'high': v['high'], 'low': v['low'], 'close': v['close'],
                            'verdict': v['verdict'], 'move': v['move_pct'],
                            'ttl': v['minutes_to_hit'],
                            'iz': v['minutes_in_zone'],
                            'dchg': v['day_change_pct'],
                        })
                        continue
                    result["no_verdict"] += 1
                if had_verdict(row):
                    clears.append({'id': int(row.id)})
        if eng is not None and (updates or clears):
            with eng.begin() as conn:
                if updates:
                    conn.execute(upd, updates)
                if clears:
                    conn.execute(clr, clears)
        result["cleared"] += len(clears)
        log.info("session=%s tickers=%d scored=%d cleared=%d",
                 session_date, len(groups[session_date]), len(updates), len(clears))

    if eng is not None and unsessioned_clears:
        with eng.begin() as conn:
            conn.execute(clr, unsessioned_clears)
    result["cleared"] += len(unsessioned_clears)
    return result


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score EW strike picks against intraday bars.")
    parser.add_argument('--start', help='YYYY-MM-DD earnings_date; with --end')
    parser.add_argument('--end', help='YYYY-MM-DD earnings_date; with --start')
    parser.add_argument('--lookback-days', type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help='without --start/--end: earnings_date from today (ET) '
                             'minus this many days')
    parser.add_argument('--force', action='store_true',
                        help='Re-score rows already scored; clear any that cannot be.')
    parser.add_argument('--earnings-time', choices=_TIMINGS,
                        help='Only picks with this earnings_time.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Score and log; write nothing.')
    args = parser.parse_args(argv)
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end go together")
    return args


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S',
    )
    args = parse_args(argv)
    if args.start:
        start = datetime.strptime(args.start, '%Y-%m-%d').date()
        end = datetime.strptime(args.end, '%Y-%m-%d').date()
    else:
        # The container runs in UTC; the trading day is Eastern.
        end = datetime.now(ET).date()
        start = end - timedelta(days=args.lookback_days)

    result = evaluate_range(start, end, force=args.force,
                            earnings_time=args.earnings_time,
                            dry_run=args.dry_run)
    summary = " ".join(f"{k}={v}" for k, v in result.items())
    log.info("DONE %s..%s %s", start, end, summary)
    print(f"{start}..{end} {summary}")
    if run_failed(result):
        log.error("all %d vendor calls came back without bars: vendor outage "
                  "or rate limit, not a quiet night", result["fetches"])
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
