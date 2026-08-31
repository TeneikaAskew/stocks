# Product Requirements and Definition of Done

Requirements below are **PROPOSED — TARGET** unless explicitly marked current. They do not claim implementation.

## Functional and UX
- **REQ-UX-001:** Every served screen SHALL expose loading, empty, stale, permission, and dependency-error states without converting unknown data to a neutral trading conclusion.
- **REQ-MARKET-001:** Market context SHALL identify symbol, venue/session, as-of time, source, and freshness.
- **REQ-SIGNAL-001:** A signal SHALL persist strategy/version, inputs, configuration, levels, timestamps, and reason codes before delivery.
- **REQ-PLAYBOOK-001:** A plan SHALL show entry/trigger, invalidation, targets, data time, evidence, and unavailable fields.
- **REQ-JOURNAL-001:** Journal records SHALL be scoped to authenticated owner and support auditable import corrections.
- **REQ-ACCESS-001:** Core workflows SHALL be keyboard operable, have labeled controls, visible focus, and WCAG 2.1 AA contrast.

## Data, reliability, performance, observability
- **REQ-DATA-001:** Decision-critical reads SHALL fail explicitly on missing/stale upstream data and SHALL NOT substitute silent empty results.
- **REQ-DATA-002:** Historical/replay reads SHALL enforce an as-of clock and prohibit future observations, revised labels, or outcome-derived features.
- **REQ-DATA-003:** Every derived record SHALL carry source/as-of, pipeline, configuration, model/rule, artifact, and code version where applicable.
- **REQ-REL-001:** Live and replay implementations SHALL pass shared semantic parity fixtures before production promotion.
- **REQ-FRESH-001:** Every served dataset SHALL have an owner, expected cadence, measured age, alert threshold, and recovery instruction.
- **REQ-PERF-001:** Interactive API p95 targets and payload bounds SHALL be defined per endpoint and monitored before an availability claim.
- **REQ-OBS-001:** Jobs SHALL emit run identity, counts, watermark, duration, error class, retry, and terminal status.

## Security and operations
- **REQ-AUTH-001:** A non-local deployment SHALL reject requests unless an approved perimeter or application authenticator establishes identity.
- **REQ-AUTHZ-001:** Admin operations SHALL require a server-enforced role; email presentation alone SHALL NOT grant privilege.
- **REQ-TENANCY-001:** User-owned rows SHALL carry an immutable owner identifier and every access path SHALL enforce it.
- **REQ-SECRET-001:** Secrets SHALL be stored outside source and passed through least-privilege secret bindings with rotation ownership.
- **REQ-DR-001:** Cloud SQL and model/config artifacts SHALL have documented RPO/RTO, restore procedure, and recurring restore evidence.
- **REQ-DEPLOY-001:** Infrastructure SHALL be reproducible from reviewed configuration; create/update paths SHALL converge.

## Model/ML and auditability
- **REQ-MODEL-001:** Promotion SHALL require point-in-time-safe training, frozen untouched validation, baseline comparison, cohort metrics, calibration when probabilistic, and documented threshold.
- **REQ-MODEL-002:** Runtime outputs SHALL include model/artifact/version, feature contract, training cutoff, as-of time, and rollback target.
- **REQ-MODEL-003:** Promoted models SHALL complete shadow validation and support immediate rollback/disablement.
- **REQ-LLM-001:** LLM nodes SHALL distinguish supplied facts from generated interpretation, use structured schemas, and may not invent prices, stops, targets, or confidence.

## Universal acceptance gate
A significant feature is done only when: functional and UI/API behavior is acceptance-tested; authentication/authorization and ownership are enforced; data contract/freshness/provenance are measured; loading/empty/error/stale behavior is tested; telemetry and alert/runbook exist; documentation and traceability are current; deployment is reproducible; rollback and reliability evidence exist. Model features additionally meet REQ-MODEL-001..003. No existence-only evidence satisfies this gate.
