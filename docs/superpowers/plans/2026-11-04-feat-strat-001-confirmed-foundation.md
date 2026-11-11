---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md
branch: feature/feat-strat-001-confirmed-foundation
pr: 1714
status: ready
---

# FEAT-STRAT-001 confirmed foundation release

**Spec:** `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` (approved, merged in #1721; it supersedes the 2026-10-12 spec approved in #1575 and changes only done_when 6, which now tracks the docs audit in #1720).

Rebuilds the foundation release from main after #1546 (shared NYSE calendar). The
earlier working tree is unreachable; Tasks 1 to 3 and the monitor rule pin are
restored byte-exact from the reviewed PR #1573 archives, and the rest is written
against the spec's acceptance mapping. No equality, 3-1-2 glossary, reference FTFC
frame set, clipped final 4h confirmation, PMG, stop or expiry policy is selected.

## Task 1: Bounded classifier truth table and invalid-input controls

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 1, "Candle and pattern classification".

- [x] Restore the existing-version truth table, invalid and gapped-input controls and the legacy monitor pin (`legacy-pattern-v1`)
- [x] Route lib/strat.py and lib/data_loader.py through `lib.eastern_time.session_schedule`

## Task 2: Closed-candle confirmation on 5m, 15m, 30m, 1h, 4h and 1w

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 2, "Closed-candle owner-decision acceptance".

- [x] `compute_confirmed_setups`: cut at the clock before aggregation, confirm only the newest closed period, report the developing period separately
- [x] Missing, invalid, gapped, stale, unresolved-anchor and shorter final buckets stay unconfirmed with reasons
- [x] `compute_strat_status` carries `confirmed_setups` at the same clock
- [x] `TestClosedCandleConfirmation` with before-close, at-close, later-row perturbation and consumer-boundary controls

## Task 3: Continuity separation and FTFC causality

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 3, "Continuity and weighted FTFC".

- [x] Keep `TestContinuityContracts` and `TestLegacyFtfcGolden` (34 final-as-of controls) unchanged in weights
- [x] Repair default FTFC membership in lib/backtest.py so future rows cannot change earlier results
- [x] Add tests/lib/test_backtest_ftfc_causality.py with the four named tests

## Task 4: Status, history and consumer adapters

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 4, "Shared status/history and consumer adapters".

- [x] History as-of contract (`TestHistoryObservationContract`)
- [x] Summarizer and `StratSnapshot` keep clock, completion, qualification and unavailable reasons
- [x] Premarket brief keeps unavailable as unavailable, never inside
- [x] Add the two named hermetic adapter tests

## Task 5: Captured-data foundation diagnostic

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 5, "Captured-data diagnostic and visual evidence".

- [x] Versioned diagnostic over captured inputs with code, config and input hashes and retrospective-vintage limits
- [x] `test_captured_foundation_diagnostic_matches_actual_producers`

## Task 6: Records and gates

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 6, "Records, focused tests and gates".

- [x] Update the FEAT-STRAT-001 catalog record and PR traceability
- [x] Focused suites and spec gate pass; the matched docs audit is tracked in #1720 and does not gate this release
- [ ] Record merge and deployed verification separately after release gates
