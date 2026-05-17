# Track E — final status (closeout 2026-05-13)

**Owner:** Per-ticker calibration (`lib/strategies/calibration.py`,
`lib/strategies/exit_config_overrides.py`, `exit_config_overrides`
Cloud SQL table, `recommended_per_ticker_config.json`).
**Audit:** [`track-E.md`](./track-E.md) (2026-05-08).
**Synthesis:** [`track-G.md`](./track-G.md) §3.
**Recommendations:** [`per_ticker_writeup.md`](./per_ticker_writeup.md) +
[`recommended_per_ticker_config.json`](./recommended_per_ticker_config.json).
**Cross-track P0 closeout:** [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md)
covers Track A + E together because the per-ticker ExitConfig adoption
landed in the same R1 sprint as the Track A foundation fixes.

This doc is the close-the-loop summary for Track E. Every Track-E-
flagged audit item is either landed, deferred-with-note, or blocked
on time-based data accumulation.

---

## Outcome

| Round | Items closed | Status |
|---|---|---|
| R1 (P0) | 3 (G.P0.12, G.P0.13, G.P0.14) | ✅ all merged 2026-05-08 → 2026-05-09 |
| Open — blocked | 2 (G.P1.11, G.P1.12) | ⏳ waiting on G.P0.14 to settle (need ≥ 2 weeks of post-deploy data) |
| Open — partial | 1 (G.P1.20) | 🟡 partially addressed via PR #384 (calibrate --as-of) + #366 (weekly walk-forward); quarterly recalibration loop not fully closed |
| Open — deferred by design | 2 (G.P2.22 walk-forward stability, G.P2.23 combo_bonus_overrides) | ⏸ deferred — need 6mo history (currently 50 days) |
| Open — follow-up | 1 (data-driven `disabled_conditions`) | 🟡 issue #380 — close-the-loop on hand-set seed |

The MR PUT anti-signal conditions are dropped: `above_vwap` removed
globally (G.P0.12), `stoch_rsi_overbought` + `rsi_overbought_zone`
removed per-ticker on IWM/QQQ (G.P0.13). The `exit_config_overrides`
table exists and is seeded for SPY/IWM/QQQ; the resolver is wired
into both `signal_monitor.fire_alert` and `lib/backtest.py`. The
counterfactual replay numbers (QQQ from net-loss to net-positive
expected return, IWM clear-loss to near-breakeven) are now testable
in production.

---

## Backlog → PR map

Every G.P-tagged Track E item from `track-G.md` §3, with the PR(s)
that addressed it.

### P0 (Track E own)

| ID | Item | Landed via |
|---|---|---|
| G.P0.12 | Drop `above_vwap` from MR PUT scoring (global) | **PR #329** — audit measured −16.1pp (QQQ) / −11.7pp (IWM) / −9.9pp (SPY) ANTI-correlation. Removed from both `lib/signals.py:check_put_conditions` and `lib/strategies/mean_reversion.py:_check_put_conditions`. |
| G.P0.13 | Drop `stoch_rsi_overbought` + `rsi_overbought_zone` (IWM/QQQ only) | **PR #329** — per-ticker drop list lives in `exit_config_overrides.disabled_conditions` JSONB; SPY conditions intact (only weak negative measured). |
| G.P0.14 | Per-ticker ExitConfig overrides | **PR #326** (new `exit_config_overrides` Cloud SQL table seeded with audit-recommended values for SPY/IWM/QQQ) + **PR #327** (`lib/strategies/exit_config_overrides.py` resolver mirroring `calibration.py` Tier-A → Tier-B fallback; wired into `signal_monitor.fire_alert` and `lib/backtest.py`). |

### P1 (Track E own) — BLOCKED on time-based settling

| ID | Item | Status | Note |
|---|---|---|---|
| G.P1.11 | SPY +0.30% CALL target unreachable: 0/78 in window | **OPEN — blocked on G.P0.14 settling** | Track-G synthesis notes this is "subsumed by G.P0.14 (per-ticker overrides)". Per-ticker config for SPY now seeds the audit-recommended +0.184% target. After ≥ 2 weeks of post-deploy data (~2026-05-23 for first walk-forward report), verify SPY CALL target-hit-rate moves above the floor. |
| G.P1.12 | Re-tune **global** ExitConfig defaults | **OPEN — blocked on G.P0.14 settling** | Same dependency: once per-ticker overrides accumulate evidence, re-derive global defaults from the median of per-ticker recommendations so new watchlist additions land on a saner default. Tracked as a follow-up to G.P0.14, not duplicate work. |
| G.P1.19 | Disable QQQ MR PUT entirely | **CLOSED-VIA-G.P0.13** | The audit's recommendation was to disable QQQ MR PUT until the PUT condition set is rebuilt. PR #329 drops the two worst PUT discriminators on IWM/QQQ via `disabled_conditions`. QQQ PUT-side may still fire on `below_vwap` + other CALL-mirror conditions (which weren't anti-signal); if the residual fire-rate still produces net-negative on QQQ PUT after G.P0.14 settles, file a follow-up. |
| G.P1.20 | Quarterly Cloud Run Job for per-ticker recalibration | **PARTIAL** | **PR #384** added a `--as-of` flag + backfill to `scripts/analysis/per_ticker_calibration.py`, plus a one-off historical run. **PR #366** scheduled a weekly per-factor walk-forward. The combination gives evidence-accumulation for the quarterly recalibration but doesn't yet auto-write back to `exit_config_overrides`. Issue **#380** tracks the close-the-loop. |
| G.P1.21 | Capacity discipline (CLAUDE.md §0) for per-ticker calibration | **CLOSED-DOC** | The Phase 0.5 capacity incident that motivated CLAUDE.md §0 was the cautionary tale; PR #321's RUNBOOK_BACKFILL.md + the explicit capacity calc on every new Cloud Run Job (e.g. EOD resolver in PR #319) is now the discipline. |

### P2 (Track E own)

| ID | Item | Landed via |
|---|---|---|
| G.P2.17 | Map per-ticker MFE recommendations from underlying-price to options-price targets | **OPEN — needs implementation** | Script `scripts/analysis/options_pnl_translation.py` doesn't exist yet (per Track-G synthesis estimate "1 day effort"). Not blocking; underlying-price targets work for signal-firing and exit logic. Options-price translation is a UI/playbook surface improvement. |
| G.P2.18 | Surface per-ticker recommendations in React playbook UI | **OPEN — needs implementation** | `platform/src/routes/PlaybookPage.tsx` currently displays hardcoded global ExitConfig. Should read per-ticker overrides via an API endpoint. Not blocking; the live system is already using per-ticker via PR #327. |
| G.P2.22 | Walk-forward stability check in per-ticker calibration | **DEFERRED — 6mo history needed** | Track E explicitly deferred this in the audit; current `signal_alerts` history is 50 days. First viable check ~2026-11-08 (6mo from audit). |
| G.P2.23 | `combo_bonus_overrides` field | **DEFERRED** | Per-track-E §"f5", needs join against `market_data_daily.strat_combo` per bar; deferred until more `strat_combo` evidence accumulates. Captured in issue **#380** (the data-driven `disabled_conditions` follow-up — same architectural concern). |

---

## Cross-track items Track E waited on (not Track E's work)

| Blocker | Owning track | Resolved? | Where verified |
|---|---|---|---|
| G.P0.1 — unfreeze daily fetcher | A | ✅ via PR #321 | Tier-A RSI calibration now runs against fresh data; calibration jobs schedule against fresh bars |
| G.P0.6 — JSONB writer fix | D | ✅ via PR #308 | Per-factor walk-forward now reads native JSONB array |
| G.P0.11 — momentum strategy zero-fires investigation | D | ✅ all three halves shipped (#320 + #330 + #371) | Track E's "preferred_strategy" output collapsed to mean-reversion only because momentum never fired; with #371's orchestration fix + standalone flag, momentum can now produce evidence on real fires (after policy review flips the flag) |

---

## Recurring work — now scheduled, not manual

| What | Cron | Path |
|---|---|---|
| `per-factor-walkforward` (G.P2.1+2+3) | Saturday 13:00 UTC weekly | `.github/workflows/per-factor-walkforward.yml` — uploads markdown report; tolerates `exit 3` (insufficient data) until ~2026-05-23 |
| `verify-brief-bias` (G.P1.10 verify side, cross-track) | Sunday 14:00 UTC weekly | `.github/workflows/verify-brief-bias.yml` |

The walk-forward is the evidence-accumulation mechanism that closes
the loop on G.P0.14 (per-ticker overrides) — every Saturday it
re-derives per-(ticker × direction × factor) verdicts. Currently
emits `INSUFFICIENT_DATA` for momentum factors (waiting on the
standalone flag flip per Track C's status); mean-reversion factor
verdicts start landing ~2026-05-23.

---

## Architectural follow-up: data-driven `disabled_conditions`

Currently `exit_config_overrides.disabled_conditions` is a static,
hand-set seed (committed to `gcp/schema.sql` during the audit and
applied via PR #329). The user flagged this in the 5/6 counterfactual
replay discussion: *"some indicators being eliminated manually and
also data could change and we then aren't considering it — we need to
have more formal process in code that sticks on call vs put indicators."*

Issue **#380** tracks the close-the-loop via three small PRs:

1. **PR-DC-1** — structured `--output-json` + `--write-db` from
   `per_factor_walkforward.py`, writing to a new
   `factor_walkforward_verdicts` table.
2. **PR-DC-2** — schema for `factor_walkforward_verdicts` (auditable
   history of why each condition was disabled).
3. **PR-DC-3** — `calibrate_disabled_conditions.py` reads the
   verdicts table, requires 3-of-4 weekly `DROP` verdicts before
   updating `exit_config_overrides.disabled_conditions`, monthly cron.

This is Track E's primary open follow-up. The hand-set seed works
*now*; the data-driven closing-out makes it regime-responsive.

---

## What's not closed

Four Track-E items are gated on time-based data accumulation, one
needs follow-up implementation:

| ID | Item | Status | Path to closure |
|---|---|---|---|
| G.P1.11 | SPY CALL target unreachable | BLOCKED on G.P0.14 evidence | After ~2026-05-23 walk-forward, verify SPY CALL hit-rate above floor; close with comment if so |
| G.P1.12 | Global ExitConfig retune | BLOCKED on G.P0.14 evidence | After per-ticker overrides accumulate evidence, re-derive global defaults |
| G.P1.20 | Quarterly recalibration loop | PARTIAL via #384 + #366 | Close-the-loop via issue #380 (PRs DC-1/2/3) |
| G.P2.22 | Walk-forward stability | DEFERRED until 6mo history | First viable check ~2026-11-08 |
| Data-driven `disabled_conditions` | Architectural follow-up | OPEN — issue #380 | Three small PRs (DC-1/2/3) |

Per-ticker recommendations are *adopted* (G.P0.14 landed); the
remaining work is making the adoption regime-responsive (issue #380)
and confirming the counterfactual replay numbers hold up in
production (G.P1.11/G.P1.12 after data accumulates).

---

## Cross-references

- Track E audit: [`track-E.md`](./track-E.md)
- Per-ticker writeup: [`per_ticker_writeup.md`](./per_ticker_writeup.md)
- Recommended config: [`recommended_per_ticker_config.json`](./recommended_per_ticker_config.json)
- Cross-track P0 closeout (Track A + E joint): [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md)
- E2E validation (R1+R2 PRs): [`validation-2026-05-09.md`](./validation-2026-05-09.md)
- Track D closeout (G.P0.11 + JSONB cross-tracks): [`track-D-status.md`](./track-D-status.md)
- Track C closeout (walk-forward cross-tracks): [`track-C-status.md`](./track-C-status.md)
- Issue #380 (data-driven `disabled_conditions` follow-up): https://github.com/TeneikaAskew/stocks/issues/380
- Synthesis: [`track-G.md`](./track-G.md) §3 (Track E items)
