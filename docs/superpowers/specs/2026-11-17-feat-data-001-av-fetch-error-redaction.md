---
feat_id: FEAT-DATA-001
req_ids: [REQ-REL-001, REQ-GOV-001]
issues: [2085]
canvases: [https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN]
site_source_notes: [SHARED-07]
done_when:
  - "tests/gcp/test_av_fetch_error_redaction.py invokes real fetch_month with synthetic HTTP, transport and JSON failures plus Error Message and Information responses; sentinel secrets, encoded secrets, URLs and arbitrary provider text are absent from formatted logs, raw LogRecord msg/args, exc_info, exc_text and stack_info. Each sink regression fails on the exact pre-change base and passes on head."
  - "The same tests prove unchanged complete outgoing request parameters including a fake key, endpoint, timeout, one attempt, FETCH_* reasons, failure frame shape and successful sorted frame values; Note, missing-series and valid empty/nonempty controls retain existing behavior."
  - "Real fetch_av_realtime_options provider Information and Error Message branches raise the same typed exception classes with fixed safe category messages instead of provider content. Tests prove no sentinel in str/repr/args and preserve every success, sample-data, empty-chain and HTTP/transport failure contract; HTTP/transport exceptions continue to propagate for existing callers. No outgoing request or dataframe calculation changes."
  - "The unchanged affected intraday and realtime-options suites and the new synthetic suite pass in mock mode with fail-on-call network, database, subprocess and gcloud guards; all tests use fake keys and no environment or secret-store credential reads. No unrelated test is deleted, skipped or weakened."
  - "FEAT-DATA-001 delivery records, SHARED-07 committed source proof, matched no-new docs audits and the ordinary gate checks pass under existing limits; normal current-head review and hosted checks pass before merge, with release and historical exposure remaining separate."
status: draft
supersedes: null
---

# Prevent credential-bearing diagnostics in the two AV fetchers

## Problem and scope

On main 379ad19d, fetch_month in gcp/fetchers/fetch_alphavantage_intraday.py logs provider Error Message at line152, Information at158 and raw exception at184. requests HTTPError may contain a credential-bearing URL. gcp/fetchers/fetch_av_realtime_options.py lines128-134 embeds provider messages in RealtimeOptionsUnavailable, which callers can expose. Issue #2085 records historical exposure; do not copy its credential-bearing content into this spec or tests.

FEAT-DATA-001 owns fetcher jobs. Runtime changes are confined to these two files and dedicated tests/gcp/test_av_fetch_error_redaction.py, with only necessary diagnostic-text expectations in their existing tests. Changing public exception types, reason values, HTTP propagation, collection/writer behavior or source policy is outside this scope.

## Design

In fetch_month, retain Error Message -> FETCH_INVALID_API, Information -> FETCH_INFO_MSG, Note -> FETCH_RATE_LIMIT and caught failure -> FETCH_REQUEST_ERROR. Log fixed category text with existing validated operational identifiers only; never interpolate provider text or the exception, attach traceback/stack data, or access request/response objects for diagnostics. In the legacy options fetcher replace only provider-derived exception messages with fixed categories. Do not wrap HTTPError or change its propagation: the OPTION companion closes its API/logging sink independently, so DATA alone does not claim whole-path containment.

## Test plan and sequence

After admission: write causal real-function failure tests first; capture synthetic logging records and outgoing requests through recording fakes; implement the minimal sink replacements; run existing caller tests and new tests with all external boundaries forbidden. Exercise a malicious exception whose __str__ raises to prove the diagnostic path never stringifies it. Test provider objects containing fake secrets in nested or encoded text. Keep all initial failures. Bind every result to base/head, and report unrun integration separately.

The OPTION companion may proceed independently after its own admission. Neither implementation stacks on the other's unmerged branch. Coordinate SHARED-07 and generated sidecar writes through the parent. Full #2085 source containment needs both slices.

## Risks

Changing failure classifications can change scheduler outcomes; exact FETCH_* and exception-class controls prevent that. A log formatter can expose raw args even when the final message looks safe, so inspect record internals as well as text. Removing provider detail is an intentional security behavior change, not a change to request or data semantics.

## Admission and ownership

Proposed, not approved. The coordinator authorized preparation and normal specification publication for issue #2085; this does not claim approval of previously unseen acceptance wording. No implementation branch starts before its covering approved specification is on main and a fresh ready plan binds it. Keep existing review history and the two-round limit. No review has been requested for this bundle.

At preparation, the open-PR search for #2085 found only handoff #2088; #2085 had no comments. This does not prove absence of unpublished work. Before implementation/publication, recheck overlapping PRs and coordinate through the internal coordinator; do not contact external agents. #1828's broad credential-safe-errors draft is not on main and is neither superseded nor implemented by this narrow work.

## Approaches considered

1. Regex-redact exception strings: rejected because arbitrary provider bodies, encoded values, exception chains and request metadata can evade a key-name pattern.
2. Silence all failures: rejected because operators and callers need the existing failure distinctions.
3. Fixed diagnostic categories at the owned output boundaries: selected. Do not stringify arbitrary exceptions or provider content. Preserve non-diagnostic behavior.

## Capacity and exclusions

Zero added requests, retries, jobs, schedules, SQL statements or cloud resources; existing request timeouts, pacing and memory/deadline limits stay unchanged. Diagnostics have fixed bounded text and no credential-derived values. Record actual local elapsed time and peak memory for affected tests without claiming production measurements. Incremental scheduled cost is zero.

No key reads during tests, credential rotation, production access, live vendor/model requests, database/schema/data changes, historical-log deletion, deployment, scheduler change, shared calendar change, or unrelated error-policy repair. Do not change logger configuration, globally filter logging, suppress unrelated diagnostics, or add a broad exception fallback. Deployment and any credential rotation are separate coordinated actions.

## Delivery and close-out

Update only this capability's catalog/lineage records, own bound plan and declared implementation-source notes. Preserve foreign SITE bytes and earlier own prose. Regenerate one canonical sidecar from the final committed source/body under the actual main verifier limits; run matched main/head audits with no new findings and normal trusted BASE/CI checks. Preserve DOC_REGISTRY and gate policy. A valid source record does not prove external review or rollout. Record current-head review/CI separately from the pre-review local evidence; never tick a compound item whose facts are pending.

After merge, verify actual squash/main identity in a fresh checkout. Release owner separately verifies deployed digest and safe synthetic error behavior without inducing real vendor failures or exposing secrets. Only then perform the prescribed documentation/SITE close-out and plan completion. Historical exposure and rotation remain tracked under #2085; this source change cannot retract old logs.
