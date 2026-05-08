# Track B — Premarket Brief Evaluation

**Eval window:** 2026-05-04 → 2026-05-07 (4 trading days × {SPY, IWM, QQQ})
**Audit date:** 2026-05-08
**Verdict:** **BROKEN** — the 8:30 AM brief ran every morning and produced
non-empty output, but it was operating on stale inputs. The
`market_data_daily` table has no SPY/IWM/QQQ OHLCV bars between
**2026-04-28 and 2026-05-08**, so every brief in the eval window read the
same 2026-04-27 row as "yesterday" and republished byte-identical bias,
PDH/PDL, change_pct, strat_candle, and playbook level triggers. The brief
itself didn't error out, didn't warn, and didn't surface the staleness
to the user.

This is a Track A foundation problem at the root, but it manifests in
Track B as a brief whose levels were structurally unreachable on 11 of
the 12 sessions and whose directional bias resolved to a 50/50 coin
flip on the directional days (4 hits / 4 misses across 8 directional
calls; the remaining 4 calls were `mixed` and uninformative).

The downstream blast radius is wide: the bias and playbook are consumed
by the AI insights pipeline (Track C), persisted to `strat_levels` for
the signal monitor's level-break detection (Track D), and shown to the
user as the morning Discord brief. All three consumers were fed
April-27 data on May 4–7.

---

## Sub-question 1 — Did the brief run?

**Yes, mechanically.** Twelve rows present in `premarket_analysis` and
twelve mirror rows in `premarket_analysis_history`, one per (date,
ticker) for May 4–7 × {SPY, IWM, QQQ}. Every history row has
`run_kind='scheduled'` and `triggered_by='cloud-scheduler:premarket-brief-daily'`.
No retries, no `manual_update`, no `auto_refresh`, no `replay_refresh`
in the window — meaning nobody ever noticed the stale-data problem and
re-ran the brief.

| analysis_date | written_at (ET)              | 3 tickers? |
|---------------|------------------------------|------------|
| 2026-05-04    | 08:30:31.605766              | yes        |
| 2026-05-05    | 08:30:30.533650              | yes        |
| 2026-05-06    | 08:30:29.468525              | yes        |
| 2026-05-07    | 08:30:34.058901              | yes        |

The Cloud Scheduler trigger fires reliably; the failure mode is
silent staleness, not job failure.

---

## Sub-question 2 — Section quality (sampled day: 2026-05-07 SPY)

The full row pulled from `premarket_analysis` for `(2026-05-07, SPY)`:

```
price                  715.17        ← actually 2026-04-27 close
rsi                    73.77         ← computed off the stale series
rsi_direction          up
consecutive_up         3
consecutive_down       0
signal_status          PUT setup (4/5)   ← contradicts the bullish FTFC
strat_candle           2U
strat_combo            322_bull_continuation
strat_setup            False             ← contradicts a "_continuation" combo
ftfc_score             1.0
ftfc_direction         bullish
ftfc_labels            {"1d":"2U","1w":"2U","1mo":"2U"}
prev_day_high          715.63        ← actually 2026-04-27 high
prev_day_low           712.295       ← actually 2026-04-27 low
analysis_ts            2026-05-07 12:30:34 UTC = 08:30 ET
change_pct             0.172         ← stale-series value
rvol                   0.38          ← stale
sma200                 665.77
ema9                   686.11
ema20                  674.60
atr14                  10.67
volatility_20d         0.241
macd_cross             Bullish
vol_regime             High
above_sma200           True
stoch_rsi_k            100.0
stoch_rsi_d            99.77
recommended_orb_window 5m
recommended_orb_reason 5-min ORB (default scalp window, no high-impact catalyst)
playbook               (see below)
```

The four Discord embeds the brief publishes:

1. **Overview** (`_build_overview_embed`, line 1175): populated. Renders
   the per-ticker price line, RSI arrow, RVOL, vol regime, and FTFC
   line. **Quality issue**: every value here is from 2026-04-27 — the
   "fresh look at this morning" framing the embed implies is false.
2. **Strat playbook** (`_build_playbook_embed`, line 1855): populated.
   Renders the trigger / stop / T1 / T2 block (see Sub-question 4 for
   the level analysis).
3. **Earnings calendar** (`_build_earnings_embed`, line 1400): not
   directly inspected per (date, ticker) — earnings data lives in a
   separate table (`earnings_calendar`) so the staleness in
   `market_data_daily` doesn't poison this section. Out of scope for
   the bias/level investigation.
4. **Economic events** (`_build_calendar_embed`, line 1764): not
   inspected for content; the `recommended_orb_reason` field
   ("5-min ORB (default ...)" or "30-min ORB recommended (10:00 JOLTS
   Job Openings)" on May 5) suggests `load_economic_events` is reaching
   the events table successfully and is not stale.

**Cross-check against `compute_strat_status` (`lib/strat.py:376`).** The
strat block is the same code path the AI insights pipeline uses
(`lib/agents/summarizers.py`). Because both consumers ingest the same
stale `market_data_daily` row, the brief and the insights agree on a
broken view — the unifying-source-of-truth invariant is preserved, just
on the wrong data.

The `daily_strat=2U` claim on May 7 SPY is consistent with the 2026-04-27
candle (open 713.17, high 715.63, low 712.295, close 715.17; the
2026-04-24 prior bar was lower). On April 27 it was a legitimate 2U.
Republishing it as the May-7 daily candle is just plain wrong.

**Internal contradictions surfaced by the section sample**:
- `signal_status="PUT setup (4/5)"` while `ftfc_direction="bullish"` and
  `strat_combo="322_bull_continuation"`. The bias-and-status contradict
  each other. This is structural — `signal_status` comes from
  `check_call_conditions` / `check_put_conditions` (line 796–808),
  which scores against indicator thresholds independently of FTFC.
  Downstream code that assumes "bias = signal direction" is wrong on
  every row in this dataset.
- `strat_candle="2U", strat_combo="322_bull_continuation",
  strat_setup=False`. A 322 continuation combo with `strat_setup=False`
  is suspect — typically the `strat_setup` flag should be TRUE when a
  named combo is in force. Same row for SPY May 4–7 (and IWM, mirroring
  values).
- These contradictions are upstream of the staleness problem (they
  exist in 2026-04-27's bar) but the staleness amplifies them by
  republishing the same broken row four mornings in a row instead of
  letting the next bar overwrite it.

---

## Sub-question 3 — Bias accuracy (per session)

Brief bias is `ftfc_direction`. Actual session direction is computed
from the intraday partition (`market_data_intraday`) — daily bars are
missing for the entire window, so we use `(close-of-16:00-bar) /
(open-of-09:30-bar) - 1` per session.

| Date  | Ticker | RTH Open | RTH Close | Day move | Brief bias | Verdict |
|-------|--------|----------|-----------|----------|------------|---------|
| 5/4   | IWM    | 278.70   | 277.74    | −0.34%   | bullish    | **MISS** |
| 5/4   | QQQ    | 674.66   | 672.44    | −0.33%   | mixed      | mixed→down (uninformative) |
| 5/4   | SPY    | 720.07   | 717.73    | −0.32%   | bullish    | **MISS** |
| 5/5   | IWM    | 280.13   | 282.61    | +0.89%   | bullish    | HIT |
| 5/5   | QQQ    | 677.96   | 681.49    | +0.52%   | mixed      | mixed→up (uninformative) |
| 5/5   | SPY    | 721.77   | 723.75    | +0.27%   | bullish    | HIT (small magnitude) |
| 5/6   | IWM    | 285.36   | 286.59    | +0.43%   | bullish    | HIT |
| 5/6   | QQQ    | 687.78   | 695.44    | +1.11%   | mixed      | mixed→up (uninformative) |
| 5/6   | SPY    | 728.16   | 733.65    | +0.75%   | bullish    | HIT |
| 5/7   | IWM    | 287.53   | 282.09    | −1.89%   | bullish    | **MISS** |
| 5/7   | QQQ    | 696.58   | 694.38    | −0.32%   | mixed      | mixed→down (uninformative) |
| 5/7   | SPY    | 735.05   | 730.90    | −0.56%   | bullish    | **MISS** |

**Summary**:
- Directional calls (excluding `mixed`): 8 calls, **4 hits / 4 misses
  (50%)**.
- IWM bias = bullish all 4 days; IWM was up 2, down 2.
- SPY bias = bullish all 4 days; SPY was up 2, down 2.
- QQQ bias = mixed all 4 days; produces no testable directional call.
- Because the underlying daily row never changed in the window, the
  brief's bias was effectively constant across May 4–7. A constant
  bias on a chop-up-down-up-down series gets 50% by definition. There
  was no information added by the brief beyond "what April-27's daily
  bar said".

**The accuracy number understates the breakage.** If daily data had
been current, the brief on May 5 would have re-evaluated FTFC against
the May 4 close (down −0.32% intraday) and likely flipped bullish→mixed
or bearish — and the same compute path on May 6 would re-flip after
the +0.75% session. The 50% hit rate is what a stuck thermostat
produces; it is not evidence that the bias logic itself works.

---

## Sub-question 4 — Levels accuracy

The published `playbook` field for each (date, ticker) is byte-identical
across May 4–7 (only the `recommended_orb_window` differs on May 5,
where 30-min ORB was selected for the 10:00 ET JOLTS release). The
trigger levels were:

| Ticker | CALL trigger          | PUT trigger          |
|--------|-----------------------|----------------------|
| SPY    | (suppressed — "no near-term structural level") | 714.47 (PWH) |
| IWM    | 278.13 (PDH)          | 276.82 (CWO)         |
| QQQ    | 664.51 (PDH)          | 663.40 (CWO)         |

Compared to the actual intraday range each session:

| Date | Ticker | RTH range            | CALL trig touched? | PUT trig touched? |
|------|--------|----------------------|--------------------|-------------------|
| 5/4  | IWM    | 276.10 – 280.79      | yes (gap-cleared at open 278.70) | yes (low 276.10 < 276.82) |
| 5/4  | QQQ    | 668.90 – 676.73      | yes (gap-cleared at open 674.66) | no (low 668.90 > 663.40) |
| 5/4  | SPY    | 714.99 – 722.12      | n/a                | no (low 714.99 > 714.47, by 0.07%) |
| 5/5  | IWM    | 280.00 – 282.945     | yes (open 280.13 already > 278.13) | no (price never came back below 280) |
| 5/5  | QQQ    | 677.51 – 682.77      | yes (already cleared) | no |
| 5/5  | SPY    | 721.49 – 725.04      | n/a                | no (~7 pts below low) |
| 5/6  | IWM    | 283.36 – 287.045     | yes (already cleared) | no |
| 5/6  | QQQ    | 686.48 – 695.93      | yes (already cleared) | no |
| 5/6  | SPY    | 723.62 – 734.59      | n/a                | no |
| 5/7  | IWM    | 281.15 – 287.58      | yes (already cleared) | no |
| 5/7  | QQQ    | 691.77 – 701.24      | yes (already cleared) | no |
| 5/7  | SPY    | 729.75 – 736.13      | n/a                | no |

**Touch rate**:
- IWM CALL trigger 278.13: touched 4/4 sessions, but on 3 of them it was
  cleared in pre-market and the trigger was a backward-looking marker,
  not a forward-looking entry signal.
- IWM PUT trigger 276.82: touched 1/4 (only May 4).
- QQQ CALL trigger 664.51: touched 4/4, but again all 4 were
  pre-market-cleared (open ≥ 674).
- QQQ PUT trigger 663.40: touched 0/4.
- SPY CALL trigger: not published (the staleness filter dropped it
  every morning because it would have been further than 3 ATR above
  the stale price — a side-effect of the price field being 2 weeks
  old vs the actual market).
- SPY PUT trigger 714.47: touched 0/4 (May 4 was closest, low
  714.99, missed by 0.07%).

**Held vs faded** is mostly not testable because most triggers were
gap-cleared, not actively broken intraday. For the one session where a
PUT trigger was tagged (IWM May 4 PUT 276.82, low 276.10), the close
was 277.74 — back above the trigger — so the breakout *faded* (a real
PUT entry at trigger break would have been stopped out as the stop was
278.13 and price closed above 277). Levels-accuracy on the only
testable case: FAIL.

The playbook formatter (`lib.strat_levels.format_levels_for_brief`,
line 790) does try to detect this regime — both IWM and QQQ playbooks
include the line `CALLS: pre-market cleared every structural level on
this side — wait for the 15-min ORB`. The detection works
**on each individual morning**, but it doesn't catch the underlying
problem that the structural levels are old. The trader sees the same
"pre-market cleared every level" warning four mornings in a row and
has no way to know it's because the levels are 7+ days stale, not
because the market has been chopping above them.

---

## Sub-question 5 — Entry / stop / target sanity (days bias was right)

The brief's targets use the playbook's per-side T1/T2 prices (which
collapse to the trigger itself when no further structural level
exists), NOT the global +0.30%/−0.38% percent targets — those live in
`lib/config.py:ExitConfig` and are consumed by the signal monitor
(Track D), not the brief.

For the 4 sessions where the brief's bullish bias was directionally
correct (5/5 IWM, 5/5 SPY, 5/6 IWM, 5/6 SPY), the published CALL
playbook would have been:

- **5/5 IWM**: CALL trigger 278.13 (PDH), T1 = 278.13 (PWH; collapsed
  to trigger), stop 276.82. Open 280.13 was already above trigger, so
  trigger was a meaningless "already cleared" marker. T1 = trigger
  means 0% room, which is structurally degenerate. Real session high
  reached 282.945 — a +1.0% intraday move from open — but the playbook
  gave the trader no target above 278.13.
- **5/5 SPY**: CALL playbook suppressed entirely ("no near-term
  structural level"). The trader gets no actionable CALL plan despite
  bias=bullish.
- **5/6 IWM**: same as 5/5 IWM — trigger and T1 collapsed at 278.13;
  open 285.36 already above. Trigger irrelevant.
- **5/6 SPY**: CALL playbook suppressed.

**Sanity verdict**: on the days the bias was right, the actionable
plan ranged from "no plan" (SPY: CALLS suppressed) to "plan that
collapsed to a single price already cleared" (IWM: trigger ≡ T1, both
pre-market-cleared). A well-disciplined trader following the brief
verbatim would not have opened a CALL position on any of the 4 hit
sessions because the playbook either offered no entry or offered an
entry that pre-market had already invalidated.

This is downstream of the staleness — fresh PDH/PWH numbers would
have re-collapsed against the live price each morning instead of
sitting 7+ trading days behind it.

---

## Cross-track signal: brief → signal monitor handshake

`signal_alerts.brief_bias` and `brief_alignment` are populated by the
signal monitor (Track D's domain) at fire-time, by reading the same
morning's `premarket_analysis` row. In our window:

| alert_date | rows with brief_bias populated |
|------------|--------------------------------|
| 2026-05-04 | 0 (out of 79 alerts)           |
| 2026-05-05 | 0 (out of 155 alerts)          |
| 2026-05-06 | 0 (out of 162 alerts)          |
| 2026-05-07 | 386 (out of 386 alerts)        |

The signal monitor was not consuming `brief_bias` on May 4–6. That is a
Track D investigation, but it surfaces here as evidence that the brief
isn't yet reliably providing the cross-system context the rest of the
pipeline expects. On May 7 it began consuming bias, and 4 of 6
(ticker, direction) buckets came back as `CONFLICTED` — the brief
publishes both `ftfc_direction='bullish'` and
`signal_status='PUT setup (4/5)'` on the same row, so the monitor
can't decide which signal the brief actually meant. The
`CONFLICTED` rate is a brief-side ambiguity that Track B should fix at
source rather than asking Track D to disambiguate downstream.

---

## Why this happened (root cause sketch)

The brief's data path is `DataLoader.load_daily(ticker)` →
`market_data_daily` table. The fetcher that populates that table is
the `fetch-market-data.yml` workflow (Cloud Run Job
`fetch-market-data`), scheduled to run nightly. The most recent real
OHLCV row for SPY/IWM/QQQ is dated **2026-04-27** (volume 33M for SPY,
inserted 2026-04-28 05:14 UTC). Every weekday after that has either no
row at all (May 1) or a NULL-OHLCV placeholder (May 8 row, inserted
this morning at 08:20 ET — exactly the "null-row pattern" that
[`docs/incidents/2026-04-30-null-rows.md`](../../incidents/2026-04-30-null-rows.md)
documented and that `gcp/premarket_brief.py:724` defensively filters
out).

The brief's filter at line 724 is the proximate cause of the silent
staleness:

```python
df = df[df[close_col].notna()]   # line 724
# ... if df.empty or len(df) < 2: NO DATA, else continue
```

This filter is correct in spirit (don't let a NULL row crash the
strat classifier), but combined with a daily fetcher that has been
silently failing for 7 trading days, it means `df.iloc[-1]` returns
the 2026-04-27 row every morning with no warning surfaced to the user.
The brief logs `[brief:%s] dropped %d row(s) with null close` to
stderr, but that stderr line never reaches the morning Discord embed
or the `notes` column of `premarket_analysis_history`. The downstream
view is "brief ran, brief succeeded, here's your morning plan" — which
is the worst possible failure shape (silent partial degradation with
all the polish of a successful run).

The fact that the brief's `change_pct=+0.177%` and PDH/PDL line up
exactly with the 2026-04-27 bar pegs the staleness duration at exactly
the gap between the last-known-good fetch and today.

This is fundamentally a Track A foundation problem (daily fetcher
broken, no alert raised). Track B's role is to surface it, not to fix
the fetcher; but the brief's own failure mode — silent re-publication
— deserves its own remediation regardless of whether Track A fixes the
fetcher.

---

## Track B verdict

**BROKEN.** Three failure layers stacked:

1. **Foundation (Track A)**: `market_data_daily` has no real OHLCV
   rows for SPY/IWM/QQQ from 2026-04-28 onward. Daily fetcher has been
   silently failing for at least 7 trading days. Single-line repro:
   `SELECT max(date) FROM market_data_daily WHERE ticker='SPY' AND
   close IS NOT NULL` → 2026-04-27.
2. **Brief silent staleness**: the brief's null-close filter
   (`gcp/premarket_brief.py:724`) gracefully degrades into reading the
   2026-04-27 row every morning, with no surfaced warning. Output looks
   identical to a healthy run.
3. **Downstream amplification**: the `signal_status` ↔ `ftfc_direction`
   contradiction (PUT setup on a bullish-FTFC row) feeds the signal
   monitor's `brief_alignment` logic and produces the
   `CONFLICTED` value on 4 of 6 alert buckets where bias was even
   consumed at all.

Output quality on the eval window:
- 12/12 rows present, 0 retries, 0 failures recorded.
- 4/8 directional bias hits (50%); the other 4 calls were `mixed` and
  carried no information.
- 1/12 sessions where any published trigger level was meaningfully
  in-range (IWM May 4 PUT side); the other 11 sessions had triggers
  that were either gap-cleared at open or structurally too far from
  spot to be touched.
- 0/4 actionable CALL plans on the days the brief's bullish bias was
  directionally correct.

The brief is currently a **broken thermometer that always reads
72°F** — looks fine if you don't compare it to the actual
temperature.

---

## Backlog (for Track G synthesis to prioritize)

1. **P0 — Fix the daily fetcher** *(belongs to Track A's backlog, but
   it gates everything Track B does)*. Without this, every other Track
   B fix is cosmetic.

2. **P0 — Brief should fail loudly on stale prior-day data.** Concrete
   change: in `generate_premarket_brief` (after line 741), check the
   age of `latest.name` (the index of `df.iloc[-1]`) against
   `analysis_date`. If the gap is > 1 trading day for non-Monday runs,
   either:
   - Set `data['status'] = 'STALE_DAILY_DATA'` and skip the per-ticker
     row entirely (so it lands in `premarket_analysis_history` with a
     `notes` annotation but does NOT corrupt `premarket_analysis`), OR
   - Emit a high-severity warning into the brief's overview embed
     (`_build_overview_embed`) that the daily data is N days stale,
     so the morning Discord brief itself is the alarm. This is
     analogous to the `regime_compute_error` line that already
     surfaces in the playbook when the regime classifier fails
     (`lib/strat_levels.py:840`).
   The current behavior — silently reading the last-good row — was
   safe-by-design for one-day fetcher hiccups; it is unsafe for
   week-long outages.

3. **P0 — `premarket_analysis_history.notes` is unused.** The schema
   has the column (`gcp/schema.sql:1232`), but `persist_to_cloud_sql`
   never populates it. Wire it to record the staleness gap, the
   number of dropped null-close rows, and any
   `regime_compute_error` so historical replays can distinguish a
   healthy run from a degraded one. Without this column populated,
   Track G has no single-query view of which historical briefs are
   trustworthy.

4. **P1 — Resolve `signal_status` vs `ftfc_direction` contradiction.**
   The code path at `gcp/premarket_brief.py:796-808` scores call/put
   conditions independently of FTFC. On a bullish-FTFC row, surfacing
   `signal_status='PUT setup'` makes the brief look self-contradicting
   to humans and to the signal monitor (which marks 4/6 May-7 alert
   buckets as `CONFLICTED`). Two reasonable fixes:
   - Gate `signal_status` by FTFC direction, so a bullish FTFC can't
     publish a PUT setup status (and vice versa). This loses the
     "fade the bias" play at the cost of consistency.
   - Rename the field to `signal_status_indicator_score` and add a
     separate `bias_aligned_signal` field that respects FTFC, so
     downstream can read the unambiguous version. This keeps the
     fade-play data but stops asking consumers to disambiguate.

5. **P1 — `strat_setup` flag drift.** May-7 SPY publishes
   `strat_combo='322_bull_continuation'` with `strat_setup=False`. A
   named continuation combo with `strat_setup=False` is internally
   inconsistent. Audit `lib.strat.StratClassifier.detect_combos` to
   confirm whether `strat_setup` is meant to be true whenever a
   non-`none` combo is in force, or whether the brief is reading the
   wrong column.

6. **P1 — Levels playbook needs a "all-pre-cleared" suppress.** The
   IWM and QQQ playbooks repeatedly publish a "CALLS above N (PDH)"
   line whose trigger is below the actual open. The
   `format_levels_for_brief` formatter has the `orb_only` regime path
   that suppresses both sides, but only fires when *every* structural
   level is cleared (`lib/strat_levels.py:856`). The intermediate case
   — "this side is fully cleared, the other isn't" — currently emits
   a warning banner but still publishes the now-meaningless trigger
   block. Suppress the trigger block on the cleared side or print
   the *next unbroken* level above spot instead.

7. **(superseded by P1 #10 below — was P2 "freshness assertion field";
   the audit-of-audit pass upgraded this to user-facing P1 with a
   wider scope, see item #10.)**

8. **P2 — Earnings / calendar embed quality not yet sampled.** This
   audit treated the bias/levels half of the brief and inferred from
   `recommended_orb_reason` that the events table was reachable. A
   fuller embed-quality audit (sample 1 day, render the four embeds
   end-to-end, and diff against actual that-morning earnings/events)
   would close the loop on Sub-question 2 from the plan.

---

## Audit-of-audit additions (2026-05-08, after self-review)

These items close gaps the original write-up left open. None of them
change the verdict (still BROKEN); they harden the evidence and add
two new backlog items.

### A. Strat candle classification — manually verified

The original write-up said "the 2U claim is consistent with the 2026-04-27
bar" but didn't compute it from primary data. With the April 24 vs
April 27 daily bars now in hand:

| Ticker | 4/24 H/L         | 4/27 H/L         | Rule                           | Class |
|--------|------------------|------------------|--------------------------------|-------|
| SPY    | 714.47 / 709.01  | 715.63 / 712.295 | H₂>H₁ AND L₂≥L₁ → 2U          | **2U ✓** |
| IWM    | 278.13 / 274.23  | 278.24 / 276.25  | H₂>H₁ AND L₂≥L₁ → 2U          | **2U ✓** |
| QQQ    | 664.51 / 656.530 | 664.43 / 660.69  | H₂<H₁ AND L₂>L₁ → inside ("1") | **1 ✓** |

The brief published `strat_candle=2U` for SPY/IWM and `1` for QQQ —
all three classifications are correct against the underlying April 27
bar. **The strat classifier itself is fine; the staleness is the
problem.** This rules out a coexisting "classifier bug" hypothesis and
narrows the fix to the data layer + the brief's freshness gate.

### B. `strat_levels` is also stale-replicated

Each morning the brief calls `persist_level_map` and writes 17 levels
per ticker per day (CDO, CMO, CWO, GAP_H_2026-04-08, GAP_H_2026-04-24,
GAP_L_2026-04-08, GAP_L_2026-04-24, PDH, PDL, PMH, PML, PQH, PQL,
PWH, PWL, PYH, PYL). For May 4–7 × {SPY, IWM, QQQ}:

- 12 (date, ticker) groups × 17 levels = **204 rows persisted**.
- The 17 level *names* per (date, ticker) are identical across all 4
  dates (set membership matches byte-for-byte).
- The 17 level *prices* per (date, ticker) are also identical across
  all 4 dates — confirmed by inspecting IWM rows in
  `snapshots/track-B/07-strat-levels-rows.csv`: CDO=276.82, CWO=276.82,
  PDH=278.13, PDL=274.23, etc. for every as_of date in the window.

**Cross-track signal**: the live signal monitor reads `strat_levels` to
detect intraday level breaks (per `gcp/signal_monitor.py` and the
`level_broken` column in `signal_alerts`). On May 5–7 it was watching
for breaks of 2026-04-27-derived levels — every one of which had
already been gap-cleared in pre-market. The level-break detection path
in the monitor was effectively dead-on-arrival each morning, even on
sessions where the monitor itself was fully healthy. Track D should
verify whether `level_broken` was always populated against stale levels
in this window.

### C. Daily-data gap span — exactly 8 trading days

Using a row-by-row scan of `market_data_daily` from 2026-04-25 to
today:

| ticker | last real bar | first NULL row     | rows in May 4–7 |
|--------|---------------|--------------------|------------------|
| SPY    | 2026-04-27    | 2026-05-08 (today) | **0**            |
| IWM    | 2026-04-27    | 2026-05-08 (today) | **0**            |
| QQQ    | 2026-04-27    | 2026-05-08 (today) | **0**            |

April 28, 29, 30 and May 1, 2, 3, 4, 5, 6, 7 have **no row of any
kind** for these three tickers (not even a NULL placeholder). Only
May 8 has a NULL placeholder, inserted at 08:20 UTC this morning. The
daily fetcher has been silently dropping all OHLCV for the eval
window for at least 8 trading days.

Table-wide blast radius (likely Track A's headline): there are **124
NULL-close rows** in `market_data_daily` overall, spanning min_date
2026-04-30 → max_date 2026-05-08. So the failure isn't just the three
ETFs — dozens of other tickers are showing the null-placeholder
pattern over the same period.

### D. SPX intraday — STILL MISSING in the eval window

`market_data_intraday_spx` has **0 rows** for any session between
2026-05-04 and 2026-05-07. The plan flagged this as "the Dec 2025 SPX
intraday gap" and asked Track A to confirm whether it was backfilled.
**It is not backfilled, and the gap now extends into May.** This is
out of scope for Track B's bias/levels audit (the brief tickers are
SPY/IWM/QQQ, not SPX), but it's relevant context for Track D's signal
monitor evaluation.

### E. `premarket_analysis` does not persist any LLM-generated fields

The brief code populates four LLM slots in the in-memory dict
(`brief['llm_overview']`, `brief['llm_orb_explanation']`,
`brief['tickers'][T]['llm_analysis']`,
`brief['tickers'][T]['llm_playbook']`) and renders them into the
Discord embeds, but the `premarket_analysis` table schema has no
columns for them (verified — only 35 columns, none of them `llm_*`).
**Implication**: the morning Discord brief shows LLM commentary that
no historical replay or audit can ever reproduce. If the LLM was
hallucinating bias or misreading the playbook on a given morning, you
can't see that from the database — only the live Discord post.

This is a P2 backlog addition: persist the four LLM strings in
`premarket_analysis` (or a sidecar `premarket_llm_explanations`
table) so post-hoc audits can grade LLM commentary, not just
deterministic fields.

### F. Embed quality (Sub-question 2 from the plan, completion)

The original write-up sampled the **overview** and **playbook** embeds
on May 7 SPY and admitted earnings/calendar were not directly
inspected. From the in-memory dict structure and the brief's
`generate_premarket_brief` pipeline, what we can say:

- **Overview embed** (`_build_overview_embed`, line 1175) is populated
  for all 12 (date, ticker) cells — every cell has the price, RSI,
  RVOL, and SMA200 fields needed to render the per-ticker line. Stale
  but populated.
- **Playbook embed** (`_build_playbook_embed`, line 1855) is populated
  for all 12 cells — confirmed via `length(playbook) > 0` on every
  row in `snapshots/track-B/02-playbook-content.csv`. Stale but populated.
- **Earnings embed**: not stored to `premarket_analysis`. The brief
  builds it from `load_earnings_for_brief` against `earnings_calendar`
  every morning. Whether the earnings table itself is fresh is a Track
  A finding (orthogonal to the daily-OHLCV problem). One indirect
  sanity check: May 7's `recommended_orb_reason` was "5-min ORB
  (default scalp window, no high-impact catalyst)" while May 5's was
  "30-min ORB recommended (10:00 JOLTS Job Openings)" — the events
  table is therefore reachable and the per-day variation works.
- **Calendar embed**: same as earnings — not persisted, so a strict
  post-hoc audit needs the live morning Discord transcript or a
  replay run. The ORB reason variation across May 4–7 is the only
  evidence we have that the calendar pipeline isn't itself stuck.

This is now a closed sub-question; the residual P2 audit (sample one
morning's full earnings + calendar Discord render) remains in the
backlog as item #8.

### G. No regressions from this audit

This audit is read-only: zero code changes, zero data writes (every
db-query workflow dispatch ran with `commit=false`, transactions
rolled back). The only filesystem changes are the new
`docs/audit/2026-05-08/track-B.md` findings doc and the
`docs/audit/2026-05-08/snapshots/track-B/*.csv` raw-data snapshots — both
are new files in a new directory, so nothing existing is modified.

### Updated backlog items (additions)

9. **P1 — Auto-backfill on staleness, then defensively skip `strat_levels`
   persistence.** When the brief detects that
   `(analysis_date - last_daily_bar_date) > 1` trading day, do two
   things in this order:
   1. **Kick off a backfill of the missing daily bars before continuing.**
      The fetcher is the `fetch-market-data` Cloud Run Job; the brief
      can invoke it synchronously via the Cloud Run Admin API
      (`gcloud run jobs execute fetch-market-data --wait`) or the
      Python `google-cloud-run` client, scoped to the missing date
      range. Make it idempotent: check for an in-flight execution
      before launching a new one so a 9:25 AM signal-monitor restart
      doesn't double-trigger. After the backfill, re-load the daily
      df and re-run the per-ticker analysis loop. If the backfill
      itself fails (e.g. AlphaVantage rate-limited), fall through to
      step 2.
   2. **Skip the `persist_level_map` call** at
      `gcp/premarket_brief.py:1030` for any ticker whose data is
      still stale post-backfill. Today this writes 17 rows per
      ticker every morning regardless of staleness; the rows
      directly corrupt the signal monitor's level-break detection
      (Track D will see `level_broken` firing against levels that
      were gone pre-market). Either skip the persist entirely or
      stamp each row with a `data_age_trading_days` column so
      downstream consumers can decide whether to trust it.

   Combining backfill + skip is important: a pure skip leaves users
   without a brief; a pure backfill leaves us with corrupted
   downstream state when the backfill itself fails. The two-phase
   approach degrades gracefully.

10. **P1 — Brief and report outputs must surface the data window.**
    Today the brief publishes prices, levels, and bias with no
    indication of which underlying data window produced them. Two
    additions, both for human validation and for downstream consumers:

    - **Per-ticker `data_as_of` field**: every (date, ticker) row in
      `premarket_analysis` should record the timestamp of the last
      OHLCV bar used for that ticker (i.e. `df.iloc[-1].name` in the
      brief loop). Add the column to `premarket_analysis` and
      `premarket_analysis_history`. Track G can then run
      `WHERE data_as_of < analysis_date - INTERVAL '1 trading day'`
      as a single-query freshness audit, and the AI insights pipeline
      (Track C) can read `data_as_of` to know whether the brief it's
      summarizing is current.
    - **User-facing "based on data from X to Y" line in the Discord
      embed**: render in the overview embed (or the per-ticker
      analysis field) something like
      `Based on data from 2026-04-27 → 2026-04-27 (1 trading day,
      stale by 6 sessions)` for a stuck-fetcher day, or
      `Based on data from 2025-05-08 → 2026-05-07 (252 trading days)`
      for a healthy day where SMA200 is in scope. This makes
      staleness visible to the trader the moment they read the brief
      on their phone, instead of requiring them to spot it from
      bias/levels that don't move.

    Together with item #9, this means: the brief tries to fix the
    staleness (#9.1), guards downstream state when it can't (#9.2),
    and tells the user exactly what window it's working from
    regardless (#10).

11. **P2 — Persist LLM-generated brief commentary.** Add columns
    `llm_overview`, `llm_orb_explanation`, and per-ticker
    `llm_analysis` / `llm_playbook` to either `premarket_analysis` or
    a sidecar `premarket_llm_explanations` table. Without this, no
    audit can ever grade what the LLM actually told users on a given
    morning — only the deterministic fields are replayable.

---

## Reusability of fetched data

**Will the data stick?** The CSVs in `docs/audit/2026-05-08/snapshots/track-B/`
are point-in-time snapshots of `market_data_daily`,
`market_data_intraday`, `premarket_analysis`,
`premarket_analysis_history`, `signal_alerts`, and `strat_levels` as
of approximately **2026-05-08 13:14 ET**. They were retrieved via the
`db-query.yml` workflow with `commit=false`, so the queries
themselves did not modify any database state.

**Can other tracks reuse this data?** Yes, with caveats:

- **Stable, won't change**: The intraday RTH OHLC for May 4–7
  (files 04, 05, 11, 12) is anchored to historical bars and won't be
  overwritten by future fetches; safe to reuse forever.
- **Will change once Track A fixes the fetcher**: The `market_data_daily`
  snapshots (files 08, 09, 13, 17) reflect the broken state of the
  table today. When the daily fetcher gets fixed and backfills May 4–7,
  these CSVs will go out of date — they will become a historical
  record of "what the table looked like before the fix" rather than
  "the current truth". That is itself useful for Track G (proves the
  brief was reading bad data); just don't use them as ground truth
  for ticker prices on those days.
- **Frozen at first-write**: The `premarket_analysis` rows for May 4–7
  (files 01, 02, 03, 06) cannot be overwritten by automatic re-runs —
  the `persist_to_cloud_sql` path requires `allow_update=True` (only
  set by `--update` CLI flag or a Discord `/replay`). Until someone
  explicitly replays those mornings, the rows in those CSVs are also
  what's in the production table.
- **Append-only**: The `premarket_analysis_history` rows (file 03)
  and `strat_levels` rows (files 07, 15, 16) are append-only by
  design; the snapshot will remain a valid subset of the live table.
- **The signal_alerts snapshot** (file 10) covers brief_bias coverage
  and is also append-only; safe to reuse.

**Track G synthesis can reference any of these CSVs by relative path
(`docs/audit/2026-05-08/snapshots/track-B/NN-name.csv`) and they will be
present in the branch.**

---

## Appendix — query trail

All SQL was dispatched via the `db-query.yml` workflow. Run IDs and
artifact IDs:

- `25557485495` — main batched 8-statement query (12 brief rows × 4
  dates × 3 tickers, playbook content, history runs, daily OHLC
  diagnostic, intraday extremes, 9:30 opening bars, May-7 SPY full
  JSON, persisted strat_levels). Artifact `6879921881`.
- `25557660050` — follow-up: market_data_daily freshness diagnostic +
  signal_alerts.brief_bias cross-check. Artifact `6879980197`.
- `25557802130` — intraday-derived RTH close per session (since daily
  data is missing) + null-row diagnostic. Artifact `6880037749`.
- `25558734056` — audit-of-audit pass: April 24 prior bar
  verification, strat_levels staleness, daily-gap span, SPX intraday
  coverage, non-scheduled-rerun detection, table-wide null-row count.
  Artifact `6880451705`.

Track A is the canonical owner of the foundation finding (daily
fetcher dead since 2026-04-28); Track B's job here was to surface
how that foundation gap manifests in the brief's morning output and
recommend the brief-side guardrails that would have made the failure
loud.
