"""FEAT-STRAT-001 ATR mark targets: the Experiment of
docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md
("Experiment"), run through the production paths into LOCAL databases.

Each arm is a database cloned from one loaded and calibrated template, which
differs from the others only in the policy rows arm_policy_sql inserts. Every
session is built by the production brief (gcp.premarket_brief.main with
BRIEF_AS_OF) and every ticker-day is scored by the production resolver
(gcp.premarket_playbook_resolver.plan_inputs and resolve_plan) on the basis the
brief stored. This file walks no bar, computes no indicator and no level, and
never sets the targets or the legs of a plan: it loops over dates, selects
rows with the resolver's own filter, and counts what the production code wrote
(CLAUDE.md 3.6). tests/scripts/test_atr_marks_experiment.py holds it to that.

Subcommands, each of which calls require_local_db first:

  load EXPORT_DIR BARS_DIR        the daily and calibration export and the
                                  bucket's 1-minute bars into DB_NAME
  placeholder FROM TO [--check]   mark sessions with no premarket value so the
                                  recompute selects them; --check lists any
                                  the recompute left (refused, never traded)
  replay ARM FROM TO [--part I --parts N]
  score FROM TO --out CSV --days-out CSV [--db ARM=NAME ...]
  report CSV
  baseline FROM TO --days-out CSV the harness check: arm A alone, DB_NAME only
  compare BASE_DAYS HEAD_DAYS     trigger-changed ticker-days between two runs

The harness check runs this file from the PR head with the working directory
and PYTHONPATH set to a detached worktree of 97190ef41, so every gcp and lib
import is that commit's. The module-level imports below are only names that
commit has; what only the head has is imported inside score and report.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import sqlalchemy

from gcp.database import get_engine
from gcp.fetchers.export_intraday_bars import read_bars
from gcp.premarket_brief import main as brief_main
from gcp.premarket_playbook_resolver import PlanOutcome, plan_inputs, resolve_plan
from lib.eastern_time import session_close, sessions_between
from lib.strat_levels import SessionLevels, parse_level_basis, price_cents

# The arms: (marks, exit legs). A is the seeded policy (today's plan).
ARMS = {'A': ((), 3), 'Q': ((0.25, 0.5, 0.75, 1.0), 4), 'Q3': ((0.25, 0.5, 0.75), 3)}
ARM_DBS = {'A': 'arm_a', 'Q': 'arm_q', 'Q3': 'arm_q3'}
TICKERS = ('SPY', 'QQQ', 'IWM')
# The gap-edges spec's two left-out ticker-days.
LEFT_OUT = {('SPY', '2025-04-09'), ('IWM', '2026-06-26')}
# lib.data_loader decides Cloud SQL from this variable alone while
# gcp.database lets DB_HOST win for the engine, so a run names a connection
# no Cloud SQL instance has.
LOCAL_SQL_NAME = 'local-experiment-not-cloud'
LOCAL_HOSTS = ('127.0.0.1', 'localhost')
# One day after the seeded rows, so an arm's rows are in force for every
# replayed session and never collide with the seeded key.
ARM_POLICY_DATE = '2015-01-03'
# A premarket VWAP no real session can hold: set by `placeholder` in the local
# template only, so the recompute selects every session of the range.
PLACEHOLDER_PRE_VWAP = -1
MARKS_VERSION = 'feat-strat-001.v6'
SPIKE_DIR = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'atr_marks_spike_2026-11-16'
DRAWS, SEED = 2000, 7
MODULES = ('gcp.premarket_brief', 'gcp.premarket_playbook_resolver', 'lib.strat_levels')

ROWS_SQL = sqlalchemy.text(
    "SELECT analysis_date, ticker, calls_trigger_price, calls_stop_price, calls_t1_price, "
    "calls_t2_price, calls_t3_price, puts_trigger_price, puts_stop_price, puts_t1_price, "
    "puts_t2_price, puts_t3_price, level_basis FROM premarket_analysis "
    "WHERE ticker = :t AND analysis_date BETWEEN :a AND :b ORDER BY analysis_date")
# The resolver's RTH filter (resolve_one), over the whole range at once.
BARS_SQL = sqlalchemy.text(
    "SELECT ts AS time, open, high, low, close, "
    "(ts AT TIME ZONE 'America/New_York')::date AS d FROM market_data_intraday "
    "WHERE ticker = :t AND (ts AT TIME ZONE 'America/New_York')::date BETWEEN :a AND :b "
    "AND (ts AT TIME ZONE 'America/New_York')::time >= '09:30' "
    "AND (ts AT TIME ZONE 'America/New_York')::time < '16:00' "
    "AND interval = '1min' ORDER BY ts")


class NotLocal(RuntimeError):
    """The environment does not name a local database with the model off."""


def require_local_db() -> None:
    """Refuse to run unless DB_HOST is local, the Cloud SQL connection name is
    the experiment's dummy and the brief's model calls are off."""
    host = os.environ.get('DB_HOST', '')
    if host not in LOCAL_HOSTS:
        raise NotLocal(f"DB_HOST={host!r}: the experiment runs only on {LOCAL_HOSTS}")
    name = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
    if name != LOCAL_SQL_NAME:
        raise NotLocal(f"CLOUD_SQL_CONNECTION_NAME={name!r}: set it to {LOCAL_SQL_NAME!r}")
    if os.environ.get('BRIEF_LLM_DISABLE') != '1':
        raise NotLocal("BRIEF_LLM_DISABLE must be 1: the replay never calls the model")


def arm_policy_sql(arm: str) -> Optional[str]:
    """The level_param_policy rows that make `arm`'s database, or None for A."""
    marks, legs = ARMS[arm]
    if not marks:
        return None
    rows = [("plan_target_marks_atr", {'marks': list(marks)},
             'targets at these distances from the entry trigger / ATR, nearest first')]
    if legs != ARMS['A'][1]:
        rows.append(('exit_legs', {'legs': legs}, 'equal legs the exit plan sells'))
    values = ',\n       '.join(
        f"('{key}', 'policy', NULL, NULL, NULL, '{json.dumps(extra)}', '{ARM_POLICY_DATE}', "
        f"'{note} (atr marks experiment, arm {arm})')" for key, extra, note in rows)
    return ("INSERT INTO level_param_policy (param_key, method_id, statistic_q, "
            "lookback_sessions, min_sample, extra, effective_from, note)\nVALUES " + values
            + "\nON CONFLICT (param_key, effective_from) DO NOTHING")


def pick_trade(calls: PlanOutcome, puts: PlanOutcome) -> tuple:
    """(side, None) or (None, reason): the spike's rule (variant `side`). Each
    side is judged alone; a side that opened through its trigger is never the
    pick; one entered side is the trade; with both, the earlier fill; one fill
    bar for both is no trade."""
    entered = [s for s, o in (('calls', calls), ('puts', puts)) if o.entry_status == 'entered']
    if len(entered) == 2:
        if calls.fill_ts == puts.fill_ts:
            return None, 'same_bar_tie'
        return ('calls' if calls.fill_ts < puts.fill_ts else 'puts'), None
    if entered:
        return entered[0], None
    return None, 'no_entry'


# ── databases ───────────────────────────────────────────────────────────

def _psql_env(db_name: str) -> dict:
    env = dict(os.environ)
    env.update(PGHOST=os.environ['DB_HOST'], PGPORT=os.environ.get('DB_PORT', '5432'),
               PGUSER=os.environ.get('DB_USER', ''), PGPASSWORD=os.environ.get('DB_PASS', ''),
               PGDATABASE=db_name)
    return env


def _arm_engine(arm: str, dbs: dict):
    """An engine on `arm`'s database, by the URL gcp.database builds for DB_HOST."""
    from urllib.parse import quote_plus
    url = (f"postgresql+pg8000://{quote_plus(os.environ.get('DB_USER', ''))}:"
           f"{quote_plus(os.environ.get('DB_PASS', ''))}@{os.environ['DB_HOST']}:"
           f"{os.environ.get('DB_PORT', '5432')}/{dbs[arm]}")
    return sqlalchemy.create_engine(url)


def _copy(table: str, frame: pd.DataFrame) -> None:
    """COPY `frame` into `table` of DB_NAME through psql."""
    cols = ', '.join(frame.columns)
    proc = subprocess.run(
        ['psql', '-v', 'ON_ERROR_STOP=1', '-c',
         f"\\copy {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')"],
        input=frame.to_csv(index=False, header=False, na_rep=''), text=True,
        capture_output=True, env=_psql_env(os.environ['DB_NAME']))
    print(table, len(frame), proc.stdout.strip(), proc.stderr.strip()[:500], flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"COPY into {table} failed: {proc.stderr.strip()[:500]}")


def _columns(engine, table: str) -> set:
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(sqlalchemy.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {'t': table})}


def load(export_dir: str, bars_dir: str, first_month: str = '2015-01',
         last_month: str = '2026-11') -> None:
    """The export's result_001.csv (market_data_daily, pre_filter_params as
    text in pfp_text) and result_002.csv (ticker_calibration), and each
    ticker's bucket bars through read_bars, into DB_NAME. A column the local
    schema lacks is named and left out."""
    require_local_db()
    engine = get_engine()
    daily = pd.read_csv(Path(export_dir) / 'result_001.csv', dtype=str, keep_default_na=False)
    daily['pre_filter_params'] = daily['pfp_text']
    daily = daily.drop(columns=[c for c in ('id', 'pfp_text') if c in daily.columns])
    for c in ('volume', 'consecutive_up', 'consecutive_down', 'pre_volume',
              'pre_excluded_stale_prints', 'pre_excluded_spikes'):
        if c in daily.columns:
            daily[c] = daily[c].str.removesuffix('.0')
    local = _columns(engine, 'market_data_daily')
    print('export columns the local schema lacks:', [c for c in daily.columns if c not in local])
    _copy('market_data_daily', daily[[c for c in daily.columns if c in local]])
    cal = pd.read_csv(Path(export_dir) / 'result_002.csv', dtype=str, keep_default_na=False)
    local = _columns(engine, 'ticker_calibration')
    _copy('ticker_calibration', cal[[c for c in cal.columns if c in local]])
    for t in TICKERS:
        # read_bars raises naming a month the download lacks: stop and report
        # it, never refetch from the vendor.
        bars, months = read_bars(bars_dir, t, first_month, last_month)
        print(t, len(bars), 'bars over', len(months), 'months', flush=True)
        bars = bars.assign(ticker=t, interval='1min')[
            ['ticker', 'ts', 'interval', 'open', 'high', 'low', 'close', 'volume', 'data_source']]
        _copy('market_data_intraday', bars)


def placeholder(start: str, end: str, check: bool = False) -> list:
    """Without --check, write PLACEHOLDER_PRE_VWAP on every session of the
    range that holds no premarket value, so the recompute selects it. With
    --check, list the (ticker, date) still holding it after the recompute:
    those were refused, and replay leaves them out."""
    require_local_db()
    params = {'tickers': list(TICKERS), 'a': start, 'b': end, 'v': PLACEHOLDER_PRE_VWAP}
    with get_engine().begin() as conn:
        if not check:
            n = conn.execute(sqlalchemy.text(
                "UPDATE market_data_daily SET pre_vwap = :v WHERE ticker = ANY(:tickers) "
                "AND date BETWEEN :a AND :b AND close IS NOT NULL AND pre_high IS NULL "
                "AND pre_low IS NULL AND pre_vwap IS NULL AND gap_pct IS NULL"), params).rowcount
            print(f"placeholder: {n} sessions marked", flush=True)
        left = [(r[0], str(r[1])) for r in conn.execute(sqlalchemy.text(
            "SELECT ticker, date FROM market_data_daily WHERE ticker = ANY(:tickers) "
            "AND date BETWEEN :a AND :b AND pre_vwap = :v ORDER BY ticker, date"), params)]
    if check:
        print(f"placeholder check: {len(left)} sessions still hold the placeholder"
              + (f": {left}" if left else ''), flush=True)
    return left


# ── replay ──────────────────────────────────────────────────────────────

def replay(arm: str, start: str, end: str, part: int = 0, parts: int = 1) -> list:
    """Build every session of the range with gcp.premarket_brief.main and
    BRIEF_AS_OF, into DB_NAME, after inserting the arm's policy rows. A
    ticker-day that still holds the placeholder is left out and named."""
    require_local_db()
    sql = arm_policy_sql(arm)
    if sql is not None:
        with get_engine().begin() as conn:
            conn.exec_driver_sql(sql)
    refused = set(placeholder(start, end, check=True))
    os.environ['BRIEF_TRIGGERED_BY'] = f'atr-marks-experiment-{arm}'
    failures = []
    dates = list(sessions_between(start, end))[part::parts]
    for n, d in enumerate(dates, 1):
        tickers = [t for t in TICKERS if (t, d.isoformat()) not in refused]
        if not tickers:
            continue
        os.environ['BRIEF_TICKERS'] = ','.join(tickers)
        os.environ['BRIEF_AS_OF'] = d.isoformat()
        try:
            code = brief_main([])
        except SystemExit as exc:
            code = exc.code
        if code not in (None, 0):
            failures.append((d.isoformat(), code))
            print(f"FAIL {d} exit {code}", flush=True)
        if n % 25 == 0 or n == len(dates):
            print(f"replay {arm} part {part}/{parts}: {n}/{len(dates)} through {d}, "
                  f"failures {len(failures)}", flush=True)
    return failures


# ── scoring ─────────────────────────────────────────────────────────────

def _no_policy():
    raise RuntimeError("a basis under the pick rule never reads the policy tables")


def _days(engine, start: str, end: str):
    """Each scored ticker-day: (ticker, day, row, basis, the RTH bars cut at
    the exchange's close, as resolve_one cuts them). Left-out days, days with
    no bars and rows with no basis are skipped."""
    for t in TICKERS:
        rows = pd.read_sql(ROWS_SQL, engine, params={'t': t, 'a': start, 'b': end})
        bars = pd.read_sql(BARS_SQL, engine, params={'t': t, 'a': start, 'b': end})
        bars['time'] = pd.to_datetime(bars['time'], utc=True)  # tz-ok: TIMESTAMPTZ ts, UTC instants, as resolve_one reads them
        by_day = {str(d): g.drop(columns='d').reset_index(drop=True) for d, g in bars.groupby('d')}
        for row in rows.to_dict('records'):
            day = str(row['analysis_date'])
            day_bars = by_day.get(day)
            basis = parse_level_basis(row.get('level_basis'))
            if (t, day) in LEFT_OUT or day_bars is None or day_bars.empty or basis is None:
                continue
            close_utc = pd.Timestamp(session_close(pd.Timestamp(day).date()))
            yield t, day, row, basis, day_bars[day_bars['time'] < close_utc].reset_index(drop=True)


def _score_day(row: dict, basis: dict, bars: pd.DataFrame) -> tuple:
    res = {}
    for side, direction in (('calls', 'call'), ('puts', 'put')):
        p = plan_inputs(side, row, basis, _no_policy)
        res[side] = (p, resolve_plan(direction, p, bars))
    pick, reason = pick_trade(res['calls'][1], res['puts'][1])
    return res, pick, reason


def _baseline_days(engine, start: str, end: str) -> pd.DataFrame:
    """Arm A on DB_NAME, one row a ticker-day: both triggers and stops (empty
    when the basis lacks one), the pick or why none, and the pick's R, exit
    and targets."""
    out = []
    for t, day, row, basis, bars in _days(engine, start, end):
        res, pick, reason = _score_day(row, basis, bars)
        rec = {'ticker': t, 'date': day, 'side': pick or '', 'reason': reason or ''}
        for side in ('calls', 'puts'):
            rec[f'{side}_trigger'] = res[side][0].trigger_price
            rec[f'{side}_stop'] = res[side][0].stop_price
        p, o = res[pick] if pick else (None, None)
        rec['r'] = o.r if o else None
        rec['exit'] = o.exit if o else None
        rec['targets'] = json.dumps(list(p.targets)) if p else None
        out.append(rec)
    return pd.DataFrame(out, columns=['ticker', 'date', 'calls_trigger', 'puts_trigger',
                                      'calls_stop', 'puts_stop', 'side', 'reason', 'r',
                                      'exit', 'targets'])


def _totals(days: pd.DataFrame) -> dict:
    traded = days[days['side'].fillna('') != '']
    return {'total': float(traded['r'].astype(float).sum()), 'trades': int(len(traded)),
            'by_ticker': {t: round(float(traded.loc[traded['ticker'] == t, 'r'].astype(float).sum()), 2)
                          for t in TICKERS}}


def _module_paths() -> dict:
    return {name: sys.modules[name].__file__ for name in MODULES}


def _git_head(cwd: Path) -> str:
    proc = subprocess.run(['git', '-C', str(cwd), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def baseline(start: str, end: str, days_out: str) -> dict:
    """The harness check (r2, Experiment, "Arm A is checked twice", (a)):
    arm A alone, from DB_NAME's database only. It prints the working
    directory's HEAD and the files the three production modules were
    imported from, and refuses to score when any of them is not under the
    working directory, so a run whose imports resolved elsewhere cannot pass
    as the check."""
    require_local_db()
    cwd = Path.cwd().resolve()
    sha = _git_head(cwd)
    paths = _module_paths()
    print(f"working directory {cwd} HEAD {sha}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    outside = [name for name, path in paths.items() if cwd not in Path(path).resolve().parents]
    if outside:
        raise RuntimeError(f"modules imported from outside {cwd}: {outside}")
    days = _baseline_days(get_engine(), start, end)
    days.to_csv(days_out, index=False)
    totals = _totals(days)
    print(f"arm A total {totals['total']:+.2f} R over {totals['trades']} trades; "
          f"by ticker {totals['by_ticker']}")
    return {'sha': sha, 'paths': paths, **totals}


def score(start: str, end: str, out: str, days_out: str, dbs: Optional[dict] = None) -> pd.DataFrame:
    """Every trade of every arm: each arm's database, its own bases, the same
    pick rule. The three arms must pick the same ticker-days with the same
    trigger, stop and fill, and every basis must carry its arm's rule version
    (the marks version for Q and Q3, a level-rule version for A)."""
    from lib.strat_levels import (  # noqa: PLC0415  (the head's names)
        LEVEL_CLUSTER_KEY, TARGET_RULE_ATR_MARKS, plan_target_rule,
    )
    require_local_db()
    dbs = dbs or ARM_DBS
    trades = []
    for arm in ARMS:
        engine = _arm_engine(arm, dbs)
        days = []
        for t, day, row, basis, bars in _days(engine, start, end):
            version = basis.get('rule_version')
            marks_rule = plan_target_rule(version) == TARGET_RULE_ATR_MARKS
            if marks_rule != bool(ARMS[arm][0]):
                raise RuntimeError(f"arm {arm} {t} {day}: basis version {version!r}")
            res, pick, reason = _score_day(row, basis, bars)
            rec = {'ticker': t, 'date': day, 'side': pick or '', 'reason': reason or ''}
            for side in ('calls', 'puts'):
                rec[f'{side}_trigger'] = res[side][0].trigger_price
                rec[f'{side}_stop'] = res[side][0].stop_price
            if pick:
                p, o = res[pick]
                sl = SessionLevels.from_basis(basis)
                s = sl.side(pick)
                cluster = sl.params.param(LEVEL_CLUSTER_KEY) if sl.params else None
                reach = price_cents(cluster.value * sl.atr) if cluster and cluster.ok and sl.atr else None
                level_cents = {price_cents(lv.price) for lv in sl.levels}
                sign = 1 if pick == 'calls' else -1
                past = [bool(reach) and any(0 < sign * (tg['cents'] - c) <= reach
                                            for c in level_cents)
                        and not tg.get('on_level') for tg in s.targets] if marks_rule else []
                trades.append({
                    'ticker': t, 'date': day, 'arm': arm, 'side': pick,
                    'trigger': p.trigger_price, 'stop': p.stop_price, 'fill': o.fill_price,
                    'fill_ts': str(o.fill_ts), 'atr': sl.atr, 'r': o.r, 'exit': o.exit,
                    'mfe_atr': o.mfe_atr, 'targets': json.dumps(list(p.targets)),
                    'n_targets': len(p.targets), 'legs': p.legs, 'rule_version': version,
                    'marks': json.dumps([tg.get('mark') for tg in s.targets] if marks_rule else []),
                    'on_level': json.dumps([bool(tg.get('on_level')) for tg in s.targets]
                                           if marks_rule else []),
                    'past_level': json.dumps(past),
                    'waypoints': json.dumps([{'names': w['names'], 'segment': w['segment'],
                                              'distance_atr': w['distance_atr']}
                                             for w in (s.plan_waypoints or [])])})
                rec['r'], rec['exit'] = o.r, o.exit
                rec['targets'] = json.dumps(list(p.targets))
            days.append(rec)
        if arm == 'A':
            pd.DataFrame(days).to_csv(days_out, index=False)
    frame = pd.DataFrame(trades)
    keys = {arm: frame.loc[frame['arm'] == arm, ['ticker', 'date', 'side', 'trigger', 'stop', 'fill']]
            .reset_index(drop=True) for arm in ARMS}
    for arm in ARMS:
        if not keys[arm].equals(keys['A']):
            raise RuntimeError(f"arm {arm} does not trade arm A's ticker-days with its trigger, "
                               "stop and fill")
    frame.to_csv(out, index=False)
    print(f"scored {len(frame)} trades over {len(ARMS)} arms into {out}")
    return frame


# ── the report ──────────────────────────────────────────────────────────

def parse_spike(directory: Path = SPIKE_DIR) -> dict:
    """The spike's figures, read from its two report files, verbatim."""
    import re
    side = (directory / 'report_v1_side.txt').read_text()
    follow = (directory / 'report_followup.txt').read_text()
    out: dict = {'arms': {}, 'diff': {}, 'reach': {}, 'tickers': {}}
    out['trades'] = int(re.search(r'trades (\d+)', side).group(1))
    for arm, total in re.findall(r'^(\w+)\s+total\s+([+-][\d.]+)', follow, re.M):
        out['arms'][arm] = float(total)
    line = next(ln for ln in side.splitlines() if ln.startswith('All '))
    for arm, d, lo, hi in re.findall(r'(\w+)-A\s+([+-][\d.]+) \(([+-][\d.]+), ([+-][\d.]+)\)', line):
        out['diff'][arm] = (float(d), (float(lo), float(hi)))
    for t in TICKERS:
        ln = next(x for x in side.splitlines() if x.startswith(t + ' '))
        out['tickers'][t] = {arm: float(v) for arm, v in
                             re.findall(r'\s(A|Q|Q3)\s+([+-][\d.]+)(?=\s)', ln)}
    for arm, body in re.findall(r"^arm (\w+)[^:\n]*: (\{'T1'[^}]*\})", side, re.M):
        out['reach'][arm] = {k: float(v.rstrip('%')) for k, v in eval_dict(body).items()}
    return out


def eval_dict(text: str) -> dict:
    """A dict printed by Python with string keys and values, read without eval."""
    import ast
    value = ast.literal_eval(text)
    if not isinstance(value, dict):
        raise ValueError(text)
    return value


def diff_range(frame: pd.DataFrame, arm: str, base: str = 'A', draws: int = DRAWS,
               seed: int = SEED) -> tuple:
    """(total, 5th percentile, 95th percentile) of arm minus base over the
    frame's trades, resampling whole days `draws` times with
    numpy.random.default_rng(seed)."""
    per_day = frame.pivot_table(index='date', columns='arm', values='r', aggfunc='sum').fillna(0.0)
    d = (per_day[arm] - per_day[base]).to_numpy()
    rng = np.random.default_rng(seed)
    sums = d[rng.integers(0, len(d), size=(draws, len(d)))].sum(axis=1)
    lo, hi = np.percentile(sums, [5, 95])
    return float(d.sum()), float(lo), float(hi)


def reach_share(mfe: pd.Series, marks) -> dict:
    """{mark: (k, n)}: k of the n trades with a reach value whose reach before
    the stop, in ATR, is at least the mark."""
    values = mfe.dropna().astype(float)
    return {m: (int((values >= m).sum()), int(len(values))) for m in marks}


def _blocks(dates: pd.Series) -> pd.Series:
    """The six-month block of each date: Mar to Aug, Sep to Feb."""
    d = pd.to_datetime(dates)
    start_year = np.where(d.dt.month >= 9, d.dt.year, np.where(d.dt.month >= 3, d.dt.year, d.dt.year - 1))
    half = np.where((d.dt.month >= 3) & (d.dt.month <= 8), 'Mar-Aug', 'Sep-Feb')
    return pd.Series([f"{y} {h}" for y, h in zip(start_year, half)], index=dates.index)


def report(csv: str) -> str:
    """The eleven measures of the spec's Reported list, per arm, with the
    spike's figure beside each it has one for."""
    frame = pd.read_csv(csv)
    frame['r'] = frame['r'].astype(float)
    spike = parse_spike()
    marks_all = ARMS['Q'][0]
    lines = []

    def spike_text(value) -> str:
        return 'spike: not produced' if value is None else f"spike: {value}"

    lines.append('== 1. total R, and by ticker ==')
    for arm in ARMS:
        a = frame[frame['arm'] == arm]
        by = {t: round(float(a.loc[a['ticker'] == t, 'r'].sum()), 2) for t in TICKERS}
        lines.append(f"{arm:3} total {a['r'].sum():+.2f} over {len(a)} trades {by}  "
                     + spike_text(spike['arms'].get(arm)))
    lines.append('== 2. six-month blocks ==')
    frame['block'] = _blocks(frame['date'])
    for block, g in frame.groupby('block'):
        lines.append(f"{block}: " + ', '.join(f"{arm} {g.loc[g['arm'] == arm, 'r'].sum():+.1f}"
                                               for arm in ARMS))
    lines.append('== 3. arm minus A, 90% range (whole days resampled 2,000 times, seed 7) ==')
    for arm in ARMS:
        if arm == 'A':
            continue
        total, lo, hi = diff_range(frame, arm)
        lines.append(f"{arm}-A {total:+.1f} ({lo:+.1f}, {hi:+.1f})  "
                     + spike_text(spike['diff'].get(arm)))
        for t in TICKERS:
            sub = frame[frame['ticker'] == t]
            if sub.empty:
                lines.append(f"   {t} {arm}-A: no trades")
                continue
            total, lo, hi = diff_range(sub, arm)
            lines.append(f"   {t} {arm}-A {total:+.1f} ({lo:+.1f}, {hi:+.1f})  "
                         + spike_text(spike['tickers'].get(t)))
    lines.append('== 4. share of entered trades whose leg sold at Tk before the stop ==')
    for arm in ARMS:
        a = frame[frame['arm'] == arm]
        legs = a['exit'].fillna('').str.split(',')
        shares = {f"T{k}": round(100 * float(legs.map(lambda e, k=k: f"t{k}" in e).mean()), 1)
                  for k in range(1, ARMS[arm][1] + 1)}
        lines.append(f"{arm}: {shares}  " + spike_text(spike['reach'].get(arm)))
    lines.append('== 5. reach of each ATR mark before the stop (mfe_atr) ==')
    for arm in ARMS:
        share = reach_share(frame.loc[frame['arm'] == arm, 'mfe_atr'], marks_all)
        lines.append(f"{arm}: " + ', '.join(f"{m}: {k} of {n}" for m, (k, n) in share.items())
                     + "  spike: not produced")
    lines.append('== 6. reach of waypoints, by level name and by segment ==')
    for arm in ('Q', 'Q3'):
        names: dict = {}
        segments: dict = {}
        for rec in frame[frame['arm'] == arm].to_dict('records'):
            for w in json.loads(rec['waypoints'] or '[]'):
                hit = rec['mfe_atr'] == rec['mfe_atr'] and rec['mfe_atr'] >= w['distance_atr']
                for n in w['names']:
                    k, total = names.get(n, (0, 0))
                    names[n] = (k + hit, total + 1)
                k, total = segments.get(w['segment'], (0, 0))
                segments[w['segment']] = (k + hit, total + 1)
        lines.append(f"{arm} by name: {names}  spike: not produced")
        lines.append(f"{arm} by segment: {segments}")
    for title, column in (('7. a target on a level against the rest', 'on_level'),
                          ('8. a target just past a level (level_cluster_atr) against the rest',
                           'past_level')):
        lines.append(f"== {title}, by mark ==")
        for arm in ('Q', 'Q3'):
            stats: dict = {}
            for rec in frame[frame['arm'] == arm].to_dict('records'):
                flags = json.loads(rec[column] or '[]')
                marks = json.loads(rec['marks'] or '[]')
                for mark, flag in zip(marks, flags):
                    hit = rec['mfe_atr'] == rec['mfe_atr'] and rec['mfe_atr'] >= mark
                    key = (mark, bool(flag))
                    k, n = stats.get(key, (0, 0))
                    stats[key] = (k + hit, n + 1)
            lines.append(f"{arm}: {dict(sorted(stats.items()))}  spike: not produced")
    lines.append('== 9. win rate, average win and loss, stopped with no sale ==')
    for arm in ARMS:
        a = frame[frame['arm'] == arm]
        wins, losses = a.loc[a['r'] > 0, 'r'], a.loc[a['r'] < 0, 'r']
        stopped = a['exit'].fillna('').map(lambda e: bool(e) and set(e.split(',')) == {'stop'})
        lines.append(f"{arm}: win rate {100 * (a['r'] > 0).mean():.1f}%, average win "
                     f"{wins.mean():+.3f}, average loss {losses.mean():+.3f}, stopped with no "
                     f"sale {100 * stopped.mean():.1f}%  spike (average win, loss): not produced")
    lines.append('== 10. entered sides whose T1 is under 1.5R and under 1.0R ==')
    for arm in ARMS:
        a = frame[frame['arm'] == arm]
        t1 = a['targets'].map(lambda s: (json.loads(s) or [None])[0])
        risk = (a['fill'] - a['stop']).abs()
        r1 = ((t1.astype(float) - a['fill']).abs() / risk).dropna()
        lines.append(f"{arm}: under 1.5R {100 * (r1 < 1.5).mean():.1f}%, under 1.0R "
                     f"{100 * (r1 < 1.0).mean():.1f}% of {len(r1)}")
    lines.append('== 11. fewer targets than legs; exits that differ from A ==')
    base_exit = frame[frame['arm'] == 'A'].set_index(['ticker', 'date'])['exit']
    for arm in ARMS:
        a = frame[frame['arm'] == arm]
        fewer = int((a['n_targets'] < a['legs']).sum())
        differs = int((a.set_index(['ticker', 'date'])['exit'] != base_exit).sum())
        lines.append(f"{arm}: fewer targets than legs {fewer}, exits differ from A {differs}")
    text = '\n'.join(lines)
    print(text)
    return text


# ── compare ─────────────────────────────────────────────────────────────

def _cents(value) -> Optional[int]:
    if value is None or value != value or value == '':
        return None
    return price_cents(float(value))


def trigger_changed(base_days: pd.DataFrame, head_days: pd.DataFrame) -> dict:
    """r2's measure, trigger-changed ticker-days: a ticker-day whose calls or
    puts trigger differs to the cent between the two runs, or is in one run
    only (a trigger or the whole ticker-day). Arm A's R and trade count in
    each run on those days and on the rest, and every day of the rest whose R
    differs between the runs, with both runs' side, stop, targets, exit and R."""
    base = {(r['ticker'], str(r['date'])): r for r in base_days.to_dict('records')}
    head = {(r['ticker'], str(r['date'])): r for r in head_days.to_dict('records')}
    changed = set()
    for key in set(base) | set(head):
        if key not in base or key not in head:
            changed.add(key)
            continue
        if any(_cents(base[key][f'{s}_trigger']) != _cents(head[key][f'{s}_trigger'])
               for s in ('calls', 'puts')):
            changed.add(key)

    def part(days: dict, keys) -> tuple:
        traded = [days[k] for k in keys if k in days and str(days[k].get('side') or '') not in ('', 'nan')]
        return round(sum(float(r['r']) for r in traded if r['r'] == r['r']), 4), len(traded)

    rest = (set(base) & set(head)) - changed
    differs = []
    for key in sorted(rest):
        rb, rh = base[key]['r'], head[key]['r']
        same = (rb != rb and rh != rh) or (rb == rh)
        if not same:
            differs.append({'ticker': key[0], 'date': key[1],
                            **{f'base_{c}': base[key][c] for c in ('side', 'calls_stop', 'puts_stop', 'targets', 'exit', 'r')},
                            **{f'head_{c}': head[key][c] for c in ('side', 'calls_stop', 'puts_stop', 'targets', 'exit', 'r')}})
    return {'count': len(changed), 'changed': sorted(changed),
            'base': {'changed': part(base, changed), 'rest': part(base, rest)},
            'head': {'changed': part(head, changed), 'rest': part(head, rest)},
            'rest_r_differs': differs}


def compare(base_path: str, head_path: str) -> dict:
    out = trigger_changed(pd.read_csv(base_path), pd.read_csv(head_path))
    print(f"trigger-changed ticker-days: {out['count']}")
    for run in ('base', 'head'):
        print(f"  {run}: changed R {out[run]['changed'][0]:+.2f} over {out[run]['changed'][1]} "
              f"trades; rest R {out[run]['rest'][0]:+.2f} over {out[run]['rest'][1]} trades")
    print(f"rest ticker-days whose R differs: {len(out['rest_r_differs'])}")
    for rec in out['rest_r_differs']:
        print('  ' + json.dumps(rec, default=str))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('load')
    p.add_argument('export_dir')
    p.add_argument('bars_dir')
    p = sub.add_parser('placeholder')
    p.add_argument('start')
    p.add_argument('end')
    p.add_argument('--check', action='store_true')
    p = sub.add_parser('replay')
    p.add_argument('arm', choices=sorted(ARMS))
    p.add_argument('start')
    p.add_argument('end')
    p.add_argument('--part', type=int, default=0)
    p.add_argument('--parts', type=int, default=1)
    p = sub.add_parser('score')
    p.add_argument('start')
    p.add_argument('end')
    p.add_argument('--out', required=True)
    p.add_argument('--days-out', required=True)
    p.add_argument('--db', action='append', default=[], help='ARM=DATABASE')
    p = sub.add_parser('report')
    p.add_argument('csv')
    p = sub.add_parser('baseline')
    p.add_argument('start')
    p.add_argument('end')
    p.add_argument('--days-out', required=True)
    p = sub.add_parser('compare')
    p.add_argument('base_days')
    p.add_argument('head_days')
    a = parser.parse_args(argv)
    if a.cmd == 'load':
        load(a.export_dir, a.bars_dir)
    elif a.cmd == 'placeholder':
        left = placeholder(a.start, a.end, check=a.check)
        return 1 if a.check and left else 0
    elif a.cmd == 'replay':
        return 1 if replay(a.arm, a.start, a.end, a.part, a.parts) else 0
    elif a.cmd == 'score':
        dbs = dict(ARM_DBS, **dict(x.split('=', 1) for x in a.db))
        score(a.start, a.end, a.out, a.days_out, dbs)
    elif a.cmd == 'report':
        require_local_db()
        report(a.csv)
    elif a.cmd == 'baseline':
        baseline(a.start, a.end, a.days_out)
    elif a.cmd == 'compare':
        require_local_db()
        compare(a.base_days, a.head_days)
    return 0


if __name__ == '__main__':
    sys.exit(main())
