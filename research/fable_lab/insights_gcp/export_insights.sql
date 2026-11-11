-- Read-only export for the insight pipeline review. SELECT only: nothing here writes.
-- Paste into a psql session on the trading database, one statement at a time, e.g.
--   \copy (<statement without the trailing semicolon>) TO 'insight_reports_full.csv' CSV HEADER
-- Each statement returns one JSON column named "row", the same shape as the Nov 11 export.
-- Optional safety for the session (still read-only):
--   SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

-- 1. Every canonical report ever written (the table the UI and Discord read).
SELECT row_to_json(t) AS row
FROM (
  SELECT id, ticker, as_of, created_at, run_kind, cost_usd, latency_ms,
         model_versions, per_role_cost, report
  FROM insight_reports
  ORDER BY as_of
) t;

-- 2. Append-only history: every run attempt, including duplicates, replays and
--    manual runs (insight_reports keeps one row per (ticker, as_of) only).
SELECT row_to_json(t) AS row
FROM (
  SELECT id, insight_run_id, ticker, as_of, written_at, run_kind, triggered_by,
         notes, cost_usd, latency_ms, model_versions, per_role_cost, report
  FROM insight_reports_history
  ORDER BY as_of, written_at
) t;

-- 3. Run audit: which runs failed or never finished, and how each was triggered.
SELECT row_to_json(t) AS row
FROM (
  SELECT id, ticker, status, trigger, started_at, finished_at, error, report_id
  FROM insight_runs
  ORDER BY started_at NULLS LAST
) t;

-- 4. Which model each role used, and when that was last changed.
SELECT row_to_json(t) AS row
FROM (
  SELECT role, provider, model, updated_at, updated_by
  FROM model_routing
  ORDER BY role
) t;

-- 5. Outcome side: there is no table that scores insight reports. The only
--    resolver (premarket-playbook-resolver) scores the 8:30 brief, writing hit
--    timestamps onto premarket_analysis. Pull those for the same dates so the
--    brief and the insight can be compared side by side.
SELECT row_to_json(t) AS row
FROM (
  SELECT p.*
  FROM premarket_analysis p
  WHERE p.analysis_date >= (SELECT MIN(as_of)::date FROM insight_reports)
  ORDER BY p.analysis_date, p.ticker
) t;

-- 6. Quick sanity count before exporting (rows per month and model).
SELECT date_trunc('month', as_of) AS month,
       model_versions->>'portfolio_manager' AS pm_model,
       COUNT(*) AS reports,
       COUNT(DISTINCT (ticker, as_of::date)) AS ticker_days,
       ROUND(SUM(cost_usd)::numeric, 3) AS cost_usd
FROM insight_reports
GROUP BY 1, 2
ORDER BY 1, 2;
