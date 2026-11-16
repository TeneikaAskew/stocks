---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-10-30-feat-playbook-001-current-orb.md
branch: fix/feat-playbook-001-current-orb
pr: 1642
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

Ruling: explicit parent authorization includes the P3 overflow repair in the same batch. No new review cohort, source publication or allowance reset. Root owns publication. API image proof remains blocked by the previously reported Docker buildx read-only-filesystem failure; no retry/override. Combined frontend/backend fleet quota is unqualified, not quota-neutral. Generated inventory, final committed source proof, full committed-doc gate and matched docs audit qualify the final committed candidate separately from source tests.

### Candidate capacity measurement

Equivalent guarded candidate workload (original producer script was not retained): two concurrent parsers, each 50,000 rows and 7,950,156 bytes, completed in 4.838243 seconds. Process peak RSS was 207,208 KiB including imports and fixture generation; maximum observed event-loop gap was 0.128466 seconds. Each response projected 599 bytes and returned 31 same-session bars. Receipt `/tmp/orb-candidate-capacity.json`, runner `/tmp/orb_candidate_capacity.py`. This is a new local candidate measurement, not byte-identical reproduction of the author's 3.493875-second/203392-KiB/0.069-second receipt, nor API image, production latency or fleet proof. Fixed parser/input/concurrency bounds are unchanged. Docker remains unretired and quota must still qualify before activation.

Renderer receipts: an initial `--insert` invocation and then corrected three-path `--restore` each hit an additional shell `timeout 60s` wrapper (exit 124). These were NOT the formal repository 60-second/512-MiB qualification. Logs `/tmp/orb-inventory.log` and `/tmp/orb-inventory-restore.log` preserve both failures; the latter partial delta is `/tmp/orb-inventory-restore-partial.patch`. The exact ordinary `--restore` for ARCHITECTURE, DATA_DEPENDENCIES and API subsequently completed with exit 0 in the confirmed quiet window (`/tmp/orb-inventory-restore-complete.log`), without splitting the renderer or changing formal caps. Existing restore compares then re-renders changed blocks, so its work differs from the formal committed comparison. The first formal measurement completed in44.42seconds at528818176-byte sampled aggregate, failing only stale-doc comparison; final committed qualification is recorded separately. The first full committed-document test likewise failed only three stale blocks before restoration.

## Authorized SEC fairness repair — 2026-10-30

Parent authorizes the remaining CODE2 repair batch for SEC `r4420960497`, retaining its Low/P3 classification, against published head `55069c27fc7ec990992d341be5d7e4613c455f6f`. The approved policy is four uncached dispatch attempts per server-verified principal per rolling60seconds within the unchanged eight-attempt process-global ceiling. All users requesting ORB must be authenticated; cache hits remain uncharged only after identity qualification. No new judgment round or historical allowance reset is invoked by this author repair.

### Existing-spec admission mapping

The approved §Reuse and proposed resource contract says **at most8full dispatch attempts/rolling60s/process INCLUDING failures/evictions**, not eight per caller. Adding the authorized four-principal predicate is stricter admission on the same bounded deque and lock; it does not increase global throughput or create a new governor architecture. `done_when[4]` covers all-attempt accounting, cache, rollover and bounded admission; the new actual-ASGI controls extend that evidence. `done_when[0]` preserves default compact behavior, and `done_when[5]` preserves unrelated condition/quote inputs. No clause promises anonymous/open/IAP ORB access. Parent adjudicated this refinement as covered by the existing specification, so the approved spec is unchanged and no successor is required merely because the old text lacked the stricter detail.

### Identity and resource behavior

Use only `request.state.user_email` established by existing Firebase middleware while AUTH_MODE is firebase. Its existing bearer verification trims and lowercases the verified email; that canonical verified email is the principal, not a new UID or account-identity scheme. Case variants of the same verified email share the allowance. Caller identity headers never qualify; missing/invalid/unverified Firebase and legacy open/IAP requests cannot reach ORB calendar, cache, claims or provider work. No anonymous production bucket and no claim that an IAP header was application-verified. Default compact history keeps its existing auth/middleware behavior.

The existing <=8 attempt records now contain timestamp plus fixed32-byte SHA256 key of the verified email. There is no per-user map, no stored plaintext principal and no principal logging. Every admitted dispatch, including provider failure and cancellation, consumes both allowances; rejected requests do not create records. Successful cache hits remain uncharged even when both allowances are full. Singleflight, two worker slots, 15second deadline, cancellation/worker-completion ownership, input/row caps, cache size/TTL and parser behavior are unchanged. This is per-process/per-verified-email isolation, not a multi-account or fleet-fairness guarantee.

### Actual author verification and deployment boundary

New targeted controls on the reviewed source produced **6 failures/6 passes** (`/tmp/orb-principal-red.log`), including one-principal starvation and open/IAP/cache authentication gaps. The existing137-test historical repair receipt remains valid for its earlier head. The complete affected suite on this repair passes **192 tests with1 existing skip** (`/tmp/orb-principal-affected-suite-final.log`,5.94seconds): the prior affected selections plus real-ASGI authentication/fairness, canonical identity, forged headers, warm-cache rejection, four/eight limits, failures, rollover, concurrent admission, repeated cancellations and bounded many-identity state. Skip: `tests/api/test_platform_auth.py:348`, no test Postgres configured; no DB setting was changed and no database contact attempted. Socket/SQL-engine tripwires and mocked provider/Firebase SDK verification were used; no real credentials, provider, SQL or browser work.

The existing GCP owner reports09:45UTC production AUTH_MODE=firebase on revision00048-v4z, generation48/48,100% traffic, image prefix77c357e3; its unauthenticated default history GET returned401 with sign-in detail and no redirect/retry. This owner-supplied evidence is not independently re-fetched here, not proof of all routes or successful authentication, and not proof this ORB repair is deployed. No security settings change is indicated by that evidence. Root/GCP owner must preserve verified authentication and qualify the actual deployment/image and combined fleet allocation before activation. Any future IAP support requires genuine application-side identity validation, not trusting caller headers or changing settings in this repair.

Root owns current-MAIN reconciliation, regenerated inventory/source proof, final ready metadata, remaining CODE2/security/CI and the sole publication. This author commit does not refresh SITE/sidecar or claim those final gates already qualify the new source.
