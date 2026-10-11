---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: [1372]
canvases: []
done_when:
  - "tests/scripts/test_spec_gate.py asserts, on a fixture tree holding scripts/maintenance/, the GCP snapshot and only the four files the three documents' blocks render from (platform/api/main.py, gcp/deploy.sh, gcp/schema.sql, scripts/discord/register_commands.py), that a feature or fix branch passes the PR-mode gate when it inserts four lines near the top of platform/api/main.py, as #1366 did, and its only other change under docs/product/, besides its own catalog and traceability records, is the inventory blocks of docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md re-rendered by scripts/maintenance/doc_inventory.py"
  - "tests/scripts/test_spec_gate.py asserts that the PR-mode gate refuses each of these with a message citing REQ-GOV-004, and accepts a control that differs from it only in the condition under test: a changed byte outside every block body in one of the three documents; a marker line added, removed, moved, renamed, re-spaced or repeated, or a line matching the marker pattern whose name is not one of that document's expected blocks; a CRLF line ending added inside a block body; a NUL, U+0085, U+2028 or U+2029 inside a block body that comes from the fixture tree's own rendered text (a route path), so that only the clean-bytes rule refuses it; a block body that differs from what main's doc_inventory.py renders from the pull request's committed blobs (a hand-edited row); a .gitattributes in the head tree that would change a file's bytes on export (export-subst, eol, ident); a symbolic link or submodule anywhere in the head tree; a head-tree path with an empty, '.', '..' or '.git' component; a render that opens a file outside the materialized tree (a job entrypoint given as an absolute path to a file the test creates outside it); one of the three documents deleted, renamed or given another file mode; and a block change in a pull request that also changes scripts/maintenance/doc_inventory.py, scripts/maintenance/check_generated_docs.py, tests/scripts/test_check_generated_docs.py or tests/fixtures/live_gcp_snapshot_2026-09-07.json"
  - "tests/scripts/test_spec_gate.py asserts that changed_lines reads the diff as bytes and reports a changed content line that begins with '---', '+++', '--' or '++', a line holding a lone carriage return, and a line after a U+2028 within the same line; that a binary or hunkless diff of a changed path raises instead of returning no lines; that feat_span and section_of read the blob's raw bytes and number lines by '\\n' only; that added_lines, which has no caller, is gone; and that the catalog scope check therefore refuses each of: a removed '---' line in another capability's record, a NUL in the branch's own Status line alongside an edit to another record, and U+2028 characters or lone carriage returns in the branch's own record alongside lines added to another record"
  - "tests/scripts/test_spec_gate.py asserts that the gate's three document paths equal MARKER_DOCS in scripts/maintenance/check_generated_docs.py, that its snapshot path equals SNAPSHOT in tests/scripts/test_check_generated_docs.py, that the gate imports scripts/maintenance only when one of the three documents changes, and that a checkout without scripts/maintenance/ (solyra's) refuses a change to them as today rather than failing"
  - "is_process_file covers scripts/maintenance/doc_inventory.py, scripts/maintenance/check_generated_docs.py, scripts/maintenance/__init__.py and tests/fixtures/live_gcp_snapshot_2026-09-07.json, so a change to any of them needs a FEAT-CICD-001 branch, and tests/scripts/test_spec_gate.py asserts it"
  - "Each new assertion is shown failing against the gate on origin/main when the PR opens; tests/scripts/test_spec_gate.py passes in full on the PR head, and the base-suite job, main's suite run against the new gate, is green within its 10-minute limit"
  - "Before the PR's one push, a red-team pass ran with four reviewers: shell, YAML/Actions, the exporter and policy documents, and the diff and byte parsing together with the render check. Each finding is proven by running the gate on a concrete snippet; the last pass found nothing, and every earlier finding is listed in the PR with the test that now refuses it"
  - "The refusal message for other docs/product/ paths in check_product_scope and the 'Never' list in .claude/skills/product-delivery/SKILL.md name the re-rendered inventory blocks as an allowed change and cite REQ-GOV-004"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Let a feature change carry the re-rendered generated docs

## Problem

Three generated documents, `docs/product/infrastructure/05-a-ARCHITECTURE.md`,
`05-c-DATA_DEPENDENCIES.md` and `05-e-API.md`, hold inventory blocks between
`<!-- inventory:NAME:start -->` and `<!-- inventory:NAME:end -->` markers. `scripts/maintenance/doc_inventory.py`
renders those blocks from the repository, and many of their rows cite code by line number (35 citations of
`platform/api/main.py`, 81 of `gcp/deploy.sh`, 146 of `gcp/schema.sql` across the three documents).

Two checks then disagree about any change that moves a cited line:

- `tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate` requires each block to equal a
  fresh render, so the change must carry the re-rendered blocks.
- `check_product_scope` in `scripts/gate/spec_gate.py` refuses any file under `docs/product/` on a feature or fix
  branch except the FEAT's own catalog and traceability records and the model registry.

No pull request can pass both. stocks#1366 hit this on 2026-10-11: four lines added to `_cors_origin_regex`
(`main.py:127`) moved every cited line below them. Its re-rendered blocks were refused by the gate (verified: main's
`check_product_scope` refuses all three documents on that commit), so the change was rewritten to keep `main.py`'s
line count, at the cost of part of its comment. REQ-GOV-004 states the rule this spec implements.

Review of this spec also found that the gate's diff reader drops changed lines silently, which the catalog scope check
relies on today. `changed_lines` reads a content line beginning with `---`, `+++`, `--` or `++` as a diff header; text-mode decoding turns a lone carriage return into a line break; a NUL makes git print "Binary files
differ" and the reader return nothing; and `feat_span` and `section_of` count lines of text decoded with newline translation and split with
`splitlines()`, which breaks at a lone carriage return or U+2028 where git does not. Each was reproduced against main's gate as a feature branch editing another capability's
catalog record unnoticed. This spec fixes them, because they are the same functions and get the same red team.

## Non-goals

- **Prose outside the blocks.** 20 of the 262 cited lines are in the documents' prose (05-a: 5 for `main.py`, 13 for
  `deploy.sh`, 2 for `schema.sql`), and `gate_derived_numbers` checks counts written in prose (05-a lines 141, 811 and
  1116, 05-c line 1430). A change that moves one of those prose citations leaves it stale, and nothing checks it. A
  change that alters one of those counts, such as adding a Cloud Run job, still fails one check or the other. Both are
  tracked in #1372; this spec covers the blocks only.
- **A change to the renderer's output.** The gate does not refuse a change to `doc_inventory.py`, but a change that
  alters its output cannot carry the blocks it would need: REQ-GOV-004 refuses blocks alongside a renderer change, and
  main's renderer could not vouch for them anyway. Such a pull request fails the docs test today and still will. It is
  part of #1372.
- **No pre-push hook.** A second executable hook would need its own pinned copy under `scripts/gate/pinned/` and the
  two-PR pinning procedure. The product-delivery skill runs the PR-mode gate at close-out (Phase 5 step 5); running it
  before each push stays a habit, not a check.
- **Restoring #1366's comment.** CI judges a PR with the base's copy of the gate, so the new rule cannot be exercised
  by the PR that adds it. The first later PR that moves a cited line uses it.

## Approaches considered

1. **The gate renders.** The gate checks that only block bodies changed, then runs main's `doc_inventory.py` over the
   pull request's committed files, read as data, and requires the committed blocks to equal that render. Chosen.
2. **Stop citing line numbers.** Rejected: readers lose links to exact lines, every block regenerates once, and counts
   and names in the blocks would still change with the code.
3. **The gate checks scope; `Run Tests` checks exactness.** This was this spec's first design. Rejected in review:
   `Run Tests` runs the pull request's own code. Four lines added to `tests/conftest.py` patched `inv.render_markdown`
   to emit a hand-edited row, and the docs test then passed. Any test module can do the same while pytest collects it,
   so no list of protected paths closes this.

Approach 1 runs the renderer only as main's code; the pull request's tree is input. `doc_inventory.py` reads the tree
by parsing it (`ast`), never by importing or executing it, and its one subprocess is the `gcloud` call of the live
path, which the gate does not use. Measured on 2026-10-11 with audit hooks on imports, subprocesses, `exec`, `compile`
and file opens: no head code was imported or run, and only the standard library was needed.

Chosen on 2026-10-11 by the owner ("Gate spec approved"), after the review that rejected Approach 3.

## Design

`check_product_scope` gains one allowance, checked before its generic refusal of `docs/product/` paths. A change to
one of the three documents passes when all of these hold, and is otherwise refused with a message that names the
condition that failed and cites REQ-GOV-004. "Base" below is the merge base; "main's code" is the gate's own
checkout, which in CI is the base commit (`spec-gate.yml` checks it out). A local `--pr` run uses the worktree's
copies instead.

- **Same file.** The document exists on both sides at the same path, with the same file mode, and is not renamed.
- **Exact markers.** On each side, the lines that are exactly `MARKER_START.format(name=n)` or
  `MARKER_END.format(name=n)`, for each `n` in that document's `EXPECTED_MARKERS` entry, form one start line and one
  later end line per name, unnested, in the same order on both sides. Any other line that `_MARKER_LINE` matches is
  refused: an unknown name, a re-spaced marker, a second copy. The docs test finds blocks by exact string and only for
  expected names, so a line it would not treat as a marker must not open a block here either. A sentence that
  mentions a marker is not a whole marker line, so it stays prose.
- **Only block bodies change.** Both blobs are read as bytes and split on `\n` only. With each block's body (the lines
  strictly between its start and end lines) removed, the two sides must be identical, byte for byte. No diff output is
  parsed.
- **Clean bytes.** No head block body contains a carriage return, a NUL, U+0085, U+2028 or U+2029. The docs test reads
  with `read_text()` (verified: a block converted to CRLF still passed it), and git treats a NUL as binary.
- **Exact render.** The gate writes the head commit's blobs to a temporary directory from `git ls-tree -r -z` and
  `git cat-file --batch`, which apply no attributes. It refuses when the head tree holds a symbolic link (mode
  120000), a submodule (160000), a `.gitattributes`, or a path with an empty, `.`, `..` or `.git` component
  (compared without case), and it checks that every resolved path stays inside the directory before writing it.
  The render runs in a child process: `spec_gate.py` itself in a hidden mode, started with `python3 -I` from a
  working directory outside the tree, with the gate's own checkout first on `sys.path`, and asserting that the
  `doc_inventory` it imported lives in that checkout. The child loads main's
  `tests/fixtures/live_gcp_snapshot_2026-09-07.json` and imports what the render needs, then installs an audit hook
  that calls `os._exit` with a code of its own on any `open`, `os.listdir` or `os.scandir` outside the directory; a
  raised exception could be caught by the renderer's own `except OSError`. The parent treats that exit code, or any
  failure, as a refusal. The child builds `doc_inventory.repo_inventory` over the directory and requires
  `doc_inventory.differing_blocks` to report nothing for each changed document. Main has no symbolic link,
  submodule or `.gitattributes` today (1,476 files at mode 100644 and 37 at 100755).
- **Render inputs unchanged.** The pull request changes none of `scripts/maintenance/doc_inventory.py`,
  `scripts/maintenance/check_generated_docs.py`, `tests/scripts/test_check_generated_docs.py` or that snapshot, as
  REQ-GOV-004 requires.

The three paths are constants in the gate, pinned by a parity test to `MARKER_DOCS` and the docs test's `SNAPSHOT`.
The gate imports `doc_inventory` and `check_generated_docs` only when one of the three documents changed, for
`EXPECTED_MARKERS`, `MARKER_START`, `MARKER_END` and the render. A checkout without `scripts/maintenance/` (solyra,
which carries the same `spec_gate.py`, and the suite's temporary repositories) gets no allowance and the refusal it
gets today; any other import error raises.

`is_process_file` covers `doc_inventory.py`, `check_generated_docs.py`, `scripts/maintenance/__init__.py` and the
snapshot, so a change to the code and data the gate now trusts needs a FEAT-CICD-001 branch, as the gate's own files
do.

The diff reader: `changed_lines` reads `git diff` as bytes, treats `---` and `+++` as file headers only before a file's
first `@@`, splits on `\n` only, and raises on a binary or hunkless diff of a path it was asked about. `feat_span`,
`section_of` and anything else compared with git's line numbers read the blob's raw bytes and decode them without
newline translation, numbering lines by `\n` only, as git does. `added_lines` has no caller and is deleted.

`spec_gate.py` and its suite are gate files. The change gets the red-team pass CLAUDE.md requires before its one push,
with a fourth reviewer for the byte parsing and the render check, and none of the pinned files
(`scripts/gate/pinned/`) change.

Capacity: only a pull request that changes one of the three documents pays for the render. Measured on main's tree on
2026-10-11: 19.8 s to build the inventory, 16.3 s to compare and 1.2 s to write the tree, inside the gate job's
5-minute timeout. The suite's fixture tree holds only the four files the blocks render from (0.5 s to build, 0.4 s to
compare), so the new tests add seconds, not minutes, to a suite that already takes about 260 s against the base-suite
job's 10-minute limit. No other workload changes.

## Risks

- **The gate depends on code outside `scripts/gate/`.** `doc_inventory.py` and `check_generated_docs.py` now decide
  part of the verdict. A pull request cannot change them for its own run (CI runs main's copies), and as process files
  a change to them needs a FEAT-CICD-001 branch, but they do not get the gate's red team.
- **Two merged pull requests can leave a block stale together** when each re-rendered against its own base. The docs
  test then fails on `main`, on every open pull request (CI tests the merge ref) and in the nightly run, until a
  `docs/` pull request re-renders the blocks; a `docs/` branch may change `docs/product/` and carries no code.
- **A change to a deploy file and the renderer together now takes two pull requests.** A deploy file belongs to
  FEAT-DEPLOY-001 and the renderer becomes a FEAT-CICD-001 process file, so a change like #1189 (`deploy.sh`,
  `doc_inventory.py` and 05-a together) lands the renderer first, with its output on `main` unchanged, then the
  deploy change with its re-rendered blocks.
- **The child's pre-imports depend on the Python version.** A module the render imports lazily after the hook is
  installed opens a file outside the tree and aborts the render. That fails closed, and the suite shows it.
- **The render grows with the repository.** If it nears the gate job's timeout, the job times out, the check stays
  red and the pull request cannot merge. The timeout is raised through the pinned-file procedure.
