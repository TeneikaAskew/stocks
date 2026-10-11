---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-11-feat-cicd-001-generated-docs-render.md
branch: feature/feat-cicd-001-generated-docs-render
pr: null
status: ready
---

# Let a feature change carry the re-rendered generated docs: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax. Every task
> cites the spec section it implements and the done_when item(s) it advances (done_when[0] is the first item).

**Goal:** `check_product_scope` accepts a feature change's re-rendered inventory blocks in 05-a, 05-c and 05-e exactly when
main's `doc_inventory.py`, run over the pull request's committed blobs, renders those blocks. The same PR makes the
gate's diff reader and catalog line numbering byte-exact.

**Architecture:** The allowance runs a fixed sequence of rules in `scripts/gate/spec_gate.py`, cheapest first: render
inputs unchanged, same file, line endings, exact markers, only block bodies, clean bytes, a plain-file head tree, then
the exact render. The render writes the head tree to a temporary directory and runs main's renderer in a child process
(`spec_gate.py` in a hidden mode, `python3 -I -B`) behind an audit-hook fence. `changed_lines` reads `git diff` as bytes,
and every catalog line number is counted by `\n` only.

**Tech Stack:** Python 3.11+ standard library (the gate already needs `tomllib`), git plumbing (`diff`, `ls-tree -z`,
`cat-file --batch`, `mktree` in tests), pytest. The suite runs the gate as a subprocess in throwaway git repositories.

**Spec:** `docs/superpowers/specs/2026-10-11-feat-cicd-001-generated-docs-render.md`. The spec is the authority. This plan
records only the decisions the spec leaves to implementation.

12 tasks. Base: `origin/main` at 2a108675 (#1375). Every `file:line` below is read from that commit.

## Global Constraints

- One branch, one PR: `feature/feat-cicd-001-generated-docs-render`, cut from `origin/main`. Never force-push. Never run
  bare `git stash`.
- The PR changes only these files: `scripts/gate/spec_gate.py`, `tests/scripts/test_spec_gate.py`,
  `.claude/skills/product-delivery/SKILL.md`, this plan, and the FEAT-CICD-001 record and lineage in
  `docs/product/02-FEATURE-CATALOG.md` and `docs/product/12-PR-ISSUE-TRACEABILITY.md`. Nothing under
  `scripts/gate/pinned/`, `.github/workflows/`, `.githooks/` or `scripts/maintenance/` changes. Neither do the snapshot
  or the three generated documents. No new module is added under `scripts/gate/` (`chore_allows` refuses one).
- Exact values: the documents are `docs/product/infrastructure/05-a-ARCHITECTURE.md`, `.../05-c-DATA_DEPENDENCIES.md` and
  `.../05-e-API.md`. The snapshot is `tests/fixtures/live_gcp_snapshot_2026-09-07.json`. Every refusal the allowance
  produces contains `REQ-GOV-004`.
- The gate stays portable. With no `scripts/maintenance/` (solyra, the suite's plain `repo`), the gate behaves as on
  main and only the refusal text gains the allowance. Any other import error raises.
- `spec-gate.yml`'s base-suite job runs main's suite against this gate, so these substrings stay in the gate's output:
  `<path> changes in this feature change`, `lines outside <FEAT>'s row and record change`,
  `requirements change on their own docs/ branch` and `docs/product/12-PR-ISSUE-TRACEABILITY.md: lines outside`.
- The gate checks its own suite (`suite_escape`, `spec_gate.py:619`):
  - No name `skip`, `skipif`, `xfail`, `importorskip`, `pytestmark`, `exit` or `_exit` appears anywhere in the file, so
    no `sys.exit` and no `os._exit`.
  - No `pytest_*` function.
  - No `test_*` function has a decorator (so no `@pytest.mark.parametrize`), and none holds a `return` or `raise`
    anywhere inside it, nested functions included.
  - No assertion is vacuous, and every existing test keeps its name and its assertion count.
  - So case tables run as loops inside one test and end in one assertion over every case that missed. Helpers that
    return live at module level.
- The PR's own suite runs in `registry-check.yml`'s `registry` job, which has a 5-minute timeout and is pinned.
  Measured on 2026-10-11: run 38105560722 (#1375's head) took 211 s in the suite step and 231 s for the whole job. The
  local suite at 2a108675 took 270 s for 96 tests, so CI runs at about 0.78× local. Budget: the new tests total ≤ 60 s
  locally (`--durations=0`), about 47 s in CI. This PR never raises the timeout.
- A child render on the fixture tree takes about 1.1 s. A fixture render with the CLI takes 0.93 s. On main's full tree
  (498d0ad1: 1,514 files, 186 MiB) the render took 37.2 s and writing the tree 1.9 s, inside the gate job's 5-minute
  timeout. All measured locally on Python 3.11.
- Before the one push that carries the gate change, the red team runs with four reviewers (Task 10).
- Commits: `type(scope): description`, imperative mood, subject ≤ 72 characters. Run
  `python3 scripts/gate/spec_gate.py --commit` before each commit. The hook runs it too: `core.hooksPath=.githooks` is
  set in `/home/user/stocks`.

## Review Focus

The spec implies five failure modes that no done_when test covers. Each line names the input, the behaviour a person
would expect, and the task whose test pins it.

1. **Blocks re-rendered from another snapshot, or with `--live`.** The person should get a refusal that says which block
   differs and gives the exact re-render command:
   `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore <doc>`.
   Pinned in Task 8, `test_a_block_must_equal_mains_render`.
2. **Prose edited next to the blocks, the habit of the monthly refresh.** The refusal should name the first changed line
   outside the blocks. Pinned in Task 5, `test_only_inventory_block_bodies_change`, by the case "a byte outside the blocks".
3. **The runner's Python lazily imports a stdlib module after the fence.** Every honest re-render would be refused. The
   refusal should name the file the renderer opened, so the fix (extend `RENDER_PREIMPORTS`) is obvious. Pinned in
   Task 8, `test_the_render_reads_only_the_pull_requests_files`, which asserts that the opened path is printed.
4. **A Windows checkout with autocrlf commits the whole document as CRLF.** The refusal should name the carriage returns,
   not a marker or line 1. Pinned in Task 5, by the case "CRLF throughout".
5. **The renderer raises on the PR's own files,** for example a syntax error in `platform/api/main.py`. The gate should
   refuse with "renderer failed" and the exception line. It must not pass, report "differs", or crash with its own
   traceback. Pinned in Task 8, `test_a_block_must_equal_mains_render`.

---

## Task 1: Branch, plan, and the byte-exact diff reader

Spec: § Design, "The diff reader" (`changed_lines`, `added_lines`). Advances done_when[2].

**Files:**
- Create: `docs/superpowers/plans/2026-10-11-feat-cicd-001-generated-docs-render.md` (this file)
- Modify: `scripts/gate/spec_gate.py:1175-1182` (add `git_bytes` after `git_out`), `:3482-3496` (`changed_lines`), and
  delete `:3853-3863` (`added_lines`)
- Modify: `tests/scripts/test_spec_gate.py:14-24` (imports `ast`, `importlib.util`, `shutil`, `types`, `Callable`) and
  `:184-198` (`pr` gains `then`)
- Test: `tests/scripts/test_spec_gate.py`, a new section appended after the last test, headed
  `# REQ-GOV-004 and the byte-exact diff reader`

**Interfaces:**
- Produces: `git_bytes(*args: str) -> bytes`. It returns the stdout of a git command that must succeed, undecoded. It
  runs `git -c core.quotePath=false`, uses `cwd=ROOT`, and raises `GitFailed` on a non-zero exit.
- Produces: `changed_lines(merge_base: str, head: str, path: str) -> list[tuple[str, int, str]]`. The signature is
  unchanged. It now raises `GitFailed` with a message containing `no text hunk`.
- Produces (suite): `load_gate(root: Path) -> types.ModuleType`. It loads root's copy of `scripts/gate/spec_gate.py`,
  registered in `sys.modules` under a unique name, so the module's `ROOT` is `root`.
- Produces (suite): `pr(repo, branch, files, then: Callable[[Path], object] | None = None, **env)`. It calls `then(repo)`
  after writing `files` and before `git add -A`.

- [ ] **Step 1: Branch and commit this plan.**

```bash
git -C /home/user/stocks fetch origin main
git -C /home/user/stocks worktree add "$WT" -b feature/feat-cicd-001-generated-docs-render origin/main
cp "$SCRATCH/plan-generated-docs-render.md" "$WT/docs/superpowers/plans/2026-10-11-feat-cicd-001-generated-docs-render.md"
cd "$WT" && git add docs/superpowers/plans/ && python3 scripts/gate/spec_gate.py --commit
git commit -m "docs(plan): plan the generated-docs render allowance"
```

  Expected: `spec gate ok (branch=feature/feat-cicd-001-generated-docs-render, 1 changed file(s))`.

- [ ] **Step 2: Write the failing tests.** `base` and `head` below are `_git(repo, "rev-parse", "base")` and
  `_git(repo, "rev-parse", "HEAD")`.

```python
def test_changed_lines_reads_the_diff_as_bytes(repo):
    sg = load_gate(repo)
    on_base(repo, {"docs/f.md": "a\n---\n-- keep\nb\nc\nd\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\n+++ added\n++ also\nb\nc\nd\n"})
    assert sg.changed_lines(base, head, "docs/f.md") == [("-", 2, "---"), ("-", 3, "-- keep"), ("+", 2, "+++ added"), ("+", 3, "++ also")]
    on_base(repo, {"docs/f.md": "a\nb\nc\nd\ne\nf\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\nb-new\r+phantom\nc\nd\ne-new\u2028@@ -9 +9 @@\nf\n"})
    assert sg.changed_lines(base, head, "docs/f.md") == [("-", 2, "b"), ("+", 2, "b-new\r+phantom"), ("-", 5, "e"), ("+", 5, "e-new\u2028@@ -9 +9 @@")]

def test_changed_lines_raises_on_a_binary_or_hunkless_diff(repo):
    sg = load_gate(repo)
    on_base(repo, {"docs/f.md": "a\n"})
    pr(repo, "docs/probe", {"docs/f.md": "a\x00\n"})                                  # binary
    with pytest.raises(sg.GitFailed, match="no text hunk"):
        sg.changed_lines(base, head, "docs/f.md")
    pr(repo, "docs/probe", {}, then=lambda r: (r / "docs/f.md").chmod(0o755))         # mode only
    with pytest.raises(sg.GitFailed, match="no text hunk"):
        sg.changed_lines(base, head, "docs/f.md")

def test_added_lines_is_gone():
    defined = {n.name for n in ast.parse(GATE.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)}
    assert "changed_lines" in defined and "added_lines" not in defined
```

  These results were measured against main's gate on 2026-10-11. The first diff returned `[]`. The second returned
  `[('-', 2, 'b'), ('+', 2, 'b-new'), ('+', 3, 'phantom'), ('-', 5, 'e'), ('+', 5, 'e-new')]`.

- [ ] **Step 3: Run them.** Command:
  `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest -k "changed_lines or added_lines_is_gone"`.
  Expected: `3 failed`.

- [ ] **Step 4: Implement `git_bytes` and rewrite `changed_lines`.** Read
  `git_bytes("diff", "--no-color", "--no-ext-diff", "--no-textconv", "-U0", merge_base, head, "--", path)` and split it
  on `b"\n"` only.
  - Every line before the first `@@` is a header.
  - After that, `rb"^@@ -(\d+)(?:,\d+)? \+(\d+)"` resets both counters.
  - Lines starting with `-` or `+` are decoded `utf-8` with `errors="replace"` and recorded.
  - Lines starting with `\` are skipped.
  - A diff with no hunk at all, whether empty, binary or mode-only, raises
    `GitFailed(f"git diff of {path} shows no text hunk (a binary file, a NUL byte or a mode-only change); the gate reads every changed line and refuses to pass on none")`.

  Delete `added_lines`. It has no caller.

- [ ] **Step 5: Run the new tests and the scope tests they touch.** Command:
  `... -k "changed_lines or added_lines_is_gone or product_records or product_documents or docs_only_feature"`.
  Expected: all pass.

- [ ] **Step 6: Commit.** `fix(gate): read the diff as bytes and refuse a diff with no text hunk`.

## Task 2: Number catalog lines as git does

Spec: § Problem (the last paragraph) and § Design, "The diff reader" (`feat_span`, `section_of`). Advances done_when[2].

**Files:**
- Modify: `scripts/gate/spec_gate.py:3499-3526` (`feat_span`, `heading_levels`, `feat_headings`) and `:3683-3717`
  (`check_product_scope` reads raw blobs)
- Modify: `scripts/gate/spec_gate.py:3814-3850` (`feat_record`, `repeated_fields`, `feat_fields`) and `:3866-3885`
  (`section_of`, `lineage_refs`)
- Test: `tests/scripts/test_spec_gate.py` (the new section)

**Interfaces:**
- Consumes: `load_gate`, `pr` (Task 1).
- Produces: `lines_of(text: str) -> list[str]`, which is `text.split("\n")`. Index `i` is git's line `i + 1`.
- Ruling: `section_of` feeds no comparison with git today. It feeds the close-out readers (`feat_record`,
  `repeated_fields`, `feat_fields`, `lineage_refs`), and those index `splitlines()` arrays. All eight functions named
  above therefore switch to `lines_of` together; otherwise their indices fall out of step with `section_of`.
- Ruling: only `check_product_scope` changes how it reads, to
  `(Tree(merge_base).raw(path) or b"").decode("utf-8", "replace")` and the same for `ch.tree.raw(path)`. The close-out
  keeps `Tree.read`, because it compares no git line numbers.

- [ ] **Step 1: Write the failing tests.**

```python
def test_feat_span_and_section_of_number_lines_as_git_does(repo):
    sg = load_gate(repo)
    assert sg.feat_span("### FEAT-A-001\nx\u2028y\n### FEAT-B-001\nz\n", "FEAT-A-001") == {1, 2}      # main: {1, 2, 3}
    assert sg.section_of("### FEAT-A-001\nx\ry\n### FEAT-B-001\n", "FEAT-A-001") == range(1, 3)    # main: range(1, 4)

def test_the_catalog_scope_check_sees_every_changed_line(repo):
    # Each case is an edit to FEAT-DATA-001's record by the FEAT-MODEL-001 branch that main's gate passed (measured).
    own = "### FEAT-MODEL-001\n\n- Status: Production"
    added = "### FEAT-DATA-001\nAdded by a FEAT-MODEL-001 branch.\nAnd a second line.\n"
    ok = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body()}
    outcomes = {}
    on_base(repo, {CATALOG: CATALOG_TEXT + "\n---\n\n-- keep this caveat\n"})
    outcomes["a removed '---' line"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT + "\n\n\n-- keep this caveat\n"}, **ok)
    on_base(repo, {CATALOG: CATALOG_TEXT})
    outcomes["a NUL in the own Status"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + "\x00").replace(
        "### FEAT-DATA-001\n\n- Status: Production", "### FEAT-DATA-001\n\n- Status: Retired")}, **ok)
    outcomes["U+2028 in the own record"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + "\u2028" * 4).replace("### FEAT-DATA-001\n", added)}, **ok)
    outcomes["lone CRs in the own record"] = pr(repo, BRANCH, {**CODE, CATALOG: CATALOG_TEXT.replace(own, own + "\r" * 4).replace("### FEAT-DATA-001\n", added)}, **ok)
    missed = {k: r.stdout[-300:] for k, r in outcomes.items() if r.returncode != 1
              or not ("lines outside FEAT-MODEL-001's row and record change" in r.stdout or "no text hunk" in r.stdout)}
    assert missed == {}, missed
```

- [ ] **Step 2: Run them.** Command: `... -k "number_lines_as_git_does or sees_every_changed_line"`. Expected: `2 failed`.
  The second fails on its U+2028 and CR cases even with Task 1's reader in place.
- [ ] **Step 3: Implement `lines_of`,** swap it into the eight functions, and make `check_product_scope` read raw blobs.
- [ ] **Step 4: Run them.** Command:
  `... -k "number_lines_as_git_does or sees_every_changed_line or close_out or lineage or records_stay_unique or product_records"`.
  Expected: all pass.
- [ ] **Step 5: Commit.** `fix(gate): number catalog lines by newline alone, as git does`.

## Task 3: The renderer's paths, process files and parity

Spec: § Design, "The three paths are constants in the gate…" and "`is_process_file` covers…". Advances done_when[4]
and done_when[3] (parity).

**Files:**
- Modify: `scripts/gate/spec_gate.py:64-65` (add constants after `REGISTRY_DOCS`) and `:1085-1088` (`is_process_file`)
- Modify: `tests/scripts/test_spec_gate.py:6` (docstring) and `:28-30` (constant)

**Interfaces:**
- Produces these constants, with exactly these values:

```python
GENERATED_DOCS = ("docs/product/infrastructure/05-a-ARCHITECTURE.md", "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md",
                  "docs/product/infrastructure/05-e-API.md")
GENERATED_RULE = "REQ-GOV-004"
RENDER_SNAPSHOT = "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
RENDER_INPUTS = ("scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
                 "tests/scripts/test_check_generated_docs.py", RENDER_SNAPSHOT)          # REQ-GOV-004: unchanged beside blocks
RENDERER_FILES = ("scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
                  "scripts/maintenance/__init__.py", RENDER_SNAPSHOT)                     # process files: FEAT-CICD-001's
```

- Produces (suite): `RENDERER_HERE = (REPO / "scripts/maintenance/doc_inventory.py").is_file()`.
- Ruling: tests that need stocks' renderer run only where `RENDERER_HERE` is true. They guard with `if RENDERER_HERE:`
  because a test may not `return`. This keeps the suite portable to solyra; see "Solyra" at the end of this plan.
- `is_process_file` gains `or path in RENDERER_FILES`.
- The suite docstring at `:6` gains one sentence: tests that need the renderer under `scripts/maintenance/` run where it
  exists (`RENDERER_HERE`), so the file can stay byte-identical in solyra.

- [ ] **Step 1: Write the failing tests.**

```python
def test_the_renderer_and_its_snapshot_are_process_files(repo):
    cicd_row = CATALOG_TEXT.replace("| [FEAT-DATA-001]", "| [FEAT-CICD-001](#feat-cicd-001) | CI | Production | unknown | none |\n| [FEAT-DATA-001]", 1)
    on_base(repo, {CATALOG: cicd_row})
    paths = ("scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
             "scripts/maintenance/__init__.py", "tests/fixtures/live_gcp_snapshot_2026-09-07.json")
    missed = [p for p in paths if "belong to FEAT-CICD-001" not in
              pr(repo, BRANCH, {**CODE, p: "# x\n"}, PR_TITLE="FEAT-MODEL-001: x", PR_BODY=body()).stdout]
    assert missed == [], missed

def test_the_gate_names_the_documents_and_snapshot_the_docs_test_reads():
    sg = load_gate(REPO)
    assert sg.GENERATED_RULE == "REQ-GOV-004" and sg.RENDER_INPUTS == (
        "scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py",
        "tests/scripts/test_check_generated_docs.py", "tests/fixtures/live_gcp_snapshot_2026-09-07.json")
    # the renderer tests cannot be switched off in a repository that carries the documents
    assert RENDERER_HERE == all((REPO / d).is_file() for d in sg.GENERATED_DOCS)
    if RENDERER_HERE:
        from scripts.maintenance import check_generated_docs as cgd
        from tests.scripts.test_check_generated_docs import SNAPSHOT
        assert sg.GENERATED_DOCS == cgd.MARKER_DOCS and REPO / sg.RENDER_SNAPSHOT == SNAPSHOT
```

- [ ] **Step 2: Run them.** Command: `... -k "process_files or names_the_documents"`. Expected: `2 failed` (main accepts all
  four paths; it has no `GENERATED_RULE`).
- [ ] **Step 3: Implement** the constants and the `is_process_file` change. Edit the docstring.
- [ ] **Step 4: Run them.** Expected: `2 passed`. Then run `... -k "FEAT_CICD or ownership or process"` and expect all to
  pass.
- [ ] **Step 5: Commit.** `feat(gate): make the renderer and its snapshot FEAT-CICD-001 process files`.

## Task 4: Load main's renderer, the refusal text, fixed inputs and the same file

Spec: § Design, the allowance's opening paragraph, "Same file", "Render inputs unchanged", and "The gate imports
`doc_inventory`…". Advances done_when[3] (lazy import, solyra-shaped checkout), done_when[1] (the render-input,
deleted, renamed and mode cases) and done_when[7] (the refusal message).

**Files:**
- Modify: `scripts/gate/spec_gate.py`. Add a block headed `# REQ-GOV-004: generated documents` immediately above
  `check_product_scope` (`:3683`). Modify `check_product_scope` (`:3683-3717`).
- Modify: `tests/scripts/test_spec_gate.py:135-153`. The `repo` fixture body moves into `make_repo(root: Path) -> Path`,
  and `repo` returns `make_repo(tmp_path)`. In `:168-181`, `on_base` gains the same `then` parameter `pr` has.
- Test: `tests/scripts/test_spec_gate.py` (the new section)

**Interfaces:**
- Produces: `maintenance_modules() -> tuple[types.ModuleType, types.ModuleType] | None`, returning main's
  `(doc_inventory, check_generated_docs)`.
  - It returns `None` when `ROOT / "scripts/maintenance"` is not a directory.
  - Otherwise it puts `str(ROOT)` first on `sys.path` and imports `scripts.maintenance.doc_inventory` and
    `scripts.maintenance.check_generated_docs`.
  - It raises `ImportError` naming the file when either module's `__file__` resolves outside
    `ROOT / "scripts/maintenance"`. A regular `scripts` package elsewhere on `sys.path` beats the namespace one.
  - Any other import error propagates.
- Produces: `generated_refusal(path: str, reason: str) -> str`. It returns exactly
  `f"{path}: {reason} ({GENERATED_RULE}: a feature change carries a generated document's inventory blocks only as main's scripts/maintenance/doc_inventory.py re-renders them from this pull request)"`.
- Produces: `generated_doc_refusals(ch: Change, merge_base: str, head: str, docs: list[str], inv: types.ModuleType, cgd: types.ModuleType) -> list[str]`,
  returning `[]` when every changed generated document is allowed. In this task it applies two rules:
  - **Render inputs.** When any `RENDER_INPUTS` path is in `ch.changed`, each doc gets the reason
    `f"changes alongside {summarize(inputs)}, which decide the render; land that change first, then re-render"`.
  - **Same file.** Each doc must exist with the same mode at the merge base and the head (`Tree.raw`, `Tree.mode`), or
    it gets the reason `"is deleted, renamed or changes file mode; only its inventory block bodies may change"`.
  - The task ends fail-closed: every remaining doc gets `"is not yet checked against main's render"`. Task 8 replaces
    that line.
- `check_product_scope` changes:
  - `generated = [p for p in ch.changed if p in GENERATED_DOCS]`.
  - `mods = maintenance_modules() if generated else None`.
  - When `mods` is set, `errs += generated_doc_refusals(...)` and those paths skip the generic branch.
  - The generic refusal becomes exactly:
    `f"{path} changes in this feature change; under {PRODUCT_DOCS} only the FEAT's own catalog and traceability records, the model registry and its generated files, and, where the repository renders them, the inventory blocks of 05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md re-rendered by scripts/maintenance/doc_inventory.py ({GENERATED_RULE}) may change here"`.
- Produces (suite) the following:
  - Constants: `INFRA = "docs/product/infrastructure"`, `GENERATED = (f"{INFRA}/05-a-ARCHITECTURE.md", f"{INFRA}/05-c-DATA_DEPENDENCIES.md", f"{INFRA}/05-e-API.md")`,
    `API_DOC = GENERATED[2]`, `SNAPSHOT_FILE = "tests/fixtures/live_gcp_snapshot_2026-09-07.json"` and
    `MAIN_PY = "platform/api/main.py"`.
  - `RENDER_TREE = ("scripts/maintenance/__init__.py", "scripts/maintenance/doc_inventory.py", "scripts/maintenance/check_generated_docs.py", SNAPSHOT_FILE, MAIN_PY, "gcp/deploy.sh", "gcp/schema.sql", "scripts/discord/register_commands.py")`.
  - `TRACE_TEXT = "# Traceability\n\n### FEAT-MODEL-001\n\n- #1\n"`, `RULE = "REQ-GOV-004"` and
    `DOCS_OK = {"PR_TITLE": "FEAT-MODEL-001: x", "PR_BODY": body() + "\n\n## Capacity\nn/a: x\n"}`.
  - `skeleton(doc: str) -> str`: the line `# <name>`, then `Prose before the blocks.`, then for each name in
    `EXPECTED_MARKERS[doc]` (read from REPO's `check_generated_docs`): the start marker, an empty line, the end marker,
    and `Prose after <name>.`, all separated by blank lines.
  - `render(root: Path, docs: tuple[str, ...] = GENERATED) -> None`. It runs
    `[sys.executable, "-B", "-m", "scripts.maintenance.doc_inventory", "--root", ".", "--snapshot", SNAPSHOT_FILE, "--insert", *docs]`
    with `cwd=root` and `check=True`. The `-B` matters: a `__pycache__` would otherwise be committed by `git add -A`.
  - `moved_main() -> str`: REPO's `main.py` with four comment lines (`# moved by four lines, as stocks#1366 moved them`,
    `# two`, `# three`, `# four`) inserted after line 4, the end of its docstring.
  - `edit(text: str, old: str, new: str) -> str`: replaces the first `old`, and asserts that `old` is present so a case
    cannot silently become its control.
  - `refused(r: subprocess.CompletedProcess, fragment: str) -> bool`: true when `r.returncode == 1` and both `RULE` and
    `fragment` are in `r.stdout`.
  - Session fixture `inventory_template(tmp_path_factory) -> tuple[Path, dict[str, str]] | None`. It returns `None`
    unless `RENDERER_HERE`. Otherwise it runs `make_repo(dir)`. Then `on_base` writes `RENDER_TREE` from REPO, the
    three skeletons and `TRACEABILITY: TRACE_TEXT`, with `then=render`. On a scratch branch from `base` it writes
    `moved_main()`, renders, reads `{MAIN_PY, *GENERATED}` into `moved`, then checks out `main` with `-f` and deletes
    the scratch branch. The render must run inside this full repository, because `lib/` and `scripts/gate/` change the
    `modules` and table-reference blocks.
  - Function fixture `inventory_repo(inventory_template, tmp_path) -> tuple[Path, dict[str, str]] | None`. It calls
    `shutil.copytree(template, tmp_path / "repo", symlinks=True)` and returns the copy with `dict(moved)`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_the_gate_imports_the_renderer_only_for_a_generated_document(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        on_base(root, {"scripts/maintenance/doc_inventory.py": 'raise RuntimeError("doc_inventory imported")\n'})
        code_only = pr(root, BRANCH, CODE, **DOCS_OK)
        with_docs = pr(root, BRANCH, {**CODE, API_DOC: moved[API_DOC]}, **DOCS_OK)
        assert (code_only.returncode, with_docs.returncode != 0, "doc_inventory imported" in with_docs.stderr) == (0, True, True), \
            code_only.stdout + with_docs.stdout + with_docs.stderr

def test_a_checkout_without_the_renderer_refuses_generated_documents_as_before(repo):
    r = pr(repo, BRANCH, {**CODE, "docs/product/infrastructure/05-e-API.md": "# API\n"}, **DOCS_OK)
    assert r.returncode == 1 and "05-e-API.md changes in this feature change" in r.stdout and RULE in r.stdout \
        and "Traceback" not in r.stderr, r.stdout + r.stderr

def test_the_refusal_names_the_inventory_allowance(repo):
    r = pr(repo, BRANCH, {**CODE, "docs/product/13-ROADMAP.md": "# Roadmap\n"}, **DOCS_OK)
    assert r.returncode == 1 and "13-ROADMAP.md changes in this feature change" in r.stdout \
        and "re-rendered by scripts/maintenance/doc_inventory.py (REQ-GOV-004)" in r.stdout, r.stdout

def test_render_inputs_and_the_documents_themselves_stay_put(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        inputs, same = "which decide the render", "is deleted, renamed or changes file mode"
        cases = {   # name: (files, then, fragment); each differs from the #1366 head in one condition
            "doc_inventory.py changes": ({**moved, "scripts/maintenance/doc_inventory.py": (REPO / "scripts/maintenance/doc_inventory.py").read_text(encoding="utf-8") + "# touched\n"}, None, inputs),
            "check_generated_docs.py changes": ({**moved, "scripts/maintenance/check_generated_docs.py": (REPO / "scripts/maintenance/check_generated_docs.py").read_text(encoding="utf-8") + "# touched\n"}, None, inputs),
            "the docs test changes": ({**moved, "tests/scripts/test_check_generated_docs.py": "# touched\n"}, None, inputs),
            "the snapshot changes": ({**moved, SNAPSHOT_FILE: (REPO / SNAPSHOT_FILE).read_text(encoding="utf-8") + "\n"}, None, inputs),
            "05-e deleted": ({**moved, API_DOC: None}, None, same),
            "05-e renamed": ({**moved, API_DOC: None, f"{INFRA}/05-e-API-v2.md": moved[API_DOC]}, None, same),
            "05-e made executable": (moved, lambda r: (r / API_DOC).chmod(0o755), same),
        }
        outcomes = {k: pr(root, BRANCH, f, then=t, **DOCS_OK) for k, (f, t, _) in cases.items()}
        missed = {k: r.stdout[-400:] for k, r in outcomes.items() if not refused(r, cases[k][2])}
        assert missed == {}, missed
```

- [ ] **Step 2: Run them.** Command: `... -k "renderer_only or without_the_renderer or names_the_inventory_allowance or stay_put"`.
  Expected: `4 failed`.
- [ ] **Step 3: Implement** `maintenance_modules`, `generated_refusal`, the two rules of `generated_doc_refusals` with its
  fail-closed last line, and the `check_product_scope` changes.
- [ ] **Step 4: Run them.** Expected: `4 passed`. Then run `... -k "product_documents or product_records or docs_only_feature"`
  and expect all to pass, because main's message substrings are kept.
- [ ] **Step 5: Commit.** `feat(gate): load main's renderer for a generated document and keep its inputs fixed`.

## Task 5: Line endings, exact markers and only block bodies

Spec: § Design, "Exact markers" and "Only block bodies change". Advances done_when[1].

**Files:**
- Modify: `scripts/gate/spec_gate.py` (the REQ-GOV-004 block)
- Test: `tests/scripts/test_spec_gate.py`

**Interfaces:**
- Consumes: `generated_doc_refusals` and `generated_refusal` (Task 4). From main's modules: `inv.MARKER_START`,
  `inv.MARKER_END`, `cgd.EXPECTED_MARKERS` and `cgd._MARKER_LINE`.
- Produces: `split_inventory(raw: bytes, names: tuple[str, ...], start: str, end: str, marker_line: re.Pattern[str]) -> tuple[list[tuple[int, bytes]], list[tuple[str, list[bytes]]]]`.
  - It returns the lines outside every block body as `(line number, bytes)`, marker lines included, and the blocks as
    `(name, body lines)` in document order.
  - The document is split on `b"\n"` only.
  - A line is a marker line when `marker_line` matches it decoded as `utf-8` with `errors="replace"`. It must equal,
    byte for byte, `start.format(name=n)` or `end.format(name=n)` for an `n` in `names`.
  - It raises `ValueError` with a message beginning `marker lines:` for any of these: a marker line that is not exact; a
    start inside an open block; a name opened twice; an end that does not close the open block; a block left open; a
    name in `names` with no block.
- `generated_doc_refusals` gains three rules, in this order, after "same file":
  1. **Line endings.** When `b"\r" in head` and `b"\r" not in base`, the reason is
     `"adds carriage returns (CRLF line endings); commit it with LF line endings"`. This is Review Focus 4.
  2. **Markers.** `split_inventory` runs on both sides with `names = cgd.EXPECTED_MARKERS[doc]`. A `ValueError` becomes
     the reason, prefixed `on main: ` when it is the base side that fails. Differing name orders give the reason
     `f"marker lines: the blocks appear in another order than on main ({...})"`.
  3. **Outside bytes.** The outside contents must be equal. Otherwise the reason is
     `f"changes line {n} outside its inventory blocks"`, where `n` is the head line number of the first difference.
     This is Review Focus 2.

- [ ] **Step 1: Write the failing test.**

```python
def test_only_inventory_block_bodies_change(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        t = moved[API_DOC]
        rs, re_, ts = "<!-- inventory:routes:start -->", "<!-- inventory:routes:end -->", "<!-- inventory:routers:start -->"
        routers = t[t.index(ts):t.index("<!-- inventory:routers:end -->") + len("<!-- inventory:routers:end -->\n")]
        routes = t[t.index(rs):t.index(re_) + len(re_) + 1]
        n = t.split("\n").index("Prose after routes.") + 1
        first_body = t.index("\n", t.index(rs) + len(rs) + 1)          # the newline ending the routes block's first body line
        cases = {
            "a byte outside the blocks": (edit(t, "Prose after routes.", "Prose after routes!"), f"changes line {n} outside its inventory blocks"),
            "CRLF throughout": (t.replace("\n", "\r\n"), "carriage return"),
            "a CRLF inside a block body": (t[:first_body] + "\r" + t[first_body:], "carriage return"),
            "a marker added": (t + re_ + "\n", "marker lines"),
            "a marker removed": (edit(t, "<!-- inventory:routers:end -->\n", ""), "marker lines"),
            "a block moved": (edit(t.replace(routes, ""), ts, routes + ts), "marker lines"),
            "a marker renamed": (t.replace("inventory:routes:", "inventory:paths:"), "marker lines"),
            "a marker re-spaced": (edit(t, rs, "<!--  inventory:routes:start -->"), "marker lines"),
            "a block repeated": (edit(t, routers, routers + routers), "marker lines"),
            "a name 05-e does not carry": (edit(t, "Prose after routes.", "Prose after routes.\n<!-- inventory:jobs:start -->"), "marker lines"),
        }
        outcomes = {k: pr(root, BRANCH, {**moved, API_DOC: text}, **DOCS_OK) for k, (text, _) in cases.items()}
        missed = {k: r.stdout[-400:] for k, r in outcomes.items() if not refused(r, cases[k][1])}
        assert missed == {}, missed
```

- [ ] **Step 2: Run it.** Command: `... -k only_inventory_block_bodies`. Expected: `1 failed`, listing all ten cases. The
  fail-closed line refuses each one, but without its fragment.
- [ ] **Step 3: Implement** `split_inventory` and the three rules.
- [ ] **Step 4: Run it.** Expected: `1 passed`.
- [ ] **Step 5: Commit.** `feat(gate): allow only inventory block bodies to change in a generated document`.

## Task 6: Clean bytes

Spec: § Design, "Clean bytes". Advances done_when[1].

**Files:**
- Modify: `scripts/gate/spec_gate.py` (the REQ-GOV-004 block)
- Test: `tests/scripts/test_spec_gate.py`

**Interfaces:**
- Produces: `CLEAN_BYTES = re.compile(rb"\r|\x00|\xc2\x85|\xe2\x80[\xa8\xa9]")`. It is applied to each head block body,
  joined with `b"\n"`, after the outside-bytes rule.
- The reason is `f"inventory:{name} carries a carriage return, NUL, U+0085, U+2028 or U+2029, which the docs test reads past"`.
- Produces (suite): `ROUTE = '\n\n@app.get("/api/zz{}")\ndef zz_probe():\n    """Probe."""\n    return {{}}\n'`, filled with
  an escape sequence written as source text. It was verified on 2026-10-11 that each escape renders into one 05-a and
  two 05-e block lines.

- [ ] **Step 1: Write the failing test.**

```python
def test_a_block_carries_only_bytes_the_docs_test_sees(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        outcomes = {esc: pr(root, BRANCH, {MAIN_PY: moved_main() + ROUTE.format(esc)}, then=render, **DOCS_OK)
                    for esc in ("\\x00", "\\x85", "\\u2028", "\\u2029")}   # rendered from the route path, so only this rule refuses
        missed = {k: r.stdout[-400:] for k, r in outcomes.items() if not refused(r, "carries a carriage return, NUL, U+0085, U+2028 or U+2029")}
        assert missed == {}, missed
```

- [ ] **Step 2: Run it.** Command: `... -k only_bytes_the_docs_test_sees`. Expected: `1 failed`.
- [ ] **Step 3: Implement** the rule.
- [ ] **Step 4: Run it.** Expected: `1 passed`. Re-run `-k only_inventory_block_bodies` and expect it to pass.
- [ ] **Step 5: Commit.** `feat(gate): refuse block bytes the docs test reads past`.

## Task 7: A head tree of plain files, and the materializer

Spec: § Design, "Exact render", the tree half (`ls-tree -r -z`, `cat-file --batch`, the refused modes and components,
the containment check). Advances done_when[1].

**Files:**
- Modify: `scripts/gate/spec_gate.py` (the REQ-GOV-004 block)
- Test: `tests/scripts/test_spec_gate.py`

**Interfaces:**
- Produces: `head_entries(head: str) -> list[tuple[str, str, str]]`. It parses
  `git_bytes("ls-tree", "-r", "-z", "--full-tree", head)` into `(mode, oid, os.fsdecode(path))`.
- Produces: `tree_refusal(entries: list[tuple[str, str, str]]) -> str | None`. It names the first problem, in one of
  these forms:
  - `f"a symbolic link ({path})"` for mode `120000`
  - `f"a submodule ({path})"` for mode `160000`
  - `f"a .gitattributes ({path})"` when the last component, lower-cased, is `.gitattributes`
  - `f"a path component {c!r} ({path})"` for a component that is empty or, lower-cased, is `.`, `..` or `.git`
- Produces: `materialize(entries: list[tuple[str, str, str]], into: pathlib.Path) -> None`. It runs one
  `git cat-file --batch` (cwd `ROOT`) and writes each blob's exact bytes to `into / path`. Before writing, it raises
  `ValueError("... outside ...")` when `os.path.realpath` of the target is not under `os.path.realpath(into) + os.sep`.
- In `generated_doc_refusals`, after the per-document rules pass:
  - When `head_entries` raises `GitFailed`, the result is one refusal for `", ".join(docs)` with reason
    `f"the head tree cannot be listed ({e})"`.
  - When `tree_refusal` finds a problem, the reason is `f"the head tree holds {why}; the render reads plain files only"`.
  - Ruling: git itself cannot list an empty component. `ls-tree -r` exits 128 with
    `fatal: empty filename in tree entry`, measured on 2026-10-11, so that case is refused by the listing rule. The
    component check still names `""` for completeness.
- Produces (suite):
  - `mktree(root: Path, lines: str) -> str` runs `git mktree` over `lines` and returns the tree id.
  - `spliced(root: Path, entry: str) -> tuple[str, str]` returns `(base, head)` rebuilt with one more root entry
    `vendor`, a tree made from the single ls-tree line `entry`, in both commits. The head commit is parented on the
    base commit, so the entry sits in the head tree and never in the diff. Call it after `pr()`, on its HEAD.
  - The splicing approach was verified on 2026-10-11. `git diff --name-only` skips an unchanged `vendor/`, and
    `ls-tree -r` lists `vendor/../x`, `vendor/./x` and `vendor/.GIT/x`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_the_head_tree_is_plain_files(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        outcomes = {f".gitattributes {a}": (pr(root, BRANCH, {**moved, ".gitattributes": f"{API_DOC} {a}\n"}, **DOCS_OK), "a .gitattributes")
                    for a in ("export-subst", "eol=crlf", "ident")}
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input="../gcp/schema.sql", cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        x = mktree(root, f"100644 blob {blob}\tx\n")
        entries = {"a symbolic link": (f"120000 blob {blob}\tlink", "a symbolic link"),
                   "a submodule": (f"160000 commit {_git(root, 'rev-parse', 'base')}\tsub", "a submodule"),
                   "an empty component": (f"040000 tree {x}\t", "cannot be listed"),
                   **{f"component {c}": (f"040000 tree {x}\t{c}", "a path component") for c in (".", "..", ".git", ".GIT")}}
        for name, (entry, fragment) in entries.items():
            pr(root, BRANCH, moved, **DOCS_OK)
            b, h = spliced(root, entry)
            outcomes[name] = (gate(root, "--pr", b, h, PR_HEAD_REF=BRANCH, **DOCS_OK), fragment)
        missed = {k: r.stdout[-400:] for k, (r, fragment) in outcomes.items() if not refused(r, fragment)}
        assert missed == {}, missed

def test_materialize_writes_inside_its_directory_only(repo, tmp_path_factory):
    sg = load_gate(repo)
    oid, out = _git(repo, "rev-parse", "base:lib/model.py"), tmp_path_factory.mktemp("tree")
    with pytest.raises(ValueError, match="outside"):
        sg.materialize([("100644", oid, "../escape.py")], out)
    sg.materialize([("100644", oid, "lib/model.py")], out)
    assert (out / "lib/model.py").read_bytes() == b"DECISION = 'size'\n" and not (out.parent / "escape.py").exists()
```

- [ ] **Step 2: Run them.** Command: `... -k "head_tree_is_plain_files or materialize_writes"`. Expected: `2 failed`.
  If another check refuses a spliced case first, without `REQ-GOV-004`, record it as a finding against the spec. Do not
  weaken the case.
- [ ] **Step 3: Implement** `head_entries`, `tree_refusal` and `materialize`, and wire the listing and tree rules.
- [ ] **Step 4: Run them.** Expected: `2 passed`.
- [ ] **Step 5: Commit.** `feat(gate): refuse a head tree the render cannot read as plain files`.

## Task 8: Main's render in a fenced child, and the acceptance

Spec: § Design, "Exact render", the child half; § Capacity. Advances done_when[0] and done_when[1] (the hand edit, the
outside open, and the controls).

**Files:**
- Modify: `scripts/gate/spec_gate.py`. Change the REQ-GOV-004 block, replacing Task 4's fail-closed line. Change `run`
  (`:4027`) so its first branch is `if mode == RENDER_MODE: return render_inventory(argv[2], argv[3:])`. Leave it out of
  the usage docstring: the mode is hidden.
- Test: `tests/scripts/test_spec_gate.py`

**Interfaces:**
- Produces these constants: `RENDER_MODE = "--render-inventory"`, `RENDER_PREIMPORTS = ("inspect",)`,
  `RENDER_DIFFERS = 3`, `RENDER_MISPLACED = 4` and `RENDER_ESCAPED = 86`.
  - `RENDER_PREIMPORTS` is exactly `("inspect",)`. `ast.get_docstring` imports `inspect` lazily. On the fixture tree,
    with Python 3.11.15, 3.12 and 3.13, a render without it opened `inspect.cpython-3*.pyc` behind the fence. With it
    the render was clean, and on main's full tree with 3.11 nothing else opened.
- Produces: `render_refusals(entries: list[tuple[str, str, str]], docs: list[str]) -> list[str]` (the parent).
  - It creates a `tempfile.TemporaryDirectory(prefix="spec-gate-render-")` holding `tree/` (written by `materialize`)
    and `run/`, the child's cwd, which lies outside the tree.
  - It runs `subprocess.run([sys.executable, "-I", "-B", str(pathlib.Path(__file__).resolve()), RENDER_MODE, str(tree), *docs], cwd=run, capture_output=True, encoding="utf-8", errors="replace")`.
  - It maps the exit code as follows. "Last stderr line" is `stderr.strip().splitlines()[-1]`.
    - `0`: `[]`.
    - `RENDER_DIFFERS`: one refusal per stdout line `doc\tname\tfirst difference`. The reason is
      `f"inventory:{name} differs from main's render; first difference: {diff}. Re-render with: python3 -m scripts.maintenance.doc_inventory --snapshot {RENDER_SNAPSHOT} --restore {doc}"`.
      This is Review Focus 1.
    - `RENDER_ESCAPED`: `f"main's renderer read outside this pull request's files ({last stderr line})"`. This is
      Review Focus 3.
    - `RENDER_MISPLACED`: `f"main's renderer was imported from outside this checkout ({last stderr line})"`.
    - Anything else: `f"main's renderer failed on this pull request's files (exit {rc}): {last stderr line}"`. This is
      Review Focus 5.
- Produces: `render_inventory(tree: str, docs: list[str]) -> int` (the child). It works in this order:
  1. It inserts `str(ROOT)` at `sys.path[0]`, imports `scripts.maintenance.doc_inventory`, and returns
     `RENDER_MISPLACED` (writing the module's path to stderr) when its `__file__` does not resolve to
     `ROOT / "scripts/maintenance/doc_inventory.py"`.
  2. It loads `json.loads((ROOT / RENDER_SNAPSHOT).read_text(encoding="utf-8"))` and imports each `RENDER_PREIMPORTS`.
  3. It calls `sys.addaudithook(render_fence(os.path.realpath(tree)))`.
  4. It builds `repo = inv.repo_inventory(pathlib.Path(tree))`, then calls
     `inv.differing_blocks(pathlib.Path(tree) / doc, repo, live, root=pathlib.Path(tree))` for each doc.
  5. It prints the tab-separated lines and returns `RENDER_DIFFERS`, or returns `0` when nothing differs.
- Produces: `render_fence(root: str) -> Callable[[str, tuple], None]`, which handles the audit events `open`,
  `os.listdir` and `os.scandir`.
  - A path argument (`str`, `bytes` or `PathLike`; `None` means `"."`) whose `os.path.realpath` is neither `root` nor
    under `root + os.sep` is fenced.
  - For a fenced path it writes `f"opened {path}\n"` to fd 2 and calls `os._exit(RENDER_ESCAPED)`. It exits rather than
    raising, because the renderer's own `except OSError` would swallow an exception.
  - Integer fds are ignored. Each was opened through a path that was already checked.
- `generated_doc_refusals` returns `render_refusals(entries, docs)` after the tree rule.
- Produces (suite): `JOB = "\ndeploy_evil_job() {{\n    gcloud run jobs deploy evil-job \\\n        --command python3 \\\n        --args {}\n}}\n"`.
  It was verified on 2026-10-11: with the absolute path the fence exits 86, and with `gcp/evil_job.py` the render opens
  nothing outside the tree.

- [ ] **Step 1: Write the failing tests.**

```python
def test_a_feature_change_carries_its_re_rendered_inventory_blocks(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        own = edit(CATALOG_TEXT, "### FEAT-MODEL-001\n\n- Status: Production", "### FEAT-MODEL-001\n\n- Status: Production\n- Note: cited lines moved")
        r = pr(root, BRANCH, {**moved, CATALOG: own, TRACEABILITY: TRACE_TEXT + "- #7\n"}, **DOCS_OK)
        changed = set(_git(root, "diff", "--name-only", "base", "HEAD").splitlines())
        assert r.returncode == 0 and changed == {MAIN_PY, *GENERATED, CATALOG, TRACEABILITY}, r.stdout + r.stderr

def test_a_block_must_equal_mains_render(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        hand = pr(root, BRANCH, {**moved, API_DOC: edit(moved[API_DOC], "Liveness probe:", "Liveness probe, hand-edited:")}, **DOCS_OK)
        broken = pr(root, BRANCH, {**moved, MAIN_PY: moved_main() + "\ndef broken(:\n"}, **DOCS_OK)
        missed = [k for k, ok in {
            "hand edit": refused(hand, "differs from main's render") and f"--restore {API_DOC}" in hand.stdout and SNAPSHOT_FILE in hand.stdout,
            "renderer failure": refused(broken, "renderer failed") and "SyntaxError" in broken.stdout and "Traceback" not in broken.stderr,
        }.items() if not ok]
        assert missed == [], hand.stdout + broken.stdout + broken.stderr

def test_the_render_reads_only_the_pull_requests_files(inventory_repo, tmp_path_factory):
    if RENDERER_HERE:
        root, moved = inventory_repo
        outside = tmp_path_factory.mktemp("outside") / "evil_job.py"
        outside.write_text('"""A job entrypoint outside the tree."""\n', encoding="utf-8")
        deploy = (REPO / "gcp/deploy.sh").read_text(encoding="utf-8")
        escaped = pr(root, BRANCH, {MAIN_PY: moved_main(), "gcp/deploy.sh": deploy + JOB.format(outside)}, then=render, **DOCS_OK)
        inside = pr(root, BRANCH, {MAIN_PY: moved_main(), "gcp/evil_job.py": outside.read_text(encoding="utf-8"),
                                   "gcp/deploy.sh": deploy + JOB.format("gcp/evil_job.py")}, then=render, **DOCS_OK)
        assert (refused(escaped, "read outside this pull request's files"), "evil_job.py" in escaped.stdout, inside.returncode) == (True, True, 0), \
            escaped.stdout + inside.stdout

def test_the_refused_heads_have_accepted_controls(inventory_repo):
    if RENDERER_HERE:
        root, moved = inventory_repo
        route = pr(root, BRANCH, {MAIN_PY: moved_main() + ROUTE.format("")}, then=render, **DOCS_OK)   # Task 6's route, no escape
        pr(root, BRANCH, moved, **DOCS_OK)
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input="x", cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        x = mktree(root, f"100644 blob {blob}\tx\n")
        b, h = spliced(root, f"040000 tree {x}\tok")   # Task 7's splice, a plain entry
        plain = gate(root, "--pr", b, h, PR_HEAD_REF=BRANCH, **DOCS_OK)
        assert (route.returncode, plain.returncode) == (0, 0), route.stdout + plain.stdout
```

- [ ] **Step 2: Run them.** Command:
  `... -k "carries_its_re_rendered or equal_mains_render or reads_only_the_pull_requests or accepted_controls"`.
  Expected: `4 failed`.
- [ ] **Step 3: Implement** the constants, `render_refusals`, `render_inventory`, `render_fence` and the `run` branch,
  and remove Task 4's fail-closed line.
- [ ] **Step 4: Run every new test.** Command: `... -k "<the 20 new test names, or-joined>" --durations=0`. Expected: all
  pass, and the sum of their durations is ≤ 60 s.
- [ ] **Step 5: Check capacity on main's full tree.**

```bash
python3 - <<'EOF'
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("sg", "scripts/gate/spec_gate.py"); sg = importlib.util.module_from_spec(spec)
sys.modules["sg"] = sg; spec.loader.exec_module(sg)
t = time.time(); print(sg.render_refusals(sg.head_entries("HEAD"), list(sg.GENERATED_DOCS)), f"{time.time() - t:.1f}s")
EOF
```

  Expected: `[]` and roughly 40 s. On 2026-10-11, 498d0ad1's tree took 37.2 s to render and 1.9 s to write. It must stay
  well under the gate job's 300 s.

- [ ] **Step 6: Commit.** `feat(gate): render main's inventory over the pull request's files in a fenced child`.

## Task 9: The skill names the allowance

Spec: § Design (the allowance). Advances done_when[7]. Task 4 already changed the refusal text.

**Files:**
- Modify: `.claude/skills/product-delivery/SKILL.md:83` (the third "Never" bullet)
- Test: `tests/scripts/test_spec_gate.py`

**Interfaces:**
- The bullet becomes exactly this:

  `- Never edit \`docs/product/\` from a feature branch except the one FEAT row or record and the traceability entry this PR owns, the \`07-MODEL-REGISTRY.md\` rows for models this spec changes, the \`generated/model-registry.json\` that step 4 regenerates, and, in stocks, the inventory blocks of \`infrastructure/05-a-ARCHITECTURE.md\`, \`05-c-DATA_DEPENDENCIES.md\` and \`05-e-API.md\` re-rendered by \`scripts/maintenance/doc_inventory.py\` when the change moves what they cite (REQ-GOV-004: the blocks only, exactly as main's renderer renders them, never in the same PR as a change to the renderer, \`check_generated_docs.py\`, its test or its snapshot).`

  The words "in stocks" keep the file true in solyra, where it is byte-identical.

- [ ] **Step 1: Write the failing test.**

```python
def test_the_skill_names_the_inventory_allowance():
    skill = (REPO / ".claude/skills/product-delivery/SKILL.md").read_text(encoding="utf-8")
    never = next(line for line in skill.splitlines() if line.startswith("- Never edit `docs/product/` from a feature branch"))
    assert "REQ-GOV-004" in never and "re-rendered by `scripts/maintenance/doc_inventory.py`" in never, never
```

- [ ] **Step 2: Run it.** Expected: `1 failed`.
- [ ] **Step 3: Edit the bullet.**
- [ ] **Step 4: Run it.** Expected: `1 passed`.
- [ ] **Step 5: Commit.** `docs(skill): name the re-rendered inventory blocks a feature change may carry`.

## Task 10: Red team before the one push

Spec: § Design, the last-but-one paragraph (the red team and the pinned files); CLAUDE.md "Before any change". Advances
done_when[6].

- [ ] **Step 1: Confirm the pinned files are untouched.**
  `git diff --quiet origin/main -- scripts/gate/pinned .github/workflows/spec-gate.yml .github/workflows/registry-check.yml .githooks/pre-commit && echo untouched`
  Expected: `untouched`.
- [ ] **Step 2: Dispatch four reviewers in parallel** on the branch head, using `superpowers:dispatching-parallel-agents`.
  Each must prove a bypass by running `python3 scripts/gate/spec_gate.py --pr <base> <head>`, or the suite's helpers,
  against a concrete snippet, and must report the snippet, the command and the observed output. Nothing else counts as
  a finding.
  1. **Shell.** Every subprocess the change adds: `git diff`, `ls-tree`, `cat-file --batch` and the `-I -B` child, with
     their argv, cwd, environment and exit codes. Also ref and path arguments that git could read as an option or as
     pathspec magic.
  2. **YAML/Actions.** Which side's renderer each job imports and with which Python:
     - `spec-gate.yml`'s `gate` job: base checkout, `fetch-depth: 0`, `pip install pyyaml`, 5-minute timeout.
     - Its `base-suite` job.
     - `registry-check.yml`: head checkout, the PR's own suite, 5-minute timeout.

     Also the suite's runtime against registry-check's 300 s.
  3. **Exporter and policy documents.**
     - The SKILL.md wording, the refusal texts and REQ-GOV-004.
     - The behaviours of `doc_inventory.py` and `check_generated_docs.py` that the allowance trusts: `EXPECTED_MARKERS`,
       `_MARKER_LINE`, and `_block_bodies`' substring search and first match.
     - The catalog and traceability scope check.
  4. **Diff and byte parsing, and the render check.**
     - `changed_lines`, `lines_of`, `split_inventory`, `CLEAN_BYTES`, the tree rules and `materialize`.
     - The fence's uncovered paths: `os.open` with `dir_fd`, `io.open_code`, `mmap`, stat-based probes, a symlink
       created mid-render, and `chdir`.
     - `RENDER_PREIMPORTS` on 3.12 and 3.13 (`/usr/bin/python3.12`, `/usr/bin/python3.13`).
- [ ] **Step 3: Fix every confirmed finding in one batch.** Each finding gets a regression case, either in the owning
  test's case table or as a new test, and each case is shown failing before its fix. Commit:
  `fix(gate): close red-team round <n> findings`.
- [ ] **Step 4: Re-run all four reviewers on the new head.** Repeat Steps 3 and 4 until every reviewer reports nothing.
- [ ] **Step 5: Record the findings** as a table for the PR body, with columns round, reviewer, finding, snippet, and the
  test that now refuses it.

## Task 11: Evidence: the full suite, the base-suite job, and RED against main

Spec: § Capacity. Advances done_when[5].

- [ ] **Step 1: Run the full suite on the head.**
  `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest --durations=0 | tee "$SCRATCH/suite-head.txt"`
  Expected: `116 passed`, plus any red-team tests (96 on main and 20 new). The new tests' durations sum to ≤ 60 s.
  If they exceed it, move work into `inventory_template`. Never raise a timeout here.
- [ ] **Step 2: Run the neighbouring suites.**
  `python3 -m pytest tests/scripts/test_check_generated_docs.py tests/scripts/test_export_model_registry.py -q -p no:cacheprovider`
  Expected: all pass, since the renderer is unchanged.
- [ ] **Step 3: Run the base-suite job exactly as `spec-gate.yml` does.**

```bash
git -C "$WT" worktree add "$SCRATCH/base-suite" origin/main
cp "$WT/scripts/gate/spec_gate.py" "$WT/scripts/gate/export_model_registry.py" "$SCRATCH/base-suite/scripts/gate/"
cd "$SCRATCH/base-suite" && time python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest \
  && python3 -m pytest tests/scripts/test_export_model_registry.py -q -p no:cacheprovider --noconftest
git -C "$WT" worktree remove --force "$SCRATCH/base-suite"
```

  Expected: `96 passed` and the exporter suite passes. Wall time is about 270 s, against the job's 600 s limit.
- [ ] **Step 4: Run RED against main.** Use a worktree of the head with main's gate and main's SKILL.md swapped in:

```bash
git -C "$WT" worktree add "$SCRATCH/red" HEAD
git -C "$WT" show origin/main:scripts/gate/spec_gate.py > "$SCRATCH/red/scripts/gate/spec_gate.py"
git -C "$WT" show origin/main:.claude/skills/product-delivery/SKILL.md > "$SCRATCH/red/.claude/skills/product-delivery/SKILL.md"
cd "$SCRATCH/red" && python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest -rf -k "<every new test name, or-joined>"
git -C "$WT" worktree remove --force "$SCRATCH/red"
```

  Expected: every new test is `FAILED` and none passes. Each case table fails in one assertion that lists every case
  main got wrong, so each case is shown failing. Keep the `FAILED … - AssertionError: …` lines for the PR body.

## Task 12: One push, the draft PR, and the close-out

Spec: § Design (none of the pinned files change) and done_when. Advances done_when[8], done_when[9], and the CI half of
done_when[5].

- [ ] **Step 1: Run the gate against main.** `python3 scripts/gate/spec_gate.py --pr origin/main`. Expected:
  `spec gate ok (branch=feature/feat-cicd-001-generated-docs-render, 4 changed file(s))`, plus one per red-team file
  if any.
- [ ] **Step 2: Diff the docs audit.** Run `python3 scripts/maintenance/docs_audit.py > "$SCRATCH/audit-branch.txt"` here
  and in a worktree of `origin/main` (about 40 s each, measured). Then
  `comm -13 <(sort "$SCRATCH/audit-main.txt") <(sort "$SCRATCH/audit-branch.txt")`. Expected: no output.
- [ ] **Step 3: Make the one push.** `git push -u origin feature/feat-cicd-001-generated-docs-render`.
- [ ] **Step 4: Open the draft PR.** Title: `FEAT-CICD-001: let a feature change carry its re-rendered inventory blocks`.
  The body contains:
  - The spec and plan paths.
  - The ten done_when items as `- [ ] <exact text>` lines.
  - The RED evidence from Task 11.
  - The red-team table from Task 10.
  - A Capacity section:
    - Volume: the head tree, 1,514 files and 186 MiB on 498d0ad1, written once per PR that changes a generated
      document.
    - Velocity: one `ls-tree`, one `cat-file --batch` and one child process per such PR, and none otherwise.
    - Wall-clock: about 40 s (37.2 s render and 1.9 s write, measured) inside the gate job's 300 s. The suite adds about
      60 s locally, about 47 s in CI, to registry-check's 231 s of 300 s.
    - Cost: a public repository on standard runners, so $0 × runs/day × 30 = $0.
- [ ] **Step 5: Wait for review and read the CI timing.** Follow CLAUDE.md §2.5 before any merge. With
  `mcp__github__actions_list` (`list_workflow_jobs`), read registry-check's job duration. Expected: under 285 s. If it
  is not, stop and raise it with the owner. The timeout is pinned, so raising it is the two-PR procedure, not a fix in
  this PR.
- [ ] **Step 6: Write the close-out commit,** which touches no gate file.
  - Set the plan's `pr:` to the PR number.
  - In the FEAT-CICD-001 record in `docs/product/02-FEATURE-CATALOG.md`, set Last reviewed to the head commit date and
    keep Status `Production but needs remediation`.
  - In `docs/product/12-PR-ISSUE-TRACEABILITY.md:419` (FEAT-CICD-001's `**PR lineage:**`), append
    ` · [#<N>](https://github.com/TeneikaAskew/stocks/pull/<N>) *gate*`.
  - Run `PR_NUMBER=<N> PR_DRAFT=false PR_TITLE="…" PR_BODY="$(cat body.md)" python3 scripts/gate/spec_gate.py --pr origin/main`.
    Expected: `spec gate ok`.
  - `git diff --name-only HEAD~1 HEAD` lists only the plan, 02 and 12.
  - Commit `docs(product): record FEAT-CICD-001's review and this PR`, then push.
- [ ] **Step 7: Mark the PR ready.** Tick each done_when box with its evidence (test name, command or file), then mark
  the PR ready for review.

Ruling: "the PR's one push" (done_when[6]) means the one push that carries the gate change. The close-out needs the PR
number, so it follows the draft PR in a second push that changes no gate file.

---

## Solyra (not this plan's PR)

These three files are byte-identical on both mains today, and the identity is kept only by convention:
`scripts/gate/spec_gate.py`, `tests/scripts/test_spec_gate.py` and `.claude/skills/product-delivery/SKILL.md`.

- **Evidence that they match.** The sha256 prefixes are equal at stocks 2a108675 and solyra 3546641: `aa259cfa0151`,
  `7ee523785cc0` and `039c440cbf7c`.
- **Evidence that nothing enforces it.** No workflow or test in either repo reads the other repo's copy. The only
  statement of the convention is `tests/scripts/test_spec_gate.py:6`.
- **Precedent.** Every gate change so far has landed as a pair: #1205/#72, #1343/#228 and #1375/#245.

This plan keeps all three files portable:

- The allowance is inert without `scripts/maintenance/`.
- The renderer tests run only where `RENDERER_HERE` is true.
- The skill bullet says "in stocks".

To keep the convention, solyra needs one PR after this one merges, on `feature/feat-cicd-001-<slug>`, carrying the
three files byte-identical to stocks main.

- **It needs a feature branch.** SKILL.md is a process file that `chore/` cannot carry, because `chore_allows` returns
  `""` for it.
- **It needs solyra's own approved spec and plan.** The spec is merged first on `docs/spec-feat-cicd-001-<slug>`, with
  `req_ids: [REQ-GOV-004]`.
- **It needs its own gate-file red team.** Solyra's CLAUDE.md carries the same rule.
- **A `chore/` PR could carry only `spec_gate.py` and the suite,** as #245 did, which would leave SKILL.md divergent.

The gate reads `doc_inventory` only where `scripts/maintenance/` exists, and solyra has neither that directory nor the
generated documents. So solyra keeps today's refusal, with the new text.
