# Task4 fix1 — scoped independent re-review

**Spec compliance: Issues found in the fix interaction.**
**Code quality: Needs fixes.** The original R1–R5 counterexamples have substantive corrections, but R1 introduces one demonstrated delivery-order regression, N1 below. **Bounded Task4 approval is withheld pending N1.** No fresh whole-task review or upstream acceptance is asserted.

## Identity and scope

Read the prior independent review, complete `reviewed-to-fix1.diff`, fix report, command log, frozen manifest, preservation checks, changed functions in context and all appended regression tests. Reviewed the interactions between activation confirmation, pending invalidation, retained bar evidence, gap reconciliation, partial-day gap validation, cluster selection and public reason propagation.

Independently verified:

- All15 live files match their fixed frozen copies and manifest hashes.
- All15 original frozen files retain their original manifest hashes.
- The11 previously approved Tasks1–3 paths match both original and fixed identities.
- Only `lib/strat_levels.py` and `tests/lib/test_strat_levels.py` differ between the two15-path manifests.
- All three reviewed level-test prefixes are preserved; legacy tracker `update` and `state` ASTs are unchanged.

Reviewed source: `ca3ecd8e111c1c1b4f8f27dcb6a1a5503bdb2fe354f74b45483ed830d2220f4b`.
Reviewed tests: `3fdf3d80d2bec533893e1b2f08ea412076f7abe1fa5d8b557fdd421a34b2d25d`.
Comparison source: `f72882e03817495ff154a5f883b397d7bdd19157550b39b9a66e5fde150af65c` from `fix1/baseline/lib/strat_levels.py`.

No source edits, Git, cloud, data-source calls, nested agents or Task5A work occurred. The only behavioral execution was the bounded pure-local N1 probe described below, justified by an untested concrete interaction; no test suite was rerun. Python was `/workspace/stocks-venv/bin/python`, shells sourced `/workspace/stocks-setup/shell-env.sh`, and the probe disabled bytecode writes.

## R1–R5 dispositions

| Finding | Disposition | Source and sensitive evidence |
|---|---|---|
| R1: pre-confirmation/prior evidence permanently contaminates ambiguity | **ADDRESSED for the original cases; fix acceptance blocked by new N1** | `lib/strat_levels.py:415,444,450` uses touch's earliest observed interval and hold/close's actual confirmation endpoint. `tests/lib/test_strat_levels.py:1512` onwards covers failed-close and hold excursions, prior adjacent hold stops and prior different-frame extrema in both delivery orders, with call/put mirrors. The12 formerly failing cases now pass. Genuine same-bar touch ambiguity and opposing-close proof are retained. However, evidence spanning a later activation is not reconciled in the coarse-first order; see N1. |
| R2: late opening-gap evidence leaves state dependent on frame order | **ADDRESSED** | `lib/strat_levels.py:393` reconciles fresh/activated states when the gap flag becomes known. Held/failed/invalidated/ambiguous precedence remains. Tests cover both frame permutations and put mirrors, plus four stronger-state controls. Added gap-event evidence/reconciliation timestamps at`:470` do not rewrite earlier activation events. Gap fresh-entry eligibility remains false and executable entry remains unknown. |
| R3: partial current day suppresses existing gap history | **ADDRESSED** | `lib/strat_levels.py:1906` admits the validated current daily aggregate as fill evidence;`:1922` refuses missing current evidence when source observations are due. `compute_gap_levels` at`:999,1025` keeps the legacy default and excludes an incomplete latest row only from gap origination, while preserving it in subsequent fill comparisons. The13 real-aggregator/builder cases assert actual up/down boundary prices, unfilled/filled current partials, no new partial origin, future-row exclusion and invalid/missing-current refusal. |
| R4: rejected single-frame cluster consumes valid members | **ADDRESSED** | `lib/strat_levels.py:1100,1113` records tentative candidate indices and consumes them only after eligibility. The exact three-level counterexample asserts named day/week members, center100.17, count2 and strength2.5. Existing tolerance, strength formula and same-frame rejection remain. |
| R5: LevelMap drops trigger-selection reasons | **ADDRESSED** | Legacy coverage at`lib/strat_levels.py:1672`, strict coverage at`:2028` and strict leg metadata at`:2048` preserve selection reasons separately from activation-evidence reasons. Six tests exercise stale-only/empty/valid hypotheses through both public builder versions. Strict basis refusal retains its actual admission reasons at`:2025` instead of implying that selection succeeded. |

## Recorded test evidence inspected

The actual `red-with-timestamps.txt` reports **36 failed,5 passed** before the source fix. Its named failures cover all five findings; the five passing controls are retained. `green-focused-1.txt` reports **43 passed**, comprising41 appended cases plus two unchanged ordering controls. `green-final.txt` reports **229 passed in23.37s**, with no skips or warnings, for the three affected level modules under explicit `--mode=mock`.

The assertions exercise actual production functions and, for gap cases, the existing local DataLoader aggregator. They are sensitive to the original defects. They do not cover a coarse range that spans activation and arrives before the activation frame: the added `test_late_prior_extrema_remain_descriptive` ends the coarse range before activation, and the sticky-ambiguity test delivers post-activation evidence after activation. N1 is therefore not contradicted by GREEN.

## N1 — P2 / Important: Coarse-first stop/target evidence spanning activation is lost

**Fix-induced location:** `lib/strat_levels.py:450` (new requirement that `_typed_activated` already be true while processing the current bar), interacting with the activation path at`:378` and pending evidence at`:404`. The pending invalidation record is created only when the configured invalidation confirmation succeeds; it cannot recover a stop/target range whose final close did not confirm invalidation.

**Concrete consistent input:** Both frames are observed at`2026-04-01T09:35:00-04:00`, using aware Eastern intervals and `is_session_open=False`. Call setup is trigger100, target102, stop98, with1m `bar_close` activation above100 and5m `bar_close` invalidation below98.

| Frame | Interval | Call OHLC | Put mirror OHLC |
|---|---|---|---|
| Fine | 09:30–09:31 | `(99,101,99,100.5)` | `(101,101,99,99.5)` |
| Coarse | 09:30–09:35 | `(99,103,97,100.5)` | `(101,103,97,99.5)` |

For puts use trigger100, target98, stop102, activation below100 and invalidation above102. The fine bar does not reach either stop or target. The enclosing coarse bar reaches both, with their order unknown after the fine close activation; its own close does not confirm invalidation. These are compatible observations of one price path, not conflicting bars.

**Why the new result is wrong:** Coarse-first delivery sees `_typed_activated=False`, skips the new ambiguity branch and has no confirmed invalidation to retain. Fine delivery then activates, but checks only its own extrema. Fine-first delivery activates before processing the coarse range and records `stop_target_order_unknown`. The same observed evidence and knowledge clock produce a safe-looking activated state or an ambiguous state solely from frame delivery order.

**Executed bounded probe:** Loaded the actual reviewed baseline and fixed source as separate modules with `importlib.util.spec_from_file_location`, constructed `LegStateTracker`/`LevelConfirmation` directly, and called `observe_bar` for the two bars in both permutations, with both directions. No mocks, replay engine, test module or source edits were used. Actual results:

| Source | Direction | Delivery order | Final state | Reasons |
|---|---|---|---|---|
| Reviewed f72882 | Call | Fine, coarse | ambiguous | stop_target_order_unknown |
| Reviewed f72882 | Call | Coarse, fine | ambiguous | stop_target_order_unknown |
| Reviewed f72882 | Put | Fine, coarse | ambiguous | stop_target_order_unknown |
| Reviewed f72882 | Put | Coarse, fine | ambiguous | stop_target_order_unknown |
| Fixed ca3ecd8 | Call | Fine, coarse | ambiguous | stop_target_order_unknown |
| Fixed ca3ecd8 | Call | Coarse, fine | **activated** | **empty** |
| Fixed ca3ecd8 | Put | Fine, coarse | ambiguous | stop_target_order_unknown |
| Fixed ca3ecd8 | Put | Coarse, fine | **activated** | **empty** |

All eight runs have `activated=True` and `invalidation.confirmed=False`. The loss of ambiguity in two fixed-source permutations proves this is introduced by fix1, rather than a newly discovered unchanged defect. Expected: both orders retain `stop_target_order_unknown`; confirmed invalidation remains false because close confirmation did not occur.

**Required bounded correction:** Retain/reconcile relevant coarse stop/target evidence when activation is subsequently established, respecting the configured activation endpoint and original evidence knowledge time. Keep wholly prior/pre-confirmation excursions descriptive, preserve same-bar touch/close semantics and sticky genuine ambiguity, and maintain bounded state rather than refolding unbounded history. Add call/put and both-order RED cases for this exact input and appropriate hold-confirmation interaction controls. No new fill-price or strategy definition is needed.

## Remaining gates and bounded outcome

R2–R5 and the original R1 counterexamples are repaired. N1 is the only new defect class found in this scoped complete fix pass. Task4 fix1 remains **Needs fixes** for N1; this review does not grant Task5A start or whole-feature acceptance.

The existing actual merged calendar/DATA basis, source/PIT, owner-defined canonical PMG/custom anchors, downstream Task5A/5E parity and M1 envelope propagation, resolver/#908 fill-dependent treatment, production replay/resource qualification and final delivery gates remain unchanged. Synthetic coherent tests are local arithmetic/contract evidence only. No new source/calendar implementation or financial rule is requested, and no existing requirement is waived.

## Exact executed N1 reproduction command

Working directory: `/workspace/stocks-strat-rebuild`. Exit code0. The command emitted the eight results tabulated above as JSON; it was run once.

```bash
. /workspace/stocks-setup/shell-env.sh && PYTHONDONTWRITEBYTECODE=1 /workspace/stocks-venv/bin/python - <<'PY'
import importlib.util, json, sys
from pathlib import Path
import pandas as pd
base=Path('/workspace/strat-rebuild-control/task4-rebuild/fix1/baseline/lib/strat_levels.py')
fixed=Path('/workspace/stocks-strat-rebuild/lib/strat_levels.py')
outputs=[]
for name,path in [('reviewed',base),('fixed',fixed)]:
    spec=importlib.util.spec_from_file_location('review_probe_'+name,path)
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
    for direction in ('call','put'):
        call=direction=='call'
        for coarse_first in (False,True):
            tracker=module.LegStateTracker(direction,100.,102. if call else 98.,98. if call else 102.,
                activation_rule=module.LevelConfirmation(100.,'above' if call else 'below','1m','bar_close'),
                invalidation_rule=module.LevelConfirmation(98. if call else 102.,'below' if call else 'above','5m','bar_close'))
            bars=[('1m','09:30','09:31',(99.,101.,99.,100.5) if call else (101.,101.,99.,99.5)),
                  ('5m','09:30','09:35',(99.,103.,97.,100.5) if call else (101.,103.,97.,99.5))]
            if coarse_first: bars.reverse()
            stamp=lambda t: pd.Timestamp('2026-04-01 '+t,tz='America/New_York')
            for frame,start,end,values in bars:
                tracker.observe_bar(*values,bar_start=stamp(start),bar_end=stamp(end),observed_at=stamp('09:35'),timeframe=frame)
            state=tracker.typed_state
            outputs.append({'source':name,'direction':direction,'coarse_first':coarse_first,'state':state['state'],
                            'activated':state['activated'],'invalidation_confirmed':state['invalidation']['confirmed'],
                            'reasons':state['reasons']})
print(json.dumps(outputs,indent=2))
PY
```

## Durable source/evidence backup

The frozen fix1 candidate, baseline, sensitive RED/GREEN logs, manifests, exact original reviewer command/argv/script/stdout and this independent review are preserved in a 42-member source-only archive. No raw provider data, native database captures, private IAM policies or credential values are included. This is a new reconstructed, **unapproved** candidate; N1 is undergoing bounded fix round2/5.

Archive: `task4-fix1-reviewed-checkpoint.tar.xz`, 140,512 bytes; SHA256 `8f892706d6789553256f972484a44aebe574012f8e7fc80f132f23297b05bc86`. Review SHA256 before this publication appendix: `afbf617da23ed99acba0114611a5e616bc49cb85e889078ab8724d64557e3490`.

- [Archive part 1/5](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370150647)
- [Archive part 2/5](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370151182)
- [Archive part 3/5](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370151631)
- [Archive part 4/5](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370152100)
- [Archive part 5/5](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6370152678)

Decode each comment’s base64 separately and concatenate decoded bytes in numeric part order. Verify archive SHA256 and every member against `BACKUP-MANIFEST.json`. Original archives/checkpoints remain intact. The historical probe used the live fixed-source path while its hash was ca3ecd8; after later edits, that identity is preserved at the archive’s `frozen-actual-tree/lib/strat_levels.py`. No probe re-execution is claimed for creating this backup.
