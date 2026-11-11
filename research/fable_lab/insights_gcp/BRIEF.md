# Insights, production side: brief for the GCP+Stocks conversation

Goal: score the part of Insights that the local lane could not replay, the model-decided fields
(direction, conviction, risk flags), using the stored production rows. Read only.

Background: LOCAL_LANE_README.md and LOCAL_LANE_PLAN.md are the local lane's results on the rule side
(persona plans rebuilt from 1-minute bars, 427 sessions x SPY/QQQ/IWM). Short version: no persona shows an
edge on the day rule, swing loses in both windows, risk reviewers judge the model trader's free-form plan
rather than the published one, and the 30 stored model calls did no better than the opposite side.

Rules
- Read only. Run each SELECT in needs_gcp.sql (Q01 to Q15) and export_insights.sql through
  `scripts/db_query_cr.sh` without `--commit`, or psql with `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`.
  No INSERT, UPDATE, DELETE, DDL, deploys, job changes or scheduler changes.
- This repository is public. Do not commit or push any exported rows, report text or CSVs from the database.
  Keep exports inside this conversation's container. You may commit code only, to this branch only.
- No paid model calls (no Gemini, no Claude API). Do not change model routing.
- Experiment first: state each hypothesis before running it, and say whether it held.
- Plain language in the final summary; give counts and 90% day-bootstrap ranges where you compare.

Questions to answer
1. How many stored insight reports exist per month and ticker (Q01, Q07)?
2. Score the model's direction on every stored SPY/QQQ/IWM day against what the market did from the
   09:30 open (not the prior close; the gap is a head start). Compare with the opposite side and with
   "whichever side triggers first". Use 1-minute bars from Cloud SQL (market_data_intraday_spy/_iwm/_qqq).
3. Same-morning flip rate (Q05): how often two runs on one day gave different directions.
4. How risk flags drive conviction and size (Q06, Q07): how often is conviction low, and why.
5. Brief call vs insight direction on the same day (Q08): agreement rate, and who was right from the open.
6. Did production publish levels on the sessions after market holidays (Q11)?
7. Check that the stored persona plans (Q03) match the local rebuild's rules (stops 2/1/0.7 ATR,
   first targets 2R/1R/1R for aggressive/neutral/conservative as the local README states).

Deliver: a final message in this conversation with the answers, the hypotheses and whether each held,
and the commands you ran. The STRAT signals task reads this conversation's transcript.
