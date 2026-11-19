---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-GOV-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [CATALYSTS-04]
done_when:
  - "Real HTTP tests in tests/api/test_catalyst_retired_provenance.py inject synthetic retired provenance into both /api/catalysts/events and /api/catalysts/ticker/{ticker}: direct aliases, rendered earnings_calendar labels, mixed-source labels, lists and nested provenance wrappers are absent from events, counts and date groups. The same tests fail on the recorded main base. No production fixtures or vendor calls are used."
  - "Positive HTTP controls retain Alpha Vantage, Unusual Whales, Yahoo, Benzinga, null/missing/unknown provenance, Earnings_Whispers and unrelated event types byte-equivalently except already-existing response formatting. Title/description mentions alone do not cause exclusion. An independent same-ticker/date sibling survives an excluded EW-derived event. A mixed EW/non-EW event is excluded whole, never relabelled as independently sourced."
  - "Tests exercise fresh mocked acquisition, cache hits, acquisition returning no data with cache fallback, peer-refresh and timeout/decliner paths, and the direct ticker live fallback. Counts, sorting, grouping, requested date/type/ticker filters, in-flight semantics and vendor-call bounds remain correct. Cache file bytes and historical database rows are not changed by response qualification."
  - "All existing catalyst source-label, estimate-number, flight/cache and API tests pass with unchanged assertions; new regression tests forbid real requests, database connections and subprocess jobs. Record exact collected base/head nodes and scoped command results; no skips or weaker assertions hide a failure."
  - "The implementation changes only platform/api/routers/catalysts.py and tests/api/test_catalyst_retired_provenance.py plus its fresh bound plan, own FEAT-CATALYST-001 catalog/lineage and CATALYSTS-04 source note, supported generated inventory and source sidecar. Existing SQL exclusions and all unrelated runtime files remain unchanged."
  - "Actual committed-source identity verifies with the fixed bounded producer/verifier; preserve every foreign SITE byte and registry byte. Matched main/head documentation audits have no new findings, trusted BASE and required current-head review/CI pass within existing limits. Main/staging output verification and sidecar close-out remain separately recorded post-merge milestones, not inferred from this proof."
status: draft
supersedes: null
---

# Exclude retired EW provenance from current catalyst responses

## Admission and ownership
Proposed, unapproved specification. TA requested clean current EW output; that authorizes preparing this contract, not claiming its exact acceptance wording approved. This is the existing EW source owner's narrow FEAT-CATALYST-001 lane, separate from #2095 documentation, #2100 clock maintenance, #2097 optional research and the GCP image owner. No new issue. Preserve all prior review history. Implementation requires approved spec on main and a fresh bound plan. The earlier SQL retirement contract remains in force and is not superseded.

## Problem and evidence
On main 666804f93ea15b3ec666b90b470d2430095f51a3, catalysts.py lines 627-648 filters cached events by ticker/date only. Offline execution of that exact function AST with synthetic cache entries returned earnings_whispers, EarningsWhispers and earnings_calendar (earnings_whispers), and the independent alphavantage control. This is component evidence, not HTTP or production proof. The general feed merges cache events at lines 277-294. Existing database predicates cannot qualify this separate cache path.

## Alternatives and selected design
Deleting cache/history is rejected: historical data must survive. Removing labels is rejected: values can still be EW-derived. Select response-boundary exclusion of positively identified retired provenance, preserving unknown data.

Use one pure local predicate on event provenance, invoked on every response-producing path after acquisition/cache selection and before response grouping/counting. Inspect source, data_source, provider, sources and provenance fields. String leaves in those fields match stripped exact earnings_whispers, EarningsWhispers or Earnings Whispers; preserve the distinct Earnings_Whispers spelling. Do not case-fold underscore spellings into a retired alias. Parse the complete known earnings_calendar (...) wrapper into comma-separated source tokens; never substring-match arbitrary prose. Within a provenance container, recursively inspect its lists and dictionaries using the same recognized provenance keys (including name for a provider/source descriptor); do not scan title, description, URL or arbitrary payload strings. Lists may contain strings or provenance objects. Use iterative traversal so nested synthetic input cannot exhaust Python recursion. Any recognized retired token excludes the entire event, even alongside a supported provider. Missing, null, numeric, unknown or malformed unrecognized provenance is retained unchanged: unknown origin is not evidence of EW origin. Tests explicitly cover these shapes and near-miss strings. This does not certify unknown data as non-EW.

Apply qualification before ticker fallback decisions so a cache containing only excluded events behaves as an empty eligible cache; the existing one live fallback remains available and its results are qualified too. Preserve general-feed single-flight acquisition, wait limits, error handling, status and fresh/cache labels. Do not introduce vendor/database requests, recursive fallback or cache rewrites to repair a response.

## Capacity and limits
No new queries, jobs, schedules or vendor calls. Traverse each event's provenance once, O(provenance nodes) time and O(provenance nodes) worst-case stack; preserve existing response payload size limits and acquisition bounds. Measure representative 1000-event synthetic payload duration/peak memory and traversal count in the implementation evidence. No production latency claim or changed resource ceiling.

## Exclusions and close-out
No source cleanup in Solyra, data purge, schema/migration, credentials, calendar migration, deployment or historical replay rewrite. The parent coordinates Solyra's separate consumers; this Stocks PR proves only its actual endpoints. Real deployed current-output/cache verification is a separate release milestone. No claim that all unknown provenance is independently verified or every report/export in other services is clean.

## Coordinated consumer readback
The coordinator independently inspected Solyra CatalystsPage.tsx (lines 169, 295-297) fetching the general events endpoint and rendering event.source verbatim, and DashboardPage.tsx (line 356) consuming the same feed. These are supplied source observations, not a deployed test run by this author. Before close-out, record negative and positive API readback through both actual consumer surfaces: no injected EW provenance or values rendered, supported source labels and independent values retained. Hermetic browser evidence must distinguish intercepted responses from a genuine deployed API readback. No frontend blacklist is added by this contract; no Solyra source change is authorized here. Actual deployed verification awaits the separately coordinated release and must not be replaced by screenshots of mocked data.
