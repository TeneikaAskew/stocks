# Open Product Decisions

**Last reviewed:** 2026-09-14 · **Owner:** TBD

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
| `/dev` on public staging | [#943](https://github.com/TeneikaAskew/stocks/issues/943): keep and gate it, or drop it from public deployments — it exposes service account, IAP audience, revision and model state without sign-in when `STAGING_SERVICE=1` (see [09](09-SECURITY-AUTH.md)) | who uses `/dev`, and whether staging must stay public | TBD |
| Magnitude serving cells | **Updated 2026-09-15.** SPY/QQQ/IWM 5m now serve `magnitude-engine-6hp7l` (calibrated, α=0, gates 1-4 at 7-8/8, gate 5 100%, gate 6 0.9-1.2×), promoted by the amended criteria; the `c49qf` constants they replaced are one pointer write away if the decision is to roll back. IWM 15m still serves the `c49qf` constant (its candidate was blocked at g1 5/8); SPY/QQQ 15m and the 30m cells serve nothing. Open: (a) keep or withdraw IWM 15m; (b) resolved 2026-09-15: the detector's HIGH tier now needs five sessions of bars per timeframe (shorter samples over the ceiling are MEDIUM); (c) the `DECISION_LIFT_MIN` operating point (2.0; curve in `mag_config.py`) | `MAGNITUDE_ENGINE_RESULTS.md` §9-10; E-26 | TBD |
| Stop-loss policy | [#815](https://github.com/TeneikaAskew/stocks/issues/815) proposes **not** adding a live stop-loss to match the backtest; the alternative is changing the backtest instead | which artifact is the source of truth for risk semantics | TBD |

Decision records should capture date, owner, context, alternatives, outcome, consequences, affected feature/requirement IDs, rollout and reversal criteria.
