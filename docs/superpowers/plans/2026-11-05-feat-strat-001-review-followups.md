---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md
branch: fix/feat-strat-001-review-followups
pr: null
status: ready
---

# FEAT-STRAT-001 review follow-ups from #1714

**Spec:** `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` (approved, merged in #1721).

Fixes the three P2 findings Codex's code review raised on #1714 at 3f1bb61b, after that PR's
two review rounds (CLAUDE.md review cap; below the P1 threshold in AGENTS.md "What blocks
the merge"). Each fix has a test that failed on 3f1bb61b with the reported symptom.

## Task 1: Coverage and FTFC at the confirmation cutoff on date-only replays

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 3, "Continuity and weighted FTFC".

- [x] `compute_strat_status` passes `confirmation_clock` to `build_multi_timeframe` and the daily adapter, so a date-only replay with `inclusive_today=False` scores IWM 2026-04-08 as W/M `2U`/`1` and FTFC 0.25, not `X`/`X` and 0.0 (Codex r4481033962)

## Task 2: Legacy Last alias and unknown report successors

Spec: `docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md` done_when 4, "Shared status/history and consumer adapters".

- [x] `compute_strat_status` renames a legacy `Last` close to `Close` before OHLC validation (Codex r4481033971)
- [x] `scripts/strat_history_report.py` scores continuation only against known successors, so a NULL-OHLC placeholder stays pending (Codex r4481033984)
