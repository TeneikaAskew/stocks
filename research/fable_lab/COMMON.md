# Fable lab: shared rules for every experiment conversation (2026-11-11)

Branch: `research/fable-lab-2026-11-11` in TeneikaAskew/stocks. Each conversation has one brief in this folder
(`BRIEF_<lane>.md`). Read this file, your brief, and `prior_work/<lane>/` (a first pass a helper started and
stopped part way; build on it, check it, don't redo what holds).

## Goal (owner's words, Nov 11)
"The goal is to have a reliable system." Find the indicators and levels that show the market is moving,
when it is moving and where it is going. Experiment first: report whether each idea meets its hypothesis
before anything is swapped in. Test every proposed fix separately before reaching one conclusion.
Nothing hard-coded: values are tailored to each ticker (e.g. 0.5 x the ticker's own ATR, not a fixed number).
Validate on all three tickers (SPY, QQQ, IWM) and on an out-of-sample holdout.

## How to work
1. Write `research/fable_lab/<lane>/PLAN.md` first: hypotheses (one line each, falsifiable), data, method,
   variants, success test, holdout, what would change the brief or Insights. Commit and push it, then run it.
2. Plain language in every README: say what each number means in everyday words. "Range" = 90% bootstrap
   confidence interval by day; if the range crosses zero, say the result may be luck.
3. Post data and values so Codex can rerun: exact commands, input files, row counts, a results CSV.
4. Work on your own branch `research/fable-lab-<lane>` cut from `research/fable-lab-2026-11-11`. Write only under
   `research/fable_lab/<lane>/`. Commit and push as you go (merge, never rebase or force-push). No PRs, no
   changes to main, no edits outside your folder.
5. Run the brief's own code from the repo (gcp/premarket_brief.py with BRIEF_AS_OF, lib/strat_levels.py,
   lib/trading_analysis.py, lib/data_loader.py) against the local data below.
6. Production: READ ONLY. You may run SELECT queries against the trading database if this environment gives
   you read access (e.g. the 1-minute tables market_data_intraday_spy / _iwm / _qqq, insight tables). Never
   write, migrate, deploy, execute Cloud Run jobs, or change schedulers. No paid LLM API calls.
7. Commit messages end with: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
   (keep that line exactly, it's the repo's attribution convention).
8. When finished: README.md in your folder with the answer first, then push. Your last message in the
   conversation is a short plain-language summary for the owner: what held up on both windows, what didn't,
   and what you recommend changing.

## Data on this branch
- `data/bars_1min_2025-03_2026-11.tar.xz` -> `bars_raw/{SPY,QQQ,IWM}_1min_YYYY-MM.csv`: Alpha Vantage 1-min,
  as-traded (adjusted=false), extended hours 04:00-20:00 ET, ascending; columns timestamp,open,high,low,close,volume.
- `data/daily_and_60min.tar.xz` -> `ftfc-replay/raw/{T}_daily_adjusted.csv` (daily) and
  `setup-replay/intraday/{T}_60min.csv`.
- Older 1-min history (2017/2018 to 2025-02) is being fetched; when ready it is pushed to this branch as
  `data/bars_1min_older_*.tar.xz` (see `data/STATUS_older_history_fetch.md`). Pull the branch to pick it up.
  Use it for a longer holdout; don't block on it.
- Another trader's QQQ levels and example days: `discord_examples/LEVELS.md` + screenshots.
- Earlier studies: `prior_studies/{direction_intraday,trading_analysis,insights,atr5_vs_atr14}` (read the READMEs).

## Windows
Primary 2026-05-01 to 2026-11-10. Holdout 2025-03-03 to 2026-04-30. Longer holdout when the older data lands.

## Facts so far (verify before relying)
- The brief runs 08:30 ET. Its entry trigger today is only the premarket high (calls) / low (puts). The ladder
  (prior day high/low, ATR bands, weekly, etc.) is used for targets, not triggers.
- Holdout, 448 calls: direction alone ~coin flip. Gap agreeing with the call: 139/208 right; gap against: 70/240.
- Trigger trades won 59% but net -21.28R: avg win +0.43R vs avg loss -0.76R (T1 too close).
- No-new-triggers-after-10:00 was the only earlier rule that held out of sample.
- ATR5 vs ATR14 levels: no gain; levels stay on ATR14.
- R = profit in units of the trade's risk (entry to stop).
