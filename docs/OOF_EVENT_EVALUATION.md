# Out-of-fold event evaluation

`lib.oof_event_evaluation.evaluate_oof_events` is the dedicated economic
evaluation boundary for model alerts. It deliberately does not train a model:
every input prediction must carry a fold identifier and a `trained_through`
timestamp strictly earlier than its alert timestamp. This makes accidental
in-sample evaluation a hard error.

## Candidate and execution contract

Each candidate defines an `instrument`, signal `spot`, decision (`long`,
`short`, or abstain), and optional `target_dte`. Contract selection is fixed:

1. calls for long decisions and puts for short decisions;
2. nearest expiration on or after the requested DTE;
3. nearest listed strike to the signal-time spot;
4. entry at the first valid **ask** after configured latency; and
5. exit at the first valid **bid** after the holding period.

The engine never substitutes underlying close-to-close returns or synthetic
option marks. It applies per-side slippage and fees, a configurable missed-fill
probability, contract and concurrent-position limits, and treats capacity-
rejected overlapping alerts as zero-P&L alerts. Thus overlap does not create
independent capital and missed/rejected alerts remain in expected-value and
fill-rate denominators.

## Output and production gate

Gross and net metric sets separately report P&L, expected value per alert,
drawdown, turnover, exposure, session Sharpe and Sortino, profit factor, hit
rate, and fill rate. Net expected utility also receives a session-block
bootstrap confidence interval. Production eligibility requires:

- real executable option quotes;
- a net expected-utility confidence interval wholly above zero; and
- maximum net drawdown no greater than the configured limit.

Without option execution data, results are always labeled **model-quality
evidence only**, never trading-performance evidence.

## Baselines

Candidate data may contain `class_prior_prediction`, `buy_hold_prediction`,
and `volatility_prediction`. These decisions must themselves be computed from
the fold's prior information. Each available baseline is independently replayed
through the same contract selection, bid/ask execution, costs, fill model, and
position limits. A missing baseline is reported as unavailable rather than
quietly invented from realized outcomes; abstention is always reported.
