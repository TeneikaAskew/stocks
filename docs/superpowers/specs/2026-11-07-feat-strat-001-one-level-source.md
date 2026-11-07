---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-MARKET-001, REQ-PLAYBOOK-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, INSIGHTS-08]
done_when:
  - "One builder: lib/strat_levels.py exposes build_session_levels(ticker, session_date, daily_df, atr, premarket, reference=None), which returns the level list, the per-side ordered trigger candidates, each candidate's broken or unbroken status, the window, the trigger pick, the stop, the targets and a reason code per side; a structural test (AST walk over lib/, gcp/, platform/ and scripts/) asserts that no module outside lib/strat_levels.py calls compute_previous_levels, compute_current_levels, identify_triggers, select_nearest_levels or reanchor_triggers, that lib/agents/trade_planner.py holds no level walk of its own, and that no parent-bar walk exists outside lib/strat_levels.py; the test fails on origin/main (lib/agents/summarizers.py:521 and :542, gcp/premarket_brief.py:1556, gcp/premarket_playbook_resolver.py:152, gcp/signal_monitor.py:940, platform/api/routers/dashboard.py:515)"
  - "Brief and planner parity: a test drives the brief's production playbook path (gcp/premarket_brief.py) and the planner's production path (context_from_bundle then compute_persona_plans) on the same 2026-11-06 inputs for SPY, QQQ and IWM and asserts the same trigger per side: SPY long PWL/PML 750.36 and short PQL 729.10, QQQ long PQL 661.14 and short PDL 647.05, IWM long PWL 276.00 and short no trigger (reason next_level_outside_window: the nearest level under the 269.13 premarket low is PYH 258.20 at 3.02 ATR); a fidelity test runs origin/main's identify_triggers on the same fixture bars and reproduces the picks premarket_analysis stored that morning (SPY calls PWL 750.36 and puts PDL 732.71, QQQ calls PQL 661.14 and puts PYH 637.01, IWM calls PWL and puts PDL 270.52), so the fixture is what production saw; the parity test fails on origin/main"
  - "Session date: build_session_levels bounds daily bars to dates before session_date, drops rows with a null close, takes previous periods by period filter (never the iloc[-2] fallback), finds the parent bar from the last completed bar, and returns status stale_daily (no levels, no triggers) when the last bar is not the prior session under lib.strat_levels.daily_data_freshness; a premarket snapshot whose own date is not session_date is refused and recorded as premarket_unavailable; tests: the AVGO 2026-11-06 live run before that day's market_data_daily row exists gives PDL 290.12 (not 321.74) and no premarket (not 2026-11-05's pre_vwap 318.14), a frame ending at the prior session whose prior bar is a 2U gives that bar's high and low as the day levels (summarizers.py:578 reads the bar before it), and the brief at 08:30 reads the session's own premarket row (premarket_brief.py:1474-1481 and :1518-1521 read the prior day's); each test fails on origin/main"
  - "Premarket prints: lib.indicators.calculate_premarket_context excludes from pre_high, pre_low and pre_vwap any one-minute bar whose high equals its low and whose price equals the prior session's close or open to the cent, and any bar whose high or low lies more than 1.0 x ATR(14) outside the 5th to 95th percentile band of that morning's premarket closes, and returns the count it excluded; on committed 2026-11-06 Alpha Vantage extended-hours fixtures it gives QQQ a pre_high below 665 and a pre_low above 648 (not 683.50 and 647.05), IWM a pre_high below 275 with pre_low 269.13 kept, SPY a pre_high below 745 (not 765.527), and AVGO neither 312.00 nor 291.53 as an extreme; the test fails on origin/main"
  - "One window: lib.strat_levels._within_staleness_window (3 x the ticker's own ATR(14) and 8% of the reference) is the only distance rule for triggers, stops, targets, the ladder and Room to trigger in every consumer; when ATR(14) is missing or not positive the builder returns no trigger on either side with reason atr_unavailable, and PlanContext.safe_atr never feeds the level walk; tests on the brief, planner, signal-monitor refresh, playbook resolver and movement-statement paths assert the window with ATR present and the atr_unavailable result with ATR missing, and fail on origin/main (strat_levels.py:935-938 falls back to the percent axis, signal_monitor.py:940-943 passes no ATR)"
  - "One level set and one side rule: the candidates are the prior-period highs and lows (PDH, PDL, PWH, PWL, PMH, PML, PQH, PQL, PYH, PYL) and the parent-bar high and low; a candidate is a long (call) level when price_cents(level) >= price_cents(cleared-above mark) and a short (put) level when price_cents(level) <= price_cents(cleared-below mark), whether it is a high or a low, so a level that premarket only touched to the cent stays on its side (a level on the reference's own cent with no premarket beyond it is on both lists) (a low above price is resistance, a high below price is support); opens, closes, gap levels and the premarket high and low are never triggers; the brief's ladder (NEXT LEVELS), the brief's CALLS/PUTS trigger, the planner's trigger and the movement statement's rungs are the same ordered side list; targets are the next distinct rungs on that list beyond the trigger; the stop is the nearest in-window level on the other side of the reference, high or low, or the premarket low for a long (high for a short) when that is nearer; Room to trigger is the trigger's own distance from the reference; a test on the 2026-11-06 SPY fixture asserts the planner's long trigger is PWL/PML 750.36, not PDH 765.97, and the brief's calls side leads with the same 750.36, and touch fixtures (reference 100, pre_high 101, PWH 101 gives long trigger PWH 101; reference 100, pre_low 99, PWL 99 gives short trigger PWL 99) hold in both the brief and the planner; the SPY test fails on origin/main (trade_planner.py:262-265 walks only highs for a long)"
  - "One broken rule: a long candidate is broken when price_cents(max(reference, premarket high)) is above price_cents(level), a short candidate when price_cents(min(reference, premarket low)) is below it, so a level touched to the cent is unbroken, and the reference is the session premarket's pre_vwap when the snapshot is present and the prior close otherwise, in every consumer; tests assert QQQ 2026-11-06 PDL 647.05 unbroken and the trigger in both the brief and the planner (the brief's cents partition at strat_levels.py:1020-1022 drops it), and fail on origin/main"
  - "No synthesized numbers: on an orb_only side every persona plan has entry_zone null, stop null, targets [] and risk_metrics null, and the report headline entry_zone and stop are null; PersonaPlan and InsightReport accept null for both; PlanContext.trigger_for (close x 1.005 and x 0.995) and the legacy single-level walk are removed; gcp/insight_discord_push.py, the orchestrator's thesis check and the risk-reviewer input each have a test with a null plan; a test asserts that every price a plan or the brief publishes is a level price from the builder's level list or a plan offset from such a level, and fails on origin/main (trade_planner.py:702-750 publishes ref +/- 1 ATR)"
  - "One copy per reason: the orb_only text in the brief banners, the planner rationale, the Discord push and the schema field descriptions comes from one reason-keyed table in lib/strat_levels.py (all_broken_by_premarket, next_level_outside_window, no_levels, atr_unavailable, stale_daily); a test renders each reason on each surface and asserts no string 'cleared every structural' remains under lib/, gcp/ or platform/; it fails on origin/main (strat_levels.py:1346, :1427 and :1509, insight_discord_push.py:166 and :174, schema.py:313)"
  - "Parent bar: code identifiers, level keys and user-facing labels say parent bar (parent_bar_high, parent_bar_low, 'Parent bar high', 'Parent bar low'); a test asserts no identifier or string containing 'mother' under lib/, gcp/ or platform/, and that the insight key-levels block labels the levels 'Parent bar high' and 'Parent bar low'; it fails on origin/main"
  - "Snapshot with each brief or plan: premarket_analysis and premarket_analysis_history gain a nullable level_basis JSONB column in gcp/schema.sql, written by the brief with the levels, ATR(14), the last daily bar date, the premarket snapshot with its own date, fetch time and excluded-print count, and the picks; the insight report JSON carries the level_basis its plan used; the planner, the signal monitor, the playbook resolver and the movement statement read the session's level_basis only from a row with run_kind = 'live' (a replay row written for the same ticker and session, gcp/premarket_brief.py:3481-3507, is never reused live) and build through build_session_levels when no live row exists; level_basis carries a rule_version, and the movement statement's reach-rate population (lib/movement_statement.py:336-339) counts only resolved rows whose level_basis carries the current rule_version, so new-rule rungs never show old-rule rates; tests assert a planner run for a brief ticker loads no daily bars for levels, that rewriting market_data_daily after the brief leaves the planner's structural levels unchanged, that every writer and reader still works when the column is absent, that a replay row for the session is ignored by each live reader, and that reach rates over a mix of old-rule and new-rule resolved rows count only the new-rule rows in both numerator and denominator; they fail on origin/main"
  - "Unchanged, each pinned by an existing or added test that passes on origin/main and on the implementation head: signal-monitor fire decisions, scores, strength labels, Discord delivery and alert targets (lib/config.py:305-306, gcp/signal_monitor.py:1504-1508) on the existing replay fixtures; the brief's CALL/PUT side pick (_resolve_signal_status); the planner's ATR stops, R-multiple targets and sizing on a side that has a trigger; the strat_levels table rows the brief writes"
  - "The implementation PR body shows, for IWM, SPY and QQQ from 2015-01-02 to 2026-11-06 through the production replay paths, the count of sessions on which the brief's trigger, the planner's trigger or the side's orb_only state changes against origin/main, per side, and the before and after picks for the 20 sessions through 2026-11-06"
  - "Source identity (DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, INSIGHTS-08): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01 / DASHBOARD-21 / INSIGHTS-01 / INSIGHTS-07 / INSIGHTS-08) note rows carry that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 and FEAT-INSIGHT-001 catalog records and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the level_basis production column apply is recorded separately after the owner's yes"
status: approved
supersedes: null
---

# One level source for the brief, the planner and every other consumer

## Authority

Proposed on 2026-11-07 by a delivery lane after the owner's directive: "Levels should be built in
ONE place and used across all. None should be built and re-rerun. The planner may have a different
premarket level due to timing and that's it." With it: "We need to remove any synthetic levels."
and "Why is there no distance limit, inconsistent." On the side rule the owner ruled: "Puts or calls
need to look at all levels, whether it's a high or a low... it should count on whichever side of
price it sits." It is not self-approved: it takes effect only
when the owner merges the spec-only PR that adds it, and that merge is the approval its `status`
records.

It builds on the FEAT-INSIGHT-001 trigger distance cap (spec PR #1745, implementation PR #1746:
the planner's walk capped at the brief's window, a level touched to the cent unbroken, synthesized
blue-sky triggers removed). No implementation PR opens until #1746 is on main. Where this spec
cites the planner it cites origin/main (bd88fa45) and names the #1746 change where it differs.

Evidence marked "production read 2026-11-07" comes from a read-only production check reported to
this lane on 2026-11-07; this lane did not run it.

## Problem

Five code paths pick levels, and each builds its own map from its own inputs:

| Consumer | Where | Builds with |
|---|---|---|
| Premarket brief (08:30 ET) | gcp/premarket_brief.py:1459 | build_level_map, ATR, anchor prior close |
| Brief regime | gcp/premarket_brief.py:1510-1556 | the planner's select_trigger_and_regime on a second PlanContext |
| Insight planner (08:45 ET, auto-refresh-top-n 08:10 ET) | lib/agents/summarizers.py:521, :542; lib/agents/trade_planner.py:185 | compute_previous_levels plus its own parent-bar walk and level walk, anchor pre_vwap |
| Signal monitor | gcp/signal_monitor.py:940 | build_level_map without ATR |
| Playbook resolver | gcp/premarket_playbook_resolver.py:152 | build_level_map from its own SQL |
| Movement statement | platform/api/routers/dashboard.py:515 | build_level_map from its own frame |

They disagree on 2026-11-06 for every ticker the brief covers:

| Ticker | Side | Brief stored (premarket_analysis) | Planner on main | Planner with #1746 |
|---|---|---|---|---|
| SPY | long | PWL/PML 750.36 | PDH 765.97 | PDH 765.97 |
| SPY | short | PDL 732.71 | PQL 729.10 | PQL 729.10 |
| QQQ | long | PQL 661.14 | PDH 683.65 | PDH 683.65 |
| QQQ | short | PYH 637.01 | PYL 402.39 (extended) | PDL 647.05 |
| IWM | long | PWL | PDH 284.70 | PDH 284.70 |
| IWM | short | PDL 270.52 | PYL 171.73 (extended) | none (orb_only) |

The brief column is the production read 2026-11-07. The planner columns were computed by this lane
on the fixtures in tests/lib/test_trade_planner_distance_cap.py (branch of #1746).

Each item below was checked against origin/main; corrections to the lane's starting list are noted.

1. Reference price. The brief anchors on the prior close (`d['price']`, premarket_brief.py:1275,
   passed at :1459); identify_triggers partitions on it at strat_levels.py:1020-1022. The planner
   anchors on pre_vwap (trade_planner.py:142-153). Confirmed.
2. Premarket date. The playbook loop filters bars to `idx < analysis_date` (premarket_brief.py:1437)
   and then reads pre_high and pre_low from `df.iloc[-1]` (:1474-1481) and pre_high, pre_low,
   pre_vwap and gap_pct from `df.iloc[-1]` again (:1518-1521), which is the prior session's row,
   so the brief uses the prior day's premarket. premarket-refresh-daily writes the session's pre_*
   at 08:20 ET (gcp/deploy.sh:4863, fetch_premarket_refresh.py:251-256), ten minutes before the brief
   (:4472). The planner overlays the newest row (summarizers.py:255-261). Confirmed by code reading;
   production read pending (premarket_analysis has no pre_* columns, and market_data_daily's
   2026-11-06 row was rewritten by the 23:00 fetcher after the brief: IWM pre_vwap 271.502 at brief
   time, 271.633 now, production read 2026-11-07). In scope.
3. Session date in live insight runs. A live run passes as_of None (orchestrator.py:656-661), so
   summarize_strat_status does not bound the frame (summarizers.py:484-504) and
   compute_previous_levels takes its iloc[-2] fallback (strat_levels.py:352-359), and the premarket
   overlay takes the newest row. auto-refresh-top-n runs at 08:10 ET (deploy.sh:5104), before the
   session's row exists, so on 2026-11-06 AVGO got 2026-11-04's levels (PDL 321.74 instead of
   290.12) and 2026-11-05's premarket (pre_vwap 318.14) (production read 2026-11-07). Added.
4. Parent bar off by one. `_walk_back_to_mother_bar` assumes `iloc[-1]` is today and starts at
   `iloc[-2]` (summarizers.py:576-578). Under the premarket contract the frame already ends at the
   prior session (:504), so it reads the bar before the prior session. Checked here: a frame ending
   2026-11-05 whose last bars are all 2U returns 2026-11-04's high and low. The planner prefers that
   value over PDH (trade_planner.py:918). Added.
5. Level set. The brief's trigger set is prior-period highs, lows and closes plus current-period
   opens (strat_levels.py:1242, opens at :528, :566, :602). The planner uses the highs for a long and
   the lows for a short, with the parent bar in place of PDH/PDL and the premarket high/low
   (trade_planner.py:262-265). The brief passes plain PDH as effective_pdh (premarket_brief.py:1536).
   The brief appends PMK_H/PMK_L after the triggers are picked (:1484-1485), so they reach only the
   strat_levels table (no code outside tests reads it) and the stale-level banner (strat_levels.py:
   1455-1478). Confirmed and extended.
6. Broken rule. The brief's rule is the cents partition against the prior close
   (strat_levels.py:1020-1022); premarket action never breaks a brief trigger. The planner uses
   max(reference, pre_high) and min(reference, pre_low) (trade_planner.py:254-255) with a strict
   compare on main and a 0.005 touch tolerance with #1746. Corrected: the tolerance is #1746's, not
   main's.
7. Missing ATR. `_within_staleness_window` drops the ATR axis and keeps 8% (strat_levels.py:935-938).
   The planner's safe_atr substitutes 1% of the close (trade_planner.py:170-176), so with #1746 the
   window becomes 3% of price, and the brief's own regime call gets the same substitute
   (premarket_brief.py:1529). Confirmed.
8. Stop anchor. The planner's stop anchor is not windowed (trade_planner.py:281-297). Corrected on
   effect: it cannot change a plan today, because only the conservative persona reads it and that
   persona takes the tightest candidate, which always includes the 0.7 ATR stop. It still includes
   pre_high and pre_low, so the IWM 2026-11-06 short anchor is the bad print 283.745.
9. Fallback. The brief shows an ORB banner; the planner returns orb_only (and with #1746 never a
   synthesized trigger). The banner copy says "pre-market cleared every structural level"
   (strat_levels.py:1346, :1427, :1509, also insight_discord_push.py:166, :174 and schema.py:313),
   which is wrong whenever the side is orb_only because the next level is outside the window.
10. Room to trigger. It is computed over the unwindowed structural list with a float compare
    (strat_levels.py:1264-1265), while the trigger uses the windowed list and the cents rule. It
    matches the trigger's distance only because the nearest level is also the nearest windowed one;
    a level on the anchor's own cent gives 0 and the line is hidden. The stale banner's
    "Room to trigger" (:1504) reads all of level_map.levels, gap and PMK levels included.
    signal_monitor.refresh_level_map passes no ATR (signal_monitor.py:940-943), so its map's window is
    percent only, while its put re-anchor passes ATR (:516-517). Confirmed.
11. Sides. The planner's long walks highs above the cleared mark and its short walks lows; the brief's
    identify_triggers and select_nearest_levels put any level above the anchor on the call side and
    any below on the put side (strat_levels.py:1021-1028, :1174-1177). So SPY's brief call trigger was
    a low (PWL 750.36) and QQQ's put trigger a high (PYH 637.01). Confirmed. The owner ruled on
    2026-11-07 that the brief's rule is right: "Puts or calls need to look at all levels, whether it's
    a high or a low", so a broken high is support and a low above price is resistance. The planner's
    highs-only long and lows-only short walk is the defect.
12. Premarket prints. pre_high and pre_low are the max and min over every 04:00 to 09:30 bar
    (lib/indicators.py:584-590), so one bad print sets them. On 2026-11-06 QQQ's 683.50 and 647.05,
    IWM's 283.745 and SPY's 765.527 were Alpha Vantage prints at prior-day prices (near the prior
    open at 08:05 ET, and repeated prints at the exact prior close); QQQ's real range was about 649
    to 664; IWM's 269.13 low is real; AVGO also had 312.00 and 291.53 (production read 2026-11-07).
    QQQ's fake 647.05 marks its real PDL as cleared on main. Added.
13. Synthetic numbers. `_orb_only_plan` publishes entry ref to ref + 1 ATR and stop ref - 1 ATR
    (trade_planner.py:702-750); `trigger_for` falls back to close x 1.005 and x 0.995 (:155-168); the
    orchestrator makes the neutral plan the report headline (orchestrator.py:626-633), so an orb_only
    report stores those numbers as its entry and stop. Confirmed.
14. Live alert targets. Corrected path: the defaults are lib/config.py:305-306 (not gcp/config.py),
    applied as price x (1 +/- pct) at gcp/signal_monitor.py:1504-1508 with entry at the bar's last
    price (:1136) and a time stop only. They are not levels. Out of scope (Non-goals).
15. Other consumers. The playbook resolver re-derives triggers from its own SQL when a row has none
    (premarket_playbook_resolver.py:104-175). The movement statement builds its own map and matches its
    rungs to the brief's stored trigger and targets by cent (lib/movement_statement.py:237-260).
    insight_discord_push already hides the orb_only placeholders (insight_discord_push.py:172-177);
    the insight key-levels block labels the parent bar "Effective PDH/PDL" (orchestrator.py:981-982).
16. Name. "mother bar" appears in lib/agents/summarizers.py (12), trade_planner.py (3) and
    orchestrator.py (1); the owner found it unfamiliar.

## Non-goals

- Live alert targets and stops (lib/config.py ExitConfig, exit_config_overrides). They are fixed
  percentages, not levels; changing them changes fires and needs its own replay. Proposed as a
  separate spec.
- The planner's ATR stops, entry buffers, R-multiple targets and sizing on a side that has a
  trigger. They are offsets from a real level, not levels (Open question 6).
- The brief's CALL/PUT side pick (_resolve_signal_status), TF bias, FTFC and every score.
- The volatility measure and the 3 ATR width. Each ticker keeps its own Wilder ATR(14). A 2015 to
  2026 check on SPY, QQQ and IWM daily bars found it within a few percent of the best of eight
  measures at predicting the next session's true range (a 5-day ATR was about 4% sharper; a median
  true range and a fixed percent of price were worse, the percent of price far worse and unstable
  across calm and volatile regimes). From the open, a one-sided move past 2 ATR happened on under 1%
  of sessions per ticker and past 3 ATR on 0.03% (IWM) to 0.22% (SPY), so a narrower 2 ATR window is
  for the entry experiment to test, not for this spec.
- Chart reference lines (CHARTS-10, GET /api/market/reference): prior-session OHLC drawn as lines,
  no pick.
- The strat_levels table: still written by the brief, unchanged; nothing reads it today.
- solyra code. The null orb_only entry and stop need solyra's report cards to accept null; that is a
  companion change in solyra, merged before this deploys (Risks).

## Approaches considered

1. Patch each consumer to match the others (pass ATR to the monitor, read today's premarket in the
   brief, copy the planner's side rule into the brief). Rejected: it keeps five builders that drift
   again, which is how items 1 to 16 arose.
2. Make the persisted strat_levels table the one source and have every consumer read it. Rejected:
   the planner covers tickers the brief does not, replays and the resolver need a build for days with
   no row, and the table lacks ATR, the premarket snapshot and the picks.
3. Chosen: one pure builder in lib/strat_levels.py that owns every level decision, plus a per-session
   snapshot of its inputs and outputs written with the brief and with each plan. Consumers read the
   session's snapshot when it exists and call the builder only when it does not; the planner passes
   only a fresher premarket snapshot.

## Design

1. Builder. `build_session_levels(ticker, session_date, daily_df, atr, premarket, reference=None)
   -> SessionLevels` in lib/strat_levels.py. It is the only code that:
   - bounds bars to `date < session_date`, drops null-close rows and checks freshness with
     daily_data_freshness (stale gives status stale_daily, no levels);
   - builds previous-period highs, lows and closes (period filter only), current-period opens, gap
     levels, and the parent bar (the last completed bar that the run of inside bars ending at the
     prior session sits within; the prior bar itself when it is not an inside bar);
   - accepts the premarket snapshot only when its own date equals session_date, else records
     premarket_unavailable and proceeds without it;
   - sets the reference: the snapshot's pre_vwap when present, else the prior close, or the caller's
     `reference` (the monitor's put re-anchor passes the session open);
   - forms the side lists from one candidate set, the prior-period highs and lows and the
     parent-bar high and low (PDH/PDL and the parent bar are all candidates; nearest unbroken wins,
     Open question 1): every candidate at or above the cleared-above mark, compared in cents, is on the
     long list and every candidate at or below the cleared-below mark on the short list, whatever its
     kind (inclusive, so a level premarket only touched to the cent stays a candidate), by the owner's
     2026-11-07 ruling ("It's about levels, not about the high or low level that it is"). A level
     premarket traded through sits between the two marks and is on neither list. Opens, closes, gap
     and premarket levels are never triggers;
   - marks broken status with one cents rule: broken for a long when
     price_cents(max(reference, premarket high)) > price_cents(level), mirrored for a short;
   - applies one window, `_within_staleness_window(level, reference, atr)`; when ATR is missing or
     not positive both sides return no trigger with reason atr_unavailable (Open question 3);
   - picks per side: trigger = the nearest unbroken in-window candidate; regime normal or extended
     at 3 ATR as today; when there is none, orb_only with reason all_broken_by_premarket,
     next_level_outside_window or no_levels; targets = the next three distinct (cents) in-window
     rungs beyond the trigger on the same list; stop = the nearest in-window level on the other side
     of the reference, of either kind, or the premarket low for a long (high for a short) if nearer; ladder = the first two
     in-window rungs of each side list; room = the trigger's distance from the reference.
   LevelMap keeps its fields so persist_level_map and the strat_levels writes are unchanged.
   identify_triggers, select_nearest_levels and reanchor_triggers become private helpers of the
   builder.
2. Premarket filter (lib.indicators.calculate_premarket_context, used by
   gcp/fetchers/fetch_premarket_refresh.py and the nightly fetcher). Before taking the max, min and
   VWAP, exclude a one-minute bar when its high equals its low and its price equals the prior
   session's close or open to the cent, or when its high or low lies more than 1.0 x ATR(14) outside
   the 5th to 95th percentile band of that morning's premarket closes. Return excluded_bars. The
   function gains prev_open and takes atr14 (the refresh job passes None today, fetch_premarket_refresh.py:194;
   it reads the prior row's atr_14 in the same query as the prior close). Thresholds are the lane's
   default (Open question 2).
3. Snapshot. A nullable `level_basis` JSONB column on premarket_analysis and premarket_analysis_history
   (gcp/schema.sql). Contents: rule_version, session_date, built_at, last daily bar date, atr, the level list
   (name, price, timeframe, type, period label), the premarket snapshot (date, fetch time, values,
   excluded_bars), reference, and per side the candidates with status, the pick, stop, targets,
   ladder and reason. About 4 KB. The insight report JSON carries the level_basis its plan used (no
   column change: insight_reports stores the report as JSONB).
4. Consumers.
   - Brief: one call to the builder with the session's premarket row (date = analysis_date). The
     second PlanContext at premarket_brief.py:1510-1556 goes; the regime comes from SessionLevels.
     It writes level_basis with the row.
   - Planner: summarize_strat_status and summarize_market_context stop building levels; the bundle
     gets SessionLevels from the session's premarket_analysis.level_basis with the planner's own
     newer premarket snapshot applied (the builder recomputes reference, broken status and picks from
     the stored levels), or from the builder when no row exists. A live run's session_date is the
     ET date of execution. select_trigger_and_regime reads the pick; context_from_bundle reads
     effective levels nowhere.
   - Signal monitor: refresh_level_map reads level_basis for the session, else builds with ATR and
     the session premarket; the put re-anchor is the builder with reference = open.
   - Playbook resolver: derive_level_map_from_daily calls the builder (rows that predate level_basis).
   - Movement statement: reads level_basis, else builds; its rungs are the side lists, so the
     stored trigger is always rung one. Its reach-rate population filters on level_basis
     rule_version, so until new-rule rows resolve each rung shows its existing low-sample state.
   - Every live reader of level_basis filters run_kind = 'live', as the dashboard query and
     movement_statement.py:407-415 already do for the slot prices.
5. No synthesized numbers. PersonaPlan.entry_zone, PersonaPlan.stop, InsightReport.entry_zone and
   InsightReport.stop become Optional; `_orb_only_plan` sets them and risk_metrics to null and
   targets to []. trigger_for and the has_multi_tf legacy branch (trade_planner.py:235-251) are
   removed; a context with no levels is orb_only with reason no_levels.
6. Copy. One table `ORB_ONLY_COPY[reason]` in lib/strat_levels.py feeds the brief banners, the planner
   rationale, the Discord push and the schema descriptions. Example for next_level_outside_window:
   "No unbroken {side} level within 3x ATR and 8% of price. Wait for the 15-min opening range."
7. Rename. `_walk_back_to_mother_bar` becomes `find_parent_bar` in lib/strat_levels.py; the bundle
   keys effective_PDH/effective_PDL become parent_bar_high/parent_bar_low; the labels become
   "Parent bar high" and "Parent bar low". Stored reports keep their old keys and are served as stored.

Jobs to redeploy: premarket-brief, fetch-premarket-refresh, fetch-market-data, insight-pipeline,
auto-refresh-top-n, signal-monitor (and signal-replay), premarket-playbook-resolver,
insight-discord-push and the API image (movement statement and insights).

## Open questions for the owner

Each has a default this spec takes; a different answer is a one-line change in the implementation PR.

1. Inside bar: is the day trigger the inside bar's own high and low, the parent bar's, or both?
   Default: both are candidates and the nearest unbroken one wins (main's planner uses only the
   parent bar, the brief only the inside bar).
2. Premarket filter thresholds (Design 2). Default as written; the code did not settle it. The
   implementation PR shows the excluded bars per ticker for the 20 sessions through 2026-11-06.
3. Missing ATR. Default: no trigger, reason atr_unavailable (REQ-DATA-001). Alternative: the 8%
   axis alone.
4. auto-refresh-top-n runs at 08:10 ET, before the session's premarket row exists. Default: those
   reports carry premarket_unavailable. Moving the schedule after 08:20 is a production config change
   and needs the owner's yes.
5. Fixture values. The #1746 fixture has QQQ PYH 640.0 while the brief stored PYH 637.01, and IWM PWL
   276.89 while the read reported PWL 276. The implementation rebuilds the fixtures from
   market_data_daily bars; stored brief values win.
6. Are the planner's R-multiple targets and ATR stops "synthetic levels" under the directive?
   Default: no, they are offsets from a real trigger (Non-goals).

## Expected effect

On 2026-11-06 (fixtures above, premarket as stored): the brief and the planner both show SPY long
PWL/PML 750.36 and short PQL 729.10, QQQ long PQL 661.14 and short PDL 647.05, IWM long PWL 276.00 and
no short trigger (the next level under IWM's real 269.13 premarket low is PYH 258.20, 3.02 ATR away).
With the print filter QQQ's pre_high is 660.40 (Alpha Vantage 5-minute extended-hours bars, the 08:05
683.50 print excluded), so PQL 661.14 is unbroken, and its pre_low moves above 647.05 (seven bars
printed exactly 647.05), so PDL is unbroken without the touch tolerance. SPY's 04:00 low of 730.64
is real and breaks PDL 732.71, so the short is PQL 729.10. Against Friday's session: QQQ crossed
661.14 in the first 15 minutes and peaked at 664.52 in the 9:45 bar; IWM never reached 276.00 (high
274.55); SPY never reached 750.36 (high 742.21) or 729.10 (low 734.58). The brief's NEXT LEVELS keep highs and lows on whichever side of price
they sit (SPY's calls ladder leads with the low 750.36) and stop listing opens, closes, gaps and levels
premarket already traded through; brief targets stop including opens and closes; the movement
statement's reach rates count only rows built under the new rule. History counts come with the implementation PR (done_when).

## Capacity and cost

- Volume: level_basis about 4 KB per row; brief tickers (3 by default, lib/config.py:179) plus the
  insight tickers per session, so under 50 rows and 200 KB a day.
- Velocity: the builder is in-memory over bars each consumer already loads. Reading level_basis is
  one query per run for all tickers (`ticker = ANY(:tickers) AND analysis_date = :d`), which replaces
  a load_daily per ticker in the planner, monitor and movement statement. The premarket filter adds
  one percentile over at most 330 bars per ticker.
- Wall-clock: unchanged within noise; no new job.
- Cost: no new scheduled job; storage under 100 MB a year.

## Source identity and close-out

The implementation PR binds DASHBOARD-01 (brief), DASHBOARD-21 (movement statement), INSIGHTS-01
(report entry and stop served null on orb_only), INSIGHTS-07 and INSIGHTS-08 (planner, live and
replay) as done_when 14 states. After merge: the staging deploy that a merge to main starts; the
level_basis column applied to production only after the owner's yes; then real queries showing a
brief row and an insight report for the same ticker and session with the same trigger per side and a
premarket snapshot dated that session, and the production read that confirms item 2 (the brief's
premarket date before the change). Those post-merge steps are close-out, not pre-merge done_when
boxes.

## Risks

- Picks change on many days (sides, level set, reference). done_when 13 shows the counts; the
  side rule follows the brief, by the owner's ruling, so the planner's picks change wherever the
  nearest unbroken level is of the other kind.
- The print filter could drop a real extreme. done_when 4 keeps IWM's real 269.13, and the PR shows
  every excluded bar for 20 sessions.
- solyra may not render a null entry or stop. The companion solyra change merges first; until then
  the API image is not deployed with this change.
- A missing level_basis column must not break writers or readers (done_when 11).
- Stored insight reports keep effective_PDH keys; readers must accept both keys.
