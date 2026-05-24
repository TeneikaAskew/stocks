# Track B follow-up — W4: brief_bias NULL on 2026-05-04 to 2026-05-06

**Audit cross-ref:** Track B audit doc (`track-B.md`), Track G G.P1.10
**Plan cross-ref:** `track-B-implementation-plan.md` Step 2.4 / W4
**Outcome:** **Closed as deploy-timing artifact. No production code change required.**

---

## Investigation question

The 2026-05-08 Track B audit found:

| `alert_date` | rows with `brief_bias` populated |
|---|---|
| 2026-05-04 | **0 / 79** |
| 2026-05-05 | **0 / 155** |
| 2026-05-06 | **0 / 162** |
| 2026-05-07 | **386 / 386** |

(Source: `docs/audit/2026-05-08/snapshots/track-B/10-signal-alerts-brief-bias.csv`.)

Two candidate causes were named in the audit:
1. The brief's `premarket_analysis` row was missing or unreadable on
   5/4-5/6 → `get_premarket_bias` returned `UNAVAILABLE` and the
   monitor wrote NULL.
2. The writer code path itself didn't exist on those dates.

This follow-up resolves which one.

---

## Evidence

### 1. Brief rows existed on 5/4-5/6

Track B confirmed in §"Sub-question 1" that 12/12 expected
`premarket_analysis` rows landed for SPY/IWM/QQQ × 5/4-5/7. So the
helper's SQL lookup *would* have returned data on those dates if it
had been called.

### 2. The writer commit landed on 2026-05-07 morning

```
$ git log --oneline --all -S "get_premarket_bias" -- gcp/signal_monitor.py lib/strategies/brief_bias.py
2adb5fe fix(signal-monitor): tz fix + exit-watcher + brief↔live overlay + nightly fetcher (#279)

$ git show -s --format='%ai' 2adb5fe
2026-05-07 08:52:26 -0400
```

Commit `2adb5fe` (PR #279) introduced **all three** of:
- The `lib/strategies/brief_bias.py` module containing
  `get_premarket_bias` and `alignment`.
- The `_resolve_brief_bias` method on `SignalMonitor`
  (`gcp/signal_monitor.py:745-758`).
- The `brief_bias` / `brief_alignment` / `brief_setup_count` columns
  on `signal_alerts` (`gcp/schema.sql`).

The commit is the only ancestor of those identifiers in the entire
git history — verified via `git log -S` for each symbol. Before this
commit, the monitor had no writer for `brief_bias` at all.

### 3. Timeline reconciliation

| Date | Time (ET) | Event |
|---|---|---|
| 2026-05-04 | 09:25 | Signal monitor starts. Writer code path does not exist yet → `brief_bias` NULL on every alert. |
| 2026-05-05 | 09:25 | Same. |
| 2026-05-06 | 09:25 | Same. |
| 2026-05-07 | **08:52** | **PR #279 (`2adb5fe`) merges to `main`.** |
| 2026-05-07 | ~09:00 | Cloud Build rebuilds the `signal-monitor` image with the new code (typical lag <30 min). |
| 2026-05-07 | 09:25 | Signal monitor starts. New revision picks up `_resolve_brief_bias` → `brief_bias` populated on every alert. |

The 5/7 image-rebuild lag concern raised by Track G §2.2 (for the
unrelated `MIN_CONDITIONS_MOMENTUM=5` raise that didn't land until
~13:49 ET) does NOT apply here: the brief_bias commit landed at
08:52 ET, ~37 minutes before the 9:25 ET monitor start, which is
within the typical rebuild window. The empirical evidence (386/386
populated on 5/7) confirms the rebuild made it.

### 4. Conflicting `brief_bias` values on 5/7

A separate finding in the audit (4/6 of 5/7's `(ticker, direction)`
buckets returned `brief_alignment='CONFLICTED'`) is **not** what W4
investigates — that's a downstream effect of the upstream
`signal_status` ↔ `ftfc_direction` contradiction in the brief, which
W1 (G.P1.5) addresses in PR #306. Once W1 lands and the next 4 days
of brief output are stable, the alignment values should resolve to
`aligned` / `opposed` / `neutral` consistently.

---

## Conclusion

The 5/4-5/6 NULL pattern is a **deploy-timing artifact**, not a code
defect. The writer that populates `brief_bias` did not exist before
2026-05-07 08:52 ET; the column exists in `signal_alerts` only because
the same commit added it via `ALTER TABLE`. Pre-existing rows stay
NULL by design (no DEFAULT specified — schema notes this is
intentional so analytics can distinguish "writer didn't run" from
"writer ran with no bias data"; see `gcp/schema.sql` ALTER comment).

**Action**: none. Track B audit item B.5/G.P1.10 is closed as
not-a-bug. Existing tests already lock the resolved-bias persist
path:

- `tests/test_signal_monitor_brief_bias.py::test_persist_row_includes_brief_columns_when_bias_resolved`
  asserts `brief_bias='PUT'`, `brief_alignment='opposed'`, and
  `brief_setup_count=3` flow through `_persist_signal_alert` when
  `_latest_brief_bias` is set.
- `tests/test_signal_monitor_brief_bias.py::test_resolve_brief_bias_caches_per_ticker`
  asserts the cache + lookup contract.
- `tests/test_signal_monitor_brief_bias.py::test_resolve_brief_bias_handles_lookup_exception`
  asserts the `UNAVAILABLE` fallback shape.

If `brief_bias` is observed as NULL on a date AFTER 2026-05-07 with a
brief row present, that *would* be a real bug — the resolution path
includes a bare-`except` swallow at `_resolve_brief_bias` (lines
749-754) that could mask transient DB errors. Track G G.P1.1 already
has a similar concern on the level-break refresh path; if a NULL
recurrence is observed, the same mitigation (log + re-raise once on
first failure to surface the cause) would apply here.

## Cross-references

- Track B audit doc: `docs/audit/2026-05-08/track-B.md` cross-track
  `signal_alerts.brief_bias` / `brief_alignment` finding (the table
  in section "Cross-track signal: brief → signal monitor handshake")
- Track G synthesis: `track-G.md` G.P1.10 ("brief_bias populated
  only on 5/7 — investigate")
- Implementation plan: `track-B-implementation-plan.md` Step 2.4 / W4
- W1 PR #306 (signal_status gate) — addresses the `CONFLICTED`
  alignment that's the residual issue once brief_bias starts being
  populated consistently
