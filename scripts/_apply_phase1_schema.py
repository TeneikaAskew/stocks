"""Phase 1 schema migration test driver.

Applies gcp/schema.sql to live Cloud SQL and runs verification checks:
1. New `earnings_history.report_time` column exists
2. New `earnings_reactions` table exists with all expected columns
3. Existing `earnings_history` row count unchanged
4. Apply schema a SECOND time → no errors (idempotent)
5. Existing earnings_history rows still readable + intact
"""
import os
import subprocess
import sys

import psycopg2

GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
DB_HOST = '34.24.66.12'


def secret(name):
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True, timeout=15).rstrip('\n')


def connect():
    return psycopg2.connect(host=DB_HOST, user=secret('db-trading-user'),
                            password=secret('db-trading-pass'),
                            dbname='trading', sslmode='require')


def step(label):
    print(f"\n{'─' * 80}\n  {label}\n{'─' * 80}")


def get_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        return cur.fetchall()


def get_row_count(conn, table):
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]


def get_sample_row(conn, table, where=None, params=()):
    with conn.cursor() as cur:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += " LIMIT 1"
        cur.execute(sql, params)
        return cur.fetchone()


def apply_schema(conn, schema_path):
    with open(schema_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


def main():
    schema_path = 'gcp/schema.sql'
    if not os.path.exists(schema_path):
        sys.exit(f"schema not found: {schema_path}")

    print(f"Phase 1 Schema Migration Test")
    print(f"Schema: {schema_path}")

    conn = connect()
    try:
        # ── PRE-CHECKS ──
        step("PRE-CHECK: capture state before migration")
        eh_count_before = get_row_count(conn, 'earnings_history')
        eh_cols_before = {c[0] for c in get_columns(conn, 'earnings_history')}
        eh_sample_before = get_sample_row(
            conn, 'earnings_history',
            where="ticker = 'AVGO' AND reported_date = '2026-03-04'"
        )
        try:
            er_exists_before = get_row_count(conn, 'earnings_reactions')
        except psycopg2.errors.UndefinedTable:
            er_exists_before = None
            conn.rollback()

        print(f"  earnings_history row count:    {eh_count_before:,}")
        print(f"  earnings_history columns:      {len(eh_cols_before)}")
        print(f"  AVGO 2026-03-04 sample row:    {'present' if eh_sample_before else 'MISSING'}")
        print(f"  earnings_reactions exists:     {er_exists_before is not None}")

        # ── APPLY (FIRST) ──
        step("APPLY (first run): execute gcp/schema.sql")
        apply_schema(conn, schema_path)
        print("  ✓ first apply succeeded")

        # ── POST-CHECKS (1ST APPLY) ──
        step("VERIFY: after first apply")
        eh_count_after = get_row_count(conn, 'earnings_history')
        eh_cols_after = get_columns(conn, 'earnings_history')
        eh_col_names_after = {c[0] for c in eh_cols_after}
        eh_sample_after = get_sample_row(
            conn, 'earnings_history',
            where="ticker = 'AVGO' AND reported_date = '2026-03-04'"
        )

        # 1. row count unchanged
        assert eh_count_after == eh_count_before, \
            f"row count changed! {eh_count_before} -> {eh_count_after}"
        print(f"  ✓ earnings_history row count preserved: {eh_count_after:,}")

        # 2. report_time column exists
        assert 'report_time' in eh_col_names_after, \
            f"report_time column not added! columns: {eh_col_names_after}"
        rt_dtype = next(c[1] for c in eh_cols_after if c[0] == 'report_time')
        print(f"  ✓ earnings_history.report_time added (type={rt_dtype})")

        # 3. existing AVGO row intact (column added with NULL default)
        assert eh_sample_after is not None, "AVGO sample row disappeared!"
        # The new column should be NULL (idx_of_report_time = position in row)
        col_names_in_order = [c[0] for c in eh_cols_after]
        rt_idx = col_names_in_order.index('report_time')
        assert eh_sample_after[rt_idx] is None, \
            f"report_time should be NULL on pre-existing rows, got: {eh_sample_after[rt_idx]}"
        print(f"  ✓ existing rows untouched, report_time defaulted to NULL")

        # 4. earnings_reactions table exists with expected columns
        er_cols = get_columns(conn, 'earnings_reactions')
        er_col_names = {c[0] for c in er_cols}
        expected_er_cols = {
            'id', 'ticker', 'fiscal_date_ending', 'reported_date',
            'reaction_basis', 'reported_eps', 'estimated_eps', 'surprise_pct',
            'd_minus_10_close', 'd_minus_1_close', 'pre_earnings_drift_10d_pct',
            'd_open', 'd_high', 'd_low', 'd_close', 'pre_report_gap_pct',
            'd_plus_1_open', 'd_plus_1_high', 'd_plus_1_low', 'd_plus_1_close',
            'post_gap_pct', 'reaction_gap_pct', 'reaction_anchor_price',
            'reaction_max_run_pct', 'reaction_max_drawdown_pct',
            'd_plus_3_close', 'sustain_3d_pct',
            'd_plus_5_close', 'sustain_5d_pct',
            'd_plus_10_close', 'sustain_10d_pct',
            'direction_consistent_5d', 'is_reversal_5d',
            'inserted_at', 'updated_at',
        }
        missing = expected_er_cols - er_col_names
        extra = er_col_names - expected_er_cols
        assert not missing, f"earnings_reactions missing columns: {missing}"
        if extra:
            print(f"  (note: extra columns present: {extra})")
        print(f"  ✓ earnings_reactions table created with {len(er_col_names)} columns "
              f"({len(expected_er_cols)} expected)")

        # 5. earnings_reactions starts empty
        er_count = get_row_count(conn, 'earnings_reactions')
        assert er_count == 0, f"earnings_reactions should be empty, got {er_count} rows"
        print(f"  ✓ earnings_reactions starts empty")

        # 6. UNIQUE constraint enforced
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = 'earnings_reactions'
                  AND constraint_type = 'UNIQUE'
                  AND constraint_name = 'uq_earnings_reactions'
            """)
            uq_count = cur.fetchone()[0]
        assert uq_count == 1, f"uq_earnings_reactions constraint not found"
        print(f"  ✓ UNIQUE(ticker, fiscal_date_ending) constraint present")

        # 7. CHECK constraint enforced
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = 'earnings_reactions'
                  AND constraint_type = 'CHECK'
                  AND constraint_name = 'ck_earnings_reactions_basis'
            """)
            ck_count = cur.fetchone()[0]
        assert ck_count == 1, "ck_earnings_reactions_basis constraint not found"
        print(f"  ✓ CHECK constraint on reaction_basis present")

        # 8. CHECK constraint actually rejects bad data
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO earnings_reactions
                      (ticker, fiscal_date_ending, reported_date, reaction_basis)
                    VALUES ('TEST', '2024-01-01', '2024-02-01', 'XXX')
                """)
                conn.rollback()
                assert False, "CHECK constraint should have rejected reaction_basis='XXX'"
            except psycopg2.errors.CheckViolation:
                conn.rollback()
                print(f"  ✓ CHECK constraint correctly rejects invalid reaction_basis")

        # 9. CHECK constraint accepts valid values
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO earnings_reactions
                  (ticker, fiscal_date_ending, reported_date, reaction_basis)
                VALUES ('TEST', '2024-01-01', '2024-02-01', 'BMO')
            """)
            cur.execute("""
                INSERT INTO earnings_reactions
                  (ticker, fiscal_date_ending, reported_date, reaction_basis)
                VALUES ('TEST', '2024-04-01', '2024-05-01', 'AMC')
            """)
            cur.execute("""
                INSERT INTO earnings_reactions
                  (ticker, fiscal_date_ending, reported_date, reaction_basis)
                VALUES ('TEST', '2024-07-01', '2024-08-01', NULL)
            """)
            cur.execute("DELETE FROM earnings_reactions WHERE ticker = 'TEST'")
            conn.commit()
        print(f"  ✓ CHECK constraint accepts BMO, AMC, NULL")

        # 10. UNIQUE constraint actually rejects dupes
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO earnings_reactions
                  (ticker, fiscal_date_ending, reported_date)
                VALUES ('TEST', '2024-01-01', '2024-02-01')
            """)
            try:
                cur.execute("""
                    INSERT INTO earnings_reactions
                      (ticker, fiscal_date_ending, reported_date)
                    VALUES ('TEST', '2024-01-01', '2024-02-15')
                """)
                conn.rollback()
                assert False, "UNIQUE should have rejected dup (TEST, 2024-01-01)"
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                print(f"  ✓ UNIQUE constraint rejects duplicate (ticker, fiscal_date_ending)")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM earnings_reactions WHERE ticker = 'TEST'")
            conn.commit()

        # ── APPLY (SECOND) — IDEMPOTENCY ──
        step("APPLY (second run): re-execute schema, expect no errors")
        apply_schema(conn, schema_path)
        print("  ✓ second apply succeeded (idempotent)")

        # ── FINAL VERIFY ──
        step("FINAL VERIFY: state after two applies")
        eh_count_final = get_row_count(conn, 'earnings_history')
        er_count_final = get_row_count(conn, 'earnings_reactions')
        eh_sample_final = get_sample_row(
            conn, 'earnings_history',
            where="ticker = 'AVGO' AND reported_date = '2026-03-04'"
        )

        assert eh_count_final == eh_count_before, \
            f"earnings_history count drifted: {eh_count_before} -> {eh_count_final}"
        print(f"  ✓ earnings_history row count stable: {eh_count_final:,}")

        assert er_count_final == 0, \
            f"earnings_reactions should still be empty, got {er_count_final}"
        print(f"  ✓ earnings_reactions still empty: {er_count_final}")

        assert eh_sample_final is not None, "AVGO sample row disappeared after 2nd apply!"
        # Verify the sample's reported_eps / surprise_pct etc. are intact
        col_names = [c[0] for c in eh_cols_after]
        before_rt_idx = col_names.index('report_time')
        # Compare all columns EXCEPT inserted_at (timestamp may shift on existing rows)
        # and report_time (was added; will be NULL)
        # actually no — ALTER ADD COLUMN doesn't touch existing rows' inserted_at
        # All columns should match exactly.
        for i, name in enumerate(col_names):
            if name == 'report_time':
                continue  # newly-added, NULL
            assert eh_sample_before[i] == eh_sample_final[i], \
                f"AVGO row column {name!r} changed: {eh_sample_before[i]} -> {eh_sample_final[i]}"
        print(f"  ✓ existing AVGO row intact across both applies")

        print(f"\n{'═' * 80}")
        print(f"  ALL PHASE 1 SCHEMA TESTS PASSED")
        print(f"{'═' * 80}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
