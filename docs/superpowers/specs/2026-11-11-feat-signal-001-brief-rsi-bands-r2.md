---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-DATA-002, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "tests/lib/test_strategies_calibration.py passes: with as_of the resolver reads only ticker_calibration rows dated on or before as_of (the SQL carries calibration_date <= :as_of on the drift_flagged query and on the legacy query) and measures the 180-day staleness against as_of, so a replay of 2026-05-04 uses the 2026-04-01 row and not a later one; without as_of the query, parameters and staleness are those of origin/main; resolve_rsi_bands returns the CALL band (p10, p50), the PUT band (p50, p90), each side's tier and the calibration date, and the Tier-B constants when no usable row exists; the as_of cases fail on origin/main"
  - "tests/gcp/test_premarket_brief.py passes: generate_premarket_brief resolves each ticker's bands once with as_of equal to the analysis date, passes them to check_call_conditions and check_put_conditions as rsi_range, and records rsi_call_band, rsi_put_band, rsi_band_tier and rsi_band_calibration_date on the ticker; a ticker with a Tier-A row (p10 35.0, p50 50.5, p90 65.0) and a latest daily RSI of 30 scores no RSI point on CALL where the hard-coded (25, 50) scored one, and a ticker with no row scores exactly as on origin/main; the tests fail on origin/main"
  - "The brief no longer calls check_call_conditions or check_put_conditions without rsi_range (an AST test over gcp/premarket_brief.py), and gcp/signal_monitor.py's calls to the resolver are unchanged"
  - "scripts/analysis/brief_rsi_band_experiment.py, run as this spec's Experiment section states, reproduces the Experiment table to the digit, and the implementation PR body carries that table and the per-ticker Tier-A rows it rebuilt"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-SIGNAL-001, DASHBOARD-01) note row carries that source_identity_sha256"
  - "The FEAT-SIGNAL-001 catalog record and the PR traceability entry are updated, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: docs/superpowers/specs/2026-11-11-feat-signal-001-brief-rsi-bands.md
---

# The premarket brief scores RSI against each ticker's calibrated band (revision 2)

## Authority

The owner approved the fix on 2026-11-11 ("Yes fix the holiday skip and RSI"), under two standing
rulings: values are never hard-coded and are tailored to the actual ticker, and a change is tested
against its hypothesis before it is swapped in. The experiment below is that test; its result is
neutral to slightly worse, so the owner decides at the merge whether to take the change. This spec is
not self-approved: it takes effect only when the owner merges the spec-only PR that adds it.

Revision 2 replaces the approved spec it names in `supersedes` (#1798) only in its Experiment
section: the experiment now scores the price-versus-VWAP factor as production does (see the
amendment note there). The design, done-when items, capacity and risks are unchanged.

## Problem

The brief scores CALL and PUT on the latest completed daily bar with
`check_call_conditions(latest)` and `check_put_conditions(latest)` (`gcp/premarket_brief.py:1265-1266`
on origin/main 300b40df), so the RSI factor always uses the function defaults, CALL (25, 50) and PUT
(50, 75) (`lib/signals.py:36`, `:101`), for every ticker.

Where per-ticker bands exist:

1. `ticker_calibration` (Cloud SQL), written quarterly (Jan, Apr, Jul, Oct 1, 02:00 ET) by the
   `calibrate-thresholds` job (`scripts/calibrate_thresholds.py`): Wilder RSI(14) percentiles p10 to
   p90 over the ticker's 1-minute closes for the 60 calendar days ending on the run date. Read by
   `lib/strategies/calibration.py` (Tier A: CALL (p10, p50), PUT (p50, p90); Tier B fallback: the
   `lib/strategies/config.py` constants (25, 50) and (50, 75); stale after 180 days; Tier B for a
   `drift_flagged` row). `gcp/signal_monitor.py:1103-1106` uses it. This is the authoritative
   per-ticker source.
2. `alert_config.json` `alerts.primary_call_alert.conditions.rsi_range` (45, 70) and
   `primary_put_alert` (30, 55): loaded into `SignalConfig.call_rsi_range` / `put_rsi_range` by
   `lib/config.load_config` (`lib/config.py:895-902`), but the file's own `_doc` calls it a legacy
   IWM-only template, it holds one band for all tickers, and neither the brief nor the monitor reads
   it. Not per-ticker; not used here.

The brief therefore ignores the per-ticker source the monitor uses, so the brief and the monitor can
score the same ticker's RSI differently.

## Non-goals

- No change to `check_call_conditions` / `check_put_conditions`, the other factors (StochRSI 30 / 70,
  consecutive periods, VWAP side, level breaks), the thresholds (setup 3, building 2) or the FTFC gate.
- No change to `scripts/calibrate_thresholds.py`, its schedule or the `ticker_calibration` schema; the
  Tier-B constants stay as the fallback the monitor already uses.
- No new `premarket_analysis` column: the band and its tier are on the brief's in-memory ticker
  record and in the job log, not persisted.
- `alert_config.json` is not edited.

## Approaches considered

1. Chosen: the brief calls the monitor's resolver, made point in time with an optional `as_of`, so
   live and replay briefs use the row in force on the analysis date (REQ-DATA-002) and brief and
   monitor agree (REQ-REL-001).
2. Read `SignalConfig` bands from `alert_config.json`. Rejected: one IWM template for all tickers.
3. Calibrate new daily-RSI bands for the brief (the Experiment's variant D). Not chosen: a new
   calibration method needs its own spec, and its result is mixed (better in the holdout, worse in
   the primary window).

## Design

`lib/strategies/calibration.py`:

- `_latest_calibration(ticker, as_of=None)`: with `as_of`, both queries add
  `AND calibration_date <= :as_of`, and staleness is `(as_of - calibration_date).days > 180`;
  without it, origin/main's queries and `date.today()`. The `lru_cache` key includes `as_of`.
- `get_call_rsi_range`, `get_put_rsi_range` and `get_resolution_tier` take an optional `as_of` and pass
  it through; the monitor's calls are unchanged.
- `resolve_rsi_bands(ticker, as_of=None) -> dict` with `call`, `put`, `call_tier`, `put_tier` and
  `calibration_date` (None for Tier B), built from one `_latest_calibration` call.

`gcp/premarket_brief.py`, per ticker, before scoring:
`bands = resolve_rsi_bands(ticker, as_of=analysis_date)`, then
`check_call_conditions(latest, rsi_range=bands['call'])` and
`check_put_conditions(latest, rsi_range=bands['put'])`; the ticker record gains `rsi_call_band`,
`rsi_put_band`, `rsi_band_tier` (`A`, `B` or `A/B` when the sides differ) and
`rsi_band_calibration_date`, and the job logs them. A failed `ticker_calibration` read raises, as in
the monitor (Rule 3.7), and a Cloud SQL configuration that is absent (local runs) gives Tier B.

Units: `ticker_calibration`'s percentiles are of 1-minute RSI; the brief scores daily RSI. The
experiment measures exactly this pairing, because it is what wiring the authoritative source means.

## Experiment

Hypothesis: per-ticker bands improve the brief's CALL/PUT selection over the hard-coded bands.

Data (read only, not in the repo): Alpha Vantage TIME_SERIES_DAILY_ADJUSTED, unadjusted OHLCV columns,
`/mnt/project-files/strat-verify/ftfc-replay/raw/{SPY,QQQ,IWM}_daily_adjusted.csv` (through
2026-11-04), and Alpha Vantage 1-minute bars, extended hours,
`/mnt/project-files/stocks-scorecard/inputs/bars_raw/{T}_1min_YYYY-MM.csv` (2025-03 to 2026-11-10).

Method: for each session D, the brief's own code on bars before D: `add_brief_indicators`,
`check_call_conditions` / `check_put_conditions` on the last row, `compute_strat_status` at 08:30 ET
on D (FTFC gate), `_resolve_signal_status` at the default thresholds. Variants differ only in the RSI
band: H hard-coded; A Tier A rebuilt point in time as `calibrate_thresholds.py` computes it (60
calendar days of 1-minute closes ending at 02:00 ET on each quarterly run date, the clock of the
`calibrate-thresholds-quarterly` scheduler in `gcp/deploy.sh`, so no bar the live job could not yet read
enters the band; run dates whose window the local history covers: 2025-07-01 to 2026-10-01; the latest run on or before D, at most 180 days old, else Tier B,
which equals H); D the same percentile rule over the ticker's own daily RSI for the 252 sessions
before D. Daily bars carry `Time`, as `lib.data_loader.load_daily` gives them, so VWAP and the
price-versus-VWAP factor score as in production. A call is any status other than `No signal`.
Same-day agreement: D's close versus D-1's close in the called direction (CALL up, PUT down). Next-day agreement: D+1's close versus D's close.

Command:

```
python scripts/analysis/brief_rsi_band_experiment.py \
  --daily-dir /mnt/project-files/strat-verify/ftfc-replay/raw \
  --minute-dir /mnt/project-files/stocks-scorecard/inputs/bars_raw \
  --out /tmp/rsi_exp
```

Result (calls, same-day agreement %, next-day agreement %):

| Window | Ticker | H | A (Tier A) | D (daily percentiles) |
|---|---|---|---|---|
| 2026-05-01 to 2026-11-04 | SPY | 67, 59.7, 52.2 | 58, 58.6, 51.7 | 67, 56.7, 46.3 |
| 2026-05-01 to 2026-11-04 | QQQ | 64, 62.5, 45.3 | 63, 61.9, 44.4 | 69, 56.5, 46.4 |
| 2026-05-01 to 2026-11-04 | IWM | 78, 56.4, 38.5 | 74, 56.8, 36.5 | 77, 50.6, 42.9 |
| 2026-05-01 to 2026-11-04 | all | 209, 59.3, 45.0 | 195, 59.0, 43.6 | 213, 54.5, 45.1 |
| 2025-03-03 to 2026-04-30 | SPY | 143, 45.5, 42.7 | 135, 46.7, 42.2 | 153, 49.0, 43.8 |
| 2025-03-03 to 2026-04-30 | QQQ | 149, 47.7, 51.0 | 140, 49.3, 50.7 | 152, 50.7, 50.0 |
| 2025-03-03 to 2026-04-30 | IWM | 171, 46.8, 45.0 | 170, 47.6, 45.3 | 166, 45.2, 48.2 |
| 2025-03-03 to 2026-04-30 | all | 463, 46.7, 46.2 | 445, 47.9, 46.1 | 471, 48.2, 47.3 |

Tier A changes the published status on 34 of 387 primary ticker-sessions and 70 of 879 holdout
ticker-sessions. The rebuilt Tier-A bands are nearly the same for all three tickers (p10 34.8 to
37.1, p50 49.6 to 51.2, p90 63.3 to 65.7), so they narrow both bands rather than tailor them.

Reading: the hypothesis is not supported. Tier A makes fewer calls (209 to 195, 463 to 445) with
about the same same-day agreement (59.3 to 59.0 in the primary window, 46.7 to 47.9 in the holdout);
next-day agreement is about equal in the holdout (46.2 to 46.1) and 1.4 points lower in the primary
window (45.0 to 43.6, under one binomial standard error at 195 calls). The owner decides whether that
is "worse".

Amendment: #1798's table loaded daily bars without the `Time` column that
`lib.data_loader.load_daily` carries, so `lib.indicators` added no VWAP and the scorers' fifth factor
(price versus VWAP) never scored (Codex review on #1808). The script now adds `Time`, as production's
loader does; the rebuilt Tier-A bands are unchanged, every variant makes more calls, and the reading
is the same.

## Capacity and cost

- **Volume:** one `ticker_calibration` row per brief ticker (the in-brief universe, under 20).
- **Velocity:** one query per ticker per run (`lru_cache` per process), the same shape the monitor
  already runs.
- **Wall-clock:** under 20 round trips at 0.5 to 2 s with pg8000 and the Cloud SQL connector, at most
  40 s on a job whose existing work is minutes; well inside its task timeout.
- **Cost:** $0 new; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/`, `scripts/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 shows
`premarket_analysis.signal_status`, which these bands change. Only the `(FEAT-SIGNAL-001,
DASHBOARD-01)` row of the Implementation-source notes table may describe this implementation, as
backend source and local tests only. After the merge, separately: fresh-clone identity check, DOC
main and staging close-out with real evidence, sidecar retirement, and the plan set to done on a
`docs/` branch.

## Risks

- **Fewer and different calls**, quantified above; the owner decides at the merge.
- **A `ticker_calibration` outage** stops the brief instead of falling back silently, as it stops the
  monitor's resolver today.
- **Unit mismatch** (1-minute percentiles on daily RSI) remains; a daily calibration would be a new
  spec.
- **Rebuilt, not read, Tier A.** The experiment rebuilds Tier A from extended-hours Alpha Vantage
  1-minute bars; production reads `market_data_intraday`, which may differ (session coverage, prints),
  so production's rows can differ slightly from the rebuilt ones. The quarterly drift guard is not
  modelled (a flagged row would be Tier B, equal to H).
- **The docs audit reads solyra's issues**; a session without solyra access cannot run it.
