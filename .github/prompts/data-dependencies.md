# Prompt: update docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md in place

You are an automated documentation agent. Bring the prose of `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md` up to date **without regenerating the file and without deleting content**.

**Output discipline (read this twice).** The file is `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`, given from the repository root: `file_path: "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md"`, never a bare `DATA_DEPENDENCIES.md` at the root and never any other directory. Edit that path only with the **`replace`** tool, one prose region at a time, on the exact current text. Never call `write_file` on this document: the rendered blocks are most of its 120 KB and a rewrite of the whole body is exactly the output that kept timing out. Do not create a second copy anywhere. A file written outside the four generated documents fails the run by name and nothing is published — run 15 died exactly that way, having written `docs/DATA_DEPENDENCIES.md`. No stdout output, no preamble, no summary. The workflow gates the file on disk.

## Live fleet counts — authoritative, already substituted below

- Cloud Run Jobs: **{{LIVE_JOBS}}** live, **{{DECLARED_JOBS}}** declared in `gcp/deploy.sh`
- Cloud Scheduler jobs: **{{LIVE_SCHEDULERS}}** live, **{{DECLARED_SCHEDULERS}}** declared
- Cloud Run Services: **{{LIVE_SERVICES}}**
- Secret Manager secrets: **{{LIVE_SECRETS}}**
- Cloud SQL relations: **{{LIVE_DB_TABLES}}** live, **{{DECLARED_RELATIONS}}** declared in `gcp/schema.sql` (tables, views and materialized views together), **{{RUNTIME_RELATIONS}}** runtime-created (live minus declared, as a set difference)

These numbers were read from `live.json` and `repo_inventory.json` and written
into this prompt by `scripts/maintenance/render_doc_prompts.py` before you were
called. They are correct as of this run. **Use them verbatim wherever the
document states a count.** Do not recount them from an input file, do not
derive a count by counting entries you can see in a truncated read, and do not
carry one forward from the previous version of the document. A 2026-09-07 run wrote a
scheduler count under half the live figure and went red on that single line.

## Inputs (under `refresh-inputs/`)

- `table_refs_digest.md` — the multi-writer tables with their writers cited `file:line`, the orphan tables with their status (partitions marked as such) and the writers or readers that do exist cited `file:line`, every declared job's written and read tables with the reached statements cited `file:line` (a row of dashes is a job that touches no table statically, not a missing job; a table marked **(runtime-created)** is one `gcp/schema.sql` does not declare: it appears in the digest's job rows and nowhere in the rendered blocks; a group written **one of `template` (name assembled at run time)** is a family the job builds from a template whose placeholder the static read cannot pin down, so write about the family and never assert that the job touches a particular member), the **runtime-created relations** (live relations `gcp/schema.sql` does not declare, with kind, rows and size) and the **hand-created live jobs** (live jobs with no `deploy_*` function, with their entry module and tables). This is the same data the rendered blocks come from, already digested, plus the two live-only name sets the prose states; `live.json` and the §1b block are not inputs, so every runtime-relation and hand-created-job name you write comes from here. **Do not open `repo_inventory.json`**: it is 400 KB, and the 220 KB reference graph inside it is what this digest and the §2/§3/§4/§5/§6/§7 blocks were rendered from.
- The current `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`. Read only the prose you may edit (named below) with `read_file` `offset`/`limit`; the rendered blocks between markers are ~120 KB of the file and are not yours to read or change. The previous version under `previous/` differs from the current one inside those blocks and in the one prose line carrying the **runtime-relation count**, which the workflow renders into the current file before you run; the current file's number is correct and the previous one is stale by construction. There is nothing else to compare.
- The fresh `docs/product/infrastructure/05-a-ARCHITECTURE.md` §5 only, if you need the domain grouping of tables.

## What docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md is

§1 table inventory (declared) and §1b live relations; §2 write graph; §3 read graph; §4 multi-writer tables; §5 orphan tables; §6 blast radius per Cloud Run Job; §7 Mermaid graph; §8 notes for follow-up work; §9 removed since last refresh. Sections 1, 1b, 2, 3, 4, 5, 6 **and the §7 graph** are **rendered by the workflow inside `<!-- inventory:<name>:start/end -->` markers** (tables, dbtables, writes, reads, multiwriter, orphans, blast, graph) and are already correct. **Do not edit inside a marker block.** A block you edit is restored from the render and the run reports it by name.

## What to do

1. Read `table_refs_digest.md`, then the prose sections below in the current file.
2. Update only these prose regions, each with the **`replace`** tool on the exact current text: the header lines (date, the counts from the **Live fleet counts** block above, the runtime-created table list from the digest's **Runtime-created relations** section), the notes after the §4 block (which multi-writer tables matter operationally and why, from the digest), the reading after the §5 block (why each orphan is what it is, from the digest), the hand-created-jobs paragraph after the §6 block (from the digest's **Hand-created live jobs** section: names, entry modules and tables come from there, not from memory), the one-paragraph reading under §7 (the graph itself is rendered; you do not draw it), and §8 follow-up notes (retire notes that are resolved, add new ones the digest shows). Nothing else.
3. Every table in `gcp/schema.sql` must appear verbatim, one row each, in §1 (the marker block guarantees this; never collapse names into wildcard shorthand in prose either).
4. If a section no longer applies, keep the heading and say so in one sentence; record it under §9 with the date.
5. Update the `Generated YYYY-MM-DD …` last line to today.

## Rules

- Never read or write anything under `docs/product/infrastructure/manual/`: it holds the hand-maintained copies of these documents and is outside the write policy; a change there fails the run.
- Update in place with `replace` only; never regenerate from scratch and never `write_file` the document (the output-discipline paragraph above says the same: there is no whole-body path).
- Cite `file:line` for every claim about code.
- No code, no SQL examples: just the dependency graph and its reading.
- Distinguish live writers (a Cloud Run Job's entrypoint or a module it imports) from one-shot `scripts/` writers.
- A missing or empty input is a hard stop: print one line naming it and stop without writing.

## What is checked after you finish

Today's stamp; every `CREATE TABLE` name present; a `### `table`` subsection in §2 and §3 for every table; a §6 row for every declared job; marker blocks identical to a fresh render; no heading lost since the previous version unless listed in §9; ≥ 80% of the previous line count; every relative link resolves.

When done, stop. Do not narrate.
