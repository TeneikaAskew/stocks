#!/usr/bin/env python3
"""Validate magnitude HPO manifests and the append-only CSV schemas."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TICKERS = ("IWM", "SPY", "QQQ")
PARAMETERS = {
    "class_weight_power", "max_depth", "num_leaves", "min_child_samples",
    "learning_rate", "n_estimators", "reg_alpha_l1", "reg_lambda_l2",
    "feature_fraction", "bagging_fraction", "calibration_method",
    "binary_tail_threshold",
}
ATTEMPT_COLUMNS = [
    "experiment_id", "run_id", "attempt_id", "attempted_at_utc", "ticker",
    "timeframe", "label_mode", "objective", "dataset_snapshot", "code_commit",
    "random_seed", "config_sha256", "config_json", "status", "failure_type",
    "failure_message", "elapsed_seconds", "inner_fold_scores_json",
    "validation_mean", "validation_standard_error", "selected_by_one_se",
    "outer_fold_id", "outer_test_log_loss", "outer_test_binary_tail_log_loss",
    "outer_test_accuracy",
]


def validate() -> None:
    common = None
    for ticker in TICKERS:
        path = ROOT / f"{ticker.lower()}.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["ticker"] == ticker, f"{path}: ticker mismatch"
        assert (
            manifest["search"]["max_attempts_per_ticker_timeframe_label_mode"] > 0
        )
        assert set(manifest["search"]["space"]) == PARAMETERS
        assert manifest["validation"]["split_unit"] == "exchange_session"
        assert manifest["validation"]["design"] == "nested_anchored_chronological"
        assert manifest["validation"]["test_role"].startswith("locked_once")
        assert manifest["selection"]["rule"] == "one_standard_error"
        assert manifest["selection"]["test_accuracy_forbidden"] is True
        assert (
            manifest["selection"]["pre_registered_objective"]
            in manifest["selection"]["allowed_objectives"]
        )

        comparable = json.loads(json.dumps(manifest))
        comparable["ticker"] = "TICKER"
        comparable["attempt_log"]["path"] = "ticker_attempts.csv"
        if common is None:
            common = comparable
        assert comparable == common, f"{path}: ticker manifests have drifted"

        table = ROOT / manifest["attempt_log"]["path"]
        with table.open(newline="", encoding="utf-8") as fh:
            rows = csv.reader(fh)
            assert next(rows) == ATTEMPT_COLUMNS, f"{table}: schema mismatch"
            for line_number, row in enumerate(rows, start=2):
                assert len(row) == len(ATTEMPT_COLUMNS), (
                    f"{table}:{line_number}: malformed row"
                )
                assert row[4] == ticker, f"{table}:{line_number}: ticker mismatch"
                assert row[13] in manifest["attempt_log"]["status_values"], (
                    f"{table}:{line_number}: bad status"
                )
                if row[13] != "succeeded":
                    assert row[14] and row[15], (
                        f"{table}:{line_number}: failure details required"
                    )


if __name__ == "__main__":
    validate()
    print("validated 3 magnitude experiment manifests and attempt tables")
