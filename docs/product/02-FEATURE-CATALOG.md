# Feature Catalog

This is the monitoring ledger; target claims are proposals.

| ID | Area | Feature | UI | Backend | Data | Model/rule | Status | Priority | Blocking issue |
|---|---|---|---|---|---|---|---|---|---|
| [FEAT-AUTH-001](#feat-auth-001) | Authentication | Protected application access | Sign-in state | /api/me | identity/config | Firebase or IAP | Production but needs remediation | P0 | [#911](https://github.com/TeneikaAskew/stocks/issues/911) |
| [FEAT-MARKET-001](#feat-market-001) | Market dashboard | Current market brief | Dashboard | /api/dashboard | market_data_daily; premarket_analysis | brief bias; movement statement | Production but needs remediation | P0 | [#861](https://github.com/TeneikaAskew/stocks/issues/861) |
| [FEAT-LIVE-001](#feat-live-001) | Intraday monitoring | Live quotes, indicators, and state | Live | /api/live | market_data_intraday | indicators; STRAT | Production but needs remediation | P0 | [#873](https://github.com/TeneikaAskew/stocks/issues/873) |
| [FEAT-CHART-001](#feat-chart-001) | Charting | Instrument/timeframe chart analysis | Charts | /api/live/history | market_data_daily; market_data_intraday | STRAT; levels | Incomplete | P1 | TBD |
| [FEAT-OPTION-001](#feat-option-001) | Options/Gamma | Options flow, Greeks, GEX | Options Flow | /api/options; /api/grid | options/greeks/gex domains | gamma; flow direction | Production but needs remediation | P0 | [#884](https://github.com/TeneikaAskew/stocks/issues/884) |
| [FEAT-SIGNAL-001](#feat-signal-001) | Signals | Signal discovery and monitoring | Signals; Live | /api/signals | signal_alerts; historical_signals | momentum; mean reversion; agreement | Production but needs remediation | P0 | [#874](https://github.com/TeneikaAskew/stocks/issues/874) |
| [FEAT-PLAYBOOK-001](#feat-playbook-001) | Trade planning | Premarket playbook cards | Playbook | /api/playbook | playbook_cards; premarket_analysis | brief bias; levels | Broken | P0 | [#861](https://github.com/TeneikaAskew/stocks/issues/861) |
| [FEAT-REPORT-001](#feat-report-001) | Reporting | Historical and generated reports | Reports | /api/analytics; /api/backtest | backtest_reports; signal_metrics | evaluation metrics | Experimental | P1 | [#906](https://github.com/TeneikaAskew/stocks/issues/906) |
| [FEAT-JOURNAL-001](#feat-journal-001) | Journal | Record/import/review trades | Journal | /api/journal | journal_entries; trades | broker import | Incomplete | P1 | TBD |
| [FEAT-INSIGHT-001](#feat-insight-001) | AI insights | Multi-agent market insight | AI Insights | /api/insights | insight_runs; insight_reports; model_routing | LLM agent graph | Experimental | P0 | [#916](https://github.com/TeneikaAskew/stocks/issues/916) |
| [FEAT-CATALYST-001](#feat-catalyst-001) | Catalysts | Earnings and event context | Catalysts | /api/catalysts; /api/earnings | earnings; events; SEC; news | earnings reactions | Incomplete | P1 | TBD |
| [FEAT-ADMIN-001](#feat-admin-001) | Administration | Model/config/STRAT operations | Admin | /api/admin; /api/config | routing; calibration; config | model routing | Production but needs remediation | P0 | [#911](https://github.com/TeneikaAskew/stocks/issues/911) |
| [FEAT-SETTINGS-001](#feat-settings-001) | Configuration | User display/preferences | Settings | /api/config | watchlists; config | None | Incomplete | P2 | TBD |
| [FEAT-HELP-001](#feat-help-001) | Help | Glossary and product explanation | Help | /api/glossary | static glossary | None | Production | P2 | TBD |
| [FEAT-WAITLIST-001](#feat-waitlist-001) | Public site | Landing and waitlist | Landing | /api/waitlist | waitlist_signups | None | Production but needs remediation | P2 | TBD |
| [FEAT-STRAT-001](#feat-strat-001) | Structural analysis | STRAT/FTFC and levels | Live; Charts; Playbook | shared domain logic | market bars; strat_levels | STRAT; FTFC; level state | Production but needs remediation | P0 | [#875](https://github.com/TeneikaAskew/stocks/issues/875) |
| [FEAT-REPLAY-001](#feat-replay-001) | Replay | Point-in-time replay | Reports/Admin | /api/backtest | historical_signals; backtest tables | strategies; execution simulation | Invalidated | P0 | [#813](https://github.com/TeneikaAskew/stocks/issues/813) |
| [FEAT-MODEL-001](#feat-model-001) | Predictive models | Magnitude/direction/meta models | Insights/Admin | /api/magnitude | predictions/artifacts | magnitude; direction; breakout | Retest Required | P0 | [#910](https://github.com/TeneikaAskew/stocks/issues/910) |
| [FEAT-ALERT-001](#feat-alert-001) | Notifications | Discord signal/insight delivery | External Discord | Discord interactions/jobs | signal_alerts; insight_reports | signal rules | Production but needs remediation | P1 | TBD |
| [FEAT-DATA-001](#feat-data-001) | Data platform | Market/options/event ingestion | All data surfaces | Cloud Run jobs | all analytical domains | validation/freshness rules | Production but needs remediation | P0 | [#860](https://github.com/TeneikaAskew/stocks/issues/860) |
| [FEAT-OPS-001](#feat-ops-001) | Operations | Freshness, job and failure monitoring | Admin | /api/health | job_runs; domain timestamps | freshness policy | Incomplete | P0 | [#862](https://github.com/TeneikaAskew/stocks/issues/862) |
| [FEAT-DEPLOY-001](#feat-deploy-001) | Delivery | Build/deploy/schedule services | None | Cloud Build/Run | Cloud SQL/GCS/Secret Manager | None | Production but needs remediation | P0 | [#829](https://github.com/TeneikaAskew/stocks/issues/829) |

## FEAT-AUTH-001 — Protected application access
**Product area:** Authentication · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #911 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs protected application access with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Sign-in state**, **/api/me**, data **identity/config**, and model/rule **Firebase or IAP**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-MARKET-001 — Current market brief
**Product area:** Market dashboard · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #861 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs current market brief with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Dashboard**, **/api/dashboard**, data **market_data_daily; premarket_analysis**, and model/rule **brief bias; movement statement**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-LIVE-001 — Live quotes, indicators, and state
**Product area:** Intraday monitoring · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #873 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs live quotes, indicators, and state with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Live**, **/api/live**, data **market_data_intraday**, and model/rule **indicators; STRAT**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-CHART-001 — Instrument/timeframe chart analysis
**Product area:** Charting · **Owner:** TBD · **Status / Production status:** Incomplete · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P1 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs instrument/timeframe chart analysis with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Charts**, **/api/live/history**, data **market_data_daily; market_data_intraday**, and model/rule **STRAT; levels**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-OPTION-001 — Options flow, Greeks, GEX
**Product area:** Options/Gamma · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #884 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs options flow, greeks, gex with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Options Flow**, **/api/options; /api/grid**, data **options/greeks/gex domains**, and model/rule **gamma; flow direction**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-SIGNAL-001 — Signal discovery and monitoring
**Product area:** Signals · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #874 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs signal discovery and monitoring with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Signals; Live**, **/api/signals**, data **signal_alerts; historical_signals**, and model/rule **momentum; mean reversion; agreement**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-PLAYBOOK-001 — Premarket playbook cards
**Product area:** Trade planning · **Owner:** TBD · **Status / Production status:** Broken · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #861 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs premarket playbook cards with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Playbook**, **/api/playbook**, data **playbook_cards; premarket_analysis**, and model/rule **brief bias; levels**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-REPORT-001 — Historical and generated reports
**Product area:** Reporting · **Owner:** TBD · **Status / Production status:** Experimental · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P1 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #906 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs historical and generated reports with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Reports**, **/api/analytics; /api/backtest**, data **backtest_reports; signal_metrics**, and model/rule **evaluation metrics**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-JOURNAL-001 — Record/import/review trades
**Product area:** Journal · **Owner:** TBD · **Status / Production status:** Incomplete · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P1 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs record/import/review trades with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Journal**, **/api/journal**, data **journal_entries; trades**, and model/rule **broker import**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-INSIGHT-001 — Multi-agent market insight
**Product area:** AI insights · **Owner:** TBD · **Status / Production status:** Experimental · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #916 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs multi-agent market insight with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **AI Insights**, **/api/insights**, data **insight_runs; insight_reports; model_routing**, and model/rule **LLM agent graph**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-CATALYST-001 — Earnings and event context
**Product area:** Catalysts · **Owner:** TBD · **Status / Production status:** Incomplete · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P1 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs earnings and event context with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Catalysts**, **/api/catalysts; /api/earnings**, data **earnings; events; SEC; news**, and model/rule **earnings reactions**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-ADMIN-001 — Model/config/STRAT operations
**Product area:** Administration · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #911 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A platform operator needs model/config/strat operations with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Admin**, **/api/admin; /api/config**, data **routing; calibration; config**, and model/rule **model routing**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-SETTINGS-001 — User display/preferences
**Product area:** Configuration · **Owner:** TBD · **Status / Production status:** Incomplete · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P2 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs user display/preferences with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Settings**, **/api/config**, data **watchlists; config**, and model/rule **None**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-HELP-001 — Glossary and product explanation
**Product area:** Help · **Owner:** TBD · **Status / Production status:** Production · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P2 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs glossary and product explanation with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Help**, **/api/glossary**, data **static glossary**, and model/rule **None**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-WAITLIST-001 — Landing and waitlist
**Product area:** Public site · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P2 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs landing and waitlist with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Landing**, **/api/waitlist**, data **waitlist_signups**, and model/rule **None**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-STRAT-001 — STRAT/FTFC and levels
**Product area:** Structural analysis · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #875 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs strat/ftfc and levels with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Live; Charts; Playbook**, **shared domain logic**, data **market bars; strat_levels**, and model/rule **STRAT; FTFC; level state**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-REPLAY-001 — Point-in-time replay
**Product area:** Replay · **Owner:** TBD · **Status / Production status:** Invalidated · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #813 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs point-in-time replay with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Reports/Admin**, **/api/backtest**, data **historical_signals; backtest tables**, and model/rule **strategies; execution simulation**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-MODEL-001 — Magnitude/direction/meta models
**Product area:** Predictive models · **Owner:** TBD · **Status / Production status:** Retest Required · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #910 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs magnitude/direction/meta models with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Insights/Admin**, **/api/magnitude**, data **predictions/artifacts**, and model/rule **magnitude; direction; breakout**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-ALERT-001 — Discord signal/insight delivery
**Product area:** Notifications · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P1 · **Target phase:** 3–5 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** TBD · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A trader needs discord signal/insight delivery with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **External Discord**, **Discord interactions/jobs**, data **signal_alerts; insight_reports**, and model/rule **signal rules**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-DATA-001 — Market/options/event ingestion
**Product area:** Data platform · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #860 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A platform operator needs market/options/event ingestion with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **All data surfaces**, **Cloud Run jobs**, data **all analytical domains**, and model/rule **validation/freshness rules**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-OPS-001 — Freshness, job and failure monitoring
**Product area:** Operations · **Owner:** TBD · **Status / Production status:** Incomplete · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #862 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A platform operator needs freshness, job and failure monitoring with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **Admin**, **/api/health**, data **job_runs; domain timestamps**, and model/rule **freshness policy**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.

## FEAT-DEPLOY-001 — Build/deploy/schedule services
**Product area:** Delivery · **Owner:** TBD · **Status / Production status:** Production but needs remediation · **Reliability:** Not fully evidenced · **Evidence:** VERIFIED — CODE; audit qualification required · **Priority:** P0 · **Target phase:** 1 · **Target release:** TBD · **Last reviewed:** 2026-08-30 · **Blocking issues:** #829 · **Relevant PR:** UNKNOWN / NEEDS HISTORY TRACE · **Next action:** satisfy the reliability gate.

**User problem/story:** A platform operator needs build/deploy/schedule services with explicit evidence and failure state so decisions are not based on stale or implicit data.
**Current behavior:** Implemented through **None**, **Cloud Build/Run**, data **Cloud SQL/GCS/Secret Manager**, and model/rule **None**; existence does not establish production trust.
**Target behavior:** Point-in-time-safe, authenticated where applicable, observable, explainable, and parity-tested behavior.
**Infrastructure/config/auth:** Cloud Run/FastAPI/Cloud SQL as applicable; protected app shell except public landing; flags/environment are enumerated in infrastructure/security documents.
**Code/tests:** See [code traceability](11-CODE-TRACEABILITY.md) and repository tests; missing feature-level proof remains a gap.
**Acceptance criteria:** universal gate in [requirements](01-PRODUCT-REQUIREMENTS.md), plus fresh identified inputs, explicit unavailable state, versioned output, authorization, telemetry, rollback/recovery, and a linked regression test.
**Dependencies/risks:** data freshness, schema contract, authentication/ownership, deployment reproducibility; principal risk is presenting implemented but unvalidated behavior as trustworthy.
