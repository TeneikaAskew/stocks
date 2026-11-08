---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-MARKET-001, REQ-PERF-002, REQ-PLAYBOOK-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, INSIGHTS-08]
done_when:
  - "Parameter tables and loader: gcp/schema.sql adds level_param_policy and ticker_level_params (Design 1) with a migration that seeds the policy rows of Design 2 and no ticker values; lib/strat_levels.load_level_params(query_fn, tickers, session_date) reads every listed ticker in one query and returns, per ticker and parameter key, the row in force on session_date (the greatest effective_from on or before it) with its value, status, method_id, sample_n, input range and run id; a ticker with no row gets status params_unavailable for every key; a row whose atr_basis differs from the policy atr_basis in force on session_date is never used and gives that key status params_basis_mismatch (no older row of another basis is substituted); a missing table or a failed query raises LevelParamsUnavailable; tests: two versions with a session between them read the earlier one, ten tickers issue exactly one query, a dropped table raises, an unknown ticker returns the typed status, and a partial calibration failure across a basis change (policy switches atr_basis from atr_14 to atr_5 effective D, the job writes atr_5 rows for SPY and fails for QQQ) leaves SPY on its atr_5 rows and gives QQQ params_basis_mismatch on D with both sides orb_only, never QQQ's atr_14 values multiplied by atr_5; the tests fail on origin/main (no such tables or function)"
  - "No numbers in the level and plan code: a structural test (AST) asserts that MAX_TRIGGER_DISTANCE_ATR, MAX_TRIGGER_DISTANCE_PCT, MIN_ROOM_PCT, compute_room_to_run, _ENTRY_BUFFER, _STOP_ATR_MULT, _TARGET_R_MULTIPLES and PlanContext.safe_atr no longer exist, and that build_session_levels and every function it calls in lib/strat_levels.py, lib.indicators.calculate_premarket_context and lib.agents.trade_planner.compute_persona_plans and every function it calls hold no numeric literal, int or float, other than 0, 1, -1, 2, -2 and 100 outside round() digit arguments and slice bounds, and read no module-level numeric constant other than the sizing and FTFC names in done_when 15; a behaviour test changes one ticker_level_params row (trigger_window_long_atr from 3.0 to 2.0 for a fixture with the nearest long level at 2.5 ATR) and the long side goes from that trigger to orb_only with no code change; both fail on origin/main and on the #1753 head (lib/strat_levels.py:865-866 and :851, lib/indicators.py:615 and :623, lib/agents/trade_planner.py:91, :130-148 and :289)"
  - "Calibration methods: lib/level_calibration.py computes every parameter in the Design 2 table by its stated input, statistic, lookback and minimum sample, reading the quantile, lookback and minimum from level_param_policy; unit tests feed each method synthetic inputs with a known answer (for example 1,000 sessions whose up-excursions are 0.004 x i ATR for i in 1..1000 give trigger_window_long_atr 3.96 at coverage 0.99), assert status insufficient_history with the actual sample_n one sample below each minimum, a fixture whose breaks include ones that never trade back to the conservative entry midpoint asserts those breaks are outside the conservative stop and target populations, that every published target is greater than zero R and greater than the persona's previous target, and that a persona whose filled-break reach share cannot be met gets no_positive_target with that target and the ones after it null, and assert no look-ahead: appending bars dated on or after effective_from changes no value; they fail on origin/main"
  - "Calibrated evidence: the implementation PR body shows, for SPY, QQQ and IWM as of 2026-11-06, every parameter's calibrated value, sample size and input range beside the #1753 constant it replaces, and the evidence row Design 2 names for that parameter computed over 2015-01-02 to 2026-11-06 (for the trigger windows, the share of sessions per year whose excursion passed the window; for the premarket thresholds, every bar each threshold drops on the 20 sessions through 2026-11-06; for the break-derived values, the break counts per side and year)"
  - "Premarket fixtures under calibrated values: with the SPY, QQQ and IWM ticker_level_params rows in force on 2026-11-06, committed as a fixture written by the calibration job from production bars (run id and input range in the fixture), calculate_premarket_context on the committed 2026-11-06 Alpha Vantage 1-minute fixtures drops the 08:05 prints (SPY 765.5267, QQQ 683.50, IWM 283.745) and QQQ's prior-close prints at 647.05, keeps SPY's 04:04 close 731.28 and IWM's 269.13 low, and returns the two threshold values and their effective_from with the counts; both production callers (gcp/fetchers/fetch_market_data.py and gcp/fetchers/fetch_premarket_refresh.py) read the thresholds once per run for their whole universe and write pre_filter_status and pre_filter_params; a ticker with no calibrated thresholds gets pre_filter_status params_unavailable, its excluded counts NULL, and the builder refuses that snapshot (premarket_status premarket_unfiltered) while a reader that shows its pre_high or pre_low labels it unfiltered; the tests fail on origin/main"
  - "ATR(5) stored next to ATR(14): gcp/schema.sql adds market_data_daily.atr_5 beside atr_14, lib/config.py IndicatorConfig.atr_extra_periods includes 5, gcp/database.py DAILY_INDICATOR_TO_SQL_COLUMN maps ATR5 to atr_5, lib/data_loader.py reads atr_5 as ATR5, and gcp/fetchers/backfill_daily_indicators.py checks atr_5 for gaps in its short warmup class; tests: the nightly fetcher's row builder writes atr_5 equal to lib.indicators.calculate_atr(high, low, close, 5) on the committed daily fixture, the backfill gap list contains atr_5, and level_basis records atr_14, atr_5 and the policy's atr_basis; they fail on origin/main"
  - "One-minute bars refreshed for every calibrated ticker: gcp/fetchers/fetch_alphavantage_intraday.py resolves --symbol=ALL at run time to the brief tickers (lib/config.py MarketConfig.tickers), the insight default tickers (gcp/insight_pipeline_job.py DEFAULT_TICKERS) and the watchlist, deduplicated, instead of the SYMBOLS constant at fetch_alphavantage_intraday.py:43; a test with a stub watchlist asserts the resolved list and that the nightly path still requests extended hours; it fails on origin/main"
  - "Calibration job: gcp/calibrate_level_params.py runs in nightly mode (every ticker that load_calibration_universe returns, writing per ticker and parameter one row effective on the next session with method_id, sample_n, input_from, input_to, run_id and calibrated_at, ON CONFLICT (ticker, param_key, effective_from) DO UPDATE) and in history mode (one version per session from 2015-01-02, inputs strictly before that session); I/O shape tests assert that N tickers cost exactly N daily-bar reads, N one-minute-bar reads and N write batches, that a rerun for the same night converges to the same rows, and that one ticker's failed read logs and skips that ticker while the run exits non-zero; they fail on origin/main"
  - "Visible insufficient history: a ticker with 100 daily bars gets trigger_window_long_atr and trigger_window_short_atr status insufficient_history, both sides orb_only with reason params_insufficient_history, and the brief banner, the planner rationale and the Discord push render ORB_ONLY_COPY['params_insufficient_history'] naming the parameter, its sample_n and the minimum; a ticker with daily bars but no one-minute bars builds levels with prior-close reference and premarket_status premarket_unfiltered; a ticker whose break-derived parameters are insufficient gets persona plans with entry_zone, stop, targets and risk_metrics null and the copy naming the parameter; a test asserts that no price the brief or a plan publishes comes from a parameter whose status is not ok; the tests fail on origin/main"
  - "Missing table is loud: when load_level_params raises LevelParamsUnavailable the brief job exits non-zero without writing a premarket_analysis row for any ticker, the insight run records status failed with reason level_params_unavailable, and the signal monitor's level refresh logs and skips the level map for that cycle with the reason in its status; a test drives each path with the query raising and fails on origin/main"
  - "level_basis records the parameters: level_basis carries params (per key: value, status, effective_from, method_id, sample_n, input_from, input_to, run_id), the policy version, atr_14, atr_5 and atr_basis, and a new rule_version; SessionLevels.from_basis rebuilds with the recorded params and never reads the table, so changing ticker_level_params after a brief leaves the planner's and the movement statement's picks for that session unchanged; the movement statement's reach-rate population counts only rows of the new rule_version; the tests fail on origin/main"
  - "Point-in-time replays: the production replay paths (gcp/premarket_brief.py replay runs, the insight replay, signal-replay and gcp/premarket_playbook_resolver.py) read the ticker_level_params rows in force on the replayed session; a test with two versions replays a session before the second and gets the first version's picks; it fails on origin/main"
  - "Copy states the ticker's own values: ORB_ONLY_COPY renders next_level_outside_window and atr_unavailable from the side's recorded window (for example 'No unbroken long level within 2.4 x ATR(14); SPY's daily move stayed inside that distance on 99% of the last 750 sessions and went past it on 1%'), the schema field descriptions in lib/agents/schema.py name no ATR multiple, and a test asserts that no string literal in lib/strat_levels.py, lib/agents/schema.py, lib/agents/trade_planner.py or gcp/insight_discord_push.py contains '3x ATR', '3 ATR', '8% of price' or '0.5 x ATR', and a test renders the window copy for a fixture whose window sits at coverage 0.99 and asserts it states the coverage share as sessions that stayed inside the window and the exceedance share (1 minus coverage) as sessions that went past it, each as its own figure, and never states the coverage share as a share of sessions that reached the window; the entry-zone rationale is held to the same test (a lower edge at follow-through quantile q is reached by 1 minus q of breaks); it fails on origin/main (lib/strat_levels.py:1015 and :1024, lib/agents/schema.py:250-251 and :314-315)"
  - "Pick changes against #1753: the implementation PR body shows, for SPY, QQQ and IWM from 2015-01-02 to 2026-11-06 through the production replay paths with history-mode parameters, per ticker and side, the count of sessions whose trigger, stop, T1, T2 or T3 changes and whose orb_only state changes against the #1753 head (feature/feat-strat-001-one-level-source as merged), the counts of persona plans whose entry zone, stop or any target changes, and the before and after picks for the 20 sessions through 2026-11-06"
  - "Unchanged, each pinned by an existing or added test that passes on the #1753 head and on the implementation head: signal-monitor fire decisions, scores, strength labels, Discord delivery and alert targets (lib/config.py:305-306, gcp/signal_monitor.py:1513-1522); the brief's CALL/PUT side pick (_resolve_signal_status); persona sizing, the catalyst damper and the FTFC gates (lib/agents/trade_planner.py:151-166); the side rule, the broken rule and the cents rule of the #1753 builder"
  - "Source identity (DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, INSIGHTS-08): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01 / DASHBOARD-21 / INSIGHTS-01 / INSIGHTS-07 / INSIGHTS-08) note rows carry that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 and FEAT-INSIGHT-001 catalog records and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the two parameter tables, the atr_5 column, the history-mode calibration run, the atr_5 history backfill, the calibration job and its scheduler, and the av-intraday-nightly universe change are applied to production only after the owner's yes and recorded separately"
status: approved
supersedes: null
---

# Per-ticker calibrated level and plan parameters

## Authority

Owner rulings, 2026-11-07: "No hard-coded numbers: use a refreshable table"; "store both the
5-day and 14-day ATR"; and, about entries, "remove percent-of-price".

On 2026-11-08 the owner asked whether "the .5 ATR static value" was removed yet, and then directed:
"I need you to start thinking about how to do a cleanup and get this actually, these hard-coded
ambiguous values out of it. It should never be hard-coded. Things should be tailored to the actual
ticker. So that needs to be fixed. And if we don't have anything that updates the metrics and the
ATRs, we need to get that in place too."

An earlier brief for this lane had day-one values equal to today's constants so that no pick
changed. The 2026-11-08 directive replaces that: every value is derived from the ticker's own data,
so picks change on day one, and done_when 14 counts them.

The calibration methods, the policy quantiles, the table shapes and the job schedule below are this
delivery lane's proposal, not owner rulings. The spec is not self-approved: it takes effect only
when the owner merges the spec-only PR that adds it, and that merge is the approval its `status`
records, as with #1745, #1747 and #1750.

It builds on the FEAT-STRAT-001 one-level-source implementation, draft PR #1753 (branch
feature/feat-strat-001-one-level-source, head 13216984 when this spec was written). No
implementation PR for this spec opens until #1753 is on main. Every file:line below is on that
head unless it says origin/main.

## Problem

The level and plan path still decides with numbers written into the code. They are the same for
SPY, QQQ, IWM and any single name, and nothing recalibrates them.

### Inventory on the #1753 head

| # | Constant | Value | Where | Read at | Role |
|---|---|---|---|---|---|
| 1 | MAX_TRIGGER_DISTANCE_ATR | 3.0 | lib/strat_levels.py:865 | :944 in _within_staleness_window | Trigger, stop, target and ladder window, ATR axis |
| 2 | MAX_TRIGGER_DISTANCE_PCT | 0.08 | lib/strat_levels.py:866 | :943 | Same window, percent-of-price axis |
| 3 | MIN_ROOM_PCT | 0.20 | lib/strat_levels.py:851 | :904 in compute_room_to_run (:869-905) | Room-to-run flag; compute_room_to_run has no caller in lib, gcp, platform or scripts (only the legacy fixture tests/fixtures/legacy_strat_levels_5e1142ae.py) |
| 4 | detect_level_clusters tolerance_pct | 0.15 (percent of price) | lib/strat_levels.py:741 default, passed at :1485 | :772 | PMG zones the brief prints (:1881-1884) |
| 5 | Window copy | "3x ATR and 8% of price", "the 3x ATR window" | lib/strat_levels.py:1015, :1024 (docstring :933) | brief, planner, Discord | User-facing text that states item 1 and 2 |
| 6 | Stale prior-close print rule | 0.1 x ATR(14) | lib/indicators.py:615 | calculate_premarket_context | Drops a print on the prior close's cent when its bar's midpoint is farther away |
| 7 | Isolated spike rule | 0.5 x ATR(14) | lib/indicators.py:623 (k), :624-631 | calculate_premarket_context | Drops a high or low beyond its own and its neighbours' bodies |
| 8 | _ENTRY_BUFFER | aggressive (0.00, 0.50), neutral (0.00, 0.25), conservative (0.10, 0.40) ATR | lib/agents/trade_planner.py:130-134 | :251-253 | Persona entry zone edges beyond the trigger |
| 9 | _STOP_ATR_MULT | aggressive 2.00, neutral 1.00, conservative 0.70 ATR | lib/agents/trade_planner.py:137-141 | :259 | Persona stop distance from the entry midpoint |
| 10 | _TARGET_R_MULTIPLES | aggressive 2.0, 3.5, 5.0; neutral 1.0, 2.0, 3.0; conservative 1.0, 1.75 | lib/agents/trade_planner.py:144-148 | :296-297 | Persona targets in multiples of risk |
| 11 | Minimum stop distance | 0.5 x ATR | lib/agents/trade_planner.py:289 | :290-291 | Floor on the stop's distance from the entry midpoint |
| 12 | PlanContext.safe_atr | close x 0.01 when ATR is missing or not positive | lib/agents/trade_planner.py:85-92 (:91) | :248 | Percent-of-price stand-in for ATR in the persona offsets |
| 13 | Schema descriptions | "within 3 ATR", ">= 3 ATR" | lib/agents/schema.py:250-251, :314-315 | report JSON schema | Text that states item 1 |
| 14 | Planner docstrings | "1 ATR stop, 1R / 2R / 3R", ">= 3 ATR" | lib/agents/trade_planner.py:17, :437 | none | Text that states items 9, 10 and 1 |

The other consumers named in the brief hold no ATR multiple or percent distance of their own on the
level and plan path: gcp/signal_monitor.py reads ATR14 at :939-944 and calls the builder at :954-955
(its :1287 atr_5m_pct is a feature ratio, not a threshold); gcp/premarket_brief.py passes ATR(14) at
:1452-1454 and :1486; gcp/premarket_playbook_resolver.py reads atr_14 at :162 and calls the builder
at :169; platform/api/routers/dashboard.py reads ATR at :508-511; lib/movement_statement.py has
only the cents equality `_LEVEL_PRICE_TOL = 0.01` at :256 (the one cents rule, not a distance) and
`LOW_SAMPLE_THRESHOLD = 30` at :98 (a sample count). Found outside the level and plan path and left
for their own spec (Non-goals): lib/config.py:305-306 (alert targets +0.30% and +0.38%, applied at
gcp/signal_monitor.py:1513-1522) and platform/api/routers/playbook.py:512 (PRICE_PROXIMITY_PCT
0.005, read at :736).

The owner's 2026-11-08 question has a plain answer: no. On the #1753 head 0.5 x ATR is still
hard-coded in three places: the spike rule (lib/indicators.py:623), the minimum stop distance
(lib/agents/trade_planner.py:289) and the aggressive entry buffer's upper edge
(lib/agents/trade_planner.py:131). This spec removes all three.

### What refreshes the inputs today

- ATR(14). lib.indicators.calculate_atr (Wilder, lib/indicators.py:144-150) runs inside
  add_all_indicators (_add_atr, :1076-1088) in fetch-market-data
  (gcp/fetchers/fetch_market_data.py:357), written as market_data_daily.atr_14 (gcp/schema.sql:68)
  through gcp/database.py:1048. It runs nightly at 23:00 ET Monday to Friday
  (gcp/deploy.sh:4645) for TICKERS (fetch_market_data.py:35: IWM, SPY, QQQ, SPX and the sector
  ETFs), the watchlist (:1178-1185) and earnings tickers within seven days (EARNINGS_WINDOW_DAYS=7,
  gcp/deploy.sh:2155). backfill-daily-indicators heals NULL derived columns of the last seven days
  at 02:30 ET Monday to Saturday (gcp/deploy.sh:5063) and sweeps every ticker on Sunday
  (:5068). The brief's tickers (lib/config.py:20, IWM, SPY, QQQ), the insight defaults
  (gcp/insight_pipeline_job.py:80) and the watchlist are in that union, so they get ATR(14)
  nightly. A ticker that auto-refresh-top-n or the UI's on-demand run picks outside the union gets
  no nightly bar, and #1753's stale_daily status already shows that.
- ATR(5). Not stored. atr_20 is stored the same way as atr_14 (lib/config.py:33,
  gcp/database.py:1049, lib/data_loader.py:531 and :576), so ATR(5) can follow that path.
- Premarket snapshot. fetch-premarket-refresh at 08:20 ET (gcp/deploy.sh:4863) for the watchlist
  and the day's earnings reporters, capped at 50 (gcp/fetchers/fetch_premarket_refresh.py:49-127),
  and the nightly fetcher.
- One-minute bars. av-intraday-nightly at 21:00 ET Monday to Saturday (gcp/deploy.sh:4764) with
  --symbol=ALL, which resolves to SYMBOLS = SPY, IWM, QQQ
  (gcp/fetchers/fetch_alphavantage_intraday.py:43), extended hours on (:121). No job refreshes
  one-minute bars for any other ticker; intraday-bulk-backfill (gcp/deploy.sh:3761) was a one-off.
  market_data_intraday holds 1-minute bars, regular and extended hours, from 2015 for IWM, SPY and
  QQQ (docs/EXPERIMENT_REGISTRY.md:727: 1.93M, 2.36M and 2.20M bars).
- The parameters themselves. Nothing; they are literals.

So two inputs the calibrated path needs have no refresh: ATR(5) everywhere, and one-minute bars for
every level-path ticker other than SPY, IWM and QQQ. Both are in scope (Design 4 and 5).

## Non-goals

- Live alert targets and stops (lib/config.py:305-306 ExitConfig, exit_config_overrides read
  through get_call_target and get_put_target at gcp/signal_monitor.py:1513-1522). They are
  percent-of-price numbers and fall under the owner's 2026-11-08 directive, but they set fire exits,
  not levels, and changing them changes fires; they need their own replay. Proposed as the next
  spec, on the same calibration tables.
- The playbook condition evaluator's "price at or near support/resistance" band
  (platform/api/routers/playbook.py:512, PRICE_PROXIMITY_PCT 0.005). Its request carries no ticker
  and no ATR, and it picks no level. Same next spec.
- Persona sizing and the FTFC gates: _SIZE_BY_CONVICTION (lib/agents/trade_planner.py:151),
  _CONSERVATIVE_CATALYST_DAMPER 0.6 (:159), _CONSERVATIVE_MIN_FTFC 0.30 (:163) and
  _FTFC_ALIGNED_MIN 0.5 (:166). They are allocation fractions and score thresholds, not ATR or price
  distances.
- Counts that set the product's shape, not a distance: three targets per side
  (lib/strat_levels.py:1647), two ladder rungs (:1650), the 20-bar gap-level lookback (:1482), the
  spike rule's two neighbour bars on each side (lib/indicators.py:626-627), the cents equality
  (lib/movement_statement.py:256) and the reach-rate low-sample count (:98).
- The ATR lengths themselves, 14 and 5: the owner named both.
- The rule shapes #1753 delivers: the side rule, the broken rule, the cents rule, the filter's two
  print tests and the reference. Only their numbers move.
- A pooled or peer-group stand-in for a ticker without enough history. A ticker without enough
  history says so (Design 6); the owner may ask for a visible peer value later (Open question 6).

## Approaches considered

1. A per-ticker copy of today's constants in a table, refreshed by hand. Rejected by the owner's
   2026-11-08 directive: the values must come from the ticker, and something must refresh them.
2. Fit each parameter by optimizing replayed P&L per ticker. Rejected: it fits outcomes, overfits a
   few regimes, needs its own validation design, and gives values nobody can explain from the bars.
3. Chosen: each parameter is a stated quantile of a stated distribution measured on the ticker's
   own bars, over a stated lookback with a stated minimum sample. The quantile, lookback and minimum
   are policy rows, versioned like the values, so the owner changes intent with a row update. A
   nightly job writes a new version per ticker with its effective date and input range; history
   mode writes point-in-time versions so replays use the values in force on their session.

## Design

### 1. Tables (gcp/schema.sql)

`level_param_policy`: one row per (param_key, effective_from). Columns: param_key VARCHAR(48),
method_id VARCHAR(48), statistic_q DOUBLE PRECISION (or NULL where the method names a fixed
statistic), lookback_sessions INTEGER, min_sample INTEGER, extra JSONB (method settings such as
follow_through_minutes or the persona reach shares), effective_from DATE, note TEXT, created_at
TIMESTAMPTZ. Primary key (param_key, effective_from). Two non-parameter keys live here too:
`atr_basis` (extra = {"column": "atr_14"}) and `calibration_universe` (extra lists the sources of
Design 5). The migration seeds the Design 2 rows effective 2015-01-02.

`ticker_level_params`: one row per (ticker, param_key, effective_from). Columns: ticker
VARCHAR(10), param_key VARCHAR(48), value DOUBLE PRECISION NULL, status VARCHAR(32) CHECK in (ok,
insufficient_history, input_unavailable, no_positive_target), atr_basis VARCHAR(16) NOT NULL, method_id VARCHAR(48), policy_effective_from DATE,
sample_n INTEGER, input_from DATE, input_to DATE, effective_from DATE, run_id UUID, source
VARCHAR(16) CHECK in (nightly, history, on_demand), calibrated_at TIMESTAMPTZ. Primary key
(ticker, param_key, effective_from); index (ticker, effective_from DESC). value is NULL exactly when
status is not ok. Each row also carries atr_basis VARCHAR(16), the ATR column its value was
calibrated in (Design 4). The migration seeds no ticker values: the first rows come from the history-mode
run, applied before the code deploys (Close-out).

A key/value row per parameter rather than one column per parameter, because each parameter carries
its own status, sample size and input range, and a new parameter is a policy row, not a schema
change.

### 2. Parameters and how each is calibrated

Units are the policy's ATR basis (atr_14 on day one) of the last completed session before the
measured session. "RTH" is 09:30 to 16:00 ET, "premarket" 04:00 to 09:30 ET, from
market_data_intraday 1-minute bars. A "break" is the first RTH bar on a session on which the side's
trigger, built by build_session_levels from daily bars with no premarket snapshot (reference = the
prior close) and the parameters in force that session, trades one cent beyond it; a "held break" is
one whose session close is beyond the trigger on the break's side. A persona's entry is "filled" on
a break when an RTH bar after the break bar, on the same session, trades at the persona's entry
midpoint (the midpoint of its calibrated entry zone); the fill bar is the first such bar. Stops,
the floor and targets are measured only on filled breaks, from the fill bar to the close, and each
persona's minimum sample counts that persona's filled breaks; a break the persona never filled is
outside its population, because the trade never existed. Break-derived parameters pool the long
and short sides (Open question 3).

| param_key | Input | Statistic (policy default) | Lookback, minimum | Replaces |
|---|---|---|---|---|
| trigger_window_long_atr | daily bars | quantile 0.99 of (high minus prior close) / ATR | 750 sessions, 250 | items 1, 2 for levels above the reference |
| trigger_window_short_atr | daily bars | quantile 0.99 of (prior close minus low) / ATR | 750, 250 | items 1, 2 for levels below |
| pm_spike_atr | RTH 1-minute bars | quantile 0.999 of wick excess: min(high minus own body top, high minus the top of the two bodies each side), and the mirror for lows, / ATR | 60 sessions, 40 sessions with at least 300 bars | item 7 |
| pm_stale_print_atr | premarket 1-minute bars with no print on the prior close's cent and no wick the spike rule flags | quantile 0.95 of max(high minus midpoint, midpoint minus low) / ATR | 60, 40 sessions with at least 60 bars | item 6 |
| level_cluster_atr | RTH 1-minute bars | quantile 0.50 of the absolute 15-minute close-to-close change / ATR | 60, 40 sessions | item 4 |
| entry_buffer_{persona}_lo_atr, _hi_atr | breaks | quantiles of follow-through F (furthest beyond the trigger before the first bar that trades back to the trigger's cent, or before follow_through_minutes = 15): aggressive lo = the trigger, hi 0.75; neutral lo = the trigger, hi 0.50; conservative lo 0.20, hi 0.65 | 750, 150 breaks | item 8 |
| stop_{persona}_atr | the persona's filled held breaks | quantile of maximum adverse excursion from the fill price (the entry midpoint) after the fill bar to the close: aggressive 0.90, neutral 0.75, conservative 0.60 | 750, 150 filled held breaks | item 9 |
| min_stop_atr | the neutral persona's filled held breaks | quantile 0.50 of the same excursion from the neutral fill | 750, 150 | item 11 |
| target_{persona}_{k}_r | the persona's filled breaks | the favourable excursion beyond the fill price after the fill bar, in the persona's own R, that share p_k of filled breaks reached before the persona's stop or the close: aggressive 0.40, 0.25, 0.15; neutral 0.60, 0.45, 0.30; conservative 0.65, 0.50; a value that is not greater than zero, or not greater than the persona's previous target, gets status no_positive_target and no target is published at that k or beyond | 750, 150 filled breaks | item 10 |

Why each statistic, and the evidence available now (the implementation PR adds the 2015 to 2026
evidence, done_when 4):

- Trigger windows. The owner's question is the distance, in the ticker's ATR, within which a level
  is reached in a session; a long level is reached when the session's high gets to it, a short level
  when the low does, so the window is the excursion the ticker makes on all but 1% of sessions,
  measured per side. On the committed daily fixture (tests/fixtures/strat_levels_2026-11-06_daily.json,
  2024-12-02 to 2026-11-06, 484 sessions, both sides pooled), the 99th percentile excursion from the
  prior close is SPY 2.61, QQQ 2.36 and IWM 2.10 ATR(14); the share past 3 ATR is 0.52%, 0.52% and
  0.31%; the maximum is 6.50, 3.67 and 4.21. The #1747 spec's 2015 to 2026 check found one-sided
  moves from the open past 2 ATR on under 1% of sessions per ticker. The percent axis goes: a
  calibrated ATR multiple already scales with the ticker's volatility, and on the fixture 3 x ATR(14)
  exceeded 8% of price on 3.5% (SPY) to 4.7% (QQQ, IWM) of sessions, all in the highest-volatility
  stretch, where the 8% cap, not the ticker's own reach, set the window. Measuring from the prior
  close, not pre_vwap, is deliberate: daily history has no premarket for 2015 to 2026, and the
  prior close includes the gap, which makes the window wider, not narrower.
- Spike threshold. A premarket wick farther beyond the bodies around it than 99.9% of the ticker's
  regular-session wicks is not a move the ticker makes in a minute. Regular-session bars are used
  because their tape is consolidated and far deeper, so their tail is genuine price discovery; the
  rare bad print there sits beyond the 0.999 quantile of about 23,000 wicks. On 2026-11-06 the bad
  08:05 prints sat 2.96 (SPY), 1.75 (QQQ) and 2.59 (IWM) ATR(14) beyond the surrounding bodies,
  while the largest other wicks that morning were 0.37, 0.63 and 0.28 ATR; the fixed 0.5 rule also
  drops QQQ's 0.63 wick (excluded_spike_prints 2 for QQQ, 1 for SPY and IWM), which may be real.
- Stale prior-close threshold. A real print on the prior close can lie no farther from its bar's
  midpoint than the bar's own prints usually do. On 2026-11-06 the 95th percentile of that spread
  over clean premarket bars was SPY 0.128, QQQ 0.133 and IWM 0.040 ATR(14), against 0.1 today; QQQ's
  prior-close prints sat 0.34 to 0.75 ATR from their bars' midpoints, so all are dropped at 0.133,
  and SPY's and IWM's prior-close prints lie inside the real premarket range, so their pre_high and
  pre_low do not depend on the threshold. One session is an illustration; the job uses 60.
- Level cluster tolerance. Two levels closer than the ticker's typical 15-minute move trade as one
  zone. Today's 0.15% of price is about 0.14 ATR(14) for SPY (ATR(14) a median 1.08% of price on the
  fixture) and 0.09 for IWM (1.67%).
- Entry buffers. An edge at follow-through quantile q is a distance that a share 1 minus q of breaks
  run at least as far as before they retest. The upper edge is how far past the trigger the persona
  will chase: aggressive 0.75 (a quarter of breaks run past it), neutral 0.50 (half do). The
  conservative lower edge, at 0.20, waits for follow-through that about 80% of breaks reach, and its
  upper edge, at 0.65, is passed by about 35%. Copy that explains an edge states the share that
  reached it, never the quantile as that share. The persona shares are policy.
- Stops and the floor. A stop inside the adverse excursion that a given share of held breaks
  survived stops out the rest of those winners. The floor at the median means no stop sits where it
  would have been hit on half of the breaks that held. This keeps today's ordering (2.0 over 1.0
  over 0.7 over 0.5) as an ordering of quantiles.
- Targets. An R multiple is a reward-for-risk demand, not a property of the ticker. The
  ticker-derived form that is defensible is a reach probability: T_k is the excursion, in the
  persona's own R, that share p_k of past filled breaks reached, measured from the fill, before the
  stop. Conditioning on the fill matters: a conservative entry about 0.4 ATR past the trigger is
  filled by only part of the breaks, and counting the unfilled ones would ask for a reach share no
  positive target can meet, producing a target at or below the entry. This spec takes that form
  (Open question 4 keeps the alternative: R multiples as persona policy rows, with each multiple's
  measured reach rate shown beside it). The aggressive analog day-5 stretch
  (lib/agents/trade_planner.py:299-306) stays.

Calibration order per ticker and as-of date: trigger windows, then the replayed triggers and
breaks they imply, then entry buffers, then each persona's fills at its entry midpoint, then stops and the
floor, then targets; the three
one-minute thresholds are independent. Every input is dated strictly before effective_from.

Removed with no parameter: MIN_ROOM_PCT and compute_room_to_run (dead code, item 3) and
PlanContext.safe_atr (item 12). A side with a trigger always has a positive ATR, because the builder
returns atr_unavailable otherwise; the planner raises PlanContextUnavailable if it ever sees a
trigger without one.

### 3. One loader, read once per run

`lib.strat_levels.load_level_params(query_fn, tickers, session_date) -> Dict[str, LevelParams]`.
One query for all tickers: the policy rows and, per (ticker, param_key), the row with the greatest
effective_from on or before session_date. Cached per (frozenset(tickers), session_date) for the run.
LevelParams exposes `value(key)` only for status ok and `status(key)` always; a caller that asks for
the value of a non-ok key gets LevelParamUnavailable naming the key, the status and the sample, and
the builder and planner turn that into the typed outcomes of Design 6.

A missing table, a failed query or an empty policy table raises LevelParamsUnavailable (an INTERNAL
failure under CLAUDE.md 3.7): the brief job exits non-zero before writing any row, the insight run
is marked failed with reason level_params_unavailable, and the signal monitor skips that cycle's
level refresh with the reason in its status. A ticker with no rows is a data state: status
params_unavailable for every key. There is no default row and no constant behind the loader.

`build_session_levels(ticker, session_date, daily_df, atr, premarket, params, reference=None)`
takes the ticker's LevelParams as a required argument. `_within_staleness_window(level, reference,
atr, window_atr)` takes the side's window: a level above the reference uses
trigger_window_long_atr, a level below uses trigger_window_short_atr (so a long's stop, below the
reference, is windowed by the short value). detect_level_clusters takes tolerance_atr and atr.
calculate_premarket_context takes stale_print_atr and spike_atr. compute_persona_plans reads the
persona keys from the ticker's LevelParams carried on PlanContext.

On-demand tickers: when an insight run's ticker has no ticker_level_params rows, the run calls
lib.level_calibration.calibrate_ticker for it before planning and writes the rows with source
on_demand. Daily-bar parameters calibrate for any ticker with 250 sessions of bars; one-minute ones
come out insufficient_history unless the ticker has one-minute bars.

### 4. ATR(5) next to ATR(14)

lib/config.py IndicatorConfig.atr_extra_periods becomes [5, 20]; add_all_indicators then emits
ATR5. gcp/database.py DAILY_INDICATOR_TO_SQL_COLUMN maps ATR5 to atr_5; gcp/schema.sql adds
`market_data_daily.atr_5 DOUBLE PRECISION` (ADD COLUMN IF NOT EXISTS) beside atr_14; lib/data_loader.py
selects atr_5 and maps it to ATR5. Because backfill_daily_indicators derives its gap list from that
mapping, atr_5 joins its short warmup class and the nightly self-heal; the Sunday full sweep fills
history once the column exists. The nightly fetch-market-data path is the refresh: same job, same
universe, same night as atr_14.

The policy row atr_basis names the ATR column every parameter is measured in and every consumer
multiplies by; day one is atr_14, so the unit does not change. level_basis records atr_14, atr_5
and atr_basis. Switching to atr_5 is a policy row with a later effective_from; the next calibration
run recomputes every value in ATR(5) units (Open question 2). Every ticker_level_params row records
the atr_basis it was calibrated in, and the loader uses a row only when that basis equals the policy
basis in force on the session. A ticker whose recalibration failed is therefore not read in the
wrong unit: its keys get params_basis_mismatch, a non-ok status with the typed outcomes of Design 6,
until a run in the new basis succeeds. To keep that window short, the basis switch is applied by
running history mode for the new basis first and adding the policy row only after every universe
ticker has rows in it. Evidence: on the daily fixture ATR(5)
predicted the next session's true range with a mean absolute error of 2.92 against 3.13 (SPY), 3.50
against 3.65 (QQQ) and 1.43 against 1.48 (IWM) for ATR(14); the #1747 spec's 2015 to 2026 check
found ATR(5) about 4% sharper.

### 5. One-minute bars for the calibration universe

The calibration universe is the brief tickers (lib/config.py MarketConfig.tickers), the insight
default tickers (gcp/insight_pipeline_job.py DEFAULT_TICKERS) and the watchlist, resolved at run
time (`lib.level_calibration.load_calibration_universe`), plus any ticker with on_demand rows.
gcp/fetchers/fetch_alphavantage_intraday.py resolves --symbol=ALL to the first three sources
instead of SYMBOLS, so av-intraday-nightly stores 1-minute regular and extended bars for every
watchlist ticker as it does for SPY, IWM and QQQ. A new watchlist ticker has no one-minute history
until it accrues; its one-minute parameters stay insufficient_history for 40 sessions unless an
operator runs the existing bulk backfill for it.

### 6. When a parameter is not ok

| Parameter not ok | Outcome | Shown as |
|---|---|---|
| trigger_window_* | that side has no trigger, reason params_insufficient_history (or params_unavailable) | ORB_ONLY_COPY row naming the parameter, sample_n and minimum, in the brief banner, the planner rationale and the Discord push |
| pm_spike_atr or pm_stale_print_atr | the fetchers write pre_filter_status params_unavailable or insufficient_history with excluded counts NULL; the builder refuses the snapshot and builds with the prior close as reference | premarket_status premarket_unfiltered in level_basis and the brief; a reader that shows that row's pre_high or pre_low labels it unfiltered |
| level_cluster_atr | no PMG zones | the brief's PMG line says the tolerance is not calibrated |
| entry, stop, floor or target keys | persona plans with entry_zone, stop, targets and risk_metrics null | rationale naming the parameter; the report headline nulls as in #1753 |
| target_{persona}_2_r or _3_r with status no_positive_target | the persona's plan publishes its earlier targets and none from that k on (no_positive_target at k = 1 nulls the plan as the row above) | rationale saying no further target met the persona's reach share on filled breaks, with the sample |
| any key with status params_basis_mismatch | the same outcome as insufficient_history for that key, reason params_basis_mismatch | copy saying the ticker's values are being recalibrated for the new ATR basis |

Every value a plan or brief publishes comes from an ok row whose version is in level_basis.

### 7. Calibration job

`gcp/calibrate_level_params.py`, a Cloud Run job `calibrate-level-params`.

- Nightly mode at 04:00 ET Tuesday to Saturday: after av-intraday-nightly (21:00 ET), fetch-market-data
  (23:00 ET) and backfill-daily-indicators (02:30 ET) have written the session, and before
  auto-refresh-top-n (08:10 ET), fetch-premarket-refresh (08:20 ET) and the brief (08:30 ET). Each
  run writes, per universe ticker and parameter, one row effective on the next session, with the
  input range, sample size, method, run id and status. Rerunning the same night converges (ON
  CONFLICT DO UPDATE).
- History mode, run once at rollout and on any policy change: per ticker one read of its daily bars
  and one of its 1-minute bars for 2015-01-02 onward, then rolling statistics in memory, writing one
  version per session with inputs strictly before it. Replays then read the version in force on
  their session.
- Per ticker: one batched daily read, one batched 1-minute read, one write batch; a ticker whose read
  fails is logged and skipped, and the run exits non-zero; progress is logged per ticker.

### 8. level_basis

level_basis gains `params` (per key used: value, status, effective_from, method_id, sample_n,
input_from, input_to, run_id), `policy_effective_from`, `atr_14`, `atr_5` and `atr_basis`, and its
rule_version moves to a new value, so the movement statement's reach rates count only rows built
under calibrated parameters (the #1753 rule_version filter). SessionLevels.from_basis rebuilds with
the recorded params and never reads the tables, so a stored brief's picks do not move when a later
calibration run writes new rows. The premarket snapshot records pre_filter_status and the two
thresholds' value and effective_from (new nullable market_data_daily columns pre_filter_status and
pre_filter_params JSONB).

### 9. Delivery split

The gate refuses a deploy file on a FEAT-STRAT-001 branch (scripts/gate/spec_gate.py:1098-1099,
DEPLOY_FEAT). So the implementation PR carries the code, schema, tests and the job module; the
calibrate-level-params job definition, its scheduler entry and the av-intraday-nightly arguments in
gcp/deploy.sh come in a companion FEAT-DEPLOY-001 spec and PR. Production steps follow the
Close-out order.

Jobs to redeploy: premarket-brief, fetch-premarket-refresh, fetch-market-data,
backfill-daily-indicators, fetch-alphavantage-intraday, insight-pipeline, auto-refresh-top-n,
signal-monitor (and signal-replay), premarket-playbook-resolver, insight-discord-push, the new
calibrate-level-params, and the API image.

## Open questions for the owner

Each has a default this spec takes; a different answer is a policy row or a one-line change.

1. Policy quantiles. Defaults as in the Design 2 table: windows cover 99% of sessions; the spike
   threshold sits past 99.9% of regular-session wicks; stops survive 90%, 75% and 60% of filled held
   breaks; the floor 50%. These are statements of intent, not ticker values, and are rows.
2. ATR basis. Default atr_14 (no unit change on day one). Alternative: atr_5, which the evidence
   says is slightly sharper.
3. Break-derived parameters pool both sides. Default pooled, for sample size. Alternative: per side
   where each side has 150 breaks.
4. Targets. Default reach-probability targets. Alternative: R multiples as persona policy rows with
   their measured reach rates shown.
5. Premarket values for tickers outside the calibration universe (earnings-window names the nightly
   fetcher covers). Default: written unfiltered and labelled unfiltered. Alternative: add every
   earnings-window ticker to the one-minute refresh, at the cost in Capacity.
6. Thin history. Default: insufficient_history, no stand-in. Alternative: a visible peer-group value
   (for example the pooled value of the ticker's sector ETF), flagged as such in level_basis and
   the output.
7. Calibration cadence. Default nightly. Alternative: weekly, which moves picks less often.

## Expected effect

Picks change on day one; done_when 14 counts the changes against #1753 over 2015 to 2026. From the
fixture evidence: the trigger windows narrow from 3.0 to about 2.1 to 2.6 ATR(14) for IWM, QQQ and
SPY, so a nearest unbroken level between that value and 3 ATR becomes orb_only
next_level_outside_window, and the percent cap no longer clips the window in volatile stretches. The
premarket filter's thresholds differ by ticker (on 2026-11-06 about 0.13 ATR for SPY and QQQ and
0.04 for IWM on the stale-print test). Persona stops, entries and targets move to values measured
on each ticker's own breaks. Copy states the ticker's own window and its coverage.

## Capacity and cost

- Volume: 23 parameter keys per ticker per night (2 windows, 3 one-minute thresholds, 6 entry
  edges, 3 stops, 1 floor, 8 targets), about 200 bytes a row; at 30 universe tickers that is 690 rows
  and about 140 KB a night, about 35 MB a year. History mode writes 23 x 2,970 sessions x 3 index
  ETFs, about 205,000 rows and 41 MB, plus 2 daily-bar keys per session for the other universe
  tickers. atr_5 adds 8 bytes per market_data_daily row. One-minute bars for the watchlist add about
  960 rows per ticker per session: 29,000 rows a night at 30 tickers, about 0.6 GB a year.
- Velocity: 2 batched reads and 1 write batch per ticker per calibration run; 1 query per run for all
  tickers in each consumer (brief, planner, monitor, resolver, movement statement, both premarket
  fetchers); 2 Alpha Vantage calls per added watchlist ticker per night (current and previous
  month), 60 calls at 30 tickers, under the 150 per minute premium limit.
- Wall-clock: nightly mode reads up to 750 sessions of RTH 1-minute bars per ticker (about 292,000
  rows, 5 to 15 s over pg8000 and the connector) plus in-memory replay of 750 builder calls (under
  2 s), so 1 to 9 minutes for 30 tickers; task-timeout 1,800 s. History mode reads about 1.16 million
  RTH rows per index ETF (30 to 60 s) and computes rolling statistics in memory (about 2 minutes),
  about 10 minutes for the three; run with a 3,600 s override. Memory: about 60 MB per ticker in
  flight; 2 GiB.
- Cost: 1 new scheduled job at 1 vCPU and 2 GiB for under 10 minutes, about $0.01 a run, 5 runs a
  week, about $0.25 a month; the one-minute refresh uses Alpha Vantage calls already paid for by the
  subscription; storage under 1 GB a year.

## Source identity and close-out

The implementation PR binds DASHBOARD-01 (brief), DASHBOARD-21 (movement statement), INSIGHTS-01,
INSIGHTS-07 and INSIGHTS-08 (planner, live and replay) as done_when 16 states. After merge, in this
order and each production step only after the owner's yes: apply the two tables, the atr_5 column
and the two pre_filter columns; seed the policy rows; run the atr_5 history backfill
(backfill-daily-indicators full mode); run calibrate-level-params in history mode; merge and deploy
the FEAT-DEPLOY-001 companion (job, scheduler, av-intraday-nightly universe); then the staging
deploy of this change. Then real queries showing, for SPY, QQQ and IWM, the parameter rows in force
for the next session, a brief row and an insight report for one session whose level_basis carries
the same parameter versions, and the nightly job's rows advancing on two consecutive nights. Those
post-merge steps are close-out, not pre-merge done_when boxes.

## Risks

- Picks change on many sessions. done_when 14 shows the counts per ticker and side, and done_when 4
  shows each value beside the constant it replaces.
- A threshold calibrated on contaminated data. A bad print inside the regular-session tail, or a
  vendor change, moves pm_spike_atr; the PR lists every bar each threshold drops on 20 sessions, and
  the policy quantile is a row the owner can change.
- Look-ahead in history mode would make replays look better than live. done_when 3 tests that bars on
  or after the effective date change nothing.
- Circularity: break-derived values depend on triggers, which depend on the windows. The fixed
  calibration order (windows first) breaks the loop.
- Day-to-day drift: nightly versions can move a pick between days with no market change. The 750
  session lookback keeps daily moves small; level_basis records the version; Open question 7 offers
  weekly.
- A missing table stops the brief. That is intended (CLAUDE.md 3.7); the Close-out order applies the
  tables and history rows before any code that reads them deploys.
- Non-universe tickers' premarket values are unfiltered and labelled so (Open question 5).
- solyra must render the new insufficient-history and unfiltered states; the null plan fields
  already exist from #1753. The companion solyra change merges before the API image deploys.
- Watchlist growth raises Alpha Vantage calls and intraday rows linearly; the Capacity numbers are
  per 30 tickers.
