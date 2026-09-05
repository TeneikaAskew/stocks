# 02 — Rule 3.7 Silent-Fallback Sweep (whole repo)

Baseline: `docs/audits/FALLBACK_AUDIT_2026-05-13.md` (~121 catalogued).
Every finding below was re-verified against the current file, not copied
from the old inventory.

**Result: 2 CRITICAL new regressions, 4 CRITICAL confirmed backlog,
2 HIGH, 6 MEDIUM, 3 resolved-since-audit.**

> **⚠ CORRECTION (added after report 09 landed).** An earlier revision
> of this file stated that the `pred_bucket` consumer chain was not
> live because `MOVEMENT_STATEMENT_ENABLED` is "default-OFF and set
> nowhere in `gcp/deploy.sh`". **That was wrong.** The flag is set
> `true` at **`platform/deploy.sh:87`** — the frontend service's
> separate deploy script, which I had not grepped — and is confirmed
> live on the `solyra-api-prod` Cloud Run service. The
> `pred_bucket → size_class → stop distances` chain **is user-facing
> today**. See report 09 TIER 6 for the full correction and severity
> assessment. The `$100` spot reachability finding below is unaffected
> and was independently confirmed by report 09 TIER 5.

## CRITICAL — NEW

### C-N1 — Fabricated $100 underlying price
`platform/api/routers/grid.py:1090`
```python
spot = spot_est.price if spot_est.price > 0 else 100.0  # safe default
```
Pattern 4 (hardcoded financial constant). When spot estimation fails
this invents a **$100 underlying** and computes GEX against it — for
IWM/SPY/QQQ trading $200-650+ that is off by 2-7x (more if spot is
squared in the notional), silently rendered as real GEX. The same file
already has `_unavailable_envelope()` at :184, and `lib/gamma.py`'s
`estimate_spot` correctly returns `SpotEstimate(price=0.0,
method="none")` and bails — this endpoint just doesn't use either.
Introduced 2026-06-21 (`1c0523c`).

> **VERIFIED BY CLAUDE — with a material severity correction.**
> The line is verbatim correct (read `grid.py:1050-1105`). But the
> agent did not check reachability. This is inside the
> `GET /api/options/{ticker}/grid/timeseries` endpoint (`grid.py:903`),
> and `grep -rno "api/options/[^\"'\`]*" platform/src/` shows the
> frontend calls `/grid` and `/{date}/grid` but **never
> `/grid/timeseries`**. No user is seeing bad GEX from this today.
> Re-rate as **latent** — must be fixed before that endpoint is wired
> up, not an active incident. See report 09 (dormant surfaces).

### C-N2 — `or 0` on gamma and open_interest with no coverage gate
`platform/api/routers/grid.py:1058,1102`
```python
float(r["gamma"] or 0) * float(r["open_interest"] or 0)
```
Pattern 2 on two forbidden fields, plus an architecture violation
(CLAUDE.md: the app must never duplicate financial math — this
reimplements `lib.gamma.aggregate_by_strike` inline). `lib/gamma.py`
pairs the same idiom with `greeks_coverage()` gating that refuses the
summary on a vendor gamma outage (added 2026-08-26, `545fc17`); this
endpoint has **no coverage check at all**, so a partial vendor gap
silently deflates strike GEX. Same endpoint as C-N1, so the same
latency caveat applies.

## CRITICAL — confirmed backlog (unchanged since 05-13 audit, not regressions)

| ID | Location | Pattern |
|---|---|---|
| C-01 | `gcp/database.py:167-190` | `query_to_dataframe()` — `except Exception: return pd.DataFrame()`. Now documented in its own docstring as deliberate-for-legacy-callers, with non-swallowing `query_to_dataframe_strict()` available for new code. **Use the strict variant for anything new.** |
| C-02 | `lib/data_loader.py:78-87` | `_query_cloud_sql()` — same swallow stacked on C-01. Comment still diagnoses the 2026-05-04→08 `level_broken=0%` incident inline while the code still returns empty. |
| C-03 | `lib/options_greeks.py:104-148` | `get_rate_and_yield()` — `_DEFAULT_RISK_FREE=0.045` / `_DEFAULT_DIV_YIELD=0.013` returned on ImportError, query exception, or missing row. **Blast radius grew:** `lib/gamma.py:999-1004,1206-1211` (`compute_gamma_flip_bs`) now also calls it, so a FRED/`daily_rates` outage silently degrades the gamma-flip level too. Still no `daily_rates` staleness gate. |
| C-04 | `lib/signals.py:241-268` | `_latest_overrides()` malformed-JSON swallow + resolver-failure swallow whose comment reads *"degrade silently to Tier-B"*. This is the exact pattern behind the 2026-05-09 "95/98 IWM PUTs fired `above_vwap` despite live-disabled" incident. |

## HIGH

### H1 — NEW: `lib/agents/summarizers.py:547-565`
`calls["volume"].fillna(0)`, `df["implied_volatility"].fillna(0)`, OI
groupby `.fillna(0)`. Feeds the AI options-flow narrative (`avg_iv`,
max-pain proxy, P/C ratio) with no coverage gate. A **partial** IV gap
drags `avg_iv` toward 0 — missing-IV contracts contribute 0 to the
weighted numerator while their volume still counts in the denominator —
understating IV in generated text. Post-audit, not previously
catalogued.

### H2 — PARTIALLY REMEDIATED: `gcp/signal_monitor.py:433-513`
`refresh_level_map()` (audit C-06) still sets `level_maps[ticker] = None`
on both empty-df and exception paths, and `check_level_breaks` still
returns `[]` against a `None` map. **Improved since the audit:** explicit
`level_refresh_success_count` / `_empty_df_count` / `_exception_count`
counters plus `logger.exception` with traceback, matching the audit's
"increment a counter" remediation direction. Structural silent-`None`
remains; no typed `LevelMapStatus` sentinel yet.

## MEDIUM

- **M1 — `lib/gamma.py:276,348,452-456,702`**: `oi = opt.get("open_interest") or 0.0`
  in `aggregate_by_strike`, `aggregate_by_strike_expiration`,
  `put_call_ratio`, `compute_gamma_flip_bs`. This week's hardening added
  `greeks_coverage()` gating on **gamma** nullity but never extended it
  to **OI** nullity — a contract with real gamma but missing OI silently
  contributes zero weight to GEX/balance/flip. The one gap in an
  otherwise well-hardened module.
- **M2 — `gcp/signal_monitor.py:1321`, `gcp/signal_monitor_eod_resolver.py:254`**:
  `current_rsi = float(latest.get(rsi_col, 0) or 0)`. Does **not**
  currently misfire — the CALL branch needs `>= call_rsi_exit` (0 never
  triggers) and the PUT branch is defensively written as
  `elif 0 < current_rsi <= put_rsi_exit` (:1356). Fragile hand-rolled
  sentinel: missing RSI silently skips the check with no counter
  distinguishing "extreme" from "absent". Replace with explicit `None`
  + counter rather than relying on the `0 <` bound being copied
  correctly at every future call site.
- **M3 — `lib/strategies/mean_reversion.py:90,127` + `lib/signals.py:87,152`**:
  `int(row.get('Broke_Prev_Day_High', 0) or 0) == 1` (audit C-09),
  unchanged and now duplicated in two files. Missing level-break column
  reads as "not broken", suppressing signals instead of erroring.
- **M4 — `lib/indicators.py:49,84`**: `rsi.fillna(50.0)`,
  `stoch_rsi.fillna(50.0)` (H-01/H-02) — insufficient-warmup reads as
  neutral 50.
- **M5 — `lib/indicators.py:530`, `lib/trading_analysis.py:112`**:
  H-26/H-27 unchanged.
- **M6 — NEW: `lib/agents/ranker/signals.py:438,442`**: insider
  transaction `value.fillna(0)` — a transaction with missing
  `share_price` counts as $0, never reaching the "big transaction"
  threshold and deflating `total_value` in the ranker's insider score.

## RESOLVED since the 05-13 audit (positive findings)

- **C-05 fully closed** — `grep -rn "continue-on-error" .github/workflows/`
  returns **zero hits** repo-wide; the six offending fetcher workflows
  no longer exist as `.yml` (migrated to Cloud Run Jobs).
- **C-33 / H-25 fixed** — `platform/api/routers/dashboard.py:270`'s
  `or 0.0` is now immediately followed by `if live_price <= 0: return {}`
  (:271-272), so a missing quote bails instead of appending a synthetic
  $0.00 bar into the RSI/EMA series.
- **C-13 / C-14 were false positives** — in `lib/options_greeks.py` the
  `fillna(0)` appears only inside the `.where()` **condition**
  (`bid>0 & ask>0`); the selected value on the true branch is the real
  bid/ask average, false branch falls back to `last_price`.

## Reference-quality files (reviewed, zero violations)

`scripts/audit_data_freshness.py` (DataResult-style design),
`gcp/fetchers/fetch_av_realtime_options.py` (typed `UNAVAILABLE`
envelope, nothing fabricated).

## Remainder not individually re-verified this pass

~8 confirmed-backlog items (C-16..C-19, C-42..C-51 recommended for a
follow-up pass), 4 ML-offline `featurize()`-matrix `.fillna(0)` files
(training inputs, not price/signal outputs — the team has begun fencing
new columns away from this with explicit Rule 3.7 comments), 9
`scripts/` legacy CLI files, and 4 verified-legitimate display-layer
exemptions.
