---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The registry job uses literal timeout-minutes: 10 through a pinned-copy-first PR and then a separate PR that makes the live workflow equal to the pin, with no other execution, permission, dependency, isolation, runner or runtime-deadline change; one PR changing both is refused."
  - "Existing native pin-order and workflow-contract controls pass and reject a live-only or simultaneous pin/live timeout change; every original test, assertion, native invocation and required check stays present and passes, with the suite still serial and unchanged."
  - "The live-stage hosted registry job on its exact head passes every test of the suite then on main and the unchanged exporter, and its measured whole-job time leaves at least 120 seconds of reserve under 600 seconds; exact head/base, pytest, setup, gate-step, exporter and whole-job timings are recorded with every attempt, and no retry selects a favourable sample."
  - "Owned records, ordinary SHARED-01 source proof, full-default main/proposed no-new audits, the gate-file red-team pass per stage, current-head review as CLAUDE.md section 2.5 counts it (or an owner-recorded substitute for that PR), every required check and zero unresolved threads are complete for each stage."
status: approved
supersedes: docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-ci-envelope.md
---

# Registry CI job envelope: ten minutes, matching base-suite

## Decision and authority

On 2026-11-02 the owner was asked to choose between two changes:
1. raising the `registry-check / registry` job limit from six to ten minutes;
2. parallelizing its suite with pytest-xdist.

The owner answered "I approve all." at 01:13:51 UTC. The coordinator relayed the answer at 01:19:22 UTC as approving the six-to-ten-minute capacity change, delivered through the normal reviewed specification and the pinned-then-live workflow process, with every test and check kept. This spec records that decision.

The approval is not a GitHub review approval. It waives no check, hook or gate-file red-team pass, and it authorizes no deployment. It covers only this CI job's wall-time limit.

Feature ownership is FEAT-CICD-001 ("CI / testing | Build, test, deploy automation"). REQ-GOV-001 preserves review resolution; REQ-GOV-004 preserves the generated-document contract.

## Why the six-minute envelope no longer holds

The superseded design, `2026-10-24-feat-cicd-001-registry-ci-envelope.md`, set a 360 second job limit. It was delivered through its pin primary (`2026-10-24-feat-cicd-001-registry-ci-envelope-pin.md`) and its live-stage acceptance (`2026-10-25-feat-cicd-001-registry-measured-acceptance.md`). That acceptance required a whole job of at most 335 seconds with at least 25 seconds of reserve. It also recorded the earlier 285 second pytest target as UNMET at 288.72 seconds on 59b9a309. Those two stage specs stay as the delivered history of the six-minute design. Their six-minute values are replaced by this spec.

Since then, the same serial suite grew from 144 to 178 tests when #1656 landed (main cb136f3e). Measured hosted receipts, all on the unchanged workflow:

| Receipt | Tests | pytest | Whole job | Reserve under 360 s |
|---|---|---|---|---|
| #1663 job 124929154616 | 144 | 292.25 s | 317 s | 43 s |
| #1608 attempt 1, job 124931132782 | 144 | cancelled | 376 s | cancelled |
| #1608 attempt 2, job 124937986134 | 144 | 307.01 s (all passed) | 367 s | cancelled at the cap |
| #1656 job 125016211960 on 1b38d42b | 178 | 307.26 s | 328 s | 32 s |
| #1676 job 125027790311 on 3fa2a035 | 178 | not read | 260 s | 100 s |
| #1649 job 125029871939 on c419a54e | 178 | not read | 344 s | 16 s |
| #1642 job 125031496374 on 8517d2d3 | 178 | not read | 350 s | 10 s |

Whole-job times are the job's started-to-completed interval.

**Where the time goes.** About 77 percent of the suite is gate subprocess runs: 1,295 gate runs took 273.9 s of a 357 s local suite. The same suite already runs under `timeout-minutes: 10` in spec-gate's base-suite job. A code-touching PR also adds a 26 to 49 second gate step before the suite. So a slow runner plus a code PR crosses 360 seconds without any test failing, as #1608 shows.

## Decision

Raise only the stocks `registry-check / registry` job to literal `timeout-minutes: 10` (600 seconds). That is the limit base-suite already uses for the same suite.

Nothing else in the job changes:
- the exact serial command `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest`;
- every test and assertion and each fresh native gate invocation;
- temporary-repository isolation;
- the exporter;
- triggers, required check names, permissions, dependencies and the runner;
- every runtime safety deadline: the 600 s BASE ceiling, renderer 60 s / 512 MiB, verifier limits, and the rest.

No workers, xdist, persistent interpreter, fixture sharing or skipped check is added. No speedup is claimed.

**New acceptance.** The six-minute design accepted a whole job of at most 335 seconds with a 25 second reserve. This spec replaces that with: the live-stage job must leave at least 120 seconds of reserve under 600 seconds. The worst job measured above (376 s) would leave 224 seconds. The old 285 second pytest ceiling is not carried forward as an acceptance limit. It stays history, as the 2026-10-25 acceptance already recorded it UNMET.

## Sequence (pinned files)

1. This spec is on main.
2. **Pin PR.** From main, with its own ready plan, change only `scripts/gate/pinned/registry-check.yml` `jobs.registry.timeout-minutes` from 6 to 10, plus this capability's own plan and records. The live workflow stays at 6 and still bounds that PR's own run.
3. **Live PR.** After the pin PR merges, a separate PR from the new main makes `.github/workflows/registry-check.yml` byte-equal to the pin.

The gate reads the trusted pin from BASE and refuses a live change that differs; WORKFLOW_CONTRACTS is the second line. Each stage PR changes a gate file, so before each push it needs the gate-file red-team pass. That means one reviewer per attack surface (shell; YAML/Actions; exporter and policy documents), with each bypass proven by running the gate against a concrete snippet. Findings are fixed in one batch, and the change goes up in one push. The operation refused on stocks#1630 is not retried, replaced or routed around.

## Cost, risks and rollback

**Cost.** One registry job runs per existing PR event; event frequency and runner class are unchanged. The limit rises from 360 to 600 seconds. Runner cost changes only when a job would previously have been cancelled at 360 seconds, or when a job hangs: at most 4 more runner-minutes per such job. Successful runs are not forced to use the extra time. No production job, schema, scheduler or deployment changes.

**Risks.**
- A genuinely hung job is cancelled four minutes later.
- The suite keeps growing, so the reserve shrinks as tests are added.
- A larger envelope does not explain or repair runner variance.

**Rollback.** Use the same pin-first order: restore the pin to 6 in one PR, then the live workflow in the next. Never edit both together, and never bypass the pin.

## Alternative not chosen

Running `pytest -n auto` (pytest-xdist) took 100.85 s locally, against 336 to 357 s serial, and would keep six minutes. It was not chosen because:
- it adds a dependency to both gate workflows;
- it needs an xdist-safety review of every test;
- the hosted runner's CPU count is unchecked;
- it changes spec-gate.yml's base-suite too, which means four pinned PRs.
