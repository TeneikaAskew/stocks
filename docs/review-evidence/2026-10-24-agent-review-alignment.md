# Agent-review alignment execution evidence

Scope: stocks PR #1583; one writer `/root`, same linked root as spec PR #1577.
Approved plan: `98f76a762cb6ec61e87b604d3d84e9ffc6264c46`; user approval
`Sentinel_fd7544adf8688191b3d10338c91a0f9b` authorizes implementation and Codex
review when ready, while keeping the PR draft. No merge/deployment authority.
Spec landed at `641a93b96e4f7fccab9f57e1be9adf3a221dbc55`.

## Lineage and transition

- Root: stocks#1577 → implementation stocks#1583, not a replacement/reset.
- Known local history: initial source review and acceptance design; one draft
  acceptance review found the hash-precheck race and ambiguous external extension
  count. Both were corrected before publication. Exact prepublication draft blob
  identities were not captured: unknown, not zero spent effort.
- First external code review: `603c84a1`, clean:
  https://github.com/TeneikaAskew/stocks/pull/1577#issuecomment-6384582599.
- First security review: `603c84a1`, clean:
  https://github.com/TeneikaAskew/stocks/pull/1577#issuecomment-6384593630.
- Second external code review: `85b047e7`, clean:
  https://github.com/TeneikaAskew/stocks/pull/1577#issuecomment-6384645818.
- Additional internal work: acceptance planning and plan self-review, including
  removal of the premature proposed-budget adoption hold. No historical activity
  is erased or silently reclassified into a fresh allowance.
- Current main rules govern delivery until the policy change lands. #1583 has
  zero external code reviews at execution start. This is observed history, not a
  grant/reset of a proposed lineage allowance. Adoption requires reconciliation of
  unknown legacy effort before asserting remaining aggregate/external allowance.

## Reserved judgment work

BASE-01: one read-only participant, complete C1-C9/C11 baseline instruction exercise,
policy `98f76a762cb6ec61e87b604d3d84e9ffc6264c46`. Inputs fixed before dispatch;
participant sees inputs/current policy, not expected outcomes or proposed spec.
Input JSON SHA-256: `ca4c88d6584ca46bd732632fabd63dcca7edf4998351cd39c653442c672ca97f`.
C7 temporary fixture commits: `f7f894f32d94d13cd3da859c5144aee2b6dd395e` and
`601ceafa7182b967a3b74d2c97461a4c7cfb57b7` (instruction exercise, not product data).

HEAD-01: reserved for the same inputs under one pinned implementation candidate,
plus independent whole-branch review. Individual reviewer roles/results will be
recorded; no hidden restart or uncounted fix-verification pass is authorized.

## Rulings and limits

Ruling: this is policy-only work. Baseline/proposed participant decisions provide
instruction-compliance evidence, not an executable controller or live durability
proof. Existing gate/generator/verifier tests provide mechanical regression evidence.
Do not invent a simulator and label its hardcoded answers enforcement.

Ruling: a real shared-writer handoff is not needed for C11's accepted control;
use uncontended publication by the designated writer. Active-writer handoff
must be refused; no second agent may write shared files in this task.

No runtime, provider, production, architecture-migration, options, STRAT or fixture
implementation changes. Solyra remains subject to its own spec/plan gates.
