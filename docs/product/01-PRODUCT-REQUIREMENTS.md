# Product Requirements and Definition of Done

**Last reviewed:** 2026-08-31 · **Owner:** TBD

Requirements are **PROPOSED — TARGET** unless marked otherwise. They state intent; they do not
claim implementation. Each is written to be testable — a reviewer should be able to name the
test that would fail if it were violated.

## Repository-rule requirements

`CLAUDE.md` encodes seven incident-derived rules, several with sub-agents already gating merges
(`gcp-capacity-cost-reviewer`, `replay-integrity-reviewer`, `fallback-guard`, `trading-logic-reviewer`).
The previous revision carried a `REQ-` equivalent for only one of them (Rule 3.7), so the plan
could declare a feature done while the repository's own gates would reject it. Each rule now has
one, and each names the agent that enforces it.

| Requirement | Mirrors | Enforced by |
|---|---|---|
| **REQ-CAP-001:** A Cloud Run job SHALL NOT be considered done without a written back-of-envelope capacity calculation — volume (rows × bytes), velocity (queries/API calls per row × total) and wall-clock at production driver speeds — recorded in the PR. Where the estimate exceeds ¼ of the configured `--task-timeout`, the architecture SHALL be revised rather than the timeout raised. | Rule 0 | `gcp-capacity-cost-reviewer` |
| **REQ-CAP-002:** A job SHALL batch SQL by partition key rather than per-row wherever N may exceed 100; SHALL write in per-group chunks rather than accumulating before first commit; SHALL log per-group progress; and SHALL upsert idempotently so a re-run converges. | Rule 0 | `gcp-capacity-cost-reviewer` |
| **REQ-CAP-003:** A new scheduled job SHALL carry a `$/run × runs/day × 30` estimate, and SHALL default to `--max-retries 0` unless transient-retry benefit is demonstrated and duplicate notifications are acceptable. | Rule 0 | `gcp-config-reviewer` |
| **REQ-REPLAY-001:** Every counterfactual, audit verification, calibration backtest and what-if SHALL execute through a production replay path (`scripts/replay_signal_monitor.py`, `REPLAY_DATE`, `BRIEF_AS_OF`, `INSIGHT_AS_OF`, `lib/backtest.py`). Hand-rolled bar iteration, indicator calculation or signal scoring in a throwaway script SHALL NOT produce evidence for any decision. | Rule 3.6 | `replay-integrity-reviewer` |
| **REQ-REPLAY-002:** Where a production job lacks the as-of flag an audit needs, the flag SHALL be added to the production job first; the audit SHALL NOT proceed on a bespoke harness. | Rule 3.6 | `replay-integrity-reviewer` |
| **REQ-DATA-001:** Decision-critical reads SHALL fail explicitly on missing or stale upstream data and SHALL NOT substitute a silent empty result. Financial fields SHALL NOT be defaulted to `0`, `0.5` or a neutral constant; unavailability SHALL propagate as `null`/`NaN` to a display layer that renders it as unavailable. | Rule 3.7 | `fallback-guard` |
| **REQ-GOV-001:** A pull request SHALL NOT merge while any review thread is unresolved. Review comments SHALL be read before CI is checked, and a finding SHALL be reproduced against pre-fix code before a fix is written. | Rule 2.5 | branch protection ("Require conversation resolution") |
| **REQ-GOV-002:** Before a remediation stream is scheduled, every included issue SHALL have a GitHub-timeline candidate inventory recording candidate PR/commit, merge state, recoverability, acceptance criteria met, and remaining work. A cross-reference SHALL NOT be treated as implementation coverage without changed-file and DoD review. | PR #924 review | product-plan governance |
| **REQ-VALID-001:** Validation or calibration SHALL NOT freeze a baseline until all upstream input-semantics and replay/data-path blockers are repaired and the affected dataset is regenerated. Code may land independently when safe, but its validation result is inadmissible before those gates pass. | audit dependency review | `replay-integrity-reviewer` + model reviewer |
| **REQ-FRESH-002:** A shared read-side freshness primitive SHALL serve every current-facing consumer; overlapping stopped-writer/still-reading defects SHALL depend on that primitive rather than implementing divergent freshness checks. | #833/#863/#922 root-cause review | operations review |
| **REQ-REVIEW-001:** A required issue-level review SHALL name an available human or authenticated reviewer and record `PASS`, `PASS WITH CORRECTIONS`, or `FAIL`. Posting to an unavailable bot SHALL NOT count as delivered review. | PR #932 closure | review-feedback gate |
| **REQ-RISK-001:** Risk-control calibration or activation SHALL use a production replay path proven to exercise the control **and match live fire identities (ticker, direction, timestamp and position context)**; aggregate capped counts are insufficient. Persisted session state SHALL be restored before any default-no-op ceiling is lowered. | #818/#816/#940 | replay + trading-logic reviewers |

**Rule 3.6 in the acceptance gate.** REQ-REL-001 below requires shared live/replay fixtures.
Fixtures alone are insufficient: a feature can pass shared fixtures while the evidence that
drove its calibration came from a divergent throwaway harness — the exact incident class
Rule 3.6 exists to prevent. Both REQ-REL-001 and REQ-REPLAY-001 must hold.

## Functional and UX

- **REQ-UX-001:** Every served screen SHALL expose loading, empty, stale, permission and
  dependency-error states, and SHALL NOT convert unknown data into a neutral trading conclusion.
  *Current gaps enumerated per screen in [03](03-UI-SCREENS.md).*
- **REQ-MARKET-001:** Market context SHALL identify symbol, venue/session, as-of time, source
  and freshness.
- **REQ-SIGNAL-001:** A signal SHALL persist strategy version, inputs, configuration, levels,
  timestamps and reason codes **before** delivery.
- **REQ-PLAYBOOK-001:** A plan SHALL show entry/trigger, invalidation, targets, data time,
  evidence, and explicitly mark unavailable fields.
- **REQ-JOURNAL-001:** Journal records SHALL be scoped to an authenticated owner and support
  auditable import corrections.
- **REQ-ACCESS-001:** Core workflows SHALL be keyboard operable with labeled controls, visible
  focus and WCAG 2.1 AA contrast.

## Data, reliability, performance, observability

- **REQ-DATA-002:** Historical and replay reads SHALL enforce an as-of clock and SHALL NOT read
  future observations, revised labels or outcome-derived features.
- **REQ-DATA-003:** Every derived record SHALL carry source/as-of, pipeline, configuration,
  model/rule, artifact and code version.
- **REQ-DATA-004:** Exchange sessions, holidays, half-days and DST SHALL resolve through one
  shared calendar; and a raw-versus-adjusted corporate-action policy SHALL be explicit.
- **REQ-REL-001:** Live and replay implementations SHALL pass shared semantic parity fixtures
  before production promotion.
- **REQ-FRESH-001:** Every served dataset SHALL have an owner, expected cadence, measured age,
  alert threshold and recovery instruction.
- **REQ-PERF-001:** Interactive API p95 targets and payload bounds SHALL be defined per endpoint
  and monitored before any availability claim.
- **REQ-PERF-002:** Scheduled jobs SHALL additionally satisfy REQ-CAP-001..003. REQ-PERF-001
  governs only interactive latency; a job cannot be declared done on interactive criteria.
- **REQ-OBS-001:** Jobs SHALL emit run identity, counts, watermark, duration, error class, retry
  and terminal status.

## Security and operations

- **REQ-AUTH-001:** A non-local deployment SHALL reject unauthenticated `/api/*` requests unless
  an approved perimeter authenticator has established identity. A deploy SHALL fail when
  `AUTH_MODE` resolves to `open` outside local development.
- **REQ-AUTH-002:** `iap` mode SHALL verify the IAP identity header at the application layer
  rather than assuming the perimeter.
- **REQ-AUTH-003:** Non-`/api/` operational endpoints exposing infrastructure detail SHALL be
  gated by the same mechanism as `/api/*`, or SHALL NOT deploy on a public service.
- **REQ-AUTHZ-001:** Admin operations SHALL require a server-enforced role, compared in constant
  time; email presentation alone SHALL NOT grant privilege.
- **REQ-TENANCY-001:** User-owned rows SHALL carry an immutable owner identifier enforced on
  every access path.
- **REQ-SECRET-001:** Secrets SHALL be passed via `--set-secrets`, never `--set-env-vars`, and
  SHALL have a named rotation owner.
- **REQ-DR-001:** Cloud SQL and model/config artifacts SHALL have documented RPO/RTO, a restore
  procedure, and recurring restore evidence.
- **REQ-DEPLOY-001:** Infrastructure SHALL be reproducible from reviewed configuration; create
  and update paths SHALL converge; every scheduler target SHALL resolve to a job the same
  configuration creates.

## Model / ML

- **REQ-MODEL-001:** Promotion SHALL require point-in-time-safe training, a frozen validation set
  unseen during selection, baseline comparison, cohort metrics, calibration where probabilistic,
  and a threshold fixed in advance.
- **REQ-MODEL-002:** Runtime outputs SHALL include model/artifact/version, feature contract,
  training cutoff, as-of time and rollback target.
- **REQ-MODEL-003:** Promoted models SHALL complete shadow validation and support immediate
  rollback. **Training SHALL NOT write production as a side effect of a job completing** —
  the gate precedent is `mag_walk_forward.promotion_verdict` ([#810](https://github.com/TeneikaAskew/stocks/pull/810)).
- **REQ-LLM-001:** LLM nodes SHALL distinguish supplied facts from generated interpretation, use
  structured schemas, and SHALL NOT invent prices, stops, targets or confidence values.
- **REQ-LLM-002:** A test SHALL assert that the documented LLM node roster matches the roster
  declared in `lib/agents/orchestrator.py`, failing CI on divergence. *(Added after the same
  topology error shipped three times — see [08](08-AI-AGENT-ARCHITECTURE.md).)*

## Universal acceptance gate

A significant feature is done only when **all** hold:

1. Functional and UI/API behavior is acceptance-tested.
2. Authentication, authorization and ownership are enforced and tested.
3. Data contract, freshness and provenance are measured.
4. Loading, empty, error and stale behavior is tested (REQ-UX-001).
5. Telemetry, an alert and a runbook exist (REQ-OBS-001, REQ-FRESH-001).
6. Documentation and traceability are current — catalog row, code locus, evidence tag, review date.
7. Deployment is reproducible and reversible (REQ-DEPLOY-001).
8. **Scheduled workloads meet REQ-CAP-001..003.**
9. **Evidence was produced through a production replay path (REQ-REPLAY-001).**
10. **No review thread is unresolved (REQ-GOV-001), and issue-level review uses an available reviewer (REQ-REVIEW-001).**
11. **Candidate/recoverability inventory and upstream validation gates pass (REQ-GOV-002, REQ-VALID-001).**
12. Model-based features additionally meet REQ-MODEL-001..003 and REQ-LLM-001..002.

**Existence of code is never evidence that any of these hold.**
