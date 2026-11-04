---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Fresh committed-input acquisition regressions preserve native Git content, modes, missing/error, replacement-ref, repository, SHA1/SHA256 and mutable index/worktree semantics while proving fewer Git subprocesses for the measured repeated-read path."
  - "The complete existing native test_spec_gate.py suite retains every test name, parameter, assertion, case and actual gate/hook invocation and passes with the unchanged serial command; paired baseline/proposed timing and subprocess measurements show the actual improvement without an alternate compiled harness."
  - "The unchanged registry-equivalent suite completes below285seconds, unchanged BASE suites below600seconds and actual current-head hosted registry including exporter succeeds under the unchanged five-minute job timeout; renderer and verifier limits remain unchanged."
  - "Own product records, fresh ordinary declared-note source proof, full-default main/proposed no-new audits, four independent prepush reviews, authenticated current-head external reviews and all required CI are complete before merge."
status: approved
supersedes: null
---

# Fresh committed-read batching for registry capacity

## Problem and measured scope

Actual main is2aac64c0e8b7a10a1e891a7caa78814575960af9; #1569 remains open/frozen at991ad3f707874b1b89e5f3bbcd9645b64c824c07. All three registry attempts carry GitHub's explicit five-minute timeout annotation. Completed suites took295.00/285.20s, above285s; third checkout/fetch consumed60.37/59.61s and suite did not finish. Exporter skipped in all3. Other five checks succeeded, including7594PASS71skipped fullCI. No API/GCP call was identified in this hermetic native-Git suite.

A representative ready gate invocation issued32 Git commands with17 Tree.read calls; repeated HEAD-plan5, HEAD-catalog4, BASE-catalog3, BASE-plan2 and HEAD-spec2 reads were observed. Python subprocess.run accounted for54.4ms cumulative of that profiled invocation, Git internal time23.1ms, measured external wall231.6ms. Separate source compile cost48.8ms. These are diagnostic samples, not proof of a general speedup. A prior full serial native144-case run took255.481s wall and253.148s CPU.

This is a necessary complementary performance repair; it is not already authorized by the immutable eight-case capacity bridge or by the completed generated-inventory implementation. The existing #1538 generated-document allowance is MAIN and needs no new approval or duplicate governance PR.

## Chosen approach and alternatives

Keep serial execution and the exact native command. Reduce redundant independent committed-file reads through fresh bounded Git batch acquisitions within existing gate predicates. Retain native CLI, verdict rules, trust boundaries and all original test calls. Do not introduce cross-acquisition caching.

Blind retries are rejected. Compiled replacement harnesses are rejected. Two-worker pytest was considered but is outside this proposal: existing safe command admission rejects worker flags and new plugin imports require their own trust treatment. No PYTEST_ADDOPTS, environment/plugin shortcut or command-grammar change is permitted. Paid/larger runners, workflow/pin/timeout changes and fetch-depth changes are excluded.

## Design and boundaries

Add a bounded fresh acquisition helper in scripts/gate/spec_gate.py for independent queries whose exact committed revisions and paths are already known within a predicate. It may reuse the established framed git cat-file batch approach, but must not silently expand policy_blob_bytes' fixed catalog/traceability contract. Keep that existing helper and its tests intact unless a directly equivalent internal reuse is independently proven.

At most64 queries and8MiB retained payload per optimized acquisition; larger or unsupported query shapes use the original uncached read path rather than a new acceptance/refusal rule. Revisions must be exact resolved commit IDs, supporting SHA1 and SHA256. Paths containing unsupported framing bytes use the original path; no caller-controlled revision/path can inject batch commands. ANY unsupported, oversized, failed, incomplete or malformed batch MUST discard ALL partial results and repeat the original fresh native reads in their original order, preserving every short-circuit and failure behavior. Validate response object type/mode/size, missing framing, exact delimiters and EOF. Never accept truncated, malformed, duplicate or mismatched replies as content. Retain established missing/read-failure behavior and meaningful refusal classes. Account for limits before allocation where a batch size is known.

The ONLY optimized callers are check()'s initial changed-entry blob/mode loop (991ad lines1959–1964) and its complete HEAD plan-discovery scan (lines2300–2308), plus a narrowly named new helper used only by those two sites. Do not alter check_close_out(), policy_blob_bytes(), or any other predicate. Dynamically dependent queries remain ordered. Preserve original early-refusal order, raw-byte versus universal-newline text semantics, modes, duplicates, symlinks, gitlinks, dirty index/worktree behavior and current policy versus merge-base separation. Do not retain content between acquisitions or invocations. Every acquisition must observe actual repository identity, Git configuration and replacement objects; do not treat a literal object ID alone as proof that presented content is immutable. Index/worktree/symbolic refs and unsupported layouts keep their original native path. No global Tree cache or test-aware production environment.

Do not change production gate predicates, PYTEST_ARGS, import ownership, source verifier/auditor/renderer, workflows, pins, hooks, skills/templates, requirement registries, STRAT, options or GCP files. No new dependencies, provider calls or deployed workload. Existing gate and verifier freshness/security regressions are mandatory controls.

## Focused regression and acceptance contract

Add named regression test_fresh_gate_acquisition_preserves_git_semantics. Real temporary repositories must compare optimized and original raw/text/mode/missing results for SHA1/SHA256; replacement refs changed between acquisitions; identical IDs in distinct repositories; changed index/worktree/symbolic targets; CRLF and non-UTF8 bytes; symlinks/gitlinks; missing/malformed/truncated response framing and failed reads. A mutation after one acquisition must be visible to the next. Prove fallback cases do not retain stale data or broaden acceptance. Real native Git establishes accepted/refused behavior; mocked response faults may test framing only and cannot substitute for success proof.

Add test_gate_batching_preserves_verdict_and_dispatch_economy. Use tests/scripts/test_spec_gate.py::test_a_done_when_item_matches_as_written_or_as_rendered's ready accepted actionlint scenario (item e2e.yml docs globs) and its explicit follow-up deferral-refused sibling. Compare pre-fix and proposed real CLI exit/verdict/diagnostic class and count actual Git child invocations, proving reduction for the same assembled input. Count instrumentation is diagnostic; full acceptance uses ordinary unmodified subprocess commands. Preserve all original assertions, test names, parameter sets, actual hook/CLI calls, negative cases and observer budgets.

Before modification, preserve exact main source and actual failing capacity evidence. Run focused RED/GREEN regressions, all affected gate and neighboring exporter/source suites as required, then one complete unchanged serial registry-equivalent timing with every original case. Compare measured before/after full wall/CPU and dispatch counts honestly; do not infer savings by multiplying one microbenchmark. Keep registry285s, whole job300s, BASE600s, renderer60s/512MiB and verifier5s/8MiB/20000-entry limits. Current exact-head hosted registry must complete the exporter and all checks; a local timing does not replace it. If batching saves too little, report the measured shortfall and stop without raising limits or selecting fewer tests.

## Delivery and authority gate

Owner approved this narrowly scoped performance specification for preparation and publication on October24,2026. It has no implementation and grants no merge authority. Publish the spec alone under the existing workflow and require its actual MAIN merge before a unique implementation branch/ready plan opens. That prerequisite spec still owes normal CI; inability of inherited serial CI to pass remains a blocker, never a bootstrap waiver.

Use a fresh one-plan/one-author/one-PR branch; INITIAL gated PLANONLY commit, one draft PR, next gated PLANONLY commit binding its real number, then CODE. The only runtime source change is scripts/gate/spec_gate.py and meaningful regressions in tests/scripts/test_spec_gate.py. Delivery paths are own plan, FEAT-CICD-001 catalog/traceability, existing SHARED-01 note updated in place retaining inventory/verifier context, and exact ordinary source sidecar. The independently approved declaration here is required; no borrowed declaration or bootstrap reuse.

Four frozen independent prepush seats cover shell, YAML/Actions, exporter/policy and byte/identity/freshness. Fix confirmed findings in one complete batch, then root release and one sole-author push. Normal authenticated external CODE/security reviews, full CI, all conversations resolved and two-round cap apply. Actual merge requires separately verified user authority; this specification publication approval adds none.

After actual merge, fresh network-only actual-main source/body and accepted/refused proof, full-default no-new audit and genuine current-source DOC marker retirement are required. #1569 stays second-round frozen; old-head registry still executes old source. Do not claim a repair on MAIN retroactively qualifies991ad. Any necessary spec re-cut uses a distinct normal PR and preserves the original unmerged branch/history. Once the lifecycle spec is legitimately MAIN, resume its separately planned fixture repair and final status-only plan closure. Do not claim these downstream tasks are complete in the performance PR.

## Capacity and risk

Volume: all144 original gate cases plus meaningful new cases, bounded64query/8MiB optimization acquisition; no product rows. Velocity: fewer native Git subprocesses for the same acquisitions and exactly the same original native gate invocations; no provider/SQL calls. Wall-clock: measured baseline255.481s local,285.20–295.00s hosted; proposed total is unknown until actually measured. Cost: no new GCP resources/schedules/dependencies; existing paid CI usage remains measured. Expected benefit is uncertain and may not cover slow full fetch; no guarantee or fictional green result.

Main risk is changing presented Git/failure/freshness semantics. Actual replacement/ref/index/worktree/error/byte/mode controls and full original suites are mandatory. Optimization that cannot preserve those contracts is discarded, not waived.
