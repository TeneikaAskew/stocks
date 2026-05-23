# Phase 1 — Data Inventory + Return Baselines

**Date:** 2026-05-23
**Owner:** Trading-hypothesis audit (see `RESEARCH_PLAN.md`)
**Status:** Complete

## TL;DR

We have **vastly more historical data than the plan initially assumed**.
This eliminates the original "use EOD-gamma as a proxy for deeper
intraday history" concession — Phase 2 onward will run against actual
10-year historical EOD options chains and 1-min intraday bars, no
proxy substitutions.

| dimension | what we have | what we don't |
|---|---|---|
| **1-min intraday bars (SPY/IWM/QQQ)** | **2015-01-02 → 2026-05-23** (10+ years, ~2M bars per ticker) | None |
| **EOD options chains via AlphaVantage (SPY/IWM/QQQ)** | **2015-01-02 → 2026-05-23** for SPY (10.6 years, 21.6M rows, 2,861 trading days). IWM/QQQ start 2016-01-04. | None |
| **Daily bars (broader universe)** | back to 1999 for some tickers, 2016-05-02 for most. Top-100 by ADV all have ≥2,529 daily bars (10 years) | None |
| **Intraday-cadence gamma snapshot history** | only Track 0's window (~weeks of REALTIME data) | This is a vendor limitation — no provider sells historical 5-min options chains. Pre-Track-0 gamma analysis uses prior-day EOD chain (which is what production also uses on D+1 morning) — this is the production replay path, not a proxy |
| **VIX history** | **NOT in our DB** — needs backfill via yfinance or AV before Phase 4 | feature engineering blocker for vol-regime conditioning |
| **`signal_alerts` history** | 2026-03-19 → 2026-05-22 (10 weeks, ~720 alerts/ticker for SPY/IWM/QQQ) | thin, but enough for in-sample sanity checks |
| **`historical_signals` table** | pre-computed `return_5min` ... `return_60min` columns per fire — gold for outcome analysis | schema includes `entry_rsi`, `entry_ema9/20`, `entry_vwap`, `signal_strength`, FTFC-related columns — pre-engineered features available |

## 1. Coverage matrix

### Intraday 1-min bars (per-ticker partition tables)

| ticker | n_rows | min_ts (UTC) | max_ts (UTC) |
|---|---|---|---|
| SPY | 2,333,961 | 2015-01-02 17:39 | 2026-05-23 00:00 |
| IWM | 1,912,217 | 2015-01-02 19:41 | 2026-05-23 00:00 |
| QQQ | 2,180,992 | 2015-01-02 19:47 | 2026-05-22 23:59 |
| SPX | 0 | — | — (index, no bars) |

After RTH filter (09:30–15:45 ET), N per ticker × horizon × 10yr:

| ticker | N (5m fwd valid) |
|---|---|
| SPY | 1,034,210 |
| IWM | 1,048,407 |
| QQQ | 1,036,723 |

### EOD options snapshots — `etf_options_snapshots`

| ticker | data_source | n_rows | n_dates | min_d | max_d |
|---|---|---|---|---|---|
| SPY | alphavantage | 21,605,776 | 2,861 | 2015-01-02 | 2026-05-23 |
| IWM | alphavantage | 10,624,640 | 2,610 | 2016-01-04 | 2026-05-23 |
| QQQ | alphavantage | 14,463,578 | 2,610 | 2016-01-04 | 2026-05-23 |

Also: 12M rows under `data_source=''` (legacy Yahoo source) covering
2025-10-11 → 2026-04-10 — minor overlap, AlphaVantage is canonical.

### Top-100 liquid universe (60-day avg dollar volume)

Saved to [`data/universe_top100_by_adv.csv`](data/universe_top100_by_adv.csv).
Top 20: SPY, NVDA, QQQ, MU, MSFT, AMD, AAPL, AMZN, META, GOOGL, IWM,
AVGO, GOOG, PLTR, LITE, TSM, MRVL, QCOM, CRWV, LLY.

Daily-bar coverage for this universe: 10 years for most (≥2,529 bars
from 2016-05-02 to 2026-05-22). Confirmed via spot checks.

Intraday-bar coverage for non-ETF names: query in flight; results
will populate this section.

## 2. The noise floor — unconditional forward return distributions

**These numbers are the load-bearing reference for Phase 2.** Any
hit-rate Phase 2 reports has to be compared against the corresponding
cell here, not against 50% (the naive coin-flip).

### Intraday (1-min bars, 10 years, RTH 09:30-15:45 ET)

| ticker | N | pct_up_5m | pct_up_15m | pct_up_30m | pct_up_60m | pct_up_240m |
|---|---|---|---|---|---|---|
| SPY | 1,034,210 | **50.52%** | **51.67%** | **52.44%** | **53.28%** | **54.63%** |
| QQQ | 1,036,723 | 50.45% | 51.65% | 52.41% | 53.38% | 54.66% |
| IWM | 1,048,407 | 49.64% | 50.57% | 51.20% | 51.75% | 52.28% |

Mean signed-return bps at horizon (basis points per bar):

| ticker | mean_5m | mean_15m | mean_30m | mean_60m | mean_240m |
|---|---|---|---|---|---|
| SPY | +0.03 | +0.09 | +0.20 | +0.35 | +1.31 |
| QQQ | +0.04 | +0.11 | +0.22 | +0.42 | +1.47 |
| IWM | −0.01 | +0.02 | +0.06 | +0.18 | +0.75 |

Std deviation 5m bps: SPY 9.30, QQQ 11.83, IWM 13.10 — IWM is the
noisiest at intraday horizons.

**Reading the noise floor:**
- A CALL alert that hits 60% at 15m → +8pp over SPY baseline. Real lift.
- A PUT alert (predicting DOWN) at 15m → must clear 100% − 51.67% =
  48.33% to beat baseline. The 76.7% flip PUT signal from the FTFC
  backtest is +28pp over the PUT baseline → very large signal.
- At the 240m (~4hr, ~EOD-ish) horizon, the baseline drift dominates:
  PUTs must overcome a 45.4% (SPY/QQQ) headwind. PUT signals that fail
  to clear 50% at this horizon are pure noise after baseline adjustment.

### Daily (full universe-wide bars, 10 years)

| ticker | N | pct_up_1d | pct_up_5d | pct_up_20d |
|---|---|---|---|---|
| SPY | 2,529 | 55.20% | 61.47% | **68.80%** |
| QQQ | 2,529 | 56.70% | 60.99% | **68.49%** |
| IWM | 2,529 | 53.30% | 54.77% | 60.12% |

Mean signed-return bps at horizon:

| ticker | mean_1d | mean_5d | mean_20d |
|---|---|---|---|
| SPY | +5.69 | +28.07 | +111.62 |
| QQQ | +8.52 | +41.87 | +165.73 |
| IWM | +4.70 | +23.26 | +93.67 |

**Reading the long-horizon noise floor:**
- The historical equity uptrend is huge. PUT signals at 20-day horizon
  must beat 31.2% baseline (100 − 68.8%) — i.e. PUTs win when the
  baseline says DOWN. Very high bar.
- Multi-day CALL signals get a huge tailwind from the secular bull
  market — a 20-day CALL hitting 70% is **only +1.2pp lift** over the
  68.8% baseline. Not impressive even though it sounds it.
- **Implication for Phase 2/3**: every CALL hit-rate must be reported
  alongside the matching unconditional baseline at that horizon. The
  "lift" is the actual statistic, not the raw hit-rate.

## 3. Auxiliary data (Phase 4 features)

Phase 4's feature engineering will draw on:

| table | column for join | columns of interest |
|---|---|---|
| `historical_signals` | `(ticker, entry_time)` | `entry_rsi`, `entry_ema9`, `entry_ema20`, `entry_vwap`, `entry_volume`, `signal_strength`, `conditions_met`, `return_5min` ... `return_60min`, `extra` (jsonb), `strategy`, `timeframe_tag`, `ftfc_score`, `proximity_bucket`, `catalyst_session` |
| `daily_rates` | `date` | risk-free rate (Greeks) — 2,844 rows from 2015 forward |
| `strat_levels` | `(ticker, as_of)` | pre-computed strat-classified levels, `timeframe`, `level_type`, `strat_class` |
| `news_sentiment` | `(ticker, published_ts)` | `sentiment_score`, `relevance_score`, `overall_sentiment_label`, `topics` |
| `earnings_options_snapshots` | `(symbol, snapshot_date)` | single-stock options Greeks — for non-ETF gamma analysis at the symbol level |
| `backtest_trades` | `(run_id, ticker, entry_time)` | existing backtest results — benchmark to beat |

## 4. Known gaps + remediation

### 4.1 VIX — NOT in DB

Critical blocker for Phase 2 (VIX-tercile conditioning) and Phase 4
(vol-regime feature). Need to backfill:

- **Source 1:** AlphaVantage `TIME_SERIES_DAILY` symbol `VIX` or `^VIX`
- **Source 2:** yfinance `^VIX` (cheaper, no API rate limits)
- **Recommendation:** add a one-shot Cloud Run Job
  `gcp/fetchers/fetch_vix_history.py` that pulls `^VIX`, `^VIX3M`,
  `^VVIX` daily back to 2015 into `market_data_daily` with the same
  schema as the rest. ~$0.02/run, one-time.

Cost estimate: <$0.10 of credits + one-time job dispatch.

### 4.2 Intraday-cadence options-chain history (pre-Track-0)

Genuine vendor limitation — nobody sells historical 5-min options
snapshots. Pre-Track-0 analysis uses prior-day EOD chain, which is
what production also uses on D+1 morning. This is the **production
replay path**, not a proxy. The constraint just means within-session
wall updates aren't captured for the historical window — same as the
live monitor was running until Track 0 deployed.

### 4.3 Broader-universe intraday coverage

`market_data_intraday_other` GROUP BY ticker times out (table too
large). Targeted probe for the top-100 universe is in flight; results
will populate this section.

## 5. What this means for the next phases

### Phase 2 (gamma × FTFC × horizon outcome grid)

- **Universe**: SPY, IWM, QQQ
- **Window**: full 10 years (2015-2016 start through 2026-05-22)
- **Levels**: King/Gate/Flip per (ticker, date) from D-1 EOD chain
  → exactly the production live signal pattern
- **Horizons**: 5m, 15m, 30m, 60m, 240m (intraday) + 1d, 5d (daily-bar)
- **Subgroups**: FTFC (prev-day-direction proxy from daily bars), VIX
  tercile (after backfill lands), ToD bucket, DoW
- **N per subgroup** will be large — the 10-year window makes thin-cell
  problems much less acute than the 30-day pilot

### Phase 3 (strat methodology edge audit)

- **Universe**: full top-100 by ADV
- **Window**: 10 years of daily bars
- **Combos**: all combos from `lib.strat.StratClassifier`
- **FTFC depth**: 1-TF / 2-TF / 3-TF / 4-TF — uses intraday bars for
  60m/30m/15m TFs which we have for the 3 ETFs (10yr); for non-ETF
  names FTFC depth is daily-only

### Phase 4 (feature importance + correlation)

- **Universe**: SPY/IWM/QQQ (because gamma features only available
  for these), expanded to top-100 for the non-gamma feature subset
- **Feature matrix**: ~30 features as planned, plus
  `historical_signals` columns (already-engineered) as direct inputs
- **Window**: 10 years (subject to Phase 2 outcome window)

### Phase 5 (walk-forward stability)

- 10-year history allows 60-day train / 20-day test windows with
  ~30 non-overlapping cycles — robust stability metric

## 6. Artifacts

- [`data/baselines_intraday.csv`](data/baselines_intraday.csv) — 10yr
  unconditional intraday return distributions per ETF × horizon
- [`data/baselines_daily.csv`](data/baselines_daily.csv) — 10yr daily-
  horizon baselines
- [`data/universe_top100_by_adv.csv`](data/universe_top100_by_adv.csv)
  — selected universe with dollar-volume rankings
- [`gcp/queries/p1_baselines.sql`](../../../gcp/queries/p1_baselines.sql)
  — reproducible baselines query

## 7. Open follow-ups (post-Phase-1)

1. **VIX backfill** — block Phase 2 vol-regime conditioning until done
2. **Schema fixes** in plan for: `news_sentiment.published_ts` (not
   `published_at`), `strat_levels.as_of` (not `date`),
   `earnings_options_snapshots.symbol` (not `ticker`)
3. **Intraday probe for top-100** in flight — results pending
