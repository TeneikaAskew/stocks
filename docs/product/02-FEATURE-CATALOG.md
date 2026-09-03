# Feature Catalog

**Last reviewed:** 2026-08-31

The monitoring ledger. Every row carries the fields the [README](README.md) governance
contract promises — Owner, Status, Priority, Target Phase, Last Reviewed, Blocking Issues,
Next Action — populated with `TBD` where genuinely unknown rather than omitted.

**26 capabilities.** The same 26 IDs appear in [11](11-CODE-TRACEABILITY.md) and the
[README](README.md) master matrix; an earlier revision had 22 here and 16 there, so six
capabilities — including the P0 model and operations rows — resolved to no code locus.

| ID | Area | Feature | UI | Backend | Data | Status | Pri | Phase | Open issues | Top blockers |
|---|---|---|---|---|---|---|---|---|---|---|
| [FEAT-AUTH-001](#feat-auth-001) | Authentication | Protected application access | SignInScreen / AuthGate | middleware `auth.py`, `/api/me` | identity/config | Production but needs remediation | P0 | 1 | 8 | [#830](https://github.com/TeneikaAskew/stocks/issues/830) [#850](https://github.com/TeneikaAskew/stocks/issues/850) [#911](https://github.com/TeneikaAskew/stocks/issues/911) [#837](https://github.com/TeneikaAskew/stocks/issues/837) |
| [FEAT-WAITLIST-001](#feat-waitlist-001) | Landing / waitlist | Public entry + waitlist capture | `/` | `/api/waitlist` | `waitlist_signups` | Production | P3 | 5 | 0 | — |
| [FEAT-MARKET-001](#feat-market-001) | Market dashboard | Daily market brief + movement read | `/dashboard` | `/api/dashboard`, `/api/movement-statement` | `market_data_daily`, `premarket_analysis` | Production but needs remediation | P0 | 3 | 0 | — |
| [FEAT-LIVE-001](#feat-live-001) | Intraday monitoring | Live quotes, indicators, STRAT state | `/live` | `/api/live` | `market_data_intraday` | Production but needs remediation | P0 | 3 | 0 | — |
| [FEAT-CHART-001](#feat-chart-001) | Charting | Instrument / timeframe analysis | `/charts` | `/api/live/history`, `/api/options/*/grid` | `market_data_daily`, `market_data_intraday` | Production but needs remediation | P1 | 5 | 0 | — |
| [FEAT-OPTION-001](#feat-option-001) | Options / gamma | Flow, Greeks, GEX grid | `/options` | `/api/options`, `/api/grid` | `etf_options_snapshots`, `intraday_gex_15m`, `realtime_gex_15m` | Retest Required | P0 | 3 | 11 | [#826](https://github.com/TeneikaAskew/stocks/issues/826) [#825](https://github.com/TeneikaAskew/stocks/issues/825) [#812](https://github.com/TeneikaAskew/stocks/issues/812) [#896](https://github.com/TeneikaAskew/stocks/issues/896) |
| [FEAT-SIGNAL-001](#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | Production but needs remediation | P0 | 1 | 10 | [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#905](https://github.com/TeneikaAskew/stocks/issues/905) |
| [FEAT-PLAYBOOK-001](#feat-playbook-001) | Premarket / playbook | Structured daily setups | `/playbook` | `/api/playbook` | `premarket_analysis`, `playbook_cards` | **Broken** | P0 | 3 | 1 | [#861](https://github.com/TeneikaAskew/stocks/issues/861) |
| [FEAT-STRAT-001](#feat-strat-001) | STRAT / levels | Candle classification, FTFC, structural levels | `/charts`, `/live` | via `lib/` | `strat_levels`, `strat_combo_results` | Production but needs remediation | P0 | 1 | 4 | [#908](https://github.com/TeneikaAskew/stocks/issues/908) [#866](https://github.com/TeneikaAskew/stocks/issues/866) [#907](https://github.com/TeneikaAskew/stocks/issues/907) [#884](https://github.com/TeneikaAskew/stocks/issues/884) |
| [FEAT-IND-001](#feat-ind-001) | Indicators | RVOL, ORB, ATR, RSI, VWAP | `/live`, `/charts` | via `lib/` | `market_data_*` | Production but needs remediation | P1 | 1 | 4 | [#894](https://github.com/TeneikaAskew/stocks/issues/894) [#892](https://github.com/TeneikaAskew/stocks/issues/892) [#870](https://github.com/TeneikaAskew/stocks/issues/870) [#912](https://github.com/TeneikaAskew/stocks/issues/912) |
| [FEAT-INSIGHT-001](#feat-insight-001) | AI insights | LLM per-ticker reports + chat | `/insights` | `/api/insights` (13) | `insight_reports`, `insight_runs`, `model_routing` | Experimental | P2 | 4 | 4 | [#827](https://github.com/TeneikaAskew/stocks/issues/827) [#867](https://github.com/TeneikaAskew/stocks/issues/867) [#916](https://github.com/TeneikaAskew/stocks/issues/916) [#442](https://github.com/TeneikaAskew/stocks/issues/442) |
| [FEAT-CATALYST-001](#feat-catalyst-001) | Earnings / catalysts | Events, reactions, news, filings | `/catalysts` | `/api/catalysts`, `/api/earnings` | `earnings_*`, `economic_events`, `news_sentiment`, `sec_filings` | Production but needs remediation | P1 | 3 | 0 | — |
| [FEAT-REPORT-001](#feat-report-001) | Reports / analytics | Backtest + walk-forward results | `/reports` | `/api/analytics`, `/api/backtest` | `backtest_*`, `walk_forward_results` | Production but needs remediation | P1 | 2 | 0 | — |
| [FEAT-REPLAY-001](#feat-replay-001) | Replay / backtest engine | Point-in-time replay + evaluation | `/reports` | `/api/backtest/replay-trades` | `backtest_*`, `signal_alerts` | **Invalidated** | P0 | 2 | 21 | [#824](https://github.com/TeneikaAskew/stocks/issues/824) [#823](https://github.com/TeneikaAskew/stocks/issues/823) [#822](https://github.com/TeneikaAskew/stocks/issues/822) [#821](https://github.com/TeneikaAskew/stocks/issues/821) |
| [FEAT-MODEL-001](#feat-model-001) | Models / research | Predictive + calibration systems | `/admin` | `/api/magnitude`, `/api/admin/strat-engine` | `ticker_calibration`, `user_style_results` | **Invalidated / Failed** (mixed) | P0 | 4 | 10 | [#817](https://github.com/TeneikaAskew/stocks/issues/817) [#813](https://github.com/TeneikaAskew/stocks/issues/813) [#910](https://github.com/TeneikaAskew/stocks/issues/910) [#909](https://github.com/TeneikaAskew/stocks/issues/909) |
| [FEAT-JOURNAL-001](#feat-journal-001) | Journal / portfolio | Per-user trade record + import | `/journal` | `/api/journal` (9) | `trades`, `journal_entries` | Production but needs remediation | P1 | 5 | 3 | [#722](https://github.com/TeneikaAskew/stocks/issues/722) [#717](https://github.com/TeneikaAskew/stocks/issues/717) [#716](https://github.com/TeneikaAskew/stocks/issues/716) |
| [FEAT-ALERT-001](#feat-alert-001) | Alerts / Discord | Signal + brief delivery | — | `gcp/discord_interactions/` | `signal_alerts` | Production but needs remediation | P1 | 3 | 0 | — |
| [FEAT-ADMIN-001](#feat-admin-001) | Administration | Operator surface | `/admin` | `/api/admin` (7), `/api/config` | `model_routing` | Production but needs remediation | P2 | 6 | 0 | — |
| [FEAT-HELP-001](#feat-help-001) | Help / glossary | Term reference | `/help` | `/api/glossary/gamma` | — | Production | P3 | 5 | 0 | — |
| [FEAT-SETTINGS-001](#feat-settings-001) | Settings | Device-local appearance/layout | `/settings` | **none — `localStorage`** | **none** | Incomplete | P3 | 5 | 0 | — |
| [FEAT-DATA-001](#feat-data-001) | Data platform | Ingestion, storage, freshness | — | fetcher jobs | 64 relations — see [06](06-DATA-ARCHITECTURE.md) | Production but needs remediation | P0 | 1 | 12 | [#926](https://github.com/TeneikaAskew/stocks/issues/926) [#925](https://github.com/TeneikaAskew/stocks/issues/925) [#863](https://github.com/TeneikaAskew/stocks/issues/863) [#862](https://github.com/TeneikaAskew/stocks/issues/862) |
| [FEAT-DEPLOY-001](#feat-deploy-001) | Infrastructure / deploy | 67 jobs, 58 schedulers, Cloud Run | — | — | — | Production but needs remediation | P1 | 6 | 15 | [#835](https://github.com/TeneikaAskew/stocks/issues/835) [#834](https://github.com/TeneikaAskew/stocks/issues/834) [#833](https://github.com/TeneikaAskew/stocks/issues/833) [#831](https://github.com/TeneikaAskew/stocks/issues/831) |
| [FEAT-OPS-001](#feat-ops-001) | Operations / reliability | Freshness, telemetry, DR | `/admin` | `/api/health/freshness` | `job_runs` | Incomplete | P1 | 6 | 4 | [#922](https://github.com/TeneikaAskew/stocks/issues/922) [#920](https://github.com/TeneikaAskew/stocks/issues/920) [#930](https://github.com/TeneikaAskew/stocks/issues/930) |
| [FEAT-CICD-001](#feat-cicd-001) | CI / testing | Build, test, deploy automation | — | — | — | Production but needs remediation | P1 | 6 | 9 | [#848](https://github.com/TeneikaAskew/stocks/issues/848) [#846](https://github.com/TeneikaAskew/stocks/issues/846) [#845](https://github.com/TeneikaAskew/stocks/issues/845) [#844](https://github.com/TeneikaAskew/stocks/issues/844) |
| [FEAT-UI-001](#feat-ui-001) | Web / UI shell | Nav, shell, responsive, a11y | all | — | — | Production but needs remediation | P2 | 5 | 2 | [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) |
| [FEAT-DEBT-001](#feat-debt-001) | Technical debt | Legacy retirement | — | — | — | Retire candidate | P3 | 7 | 3 | [#917](https://github.com/TeneikaAskew/stocks/issues/917) [#841](https://github.com/TeneikaAskew/stocks/issues/841) [#921](https://github.com/TeneikaAskew/stocks/issues/921) |

## Capability records

### FEAT-AUTH-001

**Protected application access** — Authentication

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | SignInScreen / AuthGate |
| Backend | middleware `auth.py`, `/api/me` |
| Data | identity/config |
| Models | Firebase / IAP |
| Code | `platform/api/auth.py`, `platform/api/main.py:51`, `platform/src/components/auth` |
| Tests | `platform/tests/auth-gate.spec.ts`, `admin-auth.spec.ts` |
| Open issues | 8 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-auth-001-auth-security-8-open) |
| Blocking issues | [#830](https://github.com/TeneikaAskew/stocks/issues/830) [#850](https://github.com/TeneikaAskew/stocks/issues/850) [#911](https://github.com/TeneikaAskew/stocks/issues/911) [#837](https://github.com/TeneikaAskew/stocks/issues/837) [#836](https://github.com/TeneikaAskew/stocks/issues/836) [#839](https://github.com/TeneikaAskew/stocks/issues/839) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 1 |

### FEAT-WAITLIST-001

**Public entry + waitlist capture** — Landing / waitlist

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production |
| Priority | P3 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/` |
| Backend | `/api/waitlist` |
| Data | `waitlist_signups` |
| Models | — |
| Code | `platform/src/routes/LandingPage.tsx`, `platform/api/routers/waitlist.py` |
| Tests | `landing.spec.ts`, `waitlist.test.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-MARKET-001

**Daily market brief + movement read** — Market dashboard

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/dashboard` |
| Backend | `/api/dashboard`, `/api/movement-statement` |
| Data | `market_data_daily`, `premarket_analysis` |
| Models | MODEL-BRIEF-001 |
| Code | `platform/src/routes/DashboardPage.tsx`, `platform/api/routers/dashboard.py`, `lib/movement_statement.py` |
| Tests | `dashboard.spec.ts`, `movement-read.spec.ts`, `MovementRead.test.tsx` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-LIVE-001

**Live quotes, indicators, STRAT state** — Intraday monitoring

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/live` |
| Backend | `/api/live` |
| Data | `market_data_intraday` |
| Models | MODEL-IND-001, MODEL-STRAT-001 |
| Code | `platform/src/routes/LiveMarketPage.tsx`, `platform/api/routers/live.py`, `lib/indicators.py` |
| Tests | `live-market.spec.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-CHART-001

**Instrument / timeframe analysis** — Charting

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/charts` |
| Backend | `/api/live/history`, `/api/options/*/grid` |
| Data | `market_data_daily`, `market_data_intraday` |
| Models | MODEL-STRAT-001, MODEL-LEVEL-001 |
| Code | `platform/src/routes/ChartsPage.tsx`, `platform/api/routers/live.py`, `grid.py` |
| Tests | `charts-cards.spec.ts`, `phase1-charts.spec.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-OPTION-001

**Flow, Greeks, GEX grid** — Options / gamma

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Retest Required |
| Priority | P0 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/options` |
| Backend | `/api/options`, `/api/grid` |
| Data | `etf_options_snapshots`, `intraday_gex_15m`, `realtime_gex_15m` |
| Models | MODEL-GAMMA-001, MODEL-OPT-001 |
| Code | `platform/src/routes/OptionsFlowPage.tsx`, `platform/api/routers/options.py`, `grid.py`, `lib/gamma.py`, `lib/options_greeks.py` |
| Tests | `options-flow.spec.ts`, `gamma-levels.spec.ts`, `swingGridUtils.test.ts` |
| Open issues | 11 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-option-001-options-gamma-11-open) |
| Blocking issues | [#826](https://github.com/TeneikaAskew/stocks/issues/826) [#825](https://github.com/TeneikaAskew/stocks/issues/825) [#812](https://github.com/TeneikaAskew/stocks/issues/812) [#896](https://github.com/TeneikaAskew/stocks/issues/896) [#878](https://github.com/TeneikaAskew/stocks/issues/878) [#876](https://github.com/TeneikaAskew/stocks/issues/876) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-SIGNAL-001

**Signal discovery, alerting, exits** — Signals / execution

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/signals`, `/live` |
| Backend | `/api/signals` |
| Data | `signal_alerts`, `historical_signals`, `exit_config_overrides` |
| Models | MODEL-MOM-001, MODEL-MR-001, MODEL-AGREE-001, MODEL-EXIT-001 |
| Code | `lib/signals.py`, `lib/strategies/`, `gcp/signal_monitor.py`, `platform/api/routers/signals.py` |
| Tests | `signals.spec.ts`, `tests/test_signal*.py` |
| Open issues | 10 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-signal-001-signals-execution-10-open) |
| Blocking issues | [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#905](https://github.com/TeneikaAskew/stocks/issues/905) [#915](https://github.com/TeneikaAskew/stocks/issues/915) [#285](https://github.com/TeneikaAskew/stocks/issues/285) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 1 |

### FEAT-PLAYBOOK-001

**Structured daily setups** — Premarket / playbook

| Field | Value |
|---|---|
| Owner | TBD |
| Status | **Broken** |
| Priority | P0 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/playbook` |
| Backend | `/api/playbook` |
| Data | `premarket_analysis`, `playbook_cards` |
| Models | MODEL-BRIEF-001, MODEL-LEVEL-001 |
| Code | `platform/src/routes/PlaybookPage.tsx`, `platform/api/routers/playbook.py`, `gcp/premarket_brief.py`, `scripts/analysis/phase6_playbook.py` |
| Tests | `playbook.spec.ts`, `tests/test_phase6_playbook.py` |
| Open issues | 1 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-playbook-001-premarket-playbook-1-open) |
| Blocking issues | [#861](https://github.com/TeneikaAskew/stocks/issues/861) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-STRAT-001

**Candle classification, FTFC, structural levels** — STRAT / levels

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/charts`, `/live` |
| Backend | via `lib/` |
| Data | `strat_levels`, `strat_combo_results` |
| Models | MODEL-STRAT-001, MODEL-FTFC-001, MODEL-LEVEL-001 |
| Code | `lib/strat.py`, `lib/strat_levels.py`, `lib/exec_backtest/ftfc.py` |
| Tests | `tests/test_strat*.py` |
| Open issues | 4 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-strat-001-levels-strat-4-open) |
| Blocking issues | [#908](https://github.com/TeneikaAskew/stocks/issues/908) [#866](https://github.com/TeneikaAskew/stocks/issues/866) [#907](https://github.com/TeneikaAskew/stocks/issues/907) [#884](https://github.com/TeneikaAskew/stocks/issues/884) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 1 |

### FEAT-IND-001

**RVOL, ORB, ATR, RSI, VWAP** — Indicators

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/live`, `/charts` |
| Backend | via `lib/` |
| Data | `market_data_*` |
| Models | MODEL-IND-001 |
| Code | `lib/indicators.py`, `lib/signals.py` |
| Tests | `tests/test_indicators*.py` |
| Open issues | 4 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-ind-001-indicators-4-open) |
| Blocking issues | [#894](https://github.com/TeneikaAskew/stocks/issues/894) [#892](https://github.com/TeneikaAskew/stocks/issues/892) [#870](https://github.com/TeneikaAskew/stocks/issues/870) [#912](https://github.com/TeneikaAskew/stocks/issues/912) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 1 |

### FEAT-INSIGHT-001

**LLM per-ticker reports + chat** — AI insights

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Experimental |
| Priority | P2 |
| Target phase | Phase 4 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/insights` |
| Backend | `/api/insights` (13) |
| Data | `insight_reports`, `insight_runs`, `model_routing` |
| Models | 14 LLM nodes — see [08](08-AI-AGENT-ARCHITECTURE.md) |
| Code | `lib/agents/`, `platform/api/routers/insights.py`, `gcp/insight_pipeline_job.py` |
| Tests | `insights.spec.ts`, `tests/test_agents_*.py` |
| Open issues | 4 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-insight-001-ai-insights-4-open) |
| Blocking issues | [#827](https://github.com/TeneikaAskew/stocks/issues/827) [#867](https://github.com/TeneikaAskew/stocks/issues/867) [#916](https://github.com/TeneikaAskew/stocks/issues/916) [#442](https://github.com/TeneikaAskew/stocks/issues/442) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 4 |

### FEAT-CATALYST-001

**Events, reactions, news, filings** — Earnings / catalysts

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/catalysts` |
| Backend | `/api/catalysts`, `/api/earnings` |
| Data | `earnings_*`, `economic_events`, `news_sentiment`, `sec_filings` |
| Models | MODEL-EARN-001 |
| Code | `platform/api/routers/catalysts.py`, `earnings.py`, `lib/earnings_reactions.py` |
| Tests | `catalysts.spec.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-REPORT-001

**Backtest + walk-forward results** — Reports / analytics

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 2 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/reports` |
| Backend | `/api/analytics`, `/api/backtest` |
| Data | `backtest_*`, `walk_forward_results` |
| Models | MODEL-CALIB-001, MODEL-STYLE-001 |
| Code | `platform/src/routes/ReportsPage.tsx`, `platform/api/routers/backtest.py`, `analytics.py` |
| Tests | `reports.spec.ts`, `BacktesterSection.format.test.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 2 |

### FEAT-REPLAY-001

**Point-in-time replay + evaluation** — Replay / backtest engine

| Field | Value |
|---|---|
| Owner | TBD |
| Status | **Invalidated** |
| Priority | P0 |
| Target phase | Phase 2 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/reports` |
| Backend | `/api/backtest/replay-trades` |
| Data | `backtest_*`, `signal_alerts` |
| Models | — |
| Code | `lib/backtest.py`, `lib/walk_forward.py`, `lib/exec_backtest/`, `scripts/replay_signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py` |
| Tests | `replay-trainer.spec.ts`, `tests/test_backtest*.py` |
| Open issues | 21 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-replay-001-replay-backtest-evaluation-21-open) |
| Blocking issues | [#824](https://github.com/TeneikaAskew/stocks/issues/824) [#823](https://github.com/TeneikaAskew/stocks/issues/823) [#822](https://github.com/TeneikaAskew/stocks/issues/822) [#821](https://github.com/TeneikaAskew/stocks/issues/821) [#820](https://github.com/TeneikaAskew/stocks/issues/820) [#819](https://github.com/TeneikaAskew/stocks/issues/819) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 2 |

### FEAT-MODEL-001

**Predictive + calibration systems** — Models / research

| Field | Value |
|---|---|
| Owner | TBD |
| Status | **Invalidated / Failed** (mixed) |
| Priority | P0 |
| Target phase | Phase 4 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/admin` |
| Backend | `/api/magnitude`, `/api/admin/strat-engine` |
| Data | `ticker_calibration`, `user_style_results` |
| Models | see [07](07-MODEL-REGISTRY.md) |
| Code | `gcp/research/`, `lib/walk_forward.py`, `platform/api/routers/magnitude.py` |
| Tests | `tests/test_walk_forward*.py`, `tests/test_magnitude*.py` |
| Open issues | 10 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-model-001-models-research-10-open) |
| Blocking issues | [#817](https://github.com/TeneikaAskew/stocks/issues/817) [#813](https://github.com/TeneikaAskew/stocks/issues/813) [#910](https://github.com/TeneikaAskew/stocks/issues/910) [#909](https://github.com/TeneikaAskew/stocks/issues/909) [#888](https://github.com/TeneikaAskew/stocks/issues/888) [#875](https://github.com/TeneikaAskew/stocks/issues/875) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 4 |

### FEAT-JOURNAL-001

**Per-user trade record + import** — Journal / portfolio

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/journal` |
| Backend | `/api/journal` (9) |
| Data | `trades`, `journal_entries` |
| Models | MODEL-STYLE-001 |
| Code | `platform/src/routes/JournalPage.tsx`, `platform/api/routers/journal.py`, `lib/broker_import.py` |
| Tests | `journal.spec.ts`, `journal-import.spec.ts`, `journal-onestop.spec.ts` |
| Open issues | 3 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-journal-001-journal-portfolio-3-open) |
| Blocking issues | [#722](https://github.com/TeneikaAskew/stocks/issues/722) [#717](https://github.com/TeneikaAskew/stocks/issues/717) [#716](https://github.com/TeneikaAskew/stocks/issues/716) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-ALERT-001

**Signal + brief delivery** — Alerts / Discord

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | — |
| Backend | `gcp/discord_interactions/` |
| Data | `signal_alerts` |
| Models | — |
| Code | `gcp/discord_interactions/main.py`, `gcp/notifier*.py` |
| Tests | `tests/test_notifier*.py` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-ADMIN-001

**Operator surface** — Administration

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P2 |
| Target phase | Phase 6 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/admin` |
| Backend | `/api/admin` (7), `/api/config` |
| Data | `model_routing` |
| Models | — |
| Code | `platform/src/routes/AdminPage.tsx`, `platform/api/routers/admin.py` |
| Tests | `admin.spec.ts`, `admin-auth.spec.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 6 |

### FEAT-HELP-001

**Term reference** — Help / glossary

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production |
| Priority | P3 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/help` |
| Backend | `/api/glossary/gamma` |
| Data | — |
| Models | — |
| Code | `platform/src/routes/HelpPage.tsx`, `platform/api/routers/glossary.py` |
| Tests | `help.spec.ts` |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-SETTINGS-001

**Device-local appearance/layout** — Settings

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Incomplete |
| Priority | P3 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/settings` |
| Backend | **none — `localStorage`** |
| Data | **none** |
| Models | — |
| Code | `platform/src/routes/SettingsPage.tsx`, `platform/src/stores/settingsStore.ts`, `themeStore.ts` |
| Tests | **none** |
| Open issues | 0 — full list in [12](12-PR-ISSUE-TRACEABILITY.md) |
| Blocking issues | — |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-DATA-001

**Ingestion, storage, freshness** — Data platform

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | — |
| Backend | fetcher jobs |
| Data | 64 relations — see [06](06-DATA-ARCHITECTURE.md) |
| Models | — |
| Code | `gcp/fetchers/`, `gcp/schema.sql`, `lib/data_loader.py`, `gcp/database.py` |
| Tests | `tests/test_data_loader*.py`, integration suite |
| Open issues | 12 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-data-001-data-platform-12-open) |
| Blocking issues | [#926](https://github.com/TeneikaAskew/stocks/issues/926) [#925](https://github.com/TeneikaAskew/stocks/issues/925) [#863](https://github.com/TeneikaAskew/stocks/issues/863) [#862](https://github.com/TeneikaAskew/stocks/issues/862) [#828](https://github.com/TeneikaAskew/stocks/issues/828) [#927](https://github.com/TeneikaAskew/stocks/issues/927) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 1 |

### FEAT-DEPLOY-001

**67 jobs, 58 schedulers, Cloud Run** — Infrastructure / deploy

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 6 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | — |
| Backend | — |
| Data | — |
| Models | — |
| Code | `gcp/deploy.sh`, `platform/deploy.sh`, `gcp/cloudbuild/` |
| Tests | static checks only |
| Open issues | 15 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-deploy-001-infrastructure-deploy-15-open) |
| Blocking issues | [#835](https://github.com/TeneikaAskew/stocks/issues/835) [#834](https://github.com/TeneikaAskew/stocks/issues/834) [#833](https://github.com/TeneikaAskew/stocks/issues/833) [#831](https://github.com/TeneikaAskew/stocks/issues/831) [#829](https://github.com/TeneikaAskew/stocks/issues/829) [#859](https://github.com/TeneikaAskew/stocks/issues/859) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 6 |

### FEAT-OPS-001

**Freshness, telemetry, DR** — Operations / reliability

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Incomplete |
| Priority | P1 |
| Target phase | Phase 6 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/admin` |
| Backend | `/api/health/freshness` |
| Data | `job_runs` |
| Models | — |
| Code | `gcp/freshness_watchdog.py`, `gcp/notifier*.py`, `platform/api/routers/health.py` |
| Tests | `data-pipeline-status.spec.ts` deleted in #957: widget guard ported in [solyra#29](https://github.com/TeneikaAskew/solyra/pull/29); live `/api/health/freshness` tests tracked in [#971](https://github.com/TeneikaAskew/stocks/issues/971) |
| Open issues | 4 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-ops-001-operations-reliability-4-open) |
| Blocking issues | [#922](https://github.com/TeneikaAskew/stocks/issues/922) [#920](https://github.com/TeneikaAskew/stocks/issues/920) [#930](https://github.com/TeneikaAskew/stocks/issues/930) [#944](https://github.com/TeneikaAskew/stocks/issues/944) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 6 |

### FEAT-CICD-001

**Build, test, deploy automation** — CI / testing

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 6 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | — |
| Backend | — |
| Data | — |
| Models | — |
| Code | `.github/workflows/`, `gcp/cloudbuild/` |
| Tests | 230 python tests, 29 e2e, 27 vitest |
| Open issues | 9 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-cicd-001-ci-testing-9-open) |
| Blocking issues | [#848](https://github.com/TeneikaAskew/stocks/issues/848) [#846](https://github.com/TeneikaAskew/stocks/issues/846) [#845](https://github.com/TeneikaAskew/stocks/issues/845) [#844](https://github.com/TeneikaAskew/stocks/issues/844) [#843](https://github.com/TeneikaAskew/stocks/issues/843) [#847](https://github.com/TeneikaAskew/stocks/issues/847) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 6 |

### FEAT-UI-001

**Nav, shell, responsive, a11y** — Web / UI shell

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P2 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | all |
| Backend | — |
| Data | — |
| Models | — |
| Code | [solyra `src/App.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/App.tsx), solyra `src/components/` — moved out of stocks in the #957 split |
| Tests | [solyra `tests/navigation.spec.ts`](https://github.com/TeneikaAskew/solyra/blob/main/tests/navigation.spec.ts) |
| Open issues | 2, tracked in solyra since 2026-09-03 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-ui-001-web-ui-2-open) |
| Blocking issues | [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-DEBT-001

**Legacy retirement** — Technical debt

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Retire candidate |
| Priority | P3 |
| Target phase | Phase 7 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-08-30 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | — |
| Backend | — |
| Data | — |
| Models | — |
| Code | `scripts/`, archived apps |
| Tests | — |
| Open issues | 3 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-debt-001-technical-debt-3-open) |
| Blocking issues | [#917](https://github.com/TeneikaAskew/stocks/issues/917) [#841](https://github.com/TeneikaAskew/stocks/issues/841) [#921](https://github.com/TeneikaAskew/stocks/issues/921) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 7 |

