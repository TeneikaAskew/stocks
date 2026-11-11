# Insights brief (insight pipeline): outcomes by persona, replay on current code, model question

Research only, written 2026-11-11. Code read at origin/main 300b40df. No pushes, no PRs, no production writes, no paid API calls.

## 1. What the insights brief is

`insight-pipeline-daily` (cron 8:45 ET, weekdays) runs `gcp/insight_pipeline_job.py` for SPY, QQQ, IWM. Each run calls `lib/agents/orchestrator.run_insight_pipeline`:

* 14 LLM calls: 6 analysts (market, strat, options, gamma, catalyst, sentiment), bull, bear, judge, trader, 3 risk personas, portfolio manager.
* The LLM decides only the **direction** (long, short, flat; the portfolio manager's call, forced flat if a risk persona emits a block flag) plus the prose (thesis, bull and bear case, risk flags).
* **Conviction** is computed deterministically (`_calibrate_conviction`).
* **Entries, stops, targets and sizing** are deterministic (`lib/agents/trade_planner.py`), one plan per persona, all on the same trigger and direction:

| Persona | Entry zone (beyond trigger) | Stop | Targets | Size by conviction (high, medium, low) |
|---|---|---|---|---|
| aggressive | 0 to 0.5 ATR | 2.0 ATR from entry mid | 2R, 3.5R, 5R (T3 may stretch to the analog day 5 move) | 1.5, 1.2, 0.8 |
| neutral (the headline plan) | 0 to 0.25 ATR | 1.0 ATR | 1R, 2R, 3R | 1.0, 1.0, 0.7 |
| conservative | 0.1 to 0.4 ATR | 0.7 ATR or the tightest structural level | 1R, 1.75R | 0.7, 0.5, 0.3; x0.6 with a high impact catalyst; 0 when FTFC is not aligned 0.30 or the long is below SMA200 |

* `time_horizon` is almost always `swing`.
* Inputs: Cloud SQL summaries (market_data_daily, strat state and FTFC, options, gamma, catalysts, news sentiment, signal_alerts, journal analogs) and, on current main, the shared level builder `lib.strat_levels.build_session_levels` (#1753).
* Model: `model_routing` table, all 7 roles `vertex:gemini-3.1-flash-lite` in every exported row (also the schema.sql seed). The Vertex adapter defaults to temperature 0.7. Cost about $0.0114 per report, median latency 33 s.
* **No outcome table scores insights.** `premarket-playbook-resolver` scores only the 8:30 brief (hit timestamps on `premarket_analysis`). `scripts/validation/validate_brief_accuracy.py` scores the headline insight plan for one date on demand and stores nothing. Nothing scores the three personas.

## 2. Data

* `insight_reports.csv` (Nov 11 export): 35 rows, all `run_kind=live`, as_of 2026-10-26 to 2026-11-10. 30 distinct ticker days over 10 sessions (Oct 26 to 30, Nov 4 to 6, Nov 9 to 10). **No rows for Nov 2 and Nov 3** (not run or not exported; check with the SQL below). 5 duplicates (two or three runs on the same morning); the latest premarket row per ticker day is the canonical one scored.
* Bars: Alpha Vantage 1 min, `stocks-scorecard/inputs/bars_raw`, through Nov 10. ATR(14): `market_data_daily.csv`, prior session.

## 3. Scoring rule (identical for every persona, ticker, day)

* Session bars 09:30 to 15:59 ET on the report date.
* **Fill**: first bar whose range touches the entry zone. Fill price = bar open if inside the zone, else the zone edge crossed into.
* After the fill (fill bar included), stop and T1 are checked bar by bar; a bar touching both counts as **stop first**. A gap past the stop exits at the bar open.
* **Day rule** (primary): exit at the 15:59 close if neither hit. R = (exit minus fill, signed) / |fill minus stop|.
* **Swing rule**: same fill on day 1, hold up to 5 sessions, exit at last close (truncated at Nov 10).
* **Fill5 rule**: zone stays live 5 sessions (overlapping reports, so trades repeat; a stress view only).
* Size 0 conservative plans are still scored as shadow trades; size weighted R is shown separately.

## 4. Results on the stored reports (old code), canonical 30 ticker days

**Sample caveat: 30 ticker days, 10 sessions, only 4 filled trades per persona on the day rule. Nothing below is statistically significant.**

Direction: 20 short, 10 long. Right on the day (close vs prior close) **11 of 30** (long 5 of 10, short 6 of 20); over 5 sessions 14 of 30. Most shorts came during the Oct 26 to 29 rally.

Fills: **4 of 30** on the day. Entries sat a median 0.88 ATR from the prior close; 13 of 30 were more than 1 ATR away, 5 of 30 more than 3 ATR. On 19 of the 26 no fill days the direction was wrong, so the far trigger kept the user out of bad calls.

| Persona, day rule | Fills | T1 | Stop | Close | Sum R | Avg R per fill | Size weighted R |
|---|---|---|---|---|---|---|---|
| aggressive | 4 | 0 | 0 | 4 | +2.12 | +0.53 | +1.70 |
| neutral | 4 | 2 | 1 | 1 | +2.75 | +0.69 | +1.92 |
| conservative | 4 | 3 | 1 | 0 | +3.63 | +0.91 | +0.56 |

| Persona | Swing rule sum R (fills) | Fill5 rule sum R (fills, T1/stop) |
|---|---|---|
| aggressive | -2.49 (4) | -3.66 (12, 0/4) |
| neutral | +0.57 (4) | -1.06 (12, 5/7) |
| conservative | +3.63 (4) | +3.76 (12, 7/5) |

* By ticker, day rule: IWM 6 fills +2.11R, QQQ 3 fills +3.31R, SPY 3 fills +3.08R. By direction: longs 3 fills -2.19R (no T1), shorts 9 fills +10.69R. Fill5: longs 0 T1 and 8 stops.
* By day (neutral): only Oct 30 (SPY short, T1 +1.29R), Nov 4 (IWM long, stop -1R), Nov 5 (IWM short T1 +1.29R, QQQ short +1.18R at close) traded.
* Conservative's size 0 gate fired on 2 of its 4 fills: SPY Oct 30 (a +1.54R winner skipped) and IWM Nov 4 (a -1R loser skipped). Net zero evidence for the gate.
* Why: aggressive's 2R first target is never reached inside a day and its 2 ATR stop gives back the open profit over a swing; conservative's 1R and 1.75R targets get paid before reversals, which in this choppy, mostly up tape mattered more than the call itself.

Defects seen in the stored reports:
* **Nov 6 IWM and QQQ shorts used the prior year low (171.73, 402.39) as the trigger, 21 and 16 ATR away** (`regime=extended`). Fixed on main by #1746 (cap the walk at the brief's distance window) and #1753 (one level builder; there is no `extended` regime any more).
* **SPY Oct 27: two runs 40 s apart returned short then long.** Same inputs, opposite direction: LLM nondeterminism (flash lite at temperature 0.7). IWM Oct 26 and 27 also show 08:12 and 08:46 runs with different entries.
* Stale PMK_H and PMK_L on the old 8:30 level table (see SCORECARD.md) fed the brief; the insight reports carry `level_basis = null`, so they predate #1753.

## 5. Replay on current code (planner only, LLM direction held fixed)

`tools/replay_day.py` (the scorecard's offline harness: repo fixtures for daily bars, AV 1 min premarket to 08:45, DB reads monkeypatched, nothing written) was run for all 10 sessions on main 300b40df and on PR #1784 head 049ffa3f. Each stored report's direction was then applied to the replayed persona plans and scored with the same rule.

Main 300b40df: all 30 plans `normal`; triggers are now the premarket high or low (PMK_H, PMK_L) or the prior close, much closer to price.

| Persona, LLM direction | Day: fills, T1/stop/close, sum R | Swing: T1/stop/close, sum R |
|---|---|---|
| aggressive | 12, 0/0/12, +3.92 | 1/5/6, +0.06 |
| neutral | 12, 5/1/6, +4.30 (avg +0.36) | 7/4/1, +4.76 |
| conservative | 10, 5/2/3, +5.57 (avg +0.56) | 6/3/1, +4.89 |
| neutral, **opposite** of the LLM | 21, 5/0/16, +6.23 | 15/4/2, +14.31 |

* Neutral by ticker (day): SPY +2.96 (5 fills), QQQ +1.66 (4), IWM -0.32 (3).
* Fading the LLM did as well or better than following it. With 11 of 30 calls right, the direction layer shows no edge in this window; the level and stop/target layer is what made money.
* PR #1784 with run 84421818 params: params are effective from Nov 6, so Oct 26 to Nov 5 return `params_unavailable` (orb_only, no plan). On Nov 6, 9, 10: 9 neutral plans, 1 fill (SPY Nov 9 T1 +2.96R) vs main's 2 fills (+0.88R) on the same days. Too few to judge.
* Replay caveats: the fixture planner uses conviction `medium` and FTFC +-0.8, so sizes and the conservative size 0 gate are not reproduced; the conservative stop gets no swing low or SMA200 input; AV premarket can be cleaner than the live feed; 8:45 cutoff includes the Nov 10 CPI print.
* TF bias relabel (#1732) and the stale PMK fix change the brief's labels and levels; they reach the insight only through `build_session_levels` and the FTFC score, which this replay covers for levels but not for FTFC.

## 6. Full replay with the LLM: what it needs

* `INSIGHT_AS_OF=YYYY-MM-DD` exists (`parse_as_of`, run_kind `replay_refresh`, canonical `run_kind='replay'`), **but the job always writes**: `insight_runs`, an `insight_reports_history` row, and an upsert into `insight_reports`. It is not a dry run.
* Write free path: call `run_insight_pipeline(ticker, as_of=date, snapshot=RouteSnapshot(...))` from Python and save the returned report to a file. It still needs read access to Cloud SQL (`build_context_bundle`) and Vertex credentials. Wrap the connection read only (`/mnt/project-files/stocks-scorecard/tools/ro_guard/sitecustomize.py` pattern, plus psycopg2 for `model_routing.connect`).
* Point in time risk: summarizers filter `snapshot_date < as_of`, but news, options and gamma rows may have been revised or backfilled after the date; check each section before trusting a replay.
* This sandbox has no DB or model credentials: env names checked only; `ANTHROPIC_BASE_URL` is present, no `ANTHROPIC_API_KEY`, no `GOOGLE_APPLICATION_CREDENTIALS`, no `CLOUD_SQL_*`. Run it from T's GCP session.
* Cost (estimate from stored per_role_cost, about 25K input and 4K output tokens per report): flash lite about $0.35 for the 30 ticker days; Opus 5.5 ($4/$20 per MTok) about $6 to $15; Fable 5.2 ($8/$40, thinking always on) about $12 to $30. Multiply by repeats (3 per date recommended).

## 7. Model question (Fable vs Opus)

* Today every role runs `vertex:gemini-3.1-flash-lite`. No Claude model has run this pipeline in the exported data.
* No comparison between models was found in the repo history, docs, or audits (searched for fable, opus, sonnet, model comparison, bake off; "fable" hits are the word "diffable"). MODEL-LLM-* rows in `docs/product/07-MODEL-REGISTRY.md` are all Experimental with "no promotion evidence".
* Blockers to running Claude: `lib/agents/anthropic_adapter.py` registers only when `ANTHROPIC_API_KEY` is set and **is imported nowhere in the job** (only `vertex_adapter` is); `PRICE_TABLE` has no Fable or Opus 5.5 entry (`set_route` refuses unknown models) and prices `claude-opus-4-6` at $15/$75 when the list price is $5/$25.
* A fair comparison: same frozen bundles (save `build_context_bundle` output once per ticker day and feed every model the identical JSON), same dates (all exported ticker days, at least 60 to 100), 3 repeats per model to measure flip rate, deterministic planner unchanged, scored by the rule in section 3 plus direction accuracy, and reported with the flip rate and cost per report. Include a no LLM baseline (TF bias or FTFC sign) and "both sides" plans, since this sample says the levels carry the result.

## 8. Recommended improvements

1. Build an insight outcome resolver: persist per persona fill, stop, T1 to T3 hit times and R, like the playbook resolver does for the brief.
2. Freeze bundles at run time (store the bundle JSON with the report) so any model or code can be replayed on identical inputs.
3. Lower temperature (0 to 0.2) for judge and portfolio manager, and log the flip rate; one same minute flip in 30 days is already visible.
4. Treat direction as unproven: show both sides' plans (the brief already does) until a direction layer beats the fade and a simple baseline over 60+ days.
5. Retire aggressive's 2R first target for a day product, or relabel it as a swing plan; keep conservative's 1R and 1.75R.
6. Fix PRICE_TABLE (Opus 4.6 rate; add the models to be compared) and import the Anthropic adapter only when that experiment is approved.
7. Rerun this scoring after Nov 11 exports grow, using the SQL in `export_insights.sql`.

## 9. Files and rerun commands

* `persona_outcomes.csv`: 105 rows (35 reports x 3 personas), day, swing and fill5 outcomes, `canonical` flag.
* `replay_main_outcomes.csv`, `replay_pr1784_outcomes.csv`: replayed plans, both directions, `matches_llm` flag.
* `summary_*.txt`: the tables above. `replay_json/`: raw replay output. `tools/`: scripts. `export_insights.sql`: read only SQL.

```bash
S=/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad
M=$S/replaywt/strat-params/results/monitor_inputs
R=/mnt/project-files/stocks-scorecard/research/insights
B=/mnt/project-files/stocks-scorecard/inputs/bars_raw
cd $R/tools
python3 -I score_insights.py $M/insight_reports.csv $B $R $M/market_data_daily.csv
python3 -I summarize.py $R/persona_outcomes.csv
# planner replay on a worktree of the code to test (main shown)
git -C /home/claude/stocks worktree add $S/ins_wt origin/main
cd $S/ins_wt
for p in 2026-10-26:2026-10-23 2026-10-27:2026-10-26 2026-10-28:2026-10-27 2026-10-29:2026-10-28 2026-10-30:2026-10-29 \
         2026-11-04:2026-11-03 2026-11-05:2026-11-04 2026-11-06:2026-11-05 2026-11-09:2026-11-06 2026-11-10:2026-11-09; do
  d=${p%%:*}; pr=${p##*:}
  PYTHONPATH=platform:. python3 $R/tools/replay_day.py $d $pr 08:45 $B $S/ins_replay/main/main_$d.json
done
cd $R/tools && python3 -I score_replay.py $S/ins_replay/main main $R/persona_outcomes.csv $B $R/replay_main_outcomes.csv
# PR #1784: same loop in a worktree at 049ffa3f, add the params file as the 6th argument
```
