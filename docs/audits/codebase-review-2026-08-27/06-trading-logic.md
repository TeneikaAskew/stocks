# 06 — Trading Logic / Financial Correctness (whole repo)

**Result: 6 critical / 9 high / 8 medium.** Note:
`platform/src/lib/greeksCalculator.ts` no longer exists (deleted in
`6aa0afa`); BS math now lives in `lib/options_greeks.py` and was audited
there.

## CRITICAL

### T1 — `compute_gamma_flip_bs` fabricates flips out of float underflow
`lib/gamma.py:740-741,755-760`

`_crossings_at` treats `g1 == 0.0` as a zero-crossing. `bs_gamma` calls
`scipy.stats.norm.pdf(d1)`, which **underflows to exactly 0.0** for
deep-wing spots on short-dated contracts. The escalating search added in
#771 (`pcts = [search_pct, 0.25, 0.50]`) pushes the grid into that
region, and `min(crossings, key=|p-spot|)` then returns the boundary of
the underflow zone as "the true dealer-gamma zero".

Agent's local reproduction on a pure-put chain (no flip exists):
```
0DTE  pure-put -> gamma_flip = 424.5   # spot 600 => -29.25%
1DTE  pure-put -> gamma_flip = 424.5
23DTE pure-put -> gamma_flip = None    # correct
```
Grid diagnostics at ±50% on 0DTE: `exact-zero pts=159`, first at S=300.

> **VERIFIED BY CLAUDE — CONFIRMED IN PRODUCTION DATA.**
> Ran the agent's suggested query against `gamma_levels_eod`:
>
> | ticker | days | non-null flip | `|flip-spot|/spot > 20%` | max % from spot |
> |---|---|---|---|---|
> | IWM | 2682 | 2652 | **45** | +47.9% |
> | QQQ | 2679 | 2670 | **8** | +34.4% |
> | SPY | 2928 | 2917 | **1** | +21.7% |
>
> And the regime split is the smoking gun:
>
> | regime | days | wing artifacts |
> |---|---|---|
> | negative_gex | 5037 | **54** |
> | positive_gex | 3277 | **0** |
>
> **All 54 artifacts fall on negative-GEX days; zero on positive-GEX
> days** — exactly the regime-correlated signature predicted.
>
> **Scale, which the agent could not measure:** bucketing every
> non-null flip by distance from spot shows what the #771 escalation
> actually added —
>
> | band | days | % |
> |---|---|---|
> | within 10% (original search) | 7914 | 96.06% |
> | 10-25% (escalation tier 2) | 303 | 3.68% |
> | >25% (escalation tier 3) | 22 | 0.27% |
>
> So the escalation produced ~4% of all flips, of which 54 (0.65% of
> ticker-days) are clear artifacts.
>
> **Correction to the agent's conclusion:** it proposed this as "a
> concrete mechanism for the 15m/30m phase0 log-loss collapse". That
> attribution is **not supported** — the collapse was independently
> resolved earlier in this session as a calibration artifact (the July
> baseline run used `--calibration=isotonic`; my re-runs used the
> default `none`), and the isotonic re-run on rebuilt data reproduced
> July's fold metrics. A 0.65% contaminated tail cannot produce a
> uniform collapse across all 8 folds. **The bug is real and mine
> (introduced in #771); the causal claim about the magnitude model is
> not.**

**Fix direction:** drop the `g1 == 0.0` branch (or require `g2 != 0` and
a non-degenerate neighbourhood), and require `|G|` above a
scale-relative floor (e.g. `1e-9 × max|G|`) before accepting a
crossing. Reconsider the escalation itself — `None` on a genuinely
one-sided chain was the correct, informative answer.

### T2 — Walk-forward "out-of-sample" calibration is in-sample, and auto-writes production
`lib/walk_forward.py:301-380,577-607` + `scripts/run_param_sweep.py:188-206`

`_run_anchored_folds` records `train_start`/`train_end` in `fold_dates`
but **never trains on them** — :358 runs the engine on `test_df` only
with a fixed config. `walk_forward_sweep` runs that fold set for every
grid combo, and `select_calibration_winner:607` returns
`gated.loc[gated['avg_expectancy_pct'].idxmax()]` — the max over all
combos of a metric computed on the same folds it reports.
`run_param_sweep.py:196-217` then calls `apply_winner()`, writing
`call_target`/`put_target`/`call_time_stop`/`put_time_stop`/
`consecutive_periods` into `exit_config_overrides`, which
`signal_monitor.fire_alert:955-965` and `backtest._check_exit:850-860`
read **live**.

75-combo grid ⇒ ~2.2σ upward selection bias. The `stability_score>=0.6`
and `total_trades>=40` gates are computed on the same folds, so they
filter nothing about generalization. No holdout anywhere; winner ships
to live trading unreviewed.

### T3 — Backtest signals and fills are the same bar's close; zero slippage/commission
`lib/backtest.py:804,867-887`

`_check_entry` scores `row` (whose RSI/StochRSI/VWAP/Consecutive are all
functions of that bar's close), then sets `entry_price = row[close_col]`
(:804). `_check_exit` returns `close_price` for target (:868), stop
(:872), time-stop (:880), RSI (:885).
`grep -n "slippage\|commission\|fee" lib/config.py lib/backtest.py` →
**zero matches repo-wide.**

`ExitConfig` targets are 30-38 bps and stops 15-20 bps — an edge
measured entirely inside the unmodelled transaction-cost band.
Additionally `_check_exit` never inspects `row['High']/['Low']`, so
stops/targets are close-only: intrabar stop-outs invisible, intrabar
target touches missed. Not conservative in either direction.

### T4 — The live system has NO stop-loss; the backtest that validated it does
`gcp/signal_monitor.py:1328-1357` + `gcp/signal_monitor_eod_resolver.py:272-286`

`_check_exits` handles exactly four reasons: `fixed_horizon`,
`target_hit`, `time_stop`, `rsi_extreme`. `_detect_exit` mirrors it.
Neither has a stop branch. `lib/backtest.py:871-872` **does**:
`if unrealized <= -stop: return 'stop_loss'` with `call_stop=0.0015`,
`put_stop=0.0020`.

A CALL fires at 10:05, price drops 0.9% over 20 minutes: backtest closes
at −0.15%, live holds to the 30-minute time-stop and books −0.9% — 6×
the modelled loss. Every backtested expectancy, win rate, profit factor,
and the walk-forward objective in T2 are computed under a stop the live
system does not have. `ExitConfig.call_stop`/`put_stop` are defined and
validated in config but read by exactly one code path.

> **VERIFIED BY CLAUDE — CONFIRMED.** Every `exit_reason` assignment in
> `gcp/signal_monitor.py:1328-1357` enumerated: `fixed_horizon` (:1343),
> `target_hit` (:1346, :1353), `time_stop` (:1348, :1355),
> `rsi_extreme` (:1350, :1357). **No `stop_loss` branch exists**, and
> the Discord label map (:1400-1402) has no stop entry either.
> `lib/backtest.py:871-872` does have
> `if unrealized <= -stop: return 'stop_loss', close_price`.
> The divergence is exactly as described.

### T5 — `max_daily_trades=5` interacts badly with sizing; daily loss limit is structurally unenforceable
`gcp/signal_monitor.py:749-761,1101,1216-1226`

- **(a) `max_concurrent_positions` is dead code.**
  `grep -rn "max_concurrent_positions"` returns only `lib/config.py:235,
  634, 930` — definition, load, validation. Never read by signal_monitor
  or backtest. `_persist_signal_alert:1216` appends to a list with no
  length check.

  > **VERIFIED BY CLAUDE — CONFIRMED, and worse than stated.** A
  > repo-wide grep (excluding tests/`__pycache__`) returns exactly those
  > three `lib/config.py` lines and nothing else. Note the declared
  > **default is `1`** (`config.py:235`) — so the system's stated design
  > intent is *one position at a time*, while the code actually permits
  > `max_daily_trades` (5) concurrent positions per ticker, i.e. 15
  > across the watchlist. The gap between intended and actual risk
  > posture is 15×, not 5×.
- **(b) Sizing is per-trade fraction-of-equity**, so the cap permits 5×
  leverage on one ticker (0.25/0.50/0.75/1.00 sizes), 15× across the
  3-ticker watchlist.
- **(c) The daily loss limit only moves on exit.** `daily_pnl[ticker]`
  is written only at `_check_exits:1378-1380`. Five PUTs firing
  10:01-10:05 all stay open ⇒ `daily_pnl` is 0.0 ⇒ the −2% limit never
  binds; they resolve at time-stop for −0.9% each × 0.5 size = **−2.25%
  on one ticker**, discovered after the fact. The backtest never shows
  this because `run():532-543` resolves each trade before considering
  the next — strictly sequential by construction. Different risk
  topologies.
- **(d) `daily_loss_limit` is per-ticker, not portfolio** (`daily_pnl`
  is `{t: 0.0 for t in self.tickers}`, :143) — a "−2% limit" is −6%
  across three tickers.
- **(e) `daily_profit_target` is a fourth dead control — found by
  Codex, missed by all nine reviewers.** `lib/backtest.py:548` stops
  opening trades once `day_pnl` reaches the configured target; the live
  monitor never reads the setting, so it keeps adding exposure past the
  configured +3%.

  > **VERIFIED BY CLAUDE:** repo-wide grep for `daily_profit_target`
  > returns only `lib/config.py:237` (definition), `:493-494`
  > (validation) and `:638-640` (load). **Zero reads in
  > `gcp/signal_monitor.py`.** Same shape as (a) — a risk control that
  > exists in config and in the validating backtest, but not in the
  > system that trades. Any cap-decoupling work must treat
  > `max_concurrent_positions`, `daily_loss_limit` **and**
  > `daily_profit_target` as prerequisites.

> **Directly relevant to the cap question raised in
> `LIVE_PERFORMANCE_REVIEW_2026-08-27.md` §4.** That review treated the
> cap purely as a data-censoring problem; this finding shows the cap is
> also the *only* thing bounding concurrent risk, since
> `max_concurrent_positions` is dead. Any cap-decoupling work must
> preserve that, and should probably fix (a)-(d) first.

### T6 — Exhaustive in-sample mining with no OOS and no multiple-testing control
`scripts/analysis/phase4_setup_discovery.py:170-262`, `scripts/run_backtest.py:191-200`

`run_combinatorial_scan` enumerates every 2- and 3-way combination of
~10 feature groups across both directions on the **full sample**, keeps
everything with `win_rate>=0.65 & n>=30`, and presents them as
discovered setups. Search space ≈4,000+ hypotheses; under a fair coin
`P(X>=20 | n=30, p=0.5) ≈ 4.9%`, so ~200 spurious "65%+ setups" are
guaranteed. `grep -rn "p_value\|fdr\|bonferroni\|multipletests"
scripts/analysis/` → nothing. `split_by_period`
(`shared_utils.py:99-106`) returns `(full, recent)` where
`recent ⊂ full` — a 100%-overlapping subset, not a holdout.
`run_backtest.py --param-sweep` repeats this in the CLI;
`WalkForwardValidator` is imported in that file and simply not used.

## HIGH (abbreviated)

- **T7** `gcp/signal_monitor_eod_resolver.py:172-177,309,355,363-364` —
  exits priced off after-hours prints. Both fetchers set
  `extended_hours:'true'` and `_load_intraday_from_sql` applies no RTH
  filter, so `_eod_close_resolution:355` uses the **19:59 ET** print as
  `exit_price` while :363-364 hardcodes `exit_ts` to 16:00 ET — price
  and timestamp ~4h apart, from the thinnest tape of the day.
  `resolve_one:309` can fire `target_hit` at 18:30 on a ≤35-minute
  position. **Answers review concern #4:** the *formula* is consistent
  across all exit reasons (`_exit_return_pct`, direction-signed, always
  `bar['Close']`); the defect is which bar supplies the price.
- **T8** `lib/indicators.py:22-50` — RSI has no warm-up mask and
  `fillna(50.0)`; measured first 6 bars `[50, 100, 100, 100, 100,
  82.93]` with NaN count 0 (vs EMA14 13, MACD 25, BB 19). The resolver
  recomputes RSI on **one day's bars in isolation** while live uses an
  accumulated window — measured divergence 18.31 pts at bar 5, ~3 pts at
  bar 20, straddling the 80/20 `rsi_extreme` thresholds. Live and
  resolver therefore disagree on which alerts got an RSI exit, which the
  resolver docstring (:249-251) promises cannot happen.
- **T9** `lib/gamma.py:56-57,375,397` — GEX omits the ×100 contract
  multiplier that VEX includes. Reproduced: `code call_gex = 5,000` vs
  `canonical 500,000`, ratio 100.0, while `total_vex` = −40,000 does
  include it. Every "$ notional per 1% move" figure in the UI and the AI
  gamma analyst is **100× too small**, and GEX/VEX are not on the same
  scale despite being rendered side by side. Signs and rankings
  unaffected, so `regime` and the King/Gate taxonomy are safe.
- **T10** `lib/gamma.py:783-793` — `implied_move` has no √T term:
  `avg_vega * sqrt(252) * spot * 0.01` returns the same value for 1DTE
  and 300DTE. Reproduced: 57.15 (9.52% of spot) vs a true 30d move of
  25.80 (4.30%) — 2.2× overstated. Renders in the UI via
  `options.py:596` → `useOptionsGreeks.ts:43`. Correct form is
  `S·σ_ATM·√T`.
- **T11** `gcp/signal_monitor.py:1116,1324` — `datetime.now()` instead
  of `self._now()`, so in replay `elapsed_min` is execution wall-clock:
  `time_stop`/`fixed_horizon` can **never fire**, making replay P&L
  systematically optimistic. (Cross-confirmed by report 07 finding 18.)
- **T12** `gcp/research/magnitude_engine/mag_dataset.py:276-285` —
  same-day daily indicators broadcast onto intraday bars: AV
  `interval='daily'` ADX/MFI/Aroon/ROC/BBands for date D are computed
  from D's close, then merged onto every intraday bar of D whose label
  is the next intrabar move. Direct label leakage for phase2/phase4.
  The correct pattern exists two modules over
  (`p7_build_multi_tf_features.py:405-415`, `shift(1)`, commented
  "NO-LEAK FIX 2026-05-25"). **Any phase2/phase4 gate-pass on record
  should be treated as invalid until re-run.**
- **T13** `mag_pred_train.py:119` — `fillna(0)` on the whole feature
  matrix destroys signed-distance features where **0 is the most
  meaningful value** (`dist_to_balance_pct`, `dist_to_gamma_flip_pct`):
  missing gamma reads as "pinned at the flip". LightGBM handles NaN
  natively, so this discards correct missing-value handling.
- **T14** `lib/gamma.py:567-620` — **answers review concern #1.** Edge
  cases are handled correctly (single strike → the strike; zero total
  gamma → `None`; all-put symmetric chain → center). Two real defects:
  **(a)** the docstring's "half the mass below, half above" claim is
  false — center-anchored interpolation on strikes 100/110 with weights
  90/10 returns 101.0, i.e. 90/10 not 50/50 (defensible convention,
  wrongly documented); **(b)** it is a **net**-gamma median, so the
  classic max-pin strike (`call_gamma_oi = put_gamma_oi = 1e6`,
  `net_gamma = 0`) contributes **zero weight** and is invisible. A
  metric named "OI-weighted gamma median" that ignores the largest gamma
  node is mis-specified for its stated purpose. **(c)** `spot` is now
  unused, so the feature's meaning changed without its name changing.
- **T15** `lib/gamma.py:498` — parity spot omits discounting
  (`spot = k + c_mid - p_mid`). Reproduced at K=S=600, r=5%, T=30/365:
  estimate 602.46, error +0.41% — **2× the `SPOT_PROXIMITY_PCT=0.002`
  tolerance used to tag a strike "spot"**, so on any chain without
  `spot_override` the "spot" tag lands on the wrong strike and every
  `Level.distance_pct` shifts.

## MEDIUM (abbreviated)

T16 BS gamma in `lib/options_greeks.py:75-99` is **correct** (audited
per checklist), with the `_DEFAULT_RISK_FREE`/`_DEFAULT_DIV_YIELD`
Rule-3.7 caveat · T17 `GammaGridSummary.total_gex` is window-filtered
while `regime` uses the full chain (can report `+$2B` alongside
`negative_gamma`) · T18 `profit_factor` ignores `position_size` while
`day_pnl` applies it; `_aggregate_metrics` can produce
`avg_profit_factor = inf` · T19 `lib/strat.py:294-338` FTFC is a
weighted majority vote, not Full Timeframe Continuity — `1d=2U` alone
scores 0.30 and can be labelled bullish with zero actual continuity ·
T20 `p45_deep_ds_job.py:87-93` survivorship bias (hand-picked 2026
universe run against history; ETF path unaffected) · T21 **underlying**
returns recorded for an options product — `exit_return_pct` is the
direction-signed underlying move, and that is what T2's calibration
optimizes; `scripts/analysis/options_pnl_translation.py` exists to
bridge this and is not in the loop · T22
`mag_leakage_audit.py:65-97` **doesn't test what it claims** — the
docstring promises recomputing `atr_20` from raw OHLCV and comparing;
the code counts adjacent identical values and passes if <20%, so a
systematic one-bar-forward shift would be reported CLEAN · T23
`calculate_atr` has no `min_periods` (ATR20 14% high at bar 5) — matters
wherever ATR is computed per-session, since it is the magnitude label's
denominator · T24 premarket bars inside the RTH indicator window make
VWAP 04:00-anchored, and `Price_vs_VWAP` drives 2 of 5 scored
conditions · T25 `put_call_ratio` returns `0.0` when `call_oi == 0`
(should be ∞), and `total_vex:394` lets NaN vega through, breaking the
`sum(vex_by_strike) == total_vex` invariant.

## Verified clean

- **Magnitude label leakage (review concern #2) — none found.**
  `strat_dataset.py:212-224` uses `groupby(bar_date).shift(-1)` for
  session-aware TFs, each day's last bar dropped at :228, and
  `next_open/next_close/next_high/next_low` appear in **both** drop sets
  (`mag_dataset.py:427`, `mag_pred_train.py:107`). `atr_20` is a Wilder
  RMA through bar t — genuinely t-known.
- `p7_build_multi_tf_features.py:405-415` prior-day `shift(1)` — textbook
  correct EOD-options → intraday join.
- `gcp/premarket_brief.py` `BRIEF_AS_OF` uses strict `<` throughout; no
  as-of leakage.
- `lib/strat.py:83-126` candle classification matches the canonical
  Strat spec exactly.
- `lib/backtest.py:119-134` Sharpe annualization correct (`×√252`, one
  row per trading day, correct NaN/zero-std guard).
- Reproducibility — every `np.random`/model call in `lib/`, `scripts/`,
  `gcp/` is seeded.
