# Magnitude-engine experiment manifests

The JSON files are the pre-registered, per-ticker contracts for magnitude-model
hyperparameter searches. A run must fill `dataset_snapshot` and `code_commit`
in its emitted run metadata without editing the manifest. The search is capped
at 64 attempted configurations for every ticker/timeframe/label-mode cell and
uses the fixed seed in the manifest.

## Leakage and selection contract

Splits are made from ordered New York exchange sessions, never shuffled bars.
For each outer test period, optimization and calibration use only expanding
inner-training sessions and their immediately following validation sessions.
The one-session purge and embargo protect the next-bar target at boundaries.
The outer test period stays locked until the one-standard-error rule has chosen
a configuration and the model has been refit on all eligible outer-training
sessions. Test accuracy is neither an objective nor a tie-breaker.

The objective must be selected before the first attempt and cannot change
within a run. The default is validation multiclass log loss. A run explicitly
registered as binary-tail may instead use the pre-registered EXPLOSIVE-tail
cost `(3 * false_negatives + false_positives) / observations`; its threshold is
learned inside the same inner validation procedure. The one-standard-error candidate set prevents a
noisy minimum from winning, and the ordered tie-breaks select the least complex
statistically indistinguishable candidate.

## Append-only attempt tables

Each manifest owns a sibling `<ticker>_attempts.csv`. The checked-in header is
the table schema. Runners must open it in append mode, take an exclusive file
or database lock, append exactly one row after **every** attempt, and `fsync`
before starting another attempt. Existing rows must never be updated or
removed. Invalid configurations, exceptions, pruning, and timeouts are rows,
not missing observations. `config_json` and `inner_fold_scores_json` are
canonical compact JSON strings; the configuration hash is SHA-256 over
`config_json`. Attempt IDs must be unique and monotonically increasing within a
run. Secrets and multiline exception traces must not be written to CSV.

A production runner may mirror these rows into an append-only database table,
but the exported table must preserve this schema and all statuses. Outer-test
metrics are deliberately stored separately from the selection fields so they
cannot become optimizer inputs.

Validate the contracts and pristine table headers with:

```bash
python gcp/research/magnitude_engine/experiments/validate.py
```
