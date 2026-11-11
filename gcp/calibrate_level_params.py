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
  from START to END, each from bars strictly before that session and under
  the policy rows in force on that session (a policy change part-way through
  the range applies from its effective_from on); replays then read the
  version in force on their session. The per-session samples are measured
  once per ticker (lib.level_calibration.HistoryCalibrator) and the rows are
  written every --chunk-sessions sessions, so a run that stops part-way
  keeps what it wrote and a rerun (ON CONFLICT DO UPDATE) converges.
* --atr-basis COLUMN calibrates in that ATR basis instead of the policy's:
  the preparation run of a basis switch (Design 4), written beside the
  old-basis rows before the policy row that switches the basis is added.

Per ticker: one batched daily read, one batched one-minute read; nightly
mode writes one batch per ticker, history mode one batch per chunk of
sessions. A ticker whose read or calibration fails is logged and skipped and
the run exits non-zero; progress is logged per ticker and chunk.

The job definition, its scheduler entry and the deploy wiring belong to the
companion FEAT-DEPLOY-001 change (Design 9); this module is not in
gcp/deploy.sh.

Usage:
    python -m gcp.calibrate_level_params
    python -m gcp.calibrate_level_params --tickers SPY,QQQ --effective-from 2026-11-09
    python -m gcp.calibrate_level_params --history 2015-01-02 2026-11-06 --tickers SPY
    python -m gcp.calibrate_level_params --history 2015-01-02 2026-11-06 --atr-basis atr_5
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import level_calibration as lc  # noqa: E402
from lib.strat_levels import (  # noqa: E402
    ATR_COLUMNS, POLICY_ATR_BASIS, LevelParamsUnavailable, entry_buffer_key, policy_atr_basis,
    policy_in_force,
)

logger = logging.getLogger(__name__)

JOB_NAME = 'calibrate-level-params'

QueryFn = Callable[..., pd.DataFrame]
WriteFn = Callable[[List[dict]], int]

# History mode writes the rows of this many sessions per batch (an I/O batch
# size, not a calibration threshold): a long run persists as it goes.
HISTORY_CHUNK_SESSIONS = 250

POLICY_SQL = (
    "SELECT param_key, method_id, statistic_q, lookback_sessions, min_sample, extra, "
    "effective_from FROM level_param_policy WHERE effective_from <= :as_of"
)

DAILY_SQL = (
    "SELECT date, open, high, low, close, atr_14, atr_5, sma_200 FROM market_data_daily "
    "WHERE ticker = :ticker AND date >= :start AND date < :before ORDER BY date"
)

MINUTES_SQL = (
    "SELECT ts, open, high, low, close, volume FROM market_data_intraday "
    "WHERE ticker = :ticker AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts"
)

ON_DEMAND_SQL = (
    "SELECT DISTINCT ticker FROM ticker_level_params WHERE source = 'on_demand'"
)

# The shared ('default' owner) watchlist, read through the strict query
# function: gcp.fetchers._watchlist.load_watchlist turns a failed read into
# the INSIGHT_TICKERS env list or [] (Codex P2 on e4bb463e), which would
# shorten the calibration and one-minute fetch universes silently.
WATCHLIST_SQL = (
    "SELECT ticker FROM watchlists WHERE user_id = :user_id AND removed_at IS NULL "
    "ORDER BY added_at"
)
WATCHLIST_OWNER = 'default'

_ROW_COLUMNS = ('ticker', 'param_key', 'value', 'status', 'atr_basis', 'method_id',
                'policy_effective_from', 'sample_n', 'input_from', 'input_to',
                'effective_from', 'run_id', 'source', 'calibrated_at')
_CONFLICT = ('ticker', 'param_key', 'atr_basis', 'effective_from')
# source 'on_demand' is also the ticker's enrollment in the nightly universe
# (ON_DEMAND_SQL). A nightly or manual rerun for the same effective date
# overwrites the values but keeps that mark, so a ticker first calibrated on
# demand before the 04:00 ET run stays in the universe (Codex P2 on 7b12114b).
_KEEP_ON_DEMAND = ("source = CASE WHEN ticker_level_params.source = 'on_demand' "
                   "THEN 'on_demand' ELSE EXCLUDED.source END")
UPSERT_SQL = (
    f"INSERT INTO ticker_level_params ({', '.join(_ROW_COLUMNS)}) VALUES "
    f"({', '.join(':' + c for c in _ROW_COLUMNS)}) "
    f"ON CONFLICT ({', '.join(_CONFLICT)}) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" if c != 'source' else _KEEP_ON_DEMAND
                for c in _ROW_COLUMNS if c not in _CONFLICT)
)


# ── inputs ───────────────────────────────────────────────────────────────


def read_policy_rows(query: QueryFn, as_of) -> List[dict]:
    """Every policy row effective on or before `as_of`. An empty or
    unreadable policy raises: the job never calibrates against a missing
    policy."""
    try:
        rows = query(POLICY_SQL, {'as_of': pd.Timestamp(as_of).date()})
    except Exception as exc:  # noqa: BLE001 — re-raised typed
        raise LevelParamsUnavailable(f"level_param_policy read failed: {exc}") from exc
    if rows is None or rows.empty:
        raise LevelParamsUnavailable(f"level_param_policy has no row in force on {as_of}")
    return rows.to_dict('records')


def policy_on(rows: List[dict], session, *, atr_basis: Optional[str] = None) -> dict:
    """The policy in force on `session` from `rows` (each key's row with
    the greatest effective_from on or before it). `atr_basis` replaces the
    atr_basis row's column (the basis-switch preparation run); the basis is
    checked either way, so a session with no usable basis raises."""
    day = pd.Timestamp(session).normalize()
    policy = policy_in_force([r for r in rows
                              if pd.Timestamp(r['effective_from']).normalize() <= day])
    if not policy:
        raise LevelParamsUnavailable(f"level_param_policy has no row in force on {day.date()}")
    if atr_basis is not None:
        if atr_basis not in ATR_COLUMNS:
            raise ValueError(f"--atr-basis {atr_basis!r} is not one of {sorted(ATR_COLUMNS)}")
        row = dict(policy.get(POLICY_ATR_BASIS) or {'param_key': POLICY_ATR_BASIS,
                                                     'effective_from': None})
        row['extra'] = {**(row.get('extra') or {}), 'column': atr_basis}
        policy[POLICY_ATR_BASIS] = row
    policy_atr_basis(policy)
    return policy


def window_policy_resolver(rows: List[dict], policy: dict) -> Callable[[pd.Timestamp], dict]:
    """For a historical break session `s`, `policy` with its trigger window
    rows replaced by the ones in force on `s` (Design 2: a break uses the
    parameters in force on its own session). Every other row, the ATR basis
    included, stays the calibration date's, so the break population keeps
    one unit; a session before the first policy row keeps `policy`."""
    keys = [lc.trigger_window_key(side) for side in lc.SIDES]
    dated = sorted(((pd.Timestamp(r['effective_from']).normalize(), r) for r in rows),
                   key=lambda x: x[0])
    cache: Dict[pd.Timestamp, dict] = {}

    def at(session) -> dict:
        day = pd.Timestamp(session).normalize()
        if day not in cache:
            then = policy_in_force([r for eff, r in dated if eff <= day])
            out = dict(policy)
            for k in keys:
                if then and k in then:
                    out[k] = then[k]
            cache[day] = out
        return cache[day]
    return at


def read_policy(query: QueryFn, as_of) -> dict:
    """The policy rows in force on `as_of`."""
    return policy_on(read_policy_rows(query, as_of), as_of)


def _max_lookback(policy: dict, keys: Iterable[str]) -> int:
    return max(int(policy[k]['lookback_sessions'] or 0) for k in keys if k in policy)


# Extra NYSE sessions read before the computed start, so a row missing from
# the bar tables does not cut the oldest window short.
READ_SLACK_SESSIONS = 5


def sessions_before(day, n: int) -> date:
    """The NYSE session `n` sessions before `day` (`day` itself not counted),
    from lib.eastern_time's exchange calendar, so holidays never shorten a
    lookback."""
    from datetime import timedelta  # noqa: PLC0415

    from lib.eastern_time import sessions_between  # noqa: PLC0415

    end = pd.Timestamp(day).date() - timedelta(days=1)
    if n <= 0:
        return pd.Timestamp(day).date()
    span = 2 * int(n) + 30   # 252 sessions a year: 2n calendar days always hold n sessions
    days = sessions_between(end - timedelta(days=span), end)
    if len(days) < n:
        raise RuntimeError(f"NYSE calendar gives {len(days)} sessions before {day}, need {n}")
    return days[-int(n)]


def read_windows(policies: Iterable[dict], first_session, last_session) -> dict:
    """Read bounds for one ticker whose rows are effective from
    `first_session` through `last_session` under `policies` (each policy in
    force on some of those sessions), counted in NYSE sessions: the daily
    bars a trigger window replayed on the earliest break session needs (the
    longest break-derived lookback, lc.break_lookback, then a trigger-window
    lookback and the prior ATR before it, or the longest one-minute lookback
    and its prior ATR when that is longer), and the one-minute bars the
    breaks and the one-minute thresholds read, under the longest lookbacks;
    each start is READ_SLACK_SESSIONS earlier still."""
    if isinstance(policies, dict):
        policies = [policies]
    first = pd.Timestamp(first_session)
    daily_start, minutes_start = None, None
    for policy in policies:
        window_lb = _max_lookback(policy, ('trigger_window_long_atr', 'trigger_window_short_atr'))
        break_lb = lc.break_lookback(policy)
        minute_lb = max(break_lb, _max_lookback(policy, (lc.PM_SPIKE_KEY, lc.PM_STALE_PRINT_KEY,
                                                         lc.LEVEL_CLUSTER_KEY)))
        # the one-minute samplers pick sessions from the daily frame and read
        # each one's prior ATR there, so the daily read covers their lookback too
        ds = sessions_before(first, max(break_lb + window_lb, minute_lb) + 1 + READ_SLACK_SESSIONS)
        ms = sessions_before(first, minute_lb + READ_SLACK_SESSIONS)
        daily_start = ds if daily_start is None else min(daily_start, ds)
        minutes_start = ms if minutes_start is None else min(minutes_start, ms)
    return {'daily_start': daily_start, 'minutes_start': minutes_start,
            'before': pd.Timestamp(last_session).date()}


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


def strict_watchlist(query: QueryFn) -> List[str]:
    """The shared watchlist's active tickers. A failed read raises (query
    is a strict reader); an empty result is a genuinely empty watchlist."""
    df = query(WATCHLIST_SQL, {'user_id': WATCHLIST_OWNER})
    return [] if df is None or not len(df) else [str(t) for t in df['ticker']]


def brief_insight_watchlist_tickers(*, watchlist_fn: Optional[Callable[[], Iterable[str]]] = None
                                    ) -> List[str]:
    """The brief tickers (lib.config MarketConfig.tickers), the insight
    default tickers (gcp.insight_pipeline_job.DEFAULT_TICKERS) and the
    watchlist, deduplicated: the one-minute fetch universe (Design 5). The
    watchlist is read strictly: a failed read raises instead of shortening
    the universe."""
    from lib.config import MarketConfig  # noqa: PLC0415
    from gcp.insight_pipeline_job import DEFAULT_TICKERS  # noqa: PLC0415

    if watchlist_fn is None:
        from gcp.database import query_to_dataframe_strict  # noqa: PLC0415
        watchlist_fn = lambda: strict_watchlist(query_to_dataframe_strict)  # noqa: E731
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
        watchlist_fn = lambda: strict_watchlist(query)  # noqa: E731

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
        policy_rows: List[dict], source: str, run_id: Optional[str] = None,
        chunk_sessions: Optional[int] = None, atr_basis: Optional[str] = None) -> RunResult:
    """Calibrate every ticker for every effective date, each date under the
    policy in force on it (`policy_rows`, every row effective on or before
    the last date; `atr_basis` overrides the basis for every date). Per
    ticker one daily read and one one-minute read; the rows go out every
    `chunk_sessions` dates (None: one batch per ticker), so a failure keeps
    the chunks already written."""
    if not effective_dates:
        raise ValueError("no effective dates")
    if chunk_sessions is not None and chunk_sessions < 1:
        raise ValueError("chunk_sessions must be at least 1")
    run_id = run_id or str(uuid.uuid4())
    res = RunResult(run_id=run_id)
    dates = sorted({pd.Timestamp(d).normalize() for d in effective_dates})
    policies = {eff: policy_on(policy_rows, eff, atr_basis=atr_basis) for eff in dates}
    unique: List[dict] = []
    for p in policies.values():
        if p not in unique:
            unique.append(p)
    resolvers = [window_policy_resolver(policy_rows, p) for p in unique]
    window_at = {eff: resolvers[unique.index(policies[eff])] for eff in dates}
    # A break session replays under the trigger window rows in force on it,
    # so the daily read covers each calibration policy combined with every
    # trigger window version in policy_rows (Codex P2 on 2a53b166: a
    # shortened window lookback must not truncate older break sessions).
    window_keys = {lc.trigger_window_key(side) for side in lc.SIDES}
    versions = sorted({pd.Timestamp(r['effective_from']).normalize() for r in policy_rows
                       if r.get('param_key') in window_keys})
    bound_policies = list(unique)
    for at in resolvers:
        for v in versions:
            q = at(v)
            if q not in bound_policies:
                bound_policies.append(q)
    bounds = read_windows(bound_policies, dates[0], dates[-1])
    chunk = chunk_sessions or len(dates)
    for i, ticker in enumerate(tickers, 1):
        written = ok = 0
        try:
            daily = read_daily(query, ticker, bounds['daily_start'], bounds['before'])
            minutes = read_minutes(query, ticker, bounds['minutes_start'], bounds['before'])
            hc = lc.HistoryCalibrator(ticker, daily, minutes, dates[-1])
            for start in range(0, len(dates), chunk):
                part = dates[start:start + chunk]
                rows: List[dict] = []
                stamp = _now()
                for eff in part:
                    policy = policies[eff]
                    rows.extend(lc.to_rows(ticker, hc.calibrate(policy, eff, window_at[eff]),
                                           policy, eff,
                                           run_id, source, stamp))
                written += int(write(rows) or 0)
                ok += sum(1 for r in rows if r['status'] == 'ok')
                if len(dates) > chunk:
                    logger.info("calibrate-level-params: %s wrote sessions %s to %s (%d/%d)",
                                ticker, part[0].date(), part[-1].date(),
                                start + len(part), len(dates))
        except Exception as exc:  # noqa: BLE001 — logged, ticker skipped, run exits non-zero
            logger.error("calibrate-level-params: %s failed, skipped (%d rows written before "
                         "the failure stay): %s", ticker, written, exc)
            res.rows_written += written
            res.failed.append(ticker)
            continue
        res.rows_written += written
        res.succeeded.append(ticker)
        logger.info("calibrate-level-params: %d/%d %s wrote %d rows (%d ok) for %d date(s)",
                    i, len(tickers), ticker, written, ok, len(dates))
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
    parser.add_argument('--chunk-sessions', type=int, default=None,
                        help=f'History mode: sessions per write batch (default {HISTORY_CHUNK_SESSIONS})')
    parser.add_argument('--atr-basis', default=None, choices=sorted(ATR_COLUMNS),
                        help='Calibrate in this ATR basis instead of the policy\'s: the preparation '
                             'run of a basis switch, before its policy row is added')
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc)
    if args.history:
        dates = history_sessions(args.history[0], args.history[1])
        source, policy_date = 'history', dates[-1]
        chunk = args.chunk_sessions or HISTORY_CHUNK_SESSIONS
    else:
        eff = (pd.Timestamp(args.effective_from).date() if args.effective_from
               else default_effective_from())
        dates, source, policy_date = [eff], 'nightly', eff
        chunk = None
    policy_rows = read_policy_rows(query_to_dataframe_strict, policy_date)
    policy = policy_on(policy_rows, policy_date, atr_basis=args.atr_basis)
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]
    else:
        tickers = calibration_universe(policy, query_to_dataframe_strict)
    logger.info("calibrate-level-params: %s mode, %d ticker(s), %d date(s) %s to %s, atr_basis %s%s",
                source, len(tickers), len(dates), dates[0], dates[-1], policy_atr_basis(policy),
                ' (--atr-basis)' if args.atr_basis else ' (policy in force on each date)')
    res = run(tickers, dates, query=query_to_dataframe_strict, write=_engine_writer(),
              policy_rows=policy_rows, source=source, chunk_sessions=chunk,
              atr_basis=args.atr_basis)
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
