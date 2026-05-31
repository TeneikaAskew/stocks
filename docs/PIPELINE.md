# Pipeline Architecture — Live vs Research

> Authoritative map of how the trading platform runs end-to-end: which jobs
> fire when, how data flows, and where the indicator-combination work (regime
> combos + Strat combos) plugs in. For the raw-data *fetcher* details see
> [`DATA_PIPELINE.md`](DATA_PIPELINE.md); this doc is the higher-level
> "how it all runs live" overview.

Last updated: 2026-05-31.

## TL;DR — there are two lanes, not one chain

A common misconception is that data flows in a single daily chain
(`intraday → indicators → strat engine → signal`). It does not. There are
**two independent lanes** that share one raw-data foundation and one math
library, but run on different cadences for different purposes:

| | **Lane 1 — LIVE TRADING** | **Lane 2 — RESEARCH / DISCOVERY** |
|---|---|---|
| Purpose | Fire actionable signals intraday | Find which patterns *have* edge |
| Cadence | Every trading day, intraday | Weekly / on-demand |
| Output | `signal_alerts` → Discord | ranked-combo tables, GCS model JSON |
| Places trades? | Yes (alerts) | No — informs Lane 1 |

The two lanes are deliberately decoupled: a research job crashing never stops
live signals, and a live-signal change never silently alters a backtest.

## The shared foundation (one source of truth)

```
RAW 1-min OHLCV  ──►  Cloud SQL: market_data_intraday  (SPY / IWM / QQQ)
   fetched by:
     • fetch-market-data-daily     23:00 UTC, Mon–Fri   (daily increment)
     • av-intraday-monthly          1st of month         (bulk AV 1-min backfill)
```

**One indicator engine, one Strat classifier.** Both lanes call the exact same
code, so live and research can never drift (CLAUDE.md "one source of truth for
math"):

- `lib/indicators.py : add_all_indicators` — the full indicator suite, **the
  single assembler**, decomposed into ~14 idempotent `_add_*` blocks. As of
  2026-05-31 the live `signal_monitor` calls the lean `add_signal_indicators`
  and the premarket brief calls `add_brief_indicators` — each runs only the
  blocks that capability reads, off the SAME block definitions, so values can't
  drift from the full engine (`add_all_indicators` output stays byte-identical,
  pinned by a 0.0-max-abs-diff parity test). `FEATURE_GROUPS = {signal, brief,
  regime, strat}` is the per-capability output-column contract; research/nightly
  paths still call `add_all_indicators`. It previously hand-rolled its own
  subset, which silently lagged the engine whenever a feature was added — that
  gap is now closed. Every indicator we use is computed in exactly one place.
- `lib/strat.py : StratClassifier` — candle classification (1 / 2U / 2D / 3).

Any feature added to `add_all_indicators` is automatically picked up by **every**
consumer (live monitor, research featurizer, both combo miners). This is why
promoting a candidate feature is a one-place change.

> ⚠️ **Persistence is separate from computation.** `add_all_indicators` is the
> single *compute* path, but the *persisted* feature tables
> (`market_data_daily`, `strat_features_<tf>`) write a fixed allow-list of
> columns — a newly promoted feature is computed everywhere but is **not**
> stored in those tables until its column is added to the schema + writer map +
> re-backfilled. Live firing and the brief use the in-memory computation, so
> they get new features immediately; historical SQL queries / model training on
> the feature tables do not until a backfill runs.

## Lane 1 — Live trading (daily)

```
market_data_intraday
        │
        ▼
signal-monitor                 09:25 ET, Mon–Fri   (gcp/signal_monitor.py)
  rolling 1-min window
  → add_signal_indicators      ← lean tier of the SAME engine (§ shared foundation)
  → StratClassifier            ← SAME classifier
  → strategy evaluation (momentum, agreement, brief-bias, levels)
  → fires signal_alerts + Discord webhook
        │
        ▼
signal-monitor-eod-resolver    16:30 ET, Mon–Fri
  → marks each alert win/loss after the close
```

Supporting live/daily jobs: premarket brief (08:20), premarket-playbook
resolver, insight pipeline, the many fetchers (options, FRED rates, economic
events, earnings, SEC filings, news sentiment, top movers). These enrich the
context the live monitor and brief consume. Full schedule lives in
`gcp/deploy.sh : deploy_schedulers()`.

## Lane 2 — Research / discovery

Two sub-tracks, both reading the same `market_data_intraday`:

### Track A — General regime combinations  *(Effort A)*

```
market_data_intraday
        │
        ▼
regime-combo                   Sunday 05:00 ET (weekly)   (gcp/regime_combo_job.py)
  load 1-min (trailing 365d)
  → add_all_indicators + add_candidate_features
  → lib/combo_mining            (mine_combos / model_lift)
  → regime_combo_results  table  (best combos per BIG / UP / DOWN / FLAT,
                                   per ticker × horizon 5/15/30/60, OOS hit×lift)
```

Sandbox/ad-hoc driver: `scripts/analysis/regime_combo_miner.py --ticker …`
(writes `reports/regime_combo_predictors_<ticker>.md`).

### Track B — Strat next-candle combinations  *(Effort B)*

The Strat engine is a 6-stage **research** pipeline (manual / on-demand via the
`strat-engine` Cloud Run Job — it is *not* scheduled). The featurizer aggregates
1-min bars into per-timeframe tables:

```
market_data_intraday
        │
        ▼
strat_data_builder             (on-demand)  1m → 5m/15m/30m/60m/4h
  → add_all_indicators + StratClassifier + levels/order-blocks
  → strat_features_<tf>  tables
        │
        ▼
strat-engine orchestrator      (manual, `--mode=full --ticker --tf`)
  Stage 1 verify ─► gate
  Stage 2 base-rates
  Stage 3  single-feature MI         (strat_corr_indicators.py)
  Stage 3b COMBINATION mining ◄──── EFFORT B   (strat_corr_combos.py)
           → lib/combo_mining, OOS combos per next-candle class → GCS JSON
           → NON-GATING (a 3b hiccup never blocks the model train)
  Stage 4 train + calibrate ─► THE gate
  Stage 5 FTFC assemble
  Stage 6 readout
```

Sandbox/ad-hoc driver: `scripts/analysis/strat_combo_miner.py --ticker … --tf 5m,15m,D`
(writes `reports/strat_combo_predictors_<ticker>.md`; daily bars via AV over HTTPS).

The shared label `next_bar_type` has ONE definition —
`strat_dataset.label_next_bar_type` (session-aware t+1) — used by both the
Cloud SQL path and the sandbox driver.

### Track C — Target-modular indicator correlation  *(2026-05-31)*

`indicator-correlation` (`gcp/indicator_correlation_job.py`) scores each
indicator against any of the four prediction targets the platform makes,
selectable via `--target` / `--targets` (env `INDICATOR_CORR_TARGETS`; default =
all four). All rows land in `indicator_correlation`, tagged by `target_name`
(+ `target_class` for the per-class metrics):

| `target_name` | Label source | Metrics |
|---|---|---|
| `forward_return` | forward returns per horizon | `pearson`, `rank_ic` (`target_class=''`) |
| `regime` | `regime_combo_miner.label_regimes` (BIG/UP/DOWN/FLAT) | per-class `mutual_info` + `class_lift` + `rank_ic` |
| `strat` | `label_next_bar_type` (1/2U/2D/3) | per-class `mutual_info` + `class_lift` + `rank_ic` |
| `signal` | `signal_alerts` win/loss at fire-bar | binary metrics over `FEATURE_GROUPS['signal']` (what the live monitor saw) |

Metric helpers reuse the label-agnostic `lib/combo_mining`. Per Rule 3.7 every
metric is `NULL` when unavailable — never `0`; `target_class` uses an
empty-string sentinel for the regression/overall row so the upsert dedups (NULLs
are distinct in a Postgres UNIQUE index). Bars are pulled once per ticker
(Rule 0: no per-row SQL). Runs on the **research image** (sklearn's
`mutual_info_classif` is excluded from the main image), same as `regime-combo`.
First run 2026-05-31 produced 3,016 rows across the four targets; top next-Strat
predictor was `Close_vs_Range` (rank_ic +0.465 for 2U / −0.466 for 2D).

## How research feeds back to live

Lane 2 produces **evidence**, not trades. The loop is:

1. Combo miners (A + B) surface indicator combinations with out-of-sample edge.
2. Repeated top-rankers across tickers/timeframes earn **promotion** of their
   underlying features into `lib/indicators.py` (measure-first gate).
3. Promoted features + validated combos inform the **Lane 1** strategy logic
   (`lib/strategies/`), which the live `signal-monitor` then fires on.

Example (2026-05-31): the measure-first study promoted `Realized_Vol_Short`,
`Mins_Since_Open`, `Price_vs_{EMA9,EMA20,VWAP}_ATR`, `EMA_Spread_ATR`,
`EMA9_Slope`, `BB_Squeeze`, `RSI_Divergence` — each a top OOS driver of BIG
moves and/or the next Strat candle across IWM/SPY/QQQ.

## Job inventory (combo-relevant)

| Job | Lane | Cadence | Entry point | Output |
|---|---|---|---|---|
| `signal-monitor` | Live | 09:25 ET daily | `gcp/signal_monitor.py` | `signal_alerts` |
| `signal-monitor-eod-resolver` | Live | 16:30 ET daily | `gcp/signal_monitor_eod_resolver.py` | win/loss |
| `regime-combo` | Research A | Sun 05:00 ET weekly | `gcp/regime_combo_job.py` | `regime_combo_results` |
| `strat-engine` (incl. Stage 3b) | Research B | manual | `…strat_orchestrator` | `strat_features_*`, GCS JSON |
| `indicator-correlation` | Research (research image) | manual/weekly | `gcp/indicator_correlation_job.py` | `indicator_correlation` (target-modular: forward_return / regime / strat / signal) |
| `fetch-market-data` | Foundation | 23:00 UTC daily | fetcher | `market_data_intraday` |
| `av-intraday-monthly` | Foundation | 1st monthly | fetcher | `market_data_intraday` |

## Folder conventions (prod vs research)

- `gcp/*.py` — **production** Cloud Run job entry points (scheduled / live):
  `signal_monitor.py`, `regime_combo_job.py`, `indicator_correlation_job.py`, …
- `gcp/research/strat_engine/` — the **active** research pipeline (Stages 1–6
  + 3b, featurizer, dataset).
- `gcp/research/_archive/` — **quarantined** dead research (the P7 modeling
  scripts; kept for methodology, never re-run / re-deployed).
- `scripts/analysis/` — sandbox-runnable **analysis drivers** that produce
  `reports/*.md` (the combo miners live here).
- `lib/` — the shared backend spine (indicators, strat, combo_mining, config).

Rule of thumb: if it's **scheduled or live**, it's a `gcp/*.py` job; if it
**discovers/explains**, it's research (`gcp/research/**` or `scripts/analysis/**`).
