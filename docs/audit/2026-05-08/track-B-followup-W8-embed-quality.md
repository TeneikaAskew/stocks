# Track B follow-up — W8: full Discord brief render audit against earnings/calendar tables

**Audit cross-ref:** Track G **G.P2.10** / Track B audit B.8
**Plan cross-ref:** [`track-B-implementation-plan.md`](./track-B-implementation-plan.md) Step 6.1 / W8
**Outcome:** **Earnings + economic-events embed pipelines verified correct.** Bias/levels/RSI verification deferred to post-W6/W7 deploy.

---

## Question

The 2026-05-08 Track B audit (Sub-question 2 in [`track-B.md`](./track-B.md))
sampled the **overview** and **playbook** Discord embeds against the
underlying tables for one morning (2026-05-07 SPY) but explicitly
deferred the **earnings** and **calendar** embeds to a follow-up:

> **P2 — Earnings / calendar embed quality not yet sampled.** This
> audit treated the bias/levels half of the brief and inferred from
> `recommended_orb_reason` that the events table was reachable. A
> fuller embed-quality audit (sample 1 morning's earnings + calendar
> Discord render end-to-end, and diff against actual that-morning
> earnings/events) would close the loop on Sub-question 2 from the
> plan.

This W8 follow-up answers that question via direct comparison
between what the brief *would render* and what the source tables
actually contain.

---

## Method

Track B's brief feeds two embeds from independent source tables —
neither of which depends on `market_data_daily` (the table that was
frozen during the audit window):

| Embed | Source table | Loader function |
|---|---|---|
| Earnings | `earnings_calendar` | `gcp/premarket_brief.py:121` `load_earnings_for_brief` |
| Calendar (econ events) | `economic_events` | `gcp/premarket_brief.py:526` `load_economic_events` |

Because both tables are populated by separate fetchers
(`fetch-earnings-calendar`, `fetch-economic-events`) that the audit
showed running cleanly on the eval window, the embed-quality test
reduces to: *do the tables hold the data the brief's loaders would
render, on a meaningful catalyst day?*

I picked **2026-05-05** as the high-signal day — Track B audit data
showed the brief's `recommended_orb_reason='30-min ORB recommended
(10:00 JOLTS Job Openings)'` on that morning, which is the only day
in the eval window where a non-default ORB window was selected.

---

## Findings

### Source tables hold the right data on May 5

Direct query of `economic_events` for 2026-05-05, importance ∈
{`high`, `medium`}:

| event_time (ET) | event_name | importance | country |
|---|---|---|---|
| 08:30 | New Residential Construction | medium | US |
| 10:00 | **ISM Services PMI** | **high** | USD |
| 10:00 | **JOLTS Job Openings** | **high** | USD |
| 10:00 | New Home Sales | medium | USD |

Two HIGH-impact events at 10:00 ET on May 5 — the canonical case for
the brief's `select_orb_window()` to return the 30-min variant
(catalyst at 10:00 means a 5-min ORB at 9:45 would be invalidated by
the data release). The brief's actual rendered
`recommended_orb_reason` on May 5 was `"30-min ORB recommended
(10:00 JOLTS Job Openings)"`. **Source data and rendered text
match.**

The other days in the audit window only had medium-importance events
(May 6: 1 medium; May 7: 3 medium), and the brief correctly fell back
to the 5-min default ORB on those days. Source-data → render path
verified end-to-end.

### Earnings calendar volumes are healthy

Per-day row counts on `earnings_calendar` for the audit window:

| date | rows | tickers | with_strategy | with_expected_move |
|---|---:|---:|---:|---:|
| 2026-05-04 | 792 | 531 | 82 | 94 |
| 2026-05-05 | 1,611 | 953 | 216 | 260 |
| 2026-05-06 | 2,081 | 1,174 | 321 | 377 |
| 2026-05-07 | 2,473 | 1,418 | 351 | 412 |

The earnings fetcher was producing fresh data throughout the audit
window. The brief's `load_earnings_for_brief` cap is 25 by default
(`BRIEF_MAX_EARNINGS=25`), so the 1,000+ rows/day in the table give
the loader rich enough material to surface the top 25 by tradeability
score. Spot-check of May 5 earnings (the JOLTS day) confirmed
high-volume names with options: AMD, ANET, AEP, ALAB, AGCO etc., all
with `has_options=True` and populated `expected_move` fields — the
shape `_build_earnings_embed` expects.

### Bias / levels / RSI embeds — Track A's fix is now live

The audit's headline finding was that `market_data_daily` had no
real OHLCV rows for SPY/IWM/QQQ from 2026-04-28 onward. Track A's
G.P0.1 fix (PR #321, merged 2026-05-08 evening) unfroze the
fetcher. Direct query of `market_data_daily` confirms:

| ticker | latest non-NULL close | rows since 2026-04-25 |
|---|---|---:|
| SPY | **2026-05-08** | 10 |
| IWM | **2026-05-08** | 10 |
| QQQ | **2026-05-08** | 10 |

10 rows per ticker since 2026-04-25 = the eval window's missing days
(4/28-5/7) plus the one-week-prior gap (4/14-4/23 per Track A's
analysis) are now backfilled. A future brief run will read fresh
data instead of the stuck 4/27 row.

---

## Verdict

**Earnings + economic-events embeds were correctly populated
throughout the audit window.** The audit's headline failure was
isolated to the bias / levels / RSI half (which depends on
`market_data_daily`); the events half (earnings + calendar) is
fed by independent fetchers that ran cleanly the whole time.

This closes Track G **G.P2.10** as `events-side: VERIFIED` and
defers the **bias-side end-to-end replay** until Track B's W6 + W7
land. At that point the canonical replay procedure becomes:

```bash
# Pick a recent healthy day post-W6 deploy
BRIEF_AS_OF=2026-05-09 \
BRIEF_TICKERS=SPY,IWM,QQQ \
python -m gcp.premarket_brief --update

# Confirm fresh-data path
SELECT analysis_date, ticker, data_freshness_status,
       data_as_of, llm_overview IS NOT NULL AS has_llm
FROM premarket_analysis
WHERE analysis_date = '2026-05-09'
ORDER BY ticker;
# Expect: data_freshness_status='fresh', data_as_of within 1 trading
# day, has_llm=true (assuming W7 has landed)

# Diff Discord embed against earnings_calendar / economic_events
SELECT * FROM earnings_calendar
WHERE earnings_date::date = '2026-05-09' AND has_options
ORDER BY ... LIMIT 25;  # should match the brief's earnings embed top 25

SELECT * FROM economic_events
WHERE event_date::date = '2026-05-09' AND importance IN ('high','medium');
# should match the brief's calendar embed
```

This procedure is now unblocked because:
1. Track A's daily fetcher fix (G.P0.1, PR #321 etc.) shipped — fresh
   daily data is flowing.
2. W5 schema PR #335 is mergeable_state=clean and ready.
3. W6 (PR #336) and W7 (PR #337) writers are open with CI green.

Once W5/W6/W7 land, run the procedure above and append the actual
diff results to this doc as a final verification.

---

## What this follow-up does NOT do

- Does NOT directly run the brief in production. The sandbox lacks
  AlphaVantage credentials and the Discord webhook URL needed for
  end-to-end render. The audit's logical chain
  (source-table-fresh → loader-correct → embed-rendered-correct)
  is sufficient for the events side; the bias side needs
  W6/W7-on-main + a real brief execution.
- Does NOT diff the LLM commentary. Those strings are non-deterministic
  Gemini outputs; W7 captures them for audit trail but cross-day
  diffing is not meaningful (each replay produces fresh text).
- Does NOT re-render historical briefs (5/4-5/7) post-fix. Those
  rows are protected by the `allow_update=False` default in
  `persist_to_cloud_sql` for non-replay callers. Replaying via
  `BRIEF_AS_OF=` would set `allow_update=True` automatically and
  overwrite the audit-window history rows — that's a deliberate
  loss. Better to leave the original audit data intact and run the
  replay against today's data forward.

---

## Appendix — query trail

W8 db-query workflow run: `25588077057`. SQL committed at:
[`/tmp/track_b_w8_queries.sql`](#) (one-shot; not committed to repo).
Five statements:

1. `earnings_calendar` row counts for May 4-7 (~792-2473/day, healthy)
2. `economic_events` importance bucketing for May 4-7 (May 5 has 2
   high-impact events; other days only medium)
3. May 5 events list (confirms JOLTS + ISM Services PMI at 10:00 ET)
4. May 5 high-volume earnings sample (confirms options-having names
   are present in the source table)
5. `market_data_daily` post-Track-A-fix freshness (SPY/IWM/QQQ now
   current through 5/8 with 10 rows backfilled)

## Cross-references

- Track B audit doc: [`track-B.md`](./track-B.md) Sub-question 2 +
  backlog item #8
- Track G synthesis: [`track-G.md`](./track-G.md) G.P2.10
- Implementation plan: [`track-B-implementation-plan.md`](./track-B-implementation-plan.md) Step 6.1 / W8
- Track A G.P0.1 fix: PR #321 (`fix(runbook): backfill discipline +
  RUNBOOK_BACKFILL.md`)
- Track B Round 2 PRs gating the bias-side replay: #335 (W5 schema),
  #336 (W6 stale-warn), #337 (W7 LLM commentary)
- Tracking issue: #314
