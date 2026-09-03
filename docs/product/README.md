# Living Product Plan

**Repository:** `TeneikaAskew/stocks` · **Evidence snapshot / Last reviewed:** 2026-08-31 · **`main` baseline:** `b9621c4`

The maintained index from product intent through implementation, evidence, risk and delivery.

## Navigation

| Document | Question answered |
|---|---|
| [00 Product Overview](00-PRODUCT-OVERVIEW.md) | What is the product and where is it going? |
| [01 Product Requirements](01-PRODUCT-REQUIREMENTS.md) | What shall it do, and when is it done? |
| [02 Feature Catalog](02-FEATURE-CATALOG.md) | What capabilities exist and what is their trust state? |
| [03 Ui Screens](03-UI-SCREENS.md) | What does each of the 15 screens do? |
| [04 Backend Api](04-BACKEND-API.md) | Which of the 92 platform endpoints support it, and how is each authenticated? |
| [05 Infrastructure](05-INFRASTRUCTURE.md) | What runs and deploys it — 67 jobs, 58 schedulers? |
| [06 Data Architecture](06-DATA-ARCHITECTURE.md) | What are the 64 relations and how does data flow? |
| [07 Model Registry](07-MODEL-REGISTRY.md) | Which rules and models exist, and are they trustworthy? |
| [08 Ai Agent Architecture](08-AI-AGENT-ARCHITECTURE.md) | What are the 14 LLM nodes actually wired today? |
| [09 Security Auth](09-SECURITY-AUTH.md) | How are identity, access, tenancy and perimeter separated? |
| [10 Operations Reliability](10-OPERATIONS-RELIABILITY.md) | How is production trust measured and recovered? |
| [11 Code Traceability](11-CODE-TRACEABILITY.md) | Where is each capability implemented? |
| [12 Pr Issue Traceability](12-PR-ISSUE-TRACEABILITY.md) | Which PRs built it and which open issues block it? |
| [13 Roadmap](13-ROADMAP.md) | What should be sequenced next? |
| [14 Work Breakdown](14-WORK-BREAKDOWN.md) | How does the work decompose into evidence? |
| [15 Open Decisions](15-OPEN-DECISIONS.md) | Which product choices remain unresolved? |
| [16 Consolidation Audit](16-CONSOLIDATION-AUDIT.md) | What was preserved from Claude and PR #924, and how was every section validated? |

## Where the app lives

| Environment | URL | Auth |
|---|---|---|
| Production | `https://trading-platform-5sjtb3yl7a-ue.a.run.app` | IAP SSO (`bictech.org`) — verified live 2026-08-30 |
| Staging | `UNKNOWN` (service `trading-platform-staging`) | **public + Firebase** |
| Local dev | `http://localhost:5173` (API `http://localhost:8000`) | none (`AUTH_MODE` defaults to `open`) |

No custom domain is committed in the repo despite the **Solyra** branding on the landing page.
Per-screen URLs: [03](03-UI-SCREENS.md#live-urls). Full inventory and the command to resolve the
unknowns: [05](05-INFRASTRUCTURE.md#environments-and-urls).

## Canonical-plan decision

**`docs/product/` on the default branch is the single canonical product plan.** PR #931—the original Codex product-plan PR after the Claude rebuild was folded into it—merged to `main` on 2026-08-31. PR #945 is the open follow-up against that merged version; it carries the consolidation proof and the evidence-validated PR #924 dependency gates. PR #924 remains the separate issue-to-workstream governance manifest, not a competing product plan.

| PR / branch | Role | Current state at 2026-08-31 |
|---|---|---|
| [#931](https://github.com/TeneikaAskew/stocks/pull/931) (`work-product-plan`) | Original Codex plan, rebuilt and consolidated with Claude's branch | **MERGED** — canonical baseline on `main` (`c93197e`) |
| [#945](https://github.com/TeneikaAskew/stocks/pull/945) (`codex/product-plan-preservation-audit`) | Follow-up to the merged #931 plan: preservation proof, validated gates, current traceability | **OPEN** — must merge for the newest corrections to reach `main` |
| [#924](https://github.com/TeneikaAskew/stocks/pull/924) (`work`) | Audit finding → issue → delivery-workstream manifest | **MERGED** as `a8e3075`; authoritative manifest on `main`, not a second product plan |
| `claude/stocks-plan-feedback-ipzxm0` | Evidence-backed rebuild source folded into #931 | **SUPERSEDED provenance branch**; no longer maintained |

Authority is therefore: **merged `docs/product/` → capability status and roadmap; #924 manifest → audit issue/workstream assignment; GitHub issues/PRs and current code/deployment → underlying evidence.** Until #945 merges, its changes are the reviewed follow-up candidate, not yet default-branch state. A conflict is resolved by updating `docs/product/` from underlying evidence rather than maintaining another plan copy.

### Consolidation verification

The canonical tree was compared directly with `claude/stocks-plan-feedback-ipzxm0` at
`826ca94`. No feature, requirement, screen, job, data domain, model, decision, issue, or PR record
was removed. Differences are limited to corrections and superseding state: canonical ownership,
the filed #943 security issue, current issue counts, multiline endpoint coverage, three confirmed
derived-table producers, and removal of the resolved "which plan is canonical" question. The PR
#924 manifest was separately cross-checked: every issue reference is retained in
[12](12-PR-ISSUE-TRACEABILITY.md), including its ten closed duplicate-to-canonical links. PR #924
remains linked rather than copied wholesale so one manifest, not two, owns workstream membership.

## Governance contract

**Evidence tags:** `VERIFIED — CODE`, `VERIFIED — TEST`, `VERIFIED — DEPLOYMENT`,
`VERIFIED — GITHUB`, `CLAIMED — DOCUMENTATION`, `PROPOSED — TARGET`,
`UNKNOWN / NEEDS HISTORY TRACE`. Current code and deployed configuration outrank narrative
documentation. Where deployment config and source defaults disagree, **both** are recorded
(worked example: `AUTH_MODE` in [09](09-SECURITY-AUTH.md)).

**Capability status:** Production · Production but needs remediation · Shadow · Experimental ·
Research · Incomplete · Planned · Deprecated · Dormant · Broken · Retire candidate.  
**Model status:** Production · Shadow · Experimental · Research · Failed · Retest Required ·
Invalidated · Archived · Retired.

**Monitoring fields.** Every capability record in [02](02-FEATURE-CATALOG.md) carries Owner,
Status, Priority, Target Phase, Target Release, Last Reviewed, Evidence Status, Blocking Issues
and Next Action — `TBD` where genuinely unknown, never omitted. A PR that changes behavior
updates the catalog row, the traceability entry, the evidence tag and the review date.

### Known environment limitation

This plan was reconstructed from a **shallow clone** (`git rev-parse --is-shallow-repository`
→ `true`; history reaches only `c819a6c`, 2026-07-13, PR #734). PR lineage therefore comes from
the GitHub API over **#184–#932**, classified by title, not from `git log --follow` or
changed-file inspection. Attribution before #184 is `UNKNOWN / NEEDS HISTORY TRACE`. Anyone
deepening the clone or paging further back should upgrade those rows — see
[12](12-PR-ISSUE-TRACEABILITY.md) for the procedure.

## Master traceability matrix

26 capabilities. Every Code, Tests, Issue and PR cell points at the **specific** evidence
for that row — the previous revision emitted one identical document-level link per column.

| ID | Area | Feature | UI | Backend | Data | Model | Code | Tests | Blockers | PRs | Status | Pri |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [FEAT-AUTH-001](02-FEATURE-CATALOG.md#feat-auth-001) | Authentication | Protected application access | SignInScreen / AuthGate | middleware `auth.py`, `/api/me` | identity/config | Firebase / IAP | `platform/api/auth.py` | `platform/tests/auth-gate.spec.ts` | [#830](https://github.com/TeneikaAskew/stocks/issues/830) [#850](https://github.com/TeneikaAskew/stocks/issues/850) [#911](https://github.com/TeneikaAskew/stocks/issues/911) | [#623](https://github.com/TeneikaAskew/stocks/pull/623) [#674](https://github.com/TeneikaAskew/stocks/pull/674) [#677](https://github.com/TeneikaAskew/stocks/pull/677) | Production but needs remediation | P0 |
| [FEAT-WAITLIST-001](02-FEATURE-CATALOG.md#feat-waitlist-001) | Landing / waitlist | Public entry + waitlist capture | `/` | `/api/waitlist` | `waitlist_signups` | — | `platform/src/routes/LandingPage.tsx` | `landing.spec.ts` | — | UNKNOWN | Production | P3 |
| [FEAT-MARKET-001](02-FEATURE-CATALOG.md#feat-market-001) | Market dashboard | Daily market brief + movement read | `/dashboard` | `/api/dashboard`, `/api/movement-statement` | `market_data_daily`, `premarket_analysis` | MODEL-BRIEF-001 | `platform/src/routes/DashboardPage.tsx` | `dashboard.spec.ts` | — | [#649](https://github.com/TeneikaAskew/stocks/pull/649) [#732](https://github.com/TeneikaAskew/stocks/pull/732) [#729](https://github.com/TeneikaAskew/stocks/pull/729) [#733](https://github.com/TeneikaAskew/stocks/pull/733) | Production but needs remediation | P0 |
| [FEAT-LIVE-001](02-FEATURE-CATALOG.md#feat-live-001) | Intraday monitoring | Live quotes, indicators, STRAT state | `/live` | `/api/live` | `market_data_intraday` | MODEL-IND-001, MODEL-STRAT-001 | `platform/src/routes/LiveMarketPage.tsx` | `live-market.spec.ts` | — | UNKNOWN | Production but needs remediation | P0 |
| [FEAT-CHART-001](02-FEATURE-CATALOG.md#feat-chart-001) | Charting | Instrument / timeframe analysis | `/charts` | `/api/live/history`, `/api/options/*/grid` | `market_data_daily`, `market_data_intraday` | MODEL-STRAT-001, MODEL-LEVEL-001 | `platform/src/routes/ChartsPage.tsx` | `charts-cards.spec.ts` | — | UNKNOWN | Production but needs remediation | P1 |
| [FEAT-OPTION-001](02-FEATURE-CATALOG.md#feat-option-001) | Options / gamma | Flow, Greeks, GEX grid | `/options` | `/api/options`, `/api/grid` | `etf_options_snapshots`, `intraday_gex_15m`, `realtime_gex_15m` | MODEL-GAMMA-001, MODEL-OPT-001 | `platform/src/routes/OptionsFlowPage.tsx` | `options-flow.spec.ts` | [#826](https://github.com/TeneikaAskew/stocks/issues/826) [#825](https://github.com/TeneikaAskew/stocks/issues/825) [#812](https://github.com/TeneikaAskew/stocks/issues/812) | [#255](https://github.com/TeneikaAskew/stocks/pull/255) [#536](https://github.com/TeneikaAskew/stocks/pull/536) [#640](https://github.com/TeneikaAskew/stocks/pull/640) [#791](https://github.com/TeneikaAskew/stocks/pull/791) | Retest Required | P0 |
| [FEAT-SIGNAL-001](02-FEATURE-CATALOG.md#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | MODEL-MOM-001, MODEL-MR-001, MODEL-AGREE-001, MODEL-EXIT-001 | `lib/signals.py` | `signals.spec.ts` | [#816](https://github.com/TeneikaAskew/stocks/issues/816) [#815](https://github.com/TeneikaAskew/stocks/issues/815) [#928](https://github.com/TeneikaAskew/stocks/issues/928) | [#184](https://github.com/TeneikaAskew/stocks/pull/184) [#326](https://github.com/TeneikaAskew/stocks/pull/326) [#785](https://github.com/TeneikaAskew/stocks/pull/785) [#803](https://github.com/TeneikaAskew/stocks/pull/803) | Production but needs remediation | P0 |
| [FEAT-PLAYBOOK-001](02-FEATURE-CATALOG.md#feat-playbook-001) | Premarket / playbook | Structured daily setups | `/playbook` | `/api/playbook` | `premarket_analysis`, `playbook_cards` | MODEL-BRIEF-001, MODEL-LEVEL-001 | `platform/src/routes/PlaybookPage.tsx` | `playbook.spec.ts` | [#861](https://github.com/TeneikaAskew/stocks/issues/861) | [#444](https://github.com/TeneikaAskew/stocks/pull/444) [#620](https://github.com/TeneikaAskew/stocks/pull/620) [#774](https://github.com/TeneikaAskew/stocks/pull/774) | **Broken** | P0 |
| [FEAT-STRAT-001](02-FEATURE-CATALOG.md#feat-strat-001) | STRAT / levels | Candle classification, FTFC, structural levels | `/charts`, `/live` | via `lib/` | `strat_levels`, `strat_combo_results` | MODEL-STRAT-001, MODEL-FTFC-001, MODEL-LEVEL-001 | `lib/strat.py` | `tests/test_strat*.py` | [#908](https://github.com/TeneikaAskew/stocks/issues/908) [#866](https://github.com/TeneikaAskew/stocks/issues/866) [#907](https://github.com/TeneikaAskew/stocks/issues/907) | [#242](https://github.com/TeneikaAskew/stocks/pull/242) [#244](https://github.com/TeneikaAskew/stocks/pull/244) [#796](https://github.com/TeneikaAskew/stocks/pull/796) [#799](https://github.com/TeneikaAskew/stocks/pull/799) | Production but needs remediation | P0 |
| [FEAT-IND-001](02-FEATURE-CATALOG.md#feat-ind-001) | Indicators | RVOL, ORB, ATR, RSI, VWAP | `/live`, `/charts` | via `lib/` | `market_data_*` | MODEL-IND-001 | `lib/indicators.py` | `tests/test_indicators*.py` | [#894](https://github.com/TeneikaAskew/stocks/issues/894) [#892](https://github.com/TeneikaAskew/stocks/issues/892) [#870](https://github.com/TeneikaAskew/stocks/issues/870) | UNKNOWN | Production but needs remediation | P1 |
| [FEAT-INSIGHT-001](02-FEATURE-CATALOG.md#feat-insight-001) | AI insights | LLM per-ticker reports + chat | `/insights` | `/api/insights` (13) | `insight_reports`, `insight_runs`, `model_routing` | 14 LLM nodes — see [08](08-AI-AGENT-ARCHITECTURE.md) | `lib/agents/` | `insights.spec.ts` | [#827](https://github.com/TeneikaAskew/stocks/issues/827) [#867](https://github.com/TeneikaAskew/stocks/issues/867) [#916](https://github.com/TeneikaAskew/stocks/issues/916) | [#450](https://github.com/TeneikaAskew/stocks/pull/450) [#362](https://github.com/TeneikaAskew/stocks/pull/362) [#451](https://github.com/TeneikaAskew/stocks/pull/451) | Experimental | P2 |
| [FEAT-CATALYST-001](02-FEATURE-CATALOG.md#feat-catalyst-001) | Earnings / catalysts | Events, reactions, news, filings | `/catalysts` | `/api/catalysts`, `/api/earnings` | `earnings_*`, `economic_events`, `news_sentiment`, `sec_filings` | MODEL-EARN-001 | `platform/api/routers/catalysts.py` | `catalysts.spec.ts` | — | [#220](https://github.com/TeneikaAskew/stocks/pull/220) [#514](https://github.com/TeneikaAskew/stocks/pull/514) [#532](https://github.com/TeneikaAskew/stocks/pull/532) | Production but needs remediation | P1 |
| [FEAT-REPORT-001](02-FEATURE-CATALOG.md#feat-report-001) | Reports / analytics | Backtest + walk-forward results | `/reports` | `/api/analytics`, `/api/backtest` | `backtest_*`, `walk_forward_results` | MODEL-CALIB-001, MODEL-STYLE-001 | `platform/src/routes/ReportsPage.tsx` | `reports.spec.ts` | — | UNKNOWN | Production but needs remediation | P1 |
| [FEAT-REPLAY-001](02-FEATURE-CATALOG.md#feat-replay-001) | Replay / backtest engine | Point-in-time replay + evaluation | `/reports` | `/api/backtest/replay-trades` | `backtest_*`, `signal_alerts` | — | `lib/backtest.py` | `replay-trainer.spec.ts` | [#824](https://github.com/TeneikaAskew/stocks/issues/824) [#823](https://github.com/TeneikaAskew/stocks/issues/823) [#822](https://github.com/TeneikaAskew/stocks/issues/822) | [#210](https://github.com/TeneikaAskew/stocks/pull/210) [#319](https://github.com/TeneikaAskew/stocks/pull/319) [#519](https://github.com/TeneikaAskew/stocks/pull/519) [#694](https://github.com/TeneikaAskew/stocks/pull/694) | **Invalidated** | P0 |
| [FEAT-MODEL-001](02-FEATURE-CATALOG.md#feat-model-001) | Models / research | Predictive + calibration systems | `/admin` | `/api/magnitude`, `/api/admin/strat-engine` | `ticker_calibration`, `user_style_results` | see [07](07-MODEL-REGISTRY.md) | `gcp/research/` | `tests/test_walk_forward*.py` | [#817](https://github.com/TeneikaAskew/stocks/issues/817) [#813](https://github.com/TeneikaAskew/stocks/issues/813) [#910](https://github.com/TeneikaAskew/stocks/issues/910) | [#355](https://github.com/TeneikaAskew/stocks/pull/355) [#591](https://github.com/TeneikaAskew/stocks/pull/591) [#735](https://github.com/TeneikaAskew/stocks/pull/735) [#811](https://github.com/TeneikaAskew/stocks/pull/811) | **Invalidated / Failed** (mixed) | P0 |
| [FEAT-JOURNAL-001](02-FEATURE-CATALOG.md#feat-journal-001) | Journal / portfolio | Per-user trade record + import | `/journal` | `/api/journal` (9) | `trades`, `journal_entries` | MODEL-STYLE-001 | `platform/src/routes/JournalPage.tsx` | `journal.spec.ts` | [#722](https://github.com/TeneikaAskew/stocks/issues/722) [#717](https://github.com/TeneikaAskew/stocks/issues/717) [#716](https://github.com/TeneikaAskew/stocks/issues/716) | [#626](https://github.com/TeneikaAskew/stocks/pull/626) [#718](https://github.com/TeneikaAskew/stocks/pull/718) [#720](https://github.com/TeneikaAskew/stocks/pull/720) [#764](https://github.com/TeneikaAskew/stocks/pull/764) | Production but needs remediation | P1 |
| [FEAT-ALERT-001](02-FEATURE-CATALOG.md#feat-alert-001) | Alerts / Discord | Signal + brief delivery | — | `gcp/discord_interactions/` | `signal_alerts` | — | `gcp/discord_interactions/main.py` | `tests/test_notifier*.py` | — | UNKNOWN | Production but needs remediation | P1 |
| [FEAT-ADMIN-001](02-FEATURE-CATALOG.md#feat-admin-001) | Administration | Operator surface | `/admin` | `/api/admin` (7), `/api/config` | `model_routing` | — | `platform/src/routes/AdminPage.tsx` | `admin.spec.ts` | — | UNKNOWN | Production but needs remediation | P2 |
| [FEAT-HELP-001](02-FEATURE-CATALOG.md#feat-help-001) | Help / glossary | Term reference | `/help` | `/api/glossary/gamma` | — | — | `platform/src/routes/HelpPage.tsx` | `help.spec.ts` | — | UNKNOWN | Production | P3 |
| [FEAT-SETTINGS-001](02-FEATURE-CATALOG.md#feat-settings-001) | Settings | Device-local appearance/layout | `/settings` | **none — `localStorage`** | **none** | — | `platform/src/routes/SettingsPage.tsx` | **none** | — | UNKNOWN | Incomplete | P3 |
| [FEAT-DATA-001](02-FEATURE-CATALOG.md#feat-data-001) | Data platform | Ingestion, storage, freshness | — | fetcher jobs | 64 relations — see [06](06-DATA-ARCHITECTURE.md) | — | `gcp/fetchers/` | `tests/test_data_loader*.py` | [#926](https://github.com/TeneikaAskew/stocks/issues/926) [#925](https://github.com/TeneikaAskew/stocks/issues/925) [#863](https://github.com/TeneikaAskew/stocks/issues/863) | [#205](https://github.com/TeneikaAskew/stocks/pull/205) [#518](https://github.com/TeneikaAskew/stocks/pull/518) [#760](https://github.com/TeneikaAskew/stocks/pull/760) | Production but needs remediation | P0 |
| [FEAT-DEPLOY-001](02-FEATURE-CATALOG.md#feat-deploy-001) | Infrastructure / deploy | 67 jobs, 58 schedulers, Cloud Run | — | — | — | — | `gcp/deploy.sh` | static checks only | [#835](https://github.com/TeneikaAskew/stocks/issues/835) [#834](https://github.com/TeneikaAskew/stocks/issues/834) [#833](https://github.com/TeneikaAskew/stocks/issues/833) | [#507](https://github.com/TeneikaAskew/stocks/pull/507) | Production but needs remediation | P1 |
| [FEAT-OPS-001](02-FEATURE-CATALOG.md#feat-ops-001) | Operations / reliability | Freshness, telemetry, DR | `/admin` | `/api/health/freshness` | `job_runs` | — | `gcp/freshness_watchdog.py` | `data-pipeline-status.spec.ts` | [#922](https://github.com/TeneikaAskew/stocks/issues/922) [#920](https://github.com/TeneikaAskew/stocks/issues/920) [#930](https://github.com/TeneikaAskew/stocks/issues/930) [#944](https://github.com/TeneikaAskew/stocks/issues/944) | [#189](https://github.com/TeneikaAskew/stocks/pull/189) [#235](https://github.com/TeneikaAskew/stocks/pull/235) [#494](https://github.com/TeneikaAskew/stocks/pull/494) [#771](https://github.com/TeneikaAskew/stocks/pull/771) | Incomplete | P1 |
| [FEAT-CICD-001](02-FEATURE-CATALOG.md#feat-cicd-001) | CI / testing | Build, test, deploy automation | — | — | — | — | `.github/workflows/` | 230 python tests | [#848](https://github.com/TeneikaAskew/stocks/issues/848) [#846](https://github.com/TeneikaAskew/stocks/issues/846) [#845](https://github.com/TeneikaAskew/stocks/issues/845) | [#364](https://github.com/TeneikaAskew/stocks/pull/364) [#378](https://github.com/TeneikaAskew/stocks/pull/378) | Production but needs remediation | P1 |
| [FEAT-UI-001](02-FEATURE-CATALOG.md#feat-ui-001) | Web / UI shell | Nav, shell, responsive, a11y | all | — | — | — | [solyra `src/App.tsx`](https://github.com/TeneikaAskew/solyra/blob/main/src/App.tsx) | [solyra `tests/navigation.spec.ts`](https://github.com/TeneikaAskew/solyra/blob/main/tests/navigation.spec.ts) | [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) | [#546](https://github.com/TeneikaAskew/stocks/pull/546) [#611](https://github.com/TeneikaAskew/stocks/pull/611) [#703](https://github.com/TeneikaAskew/stocks/pull/703) [#715](https://github.com/TeneikaAskew/stocks/pull/715) | Production but needs remediation | P2 |
| [FEAT-DEBT-001](02-FEATURE-CATALOG.md#feat-debt-001) | Technical debt | Legacy retirement | — | — | — | — | `scripts/` | — | [#917](https://github.com/TeneikaAskew/stocks/issues/917) [#841](https://github.com/TeneikaAskew/stocks/issues/841) [#921](https://github.com/TeneikaAskew/stocks/issues/921) | UNKNOWN | Retire candidate | P3 |

## Related planning artifacts

This plan owns capability trust status and the roadmap. Two adjacent artifacts own questions it
deliberately does not answer, and the three are reconciled in
[12](12-PR-ISSUE-TRACEABILITY.md#reconciliation-with-the-audit-remediation-workstream):

- [#924](https://github.com/TeneikaAskew/stocks/pull/924) — the canonical 105-issue inventory across 18 delivery streams.
- [#941](https://github.com/TeneikaAskew/stocks/pull/941) — which issues actually have a remediation PR. Merged into the #924 stack 2026-08-30. Since then #933 and #934 landed on `main`; **#818 is closed with its Definition of done met in full**, and #816 correctly remains open.

## Snapshot

| Metric | Value |
|---|---|
| Capabilities | 26 |
| Routed screens | 15 |
| API endpoints | 92 platform + 2 Discord |
| Cloud Run jobs / schedulers | 67 / 58 |
| Database relations | 64 (62 tables + 2 materialized views) |
| Models + LLM nodes | 21 registry entries + 14 routed LLM nodes |
| Open issues mapped | 121 of 121 (= 104 canonical audit + 13 pre-audit + 4 post-audit/ops) |
| PRs mapped | 151 significant, #184–#932 |
| Tests | 230 python · 29 Playwright · 27 Vitest |
| Capabilities at Production (unqualified) | **2 of 25** (Landing, Help) |
