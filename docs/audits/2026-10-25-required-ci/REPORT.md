# Required CI validity audit — 2026-10-25

**Retain all six required checks pending scoped follow-up.** This audit found
coverage-selection defects and four small, concretely equivalent test pairs,
not evidence that an entire required check is obsolete. No workflow, test,
requirement, protection, secret or runtime file changes in this PR.

Audit base: [main `911d30a7427a8d3249ecd82a828952a3e4b639a0`](https://github.com/TeneikaAskew/stocks/tree/911d30a7427a8d3249ecd82a828952a3e4b639a0).
The six names come from the user screenshot inspected by the parent. That
screenshot establishes neither test validity nor obsolescence; protection
settings were not independently queried. This is an independent draft audit,
not a release prerequisite for #1594, #1597 or #1583. No merge is requested.

Evidence: [inventory.json](inventory.json) holds exact workflow steps, trigger
filters, dependencies, collected node IDs per path, fixture closures, skip
markers, source hashes and source links; [validation.json](validation.json)
holds actual run outcomes, timings and failures; [hosted-sample.json](hosted-sample.json)
holds selected timestamped hosted log evidence. [REPRODUCE.md](REPRODUCE.md)
contains commands and the observation/generation scripts as documentation.
Counts describe collection, not assertion quality or a coverage percentage.

## Six-check map

| Required check | Workflow / actual execution | Local collection at audit base | Contract and dependency distinction |
|---|---|---|---|
| Backtest Pipeline / Run Tests | [backtest-pipeline.yml](../../../.github/workflows/backtest-pipeline.yml), `test`: `python -m pytest tests/ -x -q --ignore=tests/integration` | 7,662 IDs, 287 files; 3 modules skipped at collection | Unit/API/agents, library/research helpers, scripts, docs and repository invariants. Python 3.12, `requirements.txt`; first failure stops execution, not collection. No backtest pipeline is actually launched. |
| Backtest Pipeline / Research Tests (heavy ML stack) | Same workflow, `research-test`: `python -m pytest -q tests/*/test_strat*.py tests/*/test_mag*.py tests/gcp/test_featurize_all_nan_robust.py tests/gcp/test_feature_importance.py tests/meta/test_import_coverage.py` | 786 IDs, 37 files; 1 module skipped at collection | Same base plus `requirements-research.txt`: LightGBM, XGBoost, sklearn, scipy, SHAP. Real fitting/calibration/leakage plus many non-ML helpers. Local overlay installed LightGBM 4.7.0 only; XGBoost/SHAP absent locally, so not full CI dependency parity. |
| Backtest Pipeline / Integration Tests (ephemeral Postgres) | Same workflow, `integration-tests`: apply `gcp/schema.sql` with `psql -v ON_ERROR_STOP=1`; `python -m pytest tests/integration/ -q` | 83 IDs, 7 files | Python 3.12/base requirements; `pgvector/pgvector:pg15`, five-attempt Docker pull, local test DB variables. Real SQL, schema compatibility, persistence, constraints, timestamps and options/watchlist behavior. |
| registry-check / registry | [registry-check.yml](../../../.github/workflows/registry-check.yml): required-file/hook checks; compile proposed gate; run gate and require a verdict; `pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest`; exporter `--check --rev HEAD_SHA --base BASE_SHA` | 144 gate IDs | Pytest/PyYAML on runner Python. Mix of policy smoke checks, tests and generated-data validation, not merely a linter. A gate verdict of refusal can satisfy the smoke step; authoritative admission belongs to the base gate. |
| spec-gate / base-suite | [spec-gate.yml](../../../.github/workflows/spec-gate.yml): base checkout plus artifact containing proposed gate/exporter; two separate `pytest` commands for `test_spec_gate.py` and `test_export_model_registry.py`, each `-q -p no:cacheprovider --noconftest` | 144 + 41 = 185 IDs at current base | Pytest/PyYAML, runner Python, 10-minute job. Base-owned tests against PR-controlled implementation. Depends on `gate`. Credential-free checkout; distinct authority from PR-owned tests. |
| spec-gate / gate | Same workflow: base checkout, fetch head as data; `python3 scripts/gate/spec_gate.py --pr BASE_SHA HEAD_SHA`; export proposed files only after verdict | 0 pytest IDs; a policy validator | PyYAML, runner Python, 5-minute job. Approved spec/plan, branch/path ownership, immutable policy, title/body/close-out checks. PR contents are read as git objects. Does not itself certify reviewer identity, resolve review threads or prove deployment. |

The first workflow runs **every PR to main**, without a PR path filter; also
nightly `17 8 * * *`, manual dispatch and pushes to main/`claude/**` restricted
to `lib/**`, `scripts/**`, `tests/**`, `alert_config.json`, `requirements.txt`,
`requirements-research.txt`. Push-only coverage therefore excludes standalone
`gcp/`, `platform/` and workflow edits; PR and nightly coverage remain. This
asymmetry is a decision to review, not evidence of dead tests.

Registry runs on PR opened/synchronize/reopened without a path filter. Spec
gate runs on **pull_request_target** opened/synchronize/reopened/edited/ready
for review, without path selection. Its trusted base is intentional. Plain
`pull_request` checkout defaults to GitHub's merge ref, despite registry
comments calling it HEAD; explicit exporter/head-object checks still use
`HEAD_SHA`. Treat execution revision versus inspected revision separately.

Requirement mapping is behavioral, not invented per-test traceability:
[REQ-DATA-001/002](../../../docs/product/01-PRODUCT-REQUIREMENTS.md) support
missing-data and as-of contracts; REQ-GOV-004 supports generated-doc integrity;
[product-delivery](../../../.claude/skills/product-delivery/SKILL.md) and
[AGENTS.md](../../../AGENTS.md) define spec/governance obligations. FEAT-MODEL-001,
FEAT-STRAT-001, FEAT-DATA-001 and FEAT-CICD-001 in the
[catalog](../../../docs/product/02-FEATURE-CATALOG.md) still have implementation
and contracts. A model's failed trading-edge evaluation does not retire its
calibration, leakage, unavailable-state or provenance contracts.

## Prioritized findings and disposition

### A1 — Valid but misconfigured: 28 API cases fall through job selection

**High priority coverage repair.** `tests/api/test_structure_continuation.py`
(17 cases) and `tests/api/test_strat_engine_predict.py` (11 cases) catch
`ModuleNotFoundError` at module scope and skip. In complete lean collection both
skip because forced import of `strat_pred_serve` needs LightGBM. The research
globs omit `test_structure_continuation.py` entirely. The matching predict file
still skips in research collection because it adds `platform/api` but not
`platform` before importing `routers.admin`, whose imports require `api`.
Later imports in the larger suite can hide this path dependency.

Actual runs: direct files with the ML overlay still yielded **2 collection
skips**, `No module named 'api'`; adding `platform` to the local process's
`PYTHONPATH` yielded **28 passed**. This proves runnable assertions currently
missed by these selectors/environment combinations, not that all related API
behavior lacks other tests. These source-level conditions also explain the
hosted research total of 767 passed/20 skipped, but hosted `-q` did not expose
individual skip reasons, so exact hosted skip attribution remains unverified.

Current contract: [admin.py](../../../platform/api/routers/admin.py),
`admin_structure_continuation`, flag-off 404, 5m/15m-only exposure, admin identity,
and explicit null/unavailable values; REQ-DATA-001. Tests were last moved in
`259c223b` (#1001); that move alone does not establish when the defect began.
**Propose:** self-contained imports, explicit coverage selection for both files,
and CI assertions that expected API/real-ML tests actually run. Keep tests.
Risk: dropping them would remove feature-flag and unavailable-state checks;
blindly widening globs can reintroduce shared-module mock pollution.

### A2 — Valid but misconfigured: 19 playbook cases skip in both relevant jobs

`tests/lib/test_strat_levels_playbook.py` collects 25 cases. Nineteen request
`market_data`; [tests/conftest.py](../../../tests/conftest.py) defaults to
`--mode=live`, falls back to a Windows-specific gcloud path, then converts
connection errors to skips. Neither lean nor research command chooses mock
mode or provides a live-data backend. The integration job selects a different
directory. Actual default run: **6 passed, 19 skipped** (missing Windows CLI).
Actual `--mode=mock` run: **25 passed** using the committed IWM fixture.

These assert current `build_level_map` / `format_levels_for_brief` behavior in
[lib/strat_levels.py](../../../lib/strat_levels.py), including trigger labels,
price-distance guards and unavailable output. **Propose:** explicitly exercise
the committed deterministic fixture in CI; keep live diagnostics separate.
Do not add production credentials. Conditional assertions such as
`test_room_label_present_when_targets_exist` can still be vacuous for another
fixture, and `test_room_value_matches_trigger_distance` can skip without a
room line. Add purpose-built trigger/no-trigger fixtures in a later scoped
change. The passing sample does not establish mutation strength for all 25.

### A3 — Valid/retain: real ML catches a relevant regression

`tests/gcp/test_magnitude_class_weight.py` uses real LightGBM and guards
`gcp/research/magnitude_engine/mag_pred_train.py::make_lgbm`. Baseline **2 passed**;
in-memory default mutation `class_weight='balanced'` to `None`: **2 failed**.
The behavioral assertion failed with majority share **0.782**, exceeding 0.65,
not merely because a mock reported a different parameter. Restore happens by
process exit; no source bytes changed.

Retain the heavy environment and real-fit controls. They demonstrate fitting
behavior on synthetic data, not profitable live trading. The registry records
failed execution/edge assessments alongside still-current model contracts;
[07-MODEL-REGISTRY.md](../../../docs/product/07-MODEL-REGISTRY.md) explicitly
separates MODEL-TYPE-001 prediction and execution verdicts. A broad removal
based on “invalidated model” would erase useful negative/leakage coverage.

### A4 — Valid/retain: PostgreSQL is not equivalent to mocked DB coverage

All **83 integration tests passed** on a freshly applied schema in a dedicated
local pgvector PostgreSQL 15 container. In particular,
`tests/integration/test_run_kind_constraints.py::test_drift_is_raised_rather_than_silently_accepted`
replaces a real constraint with a different value set, executes the actual
schema block, expects `has drifted`, and rolls back. The same suite verifies
accepted values and database-enforced rejection. This is an executed bounded
negative control; it is not a production query.

`tests/integration/test_schema_query_contract.py` drives production summarizer
and persistence paths using actual tables. API tests returning canned rows
cannot prove column names, SQL joins or normalized PostgreSQL constraint
rendering. Last constraint-file change `711d91f8` (#1098) documents that
contract. Retain. PostgreSQL 15 is version-specific evidence; compatibility
with other major versions or production scale remains unproven here.

### A5 — Redundant with verified equivalence: four small test pairs

The AST screen removed function docstrings, compared executable bodies, then
inspection checked identical same-module/class helpers and fixture context.
All eight tests passed. These are **four pairs**, not four redundant jobs:

| File | Equivalent functions | Proposed disposition |
|---|---|---|
| `tests/lib/test_strat.py`, lines 701/745 | `TestComputeStratStatusAsOf.test_naive_date_as_of_filters` / `test_inclusive_today_default_true_legacy_contract` | Keep one explicit inclusive legacy-contract test. |
| `tests/scripts/test_docs_audit.py`, lines 2679/5668 | `test_the_pr_lookup_stops_once_every_pending_refresh_is_superseded` / `test_the_pr_walk_still_stops_once_the_current_generation_delivered` | Consolidate while preserving pagination-cost and generation explanation. |
| `tests/scripts/test_verify_docs_against_live.py`, lines 144/677 | `test_retired_service_is_caught` / `test_a_retired_service_is_reported_once_not_twice` | Keep explicit exactly-once assertion. |
| Same file, lines 468/592 | `test_the_free_tier_quota_is_not_read_as_a_fleet_count` / `test_the_free_tier_quota_is_still_not_a_fleet_count` | Keep one quota-versus-count regression. |

The first pair also fails identically when the production function's default
`inclusive_today` changes from True to False: both expect April 20 but get
April 17. Its old/legacy behavior remains an explicit current contract in
[lib/strat.py](../../../lib/strat.py), not obsolete behavior. The other pairs
have equivalent bodies and successful focused runs, not independent mutation
proof. The eight-test run took 14.75 seconds in pytest; do not interpret this
as measured savings from deleting four, or as a CI bottleneck solution.

### A6 — Valid/retain: overlap across gate jobs has distinct trust semantics

The 144 gate IDs occur in lean, registry and base-suite; 41 exporter IDs occur
in lean and base-suite. Research overlaps lean by **774 node IDs**; its 12
additional IDs are `test_feature_importance.py`. Shared IDs do **not** establish
execution equivalence: lean lacks ML dependencies, `--noconftest` changes fixture
context, and the base suite owns tests outside PR control. Proposed gate changes
cannot be certified solely by tests changed in the same PR.

Executed controls: **3 gate tests passed**, covering unapproved code on exempt
branch names, superseded specifications and base-copy enforcement; **3 exporter
tests passed**, covering missing model rows, exact PR-head checking and stale-base
attribution. These exercise concrete rejection/acceptance snippets in temporary
repositories. Keep all three governance checks. The `registry` name understates
its gate-regression work; a clearer label is a later change needing careful
required-check migration, not a change made by this audit.

### A7 — Obsolete with evidence, already excluded; unused fixtures are narrower

`archive/tests/test_e2e.py` explicitly targets retired static applications, and
`Makefile::test-e2e` labels them archived. None of the six commands collects
that path. Its retirement already happened; removing it cannot speed these
required checks. **No currently selected test is proven obsolete by removed
implementation or superseded requirements in this bounded review.**

Five fixture definitions have no matching current Python reference outside
their declaration and no use in any collected fixture closure: `sample_daily`
in `tests/conftest.py`; `trending_down_data`, `default_app_config`,
`permissive_signal_config`, `default_engine` in `tests/lib/test_integration.py`.
These are unused-fixture cleanup candidates, not expensive executed tests.
Classify their intended future/external use as **uncertain/needs decision**;
confirm external plugin/dynamic consumers before deletion. In particular,
`db_conn` is NOT unused: `request.getfixturevalue` reaches it dynamically.
`risk_config`/`exit_config` have same-name non-fixture references and are kept
unresolved. Lexical fixture scans alone are insufficient retirement evidence.

### A8 — Uncertain/needs decision: skips, versions, mocking and label fidelity

The screen found **no xfail call/marker in current test source**, and collected
markers contain no xfail. It found no literal-True assertion. Four self-comparison
assertions are deliberate NaN presence/absence checks, not tautologies:
`test_signal_monitor_level_refresh.py:302` and
`test_calibrate_earnings.py:147,224,468`. They must not be deleted by a text rule.

`test_feature_importance.py` names “real SHAP” shapes but constructs arrays;
it exercises the reducer's compatibility logic, not the installed SHAP API.
Older list-shaped and newer ndarray-shaped inputs remain supported by
`_reduce_shap_to_features`; `shap>=0.43.0` has no upper bound. Retain both until
the supported contract changes; add an actual supported-version producer/
consumer test before claiming SHAP compatibility from these names.

`tests/meta/test_import_coverage.py` intentionally imports in a clean subprocess,
avoiding sibling `sys.modules` stubs, and skips research prefixes when LightGBM
is absent. It is an import test, not runtime behavior proof. Module-level
`except ModuleNotFoundError: skip` can also hide our own broken imports, as A1
reproduces. The playbook and API holes show why a green aggregate is not proof
that all intended checks ran. Full lean hosted output reports skips without
reasons; enumerate them in a later scoped CI evidence change before retiring any.

`tests/scripts/test_docs_audit.py::test_the_real_traceability_line_reports_nothing`
uses positional line 48 with a skip fallback if wording moves. It **passed in
this audit**, so it is not currently demonstrated stale. Its neighboring
synthetic clause tests remain relevant. Prefer locating the intended content
explicitly if that real-document guard is maintained.

The global watchlist stub is a conscious hermetic boundary, not proof of live
watchlist integration. The prior [September audit](../../../docs/TEST_SUITE_AUDIT_2026-09-06.md)
is historical: its counts and route-name proxy must not be reused as current
coverage. This audit does not re-certify all 6,751 AST test-function definitions.

## Runtime and documentation-only relevance

One measured hosted sample is [documentation-only PR #1596](https://github.com/TeneikaAskew/stocks/pull/1596),
head `4a4cfe5460d80c5efed299c5171383a4aa697150`. Its workflows, test tree,
gate sources and two dependency manifests are byte-identical to the audit base
(`git diff` over those paths is empty). These are historical completed results,
not this draft's CI. `hosted-sample.json` provides job links and log timestamps.

| Check | Hosted pytest result / measured pytest time | Observed job log span |
|---|---|---|
| Run Tests | 7,594 passed, 71 skipped; 1,288.94 s | 1,368.0 s |
| Research | 767 passed, 20 skipped; 17.13 s | 79.8 s |
| Integration | 83 passed; 6.05 s | 97.7 s |
| Registry gate suite | 144 passed; 278.13 s | 294.6 s |
| Base suite | 144 passed in 277.60 s + 41 passed in 14.44 s | 302.7 s |
| Gate | Policy verdict success; no pytest workload | 14.4 s |

The lean total reconciles with local collection: 7,594 + 71 = 7,665 report
outcomes; 7,662 collected cases plus 3 module collection skips. Research:
767 + 20 = 787 outcomes; 786 collected cases plus 1 collection skip. Local
package versions differ, so this arithmetic is consistency evidence, not a
claim of identical individual outcomes. Whole-job logs include installation,
checkout and cleanup; pytest times omit that overhead. One warm-cache sample
cannot establish median, cold-cache cost or a safe timeout. Registry's suite
alone consumed 278.13 s of its current 300 s job cap; #1594 already owns live
CI recovery. This audit adds no dependency to that work.

For ordinary prose-only changes, classifier fitting and SQL execution have low
direct relevance. However, `docs/**` includes model registries, specifications,
requirements and generated inventories; the main suite contains tests that
inspect those files. `*.md` also includes executable agent policy. A blanket
“docs change => no tests” rule would discard legitimate cross-cutting coverage.

**Follow-up order, separate from this draft:**

1. Repair A1/A2 selection and self-contained fixtures under the appropriate
   approved FEAT-CICD/owning-capability spec. Acceptance: all expected 28 API
   and 19 fixture-backed playbook cases execute without production credentials.
2. Add per-job collected/executed/skipped node-ID and reason evidence, with
   expected real-ML/API cases required to execute; retain failures as failures.
3. Profile multiple current runs (cold/warm installs and `--durations`) before
   selecting partitions. Investigate long lean tests and registry headroom;
   do not assume LightGBM dominates because of its label.
4. If a docs-only optimization is approved, use exact changed-file classes,
   preserve base-policy, registry/exporter and relevant docs invariants, test
   adversarial policy/workflow/source changes against the selector, and keep
   full runtime coverage on runtime/dependency changes plus nightly canary.
   Required statuses must still reflect real validated coverage. No filter is
   proposed as ready to implement by this single sample.
5. Consolidate A5's four pairs with retained negative controls; decide A7 fixture
   ownership. No broad deletion, no skipped failure, no requirement supersession.
6. Add supported-version SHAP integration evidence and review conditional/vacuous
   assertion candidates. Model retirement requires an explicit contract decision.

## Validation limits and environment outcomes

Local Python 3.12.14/pytest 9.0.2, package versions in inventory; no full lean
execution was performed. Research with the isolated LightGBM overlay and
sanitized shell environment: **767 passed, 20 skipped**, including one collection
skip and 19 playbook runtime skips. Integration: **83 passed**. API import
repair control: **28 passed**. Playbook/mock + positional docs + HTTP-status
sample: **28 passed**. Gate/exporter controls: **3 + 3 passed**. Duplicate pairs:
**8 passed**. Expected mutation results: **2 ML failures + 2 inclusive-default
failures**, each at the intended assertion. These are samples, not exhaustive
proof of validity or deployment suitability.

The first research run had **4 failed, 763 passed, 20 skipped**. An inherited
`BASH_ENV` prepended the installed SDK ahead of fake CLI stubs. Four dispatcher
tests reached a real CLI and reported **UNAUTHENTICATED / CREDENTIALS_MISSING**;
no successful production execution or provider-data access was observed. The
runner had removed credential/DB environment variables, and the suite disables
CLI credentials. Unsetting `BASH_ENV` restored fake-command isolation; the
corrected run passes without source changes. Preserve this as a local harness
failure, not a CI defect or fabricated success. A nonexistent test selector
also returned exit 4, and an initial mutation used the wrong Python defaults
attribute; their corrected runs are separately recorded.

Publication gate/docs-audit results are recorded in [PUBLICATION.md](PUBLICATION.md).
No budget meter is exposed; no remaining percentage is claimed. The existing
1% usage floor remains in force if it becomes observable.
