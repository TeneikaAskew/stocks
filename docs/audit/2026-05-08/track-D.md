# Track D — Intraday Alerts & Signal Monitor Evaluation

**Eval window**: 2026-05-04 → 2026-05-07 (4 trading days)
**Tickers**: SPY, IWM, QQQ (`watchlists.signals=true`)
**Verdict**: **Monitor WORKING WITH GAPS** (several P0 gaps; full-session
operation only achieved on May 7)

---

## Executive summary

The signal monitor produced 782 entry alerts in window. Three P0 issues
fundamentally bound what we can conclude about live performance:

1. **Monitor died at 12:00 ET on May 4–6** (a UTC-vs-ET comparison bug in
   the market-hours loop). Last alerts on those days fall at 11:55–11:59 ET
   versus a proper 16:00 ET close. Cloud Run job execution durations
   confirm: jobs ran ~2.5 h per day vs ~6.5 h on May 7. Per the audit-plan
   header, the TZ fix landed 2026-05-07 — corroborated by execution data.
2. **Exit-watcher never persisted on May 4–6**. Every alert in those 3 days
   has `exit_reason=NULL`, `exit_ts=NULL`, `is_open=NULL`. The in-memory
   `active_positions` list is destroyed when the process dies, so exits
   were never even computed. Only May 7 has resolved exits.
3. **`conditions_met` and `strategy_agreement` JSONB are stored as JSON
   string-of-objects, not as native JSONB**. `_persist_signal_alert` calls
   `json.dumps(...)` on a list/dict before insertion; pg8000 sees a Python
   string and writes a JSONB scalar string. Downstream consumers must do
   `(conditions_met #>> '{}')::jsonb` to parse — silently masks bugs and
   breaks `jsonb_array_length`/`@>` predicates that would otherwise be O(1).

Beyond the P0 gaps, the May 7 dataset itself reveals real strategy issues:

- **`max_daily_trades=5` and `daily_loss_limit=-2%` are dead code.** Both
  counters are read at `gcp/signal_monitor.py:437,439` but **never
  incremented or updated anywhere**. IWM/SPY/QQQ each blew through the
  5-fire/day cap by 6–28× in window. (Found in audit-pass § 8.3.)
- **94.8% of alerts are tagged `weak`** (741/782) at 0.25x position
  size; only 3 are `strong`. The system spams Discord with low-conviction
  signals. (Audit-pass § 8.5.)
- **Score quartiles are non-discriminative** (Q1 12.2%, Q2 8.9%, Q3 13.3%,
  Q4 11.1% target-hit rate). High-conviction signals do not win more.
- **`MIN_CONDITIONS_MOMENTUM=5` not enforced in window — image-lag
  artifact.** Commit 0cfab76 raising the floor landed 2026-05-07 12:31
  ET, mid-session; image rebuilt 13:49 UTC = 9:49 ET. The May 7 monitor
  ran on the older image. Verify enforcement holds on May 8+ data.
- **Brief-aligned vs brief-opposed**: opposed CALLs win 20.5% (16/78) vs
  aligned PUTs 17.0% (9/53). Direction inverted from the brief's premise
  on a single-day n.
- **`level_broken` was NEVER populated** in 782 alerts — STRAT level-break
  detection produces empty crossings.
- **timeframe_tag is 81% "60m"** (633/782) — heuristic isn't differentiating.
- **Catalyst proximity = "quiet" for 100% of alerts** — bucket logic added
  no signal-quality information in window.
- **Plaintext API keys** in the Cloud Run job spec (AV/Discord/Benzinga/
  FRED). Only DB_PASS uses Secret Manager. (Audit-pass § 8.12.)
- **trades and signal_alerts in lockstep — but spammy.** 786 trades in
  4 days for 3 tickers; both tables are bloated by the broken caps.
  (Audit-pass § 8.2.)
- **No same-minute / same-second duplicates** — the 60s poll-loop dedup
  is clean. (Audit-pass § 8.4.)
- **ORB snapshots fire correctly** at 9:45 / 10:00 ET every weekday in
  window. (Audit-pass § 8.1.)

---

## 1. Alert volume

### Per-day totals
| Date       | Total | Tickers | First ET | Last ET   | Notes                  |
|------------|-------|---------|----------|-----------|------------------------|
| 2026-05-04 |  79   |    3    | 09:25:23 | 11:55:11  | **Cut off at noon ET** |
| 2026-05-05 | 155   |    3    | 09:25:24 | 11:59:08  | **Cut off at noon ET** |
| 2026-05-06 | 162   |    3    | 09:25:25 | 11:59:18  | **Cut off at noon ET** |
| 2026-05-07 | 386   |    3    | 09:30:13 | 15:57:08  | Full session (TZ fix)  |

May 7 fired ~4.9× the volume of May 4 — partly because of full-day coverage,
partly because IWM CALL alone fired 86 times (vs ≤11 on prior days).

### Per (ticker × date × direction)
Source: `signal_alerts` query in
[appendix A.2](#a2-volume-per-ticker--date--direction).

PUT-heavy bias overall — 438 PUT vs 344 CALL (56% PUT). On 5/5 and 5/6
PUTs ran 2–3× CALLs (e.g. SPY 2026-05-05: 44 PUT vs 15 CALL).

### ORB snapshot capture
ORB columns are populated on 98%+ of alerts (only 1–8 missing per day).
The 9:45 / 10:00 ET ORB-snapshot entrypoint (`run_orb_snapshot`) is
intact; the ORB H/L columns reach the persisted row through the
in-process `self.orb_levels` cache. **OK.**

---

## 2. Continuity — the noon-cutoff incident (P0)

### Smoking gun

`gcloud run jobs executions list --job=signal-monitor`:

| Execution            | Start (UTC)     | Completion (UTC)  | Wall-clock | ET window     |
|----------------------|-----------------|-------------------|------------|---------------|
| signal-monitor-vrl2j | 5/4 13:25       | 5/4 16:00         | 2 h 35 m   | 9:25 → 12:00  |
| signal-monitor-8xhfx | 5/5 13:25       | 5/5 16:00         | 2 h 35 m   | 9:25 → 12:00  |
| signal-monitor-226l4 | 5/6 13:25       | 5/6 16:00         | 2 h 35 m   | 9:25 → 12:00  |
| **signal-monitor-vhzhx** | **5/7 13:25**   | **5/7 20:00**     | **6 h 35 m**   | **9:25 → 16:00** |

Jobs were configured with `timeoutSeconds=28800` (8 h) — the cap was not
the constraint. The market-hours loop in `gcp/signal_monitor.py:147`
exited at 16:00 *UTC*-naive comparison vs `market_close_time=16:00`,
truncating the session at noon ET. Comment at lines 19–22 acknowledges the
bug class; the audit-plan header notes the TZ fix shipped 2026-05-07.

### Implications

1. **No exit data exists for May 4–6** (`exit_reason IS NULL` on all 396
   alerts). `is_open` is NULL too because the column was added later via
   `ALTER TABLE … ADD COLUMN IF NOT EXISTS … BOOLEAN` with no DEFAULT —
   pre-existing rows stay NULL. New rows since the column landed insert
   `True` correctly (May 7 shows 26 still-open and 360 exited, 0 NULL).
2. **All entry-accuracy and exit-accuracy analysis below is May 7 only.**
   May 4–6 are entry-volume-only data points.
3. **End-of-day reconciliation is still missing**: 26 of 386 May 7 alerts
   are `is_open=true` with no `exit_reason` — late-afternoon signals that
   neither hit target nor time-stopped before market close. Schema docs
   anticipate this with the `eod_close` reason but no implementation
   exists. Backlog item.

### Verification queries
- Volume-with-exits matrix (appendix A.1).
- `gcloud run jobs executions list` table above.

---

## 3. Entry accuracy (May 7 only)

### Hit-rate matrix (May 7, exits resolved)

| Ticker | Direction | Resolved n | Target hits | Time stops | RSI exits | Hit %     |
|--------|-----------|------------|-------------|------------|-----------|-----------|
| IWM    | CALL      |  80        | 11          |  69        |  0        | **13.8%** |
| IWM    | PUT       |  18        |  5          |  13        |  0        | **27.8%** |
| QQQ    | CALL      |  78        | 16          |  62        |  0        | **20.5%** |
| QQQ    | PUT       |  53        |  9          |  44        |  0        | **17.0%** |
| SPY    | CALL      |  78        |  0          |  78        |  0        | **0.0%**  |
| SPY    | PUT       |  53        |  0          |  45        |  8        | **0.0%**  |
| **All**| —         | 360        | 41          | 311        |  8        | **11.4%** |

(Excludes 26 still-open positions.)

**SPY produced zero target hits in either direction.** Of 78 SPY CALLs,
**none ever had the +0.30% target reachable within the 30-minute window** —
verified by a bar-level reconstruction (`market_data_intraday` SPY
2026-05-07 max-high in `[alert_ts, alert_ts+time_stop]`):

> SPY CALL May 7: 78 time stops / **0 had target reachable in window**.
> IWM CALL May 7: 11 target hits / 0 of 69 time stops had target reachable.

So the exit-watcher is firing target_hit and time_stop *correctly*. The
problem is upstream: the global `+0.30%` CALL target is too aggressive
relative to SPY's intraday range on a flat day.

### STRAT trigger fidelity

The plan asked: *"was the entry triggered at the candle-trigger level (2U
high / 2D low / failed-2 reclaim) or at an arbitrary mid-bar price?"*

| Ticker | Alerts | Within 0.1% of an ORB level | `level_broken` populated |
|--------|--------|-----------------------------|--------------------------|
| IWM    | 222    | 67 (30%)                    | 0                        |
| QQQ    | 282    | 121 (43%)                   | 0                        |
| SPY    | 278    | 143 (51%)                   | 0                        |

**`level_broken` is NULL on every single alert** — meaning the
`check_level_breaks()` path in `gcp/signal_monitor.py:299` never reported
a crossing in window. Either:
- `self.level_maps[ticker]` is None on every iteration (refresh failing
  silently — `refresh_level_map` does `except Exception` → warning), or
- the crossings happen but the dedup `self.fired_breaks` set never gets
  cleared, or
- the `prev_price <= lev.price < last_price` predicate is mis-shaped.

Either way, **STRAT trigger fidelity is 0%** in window — entries are
fired purely on indicator agreement, never on a STRAT level break being
the entry trigger. ~30–50% of alerts do happen to be near an ORB
H/L/Mid by coincidence.

### Score discrimination

| Quartile | Score range | n  | Wins | Win % | Avg ret % |
|----------|-------------|----|------|-------|-----------|
| Q1       | 1.50–2.25   | 90 | 11   | 12.2% | -0.026    |
| Q2       | 2.25–3.00   | 90 |  8   |  8.9% | -0.060    |
| Q3       | 3.00–3.25   | 90 | 12   | 13.3% | +0.044    |
| Q4       | 3.25–5.50   | 90 | 10   | 11.1% | -0.004    |

**Score quartiles do not discriminate** — Q4 (highest-conviction) wins
slightly less than Q1. The point of the agreement bonus + Strat bonus +
proximity multiplier was to surface high-conviction trades; the data does
not support that the composite score predicts win rate.

---

## 4. Exit-reason accuracy (May 7)

### Exit-return-pct distributions

| Ticker | Dir | Reason       | n  | Avg ret  | Min      | Max      | Std    |
|--------|-----|--------------|----|----------|----------|----------|--------|
| IWM    | C   | target_hit   | 11 | +0.324   | +0.302   | +0.351   | 0.017  |
| IWM    | C   | time_stop    | 69 | -0.167   | -0.702   | +0.257   | 0.221  |
| IWM    | P   | target_hit   |  5 | +0.425   | +0.387   | +0.548   | 0.069  |
| IWM    | P   | time_stop    | 13 | -0.003   | -0.242   | +0.280   | 0.187  |
| QQQ    | C   | target_hit   | 16 | +0.314   | +0.300   | +0.353   | 0.014  |
| QQQ    | C   | time_stop    | 62 | -0.054   | -0.704   | +0.287   | 0.186  |
| QQQ    | P   | target_hit   |  9 | +0.406   | +0.382   | +0.449   | 0.024  |
| QQQ    | P   | time_stop    | 44 | -0.066   | -0.382   | +0.237   | 0.206  |
| SPY    | C   | time_stop    | 78 | -0.031   | -0.388   | +0.212   | 0.132  |
| SPY    | P   | rsi_extreme  |  8 | +0.275   | +0.246   | +0.305   | 0.016  |
| SPY    | P   | time_stop    | 45 | -0.012   | -0.179   | +0.192   | 0.096  |

- target_hit returns cluster tightly at the configured target (CALL ≈ +0.30%,
  PUT ≈ +0.38%) — the target-detection logic is firing precisely.
- time_stop returns are slightly negative on average (0 to -0.17%) but
  with wide distributions: some time_stops left +0.28% on the table
  (target-was-reachable=False checks above confirm those weren't true
  near-misses on the same bar; price retraced before close).
- `rsi_extreme` exits only fired on SPY PUT (8 cases), all profitable
  (+0.25 to +0.31%). The RSI-exit path works.
- **No `eod_close` exits** — that reason isn't implemented.

### STRAT-correct exit?

The STRAT exit rule is "exit when next opposing candle breaks." None of
the three exit paths (target/time/RSI) reference candle structure — they
fire on raw price/time/indicator only. So **0% of exits are
STRAT-correct.** Whether that's the right design is a strategy question,
not a bug, but it is not what the plan describes.

### Are the global ExitConfig defaults right?

`avg_target_pct` per (ticker, direction) for the entire window confirms:

| Ticker | Direction | Avg target % | Avg time-stop min |
|--------|-----------|--------------|-------------------|
| IWM    | CALL      | +0.30        | 30                |
| IWM    | PUT       | -0.38        | 35                |
| QQQ    | CALL      | +0.30        | 30                |
| QQQ    | PUT       | -0.38        | 35                |
| SPY    | CALL      | +0.30        | 30                |
| SPY    | PUT       | -0.38        | 35                |

100% identical across tickers — the global hardcoded `ExitConfig` defaults
(`lib/config.py`) are in use everywhere with zero per-ticker calibration.
SPY's 0% CALL hit-rate suggests the +0.30% target is too aggressive for
SPY in a low-vol session; IWM's 13.8% suggests it's roughly right for IWM.
This is exactly the per-ticker calibration gap Track E owns.

---

## 5. Brief alignment vs hit-rate

### Alignment distribution (full window)

| brief_alignment | brief_bias | n   | %     |
|-----------------|------------|-----|-------|
| NULL            | NULL       | 396 | 50.6% |
| NULL            | CONFLICTED | 248 | 31.7% |
| opposed         | PUT        |  79 | 10.1% |
| aligned         | PUT        |  59 |  7.5% |

**82.3% of alerts had no usable brief alignment.** Most likely cause:
brief lookup failures on May 4–6 (when the monitor ran briefly) plus
CONFLICTED being the dominant brief output. Either way, brief alignment is
information-empty for most signals.

### Win rate by alignment (May 7 only)

| brief_alignment | direction | n   | wins | win % | avg score | avg ret |
|-----------------|-----------|-----|------|-------|-----------|---------|
| aligned         | PUT       |  53 |   9  | 17.0% | 3.16      | +0.014  |
| opposed         | CALL      |  78 |  16  | 20.5% | 3.10      | +0.022  |
| NULL/CONFLICTED | CALL      | 158 |  11  |  7.0% | 2.76      | -0.065  |
| NULL/CONFLICTED | PUT       |  71 |   5  |  7.0% | 3.18      | +0.053  |

**Brief-opposed CALL beats brief-aligned PUT** (20.5% vs 17.0%). On a
single-day n, the brief's premise — that aligned signals will win more —
does not hold. The aligned-vs-opposed comparison is also undermined by the
heavy directional bias of which sample fell where (only PUT got "aligned"
samples; only CALL got "opposed").

---

## 6. Strategy mix

### Stacked-agreement reality

`strategy_agreement` payload shape (per `gcp/schema.sql:744-760`):
```json
{"agree": true, "strategies": ["mean_reversion","momentum"],
 "directions": ["PUT","PUT"], "base_scores": [3.0, 3.0],
 "composite_score": 4.0}
```

After parsing (workaround the JSONB-scalar-string bug), the actual stacked
distribution in window:

| jsonb_typeof(strategy_agreement) | count |
|----------------------------------|-------|
| `string` (real stacked payload)  |   17  |
| `null` (JSONB null, NOT SQL NULL)|  765  |

**Real stacked rate = 17 / 782 = 2.2%**, far below the schema-doc claim
of "~21% historically". On 765 of 782 alerts, only mean-reversion fired
on the bar; momentum returned None (eligible neither call nor put).

### `MIN_CONDITIONS_MOMENTUM=5` not enforced in window — image-lag artifact

The 17 stacked payloads' `base_scores[1]` (momentum's score; sort is
alphabetical so mean_reversion is index 0):

| momentum base_score | count | % of stacked |
|---------------------|-------|--------------|
| 3                   | 14    | 82%          |
| 4                   |  1    |  6%          |
| 5                   |  2    | 12%          |

**14 of 17 stacked alerts have momentum at score=3, below the MIN=5
floor.** Per `lib/strategies/momentum.py:209-212`:
```python
call_eligible = (call_score >= MIN_CONDITIONS and call_core >= MIN_CORE_CONDITIONS)
```
where `MIN_CONDITIONS = MIN_CONDITIONS_MOMENTUM` from
`lib/strategies/config.py:108` (= 5 since 2026-05-06).

**Audit-pass root cause: image lag, not a runtime bypass.** Commit
`0cfab76 feat(phase-0.7.6): require score>=5 + revert 3-of-5 relaxation`
landed **2026-05-07 12:31:29 ET**, mid-session on the eval window's
final day. The signal-monitor image tagged `latest` was rebuilt
2026-05-07 17:49:43 UTC (= 13:49 ET) — after market open. The May 7
9:25-ET execution (`signal-monitor-vhzhx`) pulled an image built at
13:15 UTC (= 9:15 ET), pre-commit-0cfab76. So during the entire eval
window, the deployed code still had `MIN_CONDITIONS_MOMENTUM=3` (or the
original pre-Phase-0.7.6 value), which is consistent with the data.

This is **not a runtime gate-bypass bug**; it is a **deploy-timing
issue**: the threshold raise wasn't on the box during the eval window.
Backlog still tracks it because the May 8+ data must be re-checked to
confirm the new floor enforces. If May 8+ alerts still show momentum
firing at score=3, the runtime-bypass hypothesis is back on.

`MOMENTUM` import from `lib.strategies.__init__:32` resolves to
`MomentumStrategy()` singleton, so there's no alternate code path —
once the new image is deployed, the floor should hold.

### Conditions inventory (window)

After parsing the JSON-string-of-array via `(conditions_met #>> '{}')::jsonb`:

| Condition (top 8)        | Fires |
|--------------------------|-------|
| stoch_rsi_overbought     | 401   |
| above_vwap               | 368   |
| rsi_overbought_zone      | 358   |
| stoch_rsi_oversold       | 321   |
| below_vwap               | 308   |
| rsi_oversold_zone        | 258   |
| consecutive_up           | 248   |
| consecutive_down         | 183   |

**Zero alerts list any momentum-only condition** (`rvol_above_recent`,
`atr_expansion`, `rsi_thrust`). `conditions_met` only stores the
mean-reversion path's conditions (per `_persist_signal_alert` line 673),
so momentum's conditions are not directly visible. To get a true
momentum-vs-MR mix we'd need to additionally persist
`agreement.payload['conditions']` per leg (currently only base_scores are
captured), or add a separate column.

### Average conditions per signal

| Date / ticker | avg conds (MR) |
|---------------|----------------|
| All days      | ~3.0–3.2       |

Mean-reversion signals fire at the absolute floor (`MIN_CONDITIONS=3`).
Combined with the score quartile non-discrimination above, this means
the system is not generating differentiated-quality signals — it's a
pass/fail gate, not a tiered conviction system.

---

## 7. Catalyst proximity

| proximity_bucket | count |
|------------------|-------|
| `quiet`          | 782   |

Every alert in window is tagged `quiet`. Either there genuinely were no
catalysts (FOMC/CPI/NFP/PCE/GDP, earnings, 8-Ks) within window for these
3 ETFs — plausible — or `get_catalyst_context` is returning EMPTY_CONTEXT
on every lookup. Either way, the 0.75x de-weight / 1.10x amplification
mechanism added zero signal-quality information in window.

---

## 8. Audit-pass items (second-pass verification)

This section is the result of a self-audit walking the full Track D
scope to make sure no area was missed by the first pass. Each
sub-section is OK, NEW FINDING, or PARTIAL.

### 8.1 ORB snapshot scheduler (9:45 / 10:00 ET) — OK ✓

Verified by Cloud Scheduler + Cloud Run executions:

| Scheduler job   | Cron        | Args (decoded)                              |
|-----------------|-------------|---------------------------------------------|
| signal-monitor-daily | `25 9 * * 1-5` | (defaults — `--mode=loop`)               |
| orb-15m-alert   | `45 9 * * 1-5` | `--mode=orb-snapshot --window=15m`           |
| orb-30m-alert   | `0 10 * * 1-5` | `--mode=orb-snapshot --window=30m`           |

All three executions present every weekday in window:
- 5/4: vrl2j (9:25 loop) + scjnt (9:45 ORB) + b6jnk (10:00 ORB) ✓
- 5/5: 8xhfx + nvsbp + kfsrj ✓
- 5/6: 226l4 + k8tpw + mk4lf ✓
- 5/7: vhzhx + 2zvwh + f2vwg ✓

ORB-snapshot executions all completed in 20–30s with status=True. Discord
embed dispatch from `run_orb_snapshot()` is fire-and-forget (non-fatal
on send failure) but logs at DEBUG; would need Discord-side audit to
confirm receipt — out of scope for Track D.

### 8.2 trades-table consistency — OK ✓

```sql
SELECT s.alert_date, COUNT(DISTINCT s.id) alerts, COUNT(DISTINCT t.id) trades
FROM signal_alerts s LEFT JOIN trades t
  ON t.ticker=s.ticker AND t.entry_time=s.alert_ts
WHERE s.alert_date BETWEEN '2026-05-04' AND '2026-05-07'
GROUP BY s.alert_date;
```
Every `signal_alerts` row has a matching `trades` row (79/155/162/386).
`TradeLogger().log_trade(...)` at `gcp/signal_monitor.py:726` runs
synchronously in the persist path so the two grow in lockstep. **The
spam-volume issue (§ 8.3) means the `trades` table is also bloated** —
786+ entries in 4 days for 3 tickers — but consistency is intact.

### 8.3 Daily trade caps — NEW P0 FINDING

`lib/config.py:205,207` defines `max_daily_trades=5` and
`daily_loss_limit=-0.02`. `gcp/signal_monitor.py:437,439` reads them:
```python
if self.daily_trades[ticker] >= self.risk.max_daily_trades:
    return
if self.daily_pnl[ticker] <= self.risk.daily_loss_limit:
    return
```

But — `grep -n "daily_trades\|daily_pnl" gcp/signal_monitor.py` shows
**neither counter is ever incremented or updated anywhere in the file**.
Lines 86–87 init them to 0; lines 437/439 read them; nothing writes.

Confirmed empirically: every (ticker × day) in window blew through the
5-fire cap. May 7 worst cases:
- IWM: 111 fires (cap = 5)
- QQQ: 138 fires
- SPY: 137 fires

**Both risk caps are non-functional dead code.** Backlog: P0.

### 8.4 Same-minute / same-second duplicates — OK ✓

```sql
WITH x AS (
  SELECT ticker, direction, date_trunc('minute', alert_ts) as m, COUNT(*) c
  FROM signal_alerts WHERE alert_date BETWEEN '2026-05-04' AND '2026-05-07'
  GROUP BY ticker, direction, m
)
SELECT c, COUNT(*) FROM x GROUP BY c;
```
Result: every minute bucket holds exactly **1** fire per
(ticker, direction). The 60-second poll-loop dedup is clean — no
within-minute storms or repolling bugs. Same-second check also returned
zero rows.

### 8.5 Strength-label distribution — NEW QUALITY FINDING

```sql
SELECT strength_label, COUNT(*), AVG(total_score), AVG(position_size)
FROM signal_alerts WHERE alert_date BETWEEN '2026-05-04' AND '2026-05-07'
GROUP BY strength_label;
```

| Strength | Count | % of total | Avg score | Avg position_size |
|----------|-------|------------|-----------|-------------------|
| weak     | 741   | **94.8%**  | 2.90      | 0.25              |
| medium   |  38   |  4.9%      | 4.68      | 0.50              |
| strong   |   3   |  0.4%      | 5.50      | 0.75              |

**95% of alerts are tagged `weak` and sized at 0.25x position.** The
position-sizing tier is doing its job (smaller size on weaker signals),
but the system is firing weak signals at scale (741 in 4 days) and
sending each as a Discord embed. Combined with the score-quartile
non-discrimination finding (§ 3), the strength label is descriptive but
not predictive: fire rate ≠ win rate by score band.

This is a `Discord noise` problem too: 741 weak embeds buried the 41
real (medium / strong) calls. Backlog: P2.

### 8.6 Per-ticker stacked rate — OK / context

| Ticker | Stacked | Solo | Total | Stacked %  |
|--------|---------|------|-------|------------|
| IWM    |    3    | 219  | 222   | 1.4%       |
| SPY    |    5    | 273  | 278   | 1.8%       |
| QQQ    |    9    | 273  | 282   | 3.2%       |

QQQ has the highest agreement rate (3.2%) — consistent with QQQ being
trendier than the other two. All three are far below the schema's claim
of ~21% historical. After the §6 image-lag finding lands and momentum's
new floor is enforced, the *expected* stacked rate goes DOWN further (a
stricter momentum gate fires less often, so two-strategy agreement is
rarer). The 21% figure is from pre-Phase-0.7.x measurements and is
stale — schema doc should be updated with current expectations.

### 8.7 `daily_pnl` (mirror of 8.3) — confirmed dead

Same finding as 8.3 — `daily_pnl[ticker]` is read at line 439 against
`daily_loss_limit` but is never incremented anywhere in the file. The
-2% session loss-limit guard is non-functional.

### 8.8 `fired_breaks` (level-break dedup) — OK

`self.fired_breaks: set` is initialized at line 104 (per process), keys
are added at line 322 to dedup level crossings within the session. Since
the SignalMonitor instance is constructed fresh per Cloud Run job
execution (one per day), the set is freshly empty each session — no
cross-day leak. **However**, since `level_broken` is NULL on every alert
(§ 3), this dedup never had anything to dedupe — `check_level_breaks`
returned [] every iteration. The dedup logic is correct; the level-break
detection upstream is what's broken.

### 8.9 Discord webhook health — OUT OF SCOPE

The plan's scope did not require verifying that Discord embeds actually
arrived. The persistence-side data shows alerts were composed correctly
(per-row JSON visible in dispatch logs). Discord-side receipt audit
would need access to the Discord channel history; not in scope here.

### 8.10 Polling cadence vs poll_interval — OK

Default `monitor_cfg.poll_interval = 60s` (config). With 3 tickers
processed sequentially, each round takes ~3–5s + 60s sleep. Observed
alert timestamps spread across 60-78s intervals matches expected
cadence; no signs of throttling or stalls.

### 8.11 fire_alert → persist ordering — OK

`gcp/signal_monitor.py:519-639`: `fire_alert` first prints embed, then
posts to Discord, then calls `_persist_signal_alert`. `_persist_signal_alert`
upserts to `signal_alerts`, then logs to `trades`, then appends to
`active_positions`. Order is consistent — if a Discord post fails, the
alert is still persisted (good). If `_persist_signal_alert` fails, the
trade-log and active-positions append are inside individual `try/except`
blocks, so they won't break each other. **No regressions in the persist
ordering.**

### 8.12 Cloud Run job spec — OK

`gcp/signal_monitor` job: 1 CPU, 2 Gi memory, `maxRetries=0`,
`timeoutSeconds=28800` (8 h). Conforms to CLAUDE.md rule §0.5 (no
retries unless transient retries justified; per-job timeout headroom).
Two minor concerns:
- 1 CPU + 2 Gi is conservative; the rolling-window fits comfortably.
- All env vars (AV_API_KEY, DISCORD_WEBHOOK_URL, BENZINGA_API_KEY,
  FRED_API_KEY) are baked **as plaintext values** in the job spec
  rather than `valueFrom: secretKeyRef`. Only `DB_PASS` uses Secret
  Manager. Backlog item — not a Track D blocker, but a security
  concern: leaks via `gcloud run jobs describe` output.

---

## 9. Backlog (prioritized)

### P0 — fix before any further analysis trusts the data

- **`max_daily_trades` and `daily_loss_limit` caps are dead code** (§ 8.3,
  § 8.7). `gcp/signal_monitor.py:86-87` initializes the counters; lines
  437/439 read them; **nothing increments or updates them anywhere**.
  IWM/SPY/QQQ each blew through the 5-fire/day cap by 6–28× in the eval
  window. Fix: increment `self.daily_trades[ticker] += 1` in
  `fire_alert` (once per fire) and update `self.daily_pnl[ticker] += return_pct`
  in `_persist_exit`. Add a regression test that asserts the cap fires
  on the 6th sim signal of a (ticker, day).
- **TZ-fix verification**: confirm 2026-05-07 deploy's market-hours loop
  uses ET-aware comparison. Add a smoke test: `is_market_hours()` at
  16:00 UTC must return True (=12:00 ET, market still open).
- **`is_open` backfill**: existing pre-fix rows have `is_open IS NULL`.
  Either backfill `False` for all alerts older than the column-add
  timestamp, or DEFAULT FALSE on the column and run a one-shot UPDATE.
- **JSONB scalar-string bug** in `_persist_signal_alert`: change
  `'conditions_met': json.dumps(sig['conditions_met'])` →
  `'conditions_met': sig['conditions_met']` (let SQLAlchemy / pg8000
  bind the Python list/dict natively as JSONB). Same for
  `strategy_agreement`. Add a regression test that asserts
  `jsonb_typeof = 'array'` / `'object'` on a sampled row.
- **End-of-day reconciliation**: 26 of 360 May 7 resolved alerts (~7%)
  are stuck `is_open=true`. Implement the `eod_close` exit reason that
  the schema doc anticipates so positions don't leak across sessions.
- **Plaintext API keys in Cloud Run job spec** (§ 8.12). AV_API_KEY,
  DISCORD_WEBHOOK_URL, BENZINGA_API_KEY, FRED_API_KEY are stored as
  literal env values; only DB_PASS uses Secret Manager `secretKeyRef`.
  Anyone with `roles/run.viewer` can `gcloud run jobs describe
  signal-monitor` and read them. Move to secretKeyRef.

### P1 — strategy-correctness fixes

- **`MIN_CONDITIONS_MOMENTUM=5` deploy verification**: per § 6 audit-pass,
  the score>=5 raise (commit 0cfab76) committed mid-session 5/7, image
  rebuilt 13:49 UTC = 9:49 ET. Re-pull May 8+ stacked-payload data and
  confirm `momentum base_score >= 5` on every stacked alert. If May 8+
  still shows momentum=3 fires, the runtime-bypass hypothesis is back
  on; otherwise close the finding.
- **`level_broken` always-NULL**: trace why `check_level_breaks()`
  produces no crossings. Most likely `self.level_maps[ticker]` is None
  because `refresh_level_map()` is silently failing — convert the
  `except Exception` at `gcp/signal_monitor.py:295` to log error +
  re-raise once so we see what's actually wrong.
- **SPY +0.30% CALL target is wrong**: 0/78 SPY CALL targets reachable
  in 30 min. Either widen SPY's target to ~+0.20–0.25% or shorten the
  time stop to a window where +0.30% is plausible. Track E owns the
  per-ticker calibration; this is a concrete data point for it.

### P2 — strategy-quality questions

- **94.8% of alerts are "weak"** (§ 8.5). The system fires 741 weak
  signals in 4 days at 0.25x position size — that's not a tradeable
  cadence, that's noise. Combined with the score-quartile
  non-discrimination (Q4 11.1% vs Q1 12.2% wins), the strength label
  is descriptive but not predictive. Either raise the fire floor (so
  `weak` doesn't fire at all) or stop emitting weak signals to Discord
  (keep persisted for analysis).
- **Score quartiles don't discriminate** (Q4 11.1% vs Q1 12.2% wins) —
  the composite-score system isn't doing its job. Track C's factor
  analysis is the right place to fix this; backstop is to add a
  `signal_metrics` rollup that flags per-day quartile-vs-hit-rate
  rank-correlation and pages when |ρ| < 0.1 for 5 sessions.
- **Brief alignment is information-empty for 82% of alerts** (NULL +
  CONFLICTED). Track B should investigate why brief bias resolves
  to CONFLICTED so often.
- **timeframe_tag is 81% "60m"** — heuristic in `lib/strategies/timeframe.py`
  not differentiating. Walk-forward calibration owed to that module per
  the docstring.
- **Catalyst proximity = 100% quiet in window** — either expected for a
  catalyst-free week, or a lookup failure. Add a smoke test on the
  `get_catalyst_context` cache to confirm it can return non-`quiet` when
  events are seeded.
- **Stacked-rate schema doc is stale** (§ 8.6). Schema claims ~21%
  historically; current data shows 1.4–3.2% per ticker. Update the
  schema-doc rationale comment at `gcp/schema.sql:744-760` to reflect
  current expectations after Phase 0.7.x's tightened momentum gate.

### P3 — observability

- **Persist momentum's `conditions_met` separately** when it fires (in
  `strategy_agreement` payload or a new column), so we can do
  factor-discrimination analysis on the momentum strategy without
  re-running the bars.
- **Persist a real `is_open=False` default** on the column so analytics
  filtering on `is_open IS NOT NULL` doesn't have to defensively
  COALESCE.

---

## Appendix A — verification queries

### A.1 Continuity / exit persistence

```sql
SELECT alert_date,
       MIN(alert_ts AT TIME ZONE 'America/New_York')::time AS first_et,
       MAX(alert_ts AT TIME ZONE 'America/New_York')::time AS last_et,
       COUNT(*) FILTER (WHERE exit_ts IS NOT NULL) AS exits_persisted,
       COUNT(*) FILTER (WHERE is_open IS TRUE)     AS still_open,
       COUNT(*) FILTER (WHERE is_open IS NULL)     AS null_open,
       COUNT(*) AS total
FROM signal_alerts
WHERE alert_date BETWEEN '2026-05-04' AND '2026-05-07'
GROUP BY alert_date ORDER BY alert_date;
```
Result:
| date       | first_et | last_et  | exits | open | null_open | total |
|------------|----------|----------|-------|------|-----------|-------|
| 2026-05-04 | 09:25    | 11:55    |   0   |  0   | 79        |  79   |
| 2026-05-05 | 09:25    | 11:59    |   0   |  0   | 155       | 155   |
| 2026-05-06 | 09:25    | 11:59    |   0   |  0   | 162       | 162   |
| 2026-05-07 | 09:30    | 15:57    | 360   | 26   |   0       | 386   |

### A.2 Volume per ticker × date × direction
See `signal_alerts` query in run 25557334664 (artifact) — 24-row matrix.

### A.3 Bar-level reachability
```sql
WITH s AS (
  SELECT alert_ts, target_price, time_stop_minutes,
         alert_ts + (time_stop_minutes || ' minutes')::interval AS deadline
  FROM signal_alerts
  WHERE alert_date='2026-05-07' AND ticker='SPY' AND direction='CALL'
    AND exit_reason IS NOT NULL
), b AS (
  SELECT ts, high FROM market_data_intraday
  WHERE ticker='SPY' AND DATE(ts AT TIME ZONE 'America/New_York')='2026-05-07'
)
SELECT s.exit_reason,
       COUNT(*) AS n,
       SUM(CASE WHEN s.target_price <= mw.max_high THEN 1 ELSE 0 END) AS reachable
FROM s
LEFT JOIN LATERAL (SELECT MAX(high) AS max_high FROM b
                   WHERE b.ts BETWEEN s.alert_ts AND s.deadline) mw ON TRUE
GROUP BY s.exit_reason;
```
Result: `time_stop n=78 reachable=0` (SPY CALL May 7 — target was *never*
reachable on any time-stopped trade).

### A.4 Strategy-agreement payload parse
```sql
SELECT ticker, direction,
       (strategy_agreement #>> '{}')::jsonb AS ag
FROM signal_alerts
WHERE alert_date BETWEEN '2026-05-04' AND '2026-05-07'
  AND jsonb_typeof(strategy_agreement) = 'string'
ORDER BY alert_ts;
```
17 rows; momentum base_score (= `ag->'base_scores'->>1`) = 3 in 14 of 17.

---

## Appendix B — files read

- `gcp/signal_monitor.py` (1003 lines, full)
- `gcp/schema.sql` lines 702–860, 1750–1850 (signal_alerts + ALTERs)
- `gcp/database.py` (interface only)
- `lib/strategies/agreement.py` (full)
- `lib/strategies/momentum.py` (full)
- `lib/strategies/config.py` (full)

## Appendix C — verification environment notes

- DB access from the sandbox is via the `db-query.yml` GH Actions
  workflow (sandbox firewall blocks all outbound TCP except 443; Cloud
  SQL needs 3307/5432, both empirically confirmed blocked). The plan's
  claim that "Direct Cloud SQL access is available in this sandbox" is
  incorrect; CLAUDE.md's "Database access" section is authoritative.
- Cloud Run job execution data was pulled directly via `gcloud run jobs
  executions list --job=signal-monitor --region=us-east1`.
