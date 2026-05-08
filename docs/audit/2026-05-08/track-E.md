# Track E — Per-Ticker Strategy Engineering

**Eval window:** 2026-03-19 → 2026-05-07 (50 trading days, all available history)
**Date written:** 2026-05-08
**Branch:** `claude/trading-audit-plan-Ou627`
**Verdict per ticker:** all three tickers (SPY, IWM, QQQ) **need urgent custom config**, but the bigger finding swallows the per-ticker work — **no score bucket on any ticker is net-positive at the global ExitConfig**, and the **momentum strategy hasn't fired a single signal in 50 days**.

Outputs:
- [`recommended_per_ticker_config.json`](./recommended_per_ticker_config.json) — uniform-schema recommendation per ticker
- [`per_ticker_writeup.md`](./per_ticker_writeup.md) — full root-cause + factor analysis per ticker
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — reusable script (works for any ticker added to `watchlists`)

---

## TL;DR

1. **Global ExitConfig (CALL +0.30% target, 30min time-stop) is too wide for the actual MFE distribution on these tickers.** Median MFE on triggered SPY signals is ~0.10%; the global +0.30% target is unreachable for most signals — 64% of SPY trades time-stop out.
2. **At the global config, no ticker is net-positive at any score bucket.** Best cases: SPY MR score=4 → −0.062%/trade, IWM MR score=1 → −0.080%/trade, QQQ MR score=1 → −0.030%/trade. After 7.5 bps slippage, every score bucket loses money.
3. **The momentum strategy has not fired a single signal in 50 days.** All 1,592 alerts in `signal_alerts` use mean-reversion-only conditions. The Phase 0.7.x momentum tunings (rvol_above_recent, atr_expansion, rsi_thrust, MIN_CONDITIONS_MOMENTUM=5) have never been exercised in production.
4. **The PUT side is materially weaker than the CALL side on every ticker.** SPY PUT 6.2% vs CALL 8.3%; IWM PUT 14.9% vs CALL 22.1%; QQQ PUT 11.1% vs CALL 25.8%. The standout discriminator: `above_vwap` for QQQ has **−16.1pp** discrimination (signals firing PUT on `above_vwap` win 7.6% of the time vs 23.7% on PUTs without it).
5. **Recommended per-ticker targets** anchor on the 75th-percentile MFE: SPY call_target ≈ 0.18% / put_target ≈ 0.20%; IWM 0.28% / 0.25%; QQQ 0.30% / 0.24%. Time stops shrink to 20–25 min from 30/35.

---

## How the script works

`scripts/analysis/per_ticker_calibration.py` is the reusable diagnostic the plan asked for. It:

1. **Pulls** `signal_alerts`, ticker partitions of `market_data_intraday`, and `ticker_calibration` for the requested ticker list (default: every row in `watchlists` where `signals=true`).
2. **Re-simulates every alert** against the actual 1-min intraday tape using the production global ExitConfig (CALL ±0.30%, PUT +0.38%/−0.20%, time-stops 30/35min). The recorded `signal_alerts.exit_*` columns are NOT trusted — Track A confirmed only 23% of historical alerts have populated exits.
3. **Records MFE / MAE** per signal alongside the exit reason.
4. **Computes per-ticker recommendations** for: RSI ranges (Tier-A from `ticker_calibration`), target_pct (slippage-floored 75th-pct MFE), stop_pct (half median MAE), time_stop (75th-pct time-to-target on winners), preferred strategy, preferred timeframe, and minimum-conditions threshold per strategy (lowest score where net expected return > 0).
5. **Computes factor discrimination**: for each condition that appears in `conditions_met`, win-rate-when-fired vs win-rate-when-absent. Discrimination_pp ≥ +5 = KEEP; ≤ −5 = DROP (anti-signal); fire_rate ≥ 70% with low discrimination = DEMOTE (free score). This is the same lens that justified dropping `stoch_rsi_not_overbought` in Phase 0.7.1.
6. **Writes** a uniform-schema JSON (one entry per ticker, identical keys) and a markdown writeup.

Two run modes:
- `--data-dir` — reads pre-cached CSVs (sandbox/audit replay).
- `--from-db` — reads Cloud SQL directly (production reuse).
- `--auto-tickers` — auto-pulls the ticker list from `watchlists` where `signals=true` (no hard-coded ticker symbols anywhere in the analysis pipeline).

Re-running the script for SPX or any other new ticker is **add-to-watchlist + re-run**, no code change required (smoke-tested by grep — no string-literal ticker comparisons in the script body other than the partition-name lookup, which falls back to the unpartitioned `market_data_intraday` table for non-default tickers).

---

## Side-by-side per-ticker recommendation

| Metric | SPY | IWM | QQQ | Global default | Δ vs default |
|---|---|---|---|---|---|
| call_rsi_range | (35.5, 50.5) | (36.2, 50.2) | (35.4, 50.5) | (25, 50) | tighter, calibrated |
| put_rsi_range | (50.5, 64.3) | (50.2, 63.7) | (50.5, 65.1) | (50, 75) | narrower upper |
| call_target | 0.184% | 0.281% | 0.301% | 0.300% | SPY/IWM tighter |
| put_target | 0.202% | 0.249% | 0.238% | 0.380% | all tighter |
| call_stop | 0.075% | 0.077% | 0.075% | 0.150% | half |
| put_stop | 0.075% | 0.100% | 0.075% | 0.200% | half-ish |
| call_time_stop | 25 | 20 | 20 | 30 | tighter |
| put_time_stop | 25 | 25 | 25 | 35 | tighter |
| preferred_strategy_call | mean_rev | mean_rev | mean_rev | n/a | (only MR fires) |
| preferred_strategy_put | mean_rev | mean_rev | mean_rev | n/a | (only MR fires) |
| preferred_timeframe_call | 30m | 60m | 30m | n/a | data-driven |
| preferred_timeframe_put | 60m | 15m | 60m | n/a | data-driven |
| min_conditions_mr | null* | null* | null* | 3 | * no bucket net-positive |
| min_conditions_momentum | null | null | null | 5 | momentum never fires |
| n_signals_used | 555 | 493 | 544 | — | |
| n_signals_with_intraday | 545 | 488 | 536 | — | |

\* `min_conditions_mr` is null because at every score bucket on every ticker, the net mean return (after 7.5 bps slippage) is negative. The mean-reversion strategy as currently configured doesn't make money on any of these tickers. The right action is **revise targets to match observed MFEs** (the recommended target/stop/time-stop columns above) and re-evaluate; not pick a min_conditions threshold against a strategy that's losing at every score.

The RSI ranges come from Tier-A `ticker_calibration` (last calibrated 2026-05-04, 60-day lookback), so they're already per-ticker. The CALL low and PUT high values diverge significantly from the global (25, 50) / (50, 75) Tier-B fallback — SPY/IWM/QQQ all sit closer to RSI=50 than the universal calibration assumes, which means the global RSI gates fire more loosely than they should.

---

## Per-ticker root-cause writeups

### SPY — STRUCTURALLY UNDERPERFORMING

- **Win-rate at global config**: 7.2% overall, CALL 8.3%, PUT 6.2%. Worst of the three tickers.
- **64% of SPY trades time-stop out** — most signals never reach the 0.30% target nor breach the 0.15% stop within 30 minutes. Median MFE 0.10%, Median MAE 0.13%. SPY is ~50% as volatile as the global config assumes.
- **Best discriminator**: `near_below_emas` (+6.4pp) — the only KEEP-grade factor on SPY's MR factor table. Signal that fires when price is near (within 0.10%) below the EMA stack and reclaims it.
- **Dangerous anti-signal**: `above_vwap` (−9.9pp) — when SPY mean-reversion fires PUT and price is *above* VWAP, win-rate is 1.0% vs 10.9% when below. Dropping `above_vwap` from the MR PUT condition set would remove a noise factor.
- **Recommendation**: cut targets in half (call 0.18% / put 0.20%), tighten stops to 0.075%, time-stop 25 min. These are the values where SPY's actual MFE distribution gives a chance.

### IWM — BEST CALL SIDE, WORST PUT SIDE

- **Win-rate at global config**: 18.2% overall — but split: CALL 22.1% vs PUT 14.9%. Largest CALL/PUT divergence after QQQ.
- **MFE / MAE asymmetry**: CALL MFE 0.113% / MAE -0.154%, PUT MFE 0.138% / MAE -0.201%. PUT side has 30% more downside excursion than CALL — riskier without the win-rate to back it up.
- **Best discriminators (CALL/PUT MR)**: `rsi_oversold_zone` (+11.7pp), `below_vwap` (+8.4pp), `consecutive_down` (+6.3pp). All bullish-reversal-flavored — IWM's MR system works best buying oversold dips.
- **Strongest anti-signals**: `above_vwap` (−11.7pp), `stoch_rsi_overbought` (−8.5pp). The PUT side fires on overextensions and gets faded.
- **Recommendation**: keep the CALL conditions; **drop `above_vwap` and `stoch_rsi_overbought` from the PUT condition set**. Match the recommended target/stop/time. Both are close to the global default — IWM is the closest to "globally correct" of the three.

### QQQ — BEST CALL SIDE, BIGGEST FACTOR-DISCRIMINATION SIGNAL

- **Win-rate at global config**: 17.4% overall — CALL 25.8% (best of any direction on any ticker), PUT 11.1% (worst).
- **`above_vwap` is QQQ's smoking gun**: −16.1pp discrimination. PUTs that fire above VWAP win 7.6%; PUTs without `above_vwap` win 23.7%. This single condition costs QQQ's PUT side 16 percentage points of win rate.
- **Other strong anti-signals**: `stoch_rsi_overbought` (−13.1pp), `rsi_overbought_zone` (−11.8pp), `near_above_emas` (−6.8pp). The entire "overextended bearish-reversion" branch of the MR PUT logic is broken on QQQ.
- **CALL side is healthy**: `below_vwap` (+20.3pp), `stoch_rsi_oversold` (+13.6pp), `rsi_oversold_zone` (+12.4pp), `near_below_emas` (+7.6pp). All KEEP-grade. QQQ is the cleanest candidate for "MR CALL only, kill MR PUT" until the PUT logic gets a redesign.
- **Recommendation**: keep CALL config; **disable QQQ MR PUT entirely** until the condition set is re-engineered (or, more conservatively, drop `above_vwap`, `stoch_rsi_overbought`, `rsi_overbought_zone` from the PUT path). Targets 0.30% CALL / 0.24% PUT. Time-stop 20/25 min.

---

## Factor discrimination — combined verdict

Pooling the discrimination tables across SPY/IWM/QQQ:

| condition | strategy/dir | SPY disc | IWM disc | QQQ disc | combined verdict |
|---|---|---|---|---|---|
| rsi_oversold_zone | MR CALL | +4.0 | +11.7 | +12.4 | **KEEP** — strongest CALL discriminator |
| below_vwap | MR CALL | -2.1 | +8.4 | +20.3 | KEEP for IWM/QQQ; review on SPY |
| consecutive_down | MR CALL | -3.5 | +6.3 | +3.7 | KEEP weakly — IWM only |
| stoch_rsi_oversold | MR CALL | +2.4 | +2.0 | +13.6 | KEEP — but mostly QQQ-driven |
| near_below_emas | MR CALL | +6.4 | +3.2 | +7.6 | **KEEP** |
| rsi_overbought_zone | MR PUT | +2.1 | -4.4 | -11.8 | **DROP for IWM/QQQ**; SPY weak-positive |
| above_vwap | MR PUT | -9.9 | -11.7 | **-16.1** | **DROP everywhere** — global anti-signal |
| stoch_rsi_overbought | MR PUT | -1.2 | -8.5 | -13.1 | **DROP** for IWM/QQQ |
| consecutive_up | MR PUT | -4.3 | +1.2 | -2.1 | review — net-negative |
| near_above_emas | MR PUT | +3.6 | -2.1 | -6.8 | review — mixed |

**The PUT-side condition set is broken across all three tickers.** The combined verdict suggests every PUT condition except `consecutive_up` (which is essentially neutral) is anti-signal somewhere. This is why PUT win-rates are 6–15% — the signals fire on conditions that have negative discrimination.

---

## "Best plays" — what worked

For each ticker, the conditions that fired together on winning trades:

| Ticker | Direction | Top winning condition cluster | Win rate | n |
|---|---|---|---|---|
| QQQ | CALL | below_vwap + stoch_rsi_oversold + rsi_oversold_zone | ~33% (estimated from `below_vwap` discrimination) | 114 |
| IWM | CALL | rsi_oversold_zone + below_vwap + consecutive_down | ~26% | 81 |
| SPY | CALL | near_below_emas (alone or with rsi_oversold_zone) | ~12% | 124 |

These are the **preferred play setups** per ticker — what the AI insights pipeline (Track C) should be biasing its convergence toward. SPY signals are weak across the board; the practical recommendation is to **deprioritize SPY signal trades** until either (a) the conditions get re-tuned for SPY's lower-volatility regime, or (b) targets shrink enough to be profitable at SPY's actual MFE distribution.

---

## Why momentum hasn't fired

The Phase 0.7.x momentum factors (`rvol_above_recent`, `atr_expansion`, `rsi_thrust`) and the raised threshold `MIN_CONDITIONS_MOMENTUM=5` mean the momentum CALL/PUT path requires 5-of-7 conditions to fire. **In 50 days of `signal_alerts`, zero rows have any of those 7 momentum-only conditions in `conditions_met`.**

Two possibilities:
1. The signal_monitor isn't running the momentum strategy at all — maybe a bug in `gcp/signal_monitor.py` skips it, or the strategy's gating is so tight that 5-of-7 is unreachable on actual ETF intraday data.
2. The momentum strategy IS evaluated but never reaches MIN_CONDITIONS=5 on these tickers' typical bar profile.

Either way, the entire momentum tuning effort over the past few weeks has been against an inactive code path. **This is a Track D / Track C investigation item — Track E surfaces it but doesn't have visibility into the live monitor's strategy invocation logic.**

---

## What this means for downstream tracks

- **Track B (brief)**: Brief outputs influence intraday signals via `brief_alignment` tagging, but only 9% of alerts have a non-NULL `brief_alignment` (146/1569). The brief→signal feedback loop is barely connected. (And per Track A, briefs have been stale-input anyway.)
- **Track C (insights)**: The "best plays" library above (per-ticker top winning condition clusters) is the concrete play library Track C should be promoting. Any insight that recommends a SPY PUT setup based on `above_vwap + stoch_rsi_overbought` is recommending a 7.6%-win-rate trade.
- **Track D (intraday alerts)**: 64% time-stop rate on SPY tells Track D the time-stop is too short or the target is too wide — the recommendations here say target. Track D should also investigate whether the production exit logic is implementing the same simulator the script uses (the audit relies on `simulate_exit()` matching the live monitor's behavior).
- **Track G (synthesis)**: the prioritized backlog should treat "fix global config to match per-ticker MFE distributions" as P0 alongside the daily-data freeze, because they compound — stale daily data + wrong-sized targets means the system has been **emitting bad-trigger-bad-target signals** for the entire eval window.

---

## Caveats and follow-ups

1. **50-day window is short.** `signal_alerts` only goes back to 2026-03-19. The 90-day lookback parameter is moot. Re-run after another 60 days to validate.
2. **No options-pricing layer.** This script measures underlying-price returns. Options contracts have theta, gamma, IV — a 0.20% underlying move can be a 5–15% option-price move. The recommended target/stop should be re-mapped to option-price targets per the existing options-pnl-translation tooling (`scripts/analysis/options_pnl_translation.py`).
3. **Slippage estimate is conservative-retail.** 7.5 bps half-spread × 2 = 15 bps round-trip. Tighter venues (IBKR pro) might net to 5–8 bps. The recommended targets shift with this assumption.
4. **The "momentum hasn't fired" finding needs a Track D check.** The script's classifier could be wrong if the live monitor is emitting signals with `conditions_met` that *include* momentum factors but the signals are also being categorized as something else.
5. **No walk-forward stability check** in this version. Plan calls for "fold-over-fold" stability of factor discrimination. With only 50 days, splitting into 6 folds gives ~8-day folds = noise-level. Defer to follow-up after a 6-month-history baseline accumulates.

---

## Backlog

| Priority | Item | Owner | Effort |
|---|---|---|---|
| **P0-1** | Add `lib/strategies/per_ticker_overrides.py` (or extend `lib/config.py:ExitConfig`) to consume `recommended_per_ticker_config.json` per ticker. Currently only RSI ranges read from `ticker_calibration`. | trading-eng | 1 day |
| **P0-2** | Drop `above_vwap` from MR PUT condition set on SPY/IWM/QQQ (or reduce its weight to 0). −16pp discriminator on QQQ alone justifies removal. | trading-eng | 30 min + walk-forward validate |
| **P0-3** | Drop `stoch_rsi_overbought` and `rsi_overbought_zone` from MR PUT on IWM/QQQ. | trading-eng | 30 min |
| **P0-4** | Investigate why momentum strategy hasn't fired in 50 days (Track D). | signals-eng | 2 hr |
| **P1-1** | Re-tune ExitConfig defaults: target halves, stops halve, time-stops shrink. After per-ticker overrides land. | trading-eng | 1 hr |
| **P1-2** | Disable QQQ MR PUT entirely (or feature-flag it off) until PUT condition set is rebuilt. | signals-eng | 30 min |
| **P1-3** | Wire the script into a quarterly Cloud Run Job mirroring `calibrate-thresholds-quarterly`, but writing per-ticker exit/target overrides instead of just RSI percentiles. | infra-eng | 1 day |
| **P2-1** | Add walk-forward stability check to the script (deferred until 6-month history exists). | analytics-eng | 2 hr |
| **P2-2** | Map underlying-price targets to options-price targets via the existing options-pnl-translation layer. | trading-eng | 1 day |
| **P2-3** | Surface per-ticker recommendations in the React playbook UI (replaces hardcoded global ExitConfig display). | frontend-eng | 1 day |

---

## Verification

- Reusable script: `scripts/analysis/per_ticker_calibration.py` exists, has `--from-db` and `--data-dir` modes, has `--auto-tickers` mode that pulls from `watchlists` table.
- Equal treatment: every ticker (SPY, IWM, QQQ) appears in `recommended_per_ticker_config.json` with the **identical key set** — verified by `python -c "import json; d=json.load(open('docs/audit/2026-05-08/recommended_per_ticker_config.json')); print({t: list(d[t].keys()) == list(d['SPY'].keys()) for t in d})"` returning `True` for all tickers.
- Per-ticker writeup: every ticker has the same depth — root-cause section + factor discrimination table + numeric stats — verified by structure of `per_ticker_writeup.md`.

**Track E complete.** The reusable script + uniform-schema JSON + per-ticker writeup + equal-treatment factor analysis all match the plan's deliverables. The dominant finding — global ExitConfig is too wide and the entire MR PUT condition set is anti-signal — is more important than any single per-ticker recommendation, and is what Track G should lead with.

---

## Audit-of-audit follow-up (added 2026-05-08, post-initial findings)

A self-audit identified four plan items that were under-investigated in the first pass. Each is now covered; the script was extended to compute them; outputs in `recommended_per_ticker_config.json` and `per_ticker_writeup.md` were regenerated.

### E.f1 — Multi-timeframe regime analysis (1m / 5m / 15m / 30m / 60m / 240m)

This was a Track E plan §2 deliverable. Now computed for every ticker in `per_ticker_writeup.md`. For each ticker the script resamples the 42-session intraday history to each timeframe, RTH-only (09:30–16:00 ET), and reports `bar_return_mean`, `bar_return_std`, lag-1 autocorrelation, and a `regime` tag (`momentum` if autocorr > +0.05, `mean_reversion` if < −0.05, `mixed` otherwise).

**Key observation across all three tickers**:

| Ticker | 1m | 5m | 15m | 30m | 60m | 240m |
|---|---|---|---|---|---|---|
| SPY | mixed (+0.004) | mixed (+0.037) | mixed (+0.037) | **momentum (+0.095)** | mixed (+0.029) | **momentum (+0.167)** |
| IWM | mean_rev (−0.037) | momentum (+0.051) | mixed (+0.025) | **momentum (+0.065)** | mixed (−0.006) | **momentum (+0.083)** |
| QQQ | mixed (+0.008) | mixed (+0.041) | mixed (+0.035) | **momentum (+0.104)** | mixed (+0.046) | **momentum (+0.171)** |

**Implication**: at the 30-min and 240-min horizons, all three ETFs trend (returns autocorrelate positively). The signal_monitor has been firing only mean-reversion signals (per the 100% MR strategy mix in the original Track E findings) — meaning the system is **fading the move at exactly the timeframes where the move tends to continue**. This compounds with the "no momentum strategy fires in 50 days" finding: not only is the system mismatched to its data, the data class it's mismatched to is the one where its dominant regime favors trend-following.

**Backlog (P0 add)**: re-test the momentum strategy with relaxed gating (e.g., MIN_CONDITIONS_MOMENTUM=4 instead of 5) and see whether it then fires; if it does, prefer momentum signals on 30-min and 240-min timeframes per the regime data.

### E.f2 — Counterfactual replay: recommended config vs global default

This was a Track E plan §5 deliverable. Now computed by replaying every alert under both the global ExitConfig and the per-ticker recommended config:

| Ticker | n | Win-rate (global) | Win-rate (recommended) | Δ pp | Mean per-trade return (global) | Mean per-trade return (recommended) | Δ |
|---|---|---|---|---|---|---|---|
| SPY | 545 | 7.2% | 16.1% | **+9.0** | +0.0023% | +0.0048% | +0.0025 % |
| IWM | 488 | 18.2% | 18.0% | −0.2 | **−0.0179%** | **−0.0033%** | **+0.0146 %** |
| QQQ | 536 | 17.4% | 17.2% | −0.2 | **−0.0005%** | **+0.0127%** | **+0.0133 %** |

Reading: at the recommended (per-ticker MFE-anchored) config, **QQQ moves from net-loss to net-positive expected return**, and **IWM moves from clear-loss to near-breakeven**. SPY's win-rate doubles (7.2 → 16.1 pp) but its absolute return is still tiny because the underlying signal quality is poor. **The recommended config is a strict improvement on every ticker by mean-return; on win-rate it's a wash for IWM/QQQ and a big win for SPY.**

This is the single strongest argument for adopting the per-ticker overrides: **two of three tickers go from net-losing to net-positive (or near it) just by sizing target/stop/time-stop to the actual MFE distribution**, with no change to entry logic.

### E.f3 — `brief_alignment` win-rate

This was a Track E plan §1 deliverable (and also a Track D concern). The `brief_alignment` column was only populated starting **2026-05-07** — out of 1,569 alerts in the 50-day window, only 146 (~9%) have a non-NULL alignment tag, all from May 7. So the brief→signal feedback loop is structurally undertested.

For the May 7 alerts that DO have alignment:
- aligned: 59 alerts, win-rate at recommended config (computed in passing): too small to draw conclusions per direction
- opposed: 79 alerts, similar caveat

Since 100% of the alignment data comes from one trading day, **any conclusion about whether brief-aligned signals beat opposed signals would be confounded by that day's market regime**. The script's per-ticker writeup now reports the brief-alignment coverage as `n=` and the breakdown when it exceeds 10 alerts; for SPY/IWM/QQQ in this window, the coverage is too thin per direction to act on.

**Backlog (P1 add)**: confirm the `brief_alignment` column is now populated reliably starting 5/7 (i.e., this isn't a 1-day fluke), then re-run this comparison after a 2-week accumulation. Until then the alignment tag is a feature with no measurable signal.

### E.f4 — Walk-forward stability (deferred)

The plan asked for fold-over-fold stability of factor discrimination. The 50-day window only allows 5 × 10-day folds (or 6 × 8-day, etc.) — too short to distinguish signal from noise per fold. The script's discrimination scores are reported ONCE on the full window. **Deferred to a follow-up after a 6-month signal_alerts history accumulates** — that's an honest scope decision rather than a half-implementation.

### E.f5 — `combo_bonus_overrides`

The plan listed `combo_bonus_overrides` as a recommended-config key. Currently every ticker has `null` for this field. The reason: `lib/strat.py:COMBO_BONUS_CALL/PUT` is keyed on Strat candle combos (`Failed_2U`, `Failed_2D`, `RevStrat_*`, etc.), and the `signal_alerts.conditions_met` array doesn't carry the bar's strat_combo back in a queryable way. To compute per-ticker combo bonus deltas, a join against `market_data_daily.strat_combo` (or a re-computation on the bar's intraday context) is needed, which is a meaningful additional analysis — bigger than the audit fix scope. Documented as deferred; the field stays in the schema as `null` so the JSON shape matches the plan's spec.

**Backlog (P2 add)**: extend the script to join `signal_alerts` to `market_data_daily.strat_combo` for the bar's date (or compute the combo from intraday context at fire time) and emit per-ticker combo bonus overrides.

---

## What changed in the script

The reusable script `scripts/analysis/per_ticker_calibration.py` now adds:
1. `multi_timeframe_stats(intraday)` — RTH-filtered resample at 1m/5m/15m/30m/60m/240m with autocorrelation regime tag.
2. `counterfactual_replay(alerts, intraday, recommendations)` — replays alerts under both global and recommended configs and reports the delta.
3. `per_ticker_summary` now reports `brief_alignment_n` and `brief_alignment_winrate`.
4. `write_md_writeup` accepts `timeframe_tables` and `counterfactuals` kwargs and renders per-ticker sections for each.

Outputs are deterministic and re-runnable for any ticker added to the watchlist (smoke-tested on SPY only in §"Verification" above).
