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

## ✅ Round 2 — remaining items fixed (deps installed + verified)

After installing the full test dependency set (the sandbox starts bare; all
packages ARE pinned in `requirements*.txt`), the previously-"can't verify"
items were investigated and fixed for real. Five parallel agents each owned
a distinct file group; every change was verified by running pytest.
**Full CI-equivalent suite after this round: 3439 passed, 51 skipped, 0
failed, 0 errors.**

### A. `featurize()` missing-data — DONE (see fix #4 above)
Operator chose "add a missing flag." Implemented + verified. The `== 0.0`
test now also asserts the `vix_close__isna` indicator. No longer a silent 0.

### B. Lenient e2e tests — tightened (the safe ones)
- `gamma-levels.spec.ts`, `api-smoke.spec.ts` — done (round 1).
- `navigation.spec.ts` — now asserts each route renders its real heading
  (was: only shell mounted); skip-on-empty.
- `dashboard.spec.ts` — APIs are mocked/deterministic, so now asserts real
  values (`Daily bias BULLISH`, `$220.50`, `58.4`) + `.not.toHaveText('—')`.
- `data-pipeline-status.spec.ts` — `unknown` freshness no longer passes as
  healthy; asserts a real `ok|warn|stale` status, skips on empty endpoint.
- `phase1-charts.spec.ts`, `charts-cards.spec.ts` — reviewed, intentionally
  left as-is: they already assert real API values, and their UI assertions
  are on static labels or deliberately non-deterministic synthetic-data
  outputs where a hard assert would *false-fail*. Documented in-file.
  (Browser can't run in the sandbox — these are CI-verified.)

### C. Unit tests asserting on fabricated values — real happy-path coverage added
- `test_options_live.py` / `test_fetch_av_realtime_options.py` /
  `test_options_pnl_translation.py` (+17 tests) — parse a realistic raw AV
  payload through the REAL parser; assert Greek-sign invariants
  (call δ∈[0,1], put δ∈[-1,0], γ≥0, θ≤0), P&L sign correctness, and that
  missing fields become `None`/`NaN`, never `0` (Rule 3.7).
- `test_ranker.py` / `test_calibrate_thresholds.py` (+4) — real scoring
  drives ranking; negative-weight branch; under-sampled timeframe yields
  `None` not `0`.
- `test_agent_orchestrator.py` (+5) — verifies the orchestrator overrides
  the LLM's hardcoded trade numbers with deterministic `compute_persona_plans`
  math, and records typed failure reasons (not silent sentinels).
- `test_backtest.py` / `test_strat_history.py` (+6) — happy-path runs the
  real engine on synthetic bars and asserts non-vacuous outcomes
  (trades>0, win-rate∈[0,1], no look-ahead, ≥90% bars classified).

### D. Real production bug found + fixed — `lib/strat_levels.py`
The `test_strat_levels_freshness.py` failures were NOT a test problem.
`_trading_days_between` had a silent Rule 3.7 fallback — when
`pandas_market_calendars` is absent it approximated trading days as
`int(calendar_days / 1.4)`, which ignores weekends AND holidays, producing
wrong counts (Memorial-Day window → 3 instead of 2; a 1-day gap → 0). That
re-opens the exact 2026-05-06 stale-level-cache hole the freshness guard
exists to close. Replaced with a holiday-aware `numpy.busday_count` over an
NYSE holiday calendar (no extra dependency) and removed a second
`except: return 0` swallow. Verified: the fallback matches the `mcal` path
exactly across Memorial Day / July 4 / Christmas / single-day windows.

### E. Resource-dependent suites now skip cleanly (mitigation)
`tests/test_e2e.py` (Selenium/Playwright) and `tests/integration/` (live
Postgres) used to ERROR when their resource was absent (looked like broken
tests). They now SKIP with a clear reason when the `pytest-playwright`
plugin / a configured DB isn't present. CI provides those resources, so the
tests still run there; a *configured-but-unreachable* DB still surfaces a
real error rather than being masked.

### Good patterns to copy (already correct)
`test_fetch_market_data_fail_fast.py` (0 rows on a weekday → exit 5),
`test_audit_data_freshness.py` (fresh ts + low rows → STALE),
`tests/conftest.py` (live mode skips on empty rather than passing),
`tests/integration/conftest.py` (`run_sql` does not swallow → schema drift
raises).
