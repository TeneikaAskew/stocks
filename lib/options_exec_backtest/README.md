# Options Execution-Backtest

**Status: see [`docs/OPTIONS_EXEC_BACKTEST_RESULTS.md`](../../docs/OPTIONS_EXEC_BACKTEST_RESULTS.md) for the verdict.**

This module parallels [`lib/exec_backtest`](../exec_backtest) (Track B,
the underlying-space execution backtest, FAIL on all 3 cells). The setup
detection is identical (frozen strat-engine type model, top_prob ≥ 0.55,
2U → long / 2D → short). The trade lifecycle keeps **stop / target /
time-stop in UNDERLYING price space** — the only thing that changes is
the **P&L vehicle**: long ATM 0DTE call (long setups) / put (short
setups) instead of long / short the underlying.

The hypothesis under test: long-option asymmetry (defined downside,
leveraged upside) might rescue an edgeless underlying setup. The
counter-hypothesis: theta is the systematic cost of buying optionality
and the long-vol payoff doesn't generally beat a 40%-hit-rate /
1.5R-target geometry. We test, accept the result.

## What's here

- `pricing.py`  — pure-numpy Black-Scholes-Merton helpers (price, ATM-strike
  rounding, years-to-expiry). py_vollib_vectorized parity tested.
- `iv_lookup.py` — IV/strike resolver. PRELOADS one fold's worth of
  option snapshots from `etf_options_snapshots` into RAM at fold start
  (Rule 0 batch pattern — never per-setup SQL). Generic on ticker
  (IWM/SPY/QQQ).
- `engine.py`   — hermetic per-setup trade-lifecycle simulator. Detects
  underlying stop/target/time-stop exactly like Track B's engine, then
  prices the option mid at entry and exit via BSM walked with constant
  anchor IV (no IV path modeling — conservative read per the brief).
- `runner.py`   — walk-forward orchestrator. 5 folds (test 2022/2023/
  2024/2025/2026 — restricted to 0DTE-available years). Emit-timestamps
  mode AND full-backtest mode share the same predict-fold path.
- `cli.py`      — Cloud Run Job entry point. `--mode={emit_timestamps,
  base, variant_otm, variant_1dte}`.

## Data dependency: AV intraday backfill

The `etf_options_snapshots` table is EOD-only for 2022-2024 IWM 0DTE
(~1 snapshot/day at 4 PM ET). The backtest needs intraday snapshots
aligned with setup timestamps. The companion fetcher
[`gcp/fetchers/fetch_av_historical_options_intraday.py`](../../gcp/fetchers/fetch_av_historical_options_intraday.py)
backfills these by hitting AV's `HISTORICAL_OPTIONS` endpoint with the
`datetime=` (intraday) param.

**Two-step run:**

```bash
# 1. Emit the unique setup timestamps the type model fires on
python -m lib.options_exec_backtest.cli \
    --mode=emit_timestamps \
    --out=/tmp/oeb \
    --timestamps-out=/tmp/oeb/iwm_setup_timestamps.csv

# 2. Backfill AV intraday snapshots for those timestamps
python -m gcp.fetchers.fetch_av_historical_options_intraday \
    --datetimes-file /tmp/oeb/iwm_setup_timestamps.csv \
    --skip-existing

# 3. Run the base case (ATM 0DTE)
python -m lib.options_exec_backtest.cli --mode=base --out=/tmp/oeb/base
```

## Walk-forward — 5 folds (2022-2026)

Restricted from Track B's 8 to 5 because IWM 0DTE didn't exist daily
until 2022. Each fold trains on data < cutoff and tests on
[cutoff, next_cutoff).

| Fold | Train ends | Test window | Regime |
|-----:|:-----------|:------------|:-------|
| 1 | 2022-01-01 | 2022       | bear / Fed tightening |
| 2 | 2023-01-01 | 2023       | recovery |
| 3 | 2024-01-01 | 2024       | bull continuation |
| 4 | 2025-01-01 | 2025       | current regime |
| 5 | 2026-01-01 | 2026 partial (Jan-May) | partial-year locked OOS |

Success bar adapted from Track B's "6 of 8" to **"4 of 5"** — same 75-80%
threshold ratio.

## Costs

Per IWM 0DTE near-the-money standard execution:

| Cost | Per side | Round trip |
|------|---------:|-----------:|
| Spread       | $0.03 | $0.06 |
| Commission   | $0.65 | $1.30 |
| Slippage     | $0.01 | $0.02 |
| **Total/contract** | **$0.69** | **$1.38** |

## Hard guardrails (from the brief)

- No optimistic fills. Use snapshot mid + realistic slippage.
- No IV path modeling — anchor IV held constant.
- Type model is frozen — no threshold tuning, no retraining.
- Variants 1/2 (1-strike OTM, 1DTE) only run if base passes or borderline.
- No combining variants.
- Base test stands alone. If base fails, that is the verdict.

## Module hygiene

We do NOT modify `gcp/research/strat_engine/` (the frozen type model)
nor `lib/exec_backtest/` (Track B's reference). Both stay in-tree as
load-bearing baselines.
