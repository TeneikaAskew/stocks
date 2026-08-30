# Work Breakdown Structure

| Epic → capability | Feature | Requirement | Issue | PR evidence | Code | Test/acceptance deliverable |
|---|---|---|---|---|---|---|
| Trust foundation → data contracts | FEAT-DATA-001 | REQ-DATA-001..003 | #860–#863 | #802/#804 | `gcp`, `gcp/schema.sql`, `lib/data_loader.py` | PIT/freshness/provenance contract tests |
| Authentication → identity/perimeter | FEAT-AUTH-001 | REQ-AUTH-001, AUTHZ, TENANCY | #911 | history trace needed | `platform/api/auth.py`, UI auth, deploy | mode matrix, bypass and owner-isolation tests |
| Premarket → plan generation | FEAT-MARKET/PLAYBOOK | REQ-MARKET/PLAYBOOK | #861 | history trace needed | dashboard/playbook routers/jobs | fresh-input journey and unavailable-state E2E |
| Live intelligence → signal lifecycle | FEAT-LIVE/SIGNAL/STRAT | REQ-SIGNAL/REL | #873–#875 | #802/#804 | `lib/signals.py`, strategies, live router | shared live/replay golden fixtures |
| Options/catalysts → contextual evidence | FEAT-OPTION/CATALYST | REQ-DATA/UX | #884 | history trace needed | gamma/options/earnings modules | missing-data, timestamp and vendor-contract tests |
| Evaluation → replay/backtest | FEAT-REPLAY/REPORT | REQ-DATA-002, MODEL-001 | #813/#906 | #802/#804 | replay engines and result tables | temporal adversarial and frozen rerun evidence |
| Models → governance | FEAT-MODEL-001 | REQ-MODEL-001..003 | #909/#910 | history trace needed | research engines/artifacts/router | model card, shadow, threshold, rollback |
| AI → explanations and risk | FEAT-INSIGHT-001 | REQ-LLM-001 | #916 | #804 | `lib/agents`, insights jobs/router | schema/citation/abstention/cost evaluation |
| User outcomes → journal | FEAT-JOURNAL-001 | REQ-JOURNAL/TENANCY | TBD | history trace needed | journal router/UI/import | owner isolation and import audit tests |
| Operations → deploy/observe/recover | FEAT-OPS/DEPLOY | REQ-OBS/DR/DEPLOY | #829–#850 | #802/#804 | deploy/build/workflows/job runs | convergence, alert and restore drill evidence |

## Task template
EPIC → capability → feature ID → SHALL requirement → issue (blocker/non-blocker and dependency) → origin/evolution/remediation PR → exact code path → failing regression → implementation → unit/integration/E2E/operational proof → production verification → catalog/status update. Owner, target release, estimates and rollout remain TBD until assigned.
