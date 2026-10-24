## Delivery gate
Read `.claude/skills/product-delivery/SKILL.md` and follow it for any code change. The same gate
(`scripts/gate/spec_gate.py`) runs on every commit and every PR regardless of which agent authored it.
A branch that changes code must carry the FEAT-ID: `feature/<feat-id>-<slug>` or `fix/<feat-id>-<slug>`.
The only other shapes are `docs/<slug>` (documentation only), `chore/<slug>` (dependency fields of manifests,
lockfiles and the gate's own files), `spike/<slug>` (local commits, never a PR) and `bot/superpowers-*`
(the vendored skills), as Phase 0 of the product-delivery skill sets out.

## Review guidelines

For every reviewer of a pull request in this repository: Codex, which reads this section; Claude,
which CLAUDE.md Rule 2.5 sends here; and a person. stocks and solyra carry the same guidelines.

### The first review is the complete one

Each reviewer's first review of the change lineage is complete. A replacement or split PR
inherits its reviewed scope, findings and spent effort; a new reviewer still reads the entire
scope. Reserve judgment work under “Review budget and finding identity” below before starting.
A spec PR is fixed in place within that allowance; once `main` holds an approved spec, a
changed contract requires a new superseding spec. Before posting, the reviewer:

- It reads every changed file in full, generated files included, and the direct callers and callees
  of what changed, and where a changed file's generator runs in the reviewer's environment it re-runs
  it and compares.
- It posts, against the revision it reviews, every finding it can raise on a defect the pull request
  introduces or makes worse, at every severity, with one finding per defect class listing each
  location. When a finding is one instance of a class, it searches for every instance before it
  posts the class.
- It checks the edges a change creates (errors and rejections, late or out-of-order responses,
  signed-out and other-account states, empty and null data, and the docs, tests and generated files
  that cite what changed). Empty and null data are judged by this repository's no-silent-fallbacks
  rule, CLAUDE.md Rule 3.7.
- A spec PR is reviewed against the code it will change: the reviewer opens each file the spec names
  and checks that every `done_when` item can be met, and that each `done_when` item that describes
  behavior names a test or check that fails on `main` (or on the prior state the item names) and
  passes on the design. A broken implementation that would still pass is posted as a finding. It
  blocks the merge when it shows a realistic path to a user-visible defect. Other counterexamples
  get a reply unless an independent blocking condition below applies; P0/P1 always block. Items that record delivery (the gate, the docs audit, the
  catalog row) are only checked for being met.

### Later reviews

A later review by the same reviewer verifies earlier findings and examines new semantics and
affected dependencies, rather than restarting a complete review of unchanged material. It still
reports genuine late defects, classified under CLAUDE.md Rule 2.5 against the immutable first
review SHA for that review type: missed, new (introducing SHA), or uncounted. Moving lines does
not create a new finding. Retain every location and original thread in the finding record.

Harmless punctuation, wording or citation corrections that change no decision, acceptance
condition or executable meaning require neither renewed spec approval nor a new semantic review
cycle by themselves. An asterisk changing an executable glob, MUST becoming MAY, or misleading
documentation about available behavior is substantive, not cosmetic. Substantive changes to an
approved unmerged spec require renewed owner approval. Actual provider runs still consume the
allowance even after cosmetic pushes; required current-head review is never waived.

### Problems this pull request did not cause

A problem the pull request neither introduces nor makes worse is not posted as a finding (a reviewer
who can open an issue may open one), since every thread holds the merge (REQ-GOV-001).

### What blocks the merge

Apply these rules in order; disposition never grants merge authority:

1. Unmet required acceptance, required current-head review/checks, unresolved required
   conversations, security, data integrity, capacity and no-silent-fallback protections block
   regardless of the finding's badge. A realistic user-visible spec counterexample also blocks.
2. P0 and P1 findings always block until fixed and verified. Map CRITICAL=P0, HIGH=P1,
   MEDIUM=P2 and LOW=P3 while retaining the original label. Missing or conflicting severities
   go to the owner for adjudication; never silently relabel or downgrade them.
3. Other P2/P3 findings receive an explicit thread reply and, for a real defect, a linked issue,
   then resolution. A cosmetic preference needs an explanation, not an invented defect issue.
   A P2/P3-only second round satisfying all mandatory conditions does not force a fix or re-cut.
4. Only the owner changes a reviewer's severity. Exhaustion never auto-passes a real defect.
   Normal merge authorization, branch protections and all required evidence still apply.

### Review budget and finding identity

The designated writer maintains one ledger rooted in the original change/spec, listing all
predecessor, replacement and split PRs. Record immutable head/base/spec/policy identities,
reviewer and review type, trigger, reservation/run/completion/cancellation IDs and receipts,
original severity, stable finding IDs, all thread URLs/locations, verification and disposition,
owner decisions, spent effort and remaining aggregate/external allowances. A finding ID follows
the same underlying defect across moved lines and replacement PRs. No stage, branch or PR-number
change resets history. Missing history is unknown, not zero; ask the owner to adjudicate before
asserting an available balance, including when adopting this policy for legacy work.

The default maximum is four coordinated judgment passes per lineage, including local pre-push,
red-team and external judgment, with at most two external code-review rounds. Reserve a pass
before work starts. A declared parallel cohort on one immutable head is one aggregate pass;
record each reviewer/run separately. A new head, new cohort, repeated attempt or cancelled
reservation consumes a pass; partial completion does not refund it. Actual external code runs
also consume the external limit, even when automatically triggered. Required security review
is not omitted. Tests, generators and deterministic gates alone are not judgment passes.

Replacement and split PRs inherit all findings and share the same remaining balance, rather
than each receiving a new allowance. Before a fix/push/review that would require further
judgment, check the remaining allowance, including provider-triggered runs. At exhaustion stop
autonomous fixes, pushes and review requests; report unresolved findings and exact history to
the owner. The owner may explicitly extend a bounded scope, rescope through approved specs or
stop. An aggregate extension does not extend the external-round limit unless explicitly stated.
Do not automatically re-cut, silently add a pass, waive mandatory checks or merge a blocker.

### Generated evidence and one writer

Use the existing trusted renderer/source-snapshot protocol and its resource limits; this is
not a new generated-inventory allowance. Record committed source/base/policy hashes, exact
invocation and input identities, and SHA-256 hashes of output bytes. Two refreshes from identical
committed inputs must match exactly; prose or executable requirement changes are not renderer
output. Refuse unexpected source, policy, path or output identities under the existing verifier.

One named writer exclusively publishes shared files and branch updates. Other participants read
or produce writer-private outputs. Before publication, compare the expected branch head and
shared-output hashes; on mismatch refuse to overwrite and reconcile with the owner. Use normal
non-force pushes. Hash prechecks are not atomic compare-and-swap or a lock: if another writer
cannot be excluded, stop publication and isolate the work. Handoff requires the old writer to
be quiescent, an owner acknowledgment and recorded transfer before the new writer publishes.

### Browser proof

A change a user can see in the site carries Playwright evidence from a run that exercises the
changed code: solyra's hermetic suite for a solyra change; for a stocks change, an API test of the
changed response in the PR, while runs against the deployed site before the merge and once staging
has deployed it are close-out steps the owner posts on the PR, not boxes the PR ticks.

- solyra's hermetic suite (`npm run e2e`) intercepts every `/api` call, so it cannot prove a stocks
  change. The API test in the stocks PR is that proof.
- The deployed-site runs are the owner's: staging's trigger deploys from `main`, deploying a stocks
  branch with `platform/deploy.sh` would put unreviewed code behind the live site, and the deployed
  site's sign-in is interactive (`npm run e2e:cloud:auth` runs headed).
- Each run carries screenshots of the state each run shows, which the test saves with
  `page.screenshot` into its output directory under `test-results/` (`testInfo.outputPath(...)`),
  where the e2e workflow's `playwright-report` artifact keeps them 7 days. The test takes them itself
  because `npm run e2e` runs with Playwright's screenshot option off; solyra's e2e workflow uploads
  `test-results/` in that artifact.
- The screenshots are described state by state in a PR comment and kept in the e2e run's
  `playwright-report` artifact (saved under `test-results/`, kept 7 days) or sent to the owner, since
  images cannot be attached to a PR from a Claude Code session.

The reviewer asks for the hermetic run or the API test when the PR lacks it.
