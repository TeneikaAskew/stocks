---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-GOV-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [CATALYSTS-04]
done_when:
  - "tests/gcp/test_refresh_earnings_views_retired_score.py freezes refresh_earnings_views.market_today to the same fixture TODAY already used by its mock SQL and write-date assertion. No assertion, parametrization or existing case is removed or weakened; production source stays byte-identical to the implementation base."
  - "Deterministic controls invoke the actual test_retired_fields_are_null_on_every_row with distinct import/run clocks: Eastern-midnight crossings in standard and daylight time fail before the repair and pass after it; same-day and UTC-midnight-only controls pass on both. Actual affected pytest file passes in mock mode, with no real vendor/database/subprocess calls. Record commands, inputs, counts and bounds; this is simulated clock-boundary evidence, not a hosted rerun."
  - "The implementation diff is limited to this test and its fresh bound plan plus necessary own CATALYSTS-04 source identity, catalog/lineage and supported generated documentation. No runtime, schema, API, deployment configuration, calendar, secret, historical row or assertion changes are included. No deployment or database mutation is claimed or performed."
  - "Normal hooks, trusted gate/BASE, committed single-record source proof under existing fixed ceilings and matched main/head no-new documentation audit pass. Record exact-head CODE and CI under normal review limits and preserve #2095's review ledger; no green result from another SHA substitutes for this implementation."
status: approved
supersedes: null
---

# Freeze the retired-score test fixture's clock

## Scope and admission

Scope admitted on 2026-11-19: the owner directed “Fix the bug then” after the coordinator described this exact fixture-clock repair and its separate specification. This records approval of the narrow repair, not a claim that implementation has merged or that every technical word was reviewed. This separate narrow test-maintenance contract does not supersede, waive or repeat the broad accepted EW retirement spec. That spec explicitly owns this test but its whole-PR done_when item11 requires schema/API/platform changes and associated release disclosures; those are false for this isolated repair. No such changes are introduced merely to satisfy an old contract. Before publication of implementation, merge this admitted spec through normal review and checks, then bind a fresh ready plan from actual main.

## Problem and evidence

#2095 head7e97a26f changes only two prose cells. Its Run Tests job135348325765 failed after Eastern midnight: refresh_date2026-11-19 differed from fixture TODAY2026-11-18. The fixture captures market_today at import; production refresh_daily reads market_today at invocation. Both files are byte-identical to base666804f9. The SQL fake already uses fixture TODAY, so the inconsistent production clock is a test-harness defect.

Actual-test controlled invocation on the unchanged base reproduced winter and summer Eastern midnight failures, while same-day and UTC-midnight-only controls passed. The two-line local repair pins the reader's clock through monkeypatch in run_refresh. All four controls then passed and the actual affected suite passed five tests. These prior receipts qualify the local prototype, not a committed implementation or hosted CI.

## Design and exclusions

Add only a comment and monkeypatch.setattr(rev, 'market_today', lambda: TODAY) in run_refresh. Preserve the write-date assertion and every NULL/recommendation/archetype/lean assertion. Prefer this over removing the assertion, changing production time handling or rerunning CI until the wall clock avoids midnight. No shared fixture rewrite, deadline change or added skip.

## Delivery and cost

Zero runtime requests, SQL statements, jobs, retries or schedules added. Tests remain synthetic and use the existing mock database boundary. Own source-note proof describes test-only behavior and preserves earlier own prose and every foreign byte. No deployment or schema effects from this diff; any separately authorized release remains separate. One plan/branch/PR, normal two-round review cap, no inherited-budget reset. Do not push on #2095 or fold unrelated runtime changes into it.
