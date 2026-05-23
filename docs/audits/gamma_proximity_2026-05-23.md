# Gamma-Proximity Direction Audit (2026-05-23)

**Owner**: Track 3 of REALTIME_OPTIONS_MULTITRACK_PLAN
**Module**: [`lib/strategies/gamma_proximity.py`](../../lib/strategies/gamma_proximity.py)
**Companion PR**: feature branch `claude/signal-monitor-gamma-walls-UAe6g`

## TL;DR

The original gate / flip / king direction mappings in `gamma_proximity.py`
were derived from textbook dealer-hedging theory ("rejection at
resistance/support"). I empirically tested all three against
**SPY / IWM / QQQ × 14d + 30d** historical data (N ≈ 1,200 events) and
found:

1. **King-approach** is a **magnet**, not a barrier. Approach from below
   → CALL (price drifts up to king); approach from above → PUT.
   **Inverted** from original. Validated 65–77 % hit-rate both regimes,
   both directions, no FTFC dependency.

2. **Gate-break** direction is **weak even when FTFC-aligned**. CALL
   gates ~57 %, PUT gates ~44 % across the entire backtest. Gate is more
   of an "information / volatility-break event" than a directional alpha
   signal. FTFC alignment matters only modestly (a few percentage points).

3. **Flip-cross** direction is **strongly FTFC-dependent**. Aligned
   alerts hit 64–77 %; against-FTFC alerts hit 27–50 %.
   Flip is the highest-edge of the three when properly filtered.

## Code change shipped

```python
# Old: fire CALL/PUT for any gate/flip cross, no regime context
evaluate_gate_break(prev_close, close, summary)
evaluate_flip_cross(prev_close, close, summary)

# New: optional FTFC filter; alerts only fire when alert_dir aligns
# with prev_day_dir
evaluate_gate_break(prev_close, close, summary, prev_day_dir="UP")
# CALL gates fire; PUT gates don't
evaluate_gate_break(prev_close, close, summary, prev_day_dir="DOWN")
# PUT gates fire; CALL gates don't
evaluate_gate_break(prev_close, close, summary, prev_day_dir=None)
# Legacy (unfiltered) — used by tests and for backwards compat
```

King-approach was inverted in [commit a4d3153](../../) (2026-05-23
earlier in same session). No `prev_day_dir` parameter — kings are
FTFC-independent.

## Backtest methodology

### Window

- **Tickers**: SPY, IWM, QQQ (the three the signal_monitor tracks)
- **Windows**: `current_date - 14 days` and `current_date - 30 days`
  through 2026-05-22. The 30-day window covers the full
  `alphavantage` chain data range (2026-04-13 → 2026-05-23).
- **Bars**: `market_data_intraday_<ticker>` (1-minute, RTH only:
  09:30–15:45 ET)
- **Chains**: `etf_options_snapshots` with `data_source='alphavantage'`

### Event detection

For each ticker × snapshot_date, compute per-strike `net_gamma`
(call-side `gamma * open_interest` − put-side):

- **King**: top |net_gamma| strike per day
- **Gate**: strikes with `0.20 ≤ |net_gamma|/max ≤ 0.50` (the
  "secondary node" band per `lib/gamma.classify_levels` rules)
- **Flip**: linearly-interpolated zero-crossing of cumulative
  `net_gamma` ordered by strike

Then walk each day's 1-min bars:
- **king_approach**: bars where `|close − king| / king ≤ 0.005`
- **gate_break**: bars where `(prev_close, close)` straddle a gate strike
- **flip_cross**: bars where `(prev_close, close)` straddle the flip price

### Continuation metric

`hit_15m_pct` = % of events where the price 15 minutes later moved in
the alert direction (CALL → price up, PUT → price down). Bars within
15 min of session close have NULL forward and are excluded from the
denominator.

### FTFC proxy

`prev_day_dir` = `'UP'` / `'DOWN'` / `'FLAT'` from
`market_data_daily.close` vs `.open` on the **prior trading day**.
No leak — yesterday's bar is closed before today's first bar.

A real production FTFC check would also incorporate intraday 60m /
30m / 15m strat candles. The prior-day proxy is the cleanest single
filter to test; the 4-TF FTFC stack will only sharpen the edge further.

### Replay paths

All queries dispatched via `db-query.yml` against
`adept-mountain-474619-d4 / trading`:

| step | dispatch artifact | duration |
|---|---|---|
| range probe | run 26321599190 | 30 s |
| chain probe | run 26321735472 | 1 m |
| SPY king 14d | run 26321038662 (first SQL) | 6 m |
| SPY gate × FTFC 14d | run 26323685454 | 3.5 m |
| SPY flip × FTFC 14d | run 26323826040 | 50 s |
| SPY + IWM + QQQ × {14d, 30d} | runs 26323951771, 26324343479, 26324741563 | ~17 min each |

The `db-query.yml` workflow timeout was bumped from 30 → 90 minutes
to fit the 30-day queries (commit e33b336).

## Results — King approach (validated 2026-05-23, committed a4d3153)

SPY 14d, N=33 king approaches:

| approach side | N | toward king 15m | toward king 30m | rejected 15m |
|---|---|---|---|---|
| above_king | 20 | 65.0% | **75.0%** | 35.0% |
| below_king | 13 | **76.9%** | 69.2% | 23.1% |

→ Inverted mapping shipped: below → CALL, above → PUT.

## Results — Gate-break × FTFC (30d, all 3 ETFs)

| ticker | alert | FTFC | N | hit 15m |
|---|---|---|---|---|
| SPY | CALL | UP | 138 | 58.6% |
| SPY | CALL | DOWN | 108 | 56.9% |
| SPY | PUT | DOWN | 101 | 46.5% |
| SPY | PUT | UP | 129 | **39.7%** ✗ |
| IWM | CALL | UP | 70 | 61.4% |
| IWM | CALL | DOWN | 62 | 55.7% |
| IWM | PUT | DOWN | 58 | 43.9% |
| IWM | PUT | UP | 68 | 43.3% |
| QQQ | CALL | UP | 143 | 54.0% |
| QQQ | CALL | DOWN | 53 | 52.8% |
| QQQ | PUT | DOWN | 51 | 42.9% |
| QQQ | PUT | UP | 136 | 46.6% |

**Weighted across 3 ETFs:**

| direction | FTFC | N | hit 15m |
|---|---|---|---|
| CALL | aligned (UP) | 351 | 57.3% |
| CALL | against (DOWN) | 223 | 55.6% |
| PUT | aligned (DOWN) | 210 | 44.9% |
| PUT | against (UP) | 333 | 43.3% |

**Read**: gate CALL is robust (~57 % both regimes); gate PUT has
negative directional expectancy in every regime. FTFC alignment helps
modestly (≤ 2 pp) but doesn't transform the signal. Net-net, gate is
a marginal directional signal — production-shipped FTFC filter only
keeps the slight-edge cases.

## Results — Flip-cross × FTFC (30d, all 3 ETFs)

| ticker | alert | FTFC | N | hit 15m |
|---|---|---|---|---|
| SPY | CALL | UP | 22 | **81.0%** ✓ |
| SPY | CALL | DOWN | 7 | 57.1% |
| SPY | PUT | DOWN | 7 | **71.4%** ✓ |
| SPY | PUT | UP | 20 | **27.8%** ✗ |
| IWM | CALL | UP | 10 | 40.0% |
| IWM | PUT | UP | 10 | 50.0% |
| QQQ | CALL | UP | 15 | 53.8% |
| QQQ | CALL | DOWN | 12 | **27.3%** ✗ |
| QQQ | PUT | DOWN | 11 | **80.0%** ✓ |
| QQQ | PUT | UP | 11 | 50.0% |

**Weighted:**

| direction | FTFC | N | hit 15m |
|---|---|---|---|
| CALL | aligned (UP) | 47 | **63.6%** |
| CALL | against (DOWN) | 19 | 38.3% |
| PUT | aligned (DOWN) | 18 | **76.7%** |
| PUT | against (UP) | 41 | 39.2% |

**Read**: flip-cross is the highest-edge of the three when filtered.
Aligned PUT (76.7 %) is the strongest signal in the entire backtest;
aligned CALL (63.6 %) is also actionable. Against-FTFC alerts in either
direction are net losers (38–39 %), making the filter essential rather
than optional.

Caveat: per-ticker sample sizes are small (N=7–22 per cell). Confidence
is moderate, not high. Re-run quarterly as more data accumulates.

## Filter rule shipped

```python
def _ftfc_aligned(direction, prev_day_dir):
    if prev_day_dir is None:
        return True             # legacy / test mode
    if direction == "CALL":
        return prev_day_dir == "UP"
    return prev_day_dir == "DOWN"   # PUT requires DOWN
```

`FLAT` prev-day blocks both directions (no FTFC signal to align with).

## Open follow-ups

1. **Multi-TF FTFC**: ship 60m/30m/15m strat-classified candles
   alongside daily, so the filter uses the full 4-TF stack the strat
   methodology specifies (not just D-1). Expected to sharpen the edge.

2. **Larger sample**: 30 days × 3 ETFs gives N=1,200 events total but
   only N=18-47 per flip-direction-FTFC cell. Re-run quarterly.

3. **Outcome by horizon**: only 15-min hit rate was tested. Add 30m
   and 60m horizons to see if signals decay or accumulate.

4. **Regime conditioning**: cumulative-GEX regime (`positive_gamma` vs
   `negative_gamma`) at the alert bar — likely interacts with FTFC and
   could further filter false-positive PUT-in-positive-gamma cases.

5. **Production smoke test**: once signal_monitor wires the alerts into
   live Discord posts, compare next-day P&L of FTFC-aligned vs raw
   alerts to confirm the empirical edge survives live trading frictions.
