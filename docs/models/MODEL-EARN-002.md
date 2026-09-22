# MODEL-EARN-002 — Earnings-reaction setup classifier

**Code:** `gcp/earnings_reactions_brief.py` (`classify_context`, `:474-565`) ·
**Output:** a Discord embed — **no table, no API surface** ·
**Job:** `earnings-reactions-brief` — scheduled `earnings-reactions-brief-daily`,
`35 8 * * 1-5`, **ENABLED** ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-18

> **Registered 2026-09-18, after running unregistered on a weekday cron.** A repo-wide search
> found no model row and no reference document for this classifier, and it shares no code with
> [MODEL-EARN-001](MODEL-EARN-001.md) — `grep "lib\." gcp/earnings_reactions_brief.py` returns
> **zero matches**. Found by review on
> [#1111](https://github.com/TeneikaAskew/stocks/pull/1111); recorded as DOC-33.

## What it decides

Per upcoming reporter, one of **four** labels, from 12 quarters of reaction history. The
docstring is careful about what the label means, and the distinction is the reason this is a
separate model rather than a variant of MODEL-EARN-001:

> *"The classification CHARACTERISES the historical setup — it does NOT predict the upcoming
> direction."*

| Label | Rule | Source |
|---|---|---|
| `INSUFFICIENT-HISTORY` | fewer than `MIN_QUARTERS_FOR_CLASSIFICATION = 4` **rows** in the window | `:521-526` |
| `FAILED-GAP-RISK` | `reversal_rate >= REVERSAL_HIGH = 0.40` — checked **first**, so it overrides any drift/consistency read | `:533-538` |
| `SELL-THE-NEWS-CANDIDATE` | `drift_10d >= DRIFT_HOT_PCT = 2.0` **and** `consistency >= CONSISTENCY_HIGH = 0.60` | `:544-549` |
| `BUY-THE-NEWS-CANDIDATE` | `consistency >= 0.60` **and** drift is not hot to the upside (`None`, negative, or below +2.0) | `:552-557` |
| `FAILED-GAP-RISK` (fallback) | nothing above fits | `:560-565` |

Constants at `:72-95`. `FAILED-GAP-RISK` is reachable two ways — as a positive finding and as
the residual bucket — and the code is explicit that the second is *"a conservative default, not
a silent fallback: the reason string names exactly which thresholds were missed"*. Every branch
returns `(label, reason)`, and the reason carries the numbers that produced it, which is
CLAUDE.md Rule 3.7 done properly at a classification boundary.

`INSUFFICIENT-HISTORY` is likewise a deliberate refusal rather than an imputation — the comment
at `:72-75` says the aggregates *"would be too noisy to characterise a setup. NEVER imputed to
0 (CLAUDE.md 3.7)."*

## Where the output goes

**Discord, and nowhere else.** `build_discord_message` (`:772-830`) renders a four-section
embed — last session's actual reactions, then one section per candidate label — and `:894`
posts it via `send_to_discord`, reusing `gcp/premarket_brief.py`'s helper rather than hand-rolling
one (`:54`). There is no Cloud SQL write;
[05-c-DATA_DEPENDENCIES](../product/infrastructure/05-c-DATA_DEPENDENCIES.md) records the same
independently.

So **the labels are the product**. Unlike MODEL-EARN-001, whose score is one field among many
on a row a user may or may not read, this model's entire user-visible output *is* its
classification. A mislabel is not a degraded number; it is the whole message.

The module docstring notes the dataclass exists *"so a website surface can consume it later"* —
that is stated intent, not current wiring, and this document does not report it as one.

## This is the fourth independent archetype-shaped classifier in the earnings surface

Worth stating plainly, because the count is the finding:

| Implementation | Where | Governed by |
|---|---|---|
| `classify_archetype` | `lib/earnings_reactions.py:460` | MODEL-EARN-001 — the canonical one |
| `_derive_archetype` | `gcp/refresh_earnings_views.py:312-336` | MODEL-EARN-001, as a **divergence** — [#1135](https://github.com/TeneikaAskew/stocks/issues/1135) |
| `recommended_structure` | `lib/earnings_reactions.py` | MODEL-EARN-001 |
| **`classify_context`** | `gcp/earnings_reactions_brief.py:474` | **this model** |

`classify_context` is **not** a duplicate of `classify_archetype` — it answers a different
question (characterise the historical setup, versus tag an archetype for sizing) and its
thresholds are its own. That is why it is registered separately rather than folded into
MODEL-EARN-001, following the precedent set for
[MODEL-FLOW-001](MODEL-FLOW-001.md) in the same review cycle. But four threshold ladders across
one domain, three of them undocumented until this PR, is a structural observation a reader
should have.

## Entry points

`classify_context` · `TickerReactionContext` · `build_discord_message` · `main`

## The sufficiency gate counts rows, not clean quarters

`aggregate_history` (`:416`) sets `n_quarters = len(rows)` — the number of rows in the
12-quarter window, full stop — and `has_sufficient_history` (`:152`) compares that to
`MIN_QUARTERS_FOR_CLASSIFICATION = 4`. No row is checked for completeness.

That matters because every rate the classifier then reads is computed over a *different*
denominator. `_bool_rate` and `_avg_abs` drop `None` / `NaN` before dividing, deliberately —
*"a NULL row is excluded from BOTH numerator and denominator so the rate stays an honest
fraction (no NULL→0 imputation, CLAUDE.md 3.7)"* (`:420-423`). So a ticker with four rows of
which three have a null `is_reversal_5d` passes the gate with `n_quarters = 4` while
`hist12q_reversal_rate` rests on **one** observation, and `REVERSAL_HIGH = 0.40` is then
compared against a rate that is either 0.0 or 1.0. The per-rate honesty is real; the gate in
front of it does not share it.

> **An earlier revision of this document said the gate needs "four clean quarters".** That
> phrasing was not invented here — the code's own comment at `:484` says *"Fewer than
> `MIN_QUARTERS_FOR_CLASSIFICATION` (4) clean quarters of …"*, and the constant's name says
> quarters. Both describe an intent the function does not implement. Reading the comment and
> the name instead of `aggregate_history` is the same failure this registry has recorded
> against module docstrings (DOC-18, DOC-23, #1137); it is worth noting that it is equally
> available from a name and an inline comment, and that here it produced a *documentation*
> defect on top of the code one.

## Rationale

**UNKNOWN — not recorded in code or tests.** All four constants are stated with a one-line
label and no derivation: `MIN_QUARTERS_FOR_CLASSIFICATION = 4`, `DRIFT_HOT_PCT = 2.0`,
`CONSISTENCY_HIGH = 0.60`, `REVERSAL_HIGH = 0.40`. Nothing records why 40% is the reversal
cut, why 60% is "high" consistency, or why +2.0% counts as having run into the print.

What *is* recorded, and recorded well, is the **ordering**: the docstring explains why reversal
is checked first (*"a high reversal rate overrides any drift/consistency read because it
directly measures gap failure"*) and why the residual bucket is failed-gap. Rule precedence has
a rationale here; the thresholds it operates on do not.

## Why the status is Experimental / RETEST

**No experiment in the ledger evaluates this classifier** — no `E-` id, no Book II entry, no
backtest of whether a `SELL-THE-NEWS-CANDIDATE` label precedes a fade. It has run to Discord
every weekday since deployment on thresholds nobody has tested, and MODEL-EARN-001's quintiles
show the bar this repo can clear when it does test (a 21,592-prediction calibration).

That is the whole of the RETEST recommendation: not that the labels are wrong, but that no one
has checked.

## Tests

`tests/gcp/test_earnings_reactions_brief.py`

## Known issues

**None filed.** The threshold rationale gap is recorded above and in
[15-OPEN-DECISIONS](../product/15-OPEN-DECISIONS.md) with the other `UNKNOWN` rationales.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
