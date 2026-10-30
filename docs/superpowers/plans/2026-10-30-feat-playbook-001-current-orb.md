---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-10-30-feat-playbook-001-current-orb.md
branch: fix/feat-playbook-001-current-orb
pr: null
status: ready
---

# Current-session ORB implementation and consumer repair plan

Parent confirms approved specification merged (Stocks#1638 / Solyra#305). Local base uses exact admitted spec commit; fresh publisher must reconcile actual MAIN merge before publication. Author implementation only, no judgment rounds reserved.

## Task 1: Acquisition and identity
Spec: § Acquisition and identity; advances done_when[0].
- [ ] Write actual mocked-stream request/envelope/byte/row/deadline RED controls, then implement exact single existing-provider acquisition.

## Task 2: Session and comparison
Spec: § Session and comparison; advances done_when[2].
- [ ] Pin sharedhelper lineage; implement clocked30m qualification and distinctORBcomparison field with actualAPI/evaluator counterexamples.

## Task 3: Reuse and resource contract
Spec: § Reuse and resource contract; advances done_when[4].
- [ ] Exercise existingSingleFlight/ThreadSafeCache and boundedroutebudget; measure cappedconcurrentRSS/eventloop; freeze acceptable comparisonage policy and imagecalendar dependency.

## Task 4: Files and close-out
Spec: § Files and close-out; advances done_when[6].
- [ ] GenerateOpenAPI; update owncatalog/PRlineage andPLAYBOOK-05sourceproof; run actualdocs/gate/checks and reserve currentreviewledger.

## Consumer first-review repair — 2026-10-30

Runtime first local consumer review covered head `68139f8beecfae7e9590ecb9cbd28b0b9a5fc37e`. Root authorized one complete four-finding repair batch; no second judgment review or hosted CODE round is invoked here. Cached MAIN `05830d8d535de7f8003c9642417adedc2890ad75` is reconciled at `f624e9cb`, preserving admitted signal fairness, provenance, schemas and all three signal source notes.

- P2 timestamp identity: reject noncanonical vendor aliases and duplicate normalized instants across the entire series, including comparison and non-opening rows. Opening-window alias refusal already passed; post-window/pre-window aliases reproduced RED.
- P2 calendar admission: shared fail-fast cold construction admits one build across router/evaluator; warm date hits remain usable while a different date builds. Eight-date cache remains bounded. Contention is explicit unavailable, never a queued worker or second builder.
- P2 response deadline: two-slot admitted parser executor owns actual worker completion. Request completion and worker completion jointly release the claim/slot once; normal success publishes cache before release, while timeout/cancel returns without waiting for the parser. No background cleanup task is spawned; loop closure cannot release a live worker's claim. Late success is not cached, late errors are consumed.
- P3 overflow/isolation: vendor conversion, public parse/reduction arithmetic and projection conversion refuse overflow; only matching ORB predicates qualify the ORB projection. Unrelated minutes-after-open evaluation remains independent.

Verification: original four-class controls produced 9 failures/1 existing pass; additional arithmetic overflow reproduced one failure. Final guarded affected suite: 137 passes (parser, calendar, cancellation/deadline, evaluator, schema/OpenAPI, Eastern time, live signal series and chart voter). Socket and SQL-engine tripwires prohibit external I/O; tests use mock mode. Logs: `/tmp/orb-repair-red.log`, `/tmp/orb-overflow-red.log`, `/tmp/orb-repair-suite.log`. This is the affected hermetic suite, not all repository tests.

Ruling: preserve the existing repeated-cancellation control's resource assertions, but wait boundedly for actual worker completion after request cancellation instead of assuming request completion means worker completion — this is the corrected ownership contract; a wrong handoff would leak a slot or permit excess parsing, covered by two-expired-worker and closed-loop controls.

Ruling: explicit parent authorization includes the P3 overflow repair in the same batch. No new review cohort, source publication or allowance reset. Root owns publication. API image proof remains blocked by the previously reported Docker buildx permission denial; no retry/override. Combined frontend/backend fleet quota is unqualified, not quota-neutral. Generated inventory, final committed source proof, full committed-doc gate and matched docs audit must be completed after the shared CPU window permits them.

### Candidate capacity measurement

Equivalent guarded candidate workload (original producer script was not retained): two concurrent parsers, each 50,000 rows and 7,950,156 bytes, completed in 4.838243 seconds. Process peak RSS was 207,208 KiB including imports and fixture generation; maximum observed event-loop gap was 0.128466 seconds. Each response projected 599 bytes and returned 31 same-session bars. Receipt `/tmp/orb-candidate-capacity.json`, runner `/tmp/orb_candidate_capacity.py`. This is a new local candidate measurement, not byte-identical reproduction of the author's 3.493875-second/203392-KiB/0.069-second receipt, nor API image, production latency or fleet proof. Fixed parser/input/concurrency bounds are unchanged. Docker remains unretired and quota must still qualify before activation.

Renderer receipt: explicit three-path frozen-snapshot invocation hit the fixed 60-second timeout (exit 124) after only ARCHITECTURE completed. Its partial generated delta was restored; no cap raise, split render or retry has been performed. Full generated-document acceptance remains blocked pending a supported successful run. Log: `/tmp/orb-inventory.log`.
