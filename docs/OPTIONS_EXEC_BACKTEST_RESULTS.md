# Options Exec-Backtest Results — IWM 0DTE ATM

**VERDICT: PENDING RUN** — fill in below after dispatching
`options-exec-backtest --mode=base` (post-AV-intraday backfill).

This is the companion experiment to
[`docs/EXEC_BACKTEST_RESULTS.md`](EXEC_BACKTEST_RESULTS.md) (Track B,
**FAIL** on all 3 cells of IWM underlying). The hypothesis under test:
the long-option asymmetry (defined downside, leveraged upside) might
rescue an edgeless setup. Counter-hypothesis: theta is the systematic
cost of buying optionality, doesn't generally beat a 40%-hit /
1.5R-target geometry.

## TL;DR

— Pending run —

## Method (reference)

### Setup detection — identical to Track B

We reuse `gcp.research.strat_engine.strat_pred_train.featurize` /
`make_lgbm` directly. The model is the same calibration-none LightGBM
classifier. Per-fold retrain — no shared artifact across folds.

- **Long setup**: argmax class = `2U` AND `top_prob ≥ 0.55`
- **Short setup**: argmax class = `2D` AND `top_prob ≥ 0.55`
- Type 1 / 3 confident calls produce no setup.

### Trade vehicle — long ATM 0DTE option

| Setup | Vehicle |
|-------|---------|
| Long (2U) | Long ATM 0DTE call |
| Short (2D) | Long ATM 0DTE put |
| Variant 1 | +1 strike OTM |
| Variant 2 | ATM 1DTE |

Strike: closest available strike to underlying at the trigger fill
(read from the IV preload's strike grid — never synthesized).

### Trade lifecycle — underlying-space exits, option-space P&L

- **Entry**: stop-buy at trigger bar's high (long) / stop-sell at low
  (short), filled inside bar T+1 with slippage. **Voided** if the
  trigger isn't hit in bar T+1's window.
- **Stop**: trigger bar's opposite extreme (long stop = trigger low).
- **Target**: 1.5R from entry.
- **Time stop**: 30 min (5m/15m) / 60 min (30m).
- **EOD**: if neither stop / target / time fires by end of session,
  close at last RTH 1m bar's close.
- **Per-1m precedence**: target > stop > time, **conservatively assume
  STOP first on intrabar collision** (Track B parity).

### Pricing — BSM walk with T-1 EOD anchor IV

**Pivot 2026-05-28**: the brief asked for "anchor IV within ±300s of
trigger". Empirical testing showed AV's `HISTORICAL_OPTIONS` endpoint
is EOD-only (`date=YYYY-MM-DD` param, one snapshot/day at 4 PM ET; the
`datetime=` param the original design assumed does not exist — AV
silently returns the current chain for any unsupported param value).
`REALTIME_OPTIONS` returns the chain AT the moment of the request, not
at past moments. No vendor offers historical intraday options at our
price point. So the brief's ±300s anchor is unfulfillable for any
historical date, and we pivot to T-1 EOD anchor:

For each trade:
1. Find the most-recent EOD snapshot STRICTLY PRIOR to the trigger
   date (no look-ahead — same-day 4 PM IV did not exist at a 10:25
   AM trigger). Filter to (option_type, expiration = trigger_date +
   `expiration_dte`). Pick ATM/OTM strike against underlying-at-
   trigger (not underlying-at-anchor). Read implied_volatility —
   this is the **anchor IV** held constant through the trade.
2. Compute entry premium via `bs_price(S=entry_fill, K, T_entry,
   sigma=anchor_IV, r, q, kind)` where `r` is the day's
   `daily_rates.dgs3mo` and `q` is `sp500_div_yld`.
3. When the trade exits, compute exit premium with the SAME BSM but
   updated S (underlying at exit) and T (decayed time-to-expiry).
4. No IV path modeling — the brief locks this as conservative; any
   passing run holds even when realized IV moves favorably.

**The semantic of "constant anchor IV through the trade" is preserved
exactly.** Only the IV SOURCE changed from a ±300s intraday snapshot
to T-1 EOD. The conservatism direction: EOD IV often differs from the
actual intraday IV the trader would have paid; on average we expect
this introduces noise but not directional bias. On high-vol days
(FOMC, earnings, gap-open Monday after a weekend event) the anchor
may be materially wrong — documented as a known limitation.

If no anchor snapshot exists prior to the trigger date (e.g. the first
trade-day of the preload window has no T-1 within the 7-day preload
extension), the setup is **voided**. Same if the requested expiration
isn't in the anchor's chain (e.g. IWM Tuesday-expiring contracts in
2022 — not issued until Nov 2023). All voids count toward the
per-fold `voided` counter; nothing is silently filled with a default
(per CLAUDE.md Rule 3.7).

### Costs

Per CONTRACT, per side (× 100-share multiplier already accounted for):

| Cost | $/side | $/round-trip |
|------|-------:|-------------:|
| Spread | 0.03 | 0.06 |
| Commission | 0.65 | 1.30 |
| Slippage | 0.01 | 0.02 |
| **Total** | **0.69** | **1.38** |

### Walk-forward — DUAL WINDOW (3-fold + 5-fold)

IWM 0DTE coverage is partial in 2022-2023 (Mon/Wed/Fri only — Tue/Thu
expirations launched Nov 2023). To avoid letting that void rate drive
the verdict, the backtest runs BOTH windows in one job and reports
each independently. If both agree, the verdict is robust; if they
disagree, the disagreement itself is information.

#### 5-fold (2022-2026, wider regime variety, partial coverage in 22-23)

| Fold | Cutoff (train end) | Test window | Regime |
|-----:|:-------------------|:------------|:-------|
| 1 | 2022-01-01 | 2022       | bear / Fed tightening — Mon/Wed/Fri 0DTE only |
| 2 | 2023-01-01 | 2023       | recovery — Mon/Wed/Fri 0DTE; daily added Nov |
| 3 | 2024-01-01 | 2024       | bull continuation — daily 0DTE |
| 4 | 2025-01-01 | 2025       | current regime — daily 0DTE |
| 5 | 2026-01-01 | 2026 YTD   | partial-year locked OOS — daily 0DTE |

#### 3-fold (2024-2026, clean 99% coverage, single-bull sample)

| Fold | Cutoff (train end) | Test window | Regime |
|-----:|:-------------------|:------------|:-------|
| 1 | 2024-01-01 | 2024 | bull continuation |
| 2 | 2025-01-01 | 2025 | current regime |
| 3 | 2026-01-01 | 2026 YTD | partial-year locked OOS |

### Success bar (per window)

A cell PASSES base case in a given window iff ALL FOUR hold:

1. Net expectancy / trade > 0 in **≥ K of N** folds, where:
   - **5-fold**: K=4 (4/5 = 80%, slightly stricter than Track B's 6/8 = 75%)
   - **3-fold**: K=2 (2/3 ≈ 67%, looser — fewer folds, less statistical power)
2. Aggregate net expectancy > **$5 / contract** (per brief).
3. (hit_rate × avg_win) > (miss_rate × avg_loss) with **≥ 20% margin**.
4. No single fold's net P&L > **50%** of total (no single-regime dom).

If ALL THREE cells fail BOTH windows, variants are NOT run (per spec).
If the windows disagree, treat as BORDERLINE — escalate for review.

## Data restrictions documented

- **Test windows**: 5-fold 2022-2026 AND 3-fold 2024-2026 (both run).
- **IV anchor**: T-1 EOD snapshot from `etf_options_snapshots`
  (`market_session='EOD'`). EOD coverage is complete: ~252 days/yr for
  IWM in every year 2016-2026, verified 2026-05-28.
- **0DTE issuance coverage**: ~62% of trading days in 2022-2023 had a
  same-day-expiring IWM contract (Mon/Wed/Fri only — Tue/Thu were
  added Nov 2023). Tue/Thu setups in 2022-2023 void cleanly with
  "expiration not in chain" reason.
- **Look-ahead protection**: anchor must be from a date STRICTLY
  prior to the trigger date. Same-day 4 PM IV is rejected.
- **Snapshot tolerance**: ±300 sec. Setups outside this window are
  voided, not extrapolated.
- **IV path**: constant anchor — no IV smile or term-structure walk.
- **Volume / OI**: no filter. Even thin contracts cleared the snapshot
  filter; the cost model bakes in the realistic round-trip.

## Results

### Per-cell summary (base case, 5-fold) — PENDING

| Cell | n trades | hit rate | gross exp / contract | **net exp / contract** | total net | pos-exp folds | Verdict |
|------|---------:|---------:|---------------------:|-----------------------:|----------:|--------------:|:--------|
| 5m   | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _/5 | _pending_ |
| 15m  | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _/5 | _pending_ |
| 30m  | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _/5 | _pending_ |

### Per-cell summary (base case, 3-fold) — PENDING

| Cell | n trades | hit rate | gross exp / contract | **net exp / contract** | total net | pos-exp folds | Verdict |
|------|---------:|---------:|---------------------:|-----------------------:|----------:|--------------:|:--------|
| 5m   | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _/3 | _pending_ |
| 15m  | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _/3 | _pending_ |
| 30m  | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _/3 | _pending_ |

### Cross-window consistency check — PENDING

| Cell | 5fold verdict | 3fold verdict | Agree? |
|------|:-------------:|:-------------:|:------:|
| 5m   | _pending_ | _pending_ | _pending_ |
| 15m  | _pending_ | _pending_ | _pending_ |
| 30m  | _pending_ | _pending_ | _pending_ |

### Per-fold per-cell — PENDING

Filled from `docs/options_exec_backtest_data/base_5fold_per_fold.csv`
and `..._base_3fold_per_fold.csv` after the run.

## Post-run analysis — required regardless of pass / fail

These four diagnostics ship with both verdicts (per the brief's
"POST-RUN ANALYSIS" section):

1. **Average theta drag per trade** as a fraction of total cost — _pending_
2. **Distribution of exit reasons** (target / stop / time / EOD) — _pending_
3. **Wins: target-hits vs upside surprises beyond target** — _pending_
4. **Loss concentration by intraday window or regime** — _pending_

## Variants

Variants 1 (1-strike OTM, 0DTE) and 2 (ATM, 1DTE) are only run if
the base case PASSES or is BORDERLINE per the spec. Borderline =
within 25% of the four checks. **Do not dispatch variant runs while
the base case fails the spec by margins > 25%.**

## How to reproduce

```bash
# 1. Emit setup timestamps. The Cloud Run Job auto-uploads to
#    gs://${PROJECT_ID}-trading-data/research/options_exec_backtest/setup_timestamps.csv
#    (STABLE handoff path) AND a per-run archival copy at
#    {prefix}/{run_id}/setup_timestamps.csv.
gcloud run jobs execute options-exec-backtest \
    --update-args="--mode=emit_timestamps,--ticker=IWM" \
    --region us-east1 --wait

# 2. Backfill AV intraday snapshots. The fetcher's default --datetimes-file
#    points at the stable gs:// URL above, so no manual handoff needed.
gcloud run jobs execute fetch-av-options-historical-intraday \
    --region us-east1 --wait

# 3. Run the base case across BOTH walk-forward windows (default).
#    Same one Cloud Run Job; loads m1 bars once and reuses them.
gcloud run jobs execute options-exec-backtest \
    --update-args="--mode=base,--ticker=IWM,--folds-mode=both" \
    --region us-east1 --wait

# 4. Download both ledgers — separate subdirectories per window
gsutil cp -r gs://${PROJECT_ID}-trading-data/research/options_exec_backtest/<run_id>/base_5fold/* \
    docs/options_exec_backtest_data/
gsutil cp -r gs://${PROJECT_ID}-trading-data/research/options_exec_backtest/<run_id>/base_3fold/* \
    docs/options_exec_backtest_data/
```

## Files

| Path | Purpose |
|------|---------|
| `lib/options_exec_backtest/pricing.py` | BSM helpers + ATM strike picker |
| `lib/options_exec_backtest/iv_lookup.py` | Per-fold IV/strike snapshot resolver |
| `lib/options_exec_backtest/engine.py` | Per-setup lifecycle simulator |
| `lib/options_exec_backtest/runner.py` | Walk-forward orchestrator + emit-timestamps |
| `lib/options_exec_backtest/cli.py` | Cloud Run Job entry point |
| `gcp/fetchers/fetch_av_historical_options_intraday.py` | AV intraday backfill |
| `docs/options_exec_backtest_data/base_per_fold.csv` | Per-fold-per-cell stats |
| `docs/options_exec_backtest_data/base_results.json` | Verdict + check details |
| `docs/options_exec_backtest_data/base_trades.csv.gz` | Per-trade ledger |
