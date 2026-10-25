---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-DATA-001, REQ-REL-001, REQ-SECRET-001]
issues: []
canvases: []
done_when:
  - "tests/agents/test_news_availability.py proves an actual strict-query exception produces availableFalse with controlled reason and absent/null sentiment metrics,while a successful zero-row query remains available valid-empty without a fabricated average."
  - "News context-bundle tests include unavailable news in failed_sections,retain other successful sections,and preserve existing nonempty sentiment aggregation and historical cutoff parameters."
  - "Fake-secret exception controls prove no unsafe exception text reaches the new result or logger; no provider/SQL traffic occurs in tests and only the news summarizer switches query helper."
  - "Directly affected news summarizer/context tests,independent review,own delivery records,no-new docs audit,current-head Codex review and required CI pass; automatic release/migration effects are reviewed before source merge."
status: approved
supersedes: null
---

# News query availability

## Approved scope

The owner's October24,2026 bounded finish authorization covers the already written typed-news-error/availability brief (SHA256cd705665bf59e781f1aac0ccac1e0a2b37270a5c5cab71cabf52c759a88c2882),normal reviews/specification and implementation merges,and scoped deployment ("Do all the work needed"). This is its separate insight-consumer slice,not an expansion of logger-only1588 or a rewrite of every news consumer. FEAT-INSIGHT-001 owns AI report/context availability. Root is the sole writer; existing COMMON/DATA owners retain shared helpers/interfaces. No code before approved specification MAIN. The six-minute CI implementation is now MAIN at e7e74ccc (PR #1599); own current-head checks and authenticated Codex review remain required.

Pinned source7dbf31921e3ec492e332faed445fbd63dd47b019 uses a query helper that returns an empty frame on database failure. summarize_news_sentiment then reports available=True,article_count0 and avg0. Offline AST fixtures independently reproduce this masking. The functions also match those in the verified build input for the existing jobs image; serving API/current frontend usage is not inferred.

## Design

Change only summarize_news_sentiment to use the existing _query_strict/query_to_dataframe_strict interface already owned by COMMON. Do not modify shared helper signatures,transaction/connection ownership,global error semantics or other summarizers. Catch its failure locally and return available=False with fixed reason news_query_failed; no raw exception,query,params,credentials or traceback. Counts and sentiment metrics are absent/null on failure,not0or a sparse-coverage claim. The context bundle's existing unavailable-section path must record sentiment as failed while keeping successful sibling sections.

A genuinely successful zero-row query remains available=True with article_count0 and empty headlines; avg_sentiment_score is null because there is no observed sentiment mean. Existing nonempty aggregate calculations,headlines,lookback,strict historical cutoff and source selection remain unchanged. Do not treat empty news as a bullish/bearish/neutral observation. Tests must distinguish successful zero rows,database failure and actual observed neutral scores. Downstream context consumers must tolerate the nullable average on valid-empty; adapt only directly necessary in-repository consumers without changing ranker formulas or inventing defaults.

## Files and verification

Runtime scope:lib/agents/summarizers.py and only directly required context adapters if a tested nullable-value consumer needs correction; enumerate any such path in the plan before editing. Focused tests live under tests/agents; preserve unrelated summariers and accepted options source. The shared strict interface exists; do not duplicate it or wait for public plan-only PRs as evidence of absence.

Write real-module failing regressions for failure versus successful-empty/nonempty/neutral,context failed-section propagation,malicious exception redaction and historical parameter equality. Do not replace this with AST-only or mock-already-available proof. Reuse prior source probe evidence; no provider calls or accepted-suite reruns. Keep current request/query cardinality exactly one SELECT per news summary with the existing helper's semantics; this slice does not certify a new absolute-deadline API.

## Release and boundaries

lib/** may activate the existing API Cloud Build deployment/migration path. Before source MAIN merge,inspect actual live trigger scope,reviewed build/source identity,current schema-application revision and relevant view/dependency state through STRAT's existing allowed read-only export route. Image rollback cannot reverse committed schema units. Stop any destructive/security/migration surprise rather than disabling a gate or changing IAM. A documentation-only specification merge does not itself authorize unrelated source rollout.

Normal unique ready plan,draft PR,independent diff/tests,Codex review,current-head CI and own delivery records precede source merge/deployment. API/ranker availability contracts,Dashboard historical date/PIT behavior,article watermark/cap/dedup,topic union and source acquisition remain separate work; this minimal repair does not claim all consumer defects are closed. No schema/provider request/retry/schedule/configuration/Gamma/ranker formula or credential change. Existing native connector premium-access cause remains unknown.
