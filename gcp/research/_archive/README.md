# Archived P7 modeling scripts

**Quarantined 2026-05-26** per user instruction. These were the modeling
pipeline from the prior P7 audit session (see
`docs/research/2026-05-25/P7_final_cost_finding.md`). The verdict
from that work: every entry signal tested produced gross-of-cost edge
below the 10 bp round-trip line. The historical `BACKTEST_RESULTS.md`
that justified the +133% Sharpe / 0.43 figure was computed gross of
transaction costs.

These scripts are kept (NOT deleted) because the negative results +
methodology audit are worth preserving. They are moved out of the
active path so:
  - The active strat_engine directory in `gcp/research/strat_engine/`
    cannot be confused with the dead approach
  - These scripts cannot be accidentally run alongside the new pipeline
  - Future automated tooling (workflows, schedulers, deploys) won't
    pick them up

DO NOT re-import or re-deploy. Read for historical methodology only.

| script | purpose | verdict |
|---|---|---|
| p7a_iwm_30m_pipeline.py | LightGBM return regression | gross +7-8 bps, net -2 to -3 |
| p7b_next_candle_classifier.py | 4-class candle-type classifier | 60% acc but no P&L |
| p7c_stacked_regression.py | classifier features stacked into regression | adds ~0 lift |
| p7d_pnl_backtest.py | fixed-bps TP/SL backtest | all cells net-negative |
| p7e_structural_backtest.py | structural exit + R-multiple | still net-negative |
| p7f_voter_overlay.py | classifier filter on 3-of-5 voter | small lift, voter base too negative |
| p7g_voter_rulebook_sweep.py | strength sweep under rulebook ladder | all cells net-negative |
| p7_analyze_tf.py | early multi-TF analysis | superseded |
| p7_compile_report.py | aggregator | superseded |

**The data builder `p7_build_multi_tf_features.py` is NOT archived** —
it builds `strat_features_{tf}` and is referenced by strat_engine.
It will be copied to `gcp/research/strat_engine/strat_data_builder.py`
and the forward-compat fix (ORB + historical levels + order blocks +
current-period levels) applied there. The original stays in place for
the duration of the migration.
