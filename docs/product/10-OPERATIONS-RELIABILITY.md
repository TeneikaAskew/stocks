# Operations and Reliability Plan

## Trust posture
Current code contains health/freshness routes, `job_runs`, scheduled jobs, audit reports and incident records. That is operational evidence, not proof of end-to-end SLO attainment. PR [#802](https://github.com/TeneikaAskew/stocks/pull/802) and [#804](https://github.com/TeneikaAskew/stocks/pull/804) qualify feature trust: map correctness, fallbacks, replay integrity, infrastructure drift, dormant surfaces and coverage findings to affected catalog rows.

| Capability | Known risk theme | Trust status | Required evidence/gate |
|---|---|---|---|
| Market/premarket/playbook | stale/unfed/silent-empty paths | needs remediation/broken | freshness contract, alarms, explicit unavailable, recovery replay |
| Live signals/levels/exits | semantic divergence and risk-rule parity | needs remediation | shared live/replay fixtures and production telemetry |
| Replay/backtest | future leakage and clock/session mismatch | invalidated | quarantined artifacts, PIT audit, frozen rerun |
| Models | leakage/provenance/evaluation weaknesses | Retest Required | model promotion gate and shadow evidence |
| AI insight | prompt/model/input trace and numeric authority | Experimental | structured provenance, abstention, evaluation/cost |
| Auth/secrets | fail-open/default and binding risks | needs remediation | non-local deploy guard, least privilege, rotation |
| Deploy/schema | drift, create/update asymmetry, migration sprawl | needs remediation | declarative convergence and restore drill |
| Freshness/observability | incomplete served-dataset coverage | Incomplete | registry-driven checks and paging/runbooks |

## Proposed SLO/NFR catalog
- **Availability:** per user journey and endpoint; numeric objective/measurement window is `PRODUCT DECISION REQUIRED`.
- **Freshness:** per dataset cadence and market session, measured from event/source and ingestion timestamps—not only row presence.
- **Timeliness:** signal decision/persistence/delivery latency measured separately.
- **Job reliability:** terminal success, expected count/watermark, deadline, classified retry and consecutive-failure alert.
- **Replay parity:** shared fixture equivalence and no future reads; zero tolerated temporal violations.
- **Auditability:** complete decision/config/model/data/code trace resolvable from output ID.
- **DR:** RPO/RTO TBD; automated backups plus recurring isolated restore drill.
- **Scalability/performance:** endpoint/job capacity tests before SLO claims; avoid unbounded queries/fan-out.

## Failure and recovery
Detect → mark dependent outputs unavailable/stale → stop decision/alert propagation where unsafe → alert owner with run/as-of/error → replay idempotently from last good watermark → verify counts/quality → annotate incident and affected artifacts. Do not silently fall back to zero, empty, cached-undated, or another vendor without explicit provenance.

## Audit-to-product rule
Findings live with the impacted feature in [12](12-PR-ISSUE-TRACEABILITY.md), not as a detached audit. Closure requires regression evidence and production verification; merged code alone does not restore trust.
