# MODEL-BRIEF-001 — Brief bias / movement statement

**Code:** `lib/strategies/brief_bias.py` (266 lines), `lib/movement_statement.py` (1004 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

Two related surfaces:

**Brief bias** reads the morning `premarket_analysis` row for `(ticker, date)` and
derives a structured bias the live signal monitor displays **alongside** its own
intraday signal. The source is emphatic that this is **visibility-only**: *"Bias is NOT
used to gate or modify scores yet — until we have enough data on whether brief-aligned
signals actually outperform brief-opposed ones, this layer is read-only and purely
informational."*

**Movement statement** assembles one structured object that the website, Discord and any
other surface render identically. The source describes itself as *"the SINGLE SOURCE OF
TRUTH for the movement statement"*. That module header also calls it **NOT user-facing**,
and that part is now stale: `platform/deploy.sh:177` ships the flag `true` and
`platform/api/routers/dashboard.py:530-545` exposes the enabled endpoint that the React
Movement Read card consumes. It is feature-flagged and the flag is on.

## Bias values

| Value | Meaning |
|---|---|
| `CALL` | brief recommends a CALL setup **and FTFC does not contradict it** |
| `PUT` | brief recommends a PUT setup **and FTFC does not contradict it** |
| `NEUTRAL` | brief is "No signal", or only "building" — not actionable |
| `CONFLICTED` | brief direction disagrees with FTFC direction; the brief is internally inconsistent |
| `UNAVAILABLE` | no brief row for this `(ticker, date)` |

**`CALL`/`PUT` do not mean FTFC corroborates the call.** `classify` falls through to the parsed setup when `ftfc_direction` is missing or `mixed`; only an explicitly *opposite* bullish/bearish value produces `CONFLICTED`. So a consumer can receive `CALL` with no FTFC agreement behind it, and reading the tag as a two-source confirmation overstates the evidence attached to it.

**Cold start and failure both return `UNAVAILABLE`**, so the monitor treats an unmapped
state as *no information* rather than spurious agreement. When Cloud SQL is not
configured (CI, unit tests) or the query fails, the result is also `UNAVAILABLE` and the
monitor simply omits the brief tag — the display is additive.

## Entry points

`get_premarket_bias` · `classify` · `alignment` · `level_aware_alignment`
(`brief_bias.py`); `is_enabled` · `market_today` · `assemble_movement_statement`
(`movement_statement.py`).

`_SETUP_RE = re.compile(r'\((\d)/5\)')` at `brief_bias.py:37` parses the brief's
setup-strength notation.

## Live gating

`platform/deploy.sh:177` sets **`MOVEMENT_STATEMENT_ENABLED=true`**, and both the staging and
production Cloud Build deployments pass the same value. **The Movement Read card is enabled
in the deployed environments.**

An earlier revision of this document said the flag was `false` and the card "double-fenced".
That was wrong, and worth recording how: it was taken from
[#1025](https://github.com/TeneikaAskew/stocks/issues/1025)'s body, which described the state
on 2026-09-07. [#1024](https://github.com/TeneikaAskew/stocks/pull/1024) flipped it back to
`true` the same day — `platform/deploy.sh:133` says so in as many words. **An issue body is a
snapshot, not current state**, the same trap as a stale docstring.

What remains true: `_model_degeneracy` in `lib/movement_statement.py:363` is a render-layer
backstop that refuses to show a degenerate magnitude bucket. With the flag on, that check is
the *only* thing standing between [MODEL-MAG-001](../MAGNITUDE_ENGINE_RESULTS.md)'s collapse
and the card — one fence, not two.

## Rationale

**Partly recorded.** The `UNAVAILABLE`-on-failure choice *is* explained in source — it
exists so a missing brief cannot read as agreement, which is a deliberate application of
CLAUDE.md Rule 3.7. The visibility-only posture is also explained: there is not yet
evidence that brief-aligned signals outperform brief-opposed ones.

**The actionable threshold is recorded**, and an earlier revision wrongly said it was not:
`SignalConfig.premarket_signal_threshold` defaults to **3** and
`premarket_building_threshold` to **2** (`lib/config.py:490-491`), and
`gcp/premarket_brief.py:999-1000` reads both to produce the setup status that `classify`
parses. A score of 3+/5 is a setup; 2 is "building"; below that is no signal.

**UNKNOWN:** why 3 and 2 are the right cut-points, and how the `(\d)/5` scale itself was
constructed, are not recorded.

## Tests

`tests/gcp/test_signal_monitor_brief_bias.py` · `test_signal_monitor_level_state.py` ·
`test_signal_monitor_replay_clock.py` · `test_replay_daily_cap.py` ·
`tests/lib/test_movement_statement.py` · `tests/scripts/test_verify_brief_bias.py`

## Known issues

**None open.** [#900](https://github.com/TeneikaAskew/stocks/issues/900) (cache not keyed
by session date) closed 2026-09-14. The registry's `RETEST` recommendation therefore
rests on no current blocker and needs either a stated reason or a status change — tracked
as DOC-01 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).
