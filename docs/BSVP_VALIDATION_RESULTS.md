# BSVP + Scalping-Lanes Validation — 11.5 Years of Intraday Data

**Date:** 2026-07-13 · **Branch:** `feature/bsvp-validation`
**Scripts validated:** `tradingview-pine-scripts/iwm-bsvp` (+ core shared with `-v2`), `tradingview-pine-scripts/iwm-scalping` (+ `-v2`)
**Data:** `market_data_intraday` 1-min bars, 2015-01-02 → 2026-07-13, RTH-only (09:30–16:00 ET) — IWM 1.13M / SPY 1.36M / QQQ 1.28M RTH bars, resampled to 5m/15m/30m
**Method:** faithful Python port of the Pine math (`lib/indicators.calculate_bsvp`, unit-tested), event study of direction-adjusted forward returns (15m/30m/60m/EOD, session-confined) vs all-bars baseline, plus trade simulation using `iwm-bsvp.md`'s own rules (entry at signal close, 10-bar swing stop, 2:1 R:R target, EOD time-stop, both-hit = loss)
**Raw tables:** `bsvp_validation_2026-07-13_results.csv`, `_by_year.csv`, `_sweeps.csv` (this directory)

---

## Executive summary

1. **The core BSVP signal families have no standalone predictive edge.** Pooled
   across IWM/SPY/QQQ and 5m/15m/30m, every VPO-based entry (buy, sell,
   strong, prime, crossover) lands within a fraction of a basis point of the
   all-bars baseline. Hit rates: buy-side ≈ 51.8% vs 51.9% baseline; sell-side
   ≈ 47.6% vs 47.4%. The indicator is a *descriptive* pressure lens, not a
   predictive trigger.
2. **The readme's win-rate claims (55–70%) do not reproduce.** Under the
   readme's own trade rules the same setups win 40–46%, and the
   divergence-reversal pattern advertised at "70% WR, 3:1" wins **29–32%**
   with the worst expectancy of anything tested. Those numbers came from the
   small early alert sample; 11.5 years says otherwise.
3. **The one validated positive: the scalping composite with volume + time
   gates.** CALL lane-count ≥ 8 (of 11) inside the 09:35–14:30 window with
   RVOL ≥ 1.5 hits **55.4–56.2% vs 52.0% baseline** (n ≈ 9.8–13k events,
   +1.7 to +2.2 bps EOD edge) and is monotonic in the threshold — the dot
   counting you do by eye is real, but only long-side and only volume-gated.
4. **Short side: nothing works.** Every PUT-side signal in both scripts is
   flat-to-negative — intraday shorting of these index ETFs pays the upward
   drift away. Morning shorts are the single worst bucket tested (−2.6 bps).
5. **Time of day is a stronger conditioner than any BSVP internal.** Morning
   longs +0.60 bps / 55.0% hit; after-14:00 longs −0.92 bps. The v2 scripts'
   time multiplier is directionally right for longs but should be
   direction-aware, not symmetric.
6. **Ironically, IWM is the worst ticker for the IWM-branded signals** (buy
   EOD edge −0.5 to −1.0 bps on IWM vs +0.5 on QQQ). QQQ responds best.

---

## 1 · BSVP component verdicts

Trade sim = readme rules, pooled full period. Event edge = EOD horizon, pooled.

| Component | Trades | Win rate | Avg R | Edge (bps) | Verdict |
|---|---:|---:|---:|---:|---|
| `buySignal` | 127,320 | 45.2% | +0.01 | −0.1 | **Context only** — tracks drift, no lift |
| `strongBuy` | 123,704 | 45.2% | +0.01 | −0.2 | Same as buy — the extra conditions add nothing |
| `bullCross` | 46,476 | 45.7% | +0.00 | +0.2 | Context only |
| `sellSignal` | 99,821 | 40.2% | −0.02 | −0.3 | **Do not trade** — costs the drift |
| `strongSell` | 97,752 | 40.4% | −0.03 | −0.5 | Do not trade |
| `primeBuy` / `primeSell` | 26k / 21k | 44.8% / 38.9% | −0.02 / −0.03 | −0.9 / −0.8 | **Worse than plain buy/sell** — "prime" filter is anti-selective |
| `bullishDivConfirmed` (long) | 7,651 | 31.9% | −0.07 | **+0.4** (recent-3y **+4.8**, 52.9% hit) | **Keep as context, never with readme stops** — only component with positive lift, and it improves at lookback 21 |
| `bearishDivConfirmed` (short) | 13,485 | 28.6% | −0.15 | −1.2 | **Drop as an entry** — worst result in the study; fine as a "don't buy here" veto |
| `bullExhaustion` fade (short) | 26,753 | 33.1% | −0.08 | −1.0 | Drop |
| `sellExhaustion` fade (long) | 24,375 | 36.8% | −0.04 | +0.2 | Drift artifact — drop |
| accel arrows (`bull`/`sell`) | 41k / 79k | 44.5% / 38.6% | −0.01 / −0.01 | −0.2 / +0.1 | Decorative |
| **Entry-quality score (0–100)** | — | — | — | see below | **Does not rank** — rebuild or remove |

**Entry-quality buckets (EOD edge, buy side):** eq ≥ 70 → +0.05 bps · eq 50–70 → −0.23 · eq 30–50 → −0.04. Sell side: eq ≥ 70 is the *worst* bucket (−0.65). The score's weights (trend-strength + acceleration + divergence + alignment) measure how *developed* a move is, which by then is priced.

**Time-of-day (buy side, EOD):** 09:30–10:30 **+0.60 bps, 55.0% hit** · 10:30–14:00 +0.15, 54.7% · 14:00–16:00 **−0.92, 50.3%**. Sell side 09:30–10:30: **−2.60 bps**.

**Per-year stability (`buySignal`, 30m, EOD):** sign flips constantly (+5.2 in 2018/2022, −9.0 in 2020, −5.4 in 2025) — no stable regime; the pooled ≈ 0 isn't hiding a tradable sub-period.

## 2 · Scalping-lanes verdicts

**Composite (the readme's "count 6-7 dots" rule), pooled EOD:**

| Signal | n | Hit | Baseline | Edge (bps) | Trade sim win / avg R |
|---|---:|---:|---:|---:|---|
| call ≥ 7, no gates | 76,547 | 52.1% | 51.8% | +0.3 | 43.9% / +0.01 |
| call ≥ 8, window + RVOL≥1.5 | 13,011 | **56.0%** | 52.0% | **+1.7** | 50.9% / +0.02 |
| call ≥ 9, window + RVOL≥1.5 | 9,839 | **56.2%** | 52.0% | **+2.2** | 51.8% / +0.02 |
| put ≥ 6–9, any gating | 7k–69k | 45.5–47.2% | 45.2% | −2.7 to +0.7 | 39.6–43.6% / negative |

The RVOL gate is what turns the composite on: without it, call ≥ 8 is +0.14 bps; with it, +1.7. The readme's "6-7 dots" is under-thresholded — **8–9 of 11** is where selectivity shows. Put-side composites should not be traded from lane count.

**Per-lane lift (re-validating the tooltip "success rates"):**

| Lane | Edge (bps) | Verdict |
|---|---:|---|
| price vs VWAP (both sides) | +0.20 / +0.25 | **Best single lane** — keep, weight up |
| StochRSI >70 / <30 | +0.18 / +0.24 | Real (continuation reading) — keep |
| RSI > 60 | +0.17 | Keep |
| RSI 50-cross, EMA9/20/50 stack lanes | ±0.05 | Structure context, ~no standalone lift |
| ATR ≥ $0.15 | +0.01 | Gate is inert — and non-stationary (see §4) |
| 1m rejection lanes | −0.03 / −0.29 | Rare (n≈14k) and ~0 — context only |
| **5m breakout up / down** | **−0.38 / −0.24** | **Negative — breakout-chasing mean-reverts on these ETFs.** Remove from score or invert to a fade flag |

## 3 · Threshold sweeps

- **Divergence lookback:** bullish divergence improves 14 → **21** (+0.47 → **+1.08 bps**, 53.4% hit). Bearish stays negative at every value (7/14/21/28) — it's not a tuning problem.
- **Acceleration threshold (±20/−15):** bull side worsens as the threshold rises (chasing acceleration is anti-selective); sell side never exceeds +0.2 bps. No good setting exists.
- **Conv/div lookback (27):** 14 / 27 / 40 all within ±0.15 bps of zero for buy/sell. Not load-bearing.
- **ATR gate style:** absolute $0.15 ≈ ATR% ≈ ATR-vs-SMA50 in performance — switch to **ATR%** purely for stationarity (a $0.15 gate meant something at IWM $115 in 2015; it's always-on at $293).

## 4 · Pine script change list

### `iwm-bsvp` (and where noted, `-v2`)

**Bugs (independent of backtest):**
1. **Hidden divergences are inverted** (lines 135-136): `hiddenBullDiv` fires at `priceAtHigh`, `hiddenBearDiv` at `priceAtLow`. Hidden *bullish* divergence is a higher-low phenomenon. (Currently unused downstream, but wrong if ever wired.)
2. **`maxRange`/`minRange` never reset** (label block, lines 604-617): they ratchet monotonically over the chart's whole history, so Buy/Sell label offsets drift ever further from the pane. Track a rolling window (e.g. last 100 bars) instead.
3. **Info-table Buy/Sell ratio ignores `norm` mode** (line 187): `ratio` always uses raw `BPV/SPV` even when the normalized series drive every signal.
4. **`divergenceLookback/2`** (line 135-136) is float division feeding a series offset — works in v6 but rounds silently; make it explicit.
5. **Divergence ≠ divergence:** the detection tests "pressure fell for 2 bars at a price extreme," not pivot-vs-pivot slope comparison. This is why `bearishDivConfirmed` is noise. If divergence stays, implement true pivot comparison (`ta.pivothigh`-based).

**Data-driven changes:**
6. **Retitle the signal layer as context, not entries.** BUY/SELL/PRIME labels imply tradable edge the data doesn't support. Keep the VPO pane (it *is* a good pressure lens — your read of "helpful for understanding, not predictive" is exactly what the data says); drop or clearly demote the entry labels.
7. **Entry-quality score: remove or rebuild.** It does not rank outcomes. A rebuilt score should weight what tested positive: time-of-day (morning/midday), VWAP side, RVOL ≥ 1.5, StochRSI extreme, composite lane count — not trend-strength/acceleration.
8. **Divergence lookback 14 → 21**, keep `bullishDivConfirmed` as a long-context flag, delete the bearish twin as a signal (retain as a "don't chase longs" veto inside `buySignal`, which is how it's already used).
9. **Suppress or downgrade** buy labels after 14:00 ET and sell labels before ~10:30 ET. v2's `timeMultiplier` (1.2× morning / 0.7× afternoon) is right for longs but backwards for shorts — make it direction-aware.
10. **Session consistency warning:** on an extended-hours chart the VPO EMAs digest ETH bars the signal layer then RTH-gates away. Your 7/13 QQQ chart read vpo1 +24.2 (ETH) where the RTH-only series reads −9.5 — same histogram regime, very different level. Either compute on RTH-only charts or add a `syminfo.session` check that annotates the table when ETH is active.

### `iwm-scalping` (and `-v2`)

11. **Ship the composite score with alerts at ≥ 8 of 11 CALL lanes, gated on the time window AND RVOL ≥ 1.5** (v2's composite exists; re-threshold it and make the RVOL gate mandatory, not a bonus point). This is the only signal in either script that validated.
12. **Do not alert PUT composites** from lane count — no threshold/gating combination tested positive.
13. **Remove the 5m-breakout lanes from the score** (negative lift both directions) or re-purpose them as fade context.
14. **Replace `atrMin = 0.15` with an ATR% input** (≈ 0.08% of price matches today's $0.15 on IWM) — same performance, stationary across price regimes.
15. **Correct the tooltip "success rates"** — they're from the early small sample. Validated per-lane EOD hit rates (pooled): VWAP-side 51.9/47.4, StochRSI-extreme 51.4/46.6, RSI>60 52.0 (see `_results.csv` `lane|*` rows for the full set).

## 5 · What this means for day-to-day use

- **Keep BSVP on the chart as the regime lens you already use it as** — buyers-vs-sellers, building vs fading pressure. That use survives validation; the entry labels don't.
- **Trade the composite, not the oscillator:** morning/midday, CALL side, 8+ lanes, RVOL ≥ 1.5. That's your only statistically validated trigger, and it's modest (+2 bps EOD per event, 56% vs 52%) — a *screen* for when to look, not a money printer. On options, spreads and theta can eat 2 bps; it works best as a timing filter on setups you'd take anyway.
- **Stop taking short-side signals from either script**, especially before 10:30.
- **Prefer QQQ/SPY over IWM for these signals** despite the scripts' branding.
- **Next step (separate PR if wanted):** `calculate_bsvp` now lives in `lib/indicators.py`, so the validated composite can be wired into `signal_monitor` as a strategy (Discord alerts with the exact gates above), and journal entries can be tagged with lane-count/BSVP context automatically.

## 6 · Repo findings surfaced along the way

- **`DataLoader` timezone inconsistency:** `_load_intraday_from_sql` returns UTC-naive timestamps (`lib/data_loader.py:309`) while the AlphaVantage parquet path is ET-naive; `shared_utils.filter_rth` assumes ET. Any analysis loading intraday directly from Cloud SQL gets a shifted RTH window. The cache pull for this study converted UTC→ET explicitly; a repo fix should normalize the SQL path to ET (relates to the tz-mix checks in `gcp/queries/check_trades_tz_mix.sql`).
- **`.env` `DB_PASS` is stale** vs `db-trading-pass:latest` (known gotcha, hit again here).
- Live demonstration of audit finding C-xx: the stale password produced `Cloud SQL query failed → empty DataFrame → "0 rows"` instead of raising (`lib/data_loader.py` silent fallback, already catalogued in `docs/audits/FALLBACK_AUDIT_2026-05-13.md`).

## Methodology notes & caveats

- Event = rising edge of each signal (Pine's `sig and not sig[1]` label semantics); overlapping-bar states would multiply-count single setups.
- Forward returns are session-confined (no overnight bleed); EOD = signal close → same-day final close, direction-adjusted.
- Baseline = all RTH bars of the same ticker/timeframe — so "edge" is lift over drift, not raw return.
- Trade sim marks stop-and-target-in-same-bar as a loss (conservative).
- No transaction costs, spreads, or options translation — reported edges are *upper bounds* on tradability.
- Cells with n < 100 are reported in the CSVs but not relied on in verdicts; every verdict above rests on ≥ 2,000 events (most on 20k+).
- Pine parity: math pinned by unit tests (`tests/lib/test_indicators.py::TestPowerBalance/TestCalculateBsvp`); exact numeric parity vs a live TV chart requires an RTH-only chart (ETH charts shift VPO levels — see §4 item 10).
