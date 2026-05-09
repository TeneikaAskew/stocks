# Track C R1 Validation Report — 2026-05-09

**Scope:** End-of-day validation of the 6 Track C Round-1 PRs. Confirms that PR-A and PR-B effects are visible in production data, and that the open PRs (C/D/E/F) would behave correctly when merged.

**Method:** SQL pull from production `insight_reports`, `market_data_daily`, `news_sentiment`, and `journal_entries` ([db-query.yml run 25596388648](https://github.com/TeneikaAskew/stocks/actions/runs/25596388648)) plus hermetic local execution of each PR's logic against that data.

**TL;DR:** PR-B verified working in production. PR-A's mechanical fixes (per_role_cost, supporting_signals filter) verified. **PR-A's conviction calibration did NOT move the needle — all 21 reports still show `medium`.** PR-C validator catches 12 orphan numerals across 8/21 reports (38 % rate). PR-D's sentiment fix targets exactly the IWM 5/7 + 5/8 failures. PR-D's backtest walk-back is now mostly defensive — Track A's #323 already plugged the upstream placeholder leak. PR-E wires correctly but `journal_entries` has 0 rows so `similar_past_trades` will be empty until journals begin recording.

---

## Data pulled

| Source | Window | Rows |
|---|---|---|
| `insight_reports` | 2026-05-04 → 2026-05-09 | 21 (multiple runs per ticker per day from cron + replays) |
| `market_data_daily` | 2026-05-01 → 2026-05-09 | 18 (3 tickers × 6 days, all `complete=True`) |
| `news_sentiment` | ≥ 2026-04-25 | 28 ticker-day buckets |
| `journal_entries` | last 90 days | **0 rows total**, 0 with embeddings |

## PR-A (#305 MERGED) — verified

| Audit ID | Effect in production data |
|---|---|
| **G.P3.2** per-role cost | ✅ 5/21 reports have `per_role_cost` populated (the post-merge runs from 5/7-5/8 morning + replays). Pre-merge runs show `per_role_cost=NULL`. Sample: `{'bear': 0.00054, 'bull': 0.00..., 'judge': 0.00...}` etc. |
| **G.P2.14** direction filter on `supporting_signals` | ✅ Post-merge runs show `n_supporting` between 0 and 4 (filtered by trade direction). Pre-merge runs show uniform `n_supporting=5`. |
| **G.P3.3** `insight_reports_history` writes | ✅ Verified earlier (run 25580992531) — 492 rows, 17-day span, all 3 main tickers. |
| **G.P3.1** conviction calibration | ❌ **NOT working** — all 21 reports (pre AND post merge) still show `conviction='medium'`. Prompt-only intervention insufficient. **Recommend follow-up: deterministic post-process derived from confidence_score + analyst-agreement count.** |

## PR-B (#334 MERGED) — verified

Production batch for 5/8 morning shows all 3 SPY/IWM/QQQ at `regime=normal` (was `regime=orb_only` 10/12 in audit window). Post-PR-B runs in the data:

| Ticker | Day | Pre-merge regime | Post-merge regime |
|---|---|---|---|
| SPY | 5/7 | `orb_only` | `normal` |
| SPY | 5/8 | (only post) | `normal` |
| IWM | 5/7 | `orb_only` | `normal` |
| IWM | 5/8 | (only post) | `normal` |
| QQQ | 5/7 | `orb_only` | `normal` |
| QQQ | 5/8 | (only post) | `normal` |

Brief renderer downstream caught the 5-tuple unpack break and was fixed in [#345](https://github.com/TeneikaAskew/stocks/pull/345) within the same window.

Per-ticker calibration job (`calibrate-blue-sky-offset`) configured but **not yet deployed** — operator runs `./deploy.sh calibrate-blue-sky` + `./deploy.sh schedulers`. Until then SPY/IWM seed at 0.15 ATR, QQQ at 0.20 ATR (hand-seeded in schema).

## PR-C (#341 OPEN) — validator hermetically run on actual theses

Ran `_validate_thesis_consistency` on every report's actual prose. **8 of 21 reports (38 %) had at least one orphan price-numeral**, totaling **12 orphan numbers**.

| Ticker | Day | Regime | Orphans | Sample thesis snippet |
|---|---|---|---|---|
| QQQ | 5/7 | orb_only | `[691.09, 704.38, 618.15]` | "...targeting 677.8, 691.09 and 704.38, while being mindful of the 618.15 gamma flip..." |
| IWM | 5/7 | normal | `[275.24, 270.0]` | "...break above 275.24 could trigger... towards the King strike at 270.0..." |
| SPY | 5/4 | orb_only | `[723.33, 730.0]` | "...holds above 712.29, targeting a move towards 723.33 and 730.0..." |
| IWM | 5/4 | orb_only | `[279.75]` | "...A break above the premarket high of 279.75 could trigger..." |
| IWM | 5/8 | normal | `[270.0]` | "...the King strike at 270.0 should act as a magnet..." |
| SPY | 5/7 | orb_only | `[685.03]` | "...watching the gamma flip at 685.03..." |
| SPY | 5/7 | normal | `[685.0]` | "...closely monitoring the 685.0 level as a key support..." |
| SPY | 5/8 | normal | `[708.53]` | "...with a stop loss at 708.53 and targets at 725.0, 735.0, and 745.0..." |

Two distinct failure modes surfaced:
1. **Genuine target hallucination** (QQQ 5/7's 691.09/704.38) — exactly what the audit flagged. PR-C's prompt fix should reduce this.
2. **Missing structured field** (`gamma_flip` 618.15, "King strike" 270.0, "stop loss 708.53") — the LLM has the right number but the planner didn't put it in `key_levels` / `stop`. This is a separate data-completeness bug worth filing as a follow-up.

## PR-D (#343 OPEN) — graceful degradation simulated against historical data

**#1 backtest walk-back:** All 18 OHLCV rows for SPY/IWM/QQQ during 5/1-5/9 are `complete=True` (open/high/low/close/volume + atr_14 all populated). The walk-back path would NOT activate today — Track A's [PR #323 G.P0.3](https://github.com/TeneikaAskew/stocks/pull/323) and [PR #336 W6 freshness](https://github.com/TeneikaAskew/stocks/pull/336) already eliminated the placeholder rows upstream. PR-D's walk-back is now a **defensive guard** preventing regression if the upstream filter ever weakens.

The audit's 9/24 backtest failures pre-dated Track A's freshness fix; the original root cause was the frozen daily fetcher (G.P0.1) producing stale rows. That's now resolved at the source.

**#2 sentiment graceful empty:** News coverage per ticker:

| Ticker | Last news day | News coverage in May |
|---|---|---|
| IWM | **2026-05-04** | 7 unique days, then nothing |
| QQQ | 2026-05-07 | every weekday |
| SPY | 2026-05-07 | every weekday |

Simulated lookback windows on the IWM days that the audit found failing:

| Cron run | Lookback | Articles found | Old behavior | New behavior (PR-D) |
|---|---|---|---|---|
| IWM 5/7 | 5/5-5/7 | **0** | `available=False` → section marked failed | `available=True, article_count=0, note="sparse-coverage"` ✓ |
| IWM 5/8 | 5/6-5/8 | **0** | `available=False` → section marked failed | `available=True, article_count=0, note="sparse-coverage"` ✓ |

**The audit found IWM sentiment failed exactly on these days.** PR-D fixes them.

**#3 `failed_section_reasons` observability:** The new field would now persist the reason on every degraded section. Sample reasons that would have been captured during the audit window:

- `summarizer:backtest`: `"only N daily bars for $TICKER — need >= 60..."` or `"today's row has missing indicator features"`
- `summarizer:sentiment`: `"no news_sentiment rows for IWM in last 48h"` (no longer triggers — see #2 above)
- `analyst-llm:catalyst`: would surface any LLM error class (timeout, rate-limit, parse-error)

Operator queries `report->'failed_section_reasons'` rather than scraping Cloud Logs.

## PR-E (#344 OPEN) — query-text synthesis validated, retrieval starved

Ran `_build_embedding_query_text` on bundles synthesized from the actual report rows:

```
SPY 2026-05-07: "SPY strat candle 2U combo 212_bull_reversal FTFC bullish regime trending_up gap +0.31% vol normal above 200-SMA"
IWM 2026-05-08: "IWM strat candle 2U FTFC mixed regime ranging gap +0.31% vol normal above 200-SMA"
QQQ 2026-05-08: "QQQ strat candle 2U FTFC mixed regime ranging gap +0.31% vol normal above 200-SMA"
```

Query-text synthesis works correctly. **However: `journal_entries` has 0 rows in the last 90 days** (and 0 with embeddings). So even with PR-E wired correctly, `similar_past_trades` will always be empty until trade journaling begins. PR-E is correct infrastructure but starved of data.

**Recommended follow-up:** confirm whether `journal_entries` is being populated by the trade-execution path (separate concern). If not, file an issue against the trade-journaling pipeline.

## PR-F (#346 OPEN) — docs only, nothing to runtime-validate

Confirmed:
- `concurrency.cancel-in-progress: false` correctly set in `.github/workflows/db-query.yml:55`
- All 7 `model_routing` rows still seeded at `vertex:gemini-2.0-flash` (single-model deployment)
- `gcp/schema.sql` and `platform/src/routes/AdminPage.tsx` carry the dormancy explanation in their respective code paths

## Cross-PR sequential-merge — conflict identified + resolved

Simulated `main → C → D → E → F` merge sequence on a `claude/validation-r1-combined` branch. **PR-E conflicts with PR-C+D on `lib/agents/orchestrator.py` and `tests/test_agent_orchestrator.py`** — both PR-C and PR-E added a helper function in the same physical location at the top of the `# Helpers` section. Resolution: keep both helpers stacked. PR-F is docs-only and merges clean against any combination.

Combined branch pushed as `claude/validation-r1-combined` for a clean review surface — **408 tests pass + 34 skipped**.

## Open follow-ups uncovered by validation

| Item | Severity | Description |
|---|---|---|
| Conviction always `medium` | P1 | PR-A's prompt-only fix didn't work. Need deterministic post-process from confidence_score + analyst agreement count. |
| `key_levels` missing real levels mentioned in thesis | P2 | LLM mentions gamma flip / King strikes that aren't in `key_levels` dict. PR-C validator surfaces these as orphans; root cause is incomplete `_derive_key_levels` in orchestrator.py. |
| `journal_entries` empty | P1 | Reflection memory infrastructure is dormant for lack of upstream data. Trade-execution path may not be populating journals. Separate scope (Track D or E). |
| `run_kind='scheduled'` mislabel | P2 | [#313](https://github.com/TeneikaAskew/stocks/issues/313) — still open, valid finding from PR-A's G.P3.3 work. |

## Recommended merge order

Given the conflict in PR-E:

1. Merge **PR-C (#341)** first — touches prompts.py + orchestrator helper section + tests
2. Merge **PR-D (#343)** second — touches summarizers.py + schema.py + orchestrator failed-reason plumbing + tests
3. Merge **PR-E (#344)** third — git will need a 3-way merge on the helper-section conflict (~30s), or use the pre-resolved [`claude/validation-r1-combined`](https://github.com/TeneikaAskew/stocks/tree/claude/validation-r1-combined) branch as reference
4. Merge **PR-F (#346)** any time — docs-only, no conflicts with anything

## Test plan for the operator

After merging all R1 PRs and deploying:

- [ ] Verify `select count(*) from insight_reports where as_of >= NOW() - interval '1 day' and report->'failed_section_reasons' is not null` ≥ 0 (just the field existing)
- [ ] Spot-check next morning report — should have `per_role_cost`, non-uniform `regime`, `failed_section_reasons` if any section degraded
- [ ] Cloud Logging query for `thesis_validator orphan_count` lines — measure baseline orphan rate post-PR-C
- [ ] Cloud Logging query for `reflection_memory ticker=` lines — confirm 1 line per insight run
- [ ] Manually run `./deploy.sh apply-schema && ./deploy.sh build && ./deploy.sh calibrate-blue-sky && ./deploy.sh schedulers` to make the calibration recurring
