#!/usr/bin/env python3
"""Cloud Run Job module: calibrate-level-params (FEAT-STRAT-001,
docs/superpowers/specs/2026-11-08-feat-strat-001-per-ticker-params.md,
Design 5 and 7).

Writes ticker_level_params from each ticker's own bars with
lib.level_calibration.

* Nightly mode (default): every ticker load_calibration_universe returns,
  one row per parameter effective on the next session (--effective-from,
  default the session after the last completed one), ON CONFLICT (ticker,
  param_key, atr_basis, effective_from) DO UPDATE, so rerunning the same
  night converges.
* History mode (--history START END): per ticker, one version per session
  from START to END, each from bars strictly before that session; replays
  then read the version in force on their session.

Per ticker: one batched daily read, one batched one-minute read, one write
batch. A ticker whose read or calibration fails is logged and skipped and
the run exits non-zero; progress is logged per ticker.

The job definition, its scheduler entry and the deploy wiring belong to the
companion FEAT-DEPLOY-001 change (Design 9); this module is not in
gcp/deploy.sh.

Usage:
    python -m gcp.calibrate_level_params
    python -m gcp.calibrate_level_params --tickers SPY,QQQ --effective-from 2026-11-09
    python -m gcp.calibrate_level_params --history 2015-01-02 2026-11-06 --tickers SPY
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import level_calibration as lc  # noqa: E402
from lib.strat_levels import (  # noqa: E402
    LevelParamsUnavailable, entry_buffer_key, policy_atr_basis, policy_in_force,
)

logger = logging.getLogger(__name__)

JOB_NAME = 'calibrate-level-params'

QueryFn = Callable[..., pd.DataFrame]
WriteFn = Callable[[List[dict]], int]

POLICY_SQL = (
    "SELECT param_key, method_id, statistic_q, lookback_sessions, min_sample, extra, "
    "effective_from FROM level_param_policy WHERE effective_from <= :as_of"
)

DAILY_SQL = (
    "SELECT date, open, high, low, close, atr_14, atr_5 FROM market_data_daily "
    "WHERE ticker = :ticker AND date >= :start AND date < :before ORDER BY date"
)

MINUTES_SQL = (
    "SELECT ts, open, high, low, close, volume FROM market_data_intraday "
    "WHERE ticker = :ticker AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts"
)

ON_DEMAND_SQL = (
    "SELECT DISTINCT ticker FROM ticker_level_params WHERE source = 'on_demand'"
)

_ROW_COLUMNS = ('ticker', 'param_key', 'value', 'status', 'atr_basis', 'method_id',
                'policy_effective_from', 'sample_n', 'input_from', 'input_to',
                'effective_from', 'run_id', 'source', 'calibrated_at')
_CONFLICT = ('ticker', 'param_key', 'atr_basis', 'effective_from')
UPSERT_SQL = (
    f"INSERT INTO ticker_level_params ({', '.join(_ROW_COLUMNS)}) VALUES "
    f"({', '.join(':' + c for c in _ROW_COLUMNS)}) "
    f"ON CONFLICT ({', '.join(_CONFLICT)}) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in _ROW_COLUMNS if c not in _CONFLICT)
)


# ── inputs ───────────────────────────────────────────────────────────────


def read_policy(query: QueryFn, as_of) -> dict:
    """The policy rows in force on `as_of`. An empty or unreadable policy
    raises: the job never calibrates against a missing policy."""
    try:
        rows = query(POLICY_SQL, {'as_of': pd.Timestamp(as_of).date()})
    except Exception as exc:  # noqa: BLE001 — re-raised typed
        raise LevelParamsUnavailable(f"level_param_policy read failed: {exc}") from exc
    if rows is None or rows.empty:
        raise LevelParamsUnavailable(f"level_param_policy has no row in force on {as_of}")
    return policy_in_force(rows.to_dict('records'))


def _max_lookback(policy: dict, keys: Iterable[str]) -> int:
    return max(int(policy[k]['lookback_sessions'] or 0) for k in keys if k in policy)


def read_windows(policy: dict, first_session, last_session) -> dict:
    """Read bounds for one ticker whose rows are effective from
    `first_session` through `last_session`: the daily bars a trigger
    window replayed on the earliest break session needs (two window
    lookbacks before it, plus slack for holidays), and the one-minute bars
    the breaks and the one-minute thresholds read."""
    window_lb = _max_lookback(policy, ('trigger_window_long_atr', 'trigger_window_short_atr'))
    break_lb = _max_lookback(policy, [entry_buffer_key(p, e) for p in lc.PERSONAS for e in ('lo', 'hi')])
    minute_lb = max(break_lb, _max_lookback(policy, (lc.PM_SPIKE_KEY, lc.PM_STALE_PRINT_KEY,
                                                     lc.LEVEL_CLUSTER_KEY)))
    first = pd.Timestamp(first_session)
    slack = pd.offsets.BDay(30)
    return {
        'daily_start': (first - pd.offsets.BDay(break_lb + window_lb + 1) - slack).date(),
        'minutes_start': (first - pd.offsets.BDay(minute_lb) - slack).date(),
        'before': pd.Timestamp(last_session).date(),
    }


def read_daily(query: QueryFn, ticker: str, start, before) -> pd.DataFrame:
    df = query(DAILY_SQL, {'ticker': ticker, 'start': start, 'before': before})
    if df is None:
        raise RuntimeError(f"{ticker}: daily read returned nothing")
    return df


def read_minutes(query: QueryFn, ticker: str, start, before) -> pd.DataFrame:
    """One-minute bars from `start` to before `before` (Eastern dates),
    converted with lib.eastern_time.stored_intraday_to_eastern (the
    table's mixed timestamp conventions, CLAUDE.md 3.9). The UTC bounds are
    widened by a day each side and the Eastern dates cut after conversion."""
    from lib.eastern_time import stored_intraday_to_eastern  # noqa: PLC0415

    lo = pd.Timestamp(start).tz_localize('UTC') - pd.Timedelta(days=1)
    hi = pd.Timestamp(before).tz_localize('UTC') + pd.Timedelta(days=1)
    df = query(MINUTES_SQL, {'ticker': ticker, 'start': lo.to_pydatetime(), 'end': hi.to_pydatetime()})
    if df is None:
        raise RuntimeError(f"{ticker}: one-minute read returned nothing")
    if df.empty:
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    idx, keep = stored_intraday_to_eastern(df['ts'], df['volume'])
    out = df.loc[keep].copy()
    out['timestamp'] = pd.DatetimeIndex(idx[keep])
    day = out['timestamp'].dt.normalize()
    out = out[(day >= pd.Timestamp(start)) & (day < pd.Timestamp(before))]
    return out[['timestamp', 'open', 'high', 'low', 'close', 'volume']].reset_index(drop=True)


def brief_insight_watchlist_tickers(*, watchlist_fn: Optional[Callable[[], Iterable[str]]] = None
                                    ) -> List[str]:
    """The brief tickers (lib.config MarketConfig.tickers), the insight
    default tickers (gcp.insight_pipeline_job.DEFAULT_TICKERS) and the
    watchlist, deduplicated: the one-minute fetch universe (Design 5)."""
    from lib.config import MarketConfig  # noqa: PLC0415
    from gcp.insight_pipeline_job import DEFAULT_TICKERS  # noqa: PLC0415

    if watchlist_fn is None:
        from gcp.fetchers._watchlist import load_watchlist  # noqa: PLC0415
        watchlist_fn = load_watchlist
    out: List[str] = []
    for t in list(MarketConfig().tickers) + list(DEFAULT_TICKERS) + list(watchlist_fn() or []):
        t = str(t).strip().upper()
        if t and t not in out:
            out.append(t)
    return out


def calibration_universe(policy: dict, query: QueryFn, *,
                         watchlist_fn: Optional[Callable[[], Iterable[str]]] = None) -> List[str]:
    from lib.config import MarketConfig  # noqa: PLC0415
    from gcp.insight_pipeline_job import DEFAULT_TICKERS  # noqa: PLC0415

    if watchlist_fn is None:
        from gcp.fetchers._watchlist import load_watchlist  # noqa: PLC0415
        watchlist_fn = load_watchlist

    def on_demand():
        return list(query(ON_DEMAND_SQL, {})['ticker'])

    return lc.load_calibration_universe(
        policy, market_tickers=MarketConfig().tickers, insight_tickers=DEFAULT_TICKERS,
        watchlist_fn=watchlist_fn, on_demand_fn=on_demand)


# ── runs ─────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    run_id: str
    rows_written: int = 0
    succeeded: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(tickers: List[str], effective_dates: List[date], *, query: QueryFn, write: WriteFn,
        policy: dict, source: str, run_id: Optional[str] = None) -> RunResult:
    """Calibrate every ticker for every effective date: per ticker one daily
    read, one one-minute read and one write batch holding every date's rows.
    History mode passes every session; nightly mode one date."""
    if not effective_dates:
        raise ValueError("no effective dates")
    run_id = run_id or str(uuid.uuid4())
    res = RunResult(run_id=run_id)
    dates = sorted(pd.Timestamp(d).normalize() for d in effective_dates)
    bounds = read_windows(policy, dates[0], dates[-1])
    atr_basis = policy_atr_basis(policy)
    for i, ticker in enumerate(tickers, 1):
        try:
            daily = read_daily(query, ticker, bounds['daily_start'], bounds['before'])
            minutes = read_minutes(query, ticker, bounds['minutes_start'], bounds['before'])
            prepared = lc.prepare(daily, minutes, policy, dates[-1])
            norm, mins = prepared
            minute_sessions = sorted(set(mins['session'])) if len(mins) else []
            # Each session's replayed trigger depends only on the bars before
            # it, so history mode computes them once for every date.
            triggers = lc.replay_triggers(ticker, lc.daily_before(daily, dates[-1]), norm, policy,
                                          minute_sessions, atr_basis)
            rows: List[dict] = []
            stamp = _now()
            for eff in dates:
                results = lc.calibrate(ticker, daily, minutes, policy, eff, triggers=triggers,
                                       prepared=prepared)
                rows.extend(lc.to_rows(ticker, results, policy, eff, run_id, source, stamp))
            n = write(rows)
        except Exception as exc:  # noqa: BLE001 — logged, ticker skipped, run exits non-zero
            logger.error("calibrate-level-params: %s failed, skipped: %s", ticker, exc)
            res.failed.append(ticker)
            continue
        res.rows_written += int(n or 0)
        res.succeeded.append(ticker)
        ok = sum(1 for r in rows if r['status'] == 'ok')
        logger.info("calibrate-level-params: %d/%d %s wrote %d rows (%d ok) for %d date(s)",
                    i, len(tickers), ticker, len(rows), ok, len(dates))
    return res


def default_effective_from(today: Optional[date] = None) -> date:
    """The session after the last completed one: on a session day before the
    open, today; on a weekend or holiday, the next session."""
    from lib.eastern_time import market_today, next_session, previous_session  # noqa: PLC0415
    return next_session(previous_session(today or market_today()))


def history_sessions(start, end) -> List[date]:
    from lib.eastern_time import sessions_between  # noqa: PLC0415
    return list(sessions_between(start, end))


def _engine_writer() -> WriteFn:
    from sqlalchemy import text  # noqa: PLC0415
    from gcp.database import get_engine  # noqa: PLC0415

    def write(rows: List[dict]) -> int:
        if not rows:
            return 0
        with get_engine().begin() as conn:
            conn.execute(text(UPSERT_SQL), rows)
        return len(rows)
    return write


def main(argv: Optional[List[str]] = None) -> int:
    from gcp.database import query_to_dataframe_strict, record_job_run  # noqa: PLC0415

    parser = argparse.ArgumentParser(description='Calibrate per-ticker level parameters')
    parser.add_argument('--tickers', default=None,
                        help='Comma-separated tickers; default the calibration universe')
    parser.add_argument('--effective-from', default=None,
                        help='Nightly mode: YYYY-MM-DD the rows take effect (default the next session)')
    parser.add_argument('--history', nargs=2, metavar=('START', 'END'), default=None,
                        help='History mode: one version per session from START to END')
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc)
    if args.history:
        dates = history_sessions(args.history[0], args.history[1])
        source, policy_date = 'history', dates[-1]
    else:
        eff = (pd.Timestamp(args.effective_from).date() if args.effective_from
               else default_effective_from())
        dates, source, policy_date = [eff], 'nightly', eff
    policy = read_policy(query_to_dataframe_strict, policy_date)
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    else:
        tickers = calibration_universe(policy, query_to_dataframe_strict)
    logger.info("calibrate-level-params: %s mode, %d ticker(s), %d date(s) %s to %s, policy atr_basis %s",
                source, len(tickers), len(dates), dates[0], dates[-1], policy_atr_basis(policy))
    res = run(tickers, dates, query=query_to_dataframe_strict, write=_engine_writer(),
              policy=policy, source=source)
    logger.info("calibrate-level-params: run %s wrote %d rows, %d ok, %d failed %s",
                res.run_id, res.rows_written, len(res.succeeded), len(res.failed), res.failed)
    record_job_run(JOB_NAME, started, 'failed' if res.failed else 'success', variant=source,
                   items_total=len(tickers), items_processed=len(res.succeeded),
                   items_failed=len(res.failed), rows_written=res.rows_written)
    return res.exit_code


if __name__ == '__main__':
    from lib.logging_config import setup_logging  # noqa: E402
    setup_logging()
    sys.exit(main())
