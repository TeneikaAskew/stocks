# Exec-Backtest Results — IWM Strat Engine

**VERDICT: FAIL — all three cells (5m / 15m / 30m) failed the base-case
success bar in 0 of 8 walk-forward folds; gross expectancy is near-zero
and $0.05 round-trip friction makes the net negative across every
regime. Variants NOT run, per spec.**

## TL;DR

- **62,138 5m + 18,542 15m + 7,456 30m trades** simulated across 8
  walk-forward folds spanning 2019 recovery → 2022 bear → 2026 partial
  YTD.
- **Hit rate consistently ~38–47%** on every fold/cell — matches the
  break-even hit rate for a 1.5R-target / 1R-stop trade (40%).
- **Gross expectancy oscillates around $0.000 / share** (range −$0.044
  to +$0.017 across all folds × cells); after the $0.045–$0.05
  round-trip friction the **net expectancy is negative in EVERY fold,
  EVERY cell**.
- **Positive-expectancy fold count: 0 of 8 in every cell.** The spec
  requires ≥ 6 of 8. The model carries **zero exploitable directional
  edge** at the 0.55-confidence / 1.5R / 30–60-min-time-stop
  configuration.
- Per the spec: "If ALL 3 cells (5m/15m/30m) FAIL: verdict = FAIL, do
  NOT run variants, close track." Variants were **not** dispatched.

## What this measures (and what it does NOT)

This is the **execution** backtest, not a re-evaluation of the type
model's classification quality. The model's locked OOS metrics
(log-loss beat, ECE) are unchanged. What this test asked was:

> Given the type model's HIGH-CONFIDENCE 2U/2D predictions, can a
> mechanical strat-style execution playbook (stop-buy at trigger bar's
> high, 1.5R target, 30–60 min time stop, intrabar 1m fills, realistic
> friction) turn that classification signal into a positive $/share
> edge per trade?

The answer is no — across all three cells the model's high-confidence
predictions, when traded mechanically, hit the trigger with hit rate
~40% (the **break-even** hit rate at 1.5R) and produce ~$0.00 gross
expectancy per share before costs. The 5¢ round-trip then sinks every
fold below the line.

This is consistent with the model being a CALIBRATED **structure**
predictor (next bar = 2U / 2D / 1 / 3) rather than a directional
**magnitude/P&L** predictor. A bar can be a "2U" by 1 tick or by 50¢
— the type label is the same. The model knows when a 2U is more
likely than chance; it does not know how far that 2U will run.

## Method (reference)

### Setup detection (read-only consumption of the frozen type model)

We **retrain the same** LightGBM type model used in production for
each walk-forward fold (raw softmax, no post-hoc calibration —
matches `DEFAULT_CALIBRATION = "none"` in `strat_pred_train.py`,
locked 2026-05-27). We do NOT modify any code under
`gcp/research/strat_engine/`; we import `featurize` and `make_lgbm`
directly to keep the per-fold model identical to the production
pipeline at that fold's cutoff.

**Triggering rule:**
- Long setup: model argmax = `2U` AND `top_prob ≥ 0.55`
- Short setup: model argmax = `2D` AND `top_prob ≥ 0.55`
- Type 1 / 3 confident calls produce **no** setup.

### Trade lifecycle (mechanical, no discretion)

- **Trigger bar** = bar T whose close emitted the prediction.
  `strat_features.ts` is the bar's OPEN; bar T+1 starts at
  `ts + TF_MINUTES`.
- **Entry**: stop-buy at trigger.high (long) / stop-sell at
  trigger.low (short). Fill ONLY within bar T+1's window
  `[ts_close, ts_close + TF_MINUTES)`. If not hit during bar T+1,
  setup voided. Gap-through fills at bar open ± slippage.
- **Stop**: opposite extreme of trigger bar.
- **Target**: `entry ± 1.5 * |entry − stop|`.
- **Time stop**: 30 min (5m / 15m) / 60 min (30m).
- **Order of evaluation per 1m bar after entry**: target > stop > time.
  When both target and stop fall within a single 1m bar's range,
  **conservatively assume STOP first**.
- **Costs** (per share, both legs; $0.05 total round-trip):
  - commission: 1¢ / side
  - spread: 1¢ / side
  - slippage: 0.5¢ / side
- **Position size**: 1 unit per trade.

### Walk-forward windows

Identical to the production `DEFAULT_CUTOFFS` in
`strat_walk_forward.py`:

| Fold | Train ends | Test window      | Regime label                |
|-----:|:-----------|:-----------------|:----------------------------|
| 1    | 2019-01-01 | 2019             | recovery / bull             |
| 2    | 2020-01-01 | 2020             | COVID crash + V-recovery    |
| 3    | 2021-01-01 | 2021             | bull                        |
| 4    | 2022-01-01 | 2022             | bear / Fed tightening       |
| 5    | 2023-01-01 | 2023             | recovery                    |
| 6    | 2024-01-01 | 2024             | bull continuation           |
| 7    | 2025-01-01 | 2025             | current regime              |
| 8    | 2026-01-01 | 2026 (Jan–May 23, locked OOS) | partial-year |

### Success bar (binary per cell)

A cell **passes** base case iff ALL FOUR hold:
1. Net expectancy per trade > 0 in **≥ 6 of 8** folds.
2. Aggregate net expectancy / trade > **$0.02** (2¢) / share.
3. Hit rate > **40%**.
4. **No single fold's net P&L > 50% of total** (no single-regime
   dominance).

If ALL three cells (5m / 15m / 30m) FAIL → verdict = **FAIL** and
variants are NOT run.

## Results

### Per-cell summary (base case)

| Cell | n trades | hit rate | gross exp / sh | **net exp / sh** | total net | pos-exp folds |
|:-----|---------:|---------:|---------------:|-----------------:|----------:|:--------------|
| 5m   | 62,138   | 0.4054   | −$0.0078       | **−$0.0523**     | −$3,249   | 0 / 8         |
| 15m  | 18,542   | 0.4310   | −$0.0119       | **−$0.0543**     | −$1,007   | 0 / 8         |
| 30m  | 7,456    | 0.4328   | −$0.0150       | **−$0.0606**     | −$452     | 0 / 8         |

### Verdict checks per cell

| Cell | c1 (≥6/8 folds pos-exp) | c2 (>$0.02/sh net) | c3 (>40% hit) | c4 (≤50% single-fold) | **Pass?** |
|:-----|:------------------------|:-------------------|:--------------|:----------------------|:----------|
| 5m   | FAIL (0 / 8)            | FAIL (−$0.0523)    | PASS (0.4054) | FAIL (total<0)        | **FAIL**  |
| 15m  | FAIL (0 / 8)            | FAIL (−$0.0543)    | PASS (0.4310) | FAIL (total<0)        | **FAIL**  |
| 30m  | FAIL (0 / 8)            | FAIL (−$0.0606)    | PASS (0.4328) | FAIL (total<0)        | **FAIL**  |

> The `c4_no_dom` check (no single-regime dominance) registers `inf`
> when total net P&L is negative — every fold's "share" is
> mathematically undefined relative to a negative aggregate. The
> implementation treats negative-aggregate as a FAIL of c4
> (consistent with "the model cannot have produced a profitable
> single-regime concentration that we should worry about, because
> it is unprofitable everywhere").

### Per-fold table — 5m cell

| Fold                            | n      | hit    | gross / sh   | **net / sh**   | total net   | max DD       | Sharpe   |
|:--------------------------------|-------:|-------:|-------------:|---------------:|------------:|-------------:|---------:|
| 2019-01-01..2020-01-01          |  8,023 | 0.3834 | −0.00493     | **−0.04993**   |  −400.56    |  −403.54     | −0.2243  |
| 2020-01-01..2021-01-01 (COVID)  |  9,147 | 0.4079 | +0.00037     | **−0.04463**   |  −408.22    |  −409.64     | −0.1013  |
| 2021-01-01..2022-01-01          |  7,681 | 0.4063 | −0.01357     | **−0.05857**   |  −449.89    |  −453.62     | −0.1217  |
| 2022-01-01..2023-01-01 (bear)   |  8,290 | 0.4228 | −0.00239     | **−0.04739**   |  −392.89    |  −420.42     | −0.0923  |
| 2023-01-01..2024-01-01          |  8,476 | 0.3971 | −0.00665     | **−0.05165**   |  −437.82    |  −442.74     | −0.1541  |
| 2024-01-01..2025-01-01          |  8,659 | 0.4019 | −0.00965     | **−0.05465**   |  −473.19    |  −474.93     | −0.1406  |
| 2025-01-01..2026-01-01          |  8,183 | 0.4082 | −0.01030     | **−0.05530**   |  −452.53    |  −453.31     | −0.1147  |
| 2026-01-01..2026-05-23 (YTD)    |  3,679 | 0.4123 | −0.01852     | **−0.06352**   |  −233.70    |  −233.26     | −0.1189  |

### Per-fold table — 15m cell

| Fold                            | n      | hit    | gross / sh   | **net / sh**   | total net   | max DD       | Sharpe   |
|:--------------------------------|-------:|-------:|-------------:|---------------:|------------:|-------------:|---------:|
| 2019-01-01..2020-01-01          |  2,475 | 0.3810 | −0.01589     | **−0.06089**   |  −150.70    |  −153.63     | −0.2410  |
| 2020-01-01..2021-01-01 (COVID)  |  2,536 | 0.4503 | +0.00093     | **−0.04407**   |  −111.76    |  −112.31     | −0.0824  |
| 2021-01-01..2022-01-01          |  2,487 | 0.4222 | −0.01496     | **−0.05996**   |  −149.13    |  −160.60     | −0.1069  |
| 2022-01-01..2023-01-01 (bear)   |  2,547 | 0.4688 | +0.01724     | **−0.02776**   |   −70.71    |  −106.14     | −0.0470  |
| 2023-01-01..2024-01-01          |  2,665 | 0.4334 | +0.00148     | **−0.04352**   |  −115.98    |  −120.03     | −0.1113  |
| 2024-01-01..2025-01-01          |  2,530 | 0.4198 | −0.02347     | **−0.06847**   |  −173.23    |  −180.86     | −0.1573  |
| 2025-01-01..2026-01-01          |  2,385 | 0.4423 | −0.02429     | **−0.06929**   |  −165.25    |  −167.12     | −0.1180  |
| 2026-01-01..2026-05-23 (YTD)    |    917 | 0.4297 | −0.03236     | **−0.07736**   |   −70.94    |   −71.58     | −0.1308  |

### Per-fold table — 30m cell

| Fold                            | n      | hit    | gross / sh   | **net / sh**   | total net   | max DD       | Sharpe   |
|:--------------------------------|-------:|-------:|-------------:|---------------:|------------:|-------------:|---------:|
| 2019-01-01..2020-01-01          |    996 | 0.3785 | −0.03257     | **−0.07757**   |   −77.26    |   −76.72     | −0.2433  |
| 2020-01-01..2021-01-01 (COVID)  |  1,071 | 0.4444 | −0.00025     | **−0.04525**   |   −48.47    |   −53.43     | −0.0644  |
| 2021-01-01..2022-01-01          |    921 | 0.4245 | −0.02869     | **−0.07369**   |   −67.87    |   −72.85     | −0.1022  |
| 2022-01-01..2023-01-01 (bear)   |  1,003 | 0.4726 | +0.01243     | **−0.03257**   |   −32.67    |   −53.78     | −0.0396  |
| 2023-01-01..2024-01-01          |    958 | 0.4426 | −0.00570     | **−0.05070**   |   −48.57    |   −60.58     | −0.1029  |
| 2024-01-01..2025-01-01          |  1,131 | 0.4182 | −0.04374     | **−0.08874**   |  −100.36    |  −102.34     | −0.1427  |
| 2025-01-01..2026-01-01          |    975 | 0.4431 | −0.01241     | **−0.05741**   |   −55.97    |   −64.34     | −0.0779  |
| 2026-01-01..2026-05-23 (YTD)    |    401 | 0.4489 | −0.00734     | **−0.05234**   |   −20.99    |   −26.37     | −0.0666  |

### Variant runs

Per spec: variants run only if at least one cell PASSES or is BORDERLINE
on the base case. **No cell met the borderline definition** (c2 between
1¢ and 2¢ with c1, c3, c4 all PASS). The four-condition bar requires
positive expectancy in 6 of 8 folds — every fold of every cell was
negative — so no cell is even close. Variants were **not** dispatched.

If a future investigation wants to revisit variants on the off chance
that FTFC alignment OR a higher confidence threshold dramatically
shifts the gross-expectancy distribution, the runner already supports
them via `python -m lib.exec_backtest.cli --mode=variants
--variants=v1_ftfc,v2_conf065,v3_target20 --cells=15m`. The
infrastructure is in place; only the dispatch is gated by the spec.

## Why this fails (diagnostic)

The model's high-confidence predictions are 2U / 2D **structure**
calls — "the next bar will print higher highs and not lower lows" — not
**magnitude** calls. At a 1.5R-target / 1R-stop and 30–60-min time
stop:

- The trigger bar's range *is* the risk unit. The target is 1.5× that
  range above (long) / below (short) the trigger high/low.
- Even when the model correctly predicts a 2U, the 2U may print by 1
  tick before reversing — that's a 2U for classification purposes but
  triggers a stop on this lifecycle.
- The model has no edge on the **distance the next bar travels**.
  Empirically: hit rate ~40% × 1.5R reward vs. 60% × 1R loss = 0
  expected R-multiples → gross PnL hovers at zero.

This is the gap the type model cannot fill. If the goal is to convert
the type model's classification edge into trading expectancy, the next
work would be a **direction-magnitude head** (already in flight per
parent commit `d295d8a strat_engine: direction-target model — binary
LightGBM on next_close > next_open`) or a **regime-conditional
filter** that learns *when* high-confidence 2U/2Ds resolve to enough
magnitude to clear friction. Both are out of scope for Track B.

## Reproducibility — dispatch the same run

```bash
# 1. Image (already built once for this track; tag uniquely so concurrent
#    tracks don't collide)
gcloud builds submit /tmp/build-context \
  --tag us-east1-docker.pkg.dev/$PROJECT/trading/trading-system:research-exec-backtest \
  --machine-type=e2-highcpu-8

# 2. Cloud Run Job (one-time create; idempotent re-runs via execute)
gcloud run jobs create exec-backtest \
  --image us-east1-docker.pkg.dev/$PROJECT/trading/trading-system:research-exec-backtest \
  --memory 8Gi --cpu 4 --task-timeout 5400 --max-retries 0 \
  --service-account trading-runner@$PROJECT.iam.gserviceaccount.com \
  --command python --args="-m,lib.exec_backtest.cli,--mode=base" \
  --set-secrets="DB_PASS=db-trading-pass:latest" \
  --set-env-vars "CLOUD_SQL_CONNECTION_NAME=$CONN,DB_USER=$USER,DB_NAME=trading,GCS_BUCKET=$BUCKET"

# 3. Execute
gcloud run jobs execute exec-backtest --region=us-east1 --async
```

Outputs land in
`gs://${PROJECT}-trading-data/research/exec_backtest/{execution_id}/`:
- `base_results.json` — nested per-cell + per-fold metrics
- `base_per_fold.csv` — flat per-fold table (the source of the tables
  above)
- `base_trades.csv` — full per-trade ledger (88,137 rows)

Snapshots for this run:
- Run ID: `exec-backtest-vfxqk`
- Wall clock: 7m37s (build context staging + image push not counted)
- Cost estimate: 4 vCPU × 8 GiB × 7.6 min ≈ $0.04 per backtest run
- Repo audit copies: `docs/exec_backtest_data/base_per_fold.csv`,
  `docs/exec_backtest_data/base_results.json`,
  `docs/exec_backtest_data/base_trades.csv.gz` (25 MB → 5.5 MB gzipped)

## Architecture (delivered code)

| File                              | Role                                                      |
|-----------------------------------|-----------------------------------------------------------|
| `lib/exec_backtest/engine.py`     | Hermetic per-setup trade lifecycle. No I/O.               |
| `lib/exec_backtest/runner.py`     | Per-cell walk-forward orchestrator.                       |
| `lib/exec_backtest/ftfc.py`       | Lightweight strat-candle FTFC weighted score (variant 1). |
| `lib/exec_backtest/cli.py`        | Cloud Run Job entry point.                                |
| `tests/test_exec_backtest.py`     | 9 hermetic unit tests (entry, exit, gap, costs, voiding). |
| `docs/exec_backtest_data/*.csv`   | Per-trade audit ledger (one row per executed trade).      |
| `docs/exec_backtest_data/*.json`  | Per-fold and per-cell results.                            |

The frozen type model code under `gcp/research/strat_engine/` was NOT
modified. The runner imports `featurize`, `make_lgbm`, and
`load_labeled_dataset` from the existing production modules.

## Caveats & assumptions

- **1m data quality**: IWM intraday 1m bars from
  `market_data_intraday_iwm` are RTH-only (09:30–15:59 ET, 817,841
  rows from 2018-01-02 onwards). Setups triggered late in the session
  whose lifecycle would extend past close exit at the final RTH bar's
  close (recorded as `time` reason).
- **Gap fills**: A 1m bar that opens past the trigger fills at
  bar.open ± slippage. We do NOT use bar.high (long) / bar.low (short)
  for gap fills — that would be optimistic.
- **Stop precedence on collision**: A 1m bar whose range covers BOTH
  the target and the stop is conservatively booked as a stop hit. This
  matches the spec's "conservatively assume STOP hit first" rule and
  is the right side to be wrong on for production trading. A
  Monte-Carlo sensitivity study would be a reasonable next step if
  this verdict ever wanted to be re-litigated; today it doesn't change
  the conclusion (gross expectancy is already negative on most folds,
  not just net).
- **Position sizing**: Fixed 1 unit per trade. No volatility scaling,
  no equity-curve compounding. Net expectancy is reported in $/share.
- **No FTFC for base**: The base case applies NO higher-TF filter.
  Variant 1 would have layered FTFC weighted alignment (15m + 30m +
  60m strat-candle classification), but base failed so variants did
  not run.
- **Reproducibility**: Cutoffs and trigger rule are deterministic;
  LightGBM's `random_state=42` is the only seeded stochasticity,
  matching the production training path. Re-running the Cloud Run
  Job from this image produces identical numbers.
