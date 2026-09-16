# Documentation registry

**Last reviewed:** 2026-09-16 · **Depth:** verified · **Against:** `aa60569` · **Owner:** TBD

Which documents this repo maintains, who owns each one, and what code each one
describes. `scripts/maintenance/docs_audit.py` reads the table below; the prose
around it is for humans and is ignored by the parser.

## Why classes

A single "is this doc fresh?" rule produces wrong answers, because four kinds of
document live under `docs/` and each one fails differently:

| Class | Meaning | What the audit does |
|---|---|---|
| **A** | **Machine-owned.** A job regenerates it (the monthly refresh, `doc_inventory.py`). | Audits it, writes nothing into it, and **routes** the fix. Also checks the owning job actually **delivered** — see below. |
| **B** | **Frozen.** A deliberate hand-maintained snapshot. | Nothing. Never read as current, never written. |
| **X** | **Out of scope.** Agent and command instructions, templates. Not product documentation. | Nothing. Distinct from unclassified, which means the registry has a gap. |
| **C** | **Dated record.** An audit, incident, changelog, research write-up or design record whose whole purpose is to state what was true on its date. | Read for cross-references only. **Never re-dated, never rewritten** — rewriting a dated record destroys the record. May receive an *appended*, dated status block. |
| **D** | **Living.** Describes the system as it is now. | Full audit: review marker, issue/PR citations, links, and drift against the code it declares. |

### Class A is audited, not skipped

An owning job existing is not evidence the doc is current. On 2026-09-16 the
September refresh PR (#1060) had been open and unmerged for 8 days, three
earlier "Monthly architecture doc refresh failed" PRs (#963, #1012, #1021) were
closed without merging, and the workflow had failed five consecutive runs on
2026-09-09 — while `05-a`/`05-c` still advertised `Generated 2026-09-07`. A
`Generated` stamp records when a job *ran*, not that its output ever landed.

And a job that succeeds still proves nothing about truth: the refresh
regenerates counts from live GCP and has a model rewrite prose **in place**,
while `check_generated_docs.py` gates churn, headings, links and marker-block
byte-equality. None of that reads the code. Class A prose gets the same scrutiny
as Class D; only the write path differs.

Route a Class A fix to its owner, never into a Class D branch:

| Defect | Fix goes to |
|---|---|
| Prose the model wrote wrong | `.github/prompts/{architecture,data-dependencies,cost-analysis}.md` |
| A count or inventory error | `scripts/maintenance/doc_inventory.py` + its tests |
| Job ran but its PR never merged | Land the PR. Do not hand-stamp the doc. |
| Anything else | A separate Class-A-only PR, flagged to be re-applied if the next refresh overwrites it |

Never edit inside `<!-- inventory:*:start/end -->` (the byte-equality gate fails
the refresh), never bump a `Generated <date>` footer, and never mix Class A into
a Class D branch — the refresh's stray-write scan refuses edits outside
`05-a 05-c 05-d`.

## The review marker

Living docs carry one line, as the first paragraph after the H1:

```
**Last reviewed:** YYYY-MM-DD · **Depth:** verified|scanned · **Against:** `<sha>` · **Owner:** TBD
```

`verified` means the claims were re-read against the code, the issues or live
state **in that run**, with the evidence recorded in the PR. `scanned` means only
the mechanical checks ran. `scanned` is the honest default; CLAUDE.md §3.11 says
a doc is a claim and not evidence, and a review date bumped without a re-read is
exactly the failure that rule exists to prevent. `Against:` pins the `origin/main`
commit reviewed against, so the next run diffs from a commit rather than guessing
from a date.

## Registry

`Declared code paths` drives the drift check: when those paths gain content
commits after the doc's `Against:` SHA, the doc is queued for re-review. Pure
renames are ignored, so a file-move wave does not flag every document.

| Class | Path glob | Declared code paths |
|---|---|---|
| A | README.md | gcp/deploy.sh, gcp/schema.sql |
| A | Architecture.drawio | gcp/deploy.sh |
| A | Architecture-icons.drawio | gcp/deploy.sh |
| A | docs/product/infrastructure/05-a-ARCHITECTURE.md | gcp/deploy.sh, gcp/schema.sql, platform/api |
| A | docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md | gcp/schema.sql, gcp/fetchers |
| A | docs/product/infrastructure/05-d-COST_ANALYSIS.md | gcp/deploy.sh |
| A | docs/product/infrastructure/05-e-API.md | platform/api |
| A | docs/INVESTMENT_MODELS_SUMMARY.md | lib/strategies |
| B | docs/product/infrastructure/manual/* | |
| C | docs/archive/* | |
| C | docs/audit/* | |
| C | docs/audits/* | |
| C | docs/incidents/* | |
| C | docs/research/* | |
| C | docs/replays/* | |
| C | docs/changelog/* | |
| C | docs/superpowers/* | |
| C | docs/plans/* | |
| C | docs/analysis/* | |
| C | archive/* | |
| C | docs/PLATFORM_AUDIT_*.md | |
| C | docs/TEST_SUITE_AUDIT_*.md | |
| C | docs/MAGNITUDE_DIRECTIONAL_SESSION_HANDOFF.md | |
| C | docs/BSVP_VALIDATION_RESULTS.md | |
| C | docs/DIRECTION_*.md | |
| C | docs/EXEC_BACKTEST_RESULTS.md | |
| C | docs/OPTIONS_EXEC_BACKTEST_RESULTS.md | |
| C | docs/MAGNITUDE_ENGINE_RESULTS.md | |
| C | docs/long_only_findings.md | |
| C | BACKTEST_RESULTS.md | |
| D | CLAUDE.md | .claude, gcp/deploy.sh |
| D | RUNBOOK.md | gcp/deploy.sh, gcp/database.py |
| D | SETUP.md | .github/workflows |
| D | QUICK_REFERENCE.md | scripts, gcp/deploy.sh |
| D | DASHBOARD_SPEC.md | platform/api |
| D | docs/product/README.md | |
| D | docs/product/00-PRODUCT-OVERVIEW.md | |
| D | docs/product/01-PRODUCT-REQUIREMENTS.md | |
| D | docs/product/02-FEATURE-CATALOG.md | lib, platform/api, gcp |
| D | docs/product/04-BACKEND-API.md | platform/api |
| D | docs/product/05-INFRASTRUCTURE.md | gcp/deploy.sh |
| D | docs/product/06-DATA-ARCHITECTURE.md | gcp/schema.sql |
| D | docs/product/07-MODEL-REGISTRY.md | lib/strategies, lib/agents, gcp/research |
| D | docs/product/08-AI-AGENT-ARCHITECTURE.md | lib/agents |
| D | docs/product/09-SECURITY-AUTH.md | platform/api/auth.py, platform/deploy.sh |
| D | docs/product/10-OPERATIONS-RELIABILITY.md | gcp/deploy.sh |
| D | docs/product/11-CODE-TRACEABILITY.md | lib, platform/api |
| D | docs/product/12-PR-ISSUE-TRACEABILITY.md | |
| D | docs/product/13-ROADMAP.md | |
| D | docs/product/14-WORK-BREAKDOWN.md | |
| D | docs/product/15-OPEN-DECISIONS.md | |
| D | docs/product/16-CONSOLIDATION-AUDIT.md | |
| D | docs/product/infrastructure/05-b-ERD.md | gcp/schema.sql |
| D | docs/product/infrastructure/05-f-PIPELINE.md | gcp/fetchers, gcp/deploy.sh |
| D | docs/product/infrastructure/05-g-DATA_PIPELINE.md | gcp/fetchers, gcp/schema.sql |
| D | docs/product/infrastructure/05-h-DATA_DICTIONARY.md | gcp/schema.sql |
| D | docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md | lib |
| D | docs/product/infrastructure/05-j-GCP_IMPLEMENTATION_STATUS.md | lib, gcp |
| D | docs/product/infrastructure/05-k-FAILURE_NOTIFIER_DEPLOYMENT.md | gcp/failure_notifier.py |
| D | docs/product/infrastructure/05-l-INFRASTRUCTURE_NOTES.md | gcp/deploy.sh |
| D | docs/DOC_REGISTRY.md | scripts/maintenance/docs_audit.py |
| D | docs/AUTH_EMAILS.md | platform/api/auth.py |
| D | docs/EARNINGS_PIPELINE.md | gcp/fetchers |
| D | docs/RUNBOOK_BACKFILL.md | scripts |
| D | docs/STRAT_ENGINE_OPERATIONS.md | gcp/research/strat_engine |
| D | docs/STRAT_ENGINE_ARCHITECTURE.md | gcp/research/strat_engine |
| D | docs/STRAT_ENGINE_ERD.md | gcp/research/strat_engine |
| D | docs/STRAT_METHODOLOGY.md | lib/strat.py |
| D | docs/STRUCTURE_BRIEF_DESIGN.md | platform/api/routers/admin.py |
| D | docs/STRAT_IMPLEMENTATION_PLAN.md | lib/strat.py |
| D | docs/DISCORD_BOT_SETUP.md | scripts/discord |
| D | docs/GOOGLE_SHEETS_SETUP.md | |
| D | docs/CLAUDE_CODE_ON_WEB.md | .claude, .github/workflows |
| D | docs/claude-code-codespaces-auth.md | |
| D | docs/storage_overview.md | gcp/schema.sql |
| D | docs/gamma_levels.md | lib/options |
| D | docs/premarket_brief_cards.md | gcp/premarket_brief.py |
| D | docs/indicator_updates_summary.md | lib/indicators.py |
| D | docs/options_chain_guide.md | lib/options |
| D | docs/QUICK_START_OPTIONS.md | lib/options |
| D | docs/README_OPTIONS.md | lib/options |
| D | docs/alpha-vantage-*.md | gcp/fetchers |
| D | docs/quick_reference_card.md | |
| D | docs/trading_rules_and_alerts.md | alert_config.json |
| D | docs/Morning Checklist Updated.md | |
| D | docs/EXPERIMENT_REGISTRY.md | gcp/research |
| D | docs/RESEARCH_COMPENDIUM.md | gcp/research |
| D | docs/MODEL_REGISTRY.md | lib/strategies |
| D | docs/MODEL_CATALOG.md | |
| D | docs/MODELS_END_TO_END.md | |
| D | docs/MODEL_SUMMARY.md | |
| D | docs/MODEL_RETHINK_PLANS.md | lib/strategies |
| D | docs/models/*.md | lib/strategies |
| D | docs/STRAT_ENGINE_AND_COMBO_PIPELINE.md | gcp/research/strat_engine |
| D | docs/BRIEFING_DECK.md | |
| D | docs/FEATURE_ADOPTION_ROADMAP.md | |
| D | docs/HARDCODED_VALUES_REMEDIATION.md | lib |
| D | .github/workflows/README.md | .github/workflows |
| D | .github/prompts/*.md | scripts/maintenance/doc_inventory.py |
| D | platform/GCP_DATA_DICTIONARY.md | platform/api |
| D | platform/PLATFORM_PLAN.md | platform/api |
| D | gcp/cloudbuild/README.md | gcp/cloudbuild |
| D | gcp/queries/README.md | gcp/queries |
| D | gcp/research/*/README.md | gcp/research |
| D | gcp/research/*/*.md | gcp/research |
| D | lib/*/README.md | lib |
| D | insights/*.md | insights |
| D | reports/README.md | |
| D | scripts/research/README.md | scripts/research |
| D | tradingview-pine-scripts/*.md | tradingview-pine-scripts |
| X | .claude/agents/*.md | |
| X | .claude/commands/*.md | |
| X | .github/pull_request_template.md | |
| X | AGENTS.md | |
