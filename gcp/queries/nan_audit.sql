-- NaN/NULL audit sweep — Deliverable A2.
-- Dynamically scans EVERY double precision / real column in the public schema
-- for IEEE float8 NaN (the §3.7 silent-fallback bug class) and NULL coverage.
-- Emits one row per (table, column) that has any float8 NaN, plus a per-column
-- NULL summary. Read-only; run via ./scripts/db_query_cr.sh -f gcp/queries/nan_audit.sql
DO $$
DECLARE
    r   RECORD;
    nan_ct   BIGINT;
    null_ct  BIGINT;
    tot_ct   BIGINT;
BEGIN
    CREATE TEMP TABLE _nan_audit (
        table_name text, column_name text, data_type text,
        total_rows bigint, null_ct bigint, nan_ct bigint
    ) ON COMMIT DROP;

    FOR r IN
        SELECT c.table_name, c.column_name, c.data_type
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND c.data_type IN ('double precision', 'real')
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.ordinal_position
    LOOP
        EXECUTE format(
            'SELECT count(*), '
            'count(*) FILTER (WHERE %1$I IS NULL), '
            'count(*) FILTER (WHERE %1$I = ''NaN''::float8) '
            'FROM public.%2$I',
            r.column_name, r.table_name
        ) INTO tot_ct, null_ct, nan_ct;

        INSERT INTO _nan_audit
        VALUES (r.table_name, r.column_name, r.data_type, tot_ct, null_ct, nan_ct);
    END LOOP;
END $$;

-- Result 1: every column that STILL holds float8 NaN (the bug class).
SELECT table_name, column_name, total_rows, nan_ct,
       round(100.0 * nan_ct / NULLIF(total_rows, 0), 2) AS nan_pct
FROM _nan_audit
WHERE nan_ct > 0
ORDER BY nan_ct DESC, table_name, column_name;
