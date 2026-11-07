# Required CI audit plan

Authorized scope: documentation and evidence only, on `docs/required-ci-audit`,
based on current main `911d30a7427a8d3249ecd82a828952a3e4b639a0`.
This implements the requested audit publication, not a CI implementation change.
The product-delivery documentation exception applies; no implementation spec is
created or approved by this audit. Any later code change needs its own existing
product-delivery specification and authorization.

1. Read repository guidance and prior test audit; map the six screenshot checks
   to current workflow steps, dependencies, triggers and requirement contracts.
2. Collect actual pytest node IDs in bounded local runs. Record environment,
   skipped collection and failures separately from static estimates. Compare
   overlaps, fixture reachability and suspicious assertion/skip patterns.
3. Inspect current implementation and historical changes for high-impact cases.
   Measure existing hosted job evidence and focused local runs. Use temporary,
   isolated mutation controls without committing runtime/test modifications.
4. Publish substantive classifications, risks and follow-up decisions with
   machine-readable inventory and exact reproduction commands. No blanket
   deletion, gate weakening, release dependency, production/provider access,
   workflow dispatch, merge or deployment.
5. Verify audit-only diff, JSON, ordinary spec gate and branch/main docs audits;
   open and verify a separate draft PR through the repository publication path.

The six check names are taken from the parent-inspected screenshot. It does not
prove obsolescence, nor does this audit independently certify protection settings.
No usage-budget meter is exposed to this environment; preserve the existing 1%
floor if a meter becomes available. Do not infer remaining budget from tokens.
