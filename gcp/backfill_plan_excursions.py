"""The plan excursions history job (FEAT-STRAT-001 target hit rates r2 spec,
docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md,
Design 4 "History, once per entry version", and Design 6).

For each session and ticker it rebuilds the level basis the way the brief
builds it under BRIEF_AS_OF (generate_premarket_brief with
no_persist=True, BRIEF_AMC_REACTIONS=0 and BRIEF_LLM_DISABLE=1, so no
session writes strat_levels or premarket rows and no session makes a model
call), scores both sides with the resolver's own plan_inputs and
plan_excursion on the session's as-traded 1-minute bars from
market_data_intraday (cut at the exchange's close), picks the day's trade
with trade_of_day, and writes plan_excursions rows with source 'history',
keyed by the entry rule version of the rebuilt basis's version and carrying
the basis's own ATR (basis_atr) with the excursions in ATR.

It never writes premarket_analysis, premarket_analysis_history or
strat_levels, and a history write never replaces a resolver row. A session
that now gives no trade has its own history row deleted. A session whose
basis cannot be built, or that has no bars, is reported and left as it is.

One bar query per ticker-month. With no range it resumes after the last
session it wrote for each ticker; an explicit --start/--end reprocesses
every session in the range.

    python -m gcp.backfill_plan_excursions [--tickers SPY,QQQ,IWM]
                                          [--start 2022-01-03] [--end 2026-11-10]
"""
from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd
from sqlalchemy import text

from gcp.premarket_playbook_resolver import (
    basis_atr, excursion_statement, plan_excursion, plan_inputs, trade_of_day,
)
from lib.eastern_time import ET, previous_session, session_close, sessions_between

logger = logging.getLogger(__name__)

SOURCE = 'history'

# One ticker-month of 1-minute bars, regular session only (the resolver's
# own RTH window); each session is then cut at its exchange close.
_MONTH_BARS_SQL = text("""
    SELECT ts AS time, open, high, low, close
    FROM market_data_intraday
    WHERE ticker = :t
      AND interval = '1min'
      AND ts >= :start AND ts < :end
      AND (ts AT TIME ZONE 'America/New_York')::time >= '09:30'
      AND (ts AT TIME ZONE 'America/New_York')::time <  '16:00'
    ORDER BY ts
""")

_LAST_WRITTEN_SQL = text(
    "SELECT MAX(session_date) AS d FROM plan_excursions "
    "WHERE ticker = :t AND rule_version = :v AND source = 'history'")


@dataclass
class TickerStats:
    ticker: str
    sessions: int = 0
    written: int = 0
    deleted: int = 0
    no_trade: int = 0
    no_basis: List[str] = field(default_factory=list)
    no_bars: List[str] = field(default_factory=list)
    seconds: float = 0.0

    def line(self) -> str:
        return (f"{self.ticker}: {self.sessions} sessions read, {self.written} rows written, "
                f"{self.deleted} rows deleted, {self.no_trade} with no trade, "
                f"{len(self.no_basis)} with no basis, {len(self.no_bars)} with no bars, "
                f"{self.seconds:.1f}s")


@contextlib.contextmanager
def _replay_env(ticker: str, session: date):
    """The brief's replay switches for one session, restored afterwards."""
    want = {'BRIEF_AS_OF': session.isoformat(), 'BRIEF_TICKERS': ticker,
            'BRIEF_AMC_REACTIONS': '0', 'BRIEF_LLM_DISABLE': '1'}
    saved = {k: os.environ.get(k) for k in want}
    os.environ.update(want)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def brief_basis(ticker: str, session: date, cfg=None) -> Optional[dict]:
    """The level basis the brief builds for `ticker` on `session`, through
    generate_premarket_brief itself with nothing persisted. None when the
    brief built no basis for the ticker (no data, a failed playbook)."""
    from gcp.premarket_brief import generate_premarket_brief  # noqa: PLC0415
    from lib.strat_levels import parse_level_basis  # noqa: PLC0415
    with _replay_env(ticker, session):
        brief = generate_premarket_brief(cfg=cfg, no_persist=True)
    entry = (brief.get('tickers') or {}).get(ticker.upper()) or {}
    if entry.get('status') in ('PLAYBOOK_FAILED', 'STALE_DAILY_DATA'):
        return None
    return parse_level_basis(entry.get('level_basis'))


def _month_spans(sessions: Iterable[date]) -> Dict[tuple, List[date]]:
    out: Dict[tuple, List[date]] = {}
    for s in sessions:
        out.setdefault((s.year, s.month), []).append(s)
    return out


def read_month_bars(engine, ticker: str, sessions: List[date]) -> pd.DataFrame:
    """ONE query: the ticker's RTH 1-minute bars over the sessions of one
    month, with a UTC 'time' column."""
    start = datetime.combine(sessions[0], datetime.min.time(), tzinfo=ET)
    end = datetime.combine(sessions[-1] + timedelta(days=1), datetime.min.time(), tzinfo=ET)
    bars = pd.read_sql(_MONTH_BARS_SQL, engine,
                       params={'t': ticker.upper(), 'start': start, 'end': end})
    if not bars.empty:
        bars['time'] = pd.to_datetime(bars['time'], utc=True)  # tz-ok: ts is TIMESTAMPTZ, UTC by contract
    return bars


def session_bars(month: pd.DataFrame, session: date) -> pd.DataFrame:
    """The session's bars from 09:30 ET to its exchange close."""
    if month.empty:
        return month
    et_day = month['time'].dt.tz_convert(ET).dt.date
    close_utc = pd.Timestamp(session_close(session))
    day = month[(et_day == session) & (month['time'] < close_utc)]
    return day.reset_index(drop=True)


def _no_v2_policy():
    # A fresh brief basis is the current rule version, which carries its own
    # plan; the v2 fallback that reads the policy never applies here.
    raise RuntimeError("history job: a v2 basis has no place in a fresh replay")


def score_session(ticker: str, session: date, basis: dict, bars: pd.DataFrame):
    """The day's plan_excursions statement (or None for a basis with no
    entry rule version): both sides scored with the basis's ATR, the first
    to fill kept, keyed by entry_rule_version of the basis's version."""
    from lib.strat_levels import entry_rule_version  # noqa: PLC0415
    calls_in = plan_inputs('calls', {}, basis, _no_v2_policy)
    puts_in = plan_inputs('puts', {}, basis, _no_v2_policy)
    atr = basis_atr(basis)
    trade = trade_of_day(plan_excursion('call', calls_in, bars, atr),
                         plan_excursion('put', puts_in, bars, atr))
    stmt = excursion_statement(ticker, session, entry_rule_version(basis.get('rule_version')), trade,
                               {'calls': calls_in, 'puts': puts_in}, SOURCE)
    return trade, stmt


def last_written(engine, ticker: str, rule_version: str) -> Optional[date]:
    df = pd.read_sql(_LAST_WRITTEN_SQL, engine,
                     params={'t': ticker.upper(), 'v': rule_version})
    v = df['d'].iloc[0] if len(df) else None
    if v is None or pd.isna(v):
        return None
    return v if isinstance(v, date) and not isinstance(v, datetime) else pd.Timestamp(v).date()


def run(engine, tickers: Iterable[str], start: date, end: date, *, resume: bool,
        basis_fn: Callable[[str, date], Optional[dict]] = brief_basis,
        log: Callable[[str], None] = print) -> List[TickerStats]:
    """Write the history rows for every ticker over [start, end]. With
    `resume`, each ticker starts after the last session it has a history
    row for. Returns per-ticker stats (also printed through `log`)."""
    from lib.strat_levels import LEVEL_RULE_VERSION, entry_rule_version  # noqa: PLC0415
    out = []
    for ticker in [t.strip().upper() for t in tickers if t and t.strip()]:
        t0 = time.monotonic()
        stats = TickerStats(ticker)
        first = start
        if resume:
            done = last_written(engine, ticker, entry_rule_version(LEVEL_RULE_VERSION))
            if done is not None and done >= first:
                first = done + timedelta(days=1)
        for _, sessions in sorted(_month_spans(sessions_between(first, end)).items()):
            month = read_month_bars(engine, ticker, sessions)
            for session in sessions:
                stats.sessions += 1
                bars = session_bars(month, session)
                if bars.empty:
                    stats.no_bars.append(session.isoformat())
                    continue
                basis = basis_fn(ticker, session)
                if not basis:
                    stats.no_basis.append(session.isoformat())
                    continue
                trade, stmt = score_session(ticker, session, basis, bars)
                if stmt is None:
                    stats.no_basis.append(session.isoformat())
                    continue
                with engine.begin() as conn:
                    res = conn.execute(*stmt)
                if trade is None:
                    stats.no_trade += 1
                    stats.deleted += max(res.rowcount or 0, 0)
                else:
                    stats.written += max(res.rowcount or 0, 0)
        stats.seconds = time.monotonic() - t0
        log(stats.line())
        if stats.no_basis:
            log(f"{ticker}: no basis on {', '.join(stats.no_basis[:20])}"
                + (' ...' if len(stats.no_basis) > 20 else ''))
        if stats.no_bars:
            log(f"{ticker}: no bars on {', '.join(stats.no_bars[:20])}"
                + (' ...' if len(stats.no_bars) > 20 else ''))
        out.append(stats)
    return out


def _policy_since(engine) -> date:
    """The target_reach_rate policy row's `since` (Design 1)."""
    from lib.strat_levels import TARGET_REACH_RATE_KEY, load_level_params  # noqa: PLC0415
    today = datetime.now(ET).date()
    params = load_level_params(lambda sql, p: pd.read_sql(text(sql), engine, params=p),
                               ['SPY'], today)['SPY']
    p = params.param(TARGET_REACH_RATE_KEY)
    since = (p.extra or {}).get('since')
    if not p.ok or not since:
        raise RuntimeError(f"{TARGET_REACH_RATE_KEY} row gives no since ({p.status})")
    return date.fromisoformat(since)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s :: %(message)s')
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--tickers', default=None,
                    help='comma-separated tickers (default: the config tickers)')
    ap.add_argument('--start', default=None, help="first session (default: the policy's since)")
    ap.add_argument('--end', default=None, help='last session (default: the last full session)')
    args = ap.parse_args(argv)

    from gcp.database import get_engine  # noqa: PLC0415
    from lib.config import load_config  # noqa: PLC0415
    cfg = load_config()
    engine = get_engine()
    tickers = (args.tickers.split(',') if args.tickers else list(cfg.market.tickers))
    explicit = args.start is not None or args.end is not None
    start = date.fromisoformat(args.start) if args.start else _policy_since(engine)
    end = (date.fromisoformat(args.end) if args.end
           else previous_session(datetime.now(ET).date()))
    print(f"plan excursions history: {','.join(tickers)} {start} to {end} "
          f"({'explicit range, reprocessing' if explicit else 'resuming'})", flush=True)
    run(engine, tickers, start, end, resume=not explicit,
        basis_fn=lambda t, s: brief_basis(t, s, cfg),
        log=lambda line: print(line, flush=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
