"""replay_day.py with two changes for the ATR basis experiment:
1. the params file's atr_basis (top-level key) becomes the level_param_policy
   atr_basis row in force (a policy row dated 2015-01-03 beside the seeded
   2015-01-02 atr_14 row), as a basis switch would do in production;
2. the session's premarket snapshot is filtered the way production's
   fetch_premarket_refresh does it: lib.strat_levels.premarket_filter_inputs
   on the session's LevelParams and the prior session's ATR14 and ATR5, so
   the print filter runs in the policy's basis (the fixture default always
   uses ATR14).
Everything else is /mnt/project-files/stocks-scorecard/tools/replay_day.py,
run unchanged. Usage: as replay_day.py, the params json is required."""
import sys, json, runpy
from datetime import date
from pathlib import Path

params_json = next(Path(a) for a in sys.argv[6:] if a.endswith('.json'))
BASIS = json.loads(params_json.read_text()).get('atr_basis', 'atr_14')
import tests.lib.level_params_fixtures as lpf
import tests.lib.strat_2026_11_06 as fx
_cal = lpf.calibrated_db
def calibrated_db(path=lpf.CALIBRATED_2026_11_06, conn=None):
    db = _cal(path, conn)
    if BASIS != 'atr_14':
        db.set_policy('atr_basis', effective_from=date(2015, 1, 3), extra=json.dumps({'column': BASIS}))
    return db
lpf.calibrated_db = calibrated_db

def premarket_context(ticker, *, atr14='prior', raw=False, params=None):
    from lib.indicators import calculate_atr, calculate_premarket_context
    from lib.strat_levels import premarket_filter_inputs
    bars = fx.premarket_bars(ticker)
    d = fx.daily(ticker)
    lp = params if params is not None else lpf.fixture_params(ticker, fx.SESSION)
    atrs = {'atr_14': float(calculate_atr(d['High'], d['Low'], d['Close'], 14).iloc[-1]),
            'atr_5': float(calculate_atr(d['High'], d['Low'], d['Close'], 5).iloc[-1])}
    f = premarket_filter_inputs(lp, atrs)
    return calculate_premarket_context(
        times=bars['timestamp'], open_=bars['open'], high=bars['high'], low=bars['low'],
        close=bars['close'], volume=bars['volume'], prev_close=float(d['Close'].iloc[-1]),
        atr=None if raw else f['atr'], prev_open=float(d['Open'].iloc[-1]),
        stale_print_atr=None if raw else f['stale_print_atr'], spike_atr=None if raw else f['spike_atr'])
fx.premarket_context = premarket_context

sys.argv = ['/mnt/project-files/stocks-scorecard/tools/replay_day.py'] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
