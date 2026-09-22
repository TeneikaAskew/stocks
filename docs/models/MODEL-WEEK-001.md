# MODEL-WEEK-001 — Weekend performance review

**Code:** `gcp/weekend_review.py` ·
**Reads:** `trades` (Cloud SQL) ·
**Job:** `weekend-review` (`0 9 * * 6`, Saturday morning) ·
**Output:** a Discord embed — no table ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-22 (re-verified after the §3.7 fix)

> Registered 2026-09-18 by the round-10 sweep. It is the weakest member of the model-bearing
> set and it is listed anyway, because it labels realized outcomes with the **same score ladder
> that labels live fires** and posts the result to a person who trades off it.

## What it decides

Nothing forward-looking. It answers *"what did last week's signals actually do"* and attaches
the published strength label to each group of trades:

| Output | Grouping | Where |
|---|---|---|
| Win rate, total P&L, average return | all trades in the trailing 7 days | `:117-127` |
| Win rate | by `direction` (CALL / PUT) | `:129-135` |
| Label, score span, trades, win rate, max score | by **strength label** — `weak` / `medium` / `strong` / `perfect` — computed from the unrounded score | `:137-188` |
| Trades, win rate, total return | by ticker | `:190-201` |
| Count and average return | by `exit_reason` | `:203-209` |

**The strength grouping key is the label, not the score.** Until 2026-09-22 it was the raw
float, and each row was rendered with `int(score)`, so two rungs of the same label appeared as
two rows both printed `score: 4` with different win rates. The row now carries six keys —
`label`, `score_min`, `score_max`, `trades`, `win_rate`, `max_score` — and the observed span is
shown because a rung genuinely covers a range of fractional scores.

The label comes from `get_signal_strength_label`, the same function
`gcp/signal_monitor.py:1343` uses to label a live fire, reading the same
`RiskConfig.score_thresholds` ladder. That is the whole reason this job is model-bearing: the
weekly report is the only place the score ladder's **realized** performance is shown to anyone,
and a person reading "`strong` (5.1-5.95/8): 40% win rate" acts on it.

### It passed a different argument to that function until 2026-09-22

The call was `get_signal_strength_label(**int(score)**, cfg.risk)`, while the live monitor
passes the unrounded `total_score`. **The function and the ladder were the same; the argument
was not** — and an earlier revision of this section quoted the `int(score)` call and asserted
equivalence with the live path in the same sentence.

Fractional scores are the normal case, not an edge one: four of six catalyst-proximity
multipliers are non-integral (`lib/config.py:370-376`) and `strat_bonus` moves in quarter
points (`lib/strat.py:29-54`). Because `int()` truncates toward zero, **every mismatch was a
downgrade**:

| Raw | Bucket | Mult | Product | Live | Reported |
|---|---|---|---|---|---|
| 4 | `next_day` | 1.10 | 4.4 | medium | **weak** |
| 5 | `post` | 0.85 | 4.25 | medium | **weak** |
| 5 | `imminent` | 0.95 | 4.75 | medium | **weak** |
| 5 | `next_day` | 1.10 | 5.5 | strong | **medium** |
| 6 | `during` | 0.75 | 4.5 | medium | **weak** |
| 6 | `post` | 0.85 | 5.1 | strong | **medium** |
| 6 | `imminent` | 0.95 | 5.7 | strong | **medium** |
| 6 | `next_day` | 1.10 | 6.6 | perfect | **strong** |
| 7 | `during` | 0.75 | 5.25 | strong | **medium** |
| 7 | `post` | 0.85 | 5.95 | strong | **medium** |
| 7 | `imminent` | 0.95 | 6.65 | perfect | **strong** |
| 8 | `post` | 0.85 | 6.8 | perfect | **strong** |

Only `pre` and `quiet` (both `1.00`) were ever safe. So each rung's win rate was contaminated
by trades from the rung above it — **in the one report used to judge the ladder**.

Two further defects in the same block, both fixed:

- It grouped by the raw float and rendered `int(score)`, so 4.25 and 4.5 became two rows both
  printed `score: 4` with different win rates. One rung is now one row, showing the observed
  score span.
- A `NaN` score fell through the ladder to its else-branch and was labelled **`perfect`** —
  every `<=` against `NaN` is False. Scoreless trades are now counted and reported separately
  (CLAUDE.md Rule 3.7).

Fixed in `gcp/weekend_review.py`, covered by
`tests/gcp/test_weekend_review_score_labels.py` (see **Tests** below), mutation-tested
against the pre-fix behaviour. **This is a behaviour change**: weekly reports before this date used the
truncated labels, so their per-rung win rates are not comparable with later ones. DOC-56.

## What its own docstring claimed and the code did not do — fixed 2026-09-22

The module docstring said the job *"compares actual performance to backtest expectations"*.
**It did not, and never had.** There is no reference to a backtest, an expectation or a prior
anywhere in the file; every number is a realized statistic over `trades`. A reader who took the
docstring at face value would expect a variance report that has never existed.

Rewritten (`:1-14`) to describe what the module does, naming DOC-36 and
[#1137](https://github.com/TeneikaAskew/stocks/issues/1137) so the correction is greppable from
the code. It was previously recorded here as *"not fixed here: the code change is the
docstring's"*, with a note that [#1139](https://github.com/TeneikaAskew/stocks/pull/1139) fixes
three docstrings and not this one — so the issue could have closed with DOC-36 standing. It no
longer can.

## What actually happens on a degraded week, measured — and fixed 2026-09-22

This section has now been wrong twice, each time by describing code instead of running it, and
each time about the same block. Both corrections are kept because the second is the more
instructive.

> **First error.** An earlier revision described seven `else 0` coercions and said a `trades`
> frame without `return_pct` would publish "Total P&L: 0.0%". Wrong: the missing-column path
> raises before reaching any of them.
>
> **Second error — mine, and it survived the correction.** The replacement text said *"the real
> §3.7 violation is the all-NULL row, and it is two values, not seven"*, listing `win_rate` and
> `total_pnl` only. It was **understated then and understated further afterwards**: the
> per-direction and per-ticker rates had the same shape and were never counted, and the DOC-56
> fix added a sixth by giving every strength rung its own `(s > 0).mean()`. Counting from the
> two sites the previous sentence happened to name is the same failure as reading the first
> matching line — CLAUDE.md §3.11.1.

Measured by running frames through `generate_weekly_review` and `format_discord_message`, not
by reading them. **Before** the 2026-09-22 fix, a 3-row all-NULL week rendered:

```
[Overall] Trades: 3 | Win Rate: 0.0%
          Total P/L: 0.000% | Avg Return: nan%
[CALL]    Trades: 2 | Win Rate: 0.0%
[PUT]     Trades: 1 | Win Rate: 0.0%
[By Signal Strength] medium (4.4/8): 1 trades, 0.0% win rate
                     strong (5.1/8): 1 trades, 0.0% win rate
                    perfect (6.6/8): 1 trades, 0.0% win rate
```

Seven published zeros from **five code sites**, one of which the DOC-56 fix had introduced:

| Site | Why it was `0.0` | Origin |
|---|---|---|
| overall `win_rate` | `NaN > 0` is False for every row, so `winners` was empty — not a fallback at all, structural | pre-existing |
| overall `total_pnl` | pandas sums an all-NaN Series to `0.0` (`min_count=0`) | pre-existing |
| per-direction `win_rate` | `(s > 0).mean()` on all-NaN is `0.0` | pre-existing |
| per-rung `win_rate` | same, once grouping moved to the label | **DOC-56, 2026-09-22** |
| per-ticker `win_rate` / `total_return` | same, and the `min_count` default again | pre-existing |

`avg_return` and `by_exit_reason[].avg_return` were the only honest pair, because `.mean()`
propagates `NaN` where `.sum()` and `(s > 0).mean()` do not — the file already knew how to say
"unknown" on two of its eight numbers.

**Fixed.** All five now carry `NaN` end to end (`_win_rate` `:34`, `_total_return` `:50`) and
the embed renders unknown as an em-dash (`_pct` `:81`) — §3.7's one allowed exception is
display-layer rendering of a null. The same frame now renders:

```
[Overall] Trades: 3 | Win Rate: —
          Total P/L: — | Avg Return: —
[CALL]    Trades: 2 | Win Rate: —
[PUT]     Trades: 1 | Win Rate: —
[By Signal Strength] medium (4.4/8): 1 trades, — win rate
                     strong (5.1/8): 1 trades, — win rate
                    perfect (6.6/8): 1 trades, — win rate
```

Two things the fix deliberately does not do. A **measured** 0% — every trade lost, returns
known — still reads `0.0%`; that is the distinction the whole change rests on, and it has its
own test. And the embed's colour, which took the red "losing week" branch on `NaN > 0`, is now
the same grey the no-trades embed uses.

The missing-column case still **raises**, because a `trades` frame with rows and no
`return_pct` is a defect in the writer, not a degraded week. It now raises a `ValueError`
naming the column and the columns present (`_known_returns` `:61`), where before it surfaced as
`IndexingError: Unalignable boolean Series provided as indexer` out of pandas. Loud was never
the complaint; unintelligible was.

| `trades` returned | Before | After |
|---|---|---|
| empty | clean early return; no numbers published | unchanged |
| nonempty, no `return_pct` | `IndexingError` from pandas | `ValueError` naming the column |
| nonempty, `return_pct` all NULL | seven fabricated `0.0`s published | every rate unknown, embed grey |
| nonempty, some NULL | known rows silently diluted | known rows computed, unknown rungs dashed |
| nonempty, real returns | correct | unchanged |

`RESTRUCTURE` still follows, on narrower grounds: the fabricated zeros are gone and the crash is
now intelligible, but nothing compares any of these numbers to an expectation, the 7-day window
and the choice of win rate over expectancy carry no derivation, and **two of the five
groupings never reach the reader**: `format_discord_message` emits exactly three fields —
`Overall`, the per-direction pair, and `By Signal Strength` (`gcp/weekend_review.py:214-292`) — so `by_ticker` and
`by_exit_reason` are computed on every run and appear only in the job's stdout.

## Where the data comes from

`TradeLogger.get_weekly_trades` (`gcp/trade_logger.py:202`) **prefers Cloud SQL** —
`SELECT * FROM trades WHERE trade_date BETWEEN :start AND :end` over the trailing 7 days — and
only falls back to per-day Parquet files when Cloud SQL is not configured. So in Cloud Run this
reads the real `trades` table, not the ephemeral `data/trades` directory that
`cfg.market.trades_dir` names. Its `except` is `_outage_or_raise` (`:218-220`), which the
comment records as deliberate: *"Only an outage reaches the Parquet files; a defect raises."*

## Rationale

**UNKNOWN — not recorded.** The 7-day window, the strength-label grouping and the choice to
report win rate rather than expectancy carry no derivation. The score→label ladder itself is
`RiskConfig.score_thresholds`, owned by [MODEL-IND-001](../product/07-MODEL-REGISTRY.md#deterministic-and-heuristic-systems)'s
score path, not by
this job.

## Entry points

| Symbol | Role |
|---|---|
| `weekend_review.main` (`:294`) | The scheduled entry point |
| `generate_weekly_review` (`:99`) | Every statistic above |
| `format_discord_message` (`:214`) | The embed — three fields, not five |
| `_known_returns` (`:61`) | The single `return_pct` view; raises on a missing column |
| `_win_rate` (`:34`) · `_total_return` (`:50`) | Unknown-preserving aggregates |
| `_pct` (`:81`) | The only place a `NaN` becomes a character |

> These pointers were `:163` / `:25` / `:103` until 2026-09-22. The DOC-56 fix inserted 38 lines
> above them and none was updated, so two of the three named a line that no longer held the
> symbol. They are now gated by `test_symbol_anchored_line_pointers_resolve` in
> `tests/meta/test_model_registry_consistency.py`, which resolves every `` `sym` (`:N`) ``
> pointer in `docs/models/` against the file and fails on drift. DOC-59.

## Tests

`tests/gcp/test_trade_logger_reads.py` — one of its 15 tests,
`test_weekend_review_reads_live_trades_only`, imports `gcp.weekend_review`, takes
`inspect.getsource(generate_weekly_review)` and asserts that every `get_weekly_trades(...)` call
omits `run_kind`, so the report keeps the live-only default and backfill and replay rows stay
out of the summary. It is a source-inspection guard on data scope, not a behavioural test.

`tests/gcp/test_weekend_review_score_labels.py` — **23 cases** (`pytest --collect-only`),
covering the two behaviour changes this document records:

- the label a fractional score receives, parameterised over the eight raw-score × multiplier
  products that `int()` truncation moved a rung down;
- one rung is one row, with its observed span;
- a `NaN` score is counted, not labelled `perfect`;
- the all-NULL week — each of the five sites separately, the rendered embed, the embed colour,
  and the case that matters most, **a measured 0% still reading `0.0%`**;
- the missing-`return_pct` `ValueError`, and that its guard sits *below* the empty-frame return
  so a quiet week is not turned into a job failure.

Every one of those is mutation-tested: eight mutations of `gcp/weekend_review.py`, each
restoring one pre-fix behaviour, and each turns the suite red.

**What is still untested, and it is what RESTRUCTURE rests on.** Overall win rate, total P&L
and average return are *executed* by the fixtures above but never asserted on a normal week;
`by_ticker` and `by_exit_reason` have no test at all, which is the less surprising for their
never reaching the embed; and nothing checks the 7-day window boundary.

> Until 2026-09-22 this section read "No test file targets this module." — unqualified, and
> false. The test lives in a file whose name does not contain the module's, so a filename search
> misses it and a content search finds it at once. DOC-44.
>
> It then read **"The statistics themselves are untested … or the all-NULL week"** — written in
> the same commit that added the suite covering the strength grouping, and left standing while
> the suite grew to cover the all-NULL week too. DOC-58. A coverage claim has to be re-read when
> the coverage changes, which is exactly what DOC-44's gate was built for and exactly what it
> cannot see: `test_no_test_claims_are_true` keys on the word "no test", and this sentence does
> not contain it.

## Known issues

[#1137](https://github.com/TeneikaAskew/stocks/issues/1137) — the stale-module-docstring class.
It stays open for the other modules it covers; **this module's instance (DOC-36) is fixed**, at
`gcp/weekend_review.py:1-14`. The §3.7 fabricated zeros (DOC-62) and the coverage claim
(DOC-58) were fixed in this PR rather than filed, so neither has an issue.

What is *not* closed is the `RESTRUCTURE` recommendation itself: nothing compares any figure to
an expectation, two of the five groupings never reach the embed, and the untested surface named
under **Tests** is real. Those are design gaps, not defects with a reproduction.

Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
