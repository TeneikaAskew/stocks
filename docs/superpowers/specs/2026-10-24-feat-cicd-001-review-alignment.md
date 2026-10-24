---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-003, REQ-GOV-004]
issues: [1510, 1511]
canvases: []
done_when:
  - "A1: the policy-surface comparison and scenarios C1-C5 give one blocking and disposition decision in stocks and Solyra without changing reviewer severity"
  - "A2: scenarios C6-C8 preserve finding identity and aggregate review effort across pre-push passes, replacement PRs and interrupted reviews, stopping for owner adjudication at the limit"
  - "A3: scenarios C9-C11 preserve substantive spec reapproval, exact generated evidence and single-writer collision protection with accepted and refused controls"
  - "A4: each repository passes its unchanged base spec gate, affected regression suites and full branch-versus-main documentation audit with no new findings, and records its own FEAT-CICD-001 implementation PR"
  - "A5: the acceptance record contains immutable revisions, actual decisions and limitations for C1-C11, and a separately approved real-PR observation protocol with no claim of durability before its exit criteria pass"
status: draft
supersedes: null
---

# Align bounded agent review and owner escalation

## Status and authority

This is a proposal for owner review, not active policy or an approved implementation
plan. The October 24 authorization permits this draft. It does not approve these
proposed decisions, any rollout, or a merge. Existing instructions govern until
separately approved changes land. No implementation acceptance box is complete merely
because this document exists. This additive spec does not supersede the entire
October 14 bounded-review spec; its existing historical approval remains intact.

Use product-delivery Phase 2 to approve this written contract first. Only then write
and review the implementation plan, land the approved spec, and open the independent
FEAT-CICD-001 implementation branch under the ordinary gate. A matching Solyra spec
and approval are required there; this stocks file grants no cross-repository authority.

## Problem and inspected baseline

Stocks main inspected: `2aac64c0e8b7a10a1e891a7caa78814575960af9`.
Solyra main inspected: `f0aaf422fcfaf0b2bcadc129f8454c4714318224`.
The workspace `.agents` directory is empty; stocks has no `.agents/skills`, and the
Solyra `.agents` path is absent. The applicable skills are the repositories'
`.claude/skills/product-delivery`, `brainstorming`, and `writing-plans` instructions
and delivery templates. No active matching alignment PR was found in either repo.
Recheck main, relevant instructions and open PRs before implementation.

- [#1512](https://github.com/TeneikaAskew/stocks/pull/1512) merged October 18
  (`e400614d`): bounded-review policy text, not a mechanical review controller.
  AGENTS.md permits lower-severity disposition, but stocks
  `.claude/commands/resolve-issue.md:4216-4222` still forces re-cut for any
  second-round finding. Solyra's command has the same conflict at lines 859-863.
  [Author acknowledgment](https://github.com/TeneikaAskew/stocks/pull/1512#discussion_r4275239327)
  and [#1510](https://github.com/TeneikaAskew/stocks/issues/1510) track the gap.
- CLAUDE.md:10-14 and product-delivery Phase 4 combine a per-PR two-round cap
  with repeated pre-push red-team passes until empty. Replacement PRs and local
  passes currently escape the aggregate budget.
- [#1511](https://github.com/TeneikaAskew/stocks/issues/1511) is partially resolved:
  product-delivery Phase 2 already exempts harmless wording from renewed approval.
  Remaining alignment includes severity vocabulary, the spec-counterexample
  exception, required acceptance and performance/no-fallback precedence, and
  contradictory downstream wording. Do not relabel these as cosmetic-only issues.
- [#1538](https://github.com/TeneikaAskew/stocks/pull/1538) merged October 23
  (`a5749d4c`): exact generated-inventory allowance already exists. Reuse it.
- The #1566 to #1575 STRAT replacement carried real correctness findings. It is
  evidence of lineage cost, not evidence that all second-round findings are cosmetic.

Capability: `FEAT-CICD-001 | CI / testing | Build, test, deploy automation`.
Requirements: REQ-GOV-001 (resolved review conversations), REQ-GOV-003 (complete
first review and subsequent finding classification), REQ-GOV-004 (exact renderer
output). No registered canvas depicts this workflow.

## Non-goals

No documentation architecture migration, duplicate generated-inventory allowance,
STRAT/options/fixture implementation, changes to #1564/#1565/#1569/#1573/#1575,
production writes, deployment, merge, branch-protection changes, issue closure,
new GitHub bot/controller, or automatic semantic classification. No weakening of
security, financial/data integrity, no-silent-fallbacks, capacity or acceptance rules.
No edits to another owner's branch, shared plan, evidence or incident drafts.

## Approaches considered

1. Correct only the stale command: small, but leaves unbounded pre-push/re-cut work.
2. Align instructions and use an explicit owner-reviewed lineage ledger and
   scenario protocol: recommended; bounded scope, inspectable decisions, no false
   claim that prose provides enforcement.
3. Build an automated controller: potentially stronger enforcement, but needs its
   own authentication, concurrency and failure-mode design and approved spec.
   Excluded here. Text/fixture checks cannot substitute for that controller.

## Design

### One blocking and disposition rule

Apply the following precedence everywhere, including the spec counterexample rule:

1. Unmet required acceptance, failed required checks, missing current-head review,
   unresolved required conversations, security or data-integrity defects, forbidden
   fallbacks and mandatory capacity/performance failures block progression regardless
   of badge. A spec counterexample showing a realistic user-visible defect blocks.
   A missing proof is not proof of correctness. Delivery checks remain required.
2. P0/P1 findings block until fixed and verified. The spec-counterexample exception
   cannot excuse a P0/P1 or a requirement in item 1. This deliberately resolves the
   current D2/D3 ambiguity and requires owner approval before taking effect.
3. Other P2/P3 findings may be dispositioned by a reasoned thread reply, linking a
   tracked issue for a real deferred defect, then resolving the thread. This is not
   automatic merge permission. All normal merge prerequisites remain necessary.
   Cosmetic preference is recorded as such without manufacturing a defect issue.
4. Ambiguous severity, disputed classification, unknown required-check status or
   disputed acceptance goes to the owner and remains pending; an agent cannot
   silently downgrade a finding. Preserve original severity and text in the record.

Proposed vocabulary mapping: CRITICAL=P0, HIGH=P1, MEDIUM=P2, LOW=P3. Preserve
reviewer account/type, original label and normalized label. An absent, conflicting
or unmapped label requires adjudication; mapping is not permission to change
severity. Only the owner may change reviewer severity with recorded rationale.

An ordinary punctuation preference neither invalidates semantic approval nor
requires another review cycle by itself. Asterisks in executable globs, operators,
requirements, examples used as commands, or changed emphasis that changes a promise
are potentially semantic. Misleading documentation is a defect, not a preference.
If a cosmetic commit nevertheless triggers an external run, record that actual
cost; do not pretend the provider did no work or waive current-head requirements.

### Complete initial review, focused verification and stable identity

The initial review reads all changed files and direct callers/callees, includes
reproducible generated-output comparison, checks boundary cases and posts all
known defect classes/locations together. Retain REQ-GOV-003 per-reviewer/type first
review identity and uncounted/missed/new classification with immutable SHAs.

Later work verifies prior fixes plus changed semantics and affected dependencies.
Newly discovered genuine defects are always reported and classified, never suppressed
by a budget. Unchanged cosmetic preferences do not restart a full review. A missed
first-review defect retains its original provenance, including across replacement PRs.

The single writer maintains a review ledger in the PR body or linked immutable
review artifact: lineage ID, root and replacement PR URLs, approved spec path/blob,
reviewed base/head, pass IDs, reviewer account/type, run URLs/status, findings,
dispositions, owner decisions and spent/remaining budget. A finding ID is assigned
once per defect class within that lineage; retain all original thread URLs and
location/commit history. Do not derive identity from mutable line numbers or prose.
Re-cut/split children inherit all spent passes and the applicable findings; the
parent remains linked. Duplicate observations append evidence, not new identities.
Uncertain duplication is owner-adjudicated without erasing either finding.

### Proposed aggregate effort limit and escalation

Owner decision proposed: four coordinated review passes per lineage, at most two
external PR code-review rounds, including pre-push review work in the total.
A pass is one declared review cohort against one immutable head with one complete
review or focused-verification objective. Parallel attack-surface reviewers belong
to one pass only if declared together before starting; record every reviewer/run.
New head, newly commissioned cohort, repeated pre-push red-team attempt or restarted
interrupted attempt consumes another pass. Reserve the pass before work starts;
a failed or cancelled pass still consumes it. Run status never invents completion.
Required security/specialist reviews cannot be omitted to conserve the budget.
Routine deterministic tests/gates are recorded but do not consume judgment passes.

The budget covers the entire lineage, not each PR or agent. Split descendants do
not each receive fresh balances. Closing, renaming, replacing, switching reviewer,
or moving from local pre-push to GitHub does not reset it. A ledger unavailable or
inconsistent with observed history causes a hold for reconciliation, not a zero.
Initial ledger seeding must include known prior review effort and mark unknowns;
legacy lineages need owner adjudication before a remaining allowance is asserted.

At the limit: stop autonomous fixes/review requests/pushes likely to initiate review.
Present unresolved findings and unmet requirements with exact head, reproductions,
remaining acceptance, budget history and options: bounded explicit extension,
rescope through approved spec, or stop. Owner chooses; no automatic re-cut or pass.
An extension records reason, exact additional aggregate pass count and scope,
and separately states whether and by how many rounds the external limit increases.
Without that explicit external allowance the two-external-round limit still holds. A real defect
remains blocked until corrected and reviewed even when an extension is granted.
Current external review and CI prerequisites cannot be replaced with local review.
Do not request an extension automatically through repeated retries.

### Generated evidence and shared-file ownership

Use the existing trusted renderer/source-snapshot protocols without new allowances.
For each refresh record repository, policy/base/source commit IDs, generator blob
identity, exact invocation, input hashes, and SHA-256 hashes of every output. Compare
complete bytes from committed source and merge-base prose; preserve marker/non-owned
bytes. Re-run on the exact final head. Hash agreement proves identity, not deployment,
data freshness or external review. Any input/source change invalidates the old proof.

One named writer exclusively publishes to the branch and shared output set. Other
agents read only and return findings; they have no delegated publication authority.
Every participant checks the recorded writer identity before any shared write. An
unauthorized second writer must refuse before installing any bytes. Use isolated worktrees and writer-private output directories.
Before publishing, compare the expected branch head and every shared output hash;
if any differs, refuse publication, preserve the other writer's bytes and reconcile.
Use non-forced branch publication; a non-fast-forward rejection is a collision, not
permission to overwrite. An ownership handoff requires the prior writer to stop and confirm quiescence,
then explicit owner acknowledgment of the old/new writer and expected head/hashes
before the new writer proceeds. If quiescence cannot be established, publication
stays blocked. Shared-evidence output paths are not parallel workers' scratch space.
Hash prechecks detect stale inputs but are not atomic file compare-and-swap and do
not themselves exclude a race. This protocol depends on all participants honoring
exclusive publication; an uncontrolled concurrent writer blocks the task until
isolation is restored. No new lock service or mechanical exclusion is claimed.

### Required policy surfaces and cross-repository boundary

Future implementation must reconcile, not replace wholesale, these surfaces in each
repository: AGENTS.md review guidelines; CLAUDE.md review cap, pre-push gate review
and Rule 2.5; `.claude/commands/resolve-issue.md` second-round and downstream close-out
instructions; `.claude/skills/product-delivery/SKILL.md` Phases 2/4/5;
`.claude/agents/code-reviewer.md` severity/output rules; and
`.github/pull_request_template.md` review/merge checklist. Search other references to
these rules for contradictory instructions; replace the ambiguous AGENTS.md
"Before it posts" pronoun with an explicit reviewer subject (#1511). Preserve Solyra's LOVABLE header and
no-history-rewrite restrictions, repository-specific no-fallback rule numbering,
browser/API proof and its hermetic e2e requirements.

Stocks owns canonical requirements; this proposal changes no requirement definition.
If implementation needs to change one, stop for a separately approved requirements
change rather than widening this branch. Solyra must carry the same decisions and
scenario IDs through its own draft/approved spec, plan, catalog and PR. Do not copy
stocks-only inventory or backend evidence machinery into Solyra. Link independently
reviewed repository heads in the eventual acceptance record; a stocks pass cannot
certify Solyra. Active policy rollout awaits approval in both repositories.

## Acceptance controls

These are specified future controls, not tests claimed implemented here. Each run
records initial state, exact changed bytes, history/head, reviewer decision, expected
and actual action, evidence URI/hash and pass consumption. Run each scenario against
the inspected prior policy and proposed instructions; record conflicts on the prior
state and the deterministic expected decision under the proposal. An unchanged
baseline protection may already pass; label that a preserved regression control.
Policy-surface text comparison detects contradictions only, not real enforcement.

| ID | Input and action | Required observation / refusal control |
|---|---|---|
| C1 | Change an ordinary explanatory sentence's terminal punctuation, with no command/requirement changes | Same semantic approval; no new cycle requested solely for punctuation. If an external run actually occurs, count it and retain head checks. |
| C2 | Replace executable `tests/*.py` with `tests/**/*.py`, or weaken a mandatory requirement, or make docs describe unavailable behavior | Treat as semantic, examine actual effects, require changed-spec approval when applicable; never bypass with an asterisk/punctuation whitelist. |
| C3 | Second external round contains only P2/P3 with all required acceptance met | Reply/link real issues/resolve; no forced re-cut and no severity edits. Normal checks still gate eligibility. |
| C4 | Second round contains real P1; paired case is P2 but required acceptance fails | Both block and escalate at limit; no merge eligibility or badge-based waiver. Repeat with security/data-integrity/capacity/no-fallback failures. |
| C5 | HIGH label, conflicting HIGH/P3, then absent severity | HIGH maps to P1; conflict/missing label stays pending for owner, retaining original evidence. Test non-user-visible spec counterexample separately from real user-visible failure. |
| C6 | Two local red-team passes then two external rounds; replace PR after exhausted budget | Ledger shows four spent, zero remaining across both PRs, same finding IDs/history; next autonomous pass refused. P2-only eligible disposition does not create a third round. |
| C7 | Discover an unchanged earlier defect during focused verification and also a defect introduced by the fix | Record missed/new with original/later SHA respectively, search applicable class locations, block according to rule; no suppressed late defect or full cosmetic restart. |
| C8 | Cancel a reserved pass, create two split children, or lose the ledger | Cancelled pass remains spent; children share balance. Missing history holds for owner reconciliation; extension requires exact owner-approved count/scope. |
| C9 | Edit an unmerged approved spec's requirement or done_when; pair with citation-only correction; attempt edit to spec already on main | Substantive edit requires renewed approval, citation-only correction does not; merged spec must use a separately approved superseding spec. |
| C10 | Re-render from pinned committed inputs twice, then mutate output count/date, neighboring prose, marker or input hash | First outputs byte/hash-identical and accepted; each single-condition mutation refused by existing applicable renderer/identity gate. No fabricated successful proof record. |
| C11 | Assign A sole writer; have B attempt shared publication before and after A's precheck. Separately inject a changed remote head or stale shared-file hash before A's publication; request handoff while A is still running | B refuses before any write on both sides of the precheck; handoff stays blocked until A confirms quiescence and owner acknowledges. Stale head/hash refuses and preserves existing bytes. Uncontended authorized publication preserves exact intended bytes. Record that this is participant-protocol compliance, not atomic filesystem enforcement; an uncontrolled writer blocks publication. Never force-push. |

C10 uses existing `tests/scripts/test_spec_gate.py` controls
`test_complete_inventory_renders_from_merge_base_prose` and
`test_complete_inventory_refuses_non_renderer_prose`, plus applicable
`tests/scripts/test_doc_source_snapshot.py` mutation controls. C9 retains
`test_commit_mode_freezes_a_spec_once_main_holds_it_approved`. Existing cleanup
preservation tests do not prove C11 concurrency; perform the before/after-precheck publication and quiescent-handoff exercises
explicitly. Hash-only prechecks do not establish concurrent-writer exclusion. There is no current lineage-budget controller test.
Do not add a fixture-only simulator and call its success live process enforcement.

## Implementation sequencing and quality checks

After written-spec approval and landing, the reviewed implementation plan must map
A1-A5 to policy edits, scenario execution and evidence. Keep one writer; independent
reviewers may inspect scope, acceptance and policy contradictions in parallel.
Run unchanged BASE and proposed HEAD gates, affected existing suites and full default
docs audits on actual baseline and branch. No new findings are allowed. Do not use
the fixture task #1569 to change this task's checks. Preserve gate-file red-team
requirements if the later implementation touches covered gate surfaces; an exhausted
budget holds work for explicit adjudication rather than waiving those reviews.
No pinned workflows or gate code need change for the proposed policy-only alignment.

Capacity: no workload or schedule change. Volume is one spec in this draft;
Velocity is zero production calls; Wall-clock is local validation only; recurring
$/run x runs/day x 30 is 0. Existing renderer and verifier resource bounds remain.

## Observed real-PR acceptance and risks

Before calling the workflow durable, the owner approves a prospective observation
window: ten consecutive eligible real PR lineages, including at least three from each
repo, after both policy implementations land. Observe all pre-push/external passes,
not only successful merges. Missing evidence is unknown/failure, never success.
If the window lacks a real replacement or required-acceptance refusal, extend the
window; scenario exercises cannot be reported as observed real-PR events. No process
experiment may waive a product/security requirement or manufacture production defects.

For every lineage report: total passes, reviewer invocations and elapsed review time;
pre-push versus external work; replacement count; unique/duplicate finding IDs;
missed-first-review locations by reviewer/type; semantic versus cosmetic re-review
triggers; unresolved acceptance at each decision; escalation and owner response;
required-check/current-head/conversation status; generated identity mismatches and
writer collisions. Compare observed effort with its recorded allowance, not an
unmeasured historical estimate. Unknown historical cost prevents improvement claims.

Exit criteria: 100% ledger coverage; zero silent severity downgrades, budget resets,
unchecked acceptance waivers, lost findings or overwritten evidence; zero forced
re-cuts solely for P2/P3; zero autonomous passes beyond allowance; every true blocker
held or fixed/verified; every escalation has an explicit owner disposition. Report
median/max passes and elapsed time without claiming causation from this small sample.
A failure pauses adoption claims and returns the defect to the owner. Text tests and
this draft's local validation establish neither reliability nor deployment readiness.

Remaining owner decisions: approve the precedence rule and severity mapping; choose
or revise the proposed four-pass aggregate/two-external limit and extension authority;
approve ledger venue and handoff protocol; authorize the paired Solyra specification
and later rollout; approve the observation window. Until then status remains draft.
