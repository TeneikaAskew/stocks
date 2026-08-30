# Dependency-Driven Roadmap

Dates/releases/owners are TBD. Status is planning status, not a production claim.

| Phase | Feature IDs | Blocking issues | Dependencies | Expected outcome | Acceptance gate/status |
|---|---|---|---|---|---|
| 0 Baseline & Governance | all | #802/#804 findings | catalog/evidence owners | canonical inventory and quarantine list | traceability completeness; In progress — **1 of 105 canonical issues completed (#818, 2026-08-30)** |
| 1 Correctness Foundation | DATA, SIGNAL, STRAT, AUTH | #860, #873–#875, #911 | explicit contracts and identity | no silent/fail-open decision paths | shared regression + deployment guard; Planned |
| 2 Data/Replay/Evaluation Trust | DATA, REPLAY, REPORT | #813, #817, #884, #888, #890, #906 | Phase 1 clock/provenance | PIT-safe replay and valid cohorts | independent temporal audit/frozen rerun; Planned |
| 3 Core Product Reliability | MARKET, LIVE, PLAYBOOK, OPTION, ALERT | #861–#863 | Phases 1–2, freshness | dependable plan-to-alert workflow | journey SLO/error/recovery evidence; Planned |
| 4 Model Validation | MODEL, INSIGHT | #909, #910, #916 | valid replay/evaluation | retain/promote/pause decisions | promotion criteria + shadow + rollback; Planned |
| 5 Product UX Completion | UI, JOURNAL, SETTINGS, CATALYST | TBD | reliable APIs/ownership | coherent accessible states/workflow | E2E/accessibility/tenancy tests; Planned |
| 6 Operational Hardening | OPS, DEPLOY, AUTH | #829–#850 | owned components | reproducible, monitored, recoverable runtime | drift-free deploy and restore drill; Planned |
| 7 Production Expansion | selected proven features | PRODUCT DECISION REQUIRED | all gates | bounded expansion | explicit go-live review; Planned |

## Recommended next 10 priorities
1. Remove silent-empty and unresolved-configuration behavior from decision-critical paths.
2. Quarantine leaked or otherwise untrustworthy replay/model artifacts.
3. Establish replay/live clock, session, calculation and persistence parity.
4. Correct signal, structural level, stop and exit semantics.
5. Persist complete data/model/configuration/code decision provenance.
6. Make evaluation cohort-aware, baseline-compared, calibrated and promotion-safe.
7. Fail closed on authentication outside explicitly local deployments.
8. Cover every served and decision-critical dataset with freshness ownership/alerts.
9. Replace schema/deployment convergence sprawl with ordered reproducible configuration.
10. Validate in shadow or pause model/LLM outputs lacking point-in-time-safe evidence.

## Delivered against this roadmap (2026-08-30)

| Item | Phase | Evidence |
|---|---|---|
| #818 — daily-trade cap engages in replay | 2 Data/Replay/Evaluation Trust | #934 merged `dd4421b`, image rebuilt, replay verified: 15 fires vs a live 15, exact parity; the previously unquantified inflation factor measured at **42×** |
| #816 mechanism — emergency exposure ceiling | 3 Core Product Reliability | #933 merged `8eccde7`; **defaults are a proven no-op**, so this is mechanism only and #816 remains open |

Replay parity was Phase 2's gating property, so #818's closure is the first roadmap gate discharged with production evidence rather than planning status. It also discharges the #924 manifest's PR-E prerequisite (*#818 in PR-F merged **and deployed***), which matters because the merge alone would not have: the Cloud Run job keeps executing the previous image until rebuilt.

**New blocking dependency:** [#940](https://github.com/TeneikaAskew/stocks/issues/940) gates any calibration of the #933 ceilings and therefore gates the risk-control portion of Phase 3. Lowering a ceiling before #940 lands yields a control that opens on process restart.

## Product-development dependencies
Foundation trust blocks model validation; model validation blocks actionable intelligence claims; identity/tenancy blocks multi-user journal/config; data freshness blocks every surfaced conclusion; reproducible deploy/DR blocks production expansion.
