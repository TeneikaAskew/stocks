---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-31-feat-cicd-001-retry-split-substitution.md
branch: feature/feat-cicd-001-retry-split-render
pr: 1835
status: ready
---

# Render the declared retry split as a trusted substitution: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** `scripts/maintenance/doc_inventory.py` renders 05-a's declared job retry split (§6's list and §11's two
shapes) from the same declared-job parse `check_generated_docs.gate_derived_numbers` counts, so a change to a declared
retry (the news retry change, stocks#1671; the EW evaluator retirement, first cut as stocks#1658 and re-cut from main as stocks#1834) passes both the PR-mode render
check and `tests/scripts/test_check_generated_docs.py`.

**Spec:** `docs/superpowers/specs/2026-10-31-feat-cicd-001-retry-split-substitution.md` (approved; admitted on main by #1756).

**Requirement:** REQ-GOV-004 as amended by #1655.

## Task 1: the substitution
Spec: § Design, § File ownership. Advances done_when[0].
- [ ] Add `RETRY_SPLIT` (three literal shapes) and `render_retry_split` beside the existing substitutions; apply it in
      `insert_blocks(counts=True)` only to `docs/product/infrastructure/05-a-ARCHITECTURE.md` by its exact repository path.
- [ ] Counts from `Counter(job["max_retries"])` over `repo["jobs"]` (defaults included), the total from `len(repo["jobs"])`;
      a count keeps its token's form (a `WORD_NUMBERS` word up to twelve, digits above); raise on a repeated shape, on
      declared retry values that are not exactly the three the §6 list names, and on list counts that miss the total.
- [ ] `tests/fixtures/retry_split/`: the base `deploy.sh` (blob 6eed94ca) and the news (f3206696) and EW (9b076797)
      line-edit sets; `tests/scripts/test_doc_inventory.py` rebuilds the three blob ids and proves every render case
      the first item names.

## Task 2: the docs-check tests
Spec: § Problem, § Design. Advances done_when[1].
- [ ] Adapt `test_the_retry_split_must_match_deploy_sh` and `test_a_spelled_out_retry_count_is_validated` to derive their
      wrong counts from the §6 list as the document states it (56, 27 and "two" on main).
- [ ] Add one off-by-one case per owned per-flag count (five) and a non-owned phrasing case; `check_generated_docs.py`
      is not changed.
- [ ] Record, for the base and each fixture, the ten named suites passing on a clone carrying that fixture's
      `gcp/deploy.sh` and its `--insert`-rendered documents.

## Task 3: the gate tests
Spec: § Design. Advances done_when[2].
- [ ] `tests/scripts/test_spec_gate.py` (additions only): a retry fixture tree; the computed head is accepted; each
      refusal the third item names is refused citing REQ-GOV-004; the 05-c, 05-e and fourth-phrasing cases also run
      seeded with stale merge-base text, each beside its accepted control.

## Task 4: evidence and close-out
Spec: § Capacity and cost, § Delivery. Advances done_when[3], done_when[4], done_when[5].
- [ ] Every new assertion shown failing against origin/main's `doc_inventory.py`.
- [ ] Four-seat pre-push red team (shell; YAML/Actions; exporter and policy documents; diff and byte parsing with the
      render check), each finding proven by running the gate on a snippet; last pass empty; then one push.
- [ ] Hosted registry-check job on the exact head within 335 seconds; BASE suite, renderer measurement unchanged.
- [ ] Own (FEAT-CICD-001, SHARED-01) implementation-source note and sidecar; catalog Status and Last reviewed;
      12-PR lineage; docs audit clean against main; `python3 scripts/gate/spec_gate.py --pr origin/main`.
