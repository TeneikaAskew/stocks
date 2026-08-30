# Open Product Decisions

**Last reviewed:** 2026-08-30 · **Owner:** TBD

Every item is **PRODUCT DECISION REQUIRED**; no target implementation should silently resolve it.

| Decision | Why it matters / options requiring explicit choice | Evidence needed | Owner/by when |
|---|---|---|---|
| Product boundary | intelligence/education vs actionable recommendation vs execution | user promise, legal/risk review, observed workflows | TBD |
| Signal policy | which signals are informational, actionable, hidden, or retired | validated cohorts and user need | TBD |
| LLM authority | explanation only vs recommendations; numeric authority and veto rules | evaluation, error/risk tolerance | TBD |
| Production model roster | promote, shadow, retest, pause, remove | PIT-safe frozen results and runtime cost | TBD |
| User/tenancy model | single-user, allowlisted users, or multi-user; data sharing | ownership schema and privacy needs | TBD |
| Identity/perimeter standard | Firebase, IAP, both, local development constraints | deployment topology and operator model | TBD |
| Alert channels | Discord only vs additional channels and delivery guarantees | user demand, cost, privacy, reliability | TBD |
| Historical subsystem retirement | which replay engines/artifacts/research surfaces remain authoritative | consumer/history trace and reproducibility | TBD |
| Market/vendor contracts | authoritative source per domain and fallback behavior | SLA, licensing, quotas, timestamp semantics | TBD |
| SLO/RPO/RTO | numeric availability, latency, freshness and recovery objectives | usage windows, impact/cost analysis | TBD |
| Portfolio scope | journal only vs positions/exposure/risk portfolio | product boundary and ownership model | TBD |
| Which plan artifact is canonical | Three now carry plan state: PR [#931](https://github.com/TeneikaAskew/stocks/pull/931) (being updated by a second session as of `6019ec27`), this branch's rebuild, and [#924](https://github.com/TeneikaAskew/stocks/pull/924)'s stream manifest. The counts agree; the depth and the code-extracted inventories do not | pick one home for capability trust status, or the three will drift | TBD |
| Legacy surfaces | Apps Script, Pine scripts, static reports, archives | current consumers/owners | TBD |
| `/dev` on public staging | keep and gate it, or drop it from public deployments — it exposes service account, IAP audience, revision and model state without sign-in when `STAGING_SERVICE=1` (see [09](09-SECURITY-AUTH.md)) | who uses `/dev`, and whether staging must stay public | TBD |
| Open registration | `AUTH_OPEN_SIGNUP` defaults to `1`, so any verified Firebase identity is admitted; closing it means operating `AUTH_ALLOWED_EMAILS` | intended audience and onboarding model | TBD |
| Stop-loss policy | [#815](https://github.com/TeneikaAskew/stocks/issues/815) proposes **not** adding a live stop-loss to match the backtest; the alternative is changing the backtest instead | which artifact is the source of truth for risk semantics | TBD |

Decision records should capture date, owner, context, alternatives, outcome, consequences, affected feature/requirement IDs, rollout and reversal criteria.
