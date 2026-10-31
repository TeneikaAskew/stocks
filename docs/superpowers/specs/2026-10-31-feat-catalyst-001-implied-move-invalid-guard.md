---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-PLAYBOOK-001]
issues: []
canvases: []
done_when:
  - "tests/lib/test_earnings_reactions_recommended_structure.py::test_implied_move_invalid_returns_skip_only_where_the_guard_is_consulted: with long_only=True, score_quintile 'Q5' and a calibration that confirms over-pricing (realized_vs_implied_ratio below _IC_RATIO_THRESHOLD and avg_short_strangle_pnl_pct above _IC_STRANGLE_THRESHOLD), recommended_structure(archetype, 'Q5', calibration, implied_move_pct=None, implied_move_invalid=True) returns 'SKIP' for every archetype, where the same call without the keyword returns the long archetype action. With the keyword True, every other branch is unchanged: score_quintile other than 'Q5' returns the archetype action; calibration None or not over-priced returns the archetype action; long_only=False returns 'IC' for the over-priced Q5 case and the archetype action otherwise."
  - "tests/lib/test_earnings_reactions_recommended_structure.py::test_default_false_is_byte_identical_behaviour: for every combination of archetype in (bullish_trend, bearish_trend, reversal_play, mixed, None), score_quintile in (Q1, Q5, None), calibration in (None, under-priced, over-priced), implied_move_pct in (None, 5.0, 20.0) and long_only in (True, False), the return value with implied_move_invalid omitted equals the return value on main d806bfd1 (captured as a table in the test), and implied_move_invalid=False gives the same value."
  - "tests/lib/test_earnings_reactions_recommended_structure.py::test_invalid_flag_is_keyword_only_and_does_not_shadow_a_valid_implied_move: passing implied_move_invalid positionally raises TypeError; implied_move_invalid=True together with a non-None implied_move_pct raises ValueError at function entry, before any branch, in both modes (long_only True and False), for every score_quintile including None, and for calibration None (the brief never sends both; the contradiction is an error, not a silent choice)."
  - "git diff against the merge base changes only lib/earnings_reactions.py (the recommended_structure signature, its docstring, one entry check raising ValueError, and one branch returning 'SKIP') and the new test file. gcp/refresh_earnings_views.py, gcp/premarket_brief.py and gcp/earnings_reactions_brief.py are unchanged, and the two refresh_earnings_views call sites (L248, L252 at d806bfd1) still omit the keyword."
  - "The existing tests under tests/lib/ and tests/gcp/ that exercise recommended_structure pass unmodified."
  - "Own narrow plan and product records, the no-new documentation audit, current-head required Codex code review and CI pass through the normal gates."
status: draft
supersedes: null
---

# recommended_structure: an invalid implied move fails closed where the long-only guard is consulted

## Status

Draft seed, rev 2.1 (rev 2 plus one post-review text edit: the template heading `Design` replaces `Change`; LOCAL-DESIGN2 reviewed rev 2, `../history/rev2-catalyst-seed-69a9e44f.md`), prepared locally on 2026-10-31 against stocks main `d806bfd19a82bb723acfdb7035e2a3ad52deb77c`. Published as a specification-only draft pull request on its own `docs/spec-feat-catalyst-001-implied-move-invalid-guard` branch from main d806bfd1 (owner direction 2026-10-31 12:34 UTC); not implemented; `status: draft` until the owner's section-by-section admission of this text is recorded on that pull request (product-delivery SKILL.md:40). Rev 2 (after the first independent design review, LOCAL-DESIGN1) adds REQ-DATA-001 to req_ids (the fail-explicit requirement the guard serves), fixes the ValueError check's placement at function entry, names the mode in done_when 3, and adds the template headings; rev 1 is `../history/rev1-catalyst-seed-9ff32793.md`. It exists because the FEAT-PLAYBOOK-001 spec `2026-10-31-feat-playbook-001-premarket-brief-finite-values.md` (rev 5.1, part 2) needs one library keyword, and `lib/earnings_reactions.py` is a FEAT-CATALYST-001 catalog Code row, so the change is specified under its owner rather than edited across feature lines.

Approval attribution: the owner approved the briefing design part "prevent invalid-only data from producing a LONG CALL through the existing long-only guard" (asked 06:39:47 UTC, answered "That's fine" 10:18:34 UTC, 2026-10-31). This spec is the author's design for the library half of that part and is presented for approval; the owner has not separately approved this text. **Approval provenance, mapped to sections:** part (2) of the approved question ("prevent invalid-only data from producing a LONG CALL through the existing long-only guard") covers the Design section's keyword and guard branch and done_when 1, 2, 4 and 5; the entry-check ValueError (done_when 3), the test names, line anchors and headings are author metadata presented for admission. Part (1) of the approved question does not concern this file.

`supersedes: null` is actual: no FEAT-CATALYST-001 spec on main names `recommended_structure` (the only spec that does, `2026-10-13-feat-option-001-av-earnings-cycle-contexts.md`, belongs to FEAT-OPTION-001 and is not altered).

## Problem

`recommended_structure` (L305 to L400 at d806bfd1) consults `implied_move_pct` only in long-only mode for an over-priced Q5 row (the Q5 gate at L369, the IC return at L389 to L390, the implied test at L396 to L398) and documents `None` as "no filter, keep the long recommendation". The brief has no way to say "a value was present but invalid, so do not grant the long recommendation": its only options are a real number, None (which grants), or a fabricated number (a silent fallback that yields SKIP at the same place and is indistinguishable at the output). Replicating the guard predicate in the brief would duplicate policy that lives here.

## Design

One keyword-only argument, `implied_move_invalid: bool = False`.

- **Entry check.** If `implied_move_invalid` is true and `implied_move_pct` is not None, raise `ValueError` immediately, before any branch and in every mode: the caller is contradicting itself, and the function does not pick for it.
- **Guard branch.** In the branch reached only when `long_only` is true, `score_quintile == 'Q5'` and `is_over_priced` holds, immediately before the existing `implied_move_pct > _LO_IMPLIED_HARD_MAX` test: if `implied_move_invalid` is true, return `'SKIP'`; otherwise the existing test and return are unchanged.

The docstring gains three lines describing the three caller states (valid number, None for absent, True flag for invalid). `_LO_IMPLIED_HARD_MAX`, the IC rule, the archetype maps, `_env_long_only` and every other branch are unchanged. With the keyword omitted or False the function is byte-identical in behaviour to main (done_when 2).

## Non-goals

No change to the None rule (absent still grants the long recommendation), to thresholds, to IC mode, to `compute_playability_score`, `confidence_label` or any reader. No caller is changed in this spec; the brief adopts the keyword in its own spec. The separately owned EarningsWhispers retirement change writes NULL for EW-derived fields in `gcp/refresh_earnings_views.py` and does not call or change this function; the two contracts stay separate.

## Approaches considered

- **Brief-side predicate copy or surrogate number.** Rejected (one source of truth for math; silent fallback).
- **A sentinel value for `implied_move_pct` (for example `float('nan')`).** Rejected: a NaN compares False against the threshold and silently grants the long action, the exact failure being fixed.
- **A tri-state enum replacing `implied_move_pct`.** Rejected: changes the two existing callers' signatures for no gain.

## Risks

- A caller that sets the flag and a number gets a ValueError; today no caller sends the flag. The brief's spec pins that it never sends both.
- Default-off compatibility: `gcp/refresh_earnings_views.py:248, 252` omit the keyword and are asserted unchanged (done_when 4 and 5).

## Files and ownership

- `lib/earnings_reactions.py`: FEAT-CATALYST-001 catalog Code row. The open draft stocks#1608 (`feature/feat-catalyst-001-event-bound-reactions`, head 59aab3f0, merge base d4478433) inserts 529 lines into this file after L958, none inside `recommended_structure`; this change is additive and is sequenced with #1608's owner (the recovery thread), which does not modify #1608 for it.
- `tests/lib/test_earnings_reactions_recommended_structure.py`: new.

## Rollout

Spec alone on `docs/spec-feat-catalyst-001-implied-move-invalid-guard`, published as a draft independently of the FEAT-PLAYBOOK-001 spec draft; after the owner's admission, review and CI, merge. Then one plan and one `fix/feat-catalyst-001-implied-move-invalid-guard` branch; review and CI; merge. The FEAT-PLAYBOOK-001 brief implementation plan is cut only from a main that holds this keyword (no implementation stacking); the two specification drafts do not wait on each other. No deploy is implied: the keyword is inert until the brief passes it.
