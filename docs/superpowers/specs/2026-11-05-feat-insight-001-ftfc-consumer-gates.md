---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-PLAYBOOK-001, REQ-REL-001, REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [INSIGHTS-07]
done_when:
  - "tests/agents/test_ftfc_consumer_gates.py::test_aligned_is_the_same_for_the_raw_score_and_its_snapshot passes: compute_risk_metrics and orchestrator._calibrate_conviction read one shared aligned helper and give the same answer for the raw legacy score (0.3 - 0.1) / 0.4 and for its 2 dp snapshot, for a long and a short, while a long at 0.499 and a short at -0.499 stay unaligned on both paths (so a helper that rounds before comparing fails it); the test fails on origin/main"
  - "tests/agents/test_ftfc_consumer_gates.py::test_conservative_minimum_follows_the_trade_direction passes: the conservative persona sizes a long only at ftfc_score >= +0.30 and a short only at ftfc_score <= -0.30, and its stand-aside rationale names the threshold on the trade's side; the test fails on origin/main"
  - "No stored score, weight or threshold changes and no ranker change: lib/strat.py, lib/config.py and lib/agents/ranker/ are not in the diff, tests/agents/test_ranker.py passes unchanged, and tests/lib/test_backtest_ftfc_causality.py, tests/lib/test_exec_ftfc_contract.py, tests/lib/test_trade_planner.py, tests/agents/test_persona_risk_metrics.py and tests/agents/test_agent_orchestrator.py pass"
  - "The PR body shows the old and new decision of each gate for IWM, SPY and QQQ on the 20 sessions through 2026-11-04 and the 2026-11-05 brief, and the count of changed days from 2015-01-02, with the planner's direction shown as a hypothetical long and short because the live direction comes from an LLM"
  - "Source identity (INSIGHTS-07): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-INSIGHT-001, INSIGHTS-07) note row carries that source_identity_sha256"
  - "The FEAT-INSIGHT-001 catalog record and the PR traceability entry are updated, the matched current-main-versus-branch docs_audit.py run reports nothing new, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# FTFC consumer gates in lib/agents: one aligned rule, a directional conservative minimum

## Authority

Proposed on 2026-11-05 by a FEAT-INSIGHT-001 delivery lane, from the read-only FTFC replay of
IWM, SPY and QQQ daily bars (2015 to 2026) that the owner asked for on 2026-11-05. It is not
self-approved: it takes effect only when the owner authorizes the merge of the spec-only PR that adds
it, and that merge is the approval its `status` records.

It replaces the unmerged spec PR #1730 at the same path, with the ranker item removed (now covered by
the FEAT-STRAT-001 spec in PR #1735).

## Problem

Two defects in `lib/agents/`, each read in the code at origin/main 5ce0ad17:

1. **`ftfc_aligned` differs by path.** `compute_risk_metrics` (`lib/agents/trade_planner.py:663-667`) and
   `_calibrate_conviction` (`lib/agents/orchestrator.py:920-923`) compare the score with `>= 0.5` /
   `<= -0.5`. The legacy vote with the default weights (1d 0.30, 1w 0.10, 1mo 0) scores a 2U daily with
   a 2D weekly as `(0.3 - 0.1) / 0.4 = 0.49999999999999994`. Raw, that is not aligned;
   `summarize_strat_status` (`lib/agents/summarizers.py:456-458`) rounds it to 0.5, so a consumer of the
   snapshot reads it as aligned. Mathematically the score is 0.5.
2. **The conservative minimum ignores direction.** `_plan` (`lib/agents/trade_planner.py:575-577`) and
   `_build_rationale` (`:749-753`) stand aside when `ftfc_score < 0.30`. A short only passes when the
   bias is bullish, and a short against a strong bearish bias stands aside.

## Non-goals

- No change to how FTFC is computed, stored or rounded: `lib/strat.py`, `lib/config.py` and
  `summarize_strat_status` are untouched, so the 34 exact legacy final-as-of controls of the
  FEAT-STRAT-001 foundation spec stay exact.
- No change to the ranker. The same replay found its direction points never fire (it tests
  `("bull", "bear")` while the stored values are `bullish` / `bearish`). Those points are not fixed
  here: the FEAT-STRAT-001 spec in PR #1735 removes them from `signal_strat_alignment` altogether,
  because the vote is mixed on exactly the days whose prior bar is an inside bar, so turning them on
  would score a ticker lower while it sits on a 2-1-2 or 3-1-2 setup bar.
- No change to any other threshold, weight or formula: the 0.5 aligned level, the 0.30 conservative level and
  every other persona rule stay as they are.
- No change to which FTFC the gates read (the weighted vote versus price-versus-open continuity); that
  is FEAT-STRAT-001's decision.
- No rewrite of stored `insight_reports`.

## Approaches considered

1. Round or snap the score where it is produced. Rejected: it changes stored scores, which the
   FEAT-STRAT-001 legacy controls pin byte for byte, and every consumer at once.
2. Round to 2 dp inside the comparison. Rejected: it would also call a mathematical 0.495 aligned.
3. Chosen: one shared helper, `is_ftfc_aligned(direction, score)` in `lib/agents/trade_planner.py`,
   with a 1e-9 tolerance that absorbs floating-point error only, used by both comparison sites.

## Design

- `lib/agents/trade_planner.py`: `is_ftfc_aligned` returns `score >= 0.5 - 1e-9` for a long,
  `score <= -0.5 + 1e-9` for a short and False for flat; `compute_risk_metrics` uses it.
  `_fails_conservative_ftfc(ctx)` is the conservative minimum in the trade's direction: a short stands
  aside when `score > -0.30`, anything else when `score < 0.30` (flat never reaches a persona plan).
  `_plan` and `_build_rationale` use it; a short's rationale reads "above -0.30 threshold", a long's is
  unchanged.
- `lib/agents/orchestrator.py`: `_calibrate_conviction` uses `is_ftfc_aligned`.

With the configured weights every achievable legacy score is a ratio of multiples of 0.05 with a
denominator of at most 1.0, so none lies within 0.005 below 0.5: for every score production can
compute, the raw value and its 2 dp snapshot give the same answer.

## Expected effect

From the replay: the aligned
flag changes only for callers that pass the raw score (the planner and the orchestrator read the
snapshot, so their production answer does not change); the conservative persona's answer for a short
changes on every day the bias is bullish or bearish. The PR body carries the per-day evidence.

## Capacity and cost

- **Volume and velocity:** unchanged; no new query, row or call.
- **Wall-clock:** unchanged.
- **Cost:** $0 new GCP workload, schedule or resource.

## Source identity and close-out

`lib/` and `tests/` are inside SITE's watched scope (`docs/DOC_REGISTRY.md`, the row for
`docs/product/03-SITE-TRACEABILITY.md`). INSIGHTS-07 (`POST /api/insights/report/{ticker}/refresh`)
names `lib/agents/orchestrator.py` and `lib/agents/trade_planner.py`. Only the
`(FEAT-INSIGHT-001, INSIGHTS-07)` row of the Implementation-source
notes table may describe this implementation, as backend source and local tests only, with no claim of
deployment or review. Every other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: verify main's source and body identity in a
fresh clone, complete the DOC main and staging close-out with real evidence, retire the sidecar as the
product-delivery skill prescribes, and set the plan to `status: done` on a `docs/` branch.

## Risks

- **More conservative shorts.** Shorts with a bearish bias now size where they stood aside, and shorts
  with a bullish bias stand aside where they sized. done_when 4 shows the count.
- **The docs audit reads solyra's issues**; a session without solyra access cannot run it, so the owner
  or a session with that access runs the matched pair before the PR is marked ready.
