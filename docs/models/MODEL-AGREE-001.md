# MODEL-AGREE-001 — Strategy-agreement scoring

**Code:** `lib/strategies/agreement.py` (106 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-22

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

When [MODEL-MOM-001](MODEL-MOM-001.md) and [MODEL-MR-001](MODEL-MR-001.md) both fire on
the same bar **and target the same direction**, that is a "stacked" high-conviction
signal. This module detects that case and produces a composite score.

### How often this actually happens: 2.2%, not 21%

**Measured, and the correction was already in the repo before this document quoted the stale
number.** `gcp/schema.sql:1133-1138` names the source I cited:

> Empirical rate (Track D audit 2026-05-08, § 6 / G.P2.9): 17 stacked alerts of 782 fires =
> 2.2% (per-ticker 1.4-3.2%; QQQ highest). The pre-Phase-0.7.x estimate of **~21%** in
> `docs/plans/SIGNAL_QUALITY_TEST_PLAN.md` **is stale** — momentum's gate tightened over
> subsequent phases, lowering fires without a corresponding schema-doc update.

**And the remainder is not disagreement.** An earlier revision of this document said the other
~79% were "the opposing-direction case". `docs/audit/2026-05-08/track-D.md:308-315` measured
what those rows are:

| `jsonb_typeof(strategy_agreement)` | count |
|---|---:|
| `string` (real stacked payload) | 17 |
| `null` (JSONB null, not SQL NULL) | 765 |

> On 765 of 782 alerts, only mean-reversion fired on the bar; momentum returned `None`
> (eligible neither call nor put).

So **98% of fires are solo mean-reversion**, not two strategies pointing opposite ways. The
agreement bonus therefore affects live sizing on roughly 1 fire in 45, and the opposing-direction
overlap the momentum docstring describes is rarer still.

**This is the same fact as [MODEL-MOM-001](MODEL-MOM-001.md)'s live-gating section, from the
data side** — and it carries the same limit. That document records that momentum alone cannot
fire because `enable_standalone_momentum` is `False`. This measurement shows momentum returned
`None` on 98% of the bars **where mean reversion fired**, which is not the same as 98% of bars.

> **It does not license the conclusion an earlier revision drew here** — that the disabled flag
> "costs little because there is little to discard". `signal_alerts` contains only alerts that
> were emitted, and with the flag off a momentum-eligible bar on which mean reversion misses
> emits nothing, so the discarded population is exactly the one missing from these 782 rows.
> The counters at `gcp/signal_monitor.py:1098` and `:1102-1103` would answer it; they have not
> been read. DOC-51.

## Inputs

The two strategies' per-bar outputs. **Pure helper: no database access, no I/O.**

## Entry points

| Symbol | Signature | Role |
|---|---|---|
| `detect_agreement` | `(momentum, mean_reversion) -> Optional[dict]` | Returns the agreement payload, or `None` when they do not agree |
| `composite_score` | `(signals) -> float` | The ranking score |

The live signal monitor calls `detect_agreement` once per bar after running both
strategies and persists the payload to `signal_alerts.strategy_agreement`.

**The composite score does not rank anything.** The module docstring says the monitor
will *"use the composite score to rank Discord embed output"*, but that was intent and
was never implemented: `SignalMonitor.fire_alert` emits each alert as it happens, with
no sorting or prioritisation. The score appears only as a display line
(`Composite score: X`, `gcp/signal_monitor.py:1562`) and a `🎯 STACKED ` title
prefix (`:1518`), so nothing is ordered or prioritised.

**It does change position size, though.** `gcp/signal_monitor.py:1329-1343` adds
`AGREEMENT_BONUS` into `raw_score`, which becomes `total_score` and is passed to
`get_position_size` and `get_signal_strength_label`. The source says so outright:
*"agreement bonus flows into total_score so a stacked fire actually gets a larger position
size (not just a prettier Discord embed)"*. So same-direction agreement can raise both the
size and the strength label of a fire.

An earlier revision said the score changes nothing about what fires — an overcorrection.
The first version of this document wrongly claimed the score **ranks** alerts; removing
that claim took the real effect with it. The accurate statement is narrow: it does not
order alerts, and it does size them.

## Constants

| Name | Value | Line |
|---|---|---|
| `AGREEMENT_BONUS` | `1.0` | `lib/strategies/agreement.py:28` |

## Rationale

**UNKNOWN — not recorded in code or tests.** `AGREEMENT_BONUS = 1.0` carries no
derivation, and the composite score's weighting is not tied to a measured outcome.
This is what [#905](https://github.com/TeneikaAskew/stocks/issues/905) asks for: freeze
the score and validate its expectancy prospectively. Until that lands, the score is a
ranking heuristic, not a calibrated probability — which is why the registry records this
model as `RESTRUCTURE`.

## Tests

`tests/lib/test_strategy_agreement.py` · `tests/gcp/test_signal_monitor_agreement.py` ·
`tests/gcp/test_signal_monitor_standalone_momentum.py`

## Known issues

[#905](https://github.com/TeneikaAskew/stocks/issues/905) freeze and prospectively
validate expectancy. Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
