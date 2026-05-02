-- Per-table size and approximate row count for the connected database.
-- Drop-in equivalent of psql's `\dt+` plus index sizes.
-- Sorted largest-first so the heaviest tables surface immediately.
SELECT
  schemaname || '.' || relname                                         AS "table",
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname))     AS total,
  pg_size_pretty(pg_relation_size(schemaname||'.'||relname))           AS table_only,
  pg_size_pretty(pg_indexes_size(schemaname||'.'||relname))            AS indexes,
  n_live_tup                                                            AS approx_rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname||'.'||relname) DESC
