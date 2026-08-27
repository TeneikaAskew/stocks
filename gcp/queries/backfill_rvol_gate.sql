-- Backfill signal_alerts.rvol_gate for rows that predate the gate (PR #774,
-- first live stamps 2026-08-26). The verdict is a pure function of the stored
-- fire-time rvol and the gate config (rvol_gate_min = 1.0), so historical
-- rows are reconstructable exactly as gcp/signal_monitor.py:rvol_gate_verdict
-- would have stamped them in shadow mode:
--   rvol >= 1.0        -> 'pass'
--   rvol <  1.0        -> 'below'
--   rvol NULL or NaN   -> 'below'  (unconfirmed volume is what the gate
--                                   exists to flag; NaN never passes, §3.7)
-- Scope: only rows where rvol_gate IS NULL, so live-stamped verdicts are
-- never overwritten and the statement is idempotent. Replay rows are stamped
-- too — the verdict is as-of data, identical under replay by construction.
--
-- Purpose (2026-08-27 live-performance review): the shadow-mode dataset was
-- 2 days old and self-contradictory (below-gate 2/12 on 08-26, 8/10 on
-- 08-27); the full-history reconstruction over 2,918 resolved fires showed
-- the gate's sign flips month-to-month with no dose-response across RVOL
-- bands. Persisting the reconstructed verdicts makes every future GROUP BY
-- (including the alignment x gate interaction once brief_alignment
-- accumulates) run against the complete series without re-deriving.
--
-- Dispatch: ./scripts/db_query_cr.sh -f gcp/queries/backfill_rvol_gate.sql --commit
UPDATE signal_alerts
SET rvol_gate = CASE
    WHEN rvol IS NOT NULL AND rvol = rvol AND rvol >= 1.0 THEN 'pass'
    ELSE 'below'
END
WHERE rvol_gate IS NULL
