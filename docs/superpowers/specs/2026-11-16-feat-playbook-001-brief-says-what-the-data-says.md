---
feat_id: FEAT-PLAYBOOK-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-003, REQ-FRESH-001, REQ-LLM-001, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "B1 gamma footer says what the snapshot is: tests/gcp/test_premarket_brief.py::TestGammaFooter passes on the pure formatter: a snapshot whose Eastern date is the brief's session date renders 'Live gamma' with its time; a REALTIME snapshot of Friday 2026-11-13 20:55:30Z on a brief for Monday 2026-11-16 renders 'Gamma as of Fri 11/13 15:55 ET' and never the word Live; an EOD snapshot renders 'Gamma as of Fri 11/13 close'; a snapshot more than one session old (by lib.eastern_time.previous_session, so a holiday is not a missed session) renders its age in sessions; fails on origin/main, where the first case and the second both render 'Live gamma · 15:55 ET' (gcp/premarket_brief.py:1977, _fmt_gamma_ts :1920-1935)"
  - "B2 the newest snapshot wins: tests/gcp/test_premarket_brief.py::TestGammaFooter::test_probe_takes_the_newest_snapshot passes with the two probe statements answered by a stand-in: given a REALTIME row at 2026-11-13 20:55:30Z and an EOD row at 2026-11-13 23:00:00Z, _load_gamma_freshness returns the EOD row with its session, and days_behind counted in exchange sessions for either kind; the read raising propagates as today; fails on origin/main, where the REALTIME row returns first with days_behind 0 (:163-190)"
  - "B3 TF bias prints the stored score: tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_score_prints_two_decimals passes: format_tf_bias(-0.30 / 0.40) is '-0.75', format_tf_bias(None) is 'unavailable', and the three render sites (gcp/brief_explanations.py:147, gcp/premarket_brief.py:2047 and :2213) call it; fails on origin/main, where '{score:+.1f}' prints -0.7 for the stored -0.75"
  - "B4 the overview is told what the candles are: tests/gcp/test_brief_overview_text.py passes: the user text explain_overview_setup builds holds, per ticker, the candle label of each timeframe in ftfc_labels with its meaning (IWM 2026-11-16: daily 2D down, weekly 1 inside and neutral, monthly 2U up) and macd_cross; the system prompt states the weights the score uses, read from StratClassifier.DEFAULT_WEIGHTS and not typed into the prompt (daily 0.30, weekly 0.10, monthly none), and that an inside or outside bar adds nothing to the score; a ticker with ftfc_labels missing sends 'unavailable', never a label; fails on origin/main, where the text holds score, FTFC state, price and RSI only (:183-186) and the prompt calls the score a vote of daily and weekly candles (:162-164)"
  - "B5 the overview cannot contradict the labels: tests/gcp/test_brief_overview_text.py::TestOverviewCheck passes on the pure function overview_conflicts(text, tickers): 'strong bearish alignment on the daily and weekly' against three tickers whose weekly label is 1 returns a conflict naming weekly; the same sentence with every weekly label 2D returns none; 'the monthly is bullish' with no 2U monthly returns a conflict; text naming no timeframe returns none; and explain_overview_setup returns the deterministic sentence built from the labels, logging the withheld text, when the model's text conflicts; fails on origin/main, where neither function exists"
  - "B6 RVOL against the prior 20 sessions: tests/lib/test_indicators.py::TestRvolPrior passes: lib.indicators.calculate_rvol_prior(volume, 20) is the last volume divided by the mean of the 20 values before it; on the 21 IWM daily volumes to 2026-11-13 written in the test it is 0.7324 where calculate_rvol gives 0.7577; with fewer than 20 prior values it is NaN; calculate_rvol, calculate_rvol_recent, calculate_rvol_vs_baseline and calculate_rvol_minute_of_day are byte for byte as on origin/main; and tests/gcp/test_premarket_brief.py::test_brief_rvol_uses_prior_sessions passes (the brief's rvol is calculate_rvol_prior's and is None, rendered as no RVOL text, when it is NaN); fails on origin/main (gcp/premarket_brief.py:1109-1111)"
  - "B7 a premarket extreme must be confirmed: tests/lib/test_premarket_print_filter.py::TestConfirmedExtremes passes on bars written in the test, after rules (a) and (b): pre_high is the greater of the second-highest surviving bar high and the highest surviving open or close, pre_low the mirror; one bar whose high stands alone above every other high and every open and close does not set pre_high, and the result carries confirmed {rule: 'two-bars-or-body-v1', raw_high, raw_low, high_bars_above, low_bars_below}; two bars at the same high set it; a bar that opens or closes at its high sets it; with one surviving bar the extremes are its open and close; pre_vwap, gap_pct and the rule (a) and (b) masks are as on origin/main; fails on origin/main, where pre_high is the maximum surviving high (lib/indicators.py:634-637)"
  - "B7b the misprint rule runs live, if its module is on main: when lib/bar_prints.py exists on the PR's merge base, tests/lib/test_premarket_print_filter.py::TestIsolatedPrintsLive passes: calculate_premarket_context calls lib.bar_prints.isolated_prints on the bars it was given, reads no table, drops the flagged side of each flagged bar before taking pre_high and pre_low, applies the confirmed rule of B7 only to bars whose judged value is false, and records the rule version and the flagged count in confirmed; when the file does not exist on the merge base, the PR body says so with the merge base's sha and git ls-tree output, and Design 4 'Order' step 2 stays open for its own spec"
  - "B8 the three writers record it: tests/gcp/test_premarket_filter_params.py passes with pre_filter_params of a written row holding the confirmed block of B7 for gcp/fetchers/fetch_market_data.py, gcp/fetchers/fetch_premarket_refresh.py and gcp/backfill_ticker.py, and gcp/schema.sql unchanged; and tests/lib/test_premarket_print_filter.py::TestSession20261116 passes on tests/fixtures/premarket_2026_11_16/ (the stored 04:00 to 09:30 ET one-minute bars of SPY, QQQ and IWM, exported read-only once the nightly has written them, with sources.json naming the db-query execution, the SQL and each file's sha256): for bars to each row's pre_fetched_at the raw highs are the stored 278.92, 754.377 and 681.022, and the confirmed highs and lows are the values read by hand from the fixture and written in the test; fails on origin/main"
  - "B9 a replay that writes nothing: tests/gcp/test_premarket_brief_no_discord.py::TestNoPersist passes: with --no-persist (or BRIEF_NO_PERSIST=true) main() runs against an engine stand-in that raises on any INSERT, UPDATE, DELETE or DDL and exits 0, posts nothing, and prints the brief JSON, the canonical rows build_persist_rows(brief) would write with their run_kind, and every Discord payload; persist_to_cloud_sql writes exactly build_persist_rows' rows when the flag is off (the existing persistence tests pass unmodified); --no-persist with BRIEF_RUN_SLOT=late or with --update exits 2 before any query; fails on origin/main, where BRIEF_AS_OF resolves allow_update True (:3589-3591) and upserts the canonical row as 'replay' (:3898, :3916-3918)"
  - "B10 the dry run can show the premarket fix: tests/gcp/test_premarket_brief_no_discord.py::TestPremarketFromBars passes: with --no-persist and BRIEF_PREMARKET_FROM_BARS=true the brief reads the session's stored one-minute bars up to the row's pre_fetched_at with one strict read per ticker, computes the snapshot with gcp.fetchers.fetch_market_data.premarket_snapshot, uses it in place of the stored pre_* values in memory, and prints stored and recomputed high and low side by side; without --no-persist the variable exits 2; a ticker with no stored bars for the session prints 'premarket bars unavailable' and keeps no recomputed value; fails on origin/main"
  - "B11 evidence in the PR body: the RVOL table of this spec re-run by grep on the PR head with every row's file and line; the brief for 2026-11-16 run locally with --no-persist over the B8 fixture, its overview, TF bias line, RVOL and call and put triggers beside the stored row's; and python3 -m pytest tests/lib/test_premarket_print_filter.py tests/gcp/test_premarket_filter_callers.py tests/lib/test_brief_planner_parity.py with every changed expectation listed and why"
  - "B12 records: 02-FEATURE-CATALOG FEAT-PLAYBOOK-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the (FEAT-PLAYBOOK-001, DASHBOARD-01) implementation-source note begins with the current source hash with this change's prose first and then 'Earlier:', scripts/maintenance/doc_source_snapshot.py verify accepts the regenerated record, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# Premarket brief: say what the data says (gamma footer, today's setup, RVOL, premarket high and low, and a replay that writes nothing)

## Authority and status

Draft, 2026-11-16. Not approved; no branch implements it before the owner approves it.

The owner (T, 2026-11-16) checked the 11/16 Discord output against market data and asked for the fixes, then a replay: "Once completed i want to CHECK IWM, QQQ, SPY against market again. And that will require a replay."

Decided by the owner on 2026-11-16:

- The live gamma fix: agreed.
- The TF bias rounding and the summary's inputs: agreed as proposed; the weights do not change.
- RVOL: "Fix rvol only after confirming industry standard calculation and whats done in all codebase".
- The premarket high: the spike filter is to be explained, with what each option does to the root cause (Problem 4).
- No exit-plan or target change here; a separate spec will cover targets.

## Scope

- Five corrections to the 08:30 ET brief (`gcp/premarket_brief.py`, `gcp/brief_explanations.py`) and to two `lib/indicators.py` functions it reads through, for SPY, QQQ and IWM and whatever else the brief lists.
- No trigger rule, target, stop, exit plan, weight or threshold changes, except the premarket high and low themselves (Design 4).
- One spec, one PR, under FEAT-PLAYBOOK-001.
- Code references are to `main` 4155a10f (2026-11-16), read for this spec. Every production number has its db-query execution beside it; every read was made without `--commit`.
- The brief of 2026-11-16 was written at 13:31:23Z, 08:31 ET (`premarket_analysis_history`, `cloud-scheduler:premarket-brief-daily`, db-query-nrfqn).

## Capability

- Catalog row FEAT-PLAYBOOK-001 (`docs/product/02-FEATURE-CATALOG.md:22`, record `:205-224`) lists `gcp/premarket_brief.py` under Code.
- Design 4 edits `lib.indicators.calculate_premarket_context`, which FEAT-STRAT-001's record lists (`:250`), and adds a rule to a definition an approved FEAT-STRAT-001 spec made (Design 4, "Approved specs this meets"). Decision 4 puts the filing to the owner.
- Requirements: REQ-PLAYBOOK-001, REQ-DATA-001 (no silent fallback), REQ-DATA-003 (a derived value records its rule), REQ-FRESH-001 (the footer), REQ-LLM-001 (the overview), REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002.

## Decisions for the owner

The owner's decisions above are written in. The rest are recommended; striking one changes only the sections named.

1. **TF bias prints two decimals** (Design 2). Recommended: `-0.75`, the value stored. Alternative: one decimal rounded half away from zero, `-0.8`.
2. **The monthly candle's weight stays none** (Design 2). Recommended: leave it. The weights are `lib/strat.py:131-140` (daily 0.30, weekly 0.10, no monthly key, so `weights.get(tf, 0.0)` at `:484` gives it 0); the score gates signals and feeds the insight's conviction, and FEAT-STRAT-001's legacy controls pin it. The overview will say the monthly is shown and not weighted. Alternative: a FEAT-STRAT-001 spec that weights it.
3. **RVOL: the brief only** (Problem 3, Design 3). Recommended: the brief's daily RVOL divides by the prior 20 sessions; no other computation changes. Alternative: change `calculate_rvol` for every consumer, which moves the signal gate's input and needs its thresholds measured again (Problem 3's table).
4. **Where the premarket rule is filed** (Design 4). Recommended: here, since it moved every call trigger on 11/16 and the owner asked for the brief's fixes as one. Alternative: its own FEAT-STRAT-001 spec, with this spec keeping Designs 1, 2, 3 and 5.
5. **The premarket rule: confirmed extremes now, the misprint rule run live when its module exists** (Problem 4, Design 4). Recommended as the owner framed it: option (1) is the durable path and option (2) the interim. Option (1) cannot read stored flags: `2026-11-16-feat-data-001-bar-misprint-flags-r2.md` (PR #1988) writes a morning's flags in its nightly pass inside the 21:00 ET fetch job (its decision 5 and Design 4, read on branch `origin/docs/spec-feat-data-001-bar-misprint-flags-r2`), after the 08:20 ET fetch and the 08:30 ET brief. So the premarket computation calls that spec's pure rule (`lib.bar_prints.isolated_prints`, Design 1) on the bars it already holds. That module is task 2 of that spec's plan and is not on main; until it is, the confirmed rule alone applies (Design 4, "Order").
6. **`--no-persist` writes no history row either** (Design 5). Recommended: a dry run leaves no trace in either table. Alternative: write the history row only.

## Problem

### 1. Gamma footer: "Live gamma · 15:55 ET" on Monday morning

- The footer of the 11/16 brief read "Live gamma · 15:55 ET". The snapshot was Friday's: the newest REALTIME rows of the three tickers are 2026-11-13 20:55:30Z, 15:55 ET (db-query-xgkkp).
- The probe returns the first REALTIME row dated before the session, within 10 days, as `data_source: realtime` with `days_behind: 0` typed in (`gcp/premarket_brief.py:163-190`). The 08:30 brief can never see a same-session REALTIME row: the query is `snapshot_date < :as_of`, and the day's first REALTIME snapshot is 14:30Z, 09:30 ET.
- The footer prints "Live gamma" for that tier (`:1977`) and `_fmt_gamma_ts` (`:1920-1935`) prints the time without the date for any hour from 04:00 to 20:59.
- A newer snapshot existed: the EOD chain of 2026-11-13 23:00:00Z (same execution). The EOD probe runs only when no REALTIME row is found (`:194-208`).
- The gamma tier is not stored: `premarket_analysis` has no `gamma_data_source` column (db-query-nrfqn's second statement failed on it). It lives in the brief's dict and the Discord footer only; no other module reads it (grep, run).

### 2. "Today's setup" contradicted the candles

- The overview called the daily and weekly strongly bearish. The stored labels for 11/16 are IWM `{"1d": "2D", "1w": "1", "1mo": "2U"}`, QQQ and SPY `{"1d": "2D", "1w": "1", "1mo": "2D"}`, with `ftfc_score` -0.75 and `macd_cross` Bullish for IWM (db-query-h2n49). Every weekly candle was an inside bar.
- The score: `calculate_ftfc` (`lib/strat.py:460-497`) adds the weight for 2U, subtracts it for 2D, and adds every labelled timeframe's weight to the denominator. Daily 2D and weekly inside: -0.30 / 0.40 = -0.75.
- It printed -0.7: 0.30 / 0.40 is 0.7499999999999999 in floating point and the three render sites format it `:+.1f` (`gcp/brief_explanations.py:147`, `gcp/premarket_brief.py:2047`, `:2213`).
- The overview model is sent, per ticker, the score, the FTFC state, the price and RSI (`gcp/brief_explanations.py:183-186`), and its prompt calls the score "a weighted vote of daily and weekly candle types" (`:162-164`). It is never sent the labels, so "-0.7 bearish" read as both timeframes down.

### 3. RVOL: what the codebase computes, and what the convention is

The brief showed IWM RVOL from 17,722,264 over a 20-day mean that includes that same day: 0.7577 (stored `rvol` 0.757652, db-query-h2n49). Against the 20 sessions before it: 0.7324 (db-query-kzjkd). SPY 0.825 against 0.803, QQQ 0.853 against 0.832.

Every RVOL computation found (grep over `lib`, `gcp`, `platform/api`, `scripts`, and solyra `src`, run on main 4155a10f):

| Where | Formula | Current bar in the average | Consumers and thresholds |
|---|---|---|---|
| `gcp/premarket_brief.py:1109-1111` | last daily volume / `rolling(20).mean()` last value | yes | the brief line (`:2029`, one decimal), `premarket_analysis.rvol` (`:3710`), read by `platform/api/routers/dashboard.py:145`, `:195`. No threshold |
| `lib/indicators.py:215-218` `calculate_rvol` | volume / `rolling(20, min_periods=1).mean()` | yes | column `RVOL` (`:1195`): `market_data_daily.rvol` (`gcp/database.py:1101`), the signal monitor's RVOL gate (`gcp/signal_monitor.py:104-116`, `:1479-1482`, `rvol_gate_min`), `rvol_minimum` 1.5 (`lib/config.py:483`), strategies (`lib/strategies/momentum.py:241`, `mean_reversion.py:180`), `lib/signals.py:413`, `lib/backtest.py:858`, feature builders (`gcp/research/p7_build_multi_tf_features.py:350`, `strat_engine/strat_data_builder.py:510`) |
| `lib/indicators.py:221-230` `calculate_rvol_recent` | volume / rolling 20 median | yes | column `RVol_Recent_20` (`:1198`), the `rvol_above_recent` condition |
| `lib/indicators.py:233` `calculate_rvol_vs_baseline` | bar volume / median volume at that minute over prior sessions | no | the intraday baseline; its docstring records why the rolling form is wrong intraday |
| `lib/indicators.py:297-313` `calculate_rvol_minute_of_day` | bar volume / mean volume at that minute over the frame | yes | research frames |
| `lib/trading_analysis.py:345-349` | volume / `rolling(20).mean()` | yes | `RVOL20` (`:788`); `:351` has an `exclude_current` form |
| `lib/agents/summarizers.py:1152-1153`, `:1629` | volume / `rolling(20).mean()` as `vol_ratio` | yes | analog matching in the insight bundle |
| `scripts/fetch_market_data.py:65`, `:272-273` | volume / 20-day and 10-day mean | yes | the legacy script's CSV |
| `platform/api/routers/live.py:545-553`, `:732-734` | today's volume / mean of the last 20 stored daily volumes | depends on whether today's row is stored; not read | the live page |
| `platform/api/routers/playbook.py:671-680` | `volumeToday / avgVolume20d`, both sent by the caller | caller's | playbook conditions "RVOL > N" |
| solyra `src/` | no RVOL arithmetic found; it passes `avg_volume_20d` through (`routes/LiveMarketPage.tsx:214`) | n/a | display |

The convention, as recalled and not re-read from the vendors' pages in this session: relative volume is the current period's volume over the average of prior periods. Finviz defines it as current volume against the 3-month average; TradingView's "Relative Volume at Time" and thinkorswim's compare with the same time on prior days; StockCharts describes volume against its moving average, which on a chart includes the current bar. Platforms differ on whether the current bar is in the average. Including it pulls the ratio toward 1 by construction: with N = 20, a true ratio r prints as 20r / (19 + r).

What the table shows is safe to change: the first row only. It has no threshold and one display. Every other row either feeds a gate or a trained feature (rows 2, 3, 7), is already prior-based (row 4), or is not the brief's. Changing row 2 would move the signal gate's input on every bar; its thresholds (1.0 in the gate's evidence, `lib/config.py:494-498`; 1.5 at `:483`) were measured on the current form.

### 4. Premarket high and low: what the spike filter does, and why 11/16 passed

**What it does today.** `premarket_print_filter` (`lib/indicators.py:661-710`) drops (a) any open, high, low or close equal to the prior close to the cent when the bar's midpoint is away from it, and (b) a bar's high (low) that lies more than k beyond the bar's own open and close and beyond the opens and closes of the two bars on each side, where k is `pm_spike_atr` times ATR (`:701-710`). `pre_high` is then the highest surviving high (`:634-637`). `pm_spike_atr` is calibrated per ticker.

**Why 11/16 passed.** k is in daily ATR units. From the stored rows (db-query-kzjkd):

| Ticker | `pm_spike_atr` | ATR(14) | k | stored `pre_high` | spikes dropped | prior-close prints dropped |
|---|---|---|---|---|---|---|
| IWM | 0.542 | 4.875 | $2.64 | 278.92 | 0 | 7 |
| QQQ | 1.073 | 16.338 | $17.52 | 681.022 | 0 | 16 |
| SPY | 0.942 | 11.036 | $10.40 | 754.377 | 0 | 9 |

The owner's check against the consolidated tape gave premarket highs of 276.90, 752.44 and 674.92. The prints that set the stored highs stood $2.02, $1.94 and $6.10 above those: under k every time. They became `PMK_H`, the call trigger, about 2 points too high on IWM and SPY and 6 on QQQ, and changed which targets were skipped.

**The root cause, plainly.** The vendor's one-minute bar takes its high and low from every print reported in the minute, including isolated off-market or late-reported ones. On 11/16 the 07:35 and 07:40 IWM bars printed 277.54, the prior close (rule (a) dropped 7 such prints). A one-minute OHLC bar cannot say which trade set its high, so no reader can recover the true high from that bar alone. A threshold only chooses how large a wrong print has to be before it is ignored.

**The options.**

| Option | What it does | Root cause or mask | What it cannot catch |
|---|---|---|---|
| (1) ignore the flagged side of a flagged bar (the misprint flags of PR #1988) | a rule on the minute's own scale (6 local ranges and 50 bp) marks the print; the premarket extremes skip marked sides | closest to the cause that bars allow: it judges the print against its own minute, not the day's ATR | a print within 50 bp (11/16: IWM's was about 73 bp, SPY's about 26 bp, so SPY's would not be flagged); three or more bad bars in a row; the last two bars before the fetch, which have no later neighbours. The stored flags of a morning are written at about 21:00 ET that night, so the 08:20 ET fetch must run the pure rule itself on the bars in memory |
| (2) a confirmed extreme: a price two bars reached, or a bar opened or closed at | one bar's lone wick cannot set the level | a mask: it does not say which print was wrong | a wrong price repeated in two bars; a real high touched by one wick only, which is then understated |
| (3) cross-check against a second source's consolidated premarket high and low | compares with the tape | the only one that addresses the cause | nothing in principle; no second source is connected to production |

Recommended (decision 5): (2) now, (1) when the flags and their consumers' spec exist. (3) needs a data source and is not specified here.

The 11/16 one-minute bars are not in `market_data_intraday` yet: the newest stored bar is 2026-11-14 01:00Z (db-query-nrfqn). The prints named above are the investigation's and the owner's; B8 tests the rule on the stored bars once the nightly has written them.

### 5. The replay cannot run safely

- `BRIEF_AS_OF=2026-11-16` suppresses Discord (`gcp/premarket_brief.py:4296-4312`) but resolves `allow_update` True (`:3589-3591`), stamps the canonical row `replay` (`:3898`) and upserts it over the day's live row on `(analysis_date, ticker)` (`:3916-3918`). History rows are always written.
- Live readers filter `run_kind = 'live'`, so after such a replay the dashboard, the movement statement and the insight's `read_live_level_basis` find no brief for 11/16.
- The brief reads `pre_high` and `pre_low` from `market_data_daily`, written at 08:20 ET, so a replay prints the stored 278.92 whatever the rule in `lib/` is.

## Non-goals

- No change to triggers' rule, targets, stops, exit legs, spacing, ATR levels or the level builder (`lib/strat_levels.py`). A separate spec covers targets.
- No change to FTFC weights, to `calculate_ftfc`, or to the stored `ftfc_score`.
- No change to `calculate_rvol` or any RVOL computation other than the brief's; no threshold change.
- No change to rules (a) and (b) of the print filter, to `pm_spike_atr`, to its calibration (`lib/level_calibration.py`), or to `gcp/schema.sql`.
- No reader of the stored misprint flags (`intraday_bar_flags`); that is the second spec PR #1988's spec names. Design 4's step 2 calls the pure rule only.
- No rewrite of stored premarket fields: `--recompute-premarket` on the daily fetcher exists for that and is not run here.
- No schedule, deploy or job-size change. No production write from the implementation PR.
- No change to the insight pipeline (its own spec, `2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`).

## Approaches considered

- Gamma: label by the snapshot's own date (chosen); or keep the tiers and only add the date to the time, which still calls Friday's snapshot Live.
- Overview: send the labels and check the text (chosen); or drop the model and always print the deterministic sentence, which is what the check falls back to; or prompt changes alone, which nothing verifies.
- RVOL: the brief only (chosen); every consumer (decision 3's alternative).
- Premarket: Problem 4's table.
- Replay: a no-write mode on the production job (chosen, CLAUDE.md 3.6); or a script that rebuilds the brief outside the job, which 3.6 forbids.

## Design

### 1. Gamma footer (`gcp/premarket_brief.py`)

- `_load_gamma_freshness` keeps its two single-row probes and their timeout, runs both, and returns the row with the greater `snapshot_ts`, with `market_session` and `days_behind` counted in exchange sessions (`lib.eastern_time.previous_session`) for both kinds.
- A pure `format_gamma_footer(snapshot_ts, market_session, session_date)`: "Live gamma · HH:MM ET" only when the snapshot's Eastern date is the session date; "Gamma as of Fri 11/13 15:55 ET" for an earlier REALTIME snapshot; "Gamma as of Fri 11/13 close" for an EOD chain; with "(N sessions old)" beyond one. The date is always printed unless it is the session's.
- With several tickers the footer describes the oldest snapshot, as today. No snapshot at all: no footer, as today.

### 2. Today's setup (`gcp/brief_explanations.py`, `gcp/premarket_brief.py`)

- `format_tf_bias(score)` in `gcp/brief_explanations.py` prints two decimals of the score rounded to two, and the three render sites use it.
- `explain_overview_setup` adds, per ticker, the labels by timeframe in words (2U up, 2D down, 1 inside and neutral, 3 outside and neutral in the score) and `macd_cross`. Both are already in the brief's dict (`gcp/premarket_brief.py:1238`, `:3698`).
- `_OVERVIEW_PROMPT` states the weights, formatted from `StratClassifier.DEFAULT_WEIGHTS`, that the monthly candle is listed and carries no weight, and that the score's sign is not a statement about any one timeframe.
- `overview_conflicts(text, tickers)`: split the text into clauses; in a clause that names daily, weekly or monthly with bearish, down or lower, at least one ticker must have 2D on that timeframe; with bullish, up or higher, 2U. A clause that names a ticker is checked against that ticker's labels. Any conflict: the brief prints the deterministic sentence ("IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75. ...") and logs the withheld text. No second model call.
- The weights, the score and the FTFC state are untouched.

### 3. RVOL (`lib/indicators.py`, `gcp/premarket_brief.py`)

- New `calculate_rvol_prior(volume, period=20)`: `volume / volume.shift(1).rolling(period, min_periods=period).mean()`, NaN where the mean is not positive or there are fewer than `period` prior values.
- The brief's `:1109-1111` calls it. NaN becomes `None`, and the line prints no RVOL text, as it does for `None` today (`:2029`).
- `premarket_analysis.rvol` holds the new value from the first brief after the deploy; the dashboard's briefing strip shows it. Earlier rows keep the old basis; nothing marks the change in the row (Risks).

### 4. Premarket high and low (`lib/indicators.py`)

- In `calculate_premarket_context`, after rules (a) and (b): `pre_high = max(second-highest surviving high, highest surviving open or close)`, `pre_low` the mirror, as B7 states. `pre_range_atr` follows from them; `pre_vwap` and `gap_pct` do not change.
- The result carries `confirmed {rule, raw_high, raw_low, high_bars_above, low_bars_below}`, and the three writers put it inside `pre_filter_params` (`gcp/schema.sql:1781-1782`, an existing JSONB column). `pre_excluded_spikes` keeps its meaning.

**Order (the dependency on PR #1988's spec).**

1. Interim, in this PR whatever else is true: the confirmed rule above (B7, B8).
2. Durable, once `lib/bar_prints.py` is on main (task 2 of that spec's plan; its tables, task 1, are not needed): `calculate_premarket_context` calls `lib.bar_prints.isolated_prints` on the premarket bars it was given, live, and drops the flagged side of each flagged bar before taking `pre_high` and `pre_low`, as rule (c). It reads no stored flag: the nightly pass that writes a morning's flags runs at about 21:00 ET, after the brief. The confirmed rule then applies only to the bars the rule did not judge (its `judged` array false, which includes the last bars before the fetch, since they lack later neighbours), and `confirmed.rule` becomes `isolated-print-v1+two-bars-or-body-v1` with the flagged count beside it.
3. Which PR carries step 2 is settled when the plan is written: this one if `lib/bar_prints.py` is on the merge base (B7b), otherwise its own approved spec after that module merges. This spec does not wait for it.

**Approved specs this meets.**

- `2026-11-07-feat-strat-001-one-level-source-r2.md` (approved, implemented) defines the premarket prints in its `done_when` ("drops, before taking pre_high, pre_low and pre_vwap, (a) ... and (b) ...", `:11`) and Design (`:244`). This spec adds a third step to that definition for `pre_high` and `pre_low`. It does not supersede that spec: rules (a) and (b), their masks and `pre_vwap` are unchanged, and the gate requires `supersedes` only where a plan would point at the replaced spec.
- `2026-11-10-feat-strat-001-per-ticker-params-r2.md` (`pm_spike_atr`, `pm_stale_print_atr`): unchanged; the calibration reads the (a) and (b) masks, which do not move.
- `2026-11-11-feat-strat-001-brief-atr-levels.md` and `2026-11-11-feat-strat-001-brief-exits-in-thirds.md` use `PMK_H` and `PMK_L` as the names of the premarket high and low and as rung anchors: the names and uses stand; the values under them change on a session with an unconfirmed print.
- `2026-11-14-feat-playbook-001-brief-late-slot.md` and `2026-11-14-feat-playbook-001-brief-market-date.md`: the late snapshot goes through the same function and gets the same rule.
- A stored `level_basis` keeps the premarket values it recorded, so a stored brief rebuilds as it was.
- Tests of those specs that assert a premarket high set by one lone wick change expectation; B11 lists each.

### 5. A replay that writes nothing (`gcp/premarket_brief.py`)

- `--no-persist` (env `BRIEF_NO_PERSIST=true`): implies no Discord; `persist_to_cloud_sql` is not called; `main()` prints the brief JSON (as today), the rows `build_persist_rows(brief)` returns, and the payloads (as the no-webhook path does today, `:4363-4367`). Exit 2 with the late slot or `--update`.
- `build_persist_rows` is the row-building half of `persist_to_cloud_sql`, moved out unchanged; the write half calls it.
- `BRIEF_PREMARKET_FROM_BARS=true`, valid only with `--no-persist`: per ticker one strict read of the session's one-minute bars from `market_data_intraday` up to the stored `pre_fetched_at`, through `gcp.fetchers.fetch_market_data.premarket_snapshot` (`:380`), with the parameters `pre_filter_params` recorded. The result replaces the stored `pre_*` values in memory only.
- The overview and per-ticker model calls still run in a dry run; they are part of what is being checked.

### 6. Capacity (CLAUDE.md rule 0)

| Run | Volume | Velocity | Wall-clock |
|---|---|---|---|
| scheduled brief | unchanged rows | one more single-row gamma probe per ticker when a REALTIME row exists (the EOD probe now always runs): 3 more round trips | 1.5 to 6 s more at 0.5 to 2 s a round trip; each probe is capped at 10 s (`:114`) |
| dry run with bars | at most 330 one-minute bars per ticker (04:00 to 09:30 ET) | one read per ticker: 3 | under 6 s more |
| premarket fetchers | the same bars; one sort more in memory | no new statement | not measurable |

- No new job, schedule or table. The job's timeout and memory (`gcp/deploy.sh:1382-1398`) were not read; the additions are seconds.
- Cost: no new scheduled work. A dry run is one brief execution with its model calls; the cost of one was not read.

## Implementation plan: size

10 tasks, one branch, one PR.

1. The gamma probe and `format_gamma_footer`, with tests.
2. `format_tf_bias` and the three render sites.
3. The overview's inputs and prompt.
4. `overview_conflicts` and the deterministic sentence.
5. `calculate_rvol_prior` and the brief's call.
6. The confirmed extremes in `calculate_premarket_context`, with tests on written bars.
7. The three writers' `pre_filter_params`, and the changed expectations of earlier tests.
8. `build_persist_rows` and `--no-persist`.
9. `BRIEF_PREMARKET_FROM_BARS`, and the 11/16 fixture once the bars are stored.
10. PR-body evidence, the site note, catalog and traceability.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes.

1. **Deploy** the brief job and the fetchers from `main` at or after the merge, with the `./gcp/deploy.sh` targets the plan names.
2. **Replay 2026-11-16 with no write**, on the owner's yes:
   `gcloud run jobs execute premarket-brief --region us-east1 --update-env-vars="^|^BRIEF_AS_OF=2026-11-16|BRIEF_NO_PERSIST=true|BRIEF_PREMARKET_FROM_BARS=true|BRIEF_TICKERS=SPY,QQQ,IWM" --wait`
   - Check, read-only, before and after: the three `premarket_analysis` rows of 11/16 are `run_kind` live with the same `analysis_ts`, and `premarket_analysis_history` has no new row.
3. **Check against market data**, on the owner's yes, for SPY, QQQ and IWM from the execution's log: the footer names Friday; the overview agrees with the labels; TF bias -0.75; RVOL 0.73, 0.83 and 0.80; the recomputed premarket high and low beside the stored ones and beside the consolidated values the owner has. Recorded on the PR.
4. **The first scheduled brief after the deploy**: its footer, overview and RVOL, and the `confirmed` block in that morning's `pre_filter_params`.
5. **Browser proof** for the dashboard's briefing strip (RVOL), by the owner as AGENTS.md defines.
6. On a `docs/` branch after the merge: the DASHBOARD-01 note and the plan's status.

The insight replay of the same day is in the insight spec's Close-out and needs the 11/16 brief row left live, which step 2 does.

## Risks

- **A real premarket high made by one wick is understated** by the confirmed rule, and the call trigger sits lower than the tape's high. How often is not measured.
- **A wrong price printed twice passes** the confirmed rule.
- **The calibrated parameters were measured on unconfirmed extremes.** Distances calibrated from history against `pre_high` and `pre_low` keep their values while the levels shift on affected sessions. Not measured.
- **`premarket_analysis.rvol` changes basis on a date** with nothing in the row to say so. Anything trending it across the deploy sees a step of a few percent.
- **The overview check is text matching.** It can pass a contradiction phrased without a timeframe word and can withhold a correct sentence built unusually. B5 pins the 11/16 sentence.
- **The footer will rarely say Live at 08:30**, since no same-session snapshot exists then. That is the truthful reading.
- **A dry run still calls the model** and still costs one brief's calls.
- **`BRIEF_PREMARKET_FROM_BARS` reproduces the 08:20 fetch only as far as the stored bars equal what the vendor served then.** The nightly refetch can differ.

## What was not verified

- The 11/16 premarket bars themselves: not stored yet (db-query-nrfqn). The 07:35 and 07:40 prints, the single prints behind the stored highs, and the consolidated values are the investigation's and the owner's, not read here.
- What the confirmed rule gives for 11/16: not computed, for the same reason.
- `lib.bar_prints.isolated_prints` on premarket bars: the module is not written. Its spec's prototype counted 15,996 extended-hours flag rows over the history (that spec, decision 3) and says they include real trades at another price; what it flags in a premarket session, and how often it would drop a real high, is not measured.
- The text of the 11/16 overview: not read from the row; the description of it is the owner's.
- The RVOL convention's sources: recalled, not re-read in this session.
- Whether `platform/api/routers/live.py`'s 20 stored days include today's row: not read. solyra's files that mention RVOL were listed, not each read.
- Which tests of the earlier specs change expectation under Design 4: not run.
- How `gcp/fetchers/fetch_market_data.py`'s `--recompute-premarket` cuts bars for a session, and whether cutting at `pre_fetched_at` matches it: not read.
- Whether `generate_premarket_brief` writes anywhere besides `persist_to_cloud_sql` (on-demand calibration, caches): not traced; B9's engine stand-in is what must show it.
- The brief job's timeout, memory and per-run cost: not read.
- That `--update-env-vars` on `jobs execute` applies to that execution only: taken from CLAUDE.md 3.5's recipe, not run.
- Whether a canvas depicts the brief: not opened.
