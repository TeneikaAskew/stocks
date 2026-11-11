-- Insights lane: production reads needed. Every statement is a read only SELECT. Nothing here writes.
-- Run from the owner's GCP session against the trading database (Cloud SQL, Postgres). Not run by this lane.
-- Suggested safety line for the session:  SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
-- Export each result as CSV (psql: \copy (<statement without the semicolon>) TO 'qNN.csv' CSV HEADER).

-- Q01 How many insight reports exist per month and per model (tells us how many days the model's direction can be scored on).
SELECT date_trunc('month', as_of AT TIME ZONE 'America/New_York')::date AS month, run_kind, model_versions->>'portfolio_manager' AS pm_model, COUNT(*) AS reports, COUNT(DISTINCT (ticker, (as_of AT TIME ZONE 'America/New_York')::date)) AS ticker_days FROM insight_reports GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- Q02 One row per report with the model decided fields (direction, confidence, horizon) and the rule decided headline plan, for SPY, QQQ, IWM: the input for scoring the model's direction on every stored day.
SELECT id, ticker, as_of, (as_of AT TIME ZONE 'America/New_York')::date AS session_et, to_char(as_of AT TIME ZONE 'America/New_York', 'HH24:MI') AS run_time_et, run_kind, report->>'direction' AS direction, report->>'conviction' AS conviction, report->>'confidence_score' AS confidence_score, report->>'time_horizon' AS time_horizon, report->>'regime' AS regime, report->'entry_zone'->>'low' AS entry_low, report->'entry_zone'->>'high' AS entry_high, report->>'stop' AS stop, report->'targets' AS targets, report->'strat_status'->>'ftfc_score' AS ftfc_score, (report->'level_basis') IS NOT NULL AS has_level_basis, report->'failed_sections' AS failed_sections, cost_usd, latency_ms, model_versions->>'portfolio_manager' AS pm_model FROM insight_reports WHERE ticker IN ('SPY', 'QQQ', 'IWM') ORDER BY as_of;

-- Q03 The three persona plans of every report, one row per persona (entry zone, stop, targets, size): lets us check the local rebuild against what production really published.
SELECT r.id, r.ticker, (r.as_of AT TIME ZONE 'America/New_York')::date AS session_et, r.report->>'direction' AS direction, p->>'persona' AS persona, p->>'regime' AS plan_regime, p->'entry_zone'->>'low' AS entry_low, p->'entry_zone'->>'high' AS entry_high, p->>'stop' AS stop, p->'targets' AS targets, p->>'position_size_pct' AS size, p->'risk_metrics'->>'stop_distance_atr' AS stop_distance_atr, p->>'rationale' AS rationale FROM insight_reports r CROSS JOIN LATERAL jsonb_array_elements(r.report->'persona_plans') AS p WHERE r.ticker IN ('SPY', 'QQQ', 'IWM') ORDER BY r.as_of, p->>'persona';

-- Q04 The trigger the insight used and the ladder it could have used (from the stored level_basis): answers "which level did Insights trade from, and what were the next levels".
SELECT id, ticker, (as_of AT TIME ZONE 'America/New_York')::date AS session_et, report->>'direction' AS direction, report->'level_basis'->>'status' AS levels_status, report->'level_basis'->>'atr' AS atr, report->'level_basis'->>'reference' AS reference, report->'level_basis'->>'reference_source' AS reference_source, report->'level_basis'->'premarket' AS premarket, report->'level_basis'->'long'->'trigger' AS long_trigger, report->'level_basis'->'long'->'targets' AS long_ladder_targets, report->'level_basis'->'long'->>'reason' AS long_reason, report->'level_basis'->'short'->'trigger' AS short_trigger, report->'level_basis'->'short'->'targets' AS short_ladder_targets, report->'level_basis'->'short'->>'reason' AS short_reason FROM insight_reports WHERE ticker IN ('SPY', 'QQQ', 'IWM') AND report->'level_basis' IS NOT NULL ORDER BY as_of;

-- Q05 Same morning repeats: how often two runs for the same ticker and day gave different directions (the model's flip rate).
SELECT ticker, (as_of AT TIME ZONE 'America/New_York')::date AS session_et, COUNT(*) AS runs, COUNT(DISTINCT report->>'direction') AS distinct_directions, string_agg((report->>'direction') || '@' || to_char(written_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS'), ', ' ORDER BY written_at) AS directions, string_agg(DISTINCT run_kind, ',') AS run_kinds FROM insight_reports_history WHERE ticker IN ('SPY', 'QQQ', 'IWM') GROUP BY 1, 2 HAVING COUNT(*) > 1 ORDER BY 2, 1;

-- Q06 Risk reviewer flags per report by persona and severity: shows how often model written "warn" flags push conviction to low (which cuts size) and whether any "block" forced flat.
SELECT r.id, r.ticker, (r.as_of AT TIME ZONE 'America/New_York')::date AS session_et, r.report->>'direction' AS direction, r.report->>'conviction' AS conviction, f->>'persona' AS flag_persona, f->>'severity' AS severity, left(f->>'message', 160) AS message FROM insight_reports r CROSS JOIN LATERAL jsonb_array_elements(r.report->'risk_flags') AS f WHERE r.ticker IN ('SPY', 'QQQ', 'IWM') ORDER BY r.as_of, f->>'persona';

-- Q07 Conviction and direction counts by month: is conviction ever high, and how often is the call flat.
SELECT date_trunc('month', as_of AT TIME ZONE 'America/New_York')::date AS month, ticker, report->>'direction' AS direction, report->>'conviction' AS conviction, COUNT(*) AS reports, ROUND(AVG((report->>'confidence_score')::numeric), 2) AS avg_confidence FROM insight_reports WHERE ticker IN ('SPY', 'QQQ', 'IWM') GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;

-- Q08 The 08:30 brief's call next to the insight's direction for the same ticker and day: answers "direction from the brief vs from the insight" on real stored rows.
SELECT p.analysis_date, p.ticker, p.signal_status AS brief_status, p.ftfc_score AS brief_ftfc, p.calls_trigger_name, p.calls_trigger_price, p.puts_trigger_name, p.puts_trigger_price, i.direction AS insight_direction, i.conviction AS insight_conviction, i.run_time_et FROM premarket_analysis p LEFT JOIN LATERAL (SELECT r.report->>'direction' AS direction, r.report->>'conviction' AS conviction, to_char(r.as_of AT TIME ZONE 'America/New_York', 'HH24:MI') AS run_time_et FROM insight_reports r WHERE r.ticker = p.ticker AND (r.as_of AT TIME ZONE 'America/New_York')::date = p.analysis_date AND r.run_kind = 'live' AND (r.as_of AT TIME ZONE 'America/New_York')::time < TIME '09:30' ORDER BY r.as_of DESC LIMIT 1) i ON TRUE WHERE p.ticker IN ('SPY', 'QQQ', 'IWM') AND p.run_kind = 'live' AND p.analysis_date >= DATE '2026-05-01' ORDER BY p.analysis_date, p.ticker;

-- Q09 The brief's own scored outcomes (trigger, T1, stop hit times) for the same dates: the yardstick the insight plans should be compared with.
SELECT analysis_date, ticker, signal_status, calls_trigger_price, calls_stop_price, calls_t1_price, calls_trigger_hit_ts, calls_t1_hit_ts, calls_stop_hit_ts, calls_eod_pnl_pct, puts_trigger_price, puts_stop_price, puts_t1_price, puts_trigger_hit_ts, puts_t1_hit_ts, puts_stop_hit_ts FROM premarket_analysis WHERE ticker IN ('SPY', 'QQQ', 'IWM') AND run_kind = 'live' AND analysis_date >= DATE '2026-05-01' ORDER BY analysis_date, ticker;

-- Q10 Production's premarket snapshot and ATR per session: checks the local Alpha Vantage premarket high and low and the local ATR against what the live job actually saw.
SELECT ticker, date, open, high, low, close, atr_14, sma_200, pre_high, pre_low, pre_vwap, gap_pct FROM market_data_daily WHERE ticker IN ('SPY', 'QQQ', 'IWM') AND date >= DATE '2025-03-01' ORDER BY date, ticker;

-- Q11 Sessions right after a market holiday: did the brief and the insight publish levels, or did the "stale daily data" rule leave them with no plan (local replay says no plan on 15 such sessions).
SELECT p.analysis_date, p.ticker, p.level_basis->>'status' AS brief_levels_status, p.level_basis->>'last_bar_date' AS last_bar_date, p.calls_trigger_price, p.puts_trigger_price, (SELECT string_agg(DISTINCT r.report->>'regime', ',') FROM insight_reports r WHERE r.ticker = p.ticker AND (r.as_of AT TIME ZONE 'America/New_York')::date = p.analysis_date) AS insight_regimes FROM premarket_analysis p WHERE p.ticker IN ('SPY', 'QQQ', 'IWM') AND p.run_kind = 'live' AND p.analysis_date IN (DATE '2025-04-21', DATE '2025-05-27', DATE '2025-06-20', DATE '2025-07-07', DATE '2025-09-02', DATE '2025-11-28', DATE '2025-12-26', DATE '2026-01-02', DATE '2026-01-20', DATE '2026-02-17', DATE '2026-04-06', DATE '2026-05-26', DATE '2026-06-22', DATE '2026-07-06', DATE '2026-09-08') ORDER BY p.analysis_date, p.ticker;

-- Q12 Runs that failed or never finished, and days with no run at all (for example Nov 2 and Nov 3 are missing from the Nov 11 export).
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS run_date_et, ticker, trigger, status, COUNT(*) AS runs, MAX(left(error, 160)) AS sample_error FROM insight_runs WHERE ticker IN ('SPY', 'QQQ', 'IWM') GROUP BY 1, 2, 3, 4 ORDER BY 1, 2;

-- Q13 Which model each role uses today and when it was last changed (confirms Gemini stays in place; this lane changes nothing here).
SELECT role, provider, model, updated_at, updated_by FROM model_routing ORDER BY role;

-- Q14 High importance economic releases by date and time: tags report days (CPI, jobs, FOMC) so the 08:30 release days can be scored apart from normal days.
SELECT event_date, event_time, event_name, country, importance FROM economic_events WHERE event_date >= DATE '2025-03-01' AND importance = 'high' ORDER BY event_date, event_time;

-- Q15 How often a report section failed (a failed section means the model decided with less data): counts by section and month.
SELECT date_trunc('month', as_of AT TIME ZONE 'America/New_York')::date AS month, s AS failed_section, COUNT(*) AS reports FROM insight_reports r CROSS JOIN LATERAL jsonb_array_elements_text(r.report->'failed_sections') AS s WHERE r.ticker IN ('SPY', 'QQQ', 'IWM') GROUP BY 1, 2 ORDER BY 1, 2;
