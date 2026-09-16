# MODEL-AGREE-001 — Strategy-agreement scoring

**Code:** `lib/strategies/agreement.py` (106 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

When [MODEL-MOM-001](MODEL-MOM-001.md) and [MODEL-MR-001](MODEL-MR-001.md) both fire on
the same bar **and target the same direction**, that is a "stacked" high-conviction
signal. This module detects that case and produces a composite score.

The source records that same-direction agreement is **~21% of overlapping fires** — the
other ~79% are the opposing-direction case the momentum docstring describes.

## Inputs

The two strategies' per-bar outputs. **Pure helper: no database access, no I/O.**

## Entry points

| Symbol | Signature | Role |
|---|---|---|
| `detect_agreement` | `(momentum, mean_reversion) -> Optional[dict]` | Returns the agreement payload, or `None` when they do not agree |
| `composite_score` | `(signals) -> float` | The ranking score |

The live signal monitor calls `detect_agreement` once per bar after running both
strategies, persists the payload to `signal_alerts.strategy_agreement`, and uses the
composite score to rank Discord embed output.

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
