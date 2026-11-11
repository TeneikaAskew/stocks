"""PROPOSED replacement for the outcome block in lib/trading_analysis.py (lines 940 to 990) and for the API's pct_profitable.
Research copy only: nothing in the repo was changed.

What it fixes, one by one (each can be switched on alone so the effect of every fix is visible):
  rth_only        only signals whose bar is inside 09:30 to 15:34 ET count, and the outcome never leaves that session
  next_bar_entry  enter at the OPEN of the bar after the signal bar (the signal is only known when its bar has closed)
  real exit       'time'    : sell at the open 20 minutes after entry (decided in advance, no peeking)
                  'bracket' : target and stop both 0.15 x the ticker's own daily ATR14 (prior day), whichever is touched first
                              (stop wins a tie inside one bar), else the 20-minute time exit
  cost            1 cent per share round trip
No value from the exit bar (exit_rsi, exit_vwap, exit_obv) is returned, so nothing from the future can reach the feature ranking.
"""
import numpy as np

RTH_OPEN, LAST_SIGNAL_MIN, HOLD = 570, 934, 20      # 09:30 ; last signal bar 15:34 -> entry 15:35, exit by 15:55
BRACKET_ATR = 0.15
COST = 0.01


def realized_outcomes(mod, day_id, O, H, L, C, atr_d, sig_idx, direction, exit_rule='time',
                      rth_only=True, next_bar_entry=True, hold=HOLD, bracket_atr=BRACKET_ATR, cost=COST):
    """mod: minute of day per bar; day_id: integer session id per bar; O/H/L/C: bar arrays (any hours);
    atr_d: prior-day daily ATR14 per bar; sig_idx: row numbers of the signal bars; direction: +1 call, -1 put.
    Returns (ok, ret_pct, r_mult): ok = signal is scoreable; ret_pct = net % return; r_mult = net result in units of the bracket."""
    sig_idx = np.asarray(sig_idx); direction = np.asarray(direction, float)
    n = len(C)
    ent = sig_idx + (1 if next_bar_entry else 0)
    ext = ent + hold
    ok = ext < n
    e = np.where(ok, ent, 0); x = np.where(ok, ext, 0)
    if rth_only:
        ok &= (mod[sig_idx] >= RTH_OPEN) & (mod[sig_idx] <= LAST_SIGNAL_MIN) & (day_id[x] == day_id[sig_idx]) & (mod[x] <= 955)
    px_in = O[e] if next_bar_entry else C[sig_idx]
    px_out = O[x] if next_bar_entry else C[x]
    pnl = (px_out - px_in) * direction
    if exit_rule == 'bracket':
        dist = bracket_atr * atr_d[sig_idx]
        done = np.zeros(len(sig_idx), bool)
        for j in range(hold):                       # walk forward one bar at a time; stop is checked before target
            b = np.minimum(e + j, n - 1)
            adverse = np.where(direction > 0, px_in - L[b], H[b] - px_in)
            favor = np.where(direction > 0, H[b] - px_in, px_in - L[b])
            stop = (~done) & (adverse >= dist); pnl = np.where(stop, -dist, pnl); done |= stop
            tgt = (~done) & (favor >= dist); pnl = np.where(tgt, dist, pnl); done |= tgt
        r = (pnl - cost) / dist
    else:
        r = np.full(len(sig_idx), np.nan)
    ret = (pnl - cost) / px_in * 100
    return ok, ret, r


# The API side (platform/api/routers/signals.py line 565) would then read the stored realized column, for example:
#   SUM(CASE WHEN realized_return_pct > 0 THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(realized_return_pct), 0) AS pct_profitable,
#   SUM(CASE WHEN return_pct > 0 THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0)                        AS pct_moved_in_favor   -- the old number, renamed
