# Open Product Decisions

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
| Legacy surfaces | Apps Script, Pine scripts, static reports, archives | current consumers/owners | TBD |

Decision records should capture date, owner, context, alternatives, outcome, consequences, affected feature/requirement IDs, rollout and reversal criteria.
