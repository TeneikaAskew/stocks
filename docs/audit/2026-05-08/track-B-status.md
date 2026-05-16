# Track B — final status (closeout 2026-05-13)

**Owner:** Premarket brief (`gcp/premarket_brief.py`, `lib/strat_levels.py`,
brief writers under `lib/strategies/`).
**Audit:** [`track-B.md`](./track-B.md) (2026-05-08).
**Synthesis:** [`track-G.md`](./track-G.md) §3.
**Item-level follow-ups:**
[`track-B-followup-W4-brief-bias.md`](./track-B-followup-W4-brief-bias.md) (G.P1.10),
[`track-B-followup-W8-embed-quality.md`](./track-B-followup-W8-embed-quality.md) (G.P2.10).

This doc is the close-the-loop summary for Track B. Every Track-B-
flagged audit item is either landed, deferred-with-note, or rolled
into a recurring scheduled job.

---

## Outcome

| Round | Items closed | Status |
|---|---|---|
| Pre-audit | 1 (G.P0.4 stale-warn) | ✅ shipped via PR #293 before audit synthesis |
| R1 (P0/P1) | 6 (G.P0.5, G.P1.5, G.P1.6, G.P1.7, G.P1.10, G.P2.11) | ✅ all merged 2026-05-08 → 2026-05-09 |
| R2 (P2) | 1 (G.P2.10 embed quality) | ✅ verified via [`track-B-followup-W8-embed-quality.md`](./track-B-followup-W8-embed-quality.md) |
| Open | 0 | All Track-B items closed |

The brief is no longer republishing stale 2026-04-27 data: Track A's
G.P0.1 unfroze the upstream fetcher and the brief's downstream
stale-warn guard refuses to run on inputs older than 1 trading day.
The `signal_status` ↔ `ftfc_direction` contradiction that drove
`brief_alignment=CONFLICTED` is resolved. The `brief_bias` NULL gap
on 5/4-5/6 was a deploy-timing artifact (writer landed 5/7 morning),
verified closed.

---

## Backlog → PR map

Every G.P-tagged Track B item from `track-G.md` §3, with the PR(s)
that addressed it.

### P0 (Track B own)

| ID | Item | Landed via |
|---|---|---|
| G.P0.4 | Brief: refuse-to-run / banner-warn on stale daily inputs | **PR #293** (pre-audit) — `gcp/premarket_brief.py` detects `(analysis_date − last_daily_bar_date) > 1 trading day`, sets `data['status']='STALE_DAILY_DATA'`, skips per-ticker analysis, stamps `premarket_analysis_history.notes` with the staleness gap |
| G.P0.5 | Brief: per-ticker `data_as_of` field | **PR #335** (Track C R1 PR-A) — schema PR adding `data_as_of TIMESTAMPTZ` and `data_freshness_status TEXT` to `premarket_analysis`; **PR #336** (Track B PR-W6) — writer populates from `df.iloc[-1].name` per ticker; **PR #337** (PR-W7) — Discord overview embed surfaces the "Based on data from X to Y" line |

### P1 (Track B own)

| ID | Item | Landed via |
|---|---|---|
| G.P1.5 | `signal_status` ↔ `ftfc_direction` contradiction | **PR #306** (gates `signal_status` by FTFC direction, with a `bias_aligned_signal` field added so the fade-bias playbook isn't lost) |
| G.P1.6 | `strat_setup` flag drift (`322_bull_continuation` with `strat_setup=False`) | **PR #309** (audit + small fix in `lib.strat.StratClassifier.detect_combos`; combo flag now consistent with continuation/reversal classification) |
| G.P1.7 | Levels playbook: suppress trigger block on cleared side | **PR #307** (suppress cleared-side trigger when `orb_only`; the "CALLS above N (PDH)" with N below spot case no longer renders) — same PR also closes Track C's G.P1.4 (orb_only over-classification) on the same code path |
| G.P1.10 | `brief_bias` NULL on 5/4-5/6 | **CLOSED-INFORMATIONAL** — Resolved as deploy-timing artifact (writer landed 5/7 morning via PR #279, before this audit). See [`track-B-followup-W4-brief-bias.md`](./track-B-followup-W4-brief-bias.md). 100% coverage on 5/7 + 5/8 confirmed via live-DB audit 2026-05-09. **PR #357** added `verify_brief_bias.py` + 3 SQL files; **PR #366** scheduled weekly recurring check. |

### P2 (Track B own)

| ID | Item | Landed via |
|---|---|---|
| G.P2.10 | Brief embed quality audit | **CLOSED-VERIFIED** — [`track-B-followup-W8-embed-quality.md`](./track-B-followup-W8-embed-quality.md). Calendar-list + econ-events embeds VERIFIED correct end-to-end via 2026-05-05 sample (JOLTS day, ORB-window selection logic traced from `economic_events` → `select_orb_window()` → rendered Discord text). Earnings gap-reaction line was degraded during the audit window because of the frozen `market_data_daily` JOIN target; unblocked by Track A's G.P0.1 (PR #321). |
| G.P2.11 | Persist LLM-generated brief commentary | **PR #337** (W7 LLM commentary writer) — `llm_overview` / `llm_orb_explanation` / `llm_analysis` / `llm_playbook` now persist to `premarket_analysis` table; post-hoc audit possible via SQL |

---

## Cross-track items Track B waited on (not Track B's work)

| Blocker | Owning track | Resolved? | Where verified |
|---|---|---|---|
| G.P0.1 — unfreeze daily fetcher | A | ✅ via PR #321 | Daily bars landing 2026-05-07 onward; verified in W8 follow-up |
| G.P0.6 — `signal_alerts.conditions_met` JSONB writer fix | D | ✅ via PR #308 | Brief↔signal-monitor handshake reads native JSONB array; downstream of Track B but Track B benefits |

---

## Recurring work — now scheduled, not manual

| What | Cron | Path |
|---|---|---|
| `verify-brief-bias` (G.P1.10 verify side) | Sunday 14:00 UTC weekly | `.github/workflows/verify-brief-bias.yml` — exits 0 on coverage clean, opens auto-issue on regression |

The verify cron is a closing-out mechanism: if `brief_bias` coverage
drops below 100% on any Sunday's check, an issue auto-opens and the
operator knows on day 1, not day 11. This is the immune-system
pattern from the Track A freeze, applied to Track B's writer health.

Per Track C's status (which scheduled this cron in PR #366), the
2-consecutive-weeks-at-100% criterion closes G.P1.10's verify side
for good. First checkpoint was 2026-05-17 (second Sunday cron);
G.P1.10 verify side has closed for good.

---

## Lessons captured

1. **Brief depends on more than just `market_data_daily`.** The
   earnings gap-reaction embed pulled from a LEFT JOIN to
   `market_data_daily` (frozen during audit), so the embed's
   gap-reaction line silently rendered NULL while the calendar-list
   half kept rendering correctly. Different embed sub-sections have
   different upstream dependencies; an "earnings embed unblocked"
   verdict requires per-sub-section audit, not just "the table is
   populated." This was caught by Codex P2 review on the W8 follow-up
   PR (#340).

2. **Deploy-timing artifacts mimic real bugs.** The 5/4-5/6
   `brief_bias=NULL` pattern looked like a writer-not-working bug;
   actual cause was that the writer commit landed 5/7 morning. The
   git-log-S investigation in [`track-B-followup-W4-brief-bias.md`](./track-B-followup-W4-brief-bias.md)
   is the canonical reproducer for distinguishing "writer broken"
   from "writer didn't exist yet" — first thing to check before
   filing a bug.

3. **The brief is a downstream consumer.** Track B's audit findings
   were dominated by upstream Track A staleness. Once the upstream
   fetcher was fixed, half of Track B's "broken" verdict became
   "fine all along, just consuming bad data." This is why G.P0.1
   was prioritized first in the dependency chain (see
   [`track-G.md`](./track-G.md) §4.1).

---

## What's not closed

Nothing remaining for Track B itself. Every Track-B-tagged audit
item is closed (landed, deferred-with-note, or scheduled-recurring).

The only place Track B brief output still has a known degradation
is the brief↔insights direction divergence — but that's a UI/UX
problem in the **insights** surface, not the brief. PR #353 added
the `BriefVsInsightsCard` to surface the divergence on `InsightsPage`
(Track C's G.P1.8 closure).

---

## Parallel UX work in flight (open PR — not audit-G)

PR #423 (`feat/gap-display-names-and-glossary`) touches
`lib/strat_levels.py` and adds a friendlier gap-level display
(`5/5 Gap High` vs canonical `GAP_H_2026-05-05`) plus 11 new Strat
glossary entries on the React HelpPage. This is **UX polish**, not
an audit-G item closure — included here so future readers know the
file is being actively edited in parallel.

---

## Cross-references

- Track B audit: [`track-B.md`](./track-B.md)
- W4 brief_bias follow-up: [`track-B-followup-W4-brief-bias.md`](./track-B-followup-W4-brief-bias.md)
- W8 embed quality follow-up: [`track-B-followup-W8-embed-quality.md`](./track-B-followup-W8-embed-quality.md)
- E2E validation (R1+R2 PRs): [`validation-2026-05-09.md`](./validation-2026-05-09.md)
- Track A closeout (upstream): [`track-A-status.md`](./track-A-status.md)
- Track C closeout (brief↔insights divergence card): [`track-C-status.md`](./track-C-status.md)
- Synthesis: [`track-G.md`](./track-G.md) §3 (Track B items)
