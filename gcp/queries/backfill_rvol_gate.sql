-- Backfill signal_alerts.rvol_gate for rows that predate the gate (PR #774,
-- first live stamps 2026-08-26). The verdict is a pure function of the stored
-- fire-time rvol and the gate config (rvol_gate_min = 1.0), so historical
-- rows are reconstructable exactly as gcp/signal_monitor.py:rvol_gate_verdict
-- would have stamped them in shadow mode:
--   rvol >= 1.0        -> 'pass'
--   rvol <  1.0        -> 'below'
--   rvol NULL or NaN   -> 'below'  (unconfirmed volume is what the gate
--                                   exists to flag; NaN never passes, §3.7)
-- NaN note (Codex P1, PR #802): PostgreSQL treats float NaN as equal to
-- itself and GREATER than every finite number, so a bare `rvol >= 1.0`
-- would stamp NaN rows 'pass'. The explicit `rvol <> 'NaN'::float8` guard
-- keeps parity with the Python verdict. (The 2026-08-27 production run
-- predated this guard; verified zero NaN rvol rows existed, so no row was
-- mis-stamped.)
-- Provenance cutoff (Codex P2, PR #802): scope to alert_date BEFORE the
-- first live stamp so a rerun after any future rvol_gate_mode='off' period
-- cannot rewrite deliberately-NULL off-mode rows. Live stamps are never
-- overwritten (rvol_gate IS NULL) and the statement is idempotent.
--
-- Purpose (2026-08-27 live-performance review): the shadow-mode dataset was
-- 2 days old and self-contradictory (below-gate 2/12 on 08-26, 8/10 on
-- 08-27); the full-history reconstruction over 2,918 resolved fires showed
-- the gate's sign flips month-to-month with no dose-response across RVOL
-- bands (analysis queries: gcp/queries/rvol_gate_analysis.sql). Persisting
-- the reconstructed verdicts makes every future GROUP BY (including the
-- alignment x gate interaction once brief_alignment accumulates) run
-- against the complete series without re-deriving.
--
-- Dispatch: ./scripts/db_query_cr.sh -f gcp/queries/backfill_rvol_gate.sql --commit
UPDATE signal_alerts
SET rvol_gate = CASE
    WHEN rvol IS NOT NULL AND rvol <> 'NaN'::float8 AND rvol >= 1.0 THEN 'pass'
    ELSE 'below'
END
WHERE rvol_gate IS NULL
  AND alert_date < DATE '2026-08-26'
