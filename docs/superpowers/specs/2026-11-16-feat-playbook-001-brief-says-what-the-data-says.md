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
  - "B5 the overview cannot contradict the labels: tests/gcp/test_brief_overview_text.py::TestOverviewCheck passes on the pure function overview_conflicts(text, tickers): 'strong bearish alignment on the daily and weekly' against three tickers whose weekly label is 1 returns a conflict naming weekly; the same sentence with every weekly label 2D returns none; 'the monthly is bullish' with no 2U monthly returns a conflict; text naming no timeframe returns none; a claim about several tickers must hold for every ticker it describes: 'all three names are bearish on the weekly' with weekly labels 2D, 1 and 1 returns a conflict naming the two tickers that are not 2D, and none when all three are 2D; 'SPY and QQQ are bearish on the daily' with SPY 2D and QQQ 2U returns a conflict naming QQQ; a clause naming no ticker and no partial quantifier is read as about every ticker in the brief, and 'one of the three is bearish on the weekly' needs one; and explain_overview_setup returns the deterministic sentence built from the labels, logging the withheld text, when the model's text conflicts; fails on origin/main, where neither function exists"
  - "B6 one relative volume, in lib, and the brief shows it (stage 1): tests/lib/test_indicators.py::TestRelativeVolume passes: lib.indicators.relative_volume(volume, 20) is each bar's volume divided by the mean volume of the 20 bars before it, the bar itself excluded, and NaN with fewer than 20 prior bars or a mean that is not positive; on the 21 IWM daily volumes to 2026-11-13 written in the test its last value is 0.7324 where calculate_rvol gives 0.7577; calculate_rvol, calculate_rvol_recent, calculate_rvol_vs_baseline and calculate_rvol_minute_of_day return for the test's inputs exactly what they return on origin/main, because no signal consumer switches in this PR; and tests/gcp/test_premarket_brief.py::test_brief_rvol_is_relative_volume passes (the brief's rvol is relative_volume's last value and is None, rendered as no RVOL text, when it is NaN); fails on origin/main (gcp/premarket_brief.py:1109-1111)"
  - "B6b nothing new may be called RVOL: tests/meta/test_one_rvol_definition.py passes: a scan of lib, gcp, platform/api and scripts lists every function definition and every column or key assignment whose name matches rvol or vol_ratio in any letter case; each is lib.indicators.relative_volume, a value read from it, or a stage 2 entry listed in the test by file and name with the row of this spec's Problem 3 table beside it; an unlisted one fails, and a listed one that no longer exists fails until it is taken off the list, so the list only shrinks; fails on origin/main, where the file does not exist"
  - "B7 a premarket extreme must be confirmed: tests/lib/test_premarket_print_filter.py::TestConfirmedExtremes passes on bars written in the test, after rules (a) and (b) and the stale closing-price report rule of B7a: pre_high is the greater of the second-highest surviving bar high and the highest surviving open or close, pre_low the mirror; one bar whose high stands alone above every other high and every open and close does not set pre_high, and the result carries confirmed {rule: 'two-bars-or-body-v1', raw_high, raw_low, high_bars_above, low_bars_below}; two bars at the same high set it; a bar that opens or closes at its high sets it when it is not a thin bar (B7c); with one surviving bar the extremes are its open and close; pre_vwap, gap_pct and the rule (a) and (b) masks are as on origin/main; fails on origin/main, where pre_high is the maximum surviving high (lib/indicators.py:635-638)"
  - "B7c a thin bar sets no extreme (rule thin-bar-v1): tests/lib/test_premarket_print_filter.py::TestThinBar passes on bars written in the test: a bar whose volume is below pm_min_extreme_volume (100 shares, one round lot) gives none of its open, high, low or close to the extreme candidates, before the confirmed rule of B7 runs; the 2026-11-16 IWM 08:05 ET bar as Alpha Vantage returned it (open 276.4801, high 278.92, low 276.4801, close 278.92, volume 1) among bars trading 276.26 to 276.35 does not set pre_high, where B7 alone would accept it because it closes at its high; a bar of volume 0 with all four prices 277.54 does not set it either; the same bar at volume 100 does set it; when every surviving bar is thin, pre_high and pre_low are null and the result says why, never the thin value and never 0; pre_vwap and gap_pct are as on origin/main; the result carries thin {rule: 'thin-bar-v1', min_volume, bars_excluded}; fails on origin/main, where volume is not read for the extremes"
  - "B7a a stale closing-price report sets no extreme (rule stale-close-report-v1): tests/lib/test_premarket_print_filter.py::TestStaleCloseReport passes on bars written in the test, with rules (a) and (b) not running (ATR None) so the rule is shown to stand on its own: with prev_close 277.54, a bar with open 276.50, close 276.60 and high 277.54 does not set pre_high, counts through its body, and the result carries confirmed.stale_close_reports {rule: 'stale-close-report-v1', high: 1, low: 0, prior_close: 277.54}; the mirrored bar of a gap-up morning (open 279.10, close 279.00, low 277.54) does not set pre_low and counts {high: 0, low: 1}; the two are one parametrised test on mirrored bars, and every case below runs for both sides; a bar that opens or closes at 277.54 keeps that extreme; a high of 277.55 or 277.53 is kept; prev_close None runs nothing and records stale_close_reports None, never zeros; pre_vwap, pre_volume and gap_pct are as on origin/main; fails on origin/main, where with the filter not running a 277.54 high sets pre_high (lib/indicators.py:689-690)"
  - "B7b the misprint rule runs live, if its module is on main: when lib/bar_prints.py exists on the PR's merge base, tests/lib/test_premarket_print_filter.py::TestIsolatedPrintsLive passes: calculate_premarket_context calls lib.bar_prints.isolated_prints on the bars it was given, reads no table, drops the flagged side of each flagged bar before taking pre_high and pre_low, applies the confirmed rule of B7 only to bars whose judged value is false, and records the rule version and the flagged count in confirmed; a flagged print cannot come back through the bar's body: on a bar whose flagged high equals its own open or close to the cent, that open or close is left out of the extreme candidates as well, so the bar gives its other body value, or nothing when both equal the print, where origin/main's fallback would return the print (lib/indicators.py:635-636); the mirrored low cases run in the same parametrised test; and pre_vwap is unchanged by any of it; when the file does not exist on the merge base, the PR body says so with the merge base's sha and git ls-tree output, and Design 4 'Order' step 2 stays open for its own spec"
  - "B8 the three writers record it: tests/gcp/test_premarket_filter_params.py passes with pre_filter_params of a written row holding the confirmed block of B7 and B7a for gcp/fetchers/fetch_market_data.py, gcp/fetchers/fetch_premarket_refresh.py and gcp/backfill_ticker.py, and gcp/schema.sql unchanged; and tests/lib/test_premarket_print_filter.py::TestSession20261116 passes on tests/fixtures/premarket_2026_11_16/ (the stored 04:00 to 09:30 ET one-minute bars of SPY, QQQ and IWM, exported read-only once the nightly has written them, with sources.json naming the db-query execution, the SQL and each file's sha256): for bars to each brief row's recorded level_basis.premarket.fetched_at the raw highs are the stored 278.92, 754.377 and 681.022, and the confirmed highs and lows are the values read by hand from the fixture and written in the test; fails on origin/main"
  - "B8b rates never mix the old and the new extreme rule: LEVEL_RULE_VERSION becomes 'feat-strat-001.v4' and every basis built under the new premarket rules records it; tests/lib/test_movement_statement.py::test_reach_rates_do_not_mix_rule_versions passes: with resolved rows of v3 and of v4 in the population, the rate of a v4 session's rung counts v4 rows only and a v3 session's counts v3 rows only (lib/movement_statement.py:286-349 selects by level_basis.rule_version); and tests/lib/test_strat_levels.py::test_v3_basis_rebuilds_as_on_main passes: SessionLevels.from_basis of a stored v3 basis returns the picks it returns on origin/main, since v3 and v4 share the pick rule and differ only in how the premarket high and low were taken; fails on origin/main, where the version is v3 (lib/strat_levels.py:1516) and from_basis would rebuild anything that is not the current version under the v2 rule"
  - "B9 a replay that writes nothing: tests/gcp/test_premarket_brief_no_discord.py::TestNoPersist passes: with --no-persist (or BRIEF_NO_PERSIST=true) main() runs the whole brief, generate_premarket_brief included, against an engine stand-in that records every call and returns normally, and the test asserts on the record, not on survival: no statement other than a SELECT was executed on any SQLAlchemy connection or DBAPI cursor, commit was never called, and gcp.database.execute_sql, gcp.database.upsert_dataframe, lib.strat_levels.persist_level_map and _delete_null_close_rows were each called zero times; the fixture includes a ticker with a null-close placeholder row and a ticker with a level map, the two paths that write on origin/main; main() exits 0, posts nothing, and prints the brief JSON, the canonical rows build_persist_rows(brief) would write with their run_kind, and every Discord payload; persist_to_cloud_sql writes exactly build_persist_rows' rows when the flag is off (the existing persistence tests pass unmodified); --no-persist with BRIEF_RUN_SLOT=late or with --update exits 2 before any query; fails on origin/main, where BRIEF_AS_OF resolves allow_update True (:3589-3591) and upserts the canonical row as 'replay' (:3898, :3916-3918), generate_premarket_brief commits a strat_levels upsert (:1470-1475) and can delete market_data_daily rows (:1032, :242-270), and both swallow their errors (:1488, :242-270), so a stand-in that raises would prove nothing"
  - "B10 the dry run can show the premarket fix: tests/gcp/test_premarket_brief_no_discord.py::TestPremarketFromBars passes: with --no-persist and BRIEF_PREMARKET_FROM_BARS=true the brief reads the session's stored one-minute bars up to the cutoff the original brief recorded, level_basis.premarket.fetched_at of the session's live premarket_analysis row, with one strict read per ticker, computes the snapshot with gcp.fetchers.fetch_market_data.premarket_snapshot, uses it in place of the stored pre_* values in memory, and prints stored and recomputed high and low side by side with the cutoff used; in a case where market_data_daily.pre_fetched_at was rewritten after the brief (the nightly, or a later refresh) and bars exist between the two times, the later bars are not read and the recomputed values equal those from the brief's cutoff; a session with no live brief row, or a row whose level_basis has no premarket.fetched_at, prints 'premarket cutoff unavailable' and keeps no recomputed value, never the daily row's time; without --no-persist the variable exits 2; a ticker with no stored bars for the session prints 'premarket bars unavailable' and keeps no recomputed value; fails on origin/main"
  - "B11 evidence in the PR body: the RVOL table of this spec (Problem 3) re-run by grep on the PR head with every row's file and line and its stage, and B6b's list beside it; the brief for 2026-11-16 run locally with --no-persist over the B8 fixture, its overview, TF bias line, RVOL and call and put triggers beside the stored row's; and python3 -m pytest tests/lib/test_premarket_print_filter.py tests/gcp/test_premarket_filter_callers.py tests/lib/test_brief_planner_parity.py with every changed expectation listed and why"
  - "B12 records: 02-FEATURE-CATALOG FEAT-PLAYBOOK-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the (FEAT-PLAYBOOK-001, DASHBOARD-01) implementation-source note begins with the current source hash with this change's prose first and then 'Earlier:', scripts/maintenance/doc_source_snapshot.py verify accepts the regenerated record, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Premarket brief: say what the data says (gamma footer, today's setup, RVOL, premarket high and low, and a replay that writes nothing)

## Authority and status

Approved by the owner (T) on 2026-11-16. After reviewing the fixes the owner said "Continue working, keep it moving", having said "I approve ... any others that need to be approved to move forward". The numbered recommendations under "Decisions for the owner" stand as written unless the owner strikes one.

The owner (T, 2026-11-16) checked the 11/16 Discord output against market data and asked for the fixes, then a replay: "Once completed i want to CHECK IWM, QQQ, SPY against market again. And that will require a replay."

Decided by the owner on 2026-11-16:

- The live gamma fix: agreed.
- The TF bias rounding and the summary's inputs: agreed as proposed; the weights do not change.
- RVOL: "Fix rvol only after confirming industry standard calculation and whats done in all codebase", and then: "We need to get on one page and one calculation on rvol." One definition for the whole codebase, staged (Problem 3, Design 3).
- The premarket high: the spike filter is to be explained, with what each option does to the root cause (Problem 4). The owner's questions on the stale prints are answered there in plain words, and a named rule for closing-price reports is added beside the confirmed-extreme rule, for the high and the low alike.
- No exit-plan or target change here; a separate spec will cover targets.

## Scope

- Five corrections to the 08:30 ET brief (`gcp/premarket_brief.py`, `gcp/brief_explanations.py`) and to `lib/indicators.py` (one new function, `relative_volume`, and the premarket context), for SPY, QQQ and IWM and whatever else the brief lists.
- No trigger rule, target, stop, exit plan, weight or threshold changes, except the premarket high and low themselves (Design 4) and the level rule's version label that marks them (B8b).
- RVOL is staged. This PR is stage 1: the one definition lands in `lib` and the brief shows it. No signal consumer, threshold or stored signal column changes here; each switches in its own stage 2 PR with a replay comparison (Design 3).
- One spec, one PR, under FEAT-PLAYBOOK-001.
- Code references are to `main` 4155a10f (2026-11-16), read for this spec; Problems 3 and 4, Designs 3 to 5 and the review fixes were read again on `main` 060c89a0 the same day. Every production number has its db-query execution beside it; every read was made without `--commit`.
- The brief of 2026-11-16 was written at 13:31:23Z, 08:31 ET (`premarket_analysis_history`, `cloud-scheduler:premarket-brief-daily`, db-query-nrfqn).

## Capability

- Catalog row FEAT-PLAYBOOK-001 (`docs/product/02-FEATURE-CATALOG.md:22`, record `:205-224`) lists `gcp/premarket_brief.py` under Code.
- Design 4 edits `lib.indicators.calculate_premarket_context`, which FEAT-STRAT-001's record lists (`:250`), and adds a rule to a definition an approved FEAT-STRAT-001 spec made (Design 4, "Approved specs this meets"). Decision 4 puts the filing to the owner.
- Requirements: REQ-PLAYBOOK-001, REQ-DATA-001 (no silent fallback), REQ-DATA-003 (a derived value records its rule), REQ-FRESH-001 (the footer), REQ-LLM-001 (the overview), REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002.

## Decisions for the owner

The owner's decisions above are written in. The rest are recommended; striking one changes only the sections named.

1. **TF bias prints two decimals** (Design 2). Recommended: `-0.75`, the value stored. Alternative: one decimal rounded half away from zero, `-0.8`.
2. **The monthly candle's weight stays none** (Design 2). Recommended: leave it. The weights are `lib/strat.py:131-140` (daily 0.30, weekly 0.10, no monthly key, so `weights.get(tf, 0.0)` at `:484` gives it 0); the score gates signals and feeds the insight's conviction, and FEAT-STRAT-001's legacy controls pin it. The overview will say the monthly is shown and not weighted. Alternative: a FEAT-STRAT-001 spec that weights it.
3. **RVOL: one definition, staged** (Problem 3, Design 3). Decided by the owner: one calculation. Relative volume is a bar's volume divided by the mean volume of the prior N bars, the bar itself excluded. Recommended staging, as the owner's standing rule on replacements requires: stage 1 (this PR) puts the definition in `lib` and the brief displays it; stage 2 switches each signal consumer in its own PR, with fires and outcomes before and after for SPY, QQQ and IWM through the production replay path, and its thresholds derived again. Every other volume ratio is either switched to the definition or renamed so that nothing else is called RVOL (Problem 3's table). Alternative: switch every consumer at once here; rejected, the thresholds would shift with no evidence.
4. **Where the premarket rule is filed** (Design 4). Recommended: here, since it moved every call trigger on 11/16 and the owner asked for the brief's fixes as one. Alternative: its own FEAT-STRAT-001 spec, with this spec keeping Designs 1, 2, 3 and 5.
5. **The premarket rule: confirmed extremes now, the misprint rule run live when its module exists** (Problem 4, Design 4). Recommended as the owner framed it: option (1) is the durable path and option (2) the interim. Option (1) cannot read stored flags: `2026-11-16-feat-data-001-bar-misprint-flags-r2.md` (PR #1988) writes a morning's flags in its nightly pass inside the 21:00 ET fetch job (its decision 5 and Design 4, read on branch `origin/docs/spec-feat-data-001-bar-misprint-flags-r2`), after the 08:20 ET fetch and the 08:30 ET brief. So the premarket computation calls that spec's pure rule (`lib.bar_prints.isolated_prints`, Design 1) on the bars it already holds. That module is task 2 of that spec's plan and is not on main; until it is, the stale closing-price report rule and the confirmed rule apply (Design 4, "Order").
6. **`--no-persist` writes no history row either** (Design 5). Recommended: a dry run leaves no trace in either table. Alternative: write the history row only.
7. **The level rule's version moves to v4** (Design 4, B8b). The movement statement picks its resolved rows by `level_basis.rule_version` alone, so new extremes under the old label would show old-rule rates. Recommended: `feat-strat-001.v4`, with v3 bases rebuilt exactly as today. The first v4 sessions then have few or no resolved rows of their own rule; what the statement prints for an empty population was not read. Alternative: keep v3 and filter on a recorded extreme-rule name inside the premarket snapshot.
8. **Review fixes of 2026-11-16** (Codex's first code review of PR #1993 at a322fab2, five findings, each confirmed against `main` 060c89a0). They add B8b and change B5, B7b, B9 and B10. Written into Designs 2, 4 and 5.
9. **A thin bar sets no premarket extreme** (owner, 2026-11-16, after the 278.92 print was read as a one share trade; the owner asked for the fix in place on this PR). Rule `thin-bar-v1`, B7c: a bar under 100 shares gives no price to `pre_high` or `pre_low`. The alternative, leaving it to the confirmed rule, does not work: that rule accepts a bar that closes at its high, which the one share bar does. The 100 is a starting value with a named measurement before it is kept.

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

### 3. RVOL: one page, one calculation

The brief showed IWM RVOL from 17,722,264 over a 20-day mean that includes that same day: 0.7577 (stored `rvol` 0.757652, db-query-h2n49). Against the 20 sessions before it: 0.7324 (db-query-kzjkd). SPY 0.825 against 0.803, QQQ 0.853 against 0.832.

**The one definition (owner, 2026-11-16).** Relative volume is a bar's volume divided by the mean volume of the prior N bars. The bar being measured is not in its own average. With fewer than N prior bars there is no value; it is never filled with 1.0 or 0.

**Every RVOL computation and reader found** (grep over `lib`, `gcp`, `platform/api` and `scripts` on stocks `main` 060c89a0, and `src` on solyra `main` af6b6ce). "One definition" means the site ends up calling `lib.indicators.relative_volume`. "Renamed" means it is a different measure, it stays, and it loses the name RVOL.

| # | Where | What it computes today | Readers and thresholds | Verdict | Stage |
|---|---|---|---|---|---|
| 1 | the brief, `gcp/premarket_brief.py:1109-1111` | last daily volume / 20-day mean, today in the mean | brief line (`:2029`), `premarket_analysis.rvol` (`:3710`), dashboard API (`platform/api/routers/dashboard.py:145`, `:195`, schema `platform/api/schemas.py:461`), solyra `src/routes/DashboardPage.tsx:52`. No threshold | one definition | 1, this PR |
| 2 | `lib/indicators.py:215-218` `calculate_rvol`, column `RVOL` (`:1195`) | volume / rolling 20 mean, bar in the mean, `min_periods=1` (the first bar of a window reads exactly 1.0) | the readers in rows 3 to 6 | one definition; `calculate_rvol` is deleted when its last reader has switched | 2 |
| 3 | signal monitor entry gate, `gcp/signal_monitor.py:1479-1482`, verdict `:104-116` | reads `RVOL` | `rvol_gate_min` 1.0, mode shadow (`lib/config.py:508-509`); measured on today's form (`:495-498`); a missing value is "below" (`:114-115`) | one definition, threshold derived again | 2, with replay |
| 4 | signal monitor timeframe tag, `gcp/signal_monitor.py:1316-1319` | reads `RVOL` | `HIGH_RVOL` 2.0, `LOW_RVOL` 1.0 (`lib/strategies/timeframe.py:66`, `:68`); a missing value is treated as 1.0 (`:124`) | one definition, thresholds derived again | 2, with replay |
| 5 | the stored fire, `gcp/signal_monitor.py:1729` (`signal_alerts.rvol`), Discord text `:1642`; strategies `lib/strategies/momentum.py:241`, `mean_reversion.py:180`; `lib/signals.py:413`; `lib/backtest.py:858` | read `RVOL` | `scripts/calibrate_thresholds.py:118-123` computes its own copy (bar in the mean) for the per-ticker `rvol_min` and `rvol_max` (`:192-193`) | one definition; the per-ticker band derived again | 2, with replay |
| 6 | `market_data_daily.rvol` (`gcp/database.py:1101`), read by the insight bundle (`lib/agents/summarizers.py:227`, `:390`) and the loader (`lib/data_loader.py:565`, `:637`); feature builders (`gcp/research/p7_build_multi_tf_features.py:350`, `gcp/research/strat_engine/strat_data_builder.py:510`) | the daily `RVOL` column, stored | models trained on the stored values | one definition; stored history recomputed, features rebuilt | 2 |
| 7 | `lib/indicators.py:221-230` `calculate_rvol_recent`, column `RVol_Recent_20` (`:1198`); a copy in `lib/trading_analysis.py:797-798` | volume / rolling 20 **median**, bar in the median | the `rvol_above_recent` condition, threshold 1.2 (`lib/strategies/config.py:70`, `lib/strategies/momentum.py:98-101`, `:153-156`, `lib/trading_analysis.py:913-917`) | a different measure (median). Replay decides: replaced by the one definition if fires and outcomes are no worse, otherwise kept and renamed "volume against recent median" (`volume_vs_recent_median`, condition `volume_above_recent_median`). Either way the name RVOL leaves it | 2, with replay |
| 8 | `lib/indicators.py:233-268` `calculate_rvol_vs_baseline` with `minute_of_day_volume_baseline` (`:272`); the monitor's `_corrected_rvol` (`gcp/signal_monitor.py:2029`), stored as `signal_alerts.rvol_mod` (`gcp/schema.sql:4103`) | bar volume / median volume at that same minute over prior sessions | shadow only: recorded, gates nothing (`gcp/signal_monitor.py:1505-1507`) | a different measure: renamed "minute-of-day volume ratio" (`volume_vs_minute_of_day`). Its code calls itself the corrected RVOL; under the owner's definition it is not RVOL | 2 (a column rename) |
| 9 | `lib/indicators.py:297-313` `calculate_rvol_minute_of_day`; `lib/trading_analysis.py:351-389` (`RVOL_MOD`, `RVOL_MOD_EXCL`) | bar volume / mean volume at that minute over the frame, the bar's own session in the mean unless excluded | research frames; no caller of the `lib/indicators.py` function was found outside tests | renamed with row 8, or deleted if unused | 2 |
| 10 | `lib/trading_analysis.py:345-349` (`RVOL20`, `:788`) | volume / rolling 20 mean, bar in the mean | historical signal generation in that module | one definition | 2, with replay |
| 11 | `lib/agents/summarizers.py:1152-1153`, `:1629-1630` (`vol_ratio`) | volume / 20-day mean, bar in the mean | analog matching in the insight bundle (`:1209-1210`) | one definition, renamed to match; the matches compared before and after | 2 |
| 12 | `scripts/fetch_market_data.py:65`, `:272-273` | volume / 20-day and 10-day mean | the legacy script's CSV | one definition, or removed with the script | 2 |
| 13 | live page, `platform/api/routers/live.py:525-558` (the 20 newest stored daily volumes), `:732-734` (volume / that mean) | whether today's row is among the 20 was not read | conditions "RVOL > 1.0" (`:829`, `:841`); solyra passes the mean through (`src/routes/LiveMarketPage.tsx:214`, `src/hooks/useLiveIndicators.ts:10`) | one definition: the mean must be of the 20 sessions before today | 2 |
| 14 | playbook, `platform/api/routers/playbook.py:671-680` | `volumeToday / avgVolume20d`, both sent by solyra (`src/routes/PlaybookPage.tsx:308-320`) | conditions "RVOL > N" | follows row 13 | 2 |
| 15 | config API, `platform/api/routers/config.py:114-116` (`period`, `signal_threshold` typed as 1.0); `rvol_minimum` 1.5 (`lib/config.py:483`) | settings, not a computation | solyra `src/hooks/useConfig.ts:29`, `src/routes/HelpPage.tsx:24`; no reader of `rvol_minimum` was found outside `lib/config.py` | follow the gate's derived threshold; an unread setting is removed | 2 |
| 16 | solyra help text, `src/routes/HelpPage.tsx:69` | says RVOL is "Current volume compared to the average for this time of day", which is row 8's measure and not what any gate reads | display | text corrected to the one definition, in a solyra PR | 2 |
| 17 | solyra `src/components/options/ContractDrilldown.tsx:70`, `:234` | an `rvol` field of mock data (`src/data/contractDrilldownMock.ts:45`) for an options contract, not from the API | display | out of scope until it has a real source; it must then be the one definition or carry another name | none |

solyra holds no RVOL arithmetic (`src` searched); it shows what the API sends.

**Why the signal consumers do not switch in this PR.** Changing the denominator changes what a threshold means. Algebra, not a measurement: with the bar in a 20-bar mean, "RVOL at least t" is the same test as "volume at least 19t / (20 - t) times the mean of the 19 bars before it". At t = 1.0 that is 1.0, so the entry gate's line barely moves (19 prior bars against 20). At 1.5 it is 1.54, and at 2.0 it is 2.11: the timeframe tag's "high volume" line would loosen if the number 2.0 were kept. And where today's form reads exactly 1.0 on the first bar of a window, the definition gives no value until N prior bars exist, which the gate counts as "below". The owner's standing rule is that a replacement is tested through the production replay paths against its hypothesis before it is swapped in. So each stage 2 PR carries: the fires and their outcomes before and after, for SPY, QQQ and IWM, from `python -m scripts.replay_signal_monitor` or the `signal-monitor` job with `REPLAY_DATE` (CLAUDE.md 3.6); and the threshold derived again from that evidence and written down, never left to shift silently. Whether an intraday consumer's N prior bars may reach back into the previous session is settled in its stage 2 PR by the same replay.

**The industry convention: what was and was not verified.** Nothing was verified in this session. No vendor page was opened. What follows is recalled, and it is not evidence: relative volume is generally described as current volume against an average of earlier periods; Finviz describes current volume against a 3-month average; TradingView's "Relative Volume at Time" and thinkorswim's compare with the same time of day on prior days, which is row 8's measure; a volume moving average drawn on a chart includes the current bar. As recalled, platforms differ on N, on mean or median, and on whether the current bar is in the average, so there is no single standard to cite. The owner's definition is a decision for this codebase, in line with the common description; it is not presented as a verified industry standard.

### 4. Premarket high and low: what the spike filter does, and why 11/16 passed

**What it does today.** `premarket_print_filter` (`lib/indicators.py:661-710`) drops (a) any open, high, low or close equal to the prior close to the cent when the bar's midpoint is away from it, and (b) a bar's high (low) that lies more than k beyond the bar's own open and close and beyond the opens and closes of the two bars on each side, where k is `pm_spike_atr` times ATR (`:701-710`). `pre_high` is then the highest surviving high (`:634-637`). `pm_spike_atr` is calibrated per ticker.

**Why 11/16 passed.** k is in daily ATR units. From the stored rows (db-query-kzjkd):

| Ticker | `pm_spike_atr` | ATR(14) | k | stored `pre_high` | spikes dropped | prior-close prints dropped |
|---|---|---|---|---|---|---|
| IWM | 0.542 | 4.875 | $2.64 | 278.92 | 0 | 7 |
| QQQ | 1.073 | 16.338 | $17.52 | 681.022 | 0 | 16 |
| SPY | 0.942 | 11.036 | $10.40 | 754.377 | 0 | 9 |

The owner's check against the consolidated tape gave premarket highs of 276.90, 752.44 and 674.92. The prints that set the stored highs stood $2.02, $1.94 and $6.10 above those: under k every time. They became `PMK_H`, the call trigger, about 2 points too high on IWM and SPY and 6 on QQQ, and changed which targets were skipped.

**What the vendor's bars can and cannot tell us.** Each one-minute bar holds five numbers for its minute: open, high, low, close and volume (`market_data_intraday`, `gcp/schema.sql:140-153`). It holds no individual trades, no trade timestamps and no trade condition codes. So the two things that would identify a late-reported trade, the time it actually happened and the code that marks it as late or as a closing-price report, are not in this data. A late-reported trade cannot be filtered by its date or its condition from these bars. All a reader can see is that some print in the minute reached the bar's high.

**The closing-price reports.** Friday 11/13's official close was 277.54 (`market_data_daily`, db-query-776p2). After the close that price kept arriving in bars where the market was trading somewhere else: the 18:30 ET bar opened and peaked at 277.54 and closed at 275.60 on 397,865 shares, and the 20:00 ET bar printed 277.54 for all four prices on 389,795 shares; six smaller bars between 16:04 and 17:06 ET carry it as their open or high while trading 276.2 to 276.9 (same execution). Those are reports at the closing price, not the market's price in that minute. On Monday 11/16 two premarket bars, 07:35 and 07:40 ET, had a high of exactly 277.54 (the investigation's reading of the vendor's bars; the 11/16 bars are not in `market_data_intraday` yet, 0 rows on db-query-776p2, so they were not read here).

**What today's rule (a) already does with them.** Rule (a) drops a value equal to the prior close to the cent when the bar's midpoint is further from that close than `pm_stale_print_atr` times ATR (`lib/indicators.py:693-699`). For IWM on 11/16 that distance was 0.0329 x 4.875, about $0.16 (the row's `pre_filter_params`, db-query-776p2), and the row counts 7 prior-close prints dropped. The stored high was 278.92, not 277.54, so the 277.54 prints did not set it; whether the 07:35 and 07:40 highs are among the 7 was not confirmed, for want of the bars. Rule (a) has two limits: it runs only when the ATR and both calibrated thresholds are usable, and otherwise nothing is filtered at all (`:689-690`); and it leans on a calibrated distance. The named rule below needs neither.

**Why it looked like a problem with the HIGH.** Only because of where the market was. On 11/16 the three tickers traded below Friday's close, so a stale report at Friday's close sat above the market and could only corrupt the premarket high. On a morning that gaps up, the same reports sit below the market and would corrupt the premarket low, and the put trigger with it. Nothing about the prints is one-sided. Every rule here is written for both sides and tested on mirrored bars (B7, B7a, B7b).

**The 278.92 print is a one share trade.** Alpha Vantage's one-minute bar for 08:05 ET on 2026-11-16 reads open 276.4801, high 278.92, low 276.4801, close 278.92, volume 1 (read 2026-11-16 through the vendor's intraday endpoint with adjusted=false). Webull's one-minute bars for the same morning have no 08:05 bar at all; its 08:04 and 08:06 bars trade 276.26 to 276.34 (read the same day). Why Webull left it out is not known: neither feed carries trade condition codes, and Webull keeps other one share bars. The same Alpha Vantage read shows the 07:40 ET bar as 277.54 on all four prices with volume 0, and the 07:35 bar closing at 277.54 on 464 shares. The confirmed rule of B7 does not stop the 08:05 bar, because it closes at its high, and the spike rule does not either, because it has no wick. Volume is the one fact the bar holds that separates it, so the thin bar rule (B7c) runs before the confirmed rule: a bar under one round lot sets no extreme. The 100 share value is a starting value: the implementation PR reports, from stored bars read only, how many premarket sessions of SPY, QQQ and IWM change their pre_high or pre_low under it, before the value is kept.

**The root cause, plainly.** The vendor's one-minute bar takes its high and low from every print reported in the minute, including late and off-market ones, and gives no way to tell them apart. A threshold only chooses how large a wrong print has to be before it is ignored.

**The options.**

| Option | What it does | Root cause or mask | What it cannot catch |
|---|---|---|---|
| (1) ignore the flagged side of a flagged bar (the misprint flags of PR #1988) | a rule on the minute's own scale (6 local ranges and 50 bp) marks the print; the premarket extremes skip marked sides | closest to the cause that bars allow: it judges the print against its own minute, not the day's ATR | a print within 50 bp (11/16: IWM's was about 73 bp, SPY's about 26 bp, so SPY's would not be flagged); three or more bad bars in a row; the last two bars before the fetch, which have no later neighbours. The stored flags of a morning are written at about 21:00 ET that night, so the 08:20 ET fetch must run the pure rule itself on the bars in memory |
| (2) a confirmed extreme: a price two bars reached, or a bar opened or closed at | one bar's lone wick cannot set the level | a mask: it does not say which print was wrong | a wrong price repeated in two bars; a real high touched by one wick only, which is then understated |
| (2a) the stale closing-price report rule (`stale-close-report-v1`): a high or low equal to the prior session's official close to the cent, apart from the bar's own open and close, sets no extreme | names one known kind of bad print by the one fact the bars do hold about it, its price | a named cause for that kind only; it needs no threshold and no calibration | a stale report at any other price (278.92); a bar that opens or closes at the stale price (rule (a) drops those when it runs); a real trade at exactly the prior close made by a wick, which is then understated by the length of that wick |
| (3) cross-check against a second source's consolidated premarket high and low | compares with the tape | the only one that addresses the cause | nothing in principle; no second source is connected to production |

Recommended (decision 5): (2) and (2a) now, (1) when the flags and their consumers' spec exist. (3) needs a data source and is not specified here.

The 11/16 one-minute bars are not in `market_data_intraday` yet: the newest stored bar is 2026-11-14 01:00Z (db-query-nrfqn; still so on db-query-776p2). The prints named above are the investigation's and the owner's; B8 tests the rule on the stored bars once the nightly has written them.

### 5. The replay cannot run safely

- `BRIEF_AS_OF=2026-11-16` suppresses Discord (`gcp/premarket_brief.py:4296-4312`) but resolves `allow_update` True (`:3589-3591`), stamps the canonical row `replay` (`:3898`) and upserts it over the day's live row on `(analysis_date, ticker)` (`:3916-3918`). History rows are always written.
- Live readers filter `run_kind = 'live'`, so after such a replay the dashboard, the movement statement and the insight's `read_live_level_basis` find no brief for 11/16.
- The brief reads `pre_high` and `pre_low` from `market_data_daily`, written at 08:20 ET, so a replay prints the stored 278.92 whatever the rule in `lib/` is.
- The brief writes before it persists. `generate_premarket_brief` upserts `strat_levels` and commits (`:1470-1475`) and can delete null-close rows of `market_data_daily` (`:1032`, `:242-270`). Both catch their own errors (`:1488`; the delete is "fire-and-forget"), so a test that only makes writes raise would pass while the writes were attempted.
- `market_data_daily.pre_fetched_at` is not the brief's cutoff. The nightly rewrites it with the time it read the bars (`gcp/fetchers/fetch_market_data.py:590-610`, provenance columns `:345`), and so does the later premarket refresh (`gcp/fetchers/fetch_premarket_refresh.py:260`). Production shows it: the 11/13 row's `pre_fetched_at` is 2026-11-15 06:01Z (db-query-776p2). The brief's own cutoff is in its row: `level_basis.premarket.fetched_at` (`lib/strat_levels.py:2062`, `:2213`).

## Non-goals

- No change to triggers' rule, targets, stops, exit legs, spacing, ATR levels or the level builder's picks (`lib/strat_levels.py`); only its version label moves (B8b). A separate spec covers targets.
- No change to FTFC weights, to `calculate_ftfc`, or to the stored `ftfc_score`.
- No signal consumer of RVOL switches here, no threshold changes, and no stored signal column is renamed: that is stage 2, one PR per consumer, each with its replay comparison and its own approved spec. `calculate_rvol`, `calculate_rvol_recent`, `calculate_rvol_vs_baseline` and `calculate_rvol_minute_of_day` keep their formulas in this PR.
- No change to rules (a) and (b) of the print filter, to `pm_spike_atr`, to its calibration (`lib/level_calibration.py`), or to `gcp/schema.sql`.
- No reader of the stored misprint flags (`intraday_bar_flags`); that is the second spec PR #1988's spec names. Design 4's step 2 calls the pure rule only.
- No rewrite of stored premarket fields: `--recompute-premarket` on the daily fetcher exists for that and is not run here.
- No schedule, deploy or job-size change. No production write from the implementation PR.
- No change to the insight pipeline (its own spec, `2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`).

## Approaches considered

- Gamma: label by the snapshot's own date (chosen); or keep the tiers and only add the date to the time, which still calls Friday's snapshot Live.
- Overview: send the labels and check the text (chosen); or drop the model and always print the deterministic sentence, which is what the check falls back to; or prompt changes alone, which nothing verifies.
- RVOL: one definition in `lib`, the brief first and each signal consumer by replay (chosen, owner); every consumer at once (decision 3's alternative); the brief only with its own function, which leaves two things called RVOL (the earlier draft, withdrawn).
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
- `overview_conflicts(text, tickers)`: split the text into clauses; a clause that names daily, weekly or monthly with bearish, down or lower claims 2D on that timeframe; with bullish, up or higher, 2U. The claim must hold for every ticker the clause describes: each ticker it names, or, when it names none, every ticker in the brief. "All three names are bearish on the weekly" with one 2D and two inside bars is a conflict naming the two. Only a clause with a partial quantifier (one of, some, two of three, most) is held to that count and no more. Any conflict: the brief prints the deterministic sentence ("IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75. ...") and logs the withheld text. No second model call.
- The weights, the score and the FTFC state are untouched.

### 3. RVOL (`lib/indicators.py`, `gcp/premarket_brief.py`)

**Stage 1, this PR.**

- New `lib.indicators.relative_volume(volume, period=20)`: `volume / volume.shift(1).rolling(period, min_periods=period).mean()`, NaN where that mean is not positive or there are fewer than `period` prior bars. Its docstring states the owner's definition and that it is the only computation in the codebase that may be called relative volume or RVOL.
- The brief's `:1109-1111` calls it. NaN becomes `None`, and the line prints no RVOL text, as it does for `None` today (`:2029`).
- `premarket_analysis.rvol` holds the new value from the first brief after the deploy; the dashboard's briefing strip shows it. Earlier rows keep the old basis; nothing marks the change in the row (Risks).
- `tests/meta/test_one_rvol_definition.py` (B6b) lists every other site of Problem 3's table as a stage 2 entry. A new computation named RVOL fails it. The list can only shrink.
- Nothing else changes: rows 2 to 16 of the table keep their formulas, names, thresholds and stored columns.

**Stage 2, one PR per consumer, each under its own approved spec.** Not part of this PR's `done_when`.

- A consumer switches from its old column to `relative_volume` only in a PR that shows, for SPY, QQQ and IWM over a stated window, the fires and their outcomes before and after, run through the production replay path (`scripts.replay_signal_monitor`, or the `signal-monitor` job with `REPLAY_DATE`), against a hypothesis written down first.
- Its threshold is derived again from that evidence and recorded in the PR. A threshold number is never carried across the switch unexamined.
- A measure that is different by design (rows 7, 8 and 9) is renamed in its PR so the name RVOL is left to the one definition. A stored column is renamed by adding the new column, writing both, moving the readers, then dropping the old one, in that order.
- Stage 2 ends when B6b's list is empty and `calculate_rvol` is deleted.

### 4. Premarket high and low (`lib/indicators.py`)

- In `calculate_premarket_context`, after rules (a) and (b), the stale closing-price report rule runs (`stale-close-report-v1`, B7a): a bar's high that equals the prior session's official close (`prev_close`) to the cent, and is not that bar's own open or close to the cent, is dropped as an extreme candidate; the same for its low. The bar still counts through its open and close. The rule needs the prior close only: no ATR, no calibrated threshold, so it runs when rules (a) and (b) cannot (`:689-690`). It is written once for both sides.
- The count goes in the row: `confirmed.stale_close_reports {rule, high, low, prior_close}`, and is `None`, never zeros, when there is no prior close. It counts what this rule dropped itself; values rule (a) already dropped stay in `pre_excluded_stale_prints`.
- Before the confirmed rule, the thin bar rule (`thin-bar-v1`, B7c): a bar whose volume is below `pm_min_extreme_volume` (100) is left out of the extreme candidates entirely. It still counts in `pre_vwap`, which weights by volume and so already gives it almost no weight.
- Then the confirmed rule: `pre_high = max(second-highest surviving high, highest surviving open or close)`, `pre_low` the mirror, as B7 states. `pre_range_atr` follows from them; `pre_vwap` and `gap_pct` do not change.
- The result carries `confirmed {rule, raw_high, raw_low, high_bars_above, low_bars_below, stale_close_reports}`, and the three writers put it inside `pre_filter_params` (`gcp/schema.sql:1781-1782`, an existing JSONB column). `pre_excluded_spikes` keeps its meaning.

**Order (the dependency on PR #1988's spec).**

1. Interim, in this PR whatever else is true: the stale closing-price report rule and the confirmed rule above (B7, B7a, B8).
2. Durable, once `lib/bar_prints.py` is on main (task 2 of that spec's plan; its tables, task 1, are not needed): `calculate_premarket_context` calls `lib.bar_prints.isolated_prints` on the premarket bars it was given, live, and drops the flagged side of each flagged bar before taking `pre_high` and `pre_low`, as rule (c). A dropped print must not come back through the bar's body: today a bar whose high was dropped falls back to the larger of its open and close (`lib/indicators.py:635-636`), and if the bar opened or closed at the flagged price, that fallback is the same print. So an open or close equal to the flagged value to the cent is left out of the extreme candidates too, here and in the confirmed rule's "highest surviving open or close"; the bar gives its other body value, or nothing. `pre_vwap` is not touched. It reads no stored flag: the nightly pass that writes a morning's flags runs at about 21:00 ET, after the brief. The confirmed rule then applies only to the bars the rule did not judge (its `judged` array false, which includes the last bars before the fetch, since they lack later neighbours), and `confirmed.rule` becomes `isolated-print-v1+two-bars-or-body-v1` with the flagged count beside it.
3. Which PR carries step 2 is settled when the plan is written: this one if `lib/bar_prints.py` is on the merge base (B7b), otherwise its own approved spec after that module merges. This spec does not wait for it.

**The rule's version (B8b).** `LEVEL_RULE_VERSION` becomes `feat-strat-001.v4` (`lib/strat_levels.py:1516`), because the movement statement chooses its resolved rows by `level_basis.rule_version` alone (`lib/movement_statement.py:286-349`): under an unchanged label, rungs anchored on the new extremes would be shown rates earned by the old ones. v3 and v4 share the pick rule; `from_basis` treats a v3 basis as it does today and must not send it down the v2 branch that "anything but the current version" takes now.

**Approved specs this meets.**

- `2026-11-07-feat-strat-001-one-level-source-r2.md` (approved, implemented) defines the premarket prints in its `done_when` ("drops, before taking pre_high, pre_low and pre_vwap, (a) ... and (b) ...", `:11`) and Design (`:244`). This spec adds a third step to that definition for `pre_high` and `pre_low`. It does not supersede that spec: rules (a) and (b), their masks and `pre_vwap` are unchanged, and the gate requires `supersedes` only where a plan would point at the replaced spec.
- `2026-11-10-feat-strat-001-per-ticker-params-r2.md` (`pm_spike_atr`, `pm_stale_print_atr`): unchanged; the calibration reads the (a) and (b) masks, which do not move.
- `2026-11-11-feat-strat-001-brief-atr-levels.md` and `2026-11-11-feat-strat-001-brief-exits-in-thirds.md` use `PMK_H` and `PMK_L` as the names of the premarket high and low and as rung anchors: the names and uses stand; the values under them change on a session with an unconfirmed print.
- `2026-11-14-feat-playbook-001-brief-late-slot.md` and `2026-11-14-feat-playbook-001-brief-market-date.md`: the late snapshot goes through the same function and gets the same rule.
- A stored `level_basis` keeps the premarket values it recorded, so a stored brief rebuilds as it was.
- Tests of those specs that assert a premarket high set by one lone wick change expectation; B11 lists each.

### 5. A replay that writes nothing (`gcp/premarket_brief.py`)

- `--no-persist` (env `BRIEF_NO_PERSIST=true`): implies no Discord, and suppresses every write of the run, not only the final one. The flag is passed into `generate_premarket_brief`, which then skips the `strat_levels` upsert (`:1470-1475`) and the null-close delete (`:1032`); `persist_to_cloud_sql` is not called. Any other write path the plan's trace finds is suppressed the same way, and B9's recording stand-in is what proves none is left: it asserts that no write call was made, since the two known writers swallow errors and a raising stand-in would pass anyway. Where the engine allows it the run's sessions are also opened read-only in the database; whether `gcp.database.get_engine` can do that was not checked.
- In that mode `main()` prints the brief JSON (as today), the rows `build_persist_rows(brief)` returns, and the payloads (as the no-webhook path does today, `:4363-4367`). Exit 2 with the late slot or `--update`.
- `build_persist_rows` is the row-building half of `persist_to_cloud_sql`, moved out unchanged; the write half calls it.
- `BRIEF_PREMARKET_FROM_BARS=true`, valid only with `--no-persist`: per ticker one strict read of the session's one-minute bars from `market_data_intraday` up to the cutoff the original brief recorded, `level_basis.premarket.fetched_at` of the session's live `premarket_analysis` row, never the daily row's `pre_fetched_at`, which later jobs rewrite (Problem 5). No recorded cutoff: "premarket cutoff unavailable" and no recomputed value. The read goes through `gcp.fetchers.fetch_market_data.premarket_snapshot` (`:380`), with the parameters `pre_filter_params` recorded. The result replaces the stored `pre_*` values in memory only.
- The overview and per-ticker model calls still run in a dry run; they are part of what is being checked.

### 6. Capacity (CLAUDE.md rule 0)

| Run | Volume | Velocity | Wall-clock |
|---|---|---|---|
| scheduled brief | unchanged rows | one more single-row gamma probe per ticker when a REALTIME row exists (the EOD probe now always runs): 3 more round trips | 1.5 to 6 s more at 0.5 to 2 s a round trip; each probe is capped at 10 s (`:114`) |
| dry run with bars | at most 330 one-minute bars per ticker (04:00 to 09:30 ET) | one read per ticker, and the cutoff from the brief rows already read: 3 | under 6 s more |
| premarket fetchers | the same bars; one sort more in memory | no new statement | not measurable |

- No new job, schedule or table. The job's timeout and memory (`gcp/deploy.sh:1382-1398`) were not read; the additions are seconds.
- Cost: no new scheduled work. A dry run is one brief execution with its model calls; the cost of one was not read.

## Implementation plan: size

12 tasks, one branch, one PR.

1. The gamma probe and `format_gamma_footer`, with tests.
2. `format_tf_bias` and the three render sites.
3. The overview's inputs and prompt.
4. `overview_conflicts` (claims hold for every ticker described) and the deterministic sentence.
5. `relative_volume`, the brief's call, and the one-definition list test (B6b).
6. The stale closing-price report rule and the confirmed extremes in `calculate_premarket_context`, with mirrored high and low tests on written bars.
7. The three writers' `pre_filter_params`, and the changed expectations of earlier tests.
8. The rule version v4, the v3 rebuild, and the movement statement's mixed-version test.
9. `build_persist_rows`, `--no-persist` through `generate_premarket_brief`, and the no-write recorder.
10. `BRIEF_PREMARKET_FROM_BARS` on the brief's recorded cutoff.
11. The 11/16 fixture once the bars are stored.
12. PR-body evidence, the site note, catalog and traceability.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes.

1. **Deploy** the brief job and the fetchers from `main` at or after the merge, with the `./gcp/deploy.sh` targets the plan names.
2. **Replay 2026-11-16 with no write**, on the owner's yes:
   `gcloud run jobs execute premarket-brief --region us-east1 --update-env-vars="^|^BRIEF_AS_OF=2026-11-16|BRIEF_NO_PERSIST=true|BRIEF_PREMARKET_FROM_BARS=true|BRIEF_TICKERS=SPY,QQQ,IWM" --wait`
   - Check, read-only, before and after: the three `premarket_analysis` rows of 11/16 are `run_kind` live with the same `analysis_ts`, `premarket_analysis_history` has no new row, and the `strat_levels` rows of the three tickers and the `market_data_daily` row counts are unchanged.
3. **Check against market data**, on the owner's yes, for SPY, QQQ and IWM from the execution's log: the footer names Friday; the overview agrees with the labels; TF bias -0.75; RVOL 0.80, 0.83 and 0.73 in that order; the recomputed premarket high and low beside the stored ones and beside the consolidated values the owner has. Recorded on the PR.
4. **The first scheduled brief after the deploy**: its footer, overview and RVOL, and the `confirmed` block in that morning's `pre_filter_params`.
5. **Browser proof** for the dashboard's briefing strip (RVOL), by the owner as AGENTS.md defines.
6. On a `docs/` branch after the merge: the DASHBOARD-01 note and the plan's status.

The insight replay of the same day is in the insight spec's Close-out and needs the 11/16 brief row left live, which step 2 does.

## Risks

- **A real premarket high made by one wick is understated** by the confirmed rule, and the call trigger sits lower than the tape's high. How often is not measured.
- **A wrong price printed twice passes** the confirmed rule.
- **The stale closing-price report rule drops a real wick at exactly the prior close.** On a morning trading within cents of that close, a true high or low made there by a wick is understated by the wick's length. How often is not measured.
- **A stale report at any price but the prior close is not named by it** (278.92 on 11/16). The thin bar rule and the confirmed rule stand against those.
- **Two things are called RVOL until stage 2 ends.** The brief shows the one definition while the signal monitor still reads the old column; a fire's stored `rvol` and the brief's RVOL are then on different bases. B6b keeps the list from growing; only the stage 2 PRs end it.
- **v4 starts with no history of its own.** The movement statement's rates for v4 rungs are empty or thin until v4 sessions resolve.
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
- The RVOL convention: not verified. No vendor page was opened in this session; Problem 3's paragraph on it is recall.
- The 11/16 07:35 and 07:40 ET highs of 277.54, and whether rule (a) dropped them: not read; the bars are not stored (db-query-776p2). Friday's 18:30 and 20:00 ET bars were read.
- Why Webull's feed has no 08:05 ET bar for IWM on 2026-11-16 while Alpha Vantage's has a one share bar at 278.92: not known; no trade condition codes are available. Whether 100 shares is the right minimum: not measured yet (B7c names the measurement).
- How often a premarket bar's lone high or low equals the prior close to the cent over the history, on each side, and how often rule (a) is not running: not counted.
- What any stage 2 switch does to fires and outcomes: nothing was replayed; the threshold figures in Problem 3 are algebra.
- Whether `lib/trading_analysis.py`'s signal path and `scripts/fetch_market_data.py` still run anywhere: not traced.
- What the movement statement prints for a rule version with no resolved rows: not read.
- Whether the level basis's premarket snapshot records `fetched_at` on every stored brief row, 11/16 included: the field mapping was read (`lib/strat_levels.py:2062`), the rows were not.
- Whether `platform/api/routers/live.py`'s 20 stored days include today's row: not read. solyra's files that mention RVOL were listed by grep on its `main` af6b6ce, and only the lines cited were read.
- Which tests of the earlier specs change expectation under Design 4: not run.
- How `gcp/fetchers/fetch_market_data.py`'s `--recompute-premarket` cuts bars for a session: not read.
- Whether `generate_premarket_brief` writes anywhere besides `persist_to_cloud_sql` (on-demand calibration, caches): not traced; B9's engine stand-in is what must show it.
- The brief job's timeout, memory and per-run cost: not read.
- That `--update-env-vars` on `jobs execute` applies to that execution only: taken from CLAUDE.md 3.5's recipe, not run.
- Whether a canvas depicts the brief: not opened.
