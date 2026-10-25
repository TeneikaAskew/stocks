# Publication validation

Audit source: main `911d30a7427a8d3249ecd82a828952a3e4b639a0`.
Only `docs/audits/2026-10-25-required-ci/` changes. No runtime, test, workflow,
recovery branch or repository-setting edits. The local test container was
removed after the successful integration run.

## Checks actually performed

- `python scripts/gate/spec_gate.py --commit`: passed for all seven staged
  audit documentation files before commit `54da58031108`.
- `python scripts/gate/spec_gate.py --pr origin/main`: passed on that committed
  audit branch (seven changed documentation files).
- JSON parsing passed for the three JSON deliverables; relative Markdown links
  resolved; `git diff --check` passed. Machine inventory is generated from
  actual collected IDs, not estimated from function definitions.
- Full default `python scripts/maintenance/docs_audit.py --json` executed on
  main and the committed branch, without suppressing checks, stamping documents
  or substituting snapshots. The CLI exits zero without `--check` even when
  findings exist. **The no-new-findings comparison FAILED.**

## Exact failed comparison

At main `911d30a7427a`: 488 documents, **288 findings**.
At audit commit `54da58031108`: 492 documents, **291 findings**.
No main finding disappeared. The three additional P2 findings all target
`docs/product/03-SITE-TRACEABILITY.md`:

1. `changed-since`: one content commit to `platform/api`, `platform/deploy.sh`,
   `platform/Dockerfile`, `gcp`, `lib`, `scripts`, `tests` since `a5749d4c0b93`;
   named commit `05ab15fcc762e0ce02ddd4ce654604375dbb93df`, the prior pinned
   registry envelope change (#1591).
2. `changed-since`: the document itself changed since `a5749d4c0b93`, so its
   prior review covers different prose.
3. `source-provenance`: `implementation-source identity unavailable: object
   exceeds remaining input-byte allowance`.

These are real failed branch-vs-main results, not waived or relabeled as clean.
The same verifier failure class is already under recovery, but this audit does
not establish a repair, override its limits, adopt a prior exception, or add
itself as a release prerequisite. The full audit JSON remains local under
`/tmp/stocks-ci-audit/docs-main.json` and `docs-branch.json`; the exact added
finding objects and their source hashes are in `publication-evidence.json`.

## Draft disposition

Publish as a **draft** for the requested independent audit and keep it draft.
No readiness, merge, deployment, hosted-green or complete-validity claim is made.
Before any future readiness decision, rerun the full default main/branch audits
on the then-current source and resolve the failed comparison through the normal
owning workflow. Publication authority does not waive that comparison.

The final evidence-only commit reruns the ordinary spec gate and diff/JSON checks;
the substantive audit measurement above remains bound to its explicit commit.
The exact final revision and verified draft URL are returned with the PR.
