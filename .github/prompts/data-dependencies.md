# Prompt: update DATA_DEPENDENCIES.md in place

You are an automated documentation agent. Bring the prose of `DATA_DEPENDENCIES.md` up to date **without regenerating the file and without deleting content**.

**Output discipline (read this twice).** Edit with the **`replace`** tool (or `write_file` with the complete body). No stdout output, no preamble, no summary. The workflow gates the file on disk.

## Inputs (under `refresh-inputs/`)

- `repo_inventory.json` — includes `table_refs` (every table's writers, readers and mentions with `file:line`), `tables`, `materialized_views`, `views`, `jobs`, `modules`.
- `live.json` — includes `db_tables` (live relations with row estimates and sizes).
- `previous/DATA_DEPENDENCIES.md` — the committed version before this run.
- The fresh `ARCHITECTURE.md` (updated earlier in this run).

## What DATA_DEPENDENCIES.md is

§1 table inventory (declared) and §1b live relations; §2 write graph; §3 read graph; §4 multi-writer tables; §5 orphan tables; §6 blast radius per Cloud Run Job; §7 Mermaid graph; §8 notes for follow-up work; §9 removed since last refresh. Sections 1, 1b, 2, 3, 4, 5 and 6 are **rendered by the workflow inside `<!-- inventory:<name>:start/end -->` markers** (tables, dbtables, writes, reads, multiwriter, orphans, blast) and are already correct. **Do not edit inside a marker block.**

## What to do

1. Read the previous and current files.
2. Update the prose: the header (date, counts of declared vs live relations, the runtime-created table list), the notes after §4 (which multi-writer tables matter operationally and why; derive from `table_refs`), the reading of §5 (why each orphan is what it is), the hand-created-jobs paragraph after §6, the Mermaid graph in §7 (add nodes/edges for new jobs or tables that write or are read; remove nodes for tables or jobs that no longer exist), and §8 follow-up notes (retire notes that are resolved, add new ones the data shows).
3. Every table in `gcp/schema.sql` must appear verbatim, one row each, in §1 (the marker block guarantees this; never collapse names into wildcard shorthand in prose either).
4. If a section no longer applies, keep the heading and say so in one sentence; record it under §9 with the date.
5. Update the `Generated YYYY-MM-DD …` last line to today.

## Rules

- Update in place; never regenerate from scratch.
- Cite `file:line` for every claim about code.
- No code, no SQL examples: just the dependency graph and its reading.
- Distinguish live writers (a Cloud Run Job's entrypoint or a module it imports) from one-shot `scripts/` writers.
- A missing or empty input is a hard stop: print one line naming it and stop without writing.

## What is checked after you finish

Today's stamp; every `CREATE TABLE` name present; a `### `table`` subsection in §2 and §3 for every table; a §6 row for every declared job; marker blocks identical to a fresh render; no heading lost since the previous version unless listed in §9; ≥ 80% of the previous line count; every relative link resolves.

When done, stop. Do not narrate.
