# MODEL-WEEK-001 — Weekend performance review

**Code:** `gcp/weekend_review.py` ·
**Reads:** `trades` (Cloud SQL) ·
**Job:** `weekend-review` (`0 9 * * 6`, Saturday morning) ·
**Output:** a Discord embed — no table ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-18

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

## The zero-coercions, and why `RESTRUCTURE`

Seven financial fields are coerced to `0` when their source column is absent
(`:46`, `:50`, `:51`, `:60`, `:74`, `:87`, `:88`). For example:

```python
review['total_pnl'] = float(trades['return_pct'].sum()) if 'return_pct' in trades.columns else 0
```

A `trades` frame without `return_pct` publishes **"Total P&L: 0.0%"** to Discord, which is
indistinguishable from a genuinely flat week. That is CLAUDE.md §3.7 forbidden pattern 2 —
`0` ambiguous with missing on a financial field — seven times in one file, on the surface a
person reads to judge the system's performance. It is not a fallback between data sources and
not a display-layer `—`; it is fabricated in the data layer.

`win_rate = len(winners) / total if total > 0 else 0` (`:46`) is the one defensible member of
that list: the `total > 0` guard is division-by-zero protection on a branch that
`if trades.empty` (`:38-41`) has already returned from, so it is unreachable rather than wrong.

The recommendation is `RESTRUCTURE` rather than `RETEST` because there is no hypothesis here to
retest — the arithmetic is correct and the reporting contract is what needs fixing.

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
`RiskConfig.score_thresholds`, owned by [MODEL-IND-001](MODEL-IND-001.md)'s score path, not by
this job.

## Entry points

| Symbol | Role |
|---|---|
| `weekend_review.main` (`:163`) | The scheduled entry point |
| `generate_weekly_review` (`:25`) | Every statistic above |
| `format_discord_message` (`:103`) | The embed |

## Tests

No test file targets this module.

## Known issues

[#1137](https://github.com/TeneikaAskew/stocks/issues/1137) the module docstring claims a
backtest comparison the code does not perform.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
