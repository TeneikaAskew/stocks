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
    "timeframe", "label_mode", "objective", "dataset_snapshot",
    "magnitude_thresholds_atr_json", "code_commit", "dataset_snapshot_end_utc",
    "random_seed", "config_sha256", "config_json", "status", "failure_type",
    "failure_message", "elapsed_seconds", "inner_fold_scores_json",
    "validation_mean", "validation_standard_error", "selected_by_one_se",
    "outer_fold_id", "outer_test_log_loss", "outer_test_binary_tail_cost",
    "outer_test_accuracy",
]


def require(condition: bool, message: str) -> None:
    """Raise on invalid input even when Python assertions are optimized out."""
    if not condition:
        raise ValueError(message)


def validate() -> None:
    common = None
    for ticker in TICKERS:
        path = ROOT / f"{ticker.lower()}.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        require(manifest["ticker"] == ticker, f"{path}: ticker mismatch")
        require(
            manifest["search"]["max_attempts_per_ticker_timeframe_label_mode"] > 0,
            f"{path}: search must be bounded",
        )
        require(set(manifest["search"]["space"]) == PARAMETERS,
                f"{path}: search-space mismatch")
        require(manifest["search"]["fixed_parameters"]["bagging_freq"] > 0,
                f"{path}: bagging_fraction requires positive bagging_freq")
        contract = manifest["data_contract"]
        require(contract["magnitude_thresholds_atr"] == [0.5, 1.0, 1.5],
                f"{path}: target thresholds are not pinned")
        require("dataset_snapshot_end_utc" in contract,
                f"{path}: final outer boundary is missing")
        validation = manifest["validation"]
        require(validation["split_unit"] == "exchange_session",
                f"{path}: splits must use sessions")
        require(validation["design"] == "nested_anchored_chronological",
                f"{path}: validation design mismatch")
        require("dataset_snapshot_end_utc" in validation["outer_test_horizon"],
                f"{path}: final outer boundary is not defined")
        require(validation["test_role"].startswith("locked_once"),
                f"{path}: outer test is not locked")
        selection = manifest["selection"]
        require(selection["rule"] == "one_standard_error",
                f"{path}: selection rule mismatch")
        require(selection["test_accuracy_forbidden"] is True,
                f"{path}: test accuracy must be forbidden")
        objectives = {r["objective"] for r in selection["registered_runs"].values()}
        require(objectives == set(selection["allowed_objectives"]),
                f"{path}: registered objective mismatch")

        comparable = json.loads(json.dumps(manifest))
        comparable["ticker"] = "TICKER"
        comparable["attempt_log"]["path"] = "ticker_attempts.csv"
        if common is None:
            common = comparable
        require(comparable == common, f"{path}: ticker manifests have drifted")

        table = ROOT / manifest["attempt_log"]["path"]
        with table.open(newline="", encoding="utf-8") as fh:
            rows = csv.reader(fh)
            require(next(rows) == ATTEMPT_COLUMNS, f"{table}: schema mismatch")
            for line_number, row in enumerate(rows, start=2):
                require(len(row) == len(ATTEMPT_COLUMNS),
                        f"{table}:{line_number}: malformed row")
                require(row[4] == ticker, f"{table}:{line_number}: ticker mismatch")
                require(row[15] in manifest["attempt_log"]["status_values"],
                        f"{table}:{line_number}: bad status")
                if row[15] != "succeeded":
                    require(bool(row[16] and row[17]),
                            f"{table}:{line_number}: failure details required")


if __name__ == "__main__":
    validate()
    print("validated 3 magnitude experiment manifests and attempt tables")
