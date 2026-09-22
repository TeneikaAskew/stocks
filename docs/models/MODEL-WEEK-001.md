# MODEL-WEEK-001 — Weekend performance review

**Code:** `gcp/weekend_review.py` ·
**Reads:** `trades` (Cloud SQL) ·
**Job:** `weekend-review` (`0 9 * * 6`, Saturday morning) ·
**Output:** a Discord embed — no table ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-22

> Registered 2026-09-18 by the round-10 sweep. It is the weakest member of the model-bearing
> set and it is listed anyway, because it labels realized outcomes with the **same score ladder
> that labels live fires** and posts the result to a person who trades off it.

## What it decides

Nothing forward-looking. It answers *"what did last week's signals actually do"* and attaches
the published strength label to each score bucket:

| Output | Grouping | Where |
|---|---|---|
| Win rate, total P&L, average return | all trades in the trailing 7 days | `:44-51` |
| Win rate | by `direction` (CALL / PUT) | `:53-61` |
| Trades and win rate | by `total_score` (or `signal_strength`), **labelled `weak` / `medium` / `strong` / `perfect`** | `:63-76` |
| Trades, win rate, total return | by ticker | `:78-90` |
| Count and average return | by `exit_reason` | `:92-99` |

The label comes from `get_signal_strength_label(int(score), cfg.risk)` (`:72`) — the same
function `gcp/signal_monitor.py:1343` uses to label a live fire, reading the same
`RiskConfig.score_thresholds` ladder. That is the whole reason this job is model-bearing: the
weekly report is the only place the score ladder's **realized** performance is shown to anyone,
and a person reading "score 6 (`strong`): 40% win rate" acts on it.

## What its own docstring claims and the code does not do

The module docstring (`:3-7`) says the job *"compares actual performance to backtest
expectations"*. **It does not.** There is no reference to a backtest, an expectation, or a
prior anywhere in the file — the word appears once, in that sentence. Every number is a
realized statistic over `trades`; nothing is compared to anything. A reader who took the
docstring at face value would expect a variance report that has never existed.

Recorded against [#1137](https://github.com/TeneikaAskew/stocks/issues/1137), which is the
stale-module-docstring issue.

## What actually happens on a degraded week, measured

**An earlier revision of this document described seven `else 0` coercions
(`:46`, `:50`, `:51`, `:60`, `:74`, `:87`, `:88`) and said a `trades` frame without
`return_pct` would publish "Total P&L: 0.0%" to Discord. That is wrong, and it was wrong on
the day it was written** — asserted from reading the `else 0` branches rather than running
them. Run through `generate_weekly_review` itself, with `TradeLogger` returning each frame:

| `trades` returned | Result |
|---|---|
| empty | clean early return (`:38-41`); no numbers published |
| **nonempty, no `return_pct` column** | **raises `IndexingError`** — the job fails |
| **nonempty, `return_pct` all NULL** | `win_rate = 0.0`, `total_pnl = 0.0`, `avg_return = nan` |
| nonempty, real returns | `win_rate = 0.5`, `total_pnl = 1.0` — correct |

The missing-column case never reaches any `else 0`. Line 45 runs first:

```python
winners = trades[trades.get('return_pct', pd.Series(dtype=float)) > 0]
```

`trades.get(...)` returns an **empty** Series whose index does not match the frame's, so
pandas refuses it as an indexer — `IndexingError: Unalignable boolean Series provided as
indexer`. Every coercion below it is unreachable on that path. The job crashes, which is
loud, and loud is not the complaint.

**The real §3.7 violation is the all-NULL row, and it is two values, not seven.** When every
trade's `return_pct` is NULL:

- `win_rate = len(winners) / total` (`:46`) → `NaN > 0` is False for every row, so `winners`
  is empty and the rate is **`0.0`** — not via a fallback at all, but structurally.
- `total_pnl = trades['return_pct'].sum()` (`:50`) → pandas sums all-NaN to **`0.0`**.
- `avg_return = ...mean()` (`:51`) → `nan`, which is the honest answer and the one the other
  two should give.

So Discord publishes **"Win Rate: 0.0%"** and **"Total P&L: 0.0%"** for a week in which no
trade has a known return — indistinguishable from a week where every trade lost. That is
CLAUDE.md §3.7 forbidden pattern 2 on the surface a person reads to judge the system, and
`avg_return` sitting beside them at `nan` shows the file already knows how to say "unknown".

`RESTRUCTURE` still follows, on firmer ground than before: one input crashes the job and
another publishes fabricated zeros, and neither is a hypothesis that retesting would settle.

## Where the data comes from

`TradeLogger.get_weekly_trades` (`gcp/trade_logger.py:202`) **prefers Cloud SQL** —
`SELECT * FROM trades WHERE trade_date BETWEEN :start AND :end` over the trailing 7 days — and
only falls back to per-day Parquet files when Cloud SQL is not configured. So in Cloud Run this
reads the real `trades` table, not the ephemeral `data/trades` directory that
`cfg.market.trades_dir` names. Its `except` is `_outage_or_raise` (`:218-220`), which the
comment records as deliberate: *"Only an outage reaches the Parquet files; a defect raises."*

## Rationale

**UNKNOWN — not recorded.** The 7-day window, the score-bucket grouping and the choice to
report win rate rather than expectancy carry no derivation. The score→label ladder itself is
`RiskConfig.score_thresholds`, owned by [MODEL-IND-001](../product/07-MODEL-REGISTRY.md#deterministic-and-heuristic-systems)'s
score path, not by
this job.

## Entry points

| Symbol | Role |
|---|---|
| `weekend_review.main` (`:163`) | The scheduled entry point |
| `generate_weekly_review` (`:25`) | Every statistic above |
| `format_discord_message` (`:103`) | The embed |

## Tests

`tests/gcp/test_trade_logger_reads.py` — one of its 15 tests,
`test_weekend_review_reads_live_trades_only`, imports `gcp.weekend_review`, takes
`inspect.getsource(generate_weekly_review)` and asserts that every `get_weekly_trades(...)` call
omits `run_kind`, so the report keeps the live-only default and backfill and replay rows stay
out of the summary. It is a source-inspection guard on data scope, not a behavioural test.

**The statistics themselves are untested.** Nothing exercises win rate, total P&L, average
return, the score-bucket grouping, or the all-NULL week that publishes `0.0` for two of them
(see Known issues). That is the gap, and it is what RESTRUCTURE rests on.

> Until 2026-09-22 this section read "No test file targets this module." — unqualified, and
> false. The test lives in a file whose name does not contain the module's, so a filename search
> misses it and a content search finds it at once. DOC-44.

## Known issues

[#1137](https://github.com/TeneikaAskew/stocks/issues/1137) the module docstring claims a
backtest comparison the code does not perform.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
