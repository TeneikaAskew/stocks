# Measured live registry activation evidence

PR #1599 is the immutable-binding continuation required by merged #1594 /35671dbba024efa6700e29febdf7ee6b8cea41c2. Plan-only5106d88c and PR binding0f4d093f precede implementationa03d6652. Exact executable delta: live jobs.registry.timeout-minutes5to6, byte-equal separately reviewed BASEpin. Gate, tests, exporter, generated JSON, hook, assertions, commands, events, runner, permissions and runtime limits are unchanged.

Original #1592 /59b9a309 retains144tests/exporter PASS, pytest288.72s versus285s UNMET, whole311s/reserve49s. Pin#1591 /05ab15fc retains144PASS280.96s/exporter-current plus raw CANCELLED and consumed owner exception. No review reset or second exception. Live wholejob≤335seconds/reserve≥25 under360 remain binding.

## Local checks and four scoped prepush seats

Existing native pin-order/workflow-contract controls:2PASS12.55s. Four independent seats reviewed72e185f2 against35671dbb:

- Shell: hidden-shell/gate bypass test1PASS3.15s; concrete conditional writes, alternate shells, malformed run blocks and simultaneous pin/live changes refused. CLEAR.
- YAML/Actions:4native gate cases PASS13.73s; exact BASEpin equality, events, runner and read-only permissions preserved. CLEAR.
- Exporter/native:5PASS4.59s: `test_ci_checks_the_pr_head_commit`, `test_a_stale_main_fails_only_the_pr_that_made_it_stale`, `test_a_missing_source_fails_generation_and_the_check`, `test_an_exporter_change_counts_as_touching_the_registry`, `test_gate_workflows_and_hook_are_pinned_and_hidden_steps_are_scanned`.144cases collected, not another full suite. CLEAR.
- Policy/evidence:3PASS1.74s: `test_the_plan_names_the_spec_that_is_enforced`, `test_a_plan_on_the_base_stays_bound_to_its_branch_and_pr`, `test_a_change_cannot_add_its_own_capability_or_approve_its_own_spec`. PR gate PASS. CLEAR.

These are local control results, not hosted acceptance, external review or durable process proof.

## Raw source-proof dependency

At committed72e185f2, producer succeeded but trusted old verifier refused `object exceeds remaining input-byte allowance` after8001658chargedbytes. This is not PASS or waived. Original5s/8388608bytes/20000entries caps stay fixed. #1597 separately repairs redundant historical reads and must pass normal current-head checks before trusted final proof refresh here.

Final exact source proof, actual MAIN/proposed no-new audits, hosted timing and all required checks plus clean current-head CODE/security remain pending actual receipts. No main activation or production deployment is claimed.
