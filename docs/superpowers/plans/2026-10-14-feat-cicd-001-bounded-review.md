---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-14-feat-cicd-001-bounded-review.md
branch: feature/feat-cicd-001-bounded-review
pr: 1512
status: done
---

# Bound the review loop: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

The rule text is documentation the gate does not read, so each "test" is the spec's own grep count:
run it on the branch before the edit (it prints main's value), apply the spec's After text, run it
again. The same plan goes into both repos; only the stocks-only sentence in Task 3 differs.

## Task 1: D1 and D2 in AGENTS.md
Spec: § D1 and § D2. Advances done_when[0] and done_when[1].
- [ ] Run `grep -c 'a whole re-cut PR' AGENTS.md`, `grep -c 'an approved spec does not change in place' AGENTS.md`,
      `grep -c 'A spec PR is fixed' AGENTS.md`, `grep -c 'must fail against a broken implementation' AGENTS.md`
      and `grep -c 'realistic path to a user-visible' AGENTS.md` (expect 1, 1, 0, 1, 0)
- [ ] Replace the "first review is the complete one" paragraph and the spec-PR bullet with the spec's After text
- [ ] Run the same greps (expect 0, 0, 1, 0, 1)
- [ ] Commit: `docs(agents): fix spec PRs in place and bound the spec-review bar`

## Task 2: D3 in AGENTS.md and CLAUDE.md
Spec: § D3. Advances done_when[2].
- [ ] Run `grep -c 'Blocking threshold: P1.' AGENTS.md`, `grep -c 'which blocks only as the spec-PR rule' AGENTS.md`
      and `grep -c 'may get a reply instead of a' CLAUDE.md` (expect 0, 0, 0)
- [ ] Add `### What blocks the merge` before `### Browser proof` in AGENTS.md, and the two lines to CLAUDE.md
      Rule 2.5's merge-gate item 2, as the spec's After text gives them
- [ ] Run the same greps (expect 1, 1, 1), and check the new subsection sits directly before `### Browser proof`
- [ ] Commit: `docs(agents): block the merge on P0 and P1 findings only`

## Task 3: D4 in CLAUDE.md and the product-delivery skill
Spec: § D4. Advances done_when[3].
- [ ] Run `grep -c 'then split, re-cut, or discard' CLAUDE.md` and
      `grep -c 'If no finding that blocks the merge remains' .claude/skills/product-delivery/SKILL.md` (expect 1, 0);
      in stocks also `grep -c 'needs neither: its reply is enough' CLAUDE.md` (expect 0)
- [ ] Replace CLAUDE.md line 10 and SKILL.md's Phase 4 review-cap bullet with the spec's After text; in stocks,
      add the sentence to Rule 2.5's paragraph that ends "(the review cap)."
- [ ] Run the same greps (expect 0, 1; stocks 1)
- [ ] Commit: `docs(claude): merge after round 2 when nothing blocks`

## Task 4: close
Spec: the `done_when` frontmatter. Closes done_when[4].
- [ ] Check each of the spec's After blocks is in its file verbatim (the `> ` quote prefix removed, solyra's
      "isn't" where the spec says so) and each Before block is gone; the greps count markers only, so this is
      what shows no clause was dropped (Codex, solyra#280 r4274729914). The PR body shows the output
- [ ] `diff` the two repos' `## Review guidelines` sections of AGENTS.md: they differ only in the Rule 3.7 / Rule 4 line
- [ ] Confirm the FEAT-CICD-001 Status still holds and update Last reviewed (stocks: its record in 02-FEATURE-CATALOG;
      solyra: its row)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY under FEAT-CICD-001 (solyra: the catalog row's PRs column)
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py` in stocks,
      `node scripts/docs-audit.mjs` in solyra)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
