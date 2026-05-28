# Options Exec-Backtest Results — IWM 0DTE ATM

**VERDICT: FAIL** on all 3 cells in BOTH walk-forward windows
(3-fold 2024-2026 and 5-fold 2022-2026). Hypothesis rejected.

This is the companion experiment to
[`docs/EXEC_BACKTEST_RESULTS.md`](EXEC_BACKTEST_RESULTS.md) (Track B,
**FAIL** on all 3 cells of IWM underlying). The hypothesis under test:
the long-option asymmetry (defined downside, leveraged upside) might
rescue an edgeless setup. Counter-hypothesis: theta is the systematic
cost of buying optionality, doesn't generally beat a 40%-hit /
1.5R-target geometry.

**The counter-hypothesis won.** Long ATM 0DTE on top of Track B's
edgeless setups produces near-zero expectancy in the most-generous
regime (5-fold 2022-2026, where 2022's 30m cell did show +$6.80/contract
— but never repeated) and negative expectancy in the clean-coverage
regime (3-fold 2024-2026). On every cell × window combo, hit rates
hover at 36-39% and asymmetry ratios cluster at ~1.0 (no left-skew
protection from the bounded downside). Per spec, variants 1 (OTM)
and 2 (1DTE) are NOT run — base fails by > 25% margin on every cell.

## TL;DR

| Window | Cell | n trades | hit | net exp/contract | pos-exp folds | Verdict |
|--------|:----:|---------:|----:|-----------------:|:-------------:|:-------:|
| 3-fold (2024-2026) | 5m  | 12,312 | 37.8% | **-$0.28** | 1/3 | FAIL |
| 3-fold | 15m | 3,619  | 37.3% | **-$0.49** | 1/3 | FAIL |
| 3-fold | 30m | 1,505  | 33.9% | **+$0.17** | 1/3 | FAIL |
| 5-fold (2022-2026) | 5m  | 19,292 | 37.7% | **+$0.02** | 3/5 | FAIL |
| 5-fold | 15m | 5,794  | 38.0% | **-$0.02** | 3/5 | FAIL |
| 5-fold | 30m | 2,307  | 36.4% | **+$1.29** | 2/5 | FAIL |

Both windows agree on the FAIL verdict — no BORDERLINE state.

### Why this is a clean rejection: options cannot fix a hit-rate problem

The deeper read on the diagnostic: this is the **direction failure
showing up again wearing an options costume**, not a new finding.

Options are a payoff-shaping tool. The underlying setup already had
fine asymmetry — 1.5R target / 1R stop gives ~1.7-2× win/loss in
option-space (gamma convexity transmits cleanly through the wrapper).
What the setup LACKED was hit rate. At ~35% hit rate × 1.85× asymmetry:

  0.35 × 1.85 − 0.65 × 1.0 = +0.0025 / contract gross, i.e. break-even
  before theta; clearly negative after the $1.38 round-trip cost.

That 35% comes directly from the type model having no directional
edge — the same 49% finding the direction work surfaced weeks ago.
Long ATM 0DTE doesn't reshape that; it just inherits it and pays
theta on top.

**Implication for the unrun variants:** 1DTE (variant 2) reduces theta
but cannot rescue a 35% hit rate (theta wasn't the binding constraint;
the c3 asymmetry-margin check was, at ratio 1.00-1.10 vs the 1.20
bar). OTM (variant 1) would make the hit rate strictly worse. Per the
brief the variants don't run when base fails by > 25% margin; per
this analysis, the variants don't run because no option-shape change
can compensate for the underlying signal not carrying directional
information.

### One stone left unturned

The base case imposed an underlying stop, which is what made the
option's bounded-downside property redundant. A **no-stop structure**
(buy the option, premium is the max risk, hold to target or expiry)
is a genuinely different trade that this diagnostic does not
automatically kill — it's how a lot of 0DTE traders actually trade.
We name it for completeness, not as a recommendation: the prior
remains negative (direction model is a ~coin flip, magnitude is
likely the known intraday IV curve), so any future test of it should
set the success bar in advance and expect it to fail. The options
question is ~95% sealed, not 100%.

**Source data**: see `docs/options_exec_backtest_data/base_3fold/` and
`base_5fold/` (per_fold.csv + trades.csv.gz + results.json).
**Run ID**: `options-exec-backtest-xbkcv` (2026-05-28, 1h20m wall-clock).

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

### Per-cell summary (base case, 5-fold 2022-2026)

Hit rate, gross/net expectancy are unweighted means across trades.
Total net is the literal sum of `net_pnl_per_contract` across all
folds for the cell. "pos-exp folds" counts folds with mean net exp > 0.

| Cell | n trades | hit rate | gross exp / contract | **net exp / contract** | total net | pos-exp folds | Verdict |
|------|---------:|---------:|---------------------:|-----------------------:|----------:|--------------:|:--------|
| 5m   | 19,292 | 37.7% | +$1.39 | **+$0.02** | +$375.30 | 3/5 | FAIL (c1, c2) |
| 15m  | 5,794  | 38.0% | +$1.36 | **-$0.02** | -$100.85 | 3/5 | FAIL (c1, c2) |
| 30m  | 2,307  | 36.4% | +$2.67 | **+$1.29** | +$2,983.52 | 2/5 | FAIL (c1, c2, c4*) |

\* 30m's c4 (no-single-regime-dominance) fails because 2022 alone
contributed +$2,755 of the +$2,983 total (92% — far above the 50%
cap). The 2022 anomaly is examined in the diagnostics below.

### Per-cell summary (base case, 3-fold 2024-2026)

| Cell | n trades | hit rate | gross exp / contract | **net exp / contract** | total net | pos-exp folds | Verdict |
|------|---------:|---------:|---------------------:|-----------------------:|----------:|--------------:|:--------|
| 5m   | 12,312 | 37.8% | +$1.08 | **-$0.28** | -$3,500.99 | 1/3 | FAIL (c1, c2) |
| 15m  | 3,619  | 37.3% | +$0.89 | **-$0.49** | -$1,774.95 | 1/3 | FAIL (c1, c2) |
| 30m  | 1,505  | 33.9% | +$1.55 | **+$0.17** | +$261.45 | 1/3 | FAIL (c1, c2) |

### Cross-window consistency check

| Cell | 5fold verdict | 3fold verdict | Agree? |
|------|:-------------:|:-------------:|:------:|
| 5m   | FAIL | FAIL | ✅ |
| 15m  | FAIL | FAIL | ✅ |
| 30m  | FAIL | FAIL | ✅ |

Both windows agree on FAIL for every cell. No BORDERLINE state.

### Per-fold per-cell (raw)

Full per-fold breakdown in
`docs/options_exec_backtest_data/base_5fold/per_fold.csv` and
`base_3fold/per_fold.csv`. Key picks below.

**5-fold 30m cell — the only fold-cell with eye-catching positive exp:**

| Fold | Window | n | hit | net_exp | total_net |
|-----:|:-------|--:|----:|--------:|----------:|
| 1 | 2022 | 405 | 40.2% | **+$6.80** | +$2,755 |
| 2 | 2023 | 397 | 34.8% | -$0.08 | -$33 |
| 3 | 2024 | 731 | 31.7% | -$1.01 | -$735 |
| 4 | 2025 | 774 | 36.2% | +$1.29 | +$997 |
| 5 | 2026 YTD | 0 | — | — | — (voided, see data-quality note) |

2022's +$6.80/contract is an outlier — driven by Fed-tightening
regime where IV was systematically elevated AND the underlying was
trending hard. The 2022 30m bsm_void count (894 of 1,299 candidates)
is far higher than later folds, which suggests the type model
generated many candidates that the underlying-space trigger never
hit — survivor bias toward big-move days. Three of the next four
folds were flat-to-negative; one cell-fold dominating the cell's
total fails c4.

**5-fold YTD 2026 fold (#5) was entirely voided** with `no_rate=4706`
(5m), `no_rate=1201` (15m), `no_rate=544` (30m). Initial attribution
was to FRED-rates freshness; on investigation `daily_rates` is fully
populated through 2026-05-26 (2,846 rows, all `dgs3mo` non-null).
The real cause was a bug in `lib/options_exec_backtest/runner.py`:

  `rates_full = _load_daily_rates(engine, cutoffs[0], cutoffs[-1])`

This loaded rates only through `cutoffs[-1]` = `2026-01-01`, but the
final fold's test window is `[2026-01-01, 2026-12-31)`. Every setup
with `rate_date >= 2026-01-02` wasn't in the in-memory dict → voided
as `no_rate`. Fixed in a follow-up commit on `fix/fred-rates-freshness`
(hoist `FINAL_FOLD_TEST_END` to a module constant used by both the
fold-iteration `test_end` derivation AND the rates preload range;
regression test asserts `FINAL_FOLD_TEST_END` > every window's last
cutoff). A re-run of the backtest after the fix would populate fold-5;
the verdict on folds 1-4 alone already rejects the hypothesis (not
≥4/5 positive on any cell), so the re-run is optional for completeness
rather than for the verdict.

## Post-run analysis

Computed from `docs/options_exec_backtest_data/base_5fold/trades.csv.gz`
(n=27,393 trades). Same patterns in the 3-fold subset.

### 1. Theta drag — fraction of total trade friction

| Cell | mean theta share | median |
|------|-----------------:|-------:|
| 5m   | 45.7% | 50.9% |
| 15m  | 58.4% | 68.1% |
| 30m  | 67.7% | 82.1% |

The 30m cell pays disproportionate theta — 0DTE option holders are
bleeding ~⅔ of their per-trade friction to time decay. As expected:
longer holds on 0DTE = more theta eaten.

### 2. Exit-reason distribution (5-fold, all cells)

| exit_reason | share |
|:------------|------:|
| stop        | 40.0% |
| time        | 33.9% |
| target      | 21.6% |
| eod         |  4.5% |

Target hits = 21.6% — close to but below the c3 implicit hit-rate
contribution. Time-stops fire on ~⅓ of trades, meaning the trade
neither stops nor targets within the time budget. Those are
underlying-flat trades, where theta dominates the close.

### 3. Win/loss asymmetry — by cell

| Cell | win rate | avg win | avg loss | (win × hit) vs (loss × miss) ratio |
|------|---------:|--------:|---------:|----------------------------------:|
| 5m   | 37.8% | +$24.40 | -$14.78 | 1.003 |
| 15m  | 37.6% | +$26.83 | -$16.20 | 0.998 |
| 30m  | 35.2% | +$41.58 | -$20.63 | 1.095 |

**This is the cleanest rejection of the hypothesis.** The brief's c3
check is "(hit_rate × avg_win) > (miss_rate × avg_loss) with ≥ 20%
margin" — i.e. ratio ≥ 1.20. The actual ratios are 1.00, 1.00, 1.10.

The avg_win/avg_loss skew of ~1.7-2.0x is exactly what you'd expect
from a 1.5R-target / 1R-stop geometry: the underlying-space trade
asymmetry passes through to the option-space P&L. The OPTION WRAPPER
itself doesn't add asymmetry on top — the bounded-downside / unbounded-
upside premise of long options is fully captured in the underlying-
stop-managed setup already (the stop bounds the loss, the target
caps the win, neither is "rescued" by long optionality).

Theta then eats whatever remaining asymmetry exists, leaving net
expectancy at ~$0/contract before costs (which is what the gross_exp
column shows: $1.39 / $1.36 / $2.67 for 5m/15m/30m) and below-cost
($1.38 round-trip) after.

### 4. Loss concentration — by fold (5-fold)

See per-fold tables above. The single bright spot was 5-fold 30m
in 2022 (+$6.80/contract on n=405, total +$2,755). That fold-cell
contributes 92% of the 30m cell's total positive net — far above
the 50% c4 cap. It's the kind of single-regime windfall that
backtests pick up and overfit on; the c4 check exists exactly to
catch this. 2023 / 2024 / 2025 all flat-to-negative confirms the
2022 print didn't generalize.

The pattern across cells & windows: 2022 was the most-positive
regime (Fed tightening + elevated IV + trending underlying = long
0DTE option holders benefited from sharp directional moves before
theta could overwhelm). Every subsequent regime tightened that
window.

## Variants

Variants 1 (1-strike OTM, 0DTE) and 2 (ATM, 1DTE) are only run if
the base case PASSES or is BORDERLINE per the spec. Borderline =
within 25% of the four checks.

**NOT RUN** — base case fails by > 25% margin on every cell × window
combo:

- c1 (positive-folds bar): 3-fold has 1/3 on every cell (need 2/3 =
  borderline if 2/3, fail at 1/3 by margin). 5-fold has 3/5 on 5m
  and 15m (need 4/5, off by 25% which is borderline-equal), and 2/5
  on 30m (FAR off).
- c2 (≥$5/contract net expectancy): every cell × window combo is in
  the -$0.49 to +$1.29 range — off the $5 bar by **74-110% margin**.
- c3 (≥20% margin on (hit × win) vs (miss × loss)): actual ratios
  are 0.998, 1.00, 1.10 — off the 1.20 bar by **8-17%**, also FAIL.

Running OTM / 1DTE variants on top of a base case that misses c2 by
~100% would be hope-mode optimization. Per the brief: "If base fails,
that is the verdict."

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
