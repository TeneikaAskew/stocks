# Live Performance Review — 2026-08-27

First live review after the 2026-08-25/26 gamma rebuild, the magnitude
production-model refresh (`magnitude-engine-c49qf`, isotonic, post-#798
features), and the #774 RVOL shadow gate. Covers: the morning inference
batch scored against realized outcomes, signal performance on 08-26
(resolved) and 08-27, the full-history RVOL-gate reconstruction and
enforce/no-enforce verdict, the `max_daily_trades` cap's data-censoring
side effect, the dormant `playbook_cards` surface, and how gamma is used
across the system. All numbers reproduce from the queries referenced in
each section via `./scripts/db_query_cr.sh`.

## 1. Magnitude predictions (c49qf batch, scoring 2026-08-26 bars)

294 predictions (6 production cells). Realized label computed with the
production formula — `|next_close − next_open| / atr_20`, session-aware
LEAD, thresholds 0.5/1.0/1.5.

**Argmax is degenerate: every prediction was TIGHT.**

| TF  | n   | Argmax accuracy | TIGHT base rate |
|-----|-----|-----------------|-----------------|
| 5m  | 222 | 67.1%           | 67.1%           |
| 15m | 66  | 74.2%           | 74.2%           |

The bucket column adds exactly nothing over "always predict quiet" —
expected with a dominant class and calibrated probabilities, and why
`pred_bucket` must never be consumed as the signal.

**The probabilities rank.** On 5m bars that realized EXPLOSIVE,
`p_explosive` averaged **0.0755 vs 0.0329** on bars that stayed TIGHT
(2.3×); `p_expanded + p_explosive` separated 0.128 vs 0.082; `p_tight`
was lowest exactly on the explosive bars. This matches the walk-forward
explosive-lift result (4–8× at the top-percentile threshold on these
cells).

**Guidance:** consumers use `p_explosive` as a continuous vol-expansion
dial or top-decile threshold flag. Anything reading `pred_bucket` is
reading noise.

**THIS IS LIVE TODAY — corrected 2026-08-27 after Codex round 3.**
`lib/movement_statement.py:393-421` derives `size_class` from
`pred_bucket`, and `platform/src/components/dashboard/expectedMove.ts`
turns that class into stop distances and share counts.

An earlier revision of this section claimed the `MOVEMENT_STATEMENT_ENABLED`
flag was "default-OFF and set nowhere in `gcp/deploy.sh`, so there is no
live exposure today." **That was wrong.** The flag is default-OFF in
code, but it is set `true` at `platform/deploy.sh:87` — the *frontend*
service's separate deploy script, which the original grep never covered.
Verified live: `gcloud run services describe trading-platform` returns
`MOVEMENT_STATEMENT_ENABLED=true`. The Expected-Move card is rendering
this chain to users now.

What it is currently showing (reproducible, see report 09 §TIER 6):
every one of the 6 rows the card can serve — 3 tickers x 2 timeframes,
all from the current production model `magnitude-engine-c49qf` — is
`pred_bucket = 0` (TIGHT). So the card reads "quiet, tighter stops OK"
on every bar today.

`size_class` MUST be re-derived from the probability columns (e.g.
`p_expanded + p_explosive` thresholds) rather than argmax. Because the
chain is live, this is a **fix-forward**, not a "do not enable"
precondition. Tracked as action item 4.

## 2. Signals — 2026-08-26 (resolved) and 2026-08-27

**08-26:** 15 fires (cap-limited to 5/ticker): IWM 5 CALL, QQQ 5 CALL,
SPY 5 PUT. 3/15 winners; avg return IWM −0.068%, QQQ 0.000%,
SPY −0.108%; almost all exits by time-stop (one IWM target hit). The
five SPY PUTs fought a tape that drifted up while capped under the
gamma flip (§6).

**08-27:** all 15 slots fired within ~10 minutes of the open (all CALL,
5/ticker), resolved intraday at 13/15 winners (below-gate 8/10 +0.131%,
pass 5/5 +0.115%). The cap exhausted in the opening burst — precisely
when RVOL denominators are least stable.

## 3. RVOL gate: full-history reconstruction → do NOT enforce (yet)

Shadow stamps began 08-26 (n=30 and self-contradictory: below-gate went
2/12 on 08-26 and 8/10 on 08-27). Since every alert stores fire-time
`rvol`, the verdict was reconstructed over the full history — 2,918
resolved non-replay fires since 2026-03-19, gate_min = 1.0:

| Month | below avg ret | pass avg ret | better side |
|-------|---------------|--------------|-------------|
| Mar   | +0.033        | +0.016       | below       |
| Apr   | +0.054        | −0.028       | below       |
| May   | −0.010        | −0.035       | below       |
| Jun   | −0.053        | −0.005       | pass        |
| Jul   | −0.019        | +0.008       | pass        |
| Aug   | +0.025        | +0.065       | pass        |

No dose-response: win rates across RVOL bands sit flat at 49–54%, and
the ≥2.0 band is the *worst* performer (−0.028% avg). A real entry
filter would show returns rising with the band.

The exact cohort definition, monthly aggregation, band edges, and a
composition slice (ticker × direction × fire-hour × verdict) are checked
in as `gcp/queries/rvol_gate_analysis.sql` so the verdict is
reproducible and adversarially sliceable.

**Verdict: the gate stays in shadow.** The 08-26 pattern that motivated
enforcement (below+unaligned 0/7) did not survive out-of-sample; on
08-27 enforcement would have suppressed 8 of the 10 below-gate winners.

**Open lead — the interaction, not the level.** Jun–Aug consistently
favors pass (+0.023 vs −0.019, ~4 bps separation), and the worst 08-26
cohort was `below AND brief-unaligned`. Alignment stamps only started
accruing recently, so the interaction cannot be reconstructed — but
every fire now carries both fields. Re-test "enforce only when below
AND unaligned" once the stamped sample reaches decision grade
(~2–3 weeks of fires).

**Backfill:** `gcp/queries/backfill_rvol_gate.sql` (this PR) stamps the
reconstructed verdict onto all pre-gate rows — a pure function of the
stored `rvol` at gate_min=1.0, identical to `rvol_gate_verdict` — so
future analyses (including the interaction test) run against the
complete series. Live-stamped rows are untouched; idempotent.

## 4. The 5-per-ticker cap censors the signal record

`risk.max_daily_trades = 5` (lib/config.py RiskConfig, alert_config.json)
is a **risk-management** knob — it sits beside `max_concurrent_positions`
and the daily loss/profit limits, and as a trading-account throttle it
is defensible. The problem is that it is enforced at *fire time*, so it
is also a **data** cap:

- Fires beyond 5 are never persisted. The record of each day is
  left-truncated at the first five signals per ticker —
  first-come-first-served, not best-five.
- Both 08-26 and 08-27 filled all 15 slots in the opening burst. Every
  mid-day and afternoon signal is unobservable, so we cannot even
  measure what the cap costs.
- Market-based firing rules (score-ranked admission, time-of-day
  distribution, regime-aware budgets, RVOL/alignment interactions)
  cannot be designed or validated against a censored dataset.

This is not a new regression — the cap has been in place since at least
March (the 05-10 #386 cap-diagnostics hardened it), and nothing in this
week's changes altered firing capacity. What is new is the visibility.

**Recommendation (decision for review, not changed in this PR):**
decouple recording from trading, mirroring the shadow-gate philosophy —
persist every fire-quality signal with a `cap_suppressed` flag (alerts
beyond the cap recorded but not alerted/traded), keep `max_daily_trades`
as the trading throttle. After 2–3 weeks the censored region becomes
measurable and a market-based admission rule (e.g. best-score-wins with
an intraday budget) can be designed on evidence rather than guessed.

This is **not** a flag-only change (Codex P2 on the review PR): current
consumers assume every `signal_alerts` row is a tradeable fire. The
implementing PR must, in the same change: exclude suppressed rows in
`signal_monitor_eod_resolver.find_open_alerts` (else the resolver emits
exits for trades that never existed) and give them their own outcome
lifecycle (resolved for analytics, never alerted); exclude them from
signal replay/repost paths; and default-filter them in analytics
queries and the dashboard. A separate `signal_observations` table is
the clean alternative if the filter surface proves too wide.

## 5. Playbook cards: actionable by design, dormant since 06-13

`playbook_cards` (writer: `scripts/analysis/phase6_playbook.py`, the
on-demand `phase6-playbook` job; reader: `/api/playbook` → dashboard
playbook page) holds mined, backtested setup recipes: conditions →
direction, historical win_rate / avg_return_bps / sample_n, target and
stop percentages, best horizon. Fully actionable as designed.

Last generation: **2026-06-13** (36 cards). The job has no scheduler,
and the API deliberately serves the most recent `analysis_date` — so
the dashboard playbook page currently presents 10-week-old setups as
current. The operative daily playbook is the premarket brief + insight
pipeline (whose bias/alignment stamps land on alerts and did separate
performance on 08-26: aligned 2/5 flat vs unaligned 1/10 negative).

**Decision needed:** either schedule `phase6-playbook` (daily or weekly)
so cards stay current, or retire the surface and mark the dashboard
page with a generated-as-of banner. Serving June cards silently as
"latest" is the worst of the three options.

## 6. Gamma: how it behaved and how it is used

Levels from the 08-25 snapshot vs the 08-26 tape:

| Ticker | Regime          | Balance | Flip   | Open→Close     | Behavior |
|--------|-----------------|---------|--------|----------------|----------|
| QQQ    | positive_gamma  | 710.26  | 710.34 | 708.41→711.37  | crossed the cluster, closed 1.11 from balance (from 1.85) — pinning toward the OI center |
| SPY    | negative_gamma  | 764.11  | 767.89 | 764.73→766.08  | drifted up, held below flip all day — flip as ceiling; the 5 PUTs died on time-stops against this drift |
| IWM    | negative_gamma  | 294.10  | 305.70 | 298.64→298.93  | held below flip; closed slightly farther from balance — no pinning in negative gamma, as expected |

Consistent with the week's verified findings:

- **Regime sign carries no direction** (B6; both negative-gamma names
  drifted *up* on 08-26). Regime is context only.
- **Gamma features add ~zero to the size model's log-loss** (08-26
  phase0 full-gamma ablation) — the vol-expansion signal in
  `p_explosive` comes from other features.
- **The levels describe structure well**: balance as magnet in positive
  gamma, flip as the boundary price respects, distance-to-level
  (`dist_to_gamma_flip_pct`, `dist_to_balance_pct`) as the only
  model-safe form (raw dollar levels are non-stationary — #798).
- Open instrument: #784 (position-sizing ablation) once history accrues
  under the rebuilt data.

## 7. Action items

| # | Item | Status |
|---|------|--------|
| 1 | Backfill `rvol_gate` over full history | SQL in this PR; dispatched post-merge |
| 2 | RVOL gate enforcement | **Rejected on evidence**; re-test alignment×gate interaction ~mid-September |
| 3 | Cap decoupling (`cap_suppressed` shadow persistence + consumer lifecycle, §4) | Proposed — needs decision + PR |
| 4 | Movement statement: derive `size_class` from probabilities, not argmax (§1) | **LIVE NOW — fix-forward, not a precondition.** `MOVEMENT_STATEMENT_ENABLED=true` at `platform/deploy.sh:87`, confirmed on the running service. All 6 servable rows are bucket-0, so the card reads "quiet, tighter stops OK" on every ticker/timeframe today. Either fix the derivation or set the flag false; leaving it as-is ships low-skill sizing advice. |
| 5 | Playbook cards: schedule or retire | Needs decision |
| 6 | #784 R4 gamma sizing ablation | Waiting on data accrual |
