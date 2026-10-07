# Ticker model promotion evaluator

`python scripts/evaluate_model_promotion.py ROWS.jsonl POLICY.json --output REPORT.json`
reads only rows whose `finalized` value is the JSON boolean `true` and whose
`dataset` is `shadow` or `final_test`. It emits one JSON report for each
`(ticker, model_id)`. Each invocation must contain exactly one eligible pair so
the output is one addressable report object that the promotion command can read
directly. Training, validation, draft, and incomplete rows are not promotion evidence.

Every metric is `{ "value": ..., "ci_lower": ..., "ci_upper": ... }`. The
adverse confidence bound must clear the policy threshold. The report always
lists all mandatory gates: data-window length, sample size, feature drift,
probability drift, calibration ECE, rolling log-loss ratio to the registered
baseline, alerts per day, realized utility, and artifact/contract identity.
Every cohort named by the registered policy must clear those same gates.
Missing evidence fails closed. The overall verdict is `PASS` only when every
mandatory gate passes; there is no composite score and no averaging away a
failure. A second finalized row for the same model is rejected rather than
silently pooling repeated final-test reads.

Artifact and contract SHA-256 values are hashes of canonical JSON. The contract
must also name the evaluated ticker and model ID. Retain the resulting report
at an immutable URI before requesting approval.

## Approval and promotion

An approver creates a separate JSON object:

```json
{
  "decision": "APPROVE",
  "report_uri": "file:///registry/reports/SPY-v1.json",
  "report_id": "<report_id from the report>",
  "approved_by": "risk@example.com",
  "approved_at": "2026-09-26T12:00:00Z"
}
```

Then run:

```bash
python scripts/promote_approved_model.py \
  --report-uri file:///registry/reports/SPY-v1.json \
  --approval-uri file:///registry/approvals/SPY-v1.json \
  --contract-uri file:///registry/SPY/v1/CONTRACT.json \
  --latest-uri file:///registry/SPY/LATEST \
  --approval-trust-prefix file:///registry/approvals/
```

The promotion operation verifies the PASS report, every mandatory gate, the
approver identity, exact report URI and report ID, and ticker/model contract
identity. It first updates the model contract with the approving report and
approval URIs, identity, and timestamp. Only then does it atomically replace
`LATEST`. A validation failure leaves both the contract and `LATEST` untouched.
The approval must be stored under the configured protected trust prefix, while
the report must be outside it. Contracts must bind the evaluated artifact and
name a distinct, immediately usable rollback target.
Cloud implementations should provide the same `ObjectStore` interface and use
conditional writes/generation preconditions around this operation.

## Rollback policy

`rollback_report` evaluates each trigger independently and requests rollback if
**any** condition is true:

* calibration ECE exceeds its registered ceiling;
* the adverse bound of rolling model/baseline log loss exceeds the registered
  ratio;
* alert frequency exceeds its ceiling;
* any required feature is missing or its age exceeds the policy's registered
  maximum age; or
* the adverse bound of realized utility falls below the registered floor.

Missing monitoring evidence also fails closed and requests rollback. Rollback
reports list every trigger so operators do not have to infer the cause from a
combined score.
