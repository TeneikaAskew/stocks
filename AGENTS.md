## Delivery gate
Read `.claude/skills/product-delivery/SKILL.md` and follow it for any code change. The same gate
(`scripts/gate/spec_gate.py`) runs on every commit and every PR regardless of which agent authored it.
A branch that changes code must carry the FEAT-ID: `feature/<feat-id>-<slug>` or `fix/<feat-id>-<slug>`.
The only other shapes are `docs/<slug>` (documentation only), `chore/<slug>` (dependency fields of manifests,
lockfiles and the gate's own files), `spike/<slug>` (local commits, never a PR) and `bot/superpowers-*`
(the vendored skills), as Phase 0 of the product-delivery skill sets out.

## Review guidelines
For every reviewer of a pull request here: Codex, Claude, or a person.

**The first review is the complete one.** A PR gets two review rounds, then it is split, re-cut or
discarded, and an approved spec cannot be edited in place, so each round of new findings on a spec
PR means a new PR. A finding saved for a later round costs a whole cycle. Before posting the first
review:
- Read every changed file in full, not only the changed hunks, and the callers and callees of
  anything the diff changes.
- Report every finding you have, at every severity, in this one review. Do not stop after the first
  few, and do not hold lower-severity ones back for a later round.
- When a finding is one instance of a class (a race when the signed-in account changes, a missing
  uid in a cache key, an unhandled rejected promise), search the diff and the code it touches for
  every other instance and report the class once, listing each location.
- Check the edges a change creates, not only the path it adds: errors and rejections, responses
  that arrive late or out of order, signed-out and other-account states, empty and null data (no
  silent fallbacks, CLAUDE.md Rule 3.7), and the docs, tests and generated files that cite what changed.
- For a spec PR (`docs/superpowers/specs/`), review the design against the code it will change:
  open each file the spec names and check that every `done_when` item can be met, and that its test
  would fail against a broken implementation.

**Later rounds review the new commits.** Check that each earlier finding is fixed, then review what
changed since. A real problem in code the first review already saw is still reported, marked as
missed in the first round.

**Pre-existing problems are issues, not blockers.** A problem this PR did not introduce and does
not make worse is reported as a new issue, or in a comment labelled pre-existing, rather than as a
finding the PR must fix before it merges.
