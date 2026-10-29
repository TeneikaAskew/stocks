---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-UX-001, REQ-DATA-001, REQ-REL-001, REQ-VALID-001, REQ-CAP-001, REQ-CAP-002]
issues: [928, 1206, 1335]
site_source_notes: [CHARTS-06, DASHBOARD-05, SIGNALS-04]
canvases: []
done_when:
  - "Producer-derived zero-external-I/O tests exercise the actual momentum and mean-reversion producers, preserve their numerical decisions, and explain native momentum six-of-seven and seven-of-seven plus mean-reversion base and bonus outputs without a universal five-point ceiling"
  - "The existing historical-signals mapping and bulk-insert boundary preserve all prior extra JSONB content and persist a bounded versioned score explanation for new rows without new tables, columns, additional SQL, backdating or rewriting legacy records"
  - "The real signals API and typed response expose strategy, analytical-corpus provenance and validated nullable score explanations on SQL and legacy-parquet branches, preserving raw legacy scores while refusing guessed components or maxima"
  - "Actual router tests admit native strength six to the existing similar-signals endpoint without changing its numeric matching predicate, RSI window, query count or result limits, and retain typed rejection of invalid parameters"
  - "Current-head focused tests, producer-to-API fixtures, maximum-limit capacity evidence, FEAT-SIGNAL-001 delivery records, actual branch-versus-main documentation audit and spec gate pass with no new findings and only the declared source-note rows changed"
status: approved
supersedes: null
---

# Historical signal score semantics without changing financial decisions

## Approval and ownership

The owner approved the October 27 functional root-cause repair, a separate normal
FEAT-SIGNAL-001 specification route, existing-field reuse and explicit unknown legacy
semantics. No new financial choice is made here. This specification records that
approved scope; it does not claim implementation, testing, merge or deployment.
Normal specification review and merge to MAIN still precede the matching ready
implementation plan and CODE branch. The existing STRAT owner is the sole backend
score-contract coordinator. Root separately owns the Solyra consumer. Earnings,
options/news, governance and calendar authors remain separate.

No #1573 security-wait decision or other PR exception applies to this change.
Do not retry a denied Ready operation or substitute credentials. The separate
STRAT foundation #1575 is not changed, completed or bypassed by this specification.

## Problem and actual producers

Inspected source at MAIN `d78201b0846c1fa1cc2f80b0fe1d106661a2eb2b` establishes:

* `scripts/run_historical_signals.py` defaults to `momentum`. Its dispatcher calls
  `MarketAnalyzer.generate_technical_signals`, or the distinct mean-reversion helper
  when explicitly selected. The mapper writes both to `historical_signals` with the
  existing `strategy` tag.
* `lib/trading_analysis.py` counts seven possible conditions on each side: four core
  conditions and three confirming conditions. Five is the admission floor, with a
  separate two-core minimum; it is not the maximum. The emitted numeric strength is
  that count, but `conditions_met` is incorrectly formatted as `strength/5`.
* Mean reversion calls `lib.signals.generate_signals` and maps its `total_score` to
  `signal_strength`, with a JSON-serialized condition-name list. The current historical
  call supplies no Strat bonus, so the native bonus is zero and its unrestricted
  current base has five conditions. Generic `evaluate_signal` can receive a bonus;
  its annotation/docstring is not enforcement of a universal zero-to-three range.
* `/api/signals/{ticker}` aliases stored strength as `score` but omits the existing
  strategy column. It returns an analytical/backfill corpus, not the published-alert
  ledger. The schema accepts any `conditions_met`, while `/similar` incorrectly
  restricts its integer score argument to at most five.

A stored six is not repaired by clamping it to five, blindly changing every `/5`
to `/7`, assuming every row is mean reversion, or inferring a producer version from
today's code. Agreement/proximity scoring and the live indicator/monitor pathways
are different contracts and are not modified.

## Non-goals

No trading-condition, threshold, weighting, bonus, admission, exit, return, ranking,
model or probability change. No original-publication/PIT claim. No provider request,
SQL execution, historical replay, destructive backfill, schema migration, new table,
new column, job/schedule/resource change, IAM or credential change. In particular,
none of the seven future options-journal tables is involved. No frontend source or
shared OpenAPI regeneration occurs without its existing owner's serialized handoff.

## Approaches considered

1. Clamp the display or replace a global denominator. Rejected: changes or mislabels
   legitimate values and leaves producer/provenance loss in place.
2. Recompute old scores under current rules. Rejected: original inputs/configuration
   and producer versions are not retained sufficiently; this would fabricate history.
3. Record native components prospectively in existing JSONB, and serve a versioned,
   nullable explanation alongside unchanged legacy values. Selected.

## Design

### 1. Preserve numerical behavior; describe the actual native result

Keep the existing counter increments, thresholds, direction selection, bonus inputs
and stored numeric strength unchanged. Capture condition IDs as metadata in the same
native branches that increment the counters; do not create a second scoring engine.

For new momentum rows, record the observed count, the seven-condition definition,
the matched native condition IDs and no applied bonuses. Correct the new row's stale
fraction text using its verified native condition maximum. A native six remains six
and its new descriptive fraction is `6/7`; existing stored text is untouched.

For the current historical mean-reversion path, preserve native `base_score`,
`strat_bonus`, `total_score` and the existing JSON condition-name list. Its currently
selected call has a known zero bonus and five enabled conditions. If another caller
or profile has a different enabled set, disabled factors or bonus policy, record its
actual definition and evidence or return unavailable; never borrow this maximum.
A supplied bonus value is not evidence of a maximum bonus policy. No universal
five-, seven- or eight-point maximum is introduced.

Use a pure description/validation helper in existing `lib/signals.py`. It consumes
native results plus a declared producer definition and known execution context;
it does not query data, rerun indicators, alter scores, fetch configuration remotely
or import a database writer for source identity. Finite integer counts, unique known
matched IDs, declared maxima, named bonus contributions and total consistency are
validated. New-producer inconsistency fails before that row is persisted, rather
than silently becoming a qualified explanation.

### 2. Versioned additive response

Retain the existing row's `score` and `conditions_met` without numeric normalization.
Expose the existing nullable `strategy` and an additive typed `score_explanation`:

| Field | Meaning |
|---|---|
| `version` | `historical-score-v1`, the explanation format |
| `status` | `recorded`, `legacy_unavailable`, or `invalid_record` |
| `kind` | `condition_count`, `base_plus_bonus`, or `unknown` |
| `base_count`, `base_max` | Native count and definition maximum, only when supported |
| `matched_conditions` | Native matched IDs for that recorded definition, otherwise null |
| `bonuses`, `bonus_total` | Named numeric contributions; null means unknown, not zero |
| `composite_strength`, `composite_max` | Native total and a supported ceiling; null where not established |
| `unavailable_reasons` | Stable reason codes rather than neutral financial conclusions |
| `provenance` | Corpus, strategy, run kind, storage source, recorded producer/profile/version and available source/config/input identities and clocks |

The `historical_signals` corpus is analytical. `run_kind=live` is the existing
operational taxonomy, not proof that an alert was published. Cloud SQL versus GCS
is a storage source, not a vendor identity. Missing price-provider/receipt evidence
stays unknown. Never infer original availability from `entry_time`, `inserted_at`,
a new API read, today's deployment or the value of `run_kind`.

New producer metadata records actual current generation time, producer definition,
code identity and the known configuration/input identity. Absent source details
remain null with reasons. It does not backdate receipts to the historical bar.
Record an explicitly versioned producer definition; a new format label alone is
not evidence that an old row used that definition.

For a legacy row with score six and no supported explanation, preserve `score=6`;
base count/max, bonuses and composite reconstruction remain null with
`legacy_score_contract_missing`. A string `6/5`, a JSON list of five or six names,
current strategy defaults or current code cannot independently recover the old
configuration or original producer version. Raw condition text remains available
as legacy evidence, not an authoritative normalized denominator.

Malformed new metadata is `invalid_record` with explicit reasons; preserve its raw
legacy score while refusing the unsupported explanation. Do not silently drop an
entire row, coerce nonfinite values into zero, expose arbitrary JSONB keys, or invent
probabilities. The helper's allowlisted explanation is at most 2 KiB UTF-8 per row;
oversize/unknown-field input is refused as explanation, not truncated into validity.

### 3. Existing storage only

Source DDL already declares `historical_signals.extra JSONB`, `inserted_at`, and the
later `strategy` and `run_kind` fields. Existing insertion serializes `extra` in the
same bounded batch and uses `ON CONFLICT ... DO NOTHING`. No new table or column is
needed for the explanation: store it under the reserved `extra.score_explanation`.

The current mapper includes only `EXTRA_PREFIXES`, so merely attaching a new key to
the native signal would be lost. Explicitly merge the explanation into the mapped
extra dictionary without discarding any prior key or value. Conflicting reserved
metadata fails clearly; no silent overwrite. Preserve existing field serialization,
primary-key/idempotency behavior and run-kind handling. Do not touch old records or
stamp them with current versions. Schema declarations are source evidence, not a
new live introspection receipt.

The original source DDL still spells `conditions_met VARCHAR(8)` while the historical
MR producer emits longer JSON text. This specification does not assume a live type,
truncate names, widen the column or authorize DDL. New score metadata uses existing
JSONB and does not depend on rewriting that field. Any actual deployment-time type
conflict must be reported with exact evidence and handled through a separately
necessary approved action; it cannot be hidden by this explanation contract.

### 4. Real read paths and compatibility

In `_query_signals_sql`, project the existing `strategy`, `inserted_at`, `run_kind`
and only `extra -> 'score_explanation'`; do not return the whole extras object.
Keep ordering, count/window/score filters and SQL-call count unchanged. Apply the
pure descriptor to real SQL and parquet branches. A legacy parquet without strategy
or metadata remains explicitly unavailable; do not infer momentum from its filename.

Add typed nullable models and `SignalRow` fields in `platform/api/schemas.py` under
serialized ownership with the earnings/backend owners. Existing `score` and raw
condition fields stay compatible. `/similar` accepts a legitimate native strength
of six by removing only the guessed five-point upper transport bound. Keep its
existing integer/minimum validation, numeric SQL predicate, RSI tolerance, limits,
query count and analytical-corpus semantics. This is not a new similarity model or
cross-strategy calibration claim.

The source-note declaration covers the actual similar-card and historical-signal
read components only. It does not authorize changes to live indicator mathematics,
monitor agreement/proximity, existing SITE tables, frontend checkboxes or deployment
claims. Any permitted implementation-source note is truthful backend-only provenance.

### 5. Producer-derived acceptance and purity

`tests/lib/test_signal_score_contract.py` and
`tests/scripts/test_run_historical_signals_strategy.py` exercise actual production
methods, not handwritten four-of-five response mockups:

* Actual `MarketAnalyzer.generate_technical_signals` on finite synthetic enriched
  frames produces a native momentum six and seven, plus a below-floor/no-signal
  control. Assert unchanged numeric outputs and admission while the new descriptions
  reflect six/seven with the verified seven-condition definition.
* Actual `_generate_mean_reversion_signals` and `lib.signals` produce a known base
  count with the current zero bonus and unchanged JSON-name serialization. Exercise
  a native explicit-bonus `evaluate_signal` control to prove that total and base
  are different; do not claim that generic bonus control is this historical caller.
* A no-signal result remains no signal, not a synthetic zero-strength alert.
* New metadata with a supported profile preserves native components. Legacy six,
  legacy fractional strings, old name lists, missing version/configuration, malformed
  metadata and nonfinite values preserve raw evidence and refuse invented maxima.
* Existing extras, nested values and reserved-key collision controls prove the mapper
  and existing bulk-insert serializer preserve content and idempotency. No schema
  change or real SQL is performed in these acceptance tests.

`tests/api/test_signal_score_contract.py` invokes the actual router and response
serialization using outputs from those producer fixtures. Inject only persistence
and GCS reads at the real I/O seams; do not replace the scorer with canonical display
constants. Cover SQL/parquet known and unknown cases, six admitted by `/similar`,
invalid inputs, existing sort/window/count behavior, and no extra queries.

Install external-I/O guards during producer/helper execution. Never invoke the full
historical CLI as a supposedly pure test: even `--dry-run` reaches
`map_signals_to_table`, whose catalyst-context lookup can query the database before
it skips the final write. Isolate that existing boundary explicitly in integration
tests. No provider, calendar fetch, secret read, SQL execution, notifications or
production replay is needed to establish this semantic contract.

Each behavioral test must fail sensitively on the prior source: native six currently
formats `/5`; explanation metadata is dropped by the mapper and absent in the API;
strategy is omitted; `/similar?score=6` currently rejects it. A green display-only
fallback test is insufficient. Preserve exact source/config/input hashes and both
successes and refusal cases.

### 6. Files and serialized delivery

Expected CODE paths:

* `lib/trading_analysis.py`, `lib/signals.py`, `scripts/run_historical_signals.py`;
* `platform/api/routers/signals.py`, the owned signal models in `platform/api/schemas.py`;
* focused tests named above and existing `tests/gcp/test_historical_signals.py`;
* `gcp/historical_signals.py` only if a necessary serializer compatibility change is
  demonstrated, never to add a query, schema action, retry or database route;
* own capability/traceability records and declared implementation-source note/proof.

`platform/api/openapi.json` is shared. Its actual regeneration and frontend contract
sync require the serialized handoff; do not overwrite another owner's artifact.
Normal spec/plan/gate, authenticated current-head review, resolved threads and green
required checks remain mandatory. This is a new non-superseding SIGNAL spec: no
unmerged governance producer/test change is automatically a prerequisite. A real
current gate failure is reported precisely instead of waived or inferred from a
stale branch. No CODE is stacked onto the unmerged spec branch.

## Capacity and risks

Volume: at most the existing 50,000 rows per signals request (default 5,000), with
at most 2 KiB explanation per row: up to about 100 MiB additional serialized data
at the hard row limit, usually less; unknown legacy descriptors are smaller. The
actual maximum-limit test measures serialized bytes, wall time and peak memory.
Stay within the existing API configuration (2 GiB, 300 seconds in `platform/deploy.sh`)
and existing query/row limits; no resource increase is authorized by this spec.
Velocity: zero extra database/provider requests; metadata is included in existing
insert batches and the existing two-query list read. No job/schedule/concurrency or
account-throttle change. Work is linear in returned rows and recorded factor count.
Wall-clock: record the actual fixture/API and hard-limit results before merge, below
the existing service timeout and memory envelope; do not substitute a theoretical
bound for the measured result. A failed capacity check blocks that implementation.
Cost: no additional vendor calls or scheduled executions; marginal existing SQL
storage/CPU and response bytes are not asserted to be free. No new billable service,
purchase, quota or deployment configuration is authorized.

Key risks are silently reinterpreting legacy rows, mixing score definitions, losing
JSONB extras, leaking unrelated extras, claiming an unvalidated maximum, changing
numeric policy while improving labels, and calling a write-capable CLI during a
pure test. The named acceptance controls directly cover these defects.

## Close-out, outside pre-merge checkboxes

After the approved CODE merge, independently verify actual MAIN identity and normal
staging deployment. Root coordinates the real frontend consumer, shared OpenAPI
handoff and screenshots showing a producer-derived native six with the correct
known definition and a legacy six with unavailable definition. Do not call a local
API fixture a deployed screen. Preserve before/after image/config identity and the
normal rollback path; no migration/backfill rollback is needed because none is
performed. Retire source-proof sidecars only through existing legitimate main/staging
close-out. Full completion requires these real receipts; source identity alone does
not prove deployment, provenance vintage, confidence or financial performance.
