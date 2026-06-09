-- Gamma rename + gamma_flip migration (2026-06-09). Idempotent: re-runnable.
-- Renames flip_price -> gamma_balance_price and adds the true BS gamma_flip
-- column across gamma_levels_eod + the 6 strat_features_{tf} tables. Also
-- migrates the level_kind='flip' row value -> 'gamma_balance' and widens
-- level_kind so 'gamma_balance' fits. ALTER RENAME preserves data (the old
-- flip_price values become gamma_balance_price — correct, that IS the balance).
-- Run with --commit.
DO $$
DECLARE
    t text;
    feat_tables text[] := ARRAY[
        'strat_features_1m','strat_features_5m','strat_features_15m',
        'strat_features_30m','strat_features_60m','strat_features_4h'
    ];
BEGIN
    -- ── gamma_levels_eod ────────────────────────────────────────────────
    -- widen level_kind so 'gamma_balance' (13 chars) fits
    EXECUTE 'ALTER TABLE gamma_levels_eod ALTER COLUMN level_kind TYPE VARCHAR(20)';
    -- rename flip_price -> gamma_balance_price (guarded)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='gamma_levels_eod' AND column_name='flip_price')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='gamma_levels_eod' AND column_name='gamma_balance_price') THEN
        EXECUTE 'ALTER TABLE gamma_levels_eod RENAME COLUMN flip_price TO gamma_balance_price';
    END IF;
    EXECUTE 'ALTER TABLE gamma_levels_eod ADD COLUMN IF NOT EXISTS gamma_flip DOUBLE PRECISION';
    -- migrate the row value + tag (escaped single quotes — no nested $-quote)
    EXECUTE 'UPDATE gamma_levels_eod SET level_kind=''gamma_balance'', '
            'tags=CASE WHEN tags=''flip'' THEN ''gamma_balance'' ELSE tags END '
            'WHERE level_kind=''flip''';

    -- ── strat_features_{tf} ─────────────────────────────────────────────
    FOREACH t IN ARRAY feat_tables LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name=t AND column_name='flip_price')
           AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name=t AND column_name='gamma_balance_price') THEN
            EXECUTE format('ALTER TABLE %I RENAME COLUMN flip_price TO gamma_balance_price', t);
        END IF;
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS gamma_flip DOUBLE PRECISION', t);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS dist_to_gamma_flip_pct DOUBLE PRECISION', t);
    END LOOP;
END $$;
