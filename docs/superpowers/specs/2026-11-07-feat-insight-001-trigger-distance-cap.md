---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-PLAYBOOK-001, REQ-REL-001, REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [INSIGHTS-07]
done_when:
  - "tests/lib/test_trade_planner_distance_cap.py passes and fails on origin/main: on the 2026-11-06 inputs rebuilt from Alpha Vantage bars, the short trigger is PDL 647.05 for QQQ (not PYL 402.39), the blue-sky trigger PML 269.875 - 0.20 x ATR for IWM (not PYL 171.73) and PQL 729.10 for SPY (unchanged); every persona entry edge lies within 3.4 x ATR of the reference price; the same price geometry gives a structural trigger at ATR 2 and a blue-sky trigger at ATR 1 (the cap uses the ticker's own ATR); a structural level equal to pre_high (long) or pre_low (short) to the cent is unbroken; pre_low is never its own short trigger"
  - "tests/lib/test_trade_planner.py passes with exactly three tests changed and named in the PR body: test_select_trigger_extended_when_next_level_far_away becomes test_select_trigger_far_level_beyond_cap_is_not_a_trigger (blue-sky, normal), test_select_trigger_short_mirror moves PML from 130 to 150 so it lies inside the window, and test_extended_regime_rationale_includes_orb_recommendation reaches extended through the legacy single-level path"
  - "No other behaviour changes: lib/strat_levels.py is not in the diff (the window and its constants are imported, not copied), the legacy single-level path and the stop anchor are unchanged, and tests/agents, tests/gcp and tests/lib pass"
  - "The PR body shows the old and new short trigger and the three persona entry zones for IWM, QQQ and SPY on 2026-11-06, with whether each would have filled against that day's regular-session low"
  - "Source identity (INSIGHTS-07): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-INSIGHT-001, INSIGHTS-07) note row carries that source_identity_sha256"
  - "The FEAT-INSIGHT-001 catalog record and the PR traceability entry are updated, the matched current-main-versus-branch docs_audit.py run reports nothing new, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Cap the insight planner's trigger walk at the brief's distance window

## Authority

Proposed on 2026-11-07 by a FEAT-INSIGHT-001 delivery lane after the owner reported that the
2026-11-06 insight entries for QQQ and IWM sat "extremely far" from price and asked for a fix, a rerun
of Friday and a per-ticker ATR. It is not self-approved: it takes effect only when the owner authorizes
the merge of the spec-only PR that adds it, and that merge is the approval its `status` records.

The owner's GCP session had diagnosed the same defect on 2026-11-06 and asked for a cap of 3 ATR, 5 ATR
or a per-ticker cap. This spec answers with the window the premarket brief already applies, measured in
each ticker's own ATR(14), so the brief and the planner share one rule.

## Problem

Read in the code at origin/main bd88fa45.

1. **No distance cap.** `select_trigger_and_regime` (`lib/agents/trade_planner.py:185-410`) returns
   the nearest unbroken level in the trade direction however far away it is. On 2026-11-06 IWM's 4 AM
   print of 269.13 broke PDL 270.52 and PML 269.875, so the short trigger became the 2025 yearly low
   171.73, about 22 ATR below price; QQQ's became 402.39, about 15 ATR below. The 11-06 GCP read found
   AVGO at 138.10 the same way. IWM's largest one-session move in the last two years was 3.79 ATR, so
   these plans could not fill. The brief already drops such levels with `_within_staleness_window`
   (`lib/strat_levels.py:926-942`: at most `MAX_TRIGGER_DISTANCE_ATR` 3.0 x ATR and
   `MAX_TRIGGER_DISTANCE_PCT` 8% of price).
2. **A touched level counts as broken.** Short candidates are levels strictly below
   `min(ref, pre_low)` (`:288-291`), longs strictly above `max(ref, pre_high)` (`:276-279`). QQQ's
   pre_low on 11-06 was 647.05, an extended-hours print at exactly the prior close and equal to PDL, so
   PDL was skipped although price never traded through it.

ATR is already per ticker: `context_from_bundle` reads each ticker's `atr_14` from market_data_daily
(`:912`). The defect is the uncapped walk, not the ATR.

## Non-goals

- No change to `lib/strat_levels.py`, the brief, the signal monitor or any threshold, weight or recipe.
  The other inconsistencies the 2026-11-07 survey found between the brief and the planner (reference
  price, level set, the brief reading a prior-day premarket row, fallback copy, the unwindowed stop
  anchor) are separate specs.
- No change to the legacy single-level path (no multi-timeframe levels) or to the stop anchor.
- No filtering of Alpha Vantage echo prints in the premarket data; the tie rule makes an echo at a
  level harmless here, and the data fix is its own change.
- No rewrite of stored `insight_reports`.

## Approaches considered

1. Cap at 5 ATR, keeping 3 to 5 ATR as `extended`. Rejected: it keeps a second, looser rule beside the
   brief's, and none of SPY, QQQ or IWM moved 5 ATR from the prior close in a session in two years.
2. A per-ticker cap from each ticker's own move percentiles. Rejected for now: a new query in the
   pipeline and a rule the brief does not share. The entry experiment that follows this fix can test it.
3. Chosen: reuse the brief's window, imported from `lib.strat_levels`, on each ticker's own ATR, plus a
   one-cent touch tolerance for structural levels.

## Design

`lib/agents/trade_planner.py`, `select_trigger_and_regime`, multi-timeframe path only:

- `_TOUCH_TOLERANCE = 0.005`. A structural level (effective PDH/PDL, PW, PM, PQ, PY) counts as unbroken
  when it is within the tolerance of the cleared mark; `pre_high` / `pre_low` keep the strict compare,
  because each is the cleared mark itself. The blue-sky anchor lists use the same tolerance, so a level
  is either a candidate or an anchor, never both.
- Candidates are filtered with `_within_staleness_window(level, ref, atr)` around the reference price
  (`pre_vwap`, else the close) with the ticker's ATR (`safe_atr()`). Dropped levels are logged.
- With no candidate left, the existing no-candidate branch runs unchanged: a blue-sky trigger at the
  nearest cleared structural level -/+ 0.20 ATR when the gap is at most 1.5 ATR, else `orb_only`.

Consequence: a historical level is never 3 ATR or more away, so `extended` is now reached only through
the legacy path. The constant and the copy stay; the extended rationale test moves to the legacy path.

## Expected effect

On 2026-11-06 (local replay on Alpha Vantage bars): QQQ 402.39 to 647.05, IWM 171.73 to 268.96 (blue
sky), SPY 729.10 unchanged. All three stay unfilled that day because price rose. Days where the nearest
unbroken level lies within the window are unchanged.

## Capacity and cost

- **Volume and velocity:** unchanged; no new query, row or call.
- **Wall-clock:** unchanged.
- **Cost:** $0 new GCP workload, schedule or resource.

## Source identity and close-out

`lib/` and `tests/` are inside SITE's watched scope (`docs/DOC_REGISTRY.md`, the row for
`docs/product/03-SITE-TRACEABILITY.md`). INSIGHTS-07 names `lib/agents/trade_planner.py`. Only the
`(FEAT-INSIGHT-001, INSIGHTS-07)` row of the Implementation-source notes table may describe this
implementation, as backend source and local tests only, with no claim of deployment or review. Every
other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: deploy the insight jobs, rerun 2026-11-06 in
production as a replay, verify main's source and body identity in a fresh clone, complete the DOC main
and staging close-out with real evidence, retire the sidecar as the product-delivery skill prescribes,
and set the plan to `status: done` on a `docs/` branch.

## Risks

- **More plans fire near price.** Tickers that used to get an unreachable plan now get a reachable
  blue-sky or structural one, so sizing applies on days it did not before. The entry experiment that
  follows measures fill rate and R for this rule against the alternatives.
- **The docs audit reads solyra's issues**; a session without solyra access cannot run it, so the owner
  or a session with that access runs the matched pair before the PR is marked ready.
