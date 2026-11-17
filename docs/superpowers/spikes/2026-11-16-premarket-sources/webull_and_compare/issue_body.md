## Summary

1. The premarket brief reads Alpha Vantage one-minute bars at about 08:20 ET. After the close Alpha Vantage replaces that day's bars with a revised version, and only the revised version is stored in `market_data_intraday`.
2. On 2026-11-16 the two versions agree on all four prices in only 65 of 327 SPY, 61 of 330 QQQ and 36 of 196 IWM premarket minutes, and the stored volumes are 1.9 to 3.5 times the in-session volumes (median per minute).
3. Webull's premarket bars, read after the revision, look like the in-session read (all four prices agree in 301, 297 and 186 of those minutes, volume ratio 1.00), but hold none of the prior-close prints and none of the one-bar spikes such as IWM's 278.92 at 08:05.
4. So every measurement and replay done on stored bars studies data the brief never saw, and no morning can be replayed exactly.
5. Proposed first step: save the bars each premarket run reads, as read. Then use Webull as a cross-check. This issue records the problem for later; nothing was changed.

## What we found

### The data

Three versions of the 2026-11-16 premarket (bars stamped 04:00 to 09:29 ET) for SPY, QQQ and IWM:

| Name used below | What it is | When it was read |
|---|---|---|
| AV in-session | Alpha Vantage intraday 1min, `entitlement=realtime`, `adjusted=false`, `extended_hours=true` | files written 19:55Z (14:55 ET) on 2026-11-16 |
| Stored | `market_data_intraday` after the nightly-style fetch (execution `fetch-alphavantage-intraday-8549t`), same vendor and parameters, exported read-only (`db-query-jc8mj`) | rows inserted 22:26:51Z (IWM), 22:27:03Z (SPY), 22:27:17Z (QQQ) |
| Webull | Webull `get_stock_bars_single`, `M1`, `trading_sessions=PRE` (parameters at the end) | about 00:01Z on 2026-11-17 (19:01 ET on 11-16) |

The brief's cutoff is `level_basis.premarket.fetched_at`: 13:20:48Z (IWM), 13:20:55Z (QQQ), 13:20:58Z (SPY). "To 08:20" below means bars stamped 04:00 to 08:19 ET. Prior closes: SPY 754.37, QQQ 679.89, IWM 277.54. Alpha Vantage and Webull stamp minutes the same way: SPY closes agree to the cent on 314 of 327 minutes with no shift and on 11 of 324 with a one-minute shift either way.

### 1. The brief read the in-session version, not the stored one

| Check | Brief recorded | AV in-session, to 08:20 | Stored, to 08:20 |
|---|---|---|---|
| IWM premarket volume (`market_data_daily.pre_volume`) | 32,653 | 32,653 | 154,393 |
| SPY premarket volume | 297,421 | 297,418 | 744,145 |
| QQQ premarket volume | 533,831 | 532,886 | 1,253,349 |
| IWM `pre_vwap`, with the brief's recorded ATR and filter thresholds | 276.37323242887334 | 276.37323242887334 | 276.4271 |
| SPY `pre_vwap`, same | 750.244655 | 750.244662 | 750.348791 |
| QQQ `pre_vwap`, same | 672.084228 | 672.086176 (672.084163 with the 08:20 bar, still forming at the read) | 672.370407 |
| Stale prints excluded, SPY / QQQ / IWM | 9 / 16 / 7 | 9 / 16 / 7 | 12 / 16 / 9 |
| `pre_high` / `pre_low` recorded (old code), against the raw max high / min low | SPY 754.3772 / 747.95, QQQ 681.022 / 668.30, IWM 278.92 / 275.86 | the same six numbers | SPY 754.3772 / 747.94, QQQ 681.022 / 668.28, IWM 278.92 / 275.74 |

### 2. Bar counts

| | SPY | QQQ | IWM |
|---|---|---|---|
| Bars, AV in-session / stored / Webull, 04:00 to 09:29 | 327 / 329 / 327 | 330 / 330 / 330 | 199 / 289 / 196 |
| Bars to 08:20 | 257 / 259 / 257 | 260 / 260 / 260 | 131 / 220 / 128 |
| Minutes in stored, not in AV in-session | 2 (05:23, 06:33) | 0 | 90 |
| Minutes in stored, not in Webull | 2 | 0 | 93 |
| Minutes in AV in-session, not in Webull | 0 | 0 | 3 (04:05, 07:40, 08:05) |
| Minutes in Webull, not in either AV version | 0 | 0 | 0 |

The 90 IWM minutes that only the stored version has hold 41,594 shares (median 71.5 a minute, largest 28,705 at 04:03 ET). One of them sets the stored low: 07:29 ET, low 275.74 on 284 shares, absent from the in-session read and from Webull.

### 3. Prices, minutes present in all three (agree to the cent)

| Pair | Ticker (minutes) | Open | High | Low | Close | All four |
|---|---|---|---|---|---|---|
| AV in-session vs stored | SPY (327) | 188 | 212 | 203 | 200 | 65 |
| | QQQ (330) | 196 | 211 | 215 | 195 | 61 |
| | IWM (196) | 95 | 109 | 100 | 111 | 36 |
| AV in-session vs Webull | SPY | 320 | 309 | 315 | 314 | 301 |
| | QQQ | 320 | 303 | 319 | 319 | 297 |
| | IWM | 193 | 190 | 192 | 192 | 186 |
| Stored vs Webull | SPY | 186 | 195 | 191 | 194 | 60 |
| | QQQ | 191 | 186 | 204 | 186 | 52 |
| | IWM | 92 | 104 | 97 | 109 | 33 |

All three agree exactly where stored and Webull agree (the same counts as the last three rows).

### 4. Volume

| | SPY | QQQ | IWM |
|---|---|---|---|
| Median per-minute ratio stored / AV in-session | 2.539 (319 minutes) | 1.934 (330) | 3.521 (183) |
| Median Webull / AV in-session | 1.004 | 1.002 | 1.000 |
| Median Webull / stored | 0.398 | 0.506 | 0.263 |
| Total shares 04:00 to 09:29, AV in-session / stored / Webull | 485,801 / 1,153,174 / 492,959 | 819,778 / 1,842,999 / 820,182 | 60,283 / 251,075 / 65,686 |
| Bars under 100 shares, AV in-session / stored / Webull | 86 / 34 / 85 | 30 / 7 / 30 | 103 / 92 / 100 |
| Bars of exactly 1 share | 14 / 2 / 11 | 0 / 0 / 0 | 9 / 2 / 20 |
| Bars of 0 shares | 8 / 0 / 0 | 0 / 0 / 0 | 14 / 2 / 0 |

On 21 of the 22 bars where the in-session read shows 0 shares, Webull shows the same prices on 1 to 3 shares (for example IWM 04:14, 04:53, 05:33 ET). The other is IWM 07:40 ET, a one-price bar at the prior close 277.54 that Webull does not have.

### 5. The two known bad cases

IWM 08:05 ET (13:05Z):

| Source | Open | High | Low | Close | Volume |
|---|---|---|---|---|---|
| AV in-session | 276.4801 | 278.92 | 276.4801 | 278.92 | 1 |
| Stored | 276.4801 | 278.92 | 276.24 | 276.24 | 81 |
| Webull | no bar for this minute | | | | |

Webull omits minutes it has no trade for. Its neighbours: 08:04 ET 276.32 / 276.34 / 276.3168 / 276.3168 on 45 shares, and 08:06 ET 276.26 / 276.3066 / 276.26 / 276.3066 on 481 shares.

QQQ 07:40 ET (12:40Z), prior close 679.89 (the bar #2021 names as getting through the calibrated filter):

| Source | Open | High | Low | Close | Volume |
|---|---|---|---|---|---|
| AV in-session | 679.89 | 679.89 | 669.97 | 679.89 | 1,454 |
| Stored | 670.13 | 679.89 | 669.97 | 679.89 | 3,287 |
| Webull | 670.0072 | 670.16 | 669.97 | 670.0652 | 1,451 |

Prior-close prints, counted two ways. "Open or close": a bar whose open or close is within 5 cents of the prior close while every other price of the bar is more than 0.25 percent away. "Any price": the same with the high or low allowed to be the one near the prior close.

| | SPY | QQQ | IWM |
|---|---|---|---|
| Open or close, AV in-session | 6 (07:00, 07:36, 07:37, 07:38, 07:39, 07:42) | 6 (07:35, 07:37 to 07:41) | 3 (07:35, 07:36, 07:39) |
| Open or close, stored | 2 (07:36, 07:38) | 4 (07:37 to 07:40) | 4 (07:35, 07:36, 07:39, 07:40) |
| Open or close, Webull | 0 | 0 | 0 |
| Any price, AV in-session / stored / Webull | 12 / 12 / 0 | 14 / 14 / 0 | 5 / 6 / 0 |

The revision does not remove the prior-close prints: it moves some of them from the open or close into the high. Webull has none, on any ticker, by either count. Prior-close echoes that are not equal to the cent also appear: SPY 754.3772 and 754.3759 at 07:00 ET, QQQ 679.8507 at 07:00 ET. Webull also has none of the one-bar spikes away from the prior close: QQQ 08:05 ET high 681.022 and 08:35 ET high 680.399 in both Alpha Vantage versions, where Webull's highs are 671.84 and 670.93.

### 6. Premarket high and low per source

Each cell is high / low. "Rules" is `lib.indicators.calculate_premarket_context` on the branch of #2010 (code at 8250bff75; `lib/` is unchanged at the branch head 1d92570d2) with `atr=None`, `stale_print_atr=None`, `spike_atr=None` and the prior close passed, so the print filter does not run and the shipped stale-close, thin-bar and confirmed rules do. "Rules + filter" adds the ATR and thresholds the brief recorded that morning, which is how the brief runs.

| SPY | Raw, to 08:20 | Raw, 04:00 to 09:29 | Rules, to 08:20 | Rules, 04:00 to 09:29 | Rules + filter, to 08:20 |
|---|---|---|---|---|---|
| Brief recorded (old code) | 754.3772 / 747.95 | | | | |
| AV in-session | 754.3772 / 747.95 | 754.3772 / 747.95 | 754.3759 / 747.96 | 754.3759 / 747.96 | 754.3759 / 747.96 |
| Stored | 754.3772 / 747.94 | 754.3772 / 747.94 | 754.37 / 747.96 | 754.37 / 747.96 | 753.01 / 747.96 |
| Webull | 752.4426 / 747.95 | 752.4426 / 747.95 | 752.44 / 747.96 | 752.44 / 747.96 | 752.44 / 747.96 |

| QQQ | Raw, to 08:20 | Raw, 04:00 to 09:29 | Rules, to 08:20 | Rules, 04:00 to 09:29 | Rules + filter, to 08:20 |
|---|---|---|---|---|---|
| Brief recorded (old code) | 681.022 / 668.30 | | | | |
| AV in-session | 681.022 / 668.30 | 681.022 / 668.30 | 679.89 / 668.33 | 680.399 / 668.33 | 679.89 / 668.33 |
| Stored | 681.022 / 668.28 | 681.022 / 668.28 | 679.89 / 668.33 | 680.399 / 668.33 | 679.8507 / 668.33 |
| Webull | 674.9175 / 668.30 | 674.9175 / 668.30 | 674.84 / 668.33 | 674.84 / 668.33 | 674.84 / 668.33 |

| IWM | Raw, to 08:20 | Raw, 04:00 to 09:29 | Rules, to 08:20 | Rules, 04:00 to 09:29 | Rules + filter, to 08:20 |
|---|---|---|---|---|---|
| Brief recorded (old code) | 278.92 / 275.86 | | | | |
| AV in-session | 278.92 / 275.86 | 278.92 / 275.86 | 277.54 / 275.8969 | 277.54 / 275.8969 | 276.86 / 275.8969 |
| Stored | 278.92 / 275.74 | 278.92 / 275.74 | 277.54 / 275.74 | 277.54 / 275.74 | 276.97 / 275.74 |
| Webull | 276.90 / 275.86 | 276.90 / 275.86 | 276.86 / 275.8969 | 276.86 / 275.8969 | 276.86 / 275.8969 |

What each source would have given the 08:20 brief with the shipped rules and the filter on:

- **SPY:** high 754.3759 from the in-session read (under one cent from the prior close 754.37), 753.01 from stored, 752.44 from Webull. Low 747.96 from all three.
- **QQQ:** high 679.89 from the in-session read (the prior close itself, from the 07:40 bar above), 679.8507 from stored (4 cents under the prior close), 674.84 from Webull. Low 668.33 from all three.
- **IWM:** high 276.86 from the in-session read and from Webull, 276.97 from stored; low 275.8969 from the in-session read and Webull, 275.74 from stored. Under the shipped rules the 278.92 print sets no high in any source.
- With the filter off (`atr=None`), the IWM high from both Alpha Vantage versions is 277.54, the prior close, because the 07:35 bar closes and the 07:36 bar opens there.
- At a 09:20 cutoff (the late run of #2020), with the filter off every value equals the "Rules, 04:00 to 09:29" column; with the filter on every value equals the "Rules + filter, to 08:20" column except the QQQ high, which becomes 680.399 from both Alpha Vantage versions. The two separate one-bar spikes at 08:05 and 08:35 pass the two-bar confirmation together.

### 7. When Alpha Vantage revises (one ticker, one day)

A further Alpha Vantage read of QQQ, written 22:05:53Z (newest bar 17:05 ET), equals the stored bars on all four prices and on volume in all 330 premarket minutes. The 14:55 ET read equals the stored bars on all four prices in 61 of 330 and on volume in 0. So for QQQ on 2026-11-16 the revised bars appeared between about 14:55 and 17:05 ET, hours after the 08:20 and 09:20 runs.

### 8. A second day, IWM 2026-11-13 (Webull against stored only)

No in-session read was saved for that day. Stored rows were inserted 2026-11-14 00:39:40Z.

| | Webull | Stored |
|---|---|---|
| Premarket bars | 195 | 279 (84 not in Webull, 0 the other way) |
| All four prices agree to the cent | 51 of 195 | |
| Median per-minute volume Webull / stored | 0.372 (189 minutes) | |
| Total shares | 173,201 | 532,044 |
| Raw high / low, to 08:20 | 279.30 / 278.1087 | 279.31 / 277.86 |
| First bar open (gap against the 11-12 close 278.44) | 278.1087 (-0.119%) | 278.30 (-0.0503%) |

The brief that morning (`fetched_at` 13:20:49Z, read with `db-query-bztfd`) recorded high 279.30, low 277.86 and gap -0.119%. Its open and high match Webull and not stored; its low matches stored and not Webull (Webull's 04:01 ET bar has a low of 278.23). Stored also has 278.44, the prior close, as the low of the 07:35, 07:38 and 08:47 ET bars, where Webull's lows are 278.9146, 278.84 and 279.60.

Separately, `market_data_daily` premarket fields for 2026-11-12 and 2026-11-13 carry `pre_fetched_at` 2026-11-15 06:01:31Z, and the 11-13 row holds `pre_high` 280.65 and `pre_low` 277.86, the stored extremes over the whole premarket, not the values the brief used. Which job rewrote them was not checked.

## Why it matters

- **The 08:20 brief reads in-session bars that are never stored.** Section 1 shows the brief's volume, VWAP and excluded-print counts come from the in-session version. Nothing keeps that version.
- **Every measurement and replay on 2026-11-16 used the revised stored bars:** the prior-close measurement behind #2016 and #2021, the thin-bar count, and the ATR targets experiment. Their numbers describe data the brief does not see. Example from section 3: the in-session read and the stored bars agree on all four prices in 36 of 196 IWM minutes.
- **The thin-bar line was tuned on stored volumes.** `PM_MIN_EXTREME_VOLUME` = 100 (branch of #2010) was set where volumes are 1.9 to 3.5 times the in-session ones. On the in-session read the same line drops a larger share of bars: IWM to 08:20, 75 of 131 in-session bars against 87 of 220 stored; whole premarket, SPY 86 of 327 against 34 of 329 and QQQ 30 of 330 against 7 of 330.
- **A morning cannot be replayed exactly.** The stored bars are not what the brief read, Alpha Vantage returns only the revised version once it has revised (section 7), and the daily premarket fields are rewritten later (section 8). A replay of the brief (CLAUDE.md 3.5 and 3.6) runs on different inputs from the live run.

## What has already been done

- #2010 (open): FEAT-PLAYBOOK-001, the brief says what the data says. Its branch adds the stale-close, thin-bar and confirmed-extreme rules to `calculate_premarket_context`. IWM's 278.92 no longer sets the high in any of the three sources (section 6).
- #2021 (open): the prior-close print rule, spec r2 (supersedes #2016). It widens the stale-close match to a 5 cent tolerance around the prior close (the spec has the full condition). Its measurement was made on stored history.
- #2001 (open): FEAT-DATA-001, flags for prints isolated from their minute (`isolated-print-v1`), computed on the stored bars.
- #2020 (open): FEAT-DEPLOY-001, a late premarket refresh and brief at 09:20 ET. It also reads in-session bars.
- #2023 (open): the handoff note `docs/superpowers/spikes/2026-11-16-session-handoff.md`, which records that the vendor revises the day's bars after the close.

## Potential fixes

**(a) Save the bars each premarket run reads, as read.** The owner expects this is needed. A draft spec is being written on branch `docs/spec-feat-data-001-premarket-reads-as-read` (in progress; not pushed and no PR when this issue was opened).
- Pros: the only option that makes a morning replayable exactly; gives the many-day evidence every item below needs; lets the thin-bar line and the prior-close numbers be re-measured on the data the brief uses; independent of which vendor is chosen.
- Cons: a new table, so a schema change that needs the owner's yes; a retention decision; on its own it does not change what the brief says.
- Cost: small. On 11-16 counts, at most 3 tickers x 330 bars x 2 runs (08:20 and 09:20) = 1,980 rows a session, written in one batch per run, no new job. Whether the refresh job's other tickers should be saved too was not checked.

**(b) Read premarket from a second source (Webull) and compare or combine.**
- Pros: on 11-16 Webull held the same trades and volumes as the in-session read (section 3 and 4) without a single prior-close print or one-bar spike (section 5). Every known bad print of that day (the prior-close prints, IWM's 278.92, the QQQ spikes at 08:05 and 08:35) is absent from Webull, so a print Alpha Vantage has and Webull lacks is worth flagging. With the shipped rules Webull gives the lowest highs of the three sources: SPY 752.44, QQQ 674.84, IWM 276.86 (equal to the in-session read with the filter on).
- Cons: Webull does not give the revised bars either (read at 19:01 ET it still looks like the in-session read), so it does not fix replay. It also leaves out prints that may be real: the IWM 04:00 and 04:01 lows (275.9987 and 275.97 in-session, 276.1612 and 276.6 in Webull), and on 11-13 the 277.86 low the brief used. One day of evidence for three tickers, two for IWM. A second vendor call inside the brief's window. The reads here went through the Claude Webull connector; a Cloud Run job would need Webull's API and credentials (not checked).
- Cost: one call per ticker per run (one call returned the whole premarket here). Limits and price not checked.

**(c) Wait for, or re-fetch, the revised bars before the brief.** Not possible at 08:20 or 09:20: on 11-16 the revised QQQ bars appeared between about 14:55 and 17:05 ET (section 7), and a fetch at 08:20 returns the in-session version. It could only serve an after-close record, which the stored bars already are.

**(d) Rules that are robust to thin in-session data.**
- Pros: works with the data the brief has at 08:20; no storage or vendor change. The shipped rules with the filter already give IWM 276.86 from the in-session read, the same as Webull.
- Cons: they cannot be calibrated on as-read data until (a) exists. On 11-16 in-session bars the shipped rules still give SPY 754.3759 and QQQ 679.89 (prior-close echoes) at 08:20, and QQQ 680.399 at 09:20 (two separate one-bar spikes confirm each other). #2021's 5 cent rule targets the first two; what it gives on the in-session bars was not checked.
- Cost: code only.

**Recommended first: (a).** The data shows the brief's inputs differ from everything we measure (section 1 and 3), and we have one day of direct evidence. (b) and (d) both need many days of as-read bars to be judged, and (c) cannot work in the morning. Saving the bars is the smallest change and the one the other three depend on. After that, (b) as a cross-check is the strongest candidate, because on 11-16 every known bad print was absent from Webull. It is not a replacement on its own evidence: Webull also lacks some prints that may be real.

## What still needs research

- [ ] How many days the revision pattern holds. Direct evidence: 2026-11-16 only. Indirect: IWM 2026-11-13 through the brief row.
- [ ] Whether Webull's premarket matches the stored or the in-session Alpha Vantage bars over several days. 11-16: in-session. 11-13 (IWM): the brief's open and high match Webull, its low matches stored.
- [ ] Whether Webull carries prior-close prints and one-share prints at all. 11-16: no prior-close print on any ticker by either count; one-share bars yes (SPY 11, IWM 20; IWM 21 on 11-13). Which trade types Webull leaves out of its bars: not checked.
- [ ] Webull's limits and cost for M1 history, how far back M1 goes (11-13 worked), and whether a Cloud Run job can call it.
- [ ] Whether Webull's own bars change after the session (both reads here were after the close).
- [ ] How soon after the close Alpha Vantage revises (QQQ on 11-16: between about 14:55 and 17:05 ET), and whether in-session bars for a minute change between the 08:20 read and later in the session.
- [ ] Why the stored IWM version has 90 minutes the in-session read lacks (41,594 shares).
- [ ] Which job rewrote the `market_data_daily` premarket fields for 11-12 and 11-13 at 2026-11-15 06:01:31Z.
- [ ] Re-check the thin-bar line (`PM_MIN_EXTREME_VOLUME`) and the prior-close numbers of #2021 on as-read data once it is saved.
- [ ] What #2021's rule gives on the in-session bars (not run here).

## Data files

These are on the session machine and may not persist. They can be committed to the spike branch `spike/atr-quarter-targets` if wanted.

- AV in-session: `/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/av1116/SPY.csv`, `QQQ.csv`, `IWM.csv` (Eastern stamps, newest first); the QQQ 17:05 ET read is `QQQ_close.csv` in the same folder.
- Stored and brief rows: `/tmp/build-brief/tests/fixtures/premarket_2026_11_16/` (`*_bars.csv` in UTC, `brief_rows.json`, `daily_rows.json`, `sources.json` naming execution `db-query-jc8mj`).
- Webull and the comparison, in `/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/premarket_sources/`:
  - `webull_SPY_20261116.json`, `webull_QQQ_20261116.json`: the tool's JSON as returned (raw copies `*.raw.txt`).
  - `webull_IWM_20261116.csv`: time, open, high, low, close, volume, copied by hand from the tool's JSON because that result came back inline. Checked: every high is at or above its open and close and every low at or below; 186 of 196 bars equal the in-session read on all four prices; the 10 that differ are five prior-close bars (07:35, 07:36, 07:39, 07:43, 08:47 ET), the 04:00 and 04:01 bars named above, and 04:25, 04:26 and 09:29 ET.
  - `webull_IWM_20261113_pre.json` (premarket rows of the 11-13 call), `stored_IWM_20261113.csv` (`db-query-w66d4`, read-only).
  - `compare.py` (run from `/tmp/build-brief` so `lib` imports resolve: `cd /tmp/build-brief && python3 /tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/premarket_sources/compare.py`) and its output `compare_report.json`.

Webull calls, to re-run:

- 2026-11-16, once per ticker (SPY, QQQ, IWM): `get_stock_bars_single` with `category` `US_ETF`, `timespan` `M1`, `real_time_required` `false`, `trading_sessions` `PRE`, `start_time` 1794819600000 (09:00Z), `end_time` 1794839400000 (14:30Z), `count` 400. Times come back in UTC.
- 2026-11-13, IWM: the same with `trading_sessions` `PRE,RTH`, `start_time` 1794560400000, `end_time` 1794603600000, `count` 800, then keep the `PRE` rows (195).

Read-only database reads used: `db-query-jc8mj` (11-16 bars and brief rows), `db-query-w66d4` (11-13 IWM bars), `db-query-bztfd` (11-13 brief rows). No write, no commit.

---
_Generated by [Claude Code](https://claude.ai/code)_
