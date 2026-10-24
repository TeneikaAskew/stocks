---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-CAP-001, REQ-CAP-003, REQ-REL-001, REQ-GOV-004]
issues: [859]
canvases: []
done_when:
  - "tests/lib/test_av_account_allowance.py fails on the150RPM baseline and proves AlphaVantageConfig().rpm is600, its account_rpm alias agrees, explicit local_rpm is distinct and no invalid local/account allowance is admitted."
  - "tests/lib/test_av_account_allowance.py proves derived local delay and batch size, default conservative150RPM/0.4seconds behavior and an explicitly configured local600RPM/0.1seconds case without treating that local setting as a shared reservation."
  - "tests/scripts/test_av_client_pacing.py proves both actual research CLI parsers/default batch loops consume local batch/delay, refuse invalid or unallocated faster delay overrides before dispatch, and preserve existing error/backoff/circuit decisions with zero provider calls."
  - "Consumer/configuration tests inventory all in-repository AlphaVantageConfig consumers, preserve existing task-count pacing partition exactly once, and prove no consumer automatically turns the purchased600RPM field into600RPM for every worker."
  - "Normal own plan/product records, independent review, no-new documentation audit, current-head required CI and review pass; no source claims global account enforcement, verified unused capacity or rollout before actual evidence."
status: approved
supersedes: null
---

# Purchased Alpha Vantage allowance and explicit local pacing

## Problem and owner authority

The user explicitly authorized runtime correction on October24,2026: "Fix it in my code.600not150." The confirmed199.99/month plan supplies600requests/minute and no daily request limit. Main641a93b96 lib/config.py instead models150as the plan, returning60/rpm for delays andrpm for batch size. This is executable configuration, not merely inaccurate Markdown. Documentation-only PR1584 does not complete this change.

FEAT-DATA-001 owns data-platform configuration. This candidate requires written design approval and actual approved-spec MAIN before implementation under product-delivery. The owner subsequently approved the bounded finish pass covering this written 600-RPM design, required Codex review, normal specification/implementation merges and scoped release on October 24, 2026 ("Do all the work needed"). All five acceptance items and the account600/local150 separation remain unchanged. Specification MAIN and normal current-head checks still precede runtime implementation. Publication waits for the fixture-owned CI-envelope implementation to reach MAIN; do not retrigger unchanged five-minute CI. Root is the sole intended writer for this slice. Coordinate lib/config.py ownership with existing DATA/COMMON owners; do not push their private branches or copy their implementation. Freshness1580 owns disjoint API/UI paths and the native source worktree/evidence remains unchanged.

## Scope and selected approach

Make AlphaVantageConfig.rpm the actual purchased account allowance, default600, and expose an unambiguous account_rpm alias of that same runtime value. Introduce explicit local_rpm default150 as a conservative per-process/job pacing allocation. This preserves the existing source traffic by default while correcting the actual account value; it does NOT silently set every worker to0.1seconds. The conservative default avoids an unreviewed fourfold increase across concurrent jobs/API processes; it is neither an entitlement nor proof that all concurrent local allocations fit600.

Derived delay_between_calls becomes60/local_rpm and batch_size becomeslocal_rpm. Validate finite integer account/local values, reject booleans/zero/negative and local_rpm>rpm, and refuse an account ceiling above the confirmed600without a separately authorized plan change. Constructor/default interpretation is explicit; rpm is no longer the ambiguous local batch threshold. An explicitly configured local_rpm600 yields0.1seconds/600localbatch, but only its operator's coordinated allocation can authorize that throughput. This class is not an account-wide governor or reservation ledger.

A purely documentary fix is insufficient. Simply replacing150with600in the existing class is rejected: it would accelerate every independently constructed consumer and cannot enforce a shared account ceiling.

## Consumers and concurrent behavior

Inspect every direct AlphaVantageConfig import and derived rate/delay/batch use before code. Current consumers include evaluate_ew_strikes, fetch_alphavantage_intraday, fetch_av_earnings_options_backfill, fetch_av_historical_options, fetch_av_indicators, fetch_av_realtime_options, fetch_earnings_history, fetch_insider_transactions, lib/ticker_info and both scripts/fetch_alphavantage_* research CLIs. There are also source callers with independent pacing; this change cannot claim they participate in a global account guard.

Both research scripts currently initialize CALLS_PER_MINUTE fromcfg.rpm; migrate those actual batch thresholds tocfg.batch_size. Their --delay override currently can bypass limits, including a zero-delay fallback150. Validate override against the explicitly selected local allowance before any dispatch, permitting slower pacing but refusing a faster/unallocated override or invalid/nonfinite value; do not silently raise the local allocation. Existing invocation configuration is unchanged unless explicitly reviewed; no new environment variable, schedule, pool, resource or account binding is added here.

The intraday replace-month path already multiplies delay bytask_count. Preserve this partition exactly once, under the job's local allowance; do not divide or multiply again because the account field is600. Independent job/process local limits still do not mathematically guarantee total account usage. Test that distinction, do not invent a shared store or four-worker assumption. No automatic full600allocation to every process is introduced.

## Boundaries

No backoff, circuit-breaker, request classifier, retry count, options/Gamma/valuation formula, provider call, credential/key rotation, account purchase, IAM/security/network, job execution or deployment in this specification change. Source/storage admission protocols remain unchanged. Four already-authorized analytical reads do not wait for this configuration implementation, a new account-reservation service or the separately pending reusable database lifecycle API. Their conservative operational one-attempt plan remains valid.

Runtime files are limited to lib/config.py and the local rate/batch override blocks in scripts/fetch_alphavantage_intraday.py and scripts/fetch_alphavantage_options.py. Direct consumer files are inspected/tested for compatibility, not edited indiscriminately. If inventory reveals another use ofrpm as a pacing threshold, enumerate that additional exact path for owner review before implementation rather than silently widening this candidate. No changes to private COMMON/DATA/IND interfaces are included.

## Regression and delivery

An external read-only baseline acceptance probe already reproduces the missing account/local distinction, lack of600ceiling validation and retained current150/0.4pacing; no provider or database calls occur. After approved-spec MAIN, write the unique ready plan, move meaningful behavioral tests into the named suites and implement the minimum fix. Prove runtime600account identity, local allocation/derived intervals, explicit local600, invalid configurations, actual CLI negative-before-network controls and task-count partition with mocked clocks/transport. Preserve generic client retry and breaker behavior. Do not rerun accepted349options suites when this slice does not change those components; run directly affected compatibility checks only.

Open implementation as a draft, follow one writer and ordinary review/gate/no-new audit/current-head CI. Do not merge/deploy on unit tests alone. Existing release authorization is conditional on normal checks and actual intended runtime/configuration verification. Current source/image/key/account activation and shared consumption remain separate evidence, not inferred from configuration values.

## Capacity

Configuration work is constant-size. Default velocity remains150localrequests/minute with0.4second pacing; account allowance becomes correctly600. Explicit local600is not a global capacity grant. No new provider/SQL calls, durable tables, jobs or resources are introduced. Ordinary mocked configuration/CLI tests are low-cost and must not interfere with the fixture owner's isolated timing diagnostic. No p95, production-throughput improvement or dollar-cost reduction is claimed without measurement.
