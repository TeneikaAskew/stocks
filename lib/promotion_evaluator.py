"""Fail-closed model promotion and rollback policy evaluation.

The evaluator deliberately accepts only immutable, finalized shadow or final-test
observations.  It emits plain dictionaries so reports can be serialized, signed,
and retained independently of the training job that produced an artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

ELIGIBLE_DATASETS = frozenset({"shadow", "final_test"})


@dataclass(frozen=True)
class PromotionPolicy:
    min_window_days: float
    min_samples: int
    max_feature_drift: float
    max_probability_drift: float
    max_ece: float
    max_log_loss_ratio: float
    max_alerts_per_day: float
    min_realized_utility: float


@dataclass(frozen=True)
class CriterionSpec:
    name: str
    source: str
    operator: str
    threshold: Any


class ObjectStore(Protocol):
    """Smallest storage interface needed for an auditable pointer flip."""

    def read_bytes(self, uri: str) -> bytes: ...
    def write_bytes(self, uri: str, value: bytes) -> None: ...


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _metric(row: Mapping[str, Any], name: str) -> tuple[float, float, float]:
    metrics = row.get("metrics")
    if not isinstance(metrics, Mapping) or not isinstance(metrics.get(name), Mapping):
        raise ValueError(f"missing metric {name!r}")
    item = metrics[name]
    try:
        value = float(item["value"])
        low = float(item["ci_lower"])
        high = float(item["ci_upper"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"metric {name!r} requires value, ci_lower, and ci_upper") from exc
    if not low <= value <= high:
        raise ValueError(f"metric {name!r} confidence interval does not contain value")
    return value, low, high


def _criterion(spec: CriterionSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    value, low, high = _metric(row, spec.source)
    # Use the adverse CI bound, not the point estimate.  Uncertainty therefore
    # cannot turn a failed or inconclusive mandatory gate into a pass.
    if spec.operator == "max":
        passed = high <= float(spec.threshold)
    elif spec.operator == "min":
        passed = low >= float(spec.threshold)
    else:  # guarded at construction sites; fail loudly if extended incorrectly
        raise ValueError(f"unsupported operator {spec.operator!r}")
    return {
        "name": spec.name,
        "mandatory": True,
        "observed": value,
        "confidence_interval": {"lower": low, "upper": high},
        "operator": spec.operator,
        "threshold": spec.threshold,
        "passed": passed,
    }


def evaluate_promotions(
    rows: Iterable[Mapping[str, Any]], policy: PromotionPolicy, *, generated_at: str | None = None
) -> list[dict[str, Any]]:
    """Return one deterministic, machine-readable report per ticker/model.

    Non-finalized and non-shadow/final-test rows are ignored, never treated as
    evidence. Multiple eligible rows for one model are rejected: upstream must
    first finalize a single immutable evaluation snapshot, avoiding accidental
    averaging across experiments or repeated peeks at the final test set.
    """
    eligible: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        if row.get("finalized") is not True or row.get("dataset") not in ELIGIBLE_DATASETS:
            continue
        ticker, model_id = str(row.get("ticker", "")), str(row.get("model_id", ""))
        if not ticker or not model_id:
            raise ValueError("eligible rows require ticker and model_id")
        key = (ticker, model_id)
        if key in eligible:
            raise ValueError(f"multiple finalized evaluation rows for {ticker}/{model_id}")
        eligible[key] = row

    specs = (
        CriterionSpec("data_window", "window_days", "min", policy.min_window_days),
        CriterionSpec("sample_size", "sample_size", "min", policy.min_samples),
        CriterionSpec("feature_drift", "feature_drift", "max", policy.max_feature_drift),
        CriterionSpec(
            "probability_drift", "probability_drift", "max", policy.max_probability_drift
        ),
        CriterionSpec("calibration", "ece", "max", policy.max_ece),
        CriterionSpec(
            "worse_than_baseline_log_loss", "log_loss_ratio", "max", policy.max_log_loss_ratio
        ),
        CriterionSpec("alert_frequency", "alerts_per_day", "max", policy.max_alerts_per_day),
        CriterionSpec("realized_utility", "realized_utility", "min", policy.min_realized_utility),
    )
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    reports = []
    for (ticker, model_id), row in sorted(eligible.items()):
        criteria: list[dict[str, Any]] = []
        errors: list[str] = []
        for spec in specs:
            try:
                criteria.append(_criterion(spec, row))
            except ValueError as exc:
                errors.append(str(exc))
                criteria.append(
                    {
                        "name": spec.name,
                        "mandatory": True,
                        "observed": None,
                        "confidence_interval": None,
                        "operator": spec.operator,
                        "threshold": spec.threshold,
                        "passed": False,
                        "error": str(exc),
                    }
                )

        artifact = row.get("artifact")
        contract = row.get("contract")
        expected_artifact_sha = row.get("artifact_sha256")
        expected_contract_sha = row.get("contract_sha256")
        observed_artifact_sha = _sha256(artifact) if artifact is not None else None
        observed_contract_sha = _sha256(contract) if contract is not None else None
        identity_pass = bool(
            expected_artifact_sha
            and expected_contract_sha
            and observed_artifact_sha == expected_artifact_sha
            and observed_contract_sha == expected_contract_sha
            and isinstance(contract, Mapping)
            and contract.get("ticker") == ticker
            and contract.get("model_id") == model_id
        )
        criteria.append(
            {
                "name": "artifact_contract_identity",
                "mandatory": True,
                "observed": {
                    "artifact_sha256": observed_artifact_sha,
                    "contract_sha256": observed_contract_sha,
                    "contract_ticker": (
                        contract.get("ticker") if isinstance(contract, Mapping) else None
                    ),
                    "contract_model_id": (
                        contract.get("model_id") if isinstance(contract, Mapping) else None
                    ),
                },
                "confidence_interval": None,
                "threshold": {
                    "artifact_sha256": expected_artifact_sha,
                    "contract_sha256": expected_contract_sha,
                    "ticker": ticker,
                    "model_id": model_id,
                },
                "operator": "identity",
                "passed": identity_pass,
            }
        )
        passed = all(item["passed"] for item in criteria)
        report = {
            "schema_version": "1.0",
            "generated_at": timestamp,
            "ticker": ticker,
            "model_id": model_id,
            "evidence": {
                "dataset": row["dataset"],
                "evaluation_id": row.get("evaluation_id"),
                "finalized": True,
            },
            "artifact_identity": {"sha256": observed_artifact_sha},
            "contract_identity": {"sha256": observed_contract_sha},
            "criteria": criteria,
            "errors": errors,
            "overall_verdict": "PASS" if passed else "FAIL",
        }
        report["report_id"] = _sha256(report)
        reports.append(report)
    return reports


def rollback_report(observation: Mapping[str, Any], policy: PromotionPolicy) -> dict[str, Any]:
    """Evaluate all registered rollback triggers; any one requests rollback."""
    specs = (
        CriterionSpec("calibration_drift", "ece", "max", policy.max_ece),
        CriterionSpec(
            "worse_than_baseline_rolling_log_loss",
            "log_loss_ratio",
            "max",
            policy.max_log_loss_ratio,
        ),
        CriterionSpec(
            "excessive_alert_frequency", "alerts_per_day", "max", policy.max_alerts_per_day
        ),
        CriterionSpec(
            "realized_utility_below_floor", "realized_utility", "min", policy.min_realized_utility
        ),
    )
    checks = []
    for spec in specs:
        try:
            gate = _criterion(spec, observation)
        except ValueError as exc:
            gate = {
                "name": spec.name,
                "mandatory": True,
                "observed": None,
                "confidence_interval": None,
                "operator": spec.operator,
                "threshold": spec.threshold,
                "passed": False,
                "error": str(exc),
            }
        gate["triggered"] = not gate["passed"]
        checks.append(gate)
    feature_health = observation.get("feature_health", {})
    available = feature_health.get("missing_count") == 0
    fresh = feature_health.get("max_age_seconds") is not None and feature_health.get(
        "max_age_seconds"
    ) <= feature_health.get("max_allowed_age_seconds", -1)
    checks.append(
        {
            "name": "missing_or_stale_features",
            "mandatory": True,
            "observed": feature_health,
            "confidence_interval": None,
            "threshold": {"missing_count": 0, "max_age_seconds": "<= max_allowed_age_seconds"},
            "operator": "health",
            "passed": available and fresh,
            "triggered": not (available and fresh),
        }
    )
    triggered = [c["name"] for c in checks if c["triggered"]]
    return {
        "schema_version": "1.0",
        "ticker": observation.get("ticker"),
        "model_id": observation.get("model_id"),
        "checks": checks,
        "rollback_required": bool(triggered),
        "triggered_conditions": triggered,
    }


def promote_approved_report(
    store: ObjectStore, *, report_uri: str, approval_uri: str, contract_uri: str, latest_uri: str
) -> dict[str, Any]:
    """Promote only an explicitly approved PASS report, writing LATEST last."""
    report = json.loads(store.read_bytes(report_uri))
    approval = json.loads(store.read_bytes(approval_uri))
    if report.get("overall_verdict") != "PASS":
        raise ValueError("promotion report verdict is not PASS")
    if not report.get("criteria") or not all(
        c.get("mandatory") and c.get("passed") for c in report["criteria"]
    ):
        raise ValueError("not every mandatory promotion criterion passed")
    if approval.get("decision") != "APPROVE" or approval.get("report_uri") != report_uri:
        raise ValueError("approval must explicitly approve this report URI")
    if approval.get("report_id") != report.get("report_id") or not approval.get("approved_by"):
        raise ValueError("approval identity is incomplete or does not match report")
    contract = json.loads(store.read_bytes(contract_uri))
    if contract.get("ticker") != report.get("ticker") or contract.get("model_id") != report.get(
        "model_id"
    ):
        raise ValueError("model contract identity does not match promotion report")
    contract["promotion"] = {
        "report_uri": report_uri,
        "report_id": report["report_id"],
        "approval_uri": approval_uri,
        "approved_by": approval["approved_by"],
        "approved_at": approval.get("approved_at"),
    }
    # Contract is durable before the pointer changes. Readers can therefore
    # never observe a newly promoted model without its approving report URI.
    store.write_bytes(contract_uri, json.dumps(contract, indent=2, sort_keys=True).encode())
    store.write_bytes(latest_uri, str(report["model_id"]).encode())
    return contract


class FileStore:
    """Filesystem implementation used by the CLI and local operations."""

    def read_bytes(self, uri: str) -> bytes:
        return Path(uri.removeprefix("file://")).read_bytes()

    def write_bytes(self, uri: str, value: bytes) -> None:
        path = Path(uri.removeprefix("file://"))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(value)
        temporary.replace(path)
