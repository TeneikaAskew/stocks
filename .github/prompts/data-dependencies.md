# Prompt: regenerate DATA_DEPENDENCIES.md

You are an automated documentation agent. Regenerate `DATA_DEPENDENCIES.md` from scratch.

**Output discipline (read this twice).** Produce the regenerated file by calling the **`write_file` tool** with `file_path: "DATA_DEPENDENCIES.md"` and the full markdown body as `content`. **Do not** print the file contents to stdout, write a preamble like "Here's the regenerated doc:", or summarize what you did at the end. The workflow inspects the file on disk; any text you emit beyond tool calls is noise.

## Inputs

- The full repo tree (for code-level grep)
- `gcp/schema.sql` — the canonical list of Cloud SQL tables. Get it via `grep -E "^CREATE TABLE" gcp/schema.sql`.
- The fresh `ARCHITECTURE.md` (regenerated earlier in the same workflow run) — for the Cloud Run Job → code-module mapping
- The previous `DATA_DEPENDENCIES.md` if one exists (style reference)

## What to produce

`DATA_DEPENDENCIES.md` at the repo root with these sections:

### 1. Table inventory

A markdown table: Table | One-line purpose. Cover every table in `schema.sql`. Purpose comes from schema comments + your read of the field set.

### 2. Write graph

For every table, a subsection listing every code module that writes to it. A "write" is any of:
- `INSERT INTO <table>` / `UPDATE <table>` / `DELETE FROM <table>`
- `upsert_dataframe(..., '<table>', ...)` (the `gcp/database.py` helper)
- `bulk_insert_dataframe(..., '<table>', ...)`
- `execute_sql("INSERT INTO ...")` / `execute_sql("UPDATE ...")` / `execute_sql("DELETE ...")`
- `df.to_sql('<table>', ...)`

Cite each as `file:line` with a markdown link. If the table name is dynamic (e.g., partition routing, table name from a variable), say so explicitly and explain the routing logic — don't invent specific cites.

### 3. Read graph

For every table, a subsection listing every reader. A "read" is any of:
- `SELECT ... FROM <table>` / `SELECT ... JOIN <table>`
- `query_to_dataframe("SELECT ... FROM <table>")`
- `pd.read_sql(..., 'SELECT ... FROM <table>')`
- SQLAlchemy `.execute(text("SELECT ..."))`
- `row_exists('<table>', ...)` (the existence-check helper)

Cite each as `file:line`. Tests under `tests/` don't count as readers (state that exclusion explicitly).

### 4. Multi-writer tables (coordination risks)

A table flagging every table written by 2+ distinct modules. Columns: Table | Writers | Why a coordination risk. Be specific about the risk — e.g., "two writers with different conflict keys → duplicate rows" or "one writes UPSERT, another writes append-only INSERT → race on the same primary key."

### 5. Orphan tables

A table flagging:
- Tables with **zero writers** in the codebase (legacy / dead)
- Tables with **zero readers** in the codebase (write-only audit, or populated-but-unused)

Columns: Table | Writers | Readers | Status. The Status field should classify: "intentional (audit trail)", "drop candidate", "decision needed", or similar.

### 6. Blast radius per Cloud Run Job

For each Cloud Run Job in the fresh ARCHITECTURE.md:
- The tables it writes
- The downstream consumers (jobs / routers / scripts) that READ those tables
- Severity tag (`Highest`, `Very high`, `High`, `Medium`, `Low`, `Very narrow`, `None`)

If the job stops running, the listed downstream consumers lose fresh data.

### 7. Mermaid graph

A `flowchart LR` Mermaid diagram showing table-level data flow:
- Tables grouped by domain in subgraphs: `Market Data`, `Earnings`, `Catalysts`, `Signals`, `Insights`, `Ops`
- Cloud Run Jobs as nodes pointing TO tables they write (thick arrow `==>` for INSERT/UPSERT, dashed labelled arrow `-.->` for UPDATE-only paths)
- Tables pointing TO their primary consumers (only the heaviest few — full read graph is in §3)
- Orphan tables visually flagged (`classDef orphan` with dashed border)

## Rules

- **Cite `file:line` everywhere.** A claim without a citation is useless.
- **Be exhaustive on tables, lean on prose.** Cover every table even if it's a one-liner. The point of this doc is operator-grade coverage.
- **Distinguish live vs one-shot writers.** A migration script that ran once 6 months ago should be tagged `(one-shot historical)` so the user knows it's not part of the live blast radius.
- **No code, no SQL examples.** Just the dependency graph. If someone wants the actual SQL, they read the source file.
- **Date the doc.** Last line: `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml`.

When done, write the file and exit. Do not narrate.
