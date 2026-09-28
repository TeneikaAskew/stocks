# Plan template

File: `docs/superpowers/plans/YYYY-MM-DD-<feat-id-lowercase>-<slug>.md`

```markdown
---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-09-28-feat-signal-001-fire-parity.md
branch: feature/feat-signal-001-fire-parity
pr: null
status: ready
---

# <Title> implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: <2 to 5 minute task>
Spec: § Design, "shared fixtures". Advances done_when[0].
- [ ] Write failing test `tests/test_signals.py::test_live_replay_parity`
- [ ] Run: `pytest tests/test_signals.py -k parity` (expect FAIL)
- [ ] Implement in `lib/signals.py`
- [ ] Run again (expect PASS)
- [ ] Commit: `fix(signals): share golden fixtures between live and replay`

## Task N: close
- [ ] Update the 02-FEATURE-CATALOG row or record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY (solyra: the catalog row's PRs column)
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py` in stocks, `node scripts/docs-audit.mjs` in solyra)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
```

Rules:
- The `branch` here must be the branch you create. The gate finds this plan by that value and reads the FEAT-ID from it, so no two plans may name the same branch.
- `status` is `ready` until the PR merges, then `done`. The gate authorizes code only while it is `ready`.
- Set `pr` once the PR is opened.
- More than ~15 tasks means the spec is too big; split the spec.
