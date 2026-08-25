# BSVP + Scalping-Lanes 10-Year Validation — Design

**Date:** 2026-07-13
**Branch:** `feature/bsvp-validation`
**Status:** Approved (design presented and approved in session; scalping scope
added at user request)

**Data window (Phase 0 result, 2026-07-13):** `market_data_intraday` has
continuous 1-min coverage 2015-01-02 → 2026-07-13 for IWM (1.96M rows /
3,231 days), QQQ (2.23M / 3,082), SPY (2.39M / 3,285). Timestamps are UTC
(TIMESTAMPTZ) and include extended hours — convert to America/New_York and
RTH-filter at load.

## Problem

The `tradingview-pine-scripts/iwm-bsvp` indicator (Vadim Gimelfarb power-balance
volume pressure, VPO oscillator, divergence/exhaustion/entry-quality layer) was
built from a **small population of early historical alerts** produced by
`trade_analysis.py` / `.ipynb` when the project started. Its thresholds and the
win rates quoted in `iwm-bsvp.md` (55–70%) have never been validated against the
full intraday history. The user finds it useful for context but not as
predictive as expected.

## Goal

1. Validate every BSVP signal component against the full available 1-minute
   history (target ~10y) for IWM, SPY, QQQ on 5m/15m/30m bars.
2. Determine whether the original thresholds still hold (threshold sensitivity).
3. Produce a concrete keep / retune / drop verdict per component and a list of
   Pine script logic + threshold changes, including outright code bugs.

## Non-goals

- Wiring BSVP into `signal_monitor` as a live strategy (natural follow-up PR if
  components survive validation).
- Full `lib/backtest.py` BacktestEngine integration (engine assumes
  `lib/signals.evaluate_signal`; premature before component validation).
- TradingView webhook integration.

## Architecture

Follows the existing `scripts/analysis/` phase-script pattern (same one that
produced the UPGRADE-PLAN.md win-rate-lift numbers).

### Phase 0 — Data inventory
- One `./scripts/db_query_cr.sh` dispatch: per-ticker `min(date)`, `max(date)`,
  rows per year in `market_data_intraday`.
- Report states the *actual* validation window; no assumption of 10y.

### Phase 1 — Port BSVP math into `lib/indicators.py`
New functions (extend the existing module — one source of truth for math):

- `calculate_volume_pressure(df, fast_ma=3, lookback=27)` → columns
  `bp`, `sp`, `bpv`, `spv`, `bpv_avg`, `spv_avg` (raw mode) and the
  normalized variants (`bpn`, `spn`, `nbf`, `nsf`), matching the Pine
  double-smoothing exactly (`ema(ema(x,3),3)` for raw BPV/SPV,
  `ema(wma(x,3),3)` for TPV and normalized).
- `calculate_vpo(df, ...)` → `vpo1`, `vpo2`, `vph`.
- `calculate_bsvp_signals(df, ...)` → boolean columns for every signal family:
  `bsvp_buy`, `bsvp_sell`, `bsvp_strong_buy`, `bsvp_strong_sell`,
  `bsvp_bull_cross`, `bsvp_bear_cross`, `bsvp_bullish_div`,
  `bsvp_bearish_div`, `bsvp_bull_exhaustion`, `bsvp_sell_exhaustion`,
  `bsvp_bull_accel`, `bsvp_sell_accel`, `bsvp_prime_buy`, `bsvp_prime_sell`,
  plus `bsvp_trend_strength` (0–100) and `bsvp_entry_quality` (0–100).

Parity verification:
- Unit tests in `tests/` with hand-computed bars for BP/SP branch logic.
- Spot-check against known TradingView values from the user's 2026-07-13
  charts (QQQ 30m: vpo2≈34.7, vph≈−10.4, ratio 77/23; IWM 30m: vph≈−10.4,
  ratio 80/20) within tolerance (warm-up differences expected).

Pine parity notes: `ta.ema` → `ewm(span=n, adjust=False)`; `ta.wma` →
linear-weighted rolling; `ta.roc(x,3)` → pct change ×100; RTH filter
9:30–16:00 America/New_York (shared_utils.filter_rth already does this).

### Phase 2 — Component validation script
`scripts/analysis/bsvp_validation.py`, loading via
`scripts/analysis/shared_utils.load_ticker_1m` + `resample_to_timeframe`.

For each (ticker × timeframe × signal family):
- **Event study:** forward return at +15m/+30m/+60m/EOD after each signal
  fire, direction-adjusted (PUT signals flip sign). Baseline: all-bars
  forward returns on the same timeframe (edge = signal minus baseline).
- **Trade-rule simulation:** the readme's own rules — entry at signal close,
  stop at recent swing low/high (lookback 10 bars), target 2:1 R:R,
  time-stop at EOD. Win rate, avg R, profit factor per component.
- **Splits:** full history vs recent 3y (`split_by_period`), and per-year
  table for edge-decay visibility.
- Signal counts reported per cell — cells under 100 events flagged
  low-confidence, mirroring the UPGRADE-PLAN's 1,000+ trade bar for
  high-confidence claims.

### Phase 3 — Threshold sensitivity
Sweep the small-sample-era magic numbers on the best-performing components:
- acceleration cutoffs (+20 / −15), divergence lookback (14),
  conv/div lookback (27), fastMA (3), entry-quality bucket edges,
  trend-strength bucket edges.
- Report edge as a function of threshold; flag where the current value is
  off-peak.

### Phase 4 — Report + Pine recommendations
`reports/bsvp_validation_YYYY-MM-DD.md`:
- Data window actually used.
- Per-component verdict table (keep / retune / drop) with event counts,
  win rates, edge vs baseline, full vs recent-3y.
- Timeframe verdict (readme says 5m; user trades 30m).
- Threshold change list for the Pine script.
- **Pine code-review findings** (independent of backtest), suspects already
  identified while reading `iwm-bsvp`:
  1. `hiddenBullDiv`/`hiddenBearDiv` (lines 135–136) look inverted —
     hidden bullish divergence flagged at price *highs*.
  2. `maxRange`/`minRange` in the signal-label block grow monotonically
     forever (never reset), so label positions drift off-pane over time.
  3. Divergence detection tests "pressure declining over 2 bars at a
     price extreme," not true pivot-to-pivot divergence.
  4. Info-table Buy/Sell ratio uses raw `BPV` even when `norm=true`.
  5. `divergenceLookback/2` integer division in hidden-div lookback.

## Scalping-lanes addendum (added at user request)

`tradingview-pine-scripts/iwm-scalping` renders 24 boolean lanes with **no
composite signal** — the readme's entry rule ("≥6-7 green dots + RVOL high +
time window") has never been measured, and the per-lane success rates in its
tooltips (60.6% RSI>50, 62.6% RSI<50, etc.) date from the same small early
sample as BSVP.

Validation (same framework, same script, separate report section):

- **Composite lane-count signal:** CALL score = count of the 11 bullish lanes
  true; PUT score = count of the 11 bearish lanes. Evaluate entry rule at
  thresholds 5..9, with and without the RVOL≥1.5 + time-window gates.
- **Per-lane lift:** forward-return edge per individual lane (re-validates the
  tooltip numbers on 11.5y).
- **Lane parity notes:** match the Pine math exactly —
  `stochRsi = ta.stoch(rsi, rsi, rsi, 14)` is *unsmoothed* raw %K (not the
  platform's smoothed StochRSI); `rvol = volume / sma(volume, 50)` includes the
  current bar; 1m rejection and 5m breakout sub-signals computed from the 1m
  base data.
- **Known issue to quantify:** `atrMin = 0.15` is an absolute-dollar gate —
  non-stationary across a decade of price levels (IWM ~$115 in 2015 vs ~$293
  now). Validate ATR% and ATR-vs-SMA(ATR) alternatives.

## Data & capacity (Rule 0 back-of-envelope)

- Volume: ~390 RTH 1-min bars/day × ~252 × ~10y × 3 tickers ≈ **~3M rows/ticker,
  ~9M total** (~60 B/row → ~600 MB in memory worst case; processed per-ticker,
  resampled to 5m+ before the heavy loops → bounded).
- Velocity: data pulled **once per ticker** from Cloud SQL via the existing
  `DataLoader` (Priority 0) and cached to `data/{ticker}/intraday/*.parquet`
  (DataLoader's existing Priority 1 fallback path) so re-runs are local and
  free. No per-row queries anywhere.
- Wall-clock: local vectorized pandas; indicator computation is
  O(rows) rolling ops. Minutes, not hours, per ticker/timeframe.
- Cost: 1–3 Cloud SQL reads per ticker (bounded date-range SELECTs). No new
  scheduled jobs, no Cloud Run changes.

## Testing

- Unit tests for BP/SP branch logic (the 9-branch Gimelfarb conditional) with
  hand-computed OHLC cases.
- Parity spot-check vs TradingView screenshot values (tolerance-based).
- Validation script asserts I/O shape: N input rows → exactly one indicator
  DataFrame per (ticker, timeframe); no silent empty-frame fallbacks (Rule 3.7:
  missing data raises, doesn't return empty).

## Deliverables

1. `lib/indicators.py` BSVP functions + tests.
2. `scripts/analysis/bsvp_validation.py`.
3. `reports/bsvp_validation_<date>.md` — the validation report.
4. Recommended Pine changes list (in the report; actual `iwm-bsvp-v3` edits are
   a follow-up once the user reviews the findings).
