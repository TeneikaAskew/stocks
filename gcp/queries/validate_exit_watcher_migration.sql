-- Validation harness for the exit-watcher + brief-bias schema migration.
-- Wraps the migration in a DO block so the partial index CREATE can see
-- the column ADD inside the same statement (the db-query workflow runs
-- inline statements in separate transactions, which would defeat the
-- index validation otherwise).
--
-- Dispatch with commit=false so this leaves no trace; the whole DO block
-- runs, the validation SELECTs prove the schema is well-formed, and the
-- rollback unwinds it. Production application uses apply_schema.py which
-- commits each statement individually -- that path already works because
-- the ALTER TABLE commits before the CREATE INDEX runs.

DO $$
DECLARE
    cnt INTEGER;
    idx_def TEXT;
BEGIN
    -- Apply both migration blocks against the live signal_alerts table.
    -- IF NOT EXISTS makes them idempotent (no-op if already applied).
    ALTER TABLE signal_alerts
        ADD COLUMN IF NOT EXISTS exit_ts          TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS exit_reason      VARCHAR(32),
        ADD COLUMN IF NOT EXISTS exit_price       DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS exit_return_pct  DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS is_open          BOOLEAN,
        ADD COLUMN IF NOT EXISTS brief_bias        VARCHAR(16),
        ADD COLUMN IF NOT EXISTS brief_alignment   VARCHAR(16),
        ADD COLUMN IF NOT EXISTS brief_setup_count INTEGER;

    -- Partial index: only indexes rows where is_open IS TRUE. Standard
    -- PG syntax (https://www.postgresql.org/docs/current/indexes-partial.html).
    CREATE INDEX IF NOT EXISTS idx_signal_alerts_open
        ON signal_alerts (ticker, alert_ts) WHERE is_open IS TRUE;

    -- Verify all 8 columns landed.
    SELECT count(*) INTO cnt
      FROM information_schema.columns
     WHERE table_name = 'signal_alerts'
       AND column_name IN (
        'exit_ts', 'exit_reason', 'exit_price', 'exit_return_pct',
        'is_open', 'brief_bias', 'brief_alignment', 'brief_setup_count'
       );
    IF cnt != 8 THEN
        RAISE EXCEPTION 'Expected 8 new columns on signal_alerts, found %', cnt;
    END IF;
    RAISE NOTICE 'OK: all 8 new columns present on signal_alerts';

    -- Verify the partial index landed with the right WHERE clause.
    SELECT pg_get_indexdef(c.oid)
      INTO idx_def
      FROM pg_class c
     WHERE c.relname = 'idx_signal_alerts_open';
    IF idx_def IS NULL THEN
        RAISE EXCEPTION 'Partial index idx_signal_alerts_open was not created';
    END IF;
    IF idx_def NOT LIKE '%WHERE%is_open%' THEN
        RAISE EXCEPTION 'Index definition missing WHERE is_open clause: %', idx_def;
    END IF;
    RAISE NOTICE 'OK: partial index landed with definition: %', idx_def;
END $$;

-- One row out so the workflow summary shows something definitive.
SELECT 'exit_watcher + brief_bias migration validated' AS result;
