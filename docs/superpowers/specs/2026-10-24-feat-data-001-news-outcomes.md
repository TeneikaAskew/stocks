---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-REL-001, REQ-SECRET-001, REQ-CAP-001]
issues: []
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "tests/gcp/test_news_sentiment_outcomes.py distinguishes valid nonempty/empty, missing/null/malformed feed, non-object JSON, Information/Note/Error Message, HTTP429/503, timeout and invalid JSON with one mocked request and zero error-feed writes."
  - "Actual CLI mixed-source tests persist successful sibling rows before reporting partial failure, preserve dedup/upsert identity, distinguish all-valid-empty from all-error, and treat failed/uncertain persistence as failure without refetch or replay."
  - "Fake-key regressions prove fixed safe error categories never log raw params, bodies, headers or exceptions; the native MCP premium envelope remains a separate transcript fixture, not reconstructed upstream HTTP evidence."
  - "Reviewed rollout pairs explicit failure exits with maxRetries0 on exactly the three NEWS jobs, verifies intended images/configuration and rollback targets, and introduces no whole-task or generic-error provider retries."
  - "Directly affected news tests, independent review, own delivery records, no-new docs audit, current-head Codex review and required CI pass before normal release; persisted coverage remains unknown until existing allowed exports verify it."
status: approved
supersedes: null
---

# Typed news collection outcomes

## Approved scope and provenance

The owner approved the bounded finish pass on October24,2026,including the already written typed-news-error/availability proposal,normal specification/implementation reviews and merges,and scoped deployment ("Do all the work needed"). The preserved brief is SHA256cd705665bf59e781f1aac0ccac1e0a2b37270a5c5cab71cabf52c759a88c2882. This specification formalizes its producer slice; the insight availability slice has a separate FEAT-INSIGHT-001 specification. Approval does not bypass actual specification MAIN or current-head gates. Root is the sole writer. The six-minute CI implementation is now MAIN at e7e74ccc (PR #1599); normal own current-head checks and authenticated Codex reviews remain required.

Source pin7dbf31921e3ec492e332faed445fbd63dd47b019 _fetch catches transport/HTTP/JSON failure as[]; provider notices/error envelopes also become[],and all-empty main exits normally. Offline tests reproduce failure/empty conflation. The exact deployed image's verified build input contains the same fetcher. This does not establish any individual provider error or the native connector's credential binding.

## Design

Use a small immutable internal outcome with explicit success/nonempty,valid-empty or error status; feed data is usable only on a schema-valid successful response. Record a fixed error kind for transport,HTTP,JSON,schema or provider Information/Note/Error Message. No provider wording or wrapper label alone establishes quota exhaustion,entitlement identity or retryability. Missing/null/non-list feed and non-object envelopes are schema failures,not empty news. Error envelopes remain errors even if a feed is also present. Validate article members sufficiently to prevent a malformed element from silently disappearing as complete coverage.

The private _fetch returns the typed outcome. Ticker/topic batch helpers expose their frame and per-source outcomes explicitly; adapt their in-repository callers/tests together. Keep the complete outgoing request,endpoint,timeout30,query order,incremental bounds,topic AND behavior and one HTTP attempt unchanged. Do not add automatic retries,requests,fanout or live certification. One source failure cannot erase successful siblings. Main collects safe per-source states,persists usable sibling rows with existing(ticker,published_ts,url) upsert identity,then emits complete,valid-empty,partial or failed terminal outcome. Any source error makes the task nonzero after sibling persistence. All-valid-empty remains a truthful empty success. A persistence exception,unconfigured database or nonpositive/ambiguous acknowledgement for nonempty data is failed/uncertain,never certified persisted and never automatically replayed.

Keep diagnostics credential-safe as established by the separately merged logger1588 repair. Emit only fixed classes,bounded safe source identifiers and counts; no raw request params,body,headers,exceptions or credential-derived values. This later specification deliberately changes the logger-only spec's preserved error/Information-feed return semantics; it does not silently widen1588 or falsify its historical acceptance.

## Whole-task retry safety and release

Current metadata shows maxRetries1 on fetch-news-sentiment,fetch-news-sentiment-topics and fetch-news-sentiment-earnings. New truthful nonzero exits must not activate whole-universe replay of committed siblings. Before activating the typed-error image,set maxRetries0 on those three named jobs through the reviewed scoped release path. Preserve identity,env/secret bindings,schedules,resources and all other configuration. No IAM/security/credential change. This disables blanket task replay; a later bounded per-source retry contract is not introduced here.

Merge/release the logger-only implementation first,then branch this implementation from MAIN without stacking. Capture the logger-hardened immutable image as rollback target. Pair the zero-retry setting with the typed-error image; verify no active conflicting execution and stop on drift. On rollback restore the logger-hardened image before restoring its prior task-retry setting; never roll back to the known unsafe logger. No manual provider/job replay is authorized by this design. Natural scheduled runs and existing allowed persistence exports are verification; ACK/task green alone is insufficient.

## Files, tests and capacity

Runtime scope:gcp/fetchers/fetch_news_sentiment.py only,plus focused tests and required delivery records. No shared database,COMMON/DATA or workflow implementation copied. Exactly the three named job image/retry settings form the necessary reviewed operational scope. Insight query availability and freshness remain separately owned specifications; no Gamma/ranker formula,source selection,topic-union or historical/PIT rewrite.

Mocked real-module and CLI regressions must exercise valid empty/nonempty,all failure classes,mixed sibling success/failure/empty,malformed article,safe logger,write exception/uncertainty and no second request. Replace the existing rate-limit-to-empty test rather than treating that weak behavior as required. Reuse prior diagnostic evidence; do not rerun accepted options suites.

Existing request cardinality and timeout30 remain unchanged. Outcomes add bounded per-request bookkeeping,not raw-body storage or a new SQL table. Default ticker cap remains existing300;no concurrency or provider allowance increase. No source/SQL call is added and no performance/cost reduction is claimed. Normal plan,independent review,Codex/current-head CI and required records precede release. Unknown native binding,raw HTTP evidence and persisted completeness remain explicit.
