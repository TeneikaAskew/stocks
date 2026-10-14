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

A reviewer's first review of a pull request is the complete one. A pull request gets at most two
review rounds (CLAUDE.md, "Review cap"), and Codex's code review runs again when new commits are
pushed to a pull request open for review, so a finding held back costs a round. A spec PR is fixed
in place by a push, like any other pull request; once `main` holds a spec, it changes only through a
new spec that supersedes it. Before it posts:

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
  blocks the merge, whatever its severity, only when it shows a realistic path to a user-visible
  defect, and otherwise gets a reply. Items that record delivery (the gate, the docs audit, the
  catalog row) are only checked for being met.

### Later reviews

A later review by the same reviewer checks its earlier findings, then the new commits, and still
posts a defect it finds in what its first review covered, for the author to classify under CLAUDE.md
Rule 2.5.

### Problems this pull request did not cause

A problem the pull request neither introduces nor makes worse is not posted as a finding (a reviewer
who can open an issue may open one), since every thread holds the merge (REQ-GOV-001).

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
