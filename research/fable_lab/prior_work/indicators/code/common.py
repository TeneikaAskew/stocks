"""Shared loaders for the indicators lane. Research only; reads production code from a clean worktree."""
import os, sys, io, contextlib
import numpy as np, pandas as pd

REPO = os.environ.get('STOCKS_WT', '/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/wt-indicators')
BARS_DIR = '/mnt/project-files/stocks-scorecard/inputs/bars_raw'
DAILY_DIR = '/mnt/project-files/strat-verify/ftfc-replay/raw'
ROOT = '/mnt/project-files/stocks-scorecard/research/fable_lab/indicators'
WORK = f'{ROOT}/work'
TICKERS = ['SPY', 'QQQ', 'IWM']
PRIMARY = ('2026-05-01', '2026-11-10')
HOLDOUT = ('2025-03-03', '2026-04-30')


def window_of(dates):
    d = pd.to_datetime(pd.Series(dates)).dt.strftime('%Y-%m-%d').values
    return np.where((d >= PRIMARY[0]) & (d <= PRIMARY[1]), 'primary',
                    np.where((d >= HOLDOUT[0]) & (d <= HOLDOUT[1]), 'holdout', 'other'))


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def load_bars(ticker):
    fs = sorted(f for f in os.listdir(BARS_DIR) if f.startswith(f'{ticker}_1min_') and f.endswith('.csv'))
    df = pd.concat([pd.read_csv(os.path.join(BARS_DIR, f)) for f in fs], ignore_index=True)
    df['Time'] = pd.to_datetime(df['timestamp'])
    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Last', 'volume': 'Volume'})
    df = df[['Time', 'Open', 'High', 'Low', 'Last', 'Volume']]
    return df.drop_duplicates('Time').sort_values('Time').reset_index(drop=True), len(fs)


def wilder(x, n):
    return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    d = close.diff()
    up = wilder(d.clip(lower=0), n); dn = wilder((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def macd_hist(close):
    line = ema(close, 12) - ema(close, 26)
    return line - line.ewm(span=9, adjust=False, min_periods=9).mean()


def daily_bars(ticker, bars):
    """Daily OHLC: AV daily file before the 1-min history starts, regular-hours 1-min aggregates after."""
    D0 = pd.read_csv(f'{DAILY_DIR}/{ticker}_daily_adjusted.csv', parse_dates=['timestamp']).sort_values('timestamp')
    D0 = D0.rename(columns={'timestamp': 'Date', 'open': 'O', 'high': 'H', 'low': 'L', 'close': 'C'})
    mod = bars['Time'].dt.hour * 60 + bars['Time'].dt.minute
    r = bars[(mod >= 570) & (mod < 960)]
    g = r.groupby(r['Time'].dt.normalize())
    D1 = pd.DataFrame({'O': g['Open'].first(), 'H': g['High'].max(), 'L': g['Low'].min(), 'C': g['Last'].last(), 'n': g.size()})
    D1 = D1[D1['n'] >= 200].drop(columns='n')          # drop non-sessions (holiday prints)
    D1.index.name = 'Date'
    D0 = D0[D0['Date'] < D1.index.min()].set_index('Date')[['O', 'H', 'L', 'C']]
    return pd.concat([D0, D1]).sort_index()
