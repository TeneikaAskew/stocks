---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-003, REQ-GOV-001]
issues: []
canvases: []
done_when:
  - "D1: in stocks and solyra, grep -c 'a whole re-cut PR' AGENTS.md and grep -c 'an approved spec does not change in place' AGENTS.md each print 0 (1 on main), and grep -c 'A spec PR is fixed' AGENTS.md prints 1 (0 on main)"
  - "D2: in both repos, grep -c 'must fail against a broken implementation' AGENTS.md prints 0 (1 on main) and grep -c 'realistic path to a user-visible' AGENTS.md prints 1 (0 on main), in the spec-PR bullet, which asks each behavior done_when item to name a test or check that fails on main and passes on the design"
  - "D3: in both repos, grep -c 'Blocking threshold: P1.' AGENTS.md prints 1, under a '### What blocks the merge' heading, and grep -c 'may get a reply instead of a' CLAUDE.md prints 1, in Rule 2.5's merge-gate item 2 (both 0 on main)"
  - "D4: in both repos, grep -c 'then split, re-cut, or discard' CLAUDE.md prints 0 (1 on main) and grep -c 'If no finding that blocks the merge remains' .claude/skills/product-delivery/SKILL.md prints 1 (0 on main); in stocks, grep -c 'needs neither: its reply is enough' CLAUDE.md prints 1 (0 on main)"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on each implementation PR head, the two repos' '## Review guidelines' sections differ only in the Rule 3.7 / Rule 4 line, and each repo's FEAT-CICD-001 catalog entry shows a current Status and Last reviewed and records the PR"
status: approved
supersedes: null
---

# Bound the review loop: fix spec PRs in place, block only on real defects

## Problem

One change runs to six PRs, each a new PR whose first review is a new "complete" one that finds
more: solyra's verify-email spec (#231, #232, #233, #235, #237, #239, 2026-10-10 22:46 to
2026-10-11 00:25 UTC) and stocks' review guidelines (spec #1367, #1376, #1377; change #1380, #1387,
#1398). On 2026-10-12 stocks#1424, the third PR for one spec (after #1379, #1386), drew four new P2s:
three are a broken implementation that still passes (r4251439854, r4251439866, r4251439868), the
fourth widens a defect class (r4251439859).

The drivers are in AGENTS.md `## Review guidelines`, byte-identical in both repos except the
no-silent-fallbacks rule number (3.7 in stocks, 4 in solyra). Lines are stocks / solyra:

1. L16-19 / L35-38: "an approved spec does not change in place" and "on a spec PR a whole re-cut
   PR". Since 2026-10-11 the gate freezes a spec only once `main` holds it (`frozen_since_main`,
   stocks#1375, solyra fe3b872); #239 still cited the older freeze.
2. L32-35 / L51-54: "each `done_when` item that describes behavior must fail against a broken
   implementation", a set with no bound.
3. L24-27 / L43-46: "one finding per defect class listing each location", searched for every
   instance, which widens every fix.
4. CLAUDE.md line 10 and the product-delivery skill's Phase 4 (line 62) then send any second-round
   finding, whatever its severity, to split, re-cut or discard.

## Non-goals

- Driver 3 is REQ-GOV-003's wording; changing it needs a requirements PR. D3 bounds its cost.
- No gate change (D1). REQ-GOV-001 (no unresolved thread at merge) and REQ-GOV-003 are unchanged.
- `.claude/commands/resolve-issue.md` step 5 (both repos) and stocks' `.github/pull_request_template.md`
  L128-133 also restate the cap. CLAUDE.md line 10 governs where they differ; an issue aligns them.

## Approaches considered

More rounds keep the unbounded bar; harder pre-review failed (#1424 had three, r3b to r3d, and still
drew four P2s). Chosen: bound what blocks, and fix unmerged specs in place (D1 to D4).

## Design

Each decision stands alone (striking one strikes its section, done_when item and edits); text is
the same in both repos unless noted.

### D1. Fix in place
AGENTS.md, "The first review is the complete one", stocks L16-19, solyra L35-38. Before:
> A reviewer's first review of a pull request is the complete one. A pull request gets at most two
> review rounds (CLAUDE.md, "Review cap"), an approved spec does not change in place, and Codex's code
> review runs again when new commits are pushed to a pull request open for review, so a finding held
> back costs a round, and on a spec PR a whole re-cut PR. Before it posts:

After:
> A reviewer's first review of a pull request is the complete one. A pull request gets at most two
> review rounds (CLAUDE.md, "Review cap"), and Codex's code review runs again when new commits are
> pushed to a pull request open for review, so a finding held back costs a round. A spec PR is fixed
> in place by a push, like any other pull request; once `main` holds a spec, it changes only through a
> new spec that supersedes it. Before it posts:

Gate: no change. On main (stocks 73457c38, solyra 5fbdbb9), a scratch `docs/spec-` branch whose
second commit edits the approved spec its first added passes `--commit` and `--pr origin/main`; the
gate before stocks#1375 / solyra fe3b872 refuses it, and today's refuses editing a spec `main` holds.

### D2. A bounded spec-review bar
AGENTS.md spec-PR bullet, stocks L32-35, solyra L51-54. Before:
> - A spec PR is reviewed against the code it will change: the reviewer opens each file the spec names
>   and checks that every `done_when` item can be met, and each `done_when` item that describes
>   behavior must fail against a broken implementation. Items that record delivery (the gate, the docs
>   audit, the catalog row) are only checked for being met.

After:
> - A spec PR is reviewed against the code it will change: the reviewer opens each file the spec names
>   and checks that every `done_when` item can be met, and that each `done_when` item that describes
>   behavior names a test or check that fails on `main` (or on the prior state the item names) and
>   passes on the design. A broken implementation that would still pass may be posted as a finding;
>   whatever its severity, it blocks the merge only when it shows a realistic path to a user-visible
>   defect, and otherwise gets a reply. Items that record delivery (the gate, the docs audit, the
>   catalog row) are only checked for being met.

### D3. A blocking threshold
A new AGENTS.md subsection before "### Browser proof" (stocks L48, solyra L67). If the owner wants
P2 to block too, one word changes: "Blocking threshold: P1." becomes "P2.".
> ### What blocks the merge
>
> Blocking threshold: P1. Severity runs from P0, the most severe, to P3, as Codex's badges show; a
> finding without a badge states its severity, and only the owner changes a reviewer's severity. A
> finding at or above the threshold blocks the merge until it is fixed. A finding below it gets a
> reply on its thread, and an issue the reply links when it is real; the thread is then resolved and
> the pull request merges without the fix.

CLAUDE.md Rule 2.5 merge gate, item 2 (stocks L180-181; solyra L124-125, which reads "isn't" for
"is not"), gains two lines; before is the first two lines below. After:
> 2. Every thread either resolved, or replied to with why it is not being
>    actioned. Zero unresolved threads is the bar. A finding below the blocking
>    threshold (AGENTS.md `## Review guidelines`) may get a reply instead of a
>    fix, linking an issue when it is real; its thread is then resolved.

### D4. Exit rule after round 2
CLAUDE.md line 10, both repos. Before:
> Review cap on every PR: two rounds, then split, re-cut, or discard. Never a third round, never a stacked follow-up.

After:
> Review cap on every PR: two rounds. After the second, a PR with no finding that blocks the merge (AGENTS.md `## Review guidelines`) merges; one with such a finding is split, re-cut, or discarded. Never a third round, never a stacked follow-up.

Product-delivery SKILL.md line 62 (Phase 4), both repos. Before:
> - Review cap: TWO rounds. After the second round of review comments, do not keep fixing in place. Invoke `superpowers:finishing-a-development-branch` and present: split into smaller PRs, re-cut from the spec, or discard. A PR that is not mergeable after two rounds is a spec problem, not a code problem.

After:
> - Review cap: TWO rounds. After the second round of review comments, do not keep fixing in place. If no finding that blocks the merge remains (AGENTS.md `## Review guidelines`), reply to the rest and merge. If one remains, invoke `superpowers:finishing-a-development-branch` and present: split into smaller PRs, re-cut from the spec, or discard. A PR with a blocking finding after two rounds is a spec problem, not a code problem.

stocks CLAUDE.md Rule 2.5, L340-342, gains one sentence; before is the first three lines below
(solyra's Rule 2.5 does not restate the cap). After:
> happens only before the PR's second review round has started; once it has
> started, nothing is pushed or requested, and a PR that then needs either is
> split, re-cut or discarded (the review cap). A finding that does not block
> the merge (AGENTS.md `## Review guidelines`) needs neither: its reply is enough.

"Blocks the merge" comes from D3, narrowed by D2. If D3 is struck, it means a defect the author
confirms (Rule 2.5) that D2 does not excuse; if D2 and D3 are both struck, strike D4 too.

## Delivery and landing

Per repo, this spec merges first on `docs/spec-feat-cicd-001-bounded-review`, then the rule text on
`feature/feat-cicd-001-bounded-review` with a `status: ready` plan: AGENTS.md, CLAUDE.md and `.claude/`
are process files that only a FEAT-CICD-001 `feature/` or `fix/` branch may change. None is a gate
file, so no red-team pass. Capacity: n/a, no workload.

Approved by the owner in chat on 2026-10-14 (D1, D2, D3 and D4); the same file goes into both repos.
Today's rules would loop this change's own four PRs (spec and implementation, per repo), so each
merges after one Codex round with P2 and P3 findings replied to (an issue when real), and a P0 or P1
fixed in one push, which is the second round. That applies D1, D3 and D4 one PR early.

## Risks

- A real P2 merges unfixed. Its issue keeps it visible; the owner can move the threshold to P2.
- Only the owner changes a reviewer's severity, so an author cannot downgrade a finding to merge.
- "A realistic path to a user-visible defect" is a judgement: a wrong value a page, report or job
  output shows counts; a dispute goes to the owner.
