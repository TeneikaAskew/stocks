"""Run the production voter (lib/trading_analysis.py, unchanged) on the full extended-hours 1-min history.
  python3 -I code/voter_run.py SPY     -> work/SPY_voter_signals.parquet (the same rows historical_signals would hold)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
sys.path.insert(0, REPO)
from lib.trading_analysis import MarketAnalyzer

T = sys.argv[1]; t0 = time.time()
bars, nfiles = load_bars(T)
ma = MarketAnalyzer()
e = quiet(ma.add_technical_indicators, bars.copy())
sig = quiet(ma.generate_technical_signals, e)
keep = ['entry_time', 'trade_type', 'entry_price', 'duration_minutes', 'return_pct', 'best_return', 'signal_strength',
        'exit_time', 'exit_price', 'entry_rsi', 'exit_rsi'] + [c for c in sig.columns if c.startswith('return_') and c.endswith('min')]
sig = sig[[c for c in keep if c in sig.columns]]
sig.to_parquet(f'{WORK}/{T}_voter_signals.parquet', index=False)
print(T, 'files', nfiles, 'bars', len(bars), 'signals', len(sig), 'secs', round(time.time() - t0), flush=True)
