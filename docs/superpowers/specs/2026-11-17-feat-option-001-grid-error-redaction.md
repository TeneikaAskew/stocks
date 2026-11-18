---
feat_id: FEAT-OPTION-001
req_ids: [REQ-REL-001, REQ-GOV-001]
issues: [2085]
canvases: []
site_source_notes: [OPTIONS-01]
done_when:
  - "tests/api/test_grid_error_redaction.py exercises the real grid on-demand fetch path with synthetic HTTPError, transport/JSON failures and RealtimeOptionsUnavailable carrying sentinel credentials and provider text; no sentinel, request URL or arbitrary provider content reaches logging records or serialized HTTP detail. These regressions fail on the exact pre-change base and pass on head."
  - "The real route/caller tests retain HTTP503 for unavailable/fetch failure, HTTP429 for rate limiting, existing authentication, request validation, missing-key behavior and success/empty responses; original fetch arguments and number of attempts are unchanged, and failure makes no persistence call."
  - "Tests inspect LogRecord msg/args/exc_info/exc_text/stack_info and response serialization, and cover actual background-dispatch/outer exception handlers reached by this failure so the safe inner response cannot be re-exposed there. Success tests retain original database call shape using recording fakes. Network, database, subprocess, gcloud and real credential access fail on call."
  - "The real _fetch_on_demand and get_grid_live paths produce controlled HTTPExceptions whose traceback.format_exception(type(exc), exc, exc.__traceback__, chain=True) and TracebackException.from_exception(exc, capture_locals=False).format(chain=True) outputs contain no literal or encoded sentinel, URL or provider text. Exercise both implicit __context__ and explicit __cause__ chains with synthetic HTTP/transport/JSON/typed-provider failures, and logging.Formatter.formatException for any emitted exc_info. Assert the entire rendered output, not only str(exc), HTTP detail or __suppress_context__. A causal control without chaining suppression must fail."
  - "The unchanged applicable grid/API suites and new redaction tests pass in mock mode; no unrelated assertions, cases, status codes, retries, formulas or timeouts change."
  - "FEAT-OPTION-001 delivery records, OPTIONS-01 committed source proof, matched no-new docs audits and ordinary gate checks pass under existing limits; normal current-head review and hosted checks pass before merge. Deployed verification and historical exposure are separate close-out obligations."
status: approved
supersedes: null
---

# Keep AV failures out of grid logs and HTTP details

## Problem and scope

On main379ad19d, platform/api/routers/grid.py imports the legacy fetch_av_realtime_options at496 and calls it at503. At507, raw RealtimeOptionsUnavailable text enters HTTP503 detail; at511-512 arbitrary fetch exception text enters a warning. The DATA companion removes provider-derived typed messages, but grid must protect its own sinks even against an unchanged or failing dependency.

The catalog explicitly assigns grid.py to FEAT-OPTION-001. Runtime scope is this file's on-demand AV error handling and directly propagating outer/background handlers, plus tests/api/test_grid_error_redaction.py and only necessary diagnostic-text assertions in existing grid tests. No shared helper or global logging filter is added. No options calculations, writer, cache, freshness, entitlement, source selection, response schema or authentication change is admitted.

## Design

Keep the typed-unavailable and general-error branches distinct internally and their existing HTTP503 status. Return controlled fixed detail categories, without exception text, provider bodies, URLs, request objects or credential-derived values. Keep existing valid ticker context only through its existing validation. Log the same operational failure with fixed categories, no raw exception object or traceback metadata. Suppress chaining at this new controlled boundary where a propagated HTTPException could expose the original exception; test both outer/background sinks and route serialization. Do not catch new exception classes or change rate-limit checks. Preserve HTTP429 and existing validation/missing-key responses.

## Test plan and sequence

After admission, use the repository's existing API import/test harness and recording fakes. Establish RED controls through the actual on-demand helper and route/dispatch caller, then replace only unsafe diagnostic formatting. Include a malicious __str__ exception, encoded fake-key URL, Information/Error Message-derived typed error, success and existing empty behavior, missing config, rejected ticker and rate-limit controls. Verify no database upsert on failure. Do not use live endpoints or production credentials. Record exact collected nodes/base/head and every initial failure.

This slice can protect grid while the legacy fetcher remains unchanged and must test that configuration. DATA and OPTION implementations use separate fresh plans after their approved specs are on main; no stacking or competing shared-record edits. Complete containment of both paths requires both slices and separately verified release.

## Risks

Clients may inspect free-text error detail; only its sensitive free text intentionally changes, preserving status and response shape. Background/outer logging may reintroduce chained errors, hence real-caller coverage. This specification does not claim every unrelated grid/database error sink is remediated.

## Admission and ownership

Scope admitted on 2026-11-18 through the coordinator’s explicit confirmation of the owner’s instruction “Get those issues fixed”. The admission covers controlled diagnostic text in the two fetchers and the grid logging, HTTP-detail and rendered-traceback boundaries, preserving statuses, retry counts, reasons and successful behavior, with the synthetic tests specified here and in the companion. This records scope admission; it does not claim the owner reviewed every technical word, that implementation is complete, or that merge, auto-merge, deployment or credential rotation is authorized. No implementation branch starts before its covering approved specification is on main and a fresh ready plan binds it. Keep existing review history and the two-round limit. No review has been requested for this bundle.

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

## Exact external-boundary coverage (base 379ad19d)

`grid._fetch_on_demand` imports the legacy fetcher at496 and calls it at503. Typed provider errors enter HTTP detail at507; other fetch failures enter logging at510-513 before HTTP503 at514-517. `get_grid_live` calls this helper synchronously at721, rethrows HTTPException at742-743, and its defensive dispatch handler logs unexpected exceptions at748-749. These are the identified external logging/response boundaries: test the real helper AND routed caller, and require safe rendering at each. There is no separate background worker on this audited path; do not invent one to satisfy generic wording. If current-main refactoring introduces one, enumerate it before implementation.

Cover a synthetic transport error injected directly at the dispatch boundary as well as through the legacy fetcher. Replace that defensive panic diagnostic with fixed text while preserving its existing unavailable-envelope continuation. The BSM and persistence blocks at596-609 and626-633 are after a successful fetch and do not receive the caught fetch exception; their unrelated failures remain outside this narrow repair, with existing behavior preserved. A newly demonstrated flow of provider content into either is a scope finding, not a silent waiver.

Raw HTTP/transport exceptions may remain inside the legacy library for compatibility, but none may cross the identified grid external boundary as raw log arguments, exception metadata, serialized detail or a displayed chain. Suppression controls standard rendering, not erasure: `raise ... from None` can leave __context__ in memory. Do not claim sanitization against arbitrary object/local-variable dumps or third-party telemetry without separately auditing and testing them. Repeat the production caller search at implementation base and name any newly discovered sink before asserting coverage.
