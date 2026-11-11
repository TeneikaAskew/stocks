SELECT row_to_json(t) AS row
FROM (
  SELECT id, ticker, as_of, created_at, run_kind, cost_usd, latency_ms,
         model_versions, per_role_cost, report
  FROM insight_reports
  ORDER BY as_of
) t;
SELECT row_to_json(t) AS row
FROM (
  SELECT id, insight_run_id, ticker, as_of, written_at, run_kind, triggered_by,
         notes, cost_usd, latency_ms, model_versions, per_role_cost, report
  FROM insight_reports_history
  ORDER BY as_of, written_at
) t;
SELECT row_to_json(t) AS row
FROM (
  SELECT id, ticker, status, trigger, started_at, finished_at, error, report_id
  FROM insight_runs
  ORDER BY started_at NULLS LAST
) t;
SELECT row_to_json(t) AS row
FROM (
  SELECT role, provider, model, updated_at, updated_by
  FROM model_routing
  ORDER BY role
) t;
SELECT row_to_json(t) AS row
FROM (
  SELECT p.*
  FROM premarket_analysis p
  WHERE p.analysis_date >= (SELECT MIN(as_of)::date FROM insight_reports)
  ORDER BY p.analysis_date, p.ticker
) t;
SELECT date_trunc('month', as_of) AS month,
       model_versions->>'portfolio_manager' AS pm_model,
       COUNT(*) AS reports,
       COUNT(DISTINCT (ticker, as_of::date)) AS ticker_days,
       ROUND(SUM(cost_usd)::numeric, 3) AS cost_usd
FROM insight_reports
GROUP BY 1, 2
ORDER BY 1, 2;;
