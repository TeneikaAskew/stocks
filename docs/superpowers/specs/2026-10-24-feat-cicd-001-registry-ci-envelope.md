---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The registry job uses literal timeout-minutes: 6 through separately reviewed pinned-copy-first and matching-live-workflow PRs, with no other execution, permission, dependency, isolation or runtime-deadline change."
  - "Existing native pin-order and workflow-contract controls reject a live-only or simultaneous pin/live timeout change; all original tests, assertions, native invocations and required checks remain present and pass."
  - "Exact-head hosted receipts for both implementation stages show every required check passing and pytest at most 285 seconds; the activated six-minute job additionally meets every component allocation and finishes within 335 seconds with at least 25 seconds measured headroom."
  - "Observed stage timings, exporter execution mode, cost and verification limits, independent reviews, ordinary source proof and full-default main/proposed no-new audits are recorded before release; any unresolved capacity or evidence failure holds release without retry loops or a gate waiver."
status: approved
supersedes: null
---

# Registry CI job envelope: six minutes, unchanged safety contracts

## Decision requested and authority

The owner approved **360 seconds / literal `timeout-minutes: 6`** for only the stocks `registry-check / registry` CI job on October 24, 2026, at reviewed head `58bc6be119a7ec39d086a8b2c049203f14ca2830`. This is a capacity design, not a performance improvement. The bounded finish authorization covers required Codex reviews and conditional specification and scoped implementation merges through normal protections, preserving the285s suite ceiling and all runtime caps/checks. It grants no check waiver, protection bypass, security/access expansion or stopped-candidate release. No implementation branch opens before this approved specification is actually MAIN.

Feature ownership is FEAT-CICD-001: “CI / testing | Build, test, deploy automation.” REQ-GOV-001 preserves review resolution and REQ-GOV-004 preserves the generated-document contract. The canvas registry has no FEAT-CICD-001 mapping. Referenced PR numbers below are evidence links, not issue numbers to close.

This design neither supersedes nor activates the stopped batching or regex candidates. Their source/test commits and private evidence remain intact and excluded from implementation. #1582's eleven-pattern design preserves its own deadlines and stop-on-no-gain condition; this proposal does not revive its stopped CODE. #1581's separate runbook policy and the reusable deadline API remain outside scope.

## Problem and observations

The existing job has a five-minute wall-time limit but must complete checkout, installation, verdict startup, the full serial native suite and the final exporter. Passing assertions alone is not this check's terminal success.

| Observed receipt | Pre-suite elapsed | Suite-step elapsed | Job outcome |
| --- | ---: | ---: | --- |
| [#1579 PLANONLY job120867286364](https://github.com/TeneikaAskew/stocks/actions/runs/40092299943/job/120867286364) | 23s | 290s, cancelled | Exporter skipped; five-minute cancellation |
| [#1582 updated-head job120936965942](https://github.com/TeneikaAskew/stocks/actions/runs/40115891871/job/120936965942) | 13s | 231s | 246s whole job; exporter successful |
| [#1583 job120941516486](https://github.com/TeneikaAskew/stocks/actions/runs/40117426130/job/120941516486) | 16s | 286s, cancelled | 305s including cancellation/cleanup; exporter skipped |

These are job/step timestamp differences, not all pytest durations. The suite step includes `pip install pytest pyyaml`; its elapsed time cannot be called pure test time. The pre-suite interval includes the earlier PyYAML installation in the compile/verdict step. A successful exporter was recorded within one timestamp second; that is not proof of zero cost or a worst-case bound. The 305s cancelled job does not establish that the nominal timeout changed.

Baseline gate, original suite and registry workflow blobs on #1583 match the preserved baseline (Git blobs d3c351a7…, 65684053…, 7701917f…). Actual MAIN7dbf31921e3ec492e332faed445fbd63dd47b019 has identical live/pinned workflow SHA256 c92ada9e04ff837920e79ba0f4db97b579e4a8efe7b4b48b53472d9f703f1dcd. Future implementation must recheck current MAIN rather than assume these identities remain current.

Local uninstrumented baseline:144PASS,253.027s wall. The stopped regex candidate:144PASS,253.441s; no demonstrated gain. A separate instrumented original slowest test passed once in55.635s wall:267native gate lifecycles46.370s and2082in-body fixture Git calls5.370s. Its instrumentation does not certify hosted throughput. These results motivate budgeting required work, not fewer tests or an invented faster gate. Host hardware, package-install variance and the full startup/check cost split are not established by these receipts. No denied log route was used or is authorized by this proposal.

## Concrete budget: observations versus proposed reserves

| Allocation | Seconds | Basis and meaning |
| --- | ---: | --- |
| Setup, checkout and compile/verdict, including its installation | 25 | Proposed allocation; largest inspected pre-suite observation23s plus2s allowance. Not a measured percentile. |
| Suite-step overhead, including its separate installation and Python/shell startup | 15 | Proposed reserve; not separately measured yet. Excludes pytest's reported elapsed time. |
| Full native pytest suite | 285 | Preserved acceptance ceiling, not a new or relaxed value. |
| Required exporter | 5 | Proposed reserve; successful metadata does not prove this upper bound. |
| Post-job cleanup and completion | 5 | Proposed reserve; measure from exporter completion through terminal job completion. |
| Additional variability/headroom | 25 | Explicit proposed reserve beyond the component allocations; not a measured p95 or promised capacity gain. |
| **Whole CI job** | **360** | **25 + 15 + 285 + 5 + 5 + 25 = 360; six whole minutes.** |

Component allocations sum to335s; admitted complete jobs must retain at least25s headroom to360s. The pre-suite2s allowance and final25s reserve are separately stated, not double-counted observations. Six minutes is the smallest whole-minute proposal that includes these declared allocations; five minutes cannot hold them. This is an engineering budget for owner approval, not proof that every future run fits it.

The reserves are observation/admission criteria, **not newly inserted per-step kill timers**. Do not add timeout wrappers, retries, caching, instrumentation, split/moved steps or dependency-install changes under this scope. If a reserve is exceeded, the required check is never reported as failed when GitHub says success; instead the implementation's capacity acceptance remains incomplete and release is held with the actual evidence.

An observed pytest duration over285s remains a capacity failure even if a six-minute job finishes. The 25s variability reserve is not permission to borrow time to waive that ceiling. This proposal repairs the outer envelope mismatch only; it cannot guarantee removal of every underlying throughput failure.

## CI envelope versus runtime safety

The CI timeout limits wall time for one hosted validation job. It grants no operation, renderer, verifier, database, provider or application a longer runtime deadline. Preserve the exact serial command:

`python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest`

Preserve every original case/assertion, fresh native gate invocation, temporary-repository isolation, source/byte/identity/freshness check, failure behavior and exporter contract. Preserve the285s proposed-suite and600s BASE ceilings; renderer60s/512MiB; verifier5s/8MiB/20000entries; and every other existing resource/cancellation/cleanup invariant. No workers, xdist, persistent interpreter, alternate compiled harness, fixture sharing, skipped check, relaxed descendant assertion or dependency/runner change is included. All existing workflow triggers, required names, checkout identity, read-only permissions and unconditional commands stay exact.

## Narrow future implementation and trusted sequence

Only the registry job's literal integer changes from5to6 in these two files, through **two independent, sequential implementation PRs**:

1. From actual approved-spec MAIN, a normally gated ready plan and initial/bound PLANONLY draft precede CODE. Change only `scripts/gate/pinned/registry-check.yml`'s `jobs.registry.timeout-minutes` to6. The live workflow remains5. Complete ordinary review/check/source-proof requirements and obtain separate merge authority.
2. Only after stage1 actually MAIN, open a new branch/plan/draft PR from that MAIN; change only `.github/workflows/registry-check.yml`'s matching property to6. No stack on the unmerged stage1 branch. Complete ordinary review/check/source-proof requirements and obtain separate merge authority.

The gate reads the trusted pin from BASE and refuses a live change that differs. Existing WORKFLOW_CONTRACTS checks remain a second line. A change to both pin and live in one PR does not satisfy the sequence. No spec_gate.py validator, trusted rule, exporter, suite, hook, runtime source, interpreter flag or installation command is authorized to change. Existing native contract tests and concrete negative probes establish pin-order refusal; do not add a test that merely mirrors the number6 or alter existing tests.

Allowed accompanying delivery changes are each implementation PR's own ready plan, FEAT-CICD-001 catalog/traceability record, existing declared SHARED-01 note and ordinary source sidecar, plus any exact renderer-owned inventory updates already admitted by actual MAIN. This is no new documentation-governance exception. Four independent prepush gate-file review seats and normal review caps apply. If actual MAIN or required gates reveal a needed change beyond this list, stop at that boundary and seek the smallest separate design decision; do not widen scope silently.

## Observation and success criteria

Each implementation stage must have current-head authenticated review, no unresolved conversations and all required checks passing. Record exact head/base, source/workflow identities, actual suite case/skip/warning counts, pytest-reported elapsed time, all step timestamps and job-terminal timestamps. Preserve all original cases and refuse newly skipped coverage. Record runner image, Python/Git/package versions and available CPU/memory metadata when already available through supported evidence; do not infer missing values or expand CI instrumentation under this design.

For stage1, the unchanged five-minute live job must genuinely pass with its exporter and pytest at most285s; record actual headroom against its real300s ceiling without imposing the proposed25s end-state headroom on this unchanged bootstrap. Prospective six-minute permission cannot excuse a failed bootstrap check. For stage2, the actual head's live registry job must finish successfully within335s, giving at least25s measured headroom under360s. At least these two legitimate implementation heads supply observation; do not manufacture empty commits, replay successful suites or run acceptance repeatedly to choose a favorable timing. Any unavailable or failing acceptance remains explicit, rather than being hidden by a later passing sample.

For the activated stage2 job, measure pre-suite interval at most25s. Require pytest at most285s. Define suite-step residual as the entire suite-step interval minus pytest-reported elapsed: it includes installation, launch and shell overhead, not a pure pip measurement. Require that residual at most15s; use the known whole-second timestamp resolution conservatively. Require exporter step success within5s, cleanup/completion within5s, and complete job at most335s. Report every allocation and total; do not substitute pytest success or local timing for hosted completion.

Record whether the exporter performed its full comparison or the existing legitimate unchanged-input notice path. Neither a skipped exporter nor an invented registry change qualifies. The5s full-path reserve remains an assumption until that path has actual timing evidence; absence of that evidence limits the capacity claim. Existing exporter regression coverage must stay green. Do not claim the unchanged-input path measures every exporter workload.

Supported exact-head logs are necessary for case counts and pytest/residual attribution. A denied/empty log route is an evidence blocker, not permission to bypass access controls or guess values from step metadata. Normal recoverable CI work requires its own evidence/authority; no blind retry, check waiver, timeout extension or early merge is granted. The specification itself may face the current five-minute check: it must pass existing gates before merge, and implementation cannot be used to preempt its specification gate.

## Cost, risks and rollback

Volume: one registry job per existing PR event; event frequency, runner class, concurrency, CPU and memory unchanged. The configured CI timeout allowance rises300to360s, a nominal60s/20% increase. Successful runs are not forced to use the extra minute. ForNjobs that fully consume the added allowance, the arithmetic isNadditional nominal runner-minutes; this is not a hard maximum on actual occupancy or cost. Cancellation/cleanup tails may extend occupancy beyond the configured timeout, and billing rounding may differ. Billed cost depends on actual billable occupancy and the applicable rate; the account's rate, free allowance, rounding and cancellation-tail bounds are not established here. No new GCP workload, upload, provider request or SQL action is introduced.

Risks: slower cancellation of a genuinely hung CI job; finite proposed reserves may be exceeded; a green job can still fail the preserved285s suite criterion; exporter fast-path observations may underrepresent full-path work; infrastructure variance is not explained or repaired by a larger envelope. Observe and report those limits rather than claiming gate-code speedup or incident closure.

If legitimate hosted observations fail allocations, headroom, safety or coverage, hold release and preserve receipts. Rollback is separately authorized, reviewed source reversion through the same pin-first protocol: restore the pinned timeout to5 in one PR, then restore the matching live timeout in a subsequent PR after the pin is MAIN. Do not edit live/pin together, use the GitHub UI to bypass the pin, change branch protection or disable a check. Returning to5 knowingly restores the old envelope and may restore its cancellations; it is containment, not a claimed fix. Active jobs retain their admitted launch configuration. No rollback action or implementation merge is authorized by publishing this draft.

## Alternatives and approval boundary

Retain five minutes: no policy change, but measured pre-suite work plus a285s suite leaves no exporter allowance. Production-gate optimization with unchanged native coverage: potentially useful, but both preserved candidates demonstrated no gain and no additional optimization is designed here. Reducing process isolation changes the proof contract and requires separate explicit owner approval; it is excluded.

Design approval is recorded for this concrete six-minute design, including its proposed reserves and acceptance conditions. Only after normal specification MAIN merge may implementation planning begin. Specification and scoped implementation merges remain conditional on required current-head reviews/checks and ordinary protections; this approval does not cover unrelated governance, a runtime-cap change or deployment.
