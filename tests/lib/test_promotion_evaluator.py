import hashlib
import json

import pytest

from lib.promotion_evaluator import (
    PromotionPolicy,
    evaluate_promotions,
    promote_approved_report,
    rollback_report,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def policy():
    return PromotionPolicy(20, 100, 0.2, 0.1, 0.05, 0.99, 4, 1.0)


def row():
    artifact = {"uri": "gs://models/a", "version": "v1"}
    contract = {"ticker": "SPY", "model_id": "v1", "features": ["x"]}
    metrics = {
        "window_days": (30, 29, 31),
        "sample_size": (200, 190, 210),
        "feature_drift": (0.1, 0.08, 0.12),
        "probability_drift": (0.04, 0.03, 0.05),
        "ece": (0.02, 0.01, 0.03),
        "log_loss_ratio": (0.9, 0.87, 0.93),
        "alerts_per_day": (2, 1, 3),
        "realized_utility": (2, 1.5, 2.5),
    }
    return {
        "ticker": "SPY",
        "model_id": "v1",
        "dataset": "shadow",
        "finalized": True,
        "evaluation_id": "e1",
        "artifact": artifact,
        "contract": contract,
        "artifact_sha256": hashlib.sha256(canonical(artifact)).hexdigest(),
        "contract_sha256": hashlib.sha256(canonical(contract)).hexdigest(),
        "metrics": {
            k: {"value": v, "ci_lower": lo, "ci_upper": hi} for k, (v, lo, hi) in metrics.items()
        },
    }


def test_evaluator_reads_only_finalized_shadow_or_final_test():
    draft = row()
    draft["model_id"] = "draft"
    draft["finalized"] = False
    train = row()
    train["model_id"] = "train"
    train["dataset"] = "training"
    final = row()
    final["dataset"] = "final_test"
    reports = evaluate_promotions([draft, train, final], policy(), generated_at="now")
    assert len(reports) == 1
    assert reports[0]["overall_verdict"] == "PASS"
    assert reports[0]["evidence"] == {
        "dataset": "final_test",
        "evaluation_id": "e1",
        "finalized": True,
    }
    assert {c["name"] for c in reports[0]["criteria"]} == {
        "data_window",
        "sample_size",
        "feature_drift",
        "probability_drift",
        "calibration",
        "worse_than_baseline_log_loss",
        "alert_frequency",
        "realized_utility",
        "artifact_contract_identity",
    }


def test_adverse_ci_and_one_failure_force_fail_without_composite():
    candidate = row()
    candidate["metrics"]["ece"] = {"value": 0.04, "ci_lower": 0.03, "ci_upper": 0.06}
    report = evaluate_promotions([candidate], policy())[0]
    calibration = next(c for c in report["criteria"] if c["name"] == "calibration")
    assert calibration["observed"] == 0.04
    assert calibration["confidence_interval"] == {"lower": 0.03, "upper": 0.06}
    assert calibration["threshold"] == 0.05
    assert calibration["passed"] is False
    assert report["overall_verdict"] == "FAIL"


def test_missing_metric_and_identity_mismatch_fail_closed():
    candidate = row()
    del candidate["metrics"]["sample_size"]
    candidate["artifact"]["version"] = "tampered"
    report = evaluate_promotions([candidate], policy())[0]
    assert report["overall_verdict"] == "FAIL"
    assert any(c["name"] == "sample_size" and not c["passed"] for c in report["criteria"])
    assert any(
        c["name"] == "artifact_contract_identity" and not c["passed"] for c in report["criteria"]
    )


def test_duplicate_finalized_snapshot_is_rejected_not_averaged():
    with pytest.raises(ValueError, match="multiple finalized"):
        evaluate_promotions([row(), row()], policy())


def test_rollback_conditions_are_independent_and_fail_closed():
    candidate = row()
    observation = {
        "ticker": "SPY",
        "model_id": "v1",
        "metrics": candidate["metrics"],
        "feature_health": {
            "missing_count": 0,
            "max_age_seconds": 20,
            "max_allowed_age_seconds": 60,
        },
    }
    assert rollback_report(observation, policy())["rollback_required"] is False
    observation["metrics"]["log_loss_ratio"] = {"value": 1.1, "ci_lower": 1.0, "ci_upper": 1.2}
    observation["feature_health"]["missing_count"] = 1
    result = rollback_report(observation, policy())
    assert result["rollback_required"] is True
    assert set(result["triggered_conditions"]) == {
        "worse_than_baseline_rolling_log_loss",
        "missing_or_stale_features",
    }


class MemoryStore:
    def __init__(self, values):
        self.values = values
        self.writes = []

    def read_bytes(self, uri):
        return self.values[uri]

    def write_bytes(self, uri, value):
        self.values[uri] = value
        self.writes.append(uri)


def test_promotion_requires_approval_and_records_report_before_latest():
    report = evaluate_promotions([row()], policy(), generated_at="now")[0]
    approval = {
        "decision": "APPROVE",
        "report_uri": "report.json",
        "report_id": report["report_id"],
        "approved_by": "risk@example.com",
        "approved_at": "2026-09-26T00:00:00Z",
    }
    store = MemoryStore(
        {
            "report.json": json.dumps(report).encode(),
            "approval.json": json.dumps(approval).encode(),
            "contract.json": json.dumps(row()["contract"]).encode(),
        }
    )
    contract = promote_approved_report(
        store,
        report_uri="report.json",
        approval_uri="approval.json",
        contract_uri="contract.json",
        latest_uri="LATEST",
    )
    assert contract["promotion"]["report_uri"] == "report.json"
    assert store.writes == ["contract.json", "LATEST"]
    assert store.values["LATEST"] == b"v1"


def test_wrong_or_absent_approval_never_changes_latest():
    report = evaluate_promotions([row()], policy())[0]
    approval = {
        "decision": "REJECT",
        "report_uri": "report.json",
        "report_id": report["report_id"],
        "approved_by": "risk",
    }
    store = MemoryStore(
        {
            "report.json": json.dumps(report).encode(),
            "approval.json": json.dumps(approval).encode(),
            "contract.json": json.dumps(row()["contract"]).encode(),
            "LATEST": b"old",
        }
    )
    with pytest.raises(ValueError, match="explicitly approve"):
        promote_approved_report(
            store,
            report_uri="report.json",
            approval_uri="approval.json",
            contract_uri="contract.json",
            latest_uri="LATEST",
        )
    assert store.values["LATEST"] == b"old"
    assert store.writes == []
