---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: []
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
site_source_notes: [SHARED-01]
done_when:
  - "Command: python3 -m scripts.maintenance.canvas_from_export --export <export.json> --canvas <page.html> --output <out.html> --report <report.md> writes the updated page and a Markdown report, and with --check instead of --output it writes nothing and exits 1 when the page would change and 0 when it would not; tests/scripts/test_canvas_from_export.py runs the module as a subprocess and asserts both modes"
  - "Triggers follow deploy.sh: after a run, the page's CRONS list holds exactly the export's schedulers with declared true (name, cron, target name, detail), in the page's existing order, with schedulers no longer declared dropped and new ones appended at the end; the detail is the scheduler's args, or for a service target with no args the path after ${service_url}; the report lists added, removed and changed triggers (tests)"
  - "Job cards follow deploy.sh: a JOBS card for a job the export does not declare is removed, and its remaining mentions elsewhere on the page are counted in the report and never rewritten; a declared job the page names nowhere gets a stub card in the fetch group (kind fetcher) or the compute group (otherwise) whose note reads 'Declared in gcp/deploy.sh; not yet described on this page.' with its reads, writes, module path and resources from the export; a declared job the page already names somewhere gets no stub (tests)"
  - "Prose is never rewritten: a card's schedule text that contradicts its triggers (it says On demand or One-shot while triggers exist, names a time no trigger can fire at, or omits an exact trigger time while naming others) is listed in the report with the trigger crons and left as it was; generic text such as Scheduled or After close is never listed; test_label_disagrees covers each case"
  - "Only the data asset changes: the page's bytes outside the bundler manifest are identical before and after, every manifest asset other than the one holding JOBS and CRONS is identical, and that asset decodes to the updated script; a page with no single asset holding both JOBS and CRONS, an export whose schema is not architecture-export/1 and an export with no sources.commit are refused with a non-zero exit and nothing written (tests)"
  - "Stamped and idempotent: the comment above CRONS names the export's commit (first 8 characters) and the optional --run-label, replacing the old stamp, and a second run with the same export and label changes nothing (test)"
  - "Gaps reported: services and tables in the export that the page never names are listed in the report (test)"
  - "Real page check: the PR body states, for the 2026-11-13 export (main f1868806) run against the diagram as it stood before the 2026-11-13 hand edit, that the script made the same trigger and card changes the hand edit made (EarningsWhispers card and trigger removed, earnings-sweep-sunday added, signal-quality-report-nightly args corrected), that node --check passes on the updated script, and that a second run reports no change"
  - "Capacity measured: the PR body states the script's wall-clock and peak memory on the real page measured on the PR head (Design 3)"
  - "Canvas skill uses the script: .claude/skills/refresh-canvas/SKILL.md tells a refresh of the backend architecture diagram to download the published page with the Artifact tool, run canvas_from_export with --report, show the report as the diff, publish the --output page only on the owner's approval, and keep the provenance check on the export's commit unchanged"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and python3 scripts/maintenance/docs_audit.py reports nothing on the branch that it does not report on origin/main, using this approved SHARED-01 declaration, the FEAT-CICD-001 SHARED-01 implementation-source note in 03-SITE-TRACEABILITY updated to the current source hash, and a committed docs/review-evidence/site-source-snapshot.json that verifies"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Update the backend architecture diagram from the architecture export

## Authority

On 2026-11-13, after the first architecture export (#1775) fed the backend architecture diagram by
hand, the owner asked "is it a script or something now?" and, told that the diagram step was manual,
answered "If you can, yes!".

## Problem

The export is scripted (`scripts/maintenance/architecture_export.py`, workflow "Architecture
export"). Turning it into a diagram update is not. On 2026-11-13 that step took a one-off edit script
and a by-eye comparison of 65 triggers and 67 job cards, and it still missed three cards whose
schedule text no longer matches their triggers (backfill-daily-indicators, fetch-av-options-backfill,
fetch-top-movers). Each refresh repeats that work and the same misses.

## Non-goals

- Rewriting prose: card notes, schedule text, details panels, layout and styling stay the
  canvas's. The script reports where they disagree with the export; a person changes them.
- Changing `docs/product/canvases.yml`. The entry stays `report-only` here; it moves to
  `source_export: architecture` in Close-out on a `docs/` branch, because a feature branch cannot
  edit `docs/product/`.
- Running anywhere but on request. No workflow step, schedule, commit of the page or bot PR; the
  canvas is still saved only with the Artifact tool, in chat, after the owner approves.
- Other canvases. The Stocks models diagram and the Solyra diagram keep their own paths.

## Approaches considered

1. Keep the manual step and add a checklist to the skill. Cheapest, but every refresh is a long
   by-eye diff and the misses above repeat.
2. Regenerate the page from the export. Loses the curated notes, groupings and details that make the
   diagram useful (the skill's guardrail against regenerating the data).
3. Chosen: a script that owns the repo-owned parts only (the trigger list, the stamp and which jobs
   have cards) and reports everything else.

## Design

### 1. What the page holds

The published diagram is a bundled page: a `__bundler/manifest` script maps asset ids to
`{mime, compressed, data}`, and one gzip-compressed JavaScript asset defines `JOBS` (cards grouped
`fetch`, `compute`, ...: `J(name, sched, note, reads, writes, module, res, surface)`), `CRONS`
(`C(name, cron, job, args)`, one per line) and the details panels. The trigger timeline and each
card's trigger rows are drawn from `CRONS`.

### 2. Script

`scripts/maintenance/canvas_from_export.py`, run as
`python3 -m scripts.maintenance.canvas_from_export --export E --canvas PAGE (--output OUT | --check) [--report R] [--run-label TEXT]`.

- Finds the single asset defining both `JOBS` and `CRONS`; refuses otherwise.
- Refuses an export whose `schema` is not `architecture-export/1` or that has no `sources.commit`.
- Uses declared rows only (`declared: true`); live-only jobs are drift, not diagram content.
- Rebuilds `CRONS` as an ordered set: existing order kept, undeclared triggers dropped, new ones
  appended; the detail is `args`, or the path of a `${service_url}/...` service target.
- Rewrites the stamp comment above `CRONS` to name the export commit and run label.
- Removes cards for undeclared jobs; adds a stub card for a declared job named nowhere on the page.
- Re-encodes only that asset (gzip with mtime 0, base64, compact manifest JSON), so every other byte
  of the page is unchanged and a second run is a no-op.
- Report (Markdown): applied changes (triggers added, removed, changed; cards removed and added),
  then items for a person (schedule text that disagrees with its triggers, remaining mentions of
  removed jobs, services and tables the page never names).

### 3. Capacity (CLAUDE.md Rule 0)

One page of about 390 KB and one export of under 200 KB (93 KB repo-only), read once, no network. Measured on the
prototype: 0.07 s wall-clock and 18 MiB peak memory. The PR body restates both on the PR head.

### 4. Skill

The architecture-export section of `.claude/skills/refresh-canvas/SKILL.md` keeps step 1 (get the
export, check its commit is on main) and replaces the by-hand diff with: read the canvas with the
Artifact tool and save the page; run the script with `--report`; show the report as the diff; on
approval publish `--output` to the canvas url; then make any prose changes the owner asks for from
the report's list, by hand, as today.

## Risks

- The page format changes (for example the bundler or the `J(...)` shape). The script refuses a page
  it cannot parse rather than guessing, and the tests pin the format it expects.
- A stub card reads as finished. Its note says it is not yet described, and the report lists it.
- The schedule-text check misses a disagreement. It only lists; it never edits, so a miss leaves the
  page as it is today.

## Close-out (after merge)

1. Plan status done on a `docs/` branch.
2. On a `docs/canvases-…` branch, change the diagram's `canvases.yml` entry to
   `source_export: architecture` and name the script.
3. Next refresh: run the skill end to end, and fix the three schedule texts the prototype flagged
   if the owner approves.
