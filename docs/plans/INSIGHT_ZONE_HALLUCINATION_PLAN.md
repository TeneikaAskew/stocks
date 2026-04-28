# Investigation — `as_of` Timezone Leak in Historical Insight Replays

**Status:** Fixed in PR (this branch). Verification + follow-ups below.
**Author:** session 2026-04-28
**Scope:** `lib/strat.py:compute_strat_status` — used by every historical insight pipeline replay.
**Severity:** High — historical replays read post-`as_of` bars; the LLM saw "the future."

---

## 1. Symptom

Backfilled three single-name tickers and replayed the 09:15 ET insight pipeline at historical `as_of` cutoffs using [`scripts/backfill_and_replay.py`](../../scripts/backfill_and_replay.py). Seven runs total. Five of seven produced entry zones that were obviously impossible — for example:

| Run | Actual H/L | Insight `entry_zone` |
|---|---|---|
| ARM 2026-04-20 | 175.31 / 164.10 | **$237.68-$246.32** |
| ARM 2026-04-22 | 196.66 / 178.47 | **$237.68-$247.04** |
| CARS 2026-03-31 | 8.30 / 7.93 | **$11.18-$11.30** |

The recurring `$237.68` was suspicious — it's a number with no source in the data the LLM should have seen.

---

## 2. Root cause — silent `except` in the `as_of` cutoff filter

[`lib/strat.py:compute_strat_status`](../../lib/strat.py) is the canonical strat snapshot helper. The pre-fix implementation (lines 419-429):

```python
if as_of is not None:
    try:
        cutoff = pd.Timestamp(as_of)
        if df.index.tz is not None and cutoff.tz is None:
            cutoff = cutoff.tz_localize(df.index.tz)
        df = df[df.index <= cutoff]
        if df.empty or len(df) < 2:
            return {"available": False, "reason": f"insufficient bars on or before {as_of}"}
    except Exception:
        pass  # if the index isn't a DatetimeIndex, fall through
```

What goes wrong in our replay path:

1. [`lib.data_loader.load_daily()`](../../lib/data_loader.py) strips timezone from the DataFrame index (lines 477-479) → `df.index.tz is None`.
2. The orchestrator passes `INSIGHT_AS_OF=2026-04-20T13:15:00Z` → parsed to a **tz-aware UTC** datetime → `pd.Timestamp(as_of).tz == UTC`.
3. The conditional `df.index.tz is not None and cutoff.tz is None` is **False** (the actual situation is the opposite case — naive index, tz-aware cutoff). No normalization happens.
4. `df[df.index <= cutoff]` raises `TypeError: Invalid comparison between dtype=datetime64[ns] and Timestamp` because tz-aware vs tz-naive comparison is not supported.
5. The bare `except Exception: pass` **swallows the TypeError silently**.
6. The function continues with the **unfiltered** DataFrame → `df.iloc[-1]` is the most recent bar in the database (today, ~2026-04-27) → `trigger_high = df.iloc[-2]['High']` resolves to a future bar's high.

Concrete reproduction (pre-fix):

```
df.index dtype: datetime64[ns]      df.index tz: None
as_of:  2026-04-20 13:15:00+00:00   tz: UTC
cutoff: 2026-04-20 13:15:00+00:00   tz: UTC
FILTER ERROR: TypeError Invalid comparison between dtype=datetime64[ns] and Timestamp
                                                                       ↑
                                       except: pass  → df returned unfiltered
```

And in the actual ARM 4/20 LLM bundle:

```json
"strat": {
  "date": "2026-04-27",       ← should be 2026-04-20
  "in_force_combo": "22_bear_reversal",
  "ftfc_direction": "bearish", ← should be bullish (still uptrend through 4/20)
  "trigger_high": 237.68,      ← ARM's actual high on 4/24
  "trigger_low": 218.38         ← ARM's actual low on 4/24
}
```

So `$237.68` wasn't LLM hallucination — it was the future-dated `trigger_high` flowing in through a leaky cutoff filter. The LLM was faithfully reporting what the data layer told it.

---

## 3. The fix

```python
if as_of is not None:
    cutoff = pd.Timestamp(as_of)
    if cutoff.tz is not None:
        cutoff = cutoff.tz_convert('UTC').tz_localize(None)
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    df = df[df.index <= cutoff]
    if df.empty or len(df) < 2:
        return {"available": False, "reason": f"insufficient bars on or before {as_of}"}
```

Three changes:

- **Always normalize cutoff to naive UTC.** `data_loader.load_daily` strips timezone, so the index is naive. Aligning cutoff to the same convention avoids the TypeError entirely.
- **Defensively strip the index tz** if it's somehow tz-aware (rare, but possible if a caller passes a non-loader-produced frame).
- **Drop the bare `except Exception: pass`.** Silent exception handling is what hid this bug for as long as it existed. If anything goes wrong now, it surfaces as a real error.

After the fix, the same ARM 4/20 bundle returns:

```
strat.date = "2026-04-20"        (was "2026-04-27")
strat.trigger_high = 168.35       (was 237.68 — that's the 4/17 high)
strat.trigger_low = 162.73        (was 218.38)
strat.ftfc_direction = "bullish"  (was "bearish")
```

---

## 4. Regression coverage

5 new tests in `tests/test_strat.py::TestComputeStratStatusAsOf`:

- `test_tz_aware_datetime_as_of_filters` — the exact case that triggered the leak (ARM 4/20 datetime+UTC).
- `test_naive_date_as_of_filters` — backwards-compat check for callers passing a `date`.
- `test_tz_aware_index_with_naive_cutoff` — defensive case (tz-aware index in, tz-naive cutoff in).
- `test_as_of_before_data_returns_unavailable` — early `as_of` should produce `{available: False}`, not a stale latest-bar fallback.
- `test_as_of_none_uses_latest` — the live-runtime path still uses the latest bar when no cutoff is passed.

All 5 pass. Full strat suite (103 tests) passes.

---

## 5. Why this only mattered after PR #134

The pre-market context PR (#134) was the first work that intentionally exercised historical replays at fine-grained `as_of` precision (passing tz-aware ISO 8601 datetimes via `INSIGHT_AS_OF`). Prior callers passed:

- `as_of=None` → cutoff branch never entered, no leak.
- `as_of=date.today()` → tz-naive `date` → `pd.Timestamp(date)` is also tz-naive → comparison works.

So the bug was latent for as long as `compute_strat_status` has accepted `as_of`. It surfaced when historical replays became a routine workflow.

---

## 6. Other places that could leak the same way

Grep for `df.index <= cutoff` or `df.index <= as_of` across `lib/`:

```
lib/strat.py:425  ← fixed in this PR
```

No other site uses Python pandas filtering for the `as_of` cutoff. Every other summarizer in [`lib/agents/summarizers.py`](../../lib/agents/summarizers.py) filters at the SQL layer (`WHERE date <= :as_of`) where Postgres handles `date` ↔ `timestamptz` casting transparently — those paths are safe. Verified in:

- `summarize_market_context` (line 85): SQL, safe
- `summarize_options_flow` (line 256): SQL, safe
- `summarize_gamma_levels` (line 335): SQL, safe
- `summarize_signals_history` (line 437): SQL, safe
- `summarize_backtest_metrics` (line 537): SQL, safe
- `summarize_catalysts` (lines 832, 853, 869): SQL, safe
- `summarize_news_sentiment` (line 1027): SQL, safe

`compute_strat_status` was the only Python-side cutoff in the LLM bundle path.

---

## 7. Verification (re-run the 7 replays after the fix lands)

The replay script ([`scripts/backfill_and_replay.py`](../../scripts/backfill_and_replay.py)) uses `--skip-backfill` to avoid re-fetching AV data. Once the fix is deployed to Cloud Run:

```bash
python -m scripts.backfill_and_replay --ticker AMD --dates 2026-04-23,2026-04-24 --skip-backfill --skip-discord
python -m scripts.backfill_and_replay --ticker CARS --dates 2026-03-31 --skip-backfill --skip-discord
python -m scripts.backfill_and_replay --ticker ARM --dates 2026-04-20,2026-04-21,2026-04-22,2026-04-23 --skip-backfill --skip-discord
```

Acceptance: `trigger_high` in every produced report should equal the prior-bar high *as of the replay date*, never a future-dated high. Specifically:

| Run | `trigger_high` (expected) |
|---|---|
| AMD 4/23 | $304.25 (4/22 high) |
| AMD 4/24 | $310.22 (4/23 high) |
| CARS 3/31 | $8.07 (3/30 high) |
| ARM 4/20 | $168.35 (4/17 high) |
| ARM 4/21 | $175.31 (4/20 high) |
| ARM 4/22 | $179.40 (4/21 high) |
| ARM 4/23 | $196.66 (4/22 high) |

If the report's `entry_zone` still reads $237 or $11 after the fix, the leak has another source we haven't found — but the regression tests prove the strat path is now correct.

---

## 8. Follow-ups (separate PRs, not blocking this fix)

The original draft of this plan proposed three "PR α/β/γ" changes (deterministic top-level fields, pre-market trigger selection, prompt hygiene). Those are still good ideas — defense in depth — but with the leak fixed they're no longer urgent. Re-evaluate after the post-fix replays:

1. **If post-fix replays are clean:** keep the deterministic-plan refactor as a future hygiene PR but don't rush it.
2. **If post-fix replays still produce off-base entry zones:** the LLM-side issues from the original plan apply — implement Fix A (deterministic plan via `persona_plans[neutral]`) as the next PR.

---

## 9. Lessons

- **Bare `except: pass` is a code smell.** This whole leak survived because exceptions were silently swallowed. Future code in this repo should narrow exception handlers or re-raise after logging.
- **tz-aware vs tz-naive is the most common pandas footgun in this codebase.** `data_loader` strips tz, so any code receiving an `as_of` from outside the repo must normalize before comparing.
- **The replay framework worked.** The user-facing symptom (impossible entry zones) was visible and traceable in five minutes once we dumped the LLM bundle and grepped for the suspicious number. That's an argument for keeping the comparison-table output in the replay script — it surfaced the bug.
