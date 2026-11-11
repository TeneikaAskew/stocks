---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: []
canvases: []
done_when:
  - "scripts/maintenance/doc_inventory.py defines RELATION_TOTAL, matching only a run of digits that follows the literal word 'declares ' (optionally opened by '**' and closed by ' relations**') and is followed directly by a declared breakdown that RELATION_BREAKDOWN matches; insert_blocks(counts=True) rewrites only those digits, to the sum of the same table, materialized-view and view counts the breakdown renders, and restore_blocks (counts=False) leaves them as written"
  - "tests/scripts/test_check_generated_docs.py adds: a render over an inventory with two more declared tables rewrites both 05-a shapes, 'declares **N relations** (...)' and 'that file declares N (...)', so the total equals the parts; a 'declares N relations' not followed by a breakdown is left unchanged; the restore path leaves a wrong total for the gate to report; the first fails on origin/main and all pass on the head; no existing assertion is removed or loosened and scripts/maintenance/check_generated_docs.py is not changed"
  - "On the PR head, scripts/maintenance/doc_inventory.py --insert over the committed 05-a, 05-c and 05-e changes no byte, tests/scripts/test_check_generated_docs.py passes in full, and python3 tests/scripts/measure_inventory_render.py --ref HEAD --max-rss-mib 512 --max-seconds 60 passes"
  - "With this change on main, the FEAT-STRAT-001 per-ticker parameters branch (two tables added to gcp/schema.sql, 05-a stating 74 relations, 71 tables, 2 materialized views, 1 view) passes the PR-mode render check of python3 scripts/gate/spec_gate.py --pr origin/main and tests/scripts/test_check_generated_docs.py, and the implementation PR records both runs"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head; the FEAT-CICD-001 catalog record shows a current Last reviewed and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Render the declared relation total with its breakdown

## Problem

05-a states the schema arithmetic twice: §5's "`gcp/schema.sql` declares **72 relations** (69 tables, 2 materialized views, 1 view)" and §3's table cell "that file declares 72 (69 tables, 2 materialized views, 1 view)". `check_generated_docs.gate_derived_numbers` requires both the total and each part to match `gcp/schema.sql`. The PR-mode render check accepts a feature branch's 05-a only as main's `insert_blocks(counts=True)` renders it from merge-base prose, and that function renders `RELATION_BREAKDOWN` (the parenthetical) but not the total in front of it.

So any change that adds or removes a declared relation fails one of the two checks whichever way the total is left. Observed on the FEAT-STRAT-001 per-ticker parameters branch (stocks#1766, which adds `level_param_policy` and `ticker_level_params`): with 74 the gate reports "changes line 109 outside its inventory blocks", because main's render gives "72 (71 tables, 2 materialized views, 1 view)"; with 72 the docs test reports the total contradicts its parts. No table has been added to `gcp/schema.sql` since the render check landed (the total last moved in #1144, 2026-09-27), which is why the gap has not shown before. This is the same contradiction class the retry-split spec (`2026-10-31-feat-cicd-001-retry-split-substitution.md`) resolves for the job split.

## Non-goals

No change to the render-check comparison, `scripts/gate/spec_gate.py`, the hook, the gate workflows, their pinned copies, `scripts/maintenance/check_generated_docs.py` or the committed snapshot; no removed or loosened assertion; no new document, marker or live input; no generated-document change in this PR; no rendering of totals that are not written directly before a declared breakdown (for example the live "95 relations" figure, which comes from the snapshot). This spec does not supersede the retry-split spec and does not touch `RETRY_SPLIT`.

## Approaches considered

1. Hand-edit the total in the feature PR: refused by REQ-GOV-004, and rightly, since a typed number is what the derived check exists to catch.
2. Drop the total from the prose: hides a checked fact instead of rendering it.
3. Render the total from the same three counts the breakdown already renders. Chosen: the number is the sum of figures the renderer already owns, the outside-prose comparison stays fail-closed, and only those digits can move.

## Design

Add `RELATION_TOTAL` beside `RELATION_BREAKDOWN` in `scripts/maintenance/doc_inventory.py`:

```
RELATION_TOTAL = re.compile(
    r"(declares (?:\*\*)?)(\d+)((?: relations\*\*)? )(?=\(\d+ tables?, \d+ materialized views?, \d+ views?\))")
```

In `insert_blocks`, inside the existing `if counts:` branch that renders the breakdown, after it: replace group 2 with `t + m + v`, where `t`, `m` and `v` are the same `len(repo["tables"])`, `len(repo["materialized_views"])` and `len(repo["views"])` the breakdown uses. Every other byte is kept. The lookahead ties the total to a breakdown in the same position, so a total written anywhere else, or a breakdown with no total, is not touched. `restore_blocks` keeps `counts=False`, so a model that types a wrong total is still reported by the gate rather than corrected.

Existing substitutions become the renderer's `RUNTIME_RELATION_COUNT`, `RELATION_BREAKDOWN`, `RELATION_TOTAL`, `ASOF_LABELS`, and `RETRY_SPLIT` once that spec's implementation lands; the two changes touch different lines of `insert_blocks` and whichever lands second merges the other.

The gate needs no code change: its RENDER_MODE already runs main's `insert_blocks(counts=True)` over merge-base prose. Once this lands, a branch that changes the declared relation set carries the exact computed total and breakdown, and nothing else outside the blocks may differ.

## File ownership

`scripts/maintenance/doc_inventory.py` (RELATION_TOTAL and its one application only); `tests/scripts/test_check_generated_docs.py` (additions only); the FEAT-CICD-001 catalog and traceability records; one ready plan. `.claude/skills/product-delivery/SKILL.md` is not changed: its allowance already reads "existing fixed renderer-owned count/as-of substitutions", and RELATION_TOTAL is such a substitution once on main. The REQ-GOV-004 amendment that names the declared relation total is its own requirement-only PR, merged before this spec.

## Capacity and cost

One extra compiled-regex substitution over one in-memory document inside the existing single render; no extra process, file read, git call or snapshot field. The 60-second and 512 MiB renderer measurement is re-run unchanged.

## Risks

A broad pattern could rewrite an unrelated "declares N" figure: the lookahead requires the breakdown directly after the total, and the second done_when item's negative case holds that. A silent correction of a model's wrong total: `restore_blocks` keeps `counts=False`, held by the restore-path test. A total the renderer owns but the check reads in a different shape would re-create the contradiction: the fourth done_when item requires the real FEAT-STRAT-001 branch to pass both checks.

## Delivery

Three stages, as for the retry split: (1) the requirement-only REQ-GOV-004 change; (2) this spec alone; (3) one `fix/feat-cicd-001-declared-relation-total` implementation PR carrying its plan. The implementation is already written and tested locally (new test fails on main, passes with the change; `tests/scripts/test_check_generated_docs.py` 142 passed; `--insert` over the committed 05-a reports unchanged), and opens when this spec is on main.
