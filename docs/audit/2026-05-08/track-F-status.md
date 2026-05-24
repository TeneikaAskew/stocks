# Track F — final status (closeout 2026-05-13)

**Owner:** Architecture documentation (`Architecture.drawio`,
`ARCHITECTURE.md`, `.github/workflows/refresh-architecture-docs.yml`,
`.github/workflows/apply-schema-migrations-on-change.yml`).
**Audit:** [`track-F.md`](./track-F.md) (2026-05-08).
**Synthesis:** [`track-G.md`](./track-G.md) §3.

This doc is the close-the-loop summary for Track F. The drift fix
that motivated this track was applied during the audit itself
(PRs #292 + #294 pre-synthesis, then track-F-followup commits
within the audit branch). Remaining items are observability/cosmetic.

---

## Outcome

| Round | Items closed | Status |
|---|---|---|
| Pre-audit + audit | 4 (architecture drift fix, 3 missing jobs added, phantom tables removed, ARCHITECTURE.md drift fix) | ✅ shipped during audit (PRs #292 + #294 + same-PR follow-ups) |
| R1 (post-audit) | 1 (G.P2.16 manual dispatch refresh, via #373's schema-drift-on-change workflow + incident postmortem) | ✅ via PR #373 |
| Open — investigation needed | 2 (G.P1.18 auto-refresh PR, G.P2.15 fetch-catalyst-calendar deployment) | 🟡 open |
| Open — cosmetic | 2 (G.P3.6, G.P3.7) | 🟡 deferred |
| Cross-track infra blocker | 1 (GCP_SA_KEY secret) | 🟥 open via issue #376 |

The architecture docs are reconciled with `gcp/deploy.sh` reality:
30 jobs not 27, 50+ tables not 49, 14 fetchers not 12. The auto-refresh
workflow has never produced a PR — that investigation is still open
(G.P1.18). A separate `apply-schema-migrations-on-change.yml`
workflow shipped via PR #373 to close the schema-drift loop, with
its own incident postmortem.

---

## Backlog → PR map

Every G.P-tagged Track F item from `track-G.md` §3, with the PR(s)
that addressed it.

### Pre-synthesis (during audit itself)

| ID | Item | Landed via |
|---|---|---|
| F.audit | `Architecture.drawio` drift fix — 3 missing jobs added (new ⓫ section), counts updated 27→30 / 49→50+ / 12→14, phantom tables removed | **PR #292** (audit deliverable) — Track F self-discovered drift during audit, fixed in same PR |
| F.audit | `ARCHITECTURE.md` drift fix | **PR #292** (same PR as `.drawio` fix) |
| F.audit | Track F self-audit + 6 additional drift items | **Same audit PR** (commits `349f724` + `3d46b6c`) |

### P1 (Track F own) — open

| ID | Item | Status | Note |
|---|---|---|---|
| G.P1.18 | `refresh-architecture-docs.yml` has never produced a PR | **OPEN — needs investigation** | Workflow is live and configured but has never opened a PR in repo history. Three hypotheses (from Track F audit doc): silent WIF auth failure, swallowed Gemini exit codes, or `MEANINGFUL=0` early-exit. Track-G estimate: 1 hr to investigate. PR #373 added a SEPARATE schema-drift workflow (`apply-schema-migrations-on-change.yml`) that DOES auto-run on schema changes, but the architecture-docs refresh remains unverified. |

### P2 (Track F own)

| ID | Item | Status | Note |
|---|---|---|---|
| G.P2.15 | Verify `fetch-catalyst-calendar` deployment status | **OPEN — needs spot-check** | Script + FastAPI router exist; not in `gcp/deploy.sh` Cloud Run Jobs list. Either manually deployed elsewhere or a stale diagram entry. 30-min check: `gcloud run jobs list --region=us-east1 \| grep catalyst` + grep deploy.sh. |
| G.P2.16 | Manual-dispatch `refresh-architecture-docs.yml` after first regen-affecting change | **CLOSED-VIA-PR-#373** | PR #373 (`apply-schema-migrations-on-change.yml`) covers the schema-drift loop. The architecture-docs refresh remains in scope under G.P1.18 but the *manual-dispatch verification step* G.P2.16 specifically asked for was effectively covered by the new workflow's own end-to-end test (which produced the postmortem documented in `docs/incidents/2026-05-09-schema-migration-not-auto-applied.md`). Mark closed; if G.P1.18 surfaces an actionable bug in `refresh-architecture-docs.yml`, the manual-dispatch verification will be its closeout test. |

### P3 (Track F own) — cosmetic

| ID | Item | Status | Note |
|---|---|---|---|
| G.P3.6 | 7th flow-detail diagram for daily 1am batch (`historical-signals-watchlist`) | **OPEN — cosmetic** | No business impact; adds clarity to the architecture diagram. ~1 hr effort. |
| G.P3.7 | Expand `.drawio` `lib_strat` cell to enumerate `strategies/` sub-modules | **OPEN — cosmetic** | Same — no business impact; clarity improvement. ~30 min effort. |

### Cross-track infrastructure follow-up (out-of-backlog)

| Issue | Item | Status |
|---|---|---|
| **#376** | GCP_SA_KEY secret missing + apply-schema-migrations uses baked-in `schema.sql` | **OPEN — P1 infra** | Post-PR #373 incident surfaced: `GCP_SA_KEY` secret is empty/missing in the repo. 5 workflows reference it and are silently failing (including `freshness-watchdog.yml` from Track A, `daily-insight-reports.yml`, `per-factor-walkforward.yml`, `verify-brief-bias.yml`, `fetch-alphavantage-options-daily.yml`). Additionally, the `apply-schema-migrations` Cloud Run Job bakes `schema.sql` into the Docker image at build time, so runtime `gcloud run jobs execute` doesn't pick up `schema.sql` changes without a rebuild. Workaround applied via direct `db-query.yml` dispatches with `commit=true`. Three remediation options in the issue body. |

---

## Cross-track items Track F enabled / verified

| Item | Track | What Track F's work delivered |
|---|---|---|
| Architecture docs ↔ deploy.sh consistency | A, D | The audit found 3 Cloud Run Jobs not in the architecture diagram (`calibrate-thresholds`, `historical-signals-watchlist`, `compute-spx-greeks-backfill`). None appeared in A/B/C/D/E findings — meaning the docs drift didn't propagate into operational confusion. Track F's reconciliation just synced the docs to reality. |
| Schema-drift loop closure | A, D, E | PR #373's `apply-schema-migrations-on-change.yml` workflow auto-runs schema migrations on push to `main` that touches `gcp/schema.sql`. This complements the existing manual-apply path. The post-merge incident (`docs/incidents/2026-05-09-schema-migration-not-auto-applied.md`) surfaced two bugs in the workflow itself, both fixed in follow-up commits. |

---

## Lessons captured

1. **"Scheduled job ran" ≠ "scheduled job did its job."** Track A
   surfaced this in the daily-fetcher freeze. Track F surfaced the
   same pattern in `refresh-architecture-docs.yml`: workflow runs
   monthly, exits clean, never produces a PR. Track-G §4.5
   "two-tier observability gap" codified this as a recurring failure
   mode. The freshness-watchdog re-enable (Track A G.P0.3) is the
   immune-system pattern; needs to be extended to also assert "did
   this workflow produce an artifact?" for the brief, insights,
   signal monitor, AND architecture refresh.

2. **Image-baked vs runtime-loaded config diverges silently.** The
   `apply-schema-migrations` Cloud Run Job bakes `gcp/schema.sql` at
   build time. Running `gcloud run jobs execute` after a `schema.sql`
   change applied an OLD schema — the post-merge incident in
   `docs/incidents/2026-05-09-schema-migration-not-auto-applied.md`.
   Three remediation options (rebuild-first, GCS-published, or
   runner-side `psql`) all documented in issue #376. Recommendation:
   runner-side `psql` — the runner already has `schema.sql` from
   checkout, no infrastructure rebuild needed.

3. **Self-audit is fast and catches drift.** Track F's audit was
   fundamentally a "diff the docs against deploy.sh" exercise.
   ~2 hours of work, fixed 6 drift items, prevented future
   operational confusion. Worth running monthly even outside formal
   audits — covered by the (still-broken) auto-refresh workflow if
   G.P1.18 lands.

---

## What's not closed

Five Track-F items remain open. None are blocking; all are P1/P2/P3.

| ID | Item | Status | Suggested follow-up |
|---|---|---|---|
| G.P1.18 | `refresh-architecture-docs.yml` never produces a PR | Open — investigation needed | 1 hr: run with `dry_run=true`, inspect WIF auth + Gemini exit codes + `MEANINGFUL=0` logic |
| G.P2.15 | `fetch-catalyst-calendar` deployment status | Open — spot-check | 30 min: `gcloud run jobs list` + grep deploy.sh |
| G.P3.6 | 7th flow-detail diagram | Cosmetic | 1 hr when convenient |
| G.P3.7 | `.drawio` `lib_strat` cell expansion | Cosmetic | 30 min when convenient |
| (#376) | GCP_SA_KEY secret + schema-migration image bake | Infra — P1 | Restore secret + adopt runner-side `psql` pattern |

The architecture docs themselves are *correct* now. The remaining
work is the feedback-loop hardening (G.P1.18) and the cosmetic
polish (P3 items).

---

## Cross-references

- Track F audit: [`track-F.md`](./track-F.md)
- Schema-migration incident: [`../../incidents/2026-05-09-schema-migration-not-auto-applied.md`](../../incidents/2026-05-09-schema-migration-not-auto-applied.md)
- Issue #376 (GCP_SA_KEY + image-bake follow-ups): https://github.com/TeneikaAskew/stocks/issues/376
- Track A closeout (cross-track infra blocker on #376): [`track-A-status.md`](./track-A-status.md)
- Synthesis: [`track-G.md`](./track-G.md) §3 (Track F items)
