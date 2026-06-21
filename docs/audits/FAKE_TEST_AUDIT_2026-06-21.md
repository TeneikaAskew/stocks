# Fake / Cheating Test Audit — 2026-06-21

Goal: find tests that report **PASS** without genuinely verifying behavior —
tests that fake their way past a failure to clear a blocker. Top-priority
categories: missing data, data gaps, mock/fake data.

The audit was run as four parallel investigations (library-stub leakage,
failure-swallowing tests, fake/missing-data tests, CI/e2e config) plus a
plain-English walkthrough of the test setup.

---

## ✅ Fixed in this branch (`claude/detect-fake-test-data-5dvxbq`)

### 1. CRITICAL — `sys.modules` MagicMock leak across 6 magnitude tests
Commit: `test: stop magnitude tests leaking MagicMock stubs into sys.modules`

Files: `tests/test_featurize_all_nan_robust.py`,
`test_mag_persist_production_model.py`, `test_magnitude_inference.py`,
`test_magnitude_predictions_persistence.py`,
`test_mag_inference_lag_recreation.py`, `test_magnitude_router.py`.

These injected `MagicMock()` stand-ins into the **global** `sys.modules`
cache at collection time when `sklearn` / `lightgbm` / `google-cloud-*` /
`pg8000` were absent, and never tore them down. A later sibling test that
imported the real library received the fake instead → order-dependent
false passes (one stub hardcoded `log_loss` to `0.5`) and random crashes.
Same leak the files' own comments reference from PR #597; the
conditional-stub mitigation did not remove it.

Fix: replaced `_stub_missing_modules()` with module-level
`pytest.importorskip(...)` (the pattern already used by
`test_regime_combo_job.py`). **Verified**: after collecting all six files,
zero `MagicMock` entries remain in `sys.modules`; a later `sklearn` import
skips cleanly instead of receiving a fake.

### 2. HIGH/LOW — failure-swallowing tests made to fail for real
Commit: `test: make failure-swallowing tests fail for real`

- `earnings_options_analytics/test_system.py` — `test_*` functions used
  `print('FAIL'); return False`; under pytest (return values ignored) they
  passed unconditionally. Converted failure conditions to `assert` and
  re-raise on analysis errors. (Not in CI's path — `make test` is scoped to
  `tests/` — but a `pytest .` from repo root would have false-greened.)
- `tests/test_intraday_bulk_failure_classification.py` — HTTP-500 test used
  `pytest.raises(Exception)` (passes on ANY exception). Mock now raises the
  real `requests.exceptions.HTTPError` and the test asserts that type.
  **Verified**: 17 passed.

### 3. CRITICAL — e2e gamma tests passing on empty data
Commit: `test(e2e): skip gamma chip tests on empty data instead of silent pass`

- `platform/tests/gamma-levels.spec.ts` — two tests used
  `if (count > 0) { expect(...) }`, running zero assertions (and passing)
  when the backend returned no data. Converted to the file's existing
  `test.skip(count === 0, reason)` pattern: empty backend → visible SKIP;
  present-but-broken chip → still fails.

---

### 4. CRITICAL — `featurize()` no longer blesses missing data as `0`
Commit: `feat(magnitude): emit missing-data indicators in featurize()`

Per operator decision (add a missing flag). `featurize()` now emits a
`<col>__isna` indicator (1.0 where the source was NaN/inf) for every
feature column with missing data, appended to feature_cols. The imputed-0
value stays for the model's numeric contract but is no longer
indistinguishable from a real 0. Backward-compatible (inference selects
`enc[feature_cols]`, so existing models ignore the new columns); the model
benefits only after a retrain, and walk-forward validation should confirm
the added indicators help before relying on them. **Verified** with
scikit-learn/lightgbm installed: 57 featurize-path tests pass.

### 5. HIGH — api-smoke routes no longer pass on a 404
Commit: included with the e2e batch. `api-smoke.spec.ts` core-route smoke
tests (`/signals`, `/playbook/rules`, `/options`, `/backtest/all`) asserted
only `status < 500`, so a 404 (router failed to mount) passed. Added
`.not.toBe(404)` — these routes are always mounted and return `200 []` on
empty data, so a 404 is a real regression. (CI verifies — backend can't run
in the offline sandbox.)

---

## ⏳ Remaining — NOT auto-fixed (needs a decision or domain work)

These were deliberately left untouched because fixing them blindly would
either change live trading-model behavior or invent "expected" financial
numbers (which would just create new fake tests). Each needs a human call.

### A. DECISION NEEDED — `featurize()` blesses missing data as `0`
`tests/test_featurize_all_nan_robust.py` (the `== 0.0` assertion).
An all-NULL `vix_close` (market-fear input) is coerced to `0.0` and the
test asserts that is correct. This conflicts with CLAUDE.md Rule 3.7
(missing financial data must not silently become `0`). BUT the coercion is
in the ML feature-matrix path, where imputation is a legitimate modeling
choice. Changing it alters how the magnitude model treats missing data —
a model-owner decision, not a test cleanup. Options:
  1. Keep `0`-imputation but add an explicit `vix_close_missing` indicator
     feature (best practice) and assert on that.
  2. Make `featurize()` fail-loud / emit NaN on all-NULL required columns.
  3. Accept current behavior and document it as an intentional Rule 3.7
     exception for ML imputation.

### B. ~18 lenient e2e tests (browser) — design review needed
`platform/tests/`: `api-smoke.spec.ts` (4 endpoints assert only
`status < 500` — a 404/empty-200 passes), `navigation.spec.ts`
(route-loads asserts shell mounts, not data), `dashboard.spec.ts` /
`phase1-charts.spec.ts` / `charts-cards.spec.ts` (assert metric *labels*,
not values — an all-"—" screen passes), `data-pipeline-status.spec.ts`
(accepts `unknown` freshness as valid). These are intentionally lenient
for empty-data environments; tightening them to assert values needs CI
runs against a seeded backend to validate, and a product call on what the
"real" assertion should be per screen.

### C. ~20 unit tests asserting on fabricated values — companion tests needed
e.g. `test_options_live.py`, `test_fetch_av_realtime_options.py`,
`test_options_pnl_translation.py`, `test_ranker.py`,
`test_agent_orchestrator.py`, plus several that only test the empty/skip
path (`test_calibrate_thresholds.py`, `test_strat_history.py`,
`test_backtest.py`, …). They feed hand-typed Greeks/prices/indicators
through a mock and assert the same numbers come back (proves plumbing, not
math), or only assert the "we got nothing" path. The fix is to add
happy-path companion tests that exercise the real parse/compute path with
a realistic raw payload — this requires the production payload formats and
the heavy libs installed, so it can't be done blind without risking new
fake tests.

### Good patterns to copy (already correct)
`test_fetch_market_data_fail_fast.py` (0 rows on a weekday → exit 5),
`test_audit_data_freshness.py` (fresh ts + low rows → STALE),
`tests/conftest.py` (live mode skips on empty rather than passing),
`tests/integration/conftest.py` (`run_sql` does not swallow → schema drift
raises).
