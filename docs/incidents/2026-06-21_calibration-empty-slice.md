# Incident: CI flake — empty calibration slice in isotonic fold path

**Date**: 2026-06-21
**Severity**: low
**Duration**: ~60 min (analysis + fix)
**Error class**: Python `ValueError` in sklearn during CI full-suite run

## What happened

`tests/test_strat_dir_probes_calibration.py::test_calibration_path_runs_and_reports_ece`
passed in isolation locally (Python 3.11) but failed in the GitHub Actions CI
full-suite run (Python 3.12):

```
ValueError: Found array with 0 sample(s) (shape=(0,)) while a minimum of 1 is required.
  sklearn/isotonic.py:391  ir.fit(...)
```

The test exercises `_side_fold(..., calibrate="isotonic")` with a synthetic
fixture of 24 days × 50 rows (1200 total). The fold's train block was 14 days
× 50 = 700 rows; the date-carved calibration slice was ~140 rows (3 days × 50)
— sufficient in isolation. But `LGBMClassifier(min_child_samples=100)` on a
700-row fit-slice with only two classes and weak signal could produce a model
that predicts via the leaf-default (no actual splits). In newer
sklearn/LightGBM (CI = Python 3.12), `predict_proba()` on a (140, 4) calib
slice returns a `(0, 2)` shaped result under those conditions, and slicing
`[:, pos]` gives `array([], dtype=float64)`. The existing `calib_mask.sum()==0`
guard at entry doesn't catch this because the mask is non-empty — only the
model's output is empty.

## Root cause

Two separate gaps:

1. **Production code**: `_side_fold` in
   `gcp/research/strat_engine/strat_dir_probes.py` had no check on
   `len(p_calib)` after `model.predict_proba(...)[:, pos]`. In
   Python 3.12 + newer sklearn, the return can silently be empty
   even when the mask is non-empty, bypassing the entry guard and
   reaching `IsotonicRegression.fit([])` which raises.

2. **Test fixture too thin**: `_synthetic(per_day=50)` gives only 700
   train rows for the fold. With `min_child_samples=100` this is enough
   for LightGBM to build a model on some seeds/versions but not others,
   making the test non-deterministic across Python versions.

A secondary fingerprinting collision was discovered in
`test_locked_holdout_eval_trains_only_on_preholdout`: the set-of-float32-rounded-
to-6dp fingerprint collides in a 4800-row fixture, producing a false leak
detection failure after the fixture was enlarged.

## Fix

- **File**: `gcp/research/strat_engine/strat_dir_probes.py`, `_side_fold`, line ~604
- **Change**: Added `if len(p_calib) == 0:` guard after `predict_proba` with
  explicit `log.warning(...)` and fallback to `cal_status="RAW_calib_empty_predictions"`.
  Per Rule 3.7: fail loud with a logged reason, never silently swallow.

- **File**: `tests/test_strat_dir_probes_calibration.py`, `_synthetic` default
- **Change**: `per_day=50` → `per_day=200` (4800 total rows; calib slice ~520 rows).
  Guarantees both classes are reliably present and LightGBM produces real splits.

- **File**: same test file, `test_locked_holdout_eval_trains_only_on_preholdout`
- **Change**: fingerprint changed from `set(np.round(x, 6).tolist())` to
  `{np.float32(v).tobytes() for v in ...}` — uses exact float32 bit pattern
  instead of rounded decimal, which collides in the larger fixture.

## Why it wasn't caught earlier

- The test was only run locally on Python 3.11 where the degenerate
  `predict_proba` behavior does not reproduce. CI uses Python 3.12.
- `min_child_samples=100` is the right production value but makes the model
  fragile on thin synthetic fixtures — the test design didn't account for
  version-sensitive LightGBM splitting behavior.
- The fingerprinting approach (float32 rounded to 6dp as a set-membership
  proxy) is only collision-resistant for small arrays. The same test design
  pattern exists in two tests; the bug only manifested after the fixture was
  enlarged.

## Prevention

- [ ] Any test that exercises a LightGBM path with `min_child_samples=100`
  must use a fixture large enough that the model always builds at least one
  real split: at minimum 5× `min_child_samples` rows per class in the
  calibration slice.
- [ ] Float-value set fingerprinting for leak detection should use
  `.tobytes()` (exact binary identity) not rounded decimal (collision-prone).
  Update `test_holdout_bars_never_enter_any_training_fold` if its fixture is
  ever enlarged.
- [ ] Add a local `tox.ini` or `Makefile` target to run the research tests
  under both Python 3.11 and 3.12 before pushing.
