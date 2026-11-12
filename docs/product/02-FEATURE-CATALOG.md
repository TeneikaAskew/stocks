# Feature Catalog

**Last reviewed:** 2026-08-31 · **Last scanned:** 2026-10-20 · **Owner:** TBD

The monitoring ledger. Every row carries the fields the [README](README.md) governance
contract promises — Owner, Status, Priority, Target Phase, Last Reviewed, Blocking Issues,
Next Action — populated with `TBD` where genuinely unknown rather than omitted.

**26 capabilities.** The same 26 IDs appear in [11](11-CODE-TRACEABILITY.md) and the
[README](README.md) master matrix; an earlier revision had 22 here and 16 there, so six
capabilities — including the P0 model and operations rows — resolved to no code locus.

| ID | Area | Feature | UI | Backend | Data | Status | Pri | Phase | Open issues | Top blockers |
|---|---|---|---|---|---|---|---|---|---|---|
| [FEAT-AUTH-001](#feat-auth-001) | Authentication | Protected application access | SignInScreen / AuthGate | middleware `auth.py`, `/api/me` | identity/config | Production but needs remediation | P0 | 1 | 13 | [#830](https://github.com/TeneikaAskew/stocks/issues/830) [#850](https://github.com/TeneikaAskew/stocks/issues/850) [#911](https://github.com/TeneikaAskew/stocks/issues/911) [#836](https://github.com/TeneikaAskew/stocks/issues/836) |
| [FEAT-WAITLIST-001](#feat-waitlist-001) | Landing / waitlist | Public entry + waitlist capture | `/` | `/api/waitlist` | `waitlist_signups` | Production | P3 | 5 | 0 | — |
| [FEAT-MARKET-001](#feat-market-001) | Market dashboard | Daily market brief + movement read | `/dashboard` | `/api/dashboard`, `/api/movement-statement` | `market_data_daily`, `premarket_analysis` | Production but needs remediation | P0 | 3 | 14 | [solyra#84](https://github.com/TeneikaAskew/solyra/issues/84) [#1218](https://github.com/TeneikaAskew/stocks/issues/1218) [#1222](https://github.com/TeneikaAskew/stocks/issues/1222) [#1266](https://github.com/TeneikaAskew/stocks/issues/1266) |
| [FEAT-LIVE-001](#feat-live-001) | Intraday monitoring | Live quotes, indicators, STRAT state | `/live` | `/api/live` | `market_data_intraday` | Production but needs remediation | P0 | 3 | 20 | [solyra#75](https://github.com/TeneikaAskew/solyra/issues/75) [#1272](https://github.com/TeneikaAskew/stocks/issues/1272) [#1273](https://github.com/TeneikaAskew/stocks/issues/1273) [#1274](https://github.com/TeneikaAskew/stocks/issues/1274) |
| [FEAT-CHART-001](#feat-chart-001) | Charting | Instrument / timeframe analysis | `/charts` | `/api/live/history`, `/api/options/*/grid` | `market_data_daily`, `market_data_intraday` | Production but needs remediation | P1 | 5 | 21 | [#1257](https://github.com/TeneikaAskew/stocks/issues/1257) [#1258](https://github.com/TeneikaAskew/stocks/issues/1258) [solyra#85](https://github.com/TeneikaAskew/solyra/issues/85) [solyra#86](https://github.com/TeneikaAskew/solyra/issues/86) |
| [FEAT-OPTION-001](#feat-option-001) | Options / gamma | Flow, Greeks, GEX grid | `/options` | `/api/options`, `/api/grid` | `etf_options_snapshots`, `intraday_gex_15m`, `realtime_gex_15m` | Retest Required | P0 | 3 | 33 | [#812](https://github.com/TeneikaAskew/stocks/issues/812) [#826](https://github.com/TeneikaAskew/stocks/issues/826) [#871](https://github.com/TeneikaAskew/stocks/issues/871) [#872](https://github.com/TeneikaAskew/stocks/issues/872) |
| [FEAT-SIGNAL-001](#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | Production but needs remediation | P0 | 1 | 25 | [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#1206](https://github.com/TeneikaAskew/stocks/issues/1206) |
| [FEAT-PLAYBOOK-001](#feat-playbook-001) | Premarket / playbook | Structured daily setups | `/playbook` | `/api/playbook` | `premarket_analysis`, `playbook_cards` | Production but needs remediation | P0 | 3 | 19 | [solyra#112](https://github.com/TeneikaAskew/solyra/issues/112) [#1304](https://github.com/TeneikaAskew/stocks/issues/1304) [#1305](https://github.com/TeneikaAskew/stocks/issues/1305) [#1306](https://github.com/TeneikaAskew/stocks/issues/1306) |
| [FEAT-STRAT-001](#feat-strat-001) | STRAT / levels | Candle classification, FTFC, structural levels | `/charts`, `/live` | via `lib/` | `strat_levels`, `strat_combo_results`, `level_param_policy`, `ticker_level_params` | Production but needs remediation | P0 | 1 | 5 | [#866](https://github.com/TeneikaAskew/stocks/issues/866) [#908](https://github.com/TeneikaAskew/stocks/issues/908) [#907](https://github.com/TeneikaAskew/stocks/issues/907) [#884](https://github.com/TeneikaAskew/stocks/issues/884) |
| [FEAT-IND-001](#feat-ind-001) | Indicators | RVOL, ORB, ATR, RSI, VWAP | `/live`, `/charts` | via `lib/` | `market_data_*` | Production but needs remediation | P1 | 1 | 5 | [#870](https://github.com/TeneikaAskew/stocks/issues/870) [#892](https://github.com/TeneikaAskew/stocks/issues/892) [#894](https://github.com/TeneikaAskew/stocks/issues/894) [#912](https://github.com/TeneikaAskew/stocks/issues/912) |
| [FEAT-INSIGHT-001](#feat-insight-001) | AI insights | LLM per-ticker reports + chat | `/insights` | `/api/insights` (13) | `insight_reports`, `insight_runs`, `model_routing` | Experimental | P2 | 4 | 31 | [#827](https://github.com/TeneikaAskew/stocks/issues/827) [#867](https://github.com/TeneikaAskew/stocks/issues/867) [#1215](https://github.com/TeneikaAskew/stocks/issues/1215) [#1216](https://github.com/TeneikaAskew/stocks/issues/1216) |
| [FEAT-CATALYST-001](#feat-catalyst-001) | Earnings / catalysts | Events, reactions, news, filings | `/catalysts` | `/api/catalysts`, `/api/earnings` | `earnings_*`, `economic_events`, `news_sentiment`, `sec_filings` | Production but needs remediation | P1 | 3 | 19 | [#1223](https://github.com/TeneikaAskew/stocks/issues/1223) [#1268](https://github.com/TeneikaAskew/stocks/issues/1268) [#1269](https://github.com/TeneikaAskew/stocks/issues/1269) [#1270](https://github.com/TeneikaAskew/stocks/issues/1270) |
| [FEAT-REPORT-001](#feat-report-001) | Reports / analytics | Backtest + walk-forward results | `/reports` | `/api/analytics`, `/api/backtest` | `backtest_*`, `walk_forward_results` | Production but needs remediation | P1 | 2 | 9 | [#1278](https://github.com/TeneikaAskew/stocks/issues/1278) [#1311](https://github.com/TeneikaAskew/stocks/issues/1311) [solyra#205](https://github.com/TeneikaAskew/solyra/issues/205) [solyra#206](https://github.com/TeneikaAskew/solyra/issues/206) |
| [FEAT-REPLAY-001](#feat-replay-001) | Replay / backtest engine | Point-in-time replay + evaluation | `/reports` | `/api/backtest/replay-trades` | `backtest_*`, `signal_alerts` | **Invalidated** | P0 | 2 | 17 | [#814](https://github.com/TeneikaAskew/stocks/issues/814) [#819](https://github.com/TeneikaAskew/stocks/issues/819) [#821](https://github.com/TeneikaAskew/stocks/issues/821) [#822](https://github.com/TeneikaAskew/stocks/issues/822) |
| [FEAT-MODEL-001](#feat-model-001) | Models / research | Predictive + calibration systems | `/admin` | `/api/magnitude`, `/api/admin/strat-engine` | `ticker_calibration`, `user_style_results` | **Invalidated / Failed** (mixed) | P0 | 4 | 11 | [#813](https://github.com/TeneikaAskew/stocks/issues/813) [#817](https://github.com/TeneikaAskew/stocks/issues/817) [#874](https://github.com/TeneikaAskew/stocks/issues/874) [#875](https://github.com/TeneikaAskew/stocks/issues/875) |
| [FEAT-JOURNAL-001](#feat-journal-001) | Journal / portfolio | Per-user trade record + import | `/journal` | `/api/journal` (9) | `trades`, `journal_entries` | Production but needs remediation | P1 | 5 | 20 | [#1219](https://github.com/TeneikaAskew/stocks/issues/1219) [#1263](https://github.com/TeneikaAskew/stocks/issues/1263) [#1264](https://github.com/TeneikaAskew/stocks/issues/1264) [#1220](https://github.com/TeneikaAskew/stocks/issues/1220) |
| [FEAT-ALERT-001](#feat-alert-001) | Alerts / Discord | Signal + brief delivery | — | `gcp/discord_interactions/` | `signal_alerts` | Production but needs remediation | P1 | 3 | 0 | — |
| [FEAT-ADMIN-001](#feat-admin-001) | Administration | Operator surface | `/admin` | `/api/admin` (12), `/api/config` | `model_routing` | Production but needs remediation | P2 | 6 | 21 | [#1221](https://github.com/TeneikaAskew/stocks/issues/1221) [#1265](https://github.com/TeneikaAskew/stocks/issues/1265) [solyra#114](https://github.com/TeneikaAskew/solyra/issues/114) [#1316](https://github.com/TeneikaAskew/stocks/issues/1316) |
| [FEAT-HELP-001](#feat-help-001) | Help / glossary | Term reference | `/help` | `/api/glossary/gamma` | — | Production | P3 | 5 | 9 | [#1336](https://github.com/TeneikaAskew/stocks/issues/1336) [solyra#221](https://github.com/TeneikaAskew/solyra/issues/221) [solyra#222](https://github.com/TeneikaAskew/solyra/issues/222) [solyra#223](https://github.com/TeneikaAskew/solyra/issues/223) |
| [FEAT-SETTINGS-001](#feat-settings-001) | Settings | Account-backed appearance, trading defaults and profile | `/settings` | `/api/me/preferences`, `/api/me/profile` | `user_preferences`, `user_profile` | Production but needs remediation | P3 | 5 | 13 | [solyra#117](https://github.com/TeneikaAskew/solyra/issues/117) [solyra#119](https://github.com/TeneikaAskew/solyra/issues/119) [solyra#121](https://github.com/TeneikaAskew/solyra/issues/121) [#1322](https://github.com/TeneikaAskew/stocks/issues/1322) |
| [FEAT-DATA-001](#feat-data-001) | Data platform | Ingestion, storage, freshness | — | fetcher jobs | 64 relations — see [06](06-DATA-ARCHITECTURE.md) | Production but needs remediation | P0 | 1 | 21 | [#925](https://github.com/TeneikaAskew/stocks/issues/925) [#926](https://github.com/TeneikaAskew/stocks/issues/926) [#828](https://github.com/TeneikaAskew/stocks/issues/828) [#862](https://github.com/TeneikaAskew/stocks/issues/862) |
| [FEAT-DEPLOY-001](#feat-deploy-001) | Infrastructure / deploy | 76 jobs, 66 schedulers, Cloud Run | — | — | — | Production but needs remediation | P1 | 6 | 15 | [#834](https://github.com/TeneikaAskew/stocks/issues/834) [#835](https://github.com/TeneikaAskew/stocks/issues/835) [#832](https://github.com/TeneikaAskew/stocks/issues/832) [#851](https://github.com/TeneikaAskew/stocks/issues/851) |
| [FEAT-OPS-001](#feat-ops-001) | Operations / reliability | Freshness, telemetry, DR | `/admin` | `/api/health/freshness` | `job_runs` | Incomplete | P1 | 6 | 11 | [#922](https://github.com/TeneikaAskew/stocks/issues/922) [#1052](https://github.com/TeneikaAskew/stocks/issues/1052) [#1066](https://github.com/TeneikaAskew/stocks/issues/1066) [#1067](https://github.com/TeneikaAskew/stocks/issues/1067) |
| [FEAT-CICD-001](#feat-cicd-001) | CI / testing | Build, test, deploy automation | — | — | — | Production but needs remediation | P1 | 6 | 12 | [#844](https://github.com/TeneikaAskew/stocks/issues/844) [#845](https://github.com/TeneikaAskew/stocks/issues/845) [#846](https://github.com/TeneikaAskew/stocks/issues/846) [#848](https://github.com/TeneikaAskew/stocks/issues/848) |
| [FEAT-UI-001](#feat-ui-001) | Web / UI shell | Nav, shell, responsive, a11y | all | — | — | Production but needs remediation | P2 | 5 | 2 | [solyra#135](https://github.com/TeneikaAskew/solyra/issues/135) [solyra#95](https://github.com/TeneikaAskew/solyra/issues/95) |
| [FEAT-DEBT-001](#feat-debt-001) | Technical debt | Legacy retirement | — | — | — | Retire candidate | P3 | 7 | 11 | [#917](https://github.com/TeneikaAskew/stocks/issues/917) [#1137](https://github.com/TeneikaAskew/stocks/issues/1137) [#921](https://github.com/TeneikaAskew/stocks/issues/921) [#1227](https://github.com/TeneikaAskew/stocks/issues/1227) |

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
| Last reviewed | 2026-10-10 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | SignInScreen / AuthGate |
| Backend | middleware `auth.py`, `/api/me` |
| Data | identity/config |
| Models | Firebase / IAP |
| Code | `platform/api/auth.py`, `platform/api/main.py:51`, `platform/src/components/auth` |
| Tests | [solyra `tests/shared/auth-gate.spec.ts`](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/auth-gate.spec.ts), [solyra `tests/admin/admin-auth.spec.ts`](https://github.com/TeneikaAskew/solyra/blob/main/tests/admin/admin-auth.spec.ts) (moved in the #957 split); `tests/api/test_platform_auth.py` (refuses a Firebase token whose email is not verified: 403 on gated routes, no identity on `/api/me`) and `tests/api/test_dev_page_auth.py` (`/dev` absent in firebase mode, IAP header required in iap mode) ([#1360](https://github.com/TeneikaAskew/stocks/pull/1360)) |
| Open issues | 13 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-auth-001--auth--security-13-open) |
| Blocking issues | [#830](https://github.com/TeneikaAskew/stocks/issues/830) [#850](https://github.com/TeneikaAskew/stocks/issues/850) [#911](https://github.com/TeneikaAskew/stocks/issues/911) [#836](https://github.com/TeneikaAskew/stocks/issues/836) [#837](https://github.com/TeneikaAskew/stocks/issues/837) [#1319](https://github.com/TeneikaAskew/stocks/issues/1319) |
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
| Code | [solyra `src/routes/LandingPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/LandingPage.tsx), `platform/api/routers/waitlist.py` |
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
| Code | [solyra `src/routes/DashboardPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/DashboardPage.tsx), `platform/api/routers/dashboard.py`, `lib/movement_statement.py` |
| Tests | `dashboard.spec.ts`, `movement-read.spec.ts`, `MovementRead.test.tsx` |
| Open issues | 14 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-market-001--market-dashboard-14-open) |
| Blocking issues | [solyra#84](https://github.com/TeneikaAskew/solyra/issues/84) [#1218](https://github.com/TeneikaAskew/stocks/issues/1218) [#1222](https://github.com/TeneikaAskew/stocks/issues/1222) [#1266](https://github.com/TeneikaAskew/stocks/issues/1266) [#1267](https://github.com/TeneikaAskew/stocks/issues/1267) [solyra#126](https://github.com/TeneikaAskew/solyra/issues/126) |
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
| Code | [solyra `src/routes/LiveMarketPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/LiveMarketPage.tsx), `platform/api/routers/live.py`, `lib/indicators.py` |
| Tests | `live-market.spec.ts` |
| Open issues | 20 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-live-001--intraday-monitoring-20-open) |
| Blocking issues | [solyra#75](https://github.com/TeneikaAskew/solyra/issues/75) [#1272](https://github.com/TeneikaAskew/stocks/issues/1272) [#1273](https://github.com/TeneikaAskew/stocks/issues/1273) [#1274](https://github.com/TeneikaAskew/stocks/issues/1274) [#1275](https://github.com/TeneikaAskew/stocks/issues/1275) [solyra#124](https://github.com/TeneikaAskew/solyra/issues/124) |
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
| Code | [solyra `src/routes/ChartsPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/ChartsPage.tsx), `platform/api/routers/live.py`, `grid.py` |
| Tests | `charts-cards.spec.ts`, `phase1-charts.spec.ts` |
| Open issues | 21 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-chart-001--charting-21-open) |
| Blocking issues | [#1257](https://github.com/TeneikaAskew/stocks/issues/1257) [#1258](https://github.com/TeneikaAskew/stocks/issues/1258) [solyra#85](https://github.com/TeneikaAskew/solyra/issues/85) [solyra#86](https://github.com/TeneikaAskew/solyra/issues/86) [#1279](https://github.com/TeneikaAskew/stocks/issues/1279) [#1280](https://github.com/TeneikaAskew/stocks/issues/1280) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-OPTION-001

**Flow, Greeks, GEX grid** — Options / gamma

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Realtime collector repair: one cumulative source budget that excludes persistence time (#1743); review and job rollout pending. Snapshot provenance metadata on grid and levels responses ([spec](../superpowers/specs/2026-10-24-feat-option-001-legacy-snapshot-labels.md), approved on main) implemented on `feature/feat-option-001-snapshot-provenance`; review, solyra consumer evidence and API rollout pending |
| Priority | P0 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-07 |
| Evidence status | Preserved isolated collector and acceptance receipts; final integrated-head review/CI and immutable job deployment remain pending. No historical-snapshot restoration claim. Snapshot provenance: source and hermetic API tests only (`tests/api/test_snapshot_provenance.py`, grid and options router tests); no deployment, stored-row or signed-in screen claim. |
| UI surface | `/options` |
| Backend | `/api/options`, `/api/grid` |
| Data | `etf_options_snapshots`, `intraday_gex_15m`, `realtime_gex_15m` |
| Models | MODEL-GAMMA-001, MODEL-OPT-001 |
| Code | [solyra `src/routes/OptionsFlowPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/OptionsFlowPage.tsx), `platform/api/routers/options.py`, `grid.py`, `lib/gamma.py`, `lib/options_greeks.py` |
| Tests | `options-flow.spec.ts`, `gamma-levels.spec.ts`, `swingGridUtils.test.ts` |
| Open issues | 33 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-option-001--options--gamma-33-open) |
| Blocking issues | [#812](https://github.com/TeneikaAskew/stocks/issues/812) [#826](https://github.com/TeneikaAskew/stocks/issues/826) [#871](https://github.com/TeneikaAskew/stocks/issues/871) [#872](https://github.com/TeneikaAskew/stocks/issues/872) [#876](https://github.com/TeneikaAskew/stocks/issues/876) [#878](https://github.com/TeneikaAskew/stocks/issues/878) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |

### FEAT-SIGNAL-001

**Signal discovery, alerting, exits** — Signals / execution

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production needs remediation; historical-score contract implementation under review in #1620, not deployed; EW reader retirement source and local tests in Draft [#1801](https://github.com/TeneikaAskew/stocks/pull/1801) under the approved 2026-10-31 spec; external current-head review, hosted checks and rollout pending; the premarket brief scores RSI against the ticker's ticker_calibration band (the signal monitor's resolver, point in time), implementation under review, not deployed; honest outcome scoring (realized_return_pct under rule next-open-20m-1c-v1, `/similar` pct_profitable as the realized win share, resolver rule cross-fill-t1-v1) source and local tests in a Draft PR under the approved 2026-11-11 spec, schema apply and rollout pending |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-12 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/signals`, `/live` |
| Backend | `/api/signals` |
| Data | `signal_alerts`, `historical_signals`, `exit_config_overrides` |
| Models | MODEL-MOM-001, MODEL-MR-001, MODEL-AGREE-001, MODEL-EXIT-001 |
| Code | `lib/signals.py`, `lib/strategies/`, `gcp/signal_monitor.py`, `platform/api/routers/signals.py`, `lib/trading_analysis.py`, `gcp/premarket_playbook_resolver.py`, `scripts/analysis/honest_scoring_experiment.py` |
| Tests | `signals.spec.ts`, `tests/*/test_signal*.py`, `tests/lib/test_trading_analysis_realized_outcome.py`, `tests/lib/test_trading_analysis_feature_ranking.py`, `tests/gcp/test_premarket_playbook_resolver.py` |
| Open issues | 25 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-signal-001--signals--execution-25-open) |
| Blocking issues | [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#928](https://github.com/TeneikaAskew/stocks/issues/928) [#1206](https://github.com/TeneikaAskew/stocks/issues/1206) [#915](https://github.com/TeneikaAskew/stocks/issues/915) [#1136](https://github.com/TeneikaAskew/stocks/issues/1136) |
| Next action | Complete normal #1620 current-head review/checks and actual staging/frontend close-out; legacy records are not reconstructed or backfilled. Honest outcome scoring: review the Draft PR, apply its schema columns to Cloud SQL, then confirm the next historical-signals-watchlist run writes realized_return_pct and the next premarket-playbook-resolver run writes 2026-11-11.v2 |

### FEAT-PLAYBOOK-001

**Structured daily setups** — Premarket / playbook

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation; issue #1308 market-date repair verified locally, rollout pending |
| Priority | P0 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-11 |
| Evidence status | Existing production needs remediation; current-session ORB consumer candidate passes 137 guarded affected backend/OpenAPI tests after the first local review repair batch (timestamp identity, cold-calendar admission, bounded-response worker ownership and overflow isolation). The authorized SEC Low/P3 principal-fairness repair adds four verified-email attempts within the unchanged global eight and passes192 affected tests with1 existing Postgres-dependent skip. PLAYBOOK-05 source proof and generated inventory require final refresh for this repair; external review, hosted checks, API image/fleet qualification and deployed parity remain pending. |
| UI surface | `/playbook` |
| Backend | `/api/playbook` |
| Data | `premarket_analysis`, `playbook_cards` |
| Models | MODEL-BRIEF-001, MODEL-LEVEL-001 |
| Code | [solyra `src/routes/PlaybookPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/PlaybookPage.tsx), `platform/api/routers/playbook.py`, `gcp/premarket_brief.py`, `scripts/analysis/phase6_playbook.py` |
| Tests | `playbook.spec.ts`, `tests/scripts/test_phase6_playbook.py`, `tests/api/test_playbook_evaluate.py` (53 pass; paired summer/winter midnight, cache and historical-date controls for #1308) |
| Open issues | 19 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-playbook-001--premarket--playbook-19-open) |
| Blocking issues | [solyra#112](https://github.com/TeneikaAskew/solyra/issues/112) [#1304](https://github.com/TeneikaAskew/stocks/issues/1304) [#1305](https://github.com/TeneikaAskew/stocks/issues/1305) [#1306](https://github.com/TeneikaAskew/stocks/issues/1306) [#1307](https://github.com/TeneikaAskew/stocks/issues/1307) [#1308](https://github.com/TeneikaAskew/stocks/issues/1308) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 3 |


Current-session ORB runtime draft: [#1642](https://github.com/TeneikaAskew/stocks/pull/1642). The earlier137-test repair, formal renderer and source identity passed on the prior source. The current SEC fairness repair passes192 tests with1 existing Postgres-dependent skip; final source/document qualification remains root-owned. API-image calendar import, combined fleet allocation, hosted review/checks and deployed parity remain pending.

### FEAT-STRAT-001

**Candle classification, FTFC, structural levels** — STRAT / levels

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-12 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/charts`, `/live` |
| Backend | via `lib/` |
| Data | `strat_levels`, `strat_combo_results`, `level_param_policy`, `ticker_level_params` |
| Models | MODEL-STRAT-001, MODEL-FTFC-001, MODEL-LEVEL-001 |
| Code | `lib/strat.py` (closed-candle `compute_confirmed_setups`, rule `closed-candle-v1`; price-open FTFC `price-open-v1` from an observed price), `lib/config.py` (`continuity_timeframes_premarket`, `continuity_timeframes_session`), `lib/strat_levels.py`, `lib/exec_backtest/ftfc.py`, `lib/backtest.py` (causal default FTFC), `lib/agents/summarizers.py`, `lib/agents/schema.py`, `lib/agents/orchestrator.py`, `gcp/premarket_brief.py` (TF bias and FTFC lines, `tf_continuity` / `tf_continuity_frames`), `gcp/brief_explanations.py`, `gcp/insight_discord_push.py`, `gcp/schema.sql`, `scripts/research/strat_foundation_diagnostic.py`, `lib/strat_levels.py` `build_session_levels` (the one level builder: levels, side lists, broken status, window, triggers, stops, targets and reason per side, used by the brief, planner, signal monitor, playbook resolver, movement statement and dashboard), `lib/indicators.py` `calculate_premarket_context` (stale prior-close print and isolated spike filter), `gcp/schema.sql` (`level_basis` on `premarket_analysis` and `premarket_analysis_history`; premarket fetch time and excluded-print counts on `market_data_daily`), `lib/strat_levels.py` `load_level_params` (per-ticker parameters in force on the session, `params_unavailable` / `params_basis_mismatch` / `insufficient_history` states), `lib/level_calibration.py` (calibration methods, history calibrator, on-demand `calibrate_ticker`), `gcp/calibrate_level_params.py` (nightly and history calibration job), `gcp/schema.sql` (`level_param_policy`, `ticker_level_params`, `market_data_daily.atr_5`, `pre_filter_status` / `pre_filter_params`) |
| Tests | `tests/*/test_strat*.py`, `tests/lib/test_strat.py::TestClosedCandleConfirmation`, `tests/lib/test_backtest_ftfc_causality.py` (append, perturbation and 34 exact legacy final-as-of controls), `tests/lib/test_exec_ftfc_contract.py::TestLegacyFtfcGolden`, `tests/agents/test_agent_summarizers.py`, `tests/gcp/test_strat_snapshot_parity.py` (including the captured 2026-11-05 and first-session 2026-11-02 brief fixtures), `tests/lib/test_strat.py::TestObservedPriceContinuity`, `::TestFirstSessionOfPeriod`, `::TestGatesStayOnTfBias`, `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender`, `::TestFtfcPersistence`; captured-data diagnostic in [docs/research/artifacts/2026-11-04-strat-foundation-diagnostic](../research/artifacts/2026-11-04-strat-foundation-diagnostic/README.md), `tests/lib/test_session_levels_builder.py`, `test_session_levels_rules.py`, `test_session_levels_structure.py`, `test_premarket_print_filter.py`, `test_brief_planner_parity.py`, `test_no_synthesized_levels.py`, `test_orb_only_copy.py`, `test_parent_bar_naming.py`, `test_movement_statement_level_basis.py`, `tests/gcp/test_level_basis.py`, `tests/gcp/test_premarket_provenance.py`, `tests/gcp/test_premarket_filter_callers.py`, `tests/lib/test_level_params_loader.py`, `test_level_params_structure.py`, `test_level_params_behaviour.py`, `test_level_params_copy.py`, `test_level_calibration.py`, `test_level_calibration_history.py`, `test_level_calibration_evidence.py`, `tests/gcp/test_calibrate_level_params.py`, `test_level_params_consumers.py`, `test_atr5_column.py`, `test_premarket_filter_params.py`, `test_av_intraday_universe.py`, `tests/agents/test_on_demand_level_calibration.py`, `tests/scripts/test_backfill_watchlist_level_params.py`, `tests/lib/test_strat_levels.py::TestTargetSpacing`, `::TestExitPlanCopy`, `tests/lib/test_movement_statement_level_basis.py`, `tests/gcp/test_premarket_playbook_resolver.py::TestPlanOutcome`, `::TestPlanInputs`, `tests/gcp/test_brief_channel_routing.py`, `tests/api/test_movement_statement_exit_plan.py` |
| Open issues | 5 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-strat-001--levels--strat-5-open) |
| Blocking issues | [#866](https://github.com/TeneikaAskew/stocks/issues/866) [#908](https://github.com/TeneikaAskew/stocks/issues/908) [#907](https://github.com/TeneikaAskew/stocks/issues/907) [#884](https://github.com/TeneikaAskew/stocks/issues/884) [solyra#140](https://github.com/TeneikaAskew/solyra/issues/140) |
| Next action | Foundation release [#1714](https://github.com/TeneikaAskew/stocks/pull/1714) merged ([spec](../superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md), [plan](../superpowers/plans/2026-11-04-feat-strat-001-confirmed-foundation.md)): confirmed setups only from closed candles, causal default FTFC, explicit unavailable consumer states. Its three P2 review follow-ups are in [#1727](https://github.com/TeneikaAskew/stocks/pull/1727) ([plan](../superpowers/plans/2026-11-05-feat-strat-001-review-followups.md)): the legacy `Last` close alias, the replay cutoff for coverage and FTFC, and unknown successors in the history report. Deployed verification is recorded after release gates. TF bias and true FTFC ([spec](../superpowers/specs/2026-11-05-feat-strat-001-tf-continuity-display.md), [plan](../superpowers/plans/2026-11-05-feat-strat-001-tf-continuity-display.md)): the weighted candle vote is displayed as TF bias and stays the gate input; the brief shows and stores price-versus-open FTFC (Q, M, W premarket) in `tf_continuity` / `tf_continuity_frames`, whose production migration the owner applies later. Structural levels (#866, #907, #908) need their own approved contract. One level source ([spec](../superpowers/specs/2026-11-07-feat-strat-001-one-level-source-r2.md), [plan](../superpowers/plans/2026-11-07-feat-strat-001-one-level-source.md)): levels, triggers, stops and targets are built in one place for every consumer from prior-period highs, lows and closes, the parent bar and the filtered premarket extremes, with one side rule, one broken rule and one window, no synthesized numbers, and the brief's `level_basis` stored and read by every live consumer. The `level_basis` and `market_data_daily` column apply waits for the owner's yes, and the solyra null entry and stop change lands before the API image is deployed. Per-ticker parameters ([spec](../superpowers/specs/2026-11-08-feat-strat-001-per-ticker-params.md), [plan](../superpowers/plans/2026-11-08-feat-strat-001-per-ticker-params.md), merged spec [#1754](https://github.com/TeneikaAskew/stocks/pull/1754)): every ATR multiple, percent-of-price window, entry buffer, stop multiple, target multiple and premarket filter threshold in the level and plan path is read from `ticker_level_params`, calibrated per ticker from its own history by a nightly job, with ATR(5) stored beside ATR(14). The two tables, the `atr_5` column, the `atr_5` and history-mode backfills, the job's scheduler and the av-intraday-nightly universe change are applied to production only after the owner's yes. Exits in thirds ([spec](../superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md), merged spec [#1812](https://github.com/TeneikaAskew/stocks/pull/1812), implementation [#1832](https://github.com/TeneikaAskew/stocks/pull/1832), draft): the brief's targets are spaced by each ticker's `target_min_spacing_atr` x ATR, the exit is planned in `exit_legs` legs, new entries stop at the policy's `entry_cutoff_et`, an open already through the trigger is not an entry, and a prior-close target on a gap of at least `gap_fill_flag_atr` x ATR is labelled a gap fill; the gating t1..t3 stay as they were and the spaced targets go to `plan_t1..t3_price`. The resolver scores the plan on top of the honest outcome scoring rule ([#1833](https://github.com/TeneikaAskew/stocks/pull/1833)): per side, the plan entry status, fill, R over the legs, R status and each leg's exit (`RESOLVER_VERSION` 2026-11-12.v3, 18 nullable `premarket_analysis` columns); the production replay experiment runs before merge, and the four policy rows, the six plan target columns, the 18 plan outcome columns and the seeded-key history run are applied only after the owner's yes. |

### FEAT-IND-001

**RVOL, ORB, ATR, RSI, VWAP** — Indicators

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P1 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-05 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/live`, `/charts` |
| Backend | via `lib/` |
| Data | `market_data_*` |
| Models | MODEL-IND-001 |
| Code | `lib/indicators.py`, `lib/signals.py` |
| Tests | `tests/lib/test_indicators*.py` |
| Open issues | 5 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-ind-001--indicators-5-open) |
| Blocking issues | [#870](https://github.com/TeneikaAskew/stocks/issues/870) [#892](https://github.com/TeneikaAskew/stocks/issues/892) [#894](https://github.com/TeneikaAskew/stocks/issues/894) [#912](https://github.com/TeneikaAskew/stocks/issues/912) [#1276](https://github.com/TeneikaAskew/stocks/issues/1276) |
| Next action | The premarket brief's level-break flags ([spec](../superpowers/specs/2026-11-05-feat-ind-001-brief-level-breaks.md), [plan](../superpowers/plans/2026-11-05-feat-ind-001-brief-level-breaks.md)): `add_brief_indicators` produces `Broke_Prev_Day_High` / `Broke_Prev_Day_Low`, so `level_break_pdh` / `level_break_pdl` can score (CALL and PUT still top out at 4 of 5 on real bars). Merge and deployed verification are recorded after release gates; otherwise sequence from [13](13-ROADMAP.md) Phase 1. |

### FEAT-INSIGHT-001

**LLM per-ticker reports + chat** — AI insights

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Experimental; EW reader retirement source and local tests in Draft [#1800](https://github.com/TeneikaAskew/stocks/pull/1800) under the approved 2026-10-31 spec; external current-head review, hosted checks and rollout pending |
| Priority | P2 |
| Target phase | Phase 4 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-11 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/insights` |
| Backend | `/api/insights` (13) |
| Data | `insight_reports`, `insight_runs`, `model_routing` |
| Models | 14 LLM nodes — see [08](08-AI-AGENT-ARCHITECTURE.md) |
| Code | `lib/agents/`, `platform/api/routers/insights.py`, `gcp/insight_pipeline_job.py` |
| Tests | `insights.spec.ts`, `tests/agents/test_agent_*.py` |
| Open issues | 31 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-insight-001--ai-insights-31-open) |
| Blocking issues | [#827](https://github.com/TeneikaAskew/stocks/issues/827) [#867](https://github.com/TeneikaAskew/stocks/issues/867) [#1215](https://github.com/TeneikaAskew/stocks/issues/1215) [#1216](https://github.com/TeneikaAskew/stocks/issues/1216) [#1217](https://github.com/TeneikaAskew/stocks/issues/1217) [#916](https://github.com/TeneikaAskew/stocks/issues/916) |
| Next action | The one-level source merged in [#1753](https://github.com/TeneikaAskew/stocks/pull/1753): the insight planner reads the brief's session levels, recorded in `level_basis`, instead of walking levels on its own. Next, under FEAT-STRAT-001: the per-ticker parameters ([#1784](https://github.com/TeneikaAskew/stocks/pull/1784), [spec](../superpowers/specs/2026-11-10-feat-strat-001-per-ticker-params-r2.md)) replace the fixed 3 x ATR(14) and 8% window, entry buffers, stops and targets with values calibrated from each ticker's own history, and the insight planner and report read the same row the brief does. Deployed verification is recorded after release gates; otherwise sequence from [13](13-ROADMAP.md) Phase 4. |

### FEAT-CATALYST-001

**Events, reactions, news, filings** — Earnings / catalysts

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation; finite EPS normalization and EW retirement verified locally, external review and rollout pending |
| Priority | P1 |
| Target phase | Phase 3 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-11 |
| Evidence status | Finite EPS source/local tests verified; event-bound reaction repairs ([#1608](https://github.com/TeneikaAskew/stocks/pull/1608)) locally validated; current-head external review, hosted checks and rollout pending; other catalyst work remains open |
| UI surface | `/catalysts` |
| Backend | `/api/catalysts`, `/api/earnings` |
| Data | `earnings_*`, `economic_events`, `news_sentiment`, `sec_filings` |
| Models | MODEL-EARN-001 |
| Code | `platform/api/routers/catalysts.py`, `earnings.py`, `lib/earnings_reactions.py` |
| Tests | `catalysts.spec.ts`; `tests/gcp/test_compute_earnings_reactions.py`, `test_earnings_daily_path.py`, `test_earnings_local_admission.py`, `test_earnings_reactions_brief.py`; `tests/integration/test_earnings_daily_path_persistence.py`; `tests/api/test_earnings_router.py`; `tests/research/test_earnings_new7_reproduction.py`; `tests/api/test_catalyst_earnings_estimate_numbers.py`, `tests/scripts/test_earnings_calendar_finite_numbers.py`, `tests/integration/test_catalyst_earnings_estimate_numbers_pg.py` |
| Open issues | 19 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-catalyst-001--earnings--catalysts-19-open) |
| Blocking issues | [#1223](https://github.com/TeneikaAskew/stocks/issues/1223) [#1268](https://github.com/TeneikaAskew/stocks/issues/1268) [#1269](https://github.com/TeneikaAskew/stocks/issues/1269) [#1270](https://github.com/TeneikaAskew/stocks/issues/1270) [#1299](https://github.com/TeneikaAskew/stocks/issues/1299) [#1300](https://github.com/TeneikaAskew/stocks/issues/1300) |
| Next action | Complete narrow [#1621](https://github.com/TeneikaAskew/stocks/pull/1621) reviews/checks and existing API/producer rollout. [#1608](https://github.com/TeneikaAskew/stocks/pull/1608): event-bound timing, mature prior-history admission and nullable descriptive daily evidence locally validated; normal source review/CI and schema-before-code rollout remain pending. Actual `/catalysts` outcome-panel binding is a separate Solyra change; no deployment or predictive-edge claim. Broader Phase 3 work remains open. |

Finite-number slice: approved spec [#1618](https://github.com/TeneikaAskew/stocks/pull/1618) is MAIN. Implementation draft [#1621](https://github.com/TeneikaAskew/stocks/pull/1621) preserves actual producer/API normalization,185focused checks including independent-session local PostgreSQL commit/read and the real routed response, and31API preservation checks (overlapping suite). Final hermetic unit verification at2ad639e1:7719passed,51skipped,112warnings; integration was excluded from that full unit command and the real local PG proof is separately retained. No deployment/source-equivalence, current-source freshness or complete catalyst remediation is certified. Touches #1269 and only #1301's numeric-title behavior; cross-source dedup/selection remains unchanged and unresolved.

EW-only retirement: [#1758](https://github.com/TeneikaAskew/stocks/pull/1758), fresh implementation bound to the approved own-scope specification merged in #1703. Six reader predicates, ingestion removal and five NULL score-dependent outputs are locally tested; historical rows and #1608 behavior remain intact. Source identity, external review/CI and production release are separate; no deployment or complete catalyst-remediation claim.

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
| Models | MODEL-CALIB-001, MODEL-SWEEP-001, MODEL-STYLE-001 |
| Code | [solyra `src/routes/ReportsPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/ReportsPage.tsx), `platform/api/routers/backtest.py`, `analytics.py` |
| Tests | `reports.spec.ts`, `BacktesterSection.format.test.ts` |
| Open issues | 9 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-report-001--reports--analytics-9-open) |
| Blocking issues | [#1278](https://github.com/TeneikaAskew/stocks/issues/1278) [#1311](https://github.com/TeneikaAskew/stocks/issues/1311) [solyra#205](https://github.com/TeneikaAskew/solyra/issues/205) [solyra#206](https://github.com/TeneikaAskew/solyra/issues/206) [solyra#134](https://github.com/TeneikaAskew/solyra/issues/134) [solyra#136](https://github.com/TeneikaAskew/solyra/issues/136) |
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
| Tests | `replay-trainer.spec.ts`, `tests/*/test_backtest*.py` |
| Open issues | 17 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-replay-001--replay--backtest--evaluation-17-open) |
| Blocking issues | [#814](https://github.com/TeneikaAskew/stocks/issues/814) [#819](https://github.com/TeneikaAskew/stocks/issues/819) [#821](https://github.com/TeneikaAskew/stocks/issues/821) [#822](https://github.com/TeneikaAskew/stocks/issues/822) [#823](https://github.com/TeneikaAskew/stocks/issues/823) [#824](https://github.com/TeneikaAskew/stocks/issues/824) |
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
| Last reviewed | 2026-09-14 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/admin` |
| Backend | `/api/magnitude`, `/api/admin/strat-engine` |
| Data | `ticker_calibration`, `user_style_results` |
| Models | see [07](07-MODEL-REGISTRY.md) |
| Code | `gcp/research/`, `lib/walk_forward.py`, `platform/api/routers/magnitude.py` |
| Tests | `tests/lib/test_walk_forward*.py`, `tests/*/test_magnitude*.py` |
| Open issues | 11 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-model-001--models--research-11-open) |
| Blocking issues | [#813](https://github.com/TeneikaAskew/stocks/issues/813) [#817](https://github.com/TeneikaAskew/stocks/issues/817) [#874](https://github.com/TeneikaAskew/stocks/issues/874) [#875](https://github.com/TeneikaAskew/stocks/issues/875) [#888](https://github.com/TeneikaAskew/stocks/issues/888) [#909](https://github.com/TeneikaAskew/stocks/issues/909) |
| Next action | 2026-09-14 (E-35): magnitude promotion criteria were measured mutually unsatisfiable and replaced with a decision-rule verdict; `pred_bucket` on `/api/magnitude` is now that decision, not argmax. The four constant-output `c49qf` cells still serve pending the decision in [15](15-OPEN-DECISIONS.md). Then sequence from [13](13-ROADMAP.md) Phase 4 |

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
| Code | [solyra `src/routes/JournalPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/JournalPage.tsx), `platform/api/routers/journal.py`, `lib/broker_import.py` |
| Tests | `journal.spec.ts`, `journal-import.spec.ts`, `journal-onestop.spec.ts` |
| Open issues | 20 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-journal-001--journal--portfolio-20-open) |
| Blocking issues | [#1219](https://github.com/TeneikaAskew/stocks/issues/1219) [#1263](https://github.com/TeneikaAskew/stocks/issues/1263) [#1264](https://github.com/TeneikaAskew/stocks/issues/1264) [#1220](https://github.com/TeneikaAskew/stocks/issues/1220) [#1312](https://github.com/TeneikaAskew/stocks/issues/1312) [#1313](https://github.com/TeneikaAskew/stocks/issues/1313) |
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
| Code | `gcp/discord_interactions/main.py`, `gcp/failure_notifier.py` |
| Tests | `tests/gcp/test_notifier*.py` |
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
| Backend | `/api/admin` (12), `/api/config` |
| Data | `model_routing` |
| Models | — |
| Code | [solyra `src/routes/AdminPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/AdminPage.tsx), `platform/api/routers/admin.py` |
| Tests | `admin.spec.ts`, `admin-auth.spec.ts` |
| Open issues | 21 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-admin-001--administration-21-open) |
| Blocking issues | [#1221](https://github.com/TeneikaAskew/stocks/issues/1221) [#1265](https://github.com/TeneikaAskew/stocks/issues/1265) [solyra#114](https://github.com/TeneikaAskew/solyra/issues/114) [#1316](https://github.com/TeneikaAskew/stocks/issues/1316) [#1317](https://github.com/TeneikaAskew/stocks/issues/1317) [#1318](https://github.com/TeneikaAskew/stocks/issues/1318) |
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
| Code | [solyra `src/routes/HelpPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/HelpPage.tsx), `platform/api/routers/glossary.py` |
| Tests | `help.spec.ts` |
| Open issues | 9 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-help-001--help--glossary-9-open) |
| Blocking issues | [#1336](https://github.com/TeneikaAskew/stocks/issues/1336) [solyra#221](https://github.com/TeneikaAskew/solyra/issues/221) [solyra#222](https://github.com/TeneikaAskew/solyra/issues/222) [solyra#223](https://github.com/TeneikaAskew/solyra/issues/223) [solyra#224](https://github.com/TeneikaAskew/solyra/issues/224) [#1337](https://github.com/TeneikaAskew/stocks/issues/1337) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-SETTINGS-001

**Account-backed appearance, trading defaults and profile** — Settings

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation |
| Priority | P3 |
| Target phase | Phase 5 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-10-07 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/settings` |
| Backend | GET and PUT `/api/me/preferences` (`platform/api/routers/preferences.py:132`, `:149`); GET and PUT `/api/me/profile` (`platform/api/routers/profile.py:145`, `:162`); both mounted at `platform/api/main.py:187-189` and gated in `firebase` mode, because only the exact `/api/me` is open (`_OPEN_API_EXACT`, `platform/api/auth.py:69`); the owner rule per auth mode is in [04](04-BACKEND-API.md) |
| Data | `user_preferences` and `user_profile`, one row per `user_email`, upserted with `ON CONFLICT (user_email) DO UPDATE` |
| Models | — |
| Code | [solyra `src/routes/SettingsPage.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/routes/SettingsPage.tsx), [solyra `src/stores/settingsStore.ts`](https://github.com/TeneikaAskew/solyra/blob/main/src/stores/settingsStore.ts), [solyra `src/stores/themeStore.ts`](https://github.com/TeneikaAskew/solyra/blob/main/src/stores/themeStore.ts), [solyra `src/hooks/usePreferences.ts`](https://github.com/TeneikaAskew/solyra/blob/main/src/hooks/usePreferences.ts), [solyra `src/hooks/useProfile.ts`](https://github.com/TeneikaAskew/solyra/blob/main/src/hooks/useProfile.ts), `platform/api/routers/preferences.py`, `platform/api/routers/profile.py` |
| Tests | `tests/api/test_preferences_router.py`, `tests/api/test_profile_router.py`, [solyra `tests/settings/settings.spec.ts`](https://github.com/TeneikaAskew/solyra/blob/main/tests/settings/settings.spec.ts) |
| Open issues | 13 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-settings-001--settings-13-open) |
| Blocking issues | [solyra#117](https://github.com/TeneikaAskew/solyra/issues/117) [solyra#119](https://github.com/TeneikaAskew/solyra/issues/119) [solyra#121](https://github.com/TeneikaAskew/solyra/issues/121) [#1322](https://github.com/TeneikaAskew/stocks/issues/1322) [#1323](https://github.com/TeneikaAskew/stocks/issues/1323) [solyra#216](https://github.com/TeneikaAskew/solyra/issues/216) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 5 |

### FEAT-DATA-001

**Ingestion, storage, freshness** — Data platform

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation — logger #1607 image rollout verified; allowance #1606 source integrated, release gated; one NYSE session calendar in `lib/eastern_time.py` replaces the 2026-only holiday sets and the ad hoc library wrappers ([#1546](https://github.com/TeneikaAskew/stocks/pull/1546)); the premarket brief's daily-data freshness check counts NYSE sessions, so sessions after an NYSE holiday are no longer skipped as STALE_DAILY_DATA (implementation under review, not deployed) |
| Priority | P0 |
| Target phase | Phase 1 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-11 |
| Evidence status | Logger source bd8c5310/build20c56463/image ef54b4b6 deployed Ready to three jobs with projected config preserved; next scheduled outcomes unobserved. Allowance runtime/test bytes unchanged from reviewed258fb789,224 tests preserved; prior CODE/SEC/CI clean, combined source proof and owner-approved CODE7 remain required. No complete data-platform, persistence or provider-root-cause certification. |
| UI surface | — |
| Backend | fetcher jobs |
| Data | 64 relations — see [06](06-DATA-ARCHITECTURE.md) |
| Models | — |
| Code | `gcp/fetchers/`, `gcp/schema.sql`, `lib/data_loader.py`, `gcp/database.py`, `lib/eastern_time.py` (NYSE sessions) |
| Tests | `tests/lib/test_data_loader*.py`, integration suite |
| Open issues | 21 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-data-001--data-platform-21-open) |
| Blocking issues | [#925](https://github.com/TeneikaAskew/stocks/issues/925) [#926](https://github.com/TeneikaAskew/stocks/issues/926) [#828](https://github.com/TeneikaAskew/stocks/issues/828) [#862](https://github.com/TeneikaAskew/stocks/issues/862) [#863](https://github.com/TeneikaAskew/stocks/issues/863) [#913](https://github.com/TeneikaAskew/stocks/issues/913) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 1 |

### FEAT-DEPLOY-001

**76 jobs, 66 schedulers, Cloud Run** — Infrastructure / deploy

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation — notifier runtime access isolated; EW calendar binding source retirement prepared, rollout pending; 03-SITE citation of the deleted prompt renderer retired (#1794); `evaluate-ew-strikes` job and `evaluate-ew-strikes-daily` scheduler retired from the declared fleet ([#1834](https://github.com/TeneikaAskew/stocks/pull/1834), spec [#1666](https://github.com/TeneikaAskew/stocks/pull/1666)), live deletion is the separately authorized close-out |
| Priority | P1 |
| Target phase | Phase 6 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-12 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | — |
| Backend | — |
| Data | — |
| Models | — |
| Code | `gcp/deploy.sh`, `platform/deploy.sh` (deploys `solyra-api-staging` only; `solyra-api-prod` retired 2026-10-10, [#1366](https://github.com/TeneikaAskew/stocks/pull/1366)), `gcp/cloudbuild/` |
| Tests | static checks; `tests/gcp/test_platform_deploy_service_config.py` runs `platform/deploy.sh` against a stub `gcloud` and asserts the staging service's auth mode, service account, environment, secrets, ingress and the `SETUP_IAM` grant ([#1350](https://github.com/TeneikaAskew/stocks/pull/1350)), and that a run without `STAGING_SERVICE=1` or with `STAGING=1` is refused before any `gcloud` call; `tests/gcp/test_staging_deploy_paths.py` asserts the retired service has no deploy path ([#1366](https://github.com/TeneikaAskew/stocks/pull/1366)); `tests/scripts/test_refresh_architecture_drawio.py` asserts the diagrams and their generator draw no retired service and refuse a snapshot without table statistics, and `tests/api/test_dev_page_auth.py` covers the `/dev` proxy line ([#1384](https://github.com/TeneikaAskew/stocks/pull/1384)); `tests/gcp/test_deploy_ew_evaluator.py` proves with a recording `gcloud` stub that no deploy path creates or schedules `evaluate-ew-strikes`, that `deploy_schedulers` deletes its retired schedule and that the dispatcher target is a RETIRED stub ([#1834](https://github.com/TeneikaAskew/stocks/pull/1834)) |
| Open issues | 15 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-deploy-001--infrastructure--deploy-15-open) |
| Blocking issues | [#834](https://github.com/TeneikaAskew/stocks/issues/834) [#835](https://github.com/TeneikaAskew/stocks/issues/835) [#832](https://github.com/TeneikaAskew/stocks/issues/832) [#851](https://github.com/TeneikaAskew/stocks/issues/851) [#855](https://github.com/TeneikaAskew/stocks/issues/855) [#856](https://github.com/TeneikaAskew/stocks/issues/856) |
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
| Last reviewed | 2026-10-13 |
| Evidence status | VERIFIED — CODE (implementation); evaluation evidence per [07](07-MODEL-REGISTRY.md) |
| UI surface | `/admin` |
| Backend | `/api/health/freshness` |
| Data | `job_runs` |
| Models | — |
| Code | `scripts/audit_data_freshness.py`, `gcp/failure_notifier.py`, `platform/api/routers/health.py` |
| Tests | `data-pipeline-status.spec.ts` deleted in #957: widget guard ported in [solyra#29](https://github.com/TeneikaAskew/solyra/pull/29); live `/api/health/freshness` tests tracked in [#971](https://github.com/TeneikaAskew/stocks/issues/971) |
| Open issues | 11 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-ops-001--operations--reliability-11-open) |
| Blocking issues | [#922](https://github.com/TeneikaAskew/stocks/issues/922) [#1052](https://github.com/TeneikaAskew/stocks/issues/1052) [#1066](https://github.com/TeneikaAskew/stocks/issues/1066) [#1067](https://github.com/TeneikaAskew/stocks/issues/1067) [#1224](https://github.com/TeneikaAskew/stocks/issues/1224) [#1290](https://github.com/TeneikaAskew/stocks/issues/1290) |
| Next action | Freshness audit alert replacement in PR #1499 after the review cap;  TBD — sequence from [13](13-ROADMAP.md) Phase 6 |

### FEAT-CICD-001

**Build, test, deploy automation** — CI / testing

| Field | Value |
|---|---|
| Owner | TBD |
| Status | Production but needs remediation — historical SITE presence repair [#1597](https://github.com/TeneikaAskew/stocks/pull/1597) continues #1595 with original VP-01 and review history, final evidence pending; committed source identity and complete generated-inventory verification merged; local delivery-tool close-out checked; AV/global rollout and remediation pending; tests that fake gcloud cannot reach a real one, the deliberate `--mode=live` secret read excepted ([#1536](https://github.com/TeneikaAskew/stocks/pull/1536)); trusted registry six-minute pin #1591 and matching live activation #1599 merged as e7e74ccc; exact live/pin equality and all six hosted checks verified, registry144PASS/exporter-current314s/46s reserve ([receipt](https://github.com/TeneikaAskew/stocks/pull/1599#issuecomment-6400278126)); spec-gate supersedes-chain retirement (status-only flip of a superseding spec, lineage validation, truthful fail-closed redundant-retirement refusal) merged from [#1656](https://github.com/TeneikaAskew/stocks/pull/1656) as cb136f3e under its approved source-note spec ([#1667](https://github.com/TeneikaAskew/stocks/pull/1667); it supersedes the merged replacement spec [#1664](https://github.com/TeneikaAskew/stocks/pull/1664)), with bounded local three-role red-team review accepted in place of hosted CODE review, which was unavailable on provider quota (owner's exception for that PR only, [comment](https://github.com/TeneikaAskew/stocks/pull/1656#issuecomment-6565852104)), and required CI green on its head; the replaced spec's status-only retirement merged in [#1676](https://github.com/TeneikaAskew/stocks/pull/1676) as e9a06998; the gate change runs in the pre-commit hook and CI only and deploys nothing; DOC-only close-out binding to the 2026-11-02 protocol spec by exact path (approved clarification spec [#1692](https://github.com/TeneikaAskew/stocks/pull/1692); close-outs had been refused as superseded) in draft re-cut [#1694](https://github.com/TeneikaAskew/stocks/pull/1694) of [#1691](https://github.com/TeneikaAskew/stocks/pull/1691) with the same code and test bytes, review coverage and merge pending; capacity fixture bridge (test only: the eight capacity-bearing gate-suite functions carry an explicit same-value `Cost:` beside each historical `30:` carrier, with a frozen BASE case oracle, a pre-dispatch pair guard and `test_capacity_bridge_case_and_carrier_equivalence`; gate, template, pins, workflows and hooks byte-identical to main) merged in [#1713](https://github.com/TeneikaAskew/stocks/pull/1713) as 178973b0 after Codex code and security reviews completed on its head, no findings reported, a re-cut of [#1706](https://github.com/TeneikaAskew/stocks/pull/1706) under the whole-job successor spec ([#1710](https://github.com/TeneikaAskew/stocks/pull/1710), which supersedes the Oct 13 bridge spec [#1473](https://github.com/TeneikaAskew/stocks/pull/1473) whose 285 s clause unchanged main cannot meet, [#1707](https://github.com/TeneikaAskew/stocks/issues/1707), and tracks the matched docs audit in [#1708](https://github.com/TeneikaAskew/stocks/issues/1708)): fixture compatibility delivered; Cost predicate correction (the fourth `CAPACITY_LABELS` literal becomes `Cost` and the default PR template's one cost line becomes `- Cost:`, with `test_capacity_cost_label_contract` and `test_capacity_cost_rendered_budget_guards`) in draft [#1716](https://github.com/TeneikaAskew/stocks/pull/1716) under #1710's Cost successor spec, which supersedes the Oct 13 Cost spec [#1474](https://github.com/TeneikaAskew/stocks/pull/1474): verified in source and local tests, four-seat gate review, hosted CI, current-head review and merge pending, production rollout unchanged; its CODE is a recorded prerequisite of the deploy-side EW retirement [#1659](https://github.com/TeneikaAskew/stocks/pull/1659) and of the catalyst-side EW re-cut. Owner directive on done and autonomy (done means merged, deployed where the change ships and verified against live GCP; sessions make reversible calls themselves and stop only for irreversible steps, money or outside contact) added to `CLAUDE.md` under its approved spec (merged in [#1705](https://github.com/TeneikaAskew/stocks/pull/1705)) in [#1726](https://github.com/TeneikaAskew/stocks/pull/1726), review and merge pending; registry ten-minute pin stage (pinned copy only, the live job still bounded at six minutes) in draft [#1696](https://github.com/TeneikaAskew/stocks/pull/1696) under its pin-stage primary spec (merged, [#1693](https://github.com/TeneikaAskew/stocks/pull/1693); parent design [#1683](https://github.com/TeneikaAskew/stocks/pull/1683), merged), gate-file red-team recorded, review coverage and merge pending; SITE source verifier combined input ceiling raised from eight to twelve MiB, with the registry file's eight-MiB per-file check kept under its own constant, in draft [#1699](https://github.com/TeneikaAskew/stocks/pull/1699) under its approved spec (on main since 5f16c96e), local four-seat review recorded, current-head review and merge pending. `scripts/gate/` is owned by this capability through the gate's `WORKFLOW_FEAT` constant, while the Code row lists `.github/workflows/` and the review guidelines; monthly architecture-doc refresh retired, renderers kept on demand ([#1788](https://github.com/TeneikaAskew/stocks/pull/1788), records [#1787](https://github.com/TeneikaAskew/stocks/pull/1787)); CPU-deadline refusal test finds its cap on each host (escalating 0.75, 1.5, 3 and 5 s) and the stale SHARED-01 pin sentence reworded ([#1814](https://github.com/TeneikaAskew/stocks/pull/1814), spec [#1811](https://github.com/TeneikaAskew/stocks/pull/1811) revised in [#1817](https://github.com/TeneikaAskew/stocks/pull/1817)); 05-a's declared retry split is rendered from `gcp/deploy.sh` by the docs renderer, so a PR that changes a job's retries updates the counts it states ([#1836](https://github.com/TeneikaAskew/stocks/pull/1836), re-cut of [#1835](https://github.com/TeneikaAskew/stocks/pull/1835), spec admitted in [#1756](https://github.com/TeneikaAskew/stocks/pull/1756); unblocks #1671 and #1834), review and merge pending |
| Priority | P1 |
| Target phase | Phase 6 — see [13](13-ROADMAP.md) |
| Target release | TBD |
| Last reviewed | 2026-11-12 |
| Evidence status | LOCAL DELIVERY TOOLING VERIFIED — [#1470](https://github.com/TeneikaAskew/stocks/pull/1470) committed-source verifier and [#1538](https://github.com/TeneikaAskew/stocks/pull/1538) complete generated-inventory tooling merged after authenticated CODE review and required CI. Fresh actual-main identity, local-tool accepted/refused checks and terminal marker/record retirement verified in this DOC close-out. AV/global rollout and product deployment/data-freshness verification remain separate. |
| UI surface | — |
| Backend | — |
| Data | — |
| Models | — |
| Code | `.github/workflows/`; review guidelines in `AGENTS.md` (`## Review guidelines`), merge gate in `CLAUDE.md` Rule 2.5 |
| Tests | 7352 pytest items in `make test`'s scope (a parametrized test counts once per case), collected 2026-10-11 at `17bbacd3` by `python3 -m pytest tests/ --ignore=tests/integration --collect-only -q -p no:cacheprovider` with 0 collection errors; 29 e2e and 27 vitest tests moved to solyra in the #957 split |
| Open issues | 12 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-cicd-001--ci--testing-12-open) |
| Blocking issues | [#844](https://github.com/TeneikaAskew/stocks/issues/844) [#845](https://github.com/TeneikaAskew/stocks/issues/845) [#846](https://github.com/TeneikaAskew/stocks/issues/846) [#848](https://github.com/TeneikaAskew/stocks/issues/848) [#847](https://github.com/TeneikaAskew/stocks/issues/847) [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28) |
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
| Tests | [solyra `tests/shared/navigation.spec.ts`](https://github.com/TeneikaAskew/solyra/blob/main/tests/shared/navigation.spec.ts) |
| Open issues | 2 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-ui-001--web--ui-2-open) |
| Blocking issues | [solyra#135](https://github.com/TeneikaAskew/solyra/issues/135) [solyra#95](https://github.com/TeneikaAskew/solyra/issues/95) |
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
| Open issues | 11 — full list in [12](12-PR-ISSUE-TRACEABILITY.md#feat-debt-001--technical-debt-11-open) |
| Blocking issues | [#917](https://github.com/TeneikaAskew/stocks/issues/917) [#1137](https://github.com/TeneikaAskew/stocks/issues/1137) [#921](https://github.com/TeneikaAskew/stocks/issues/921) [#1227](https://github.com/TeneikaAskew/stocks/issues/1227) [#1335](https://github.com/TeneikaAskew/stocks/issues/1335) [solyra#79](https://github.com/TeneikaAskew/solyra/issues/79) |
| Next action | TBD — sequence from [13](13-ROADMAP.md) Phase 7 |

