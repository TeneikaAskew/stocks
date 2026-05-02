# `gcp/queries/`

Reusable SQL queries for the `db-query.yml` GitHub Actions workflow.

## Why this directory exists

The Claude Code on the web sandbox cannot reach Cloud SQL (sandbox blocks
outbound TCP on every non-443 port). Sessions dispatch
`.github/workflows/db-query.yml` with either:

- `sql=...` for inline SQL (multi-statement OK, separated by `;`), or
- `sql_file=gcp/queries/<name>.sql` for SQL too large for a dispatch input
  or DDL with embedded semicolons (DO blocks, function definitions).

Files in this directory are committed once and reusable across every session.

## Naming convention

- `snake_case_descriptive_name.sql`
- Prefix with intent: `check_*`, `count_*`, `list_*`, `audit_*`, `fix_*`
- One semantic operation per file. For multi-step operations, use one file
  and rely on the workflow's per-statement transaction (NOTE: file content
  is sent as a SINGLE statement; for true multi-statement, split into
  separate files or use inline `sql` input).

## Examples

- `sample_table_sizes.sql` — list all tables with sizes and row counts (drop-in
  replacement for `gcloud sql connect`'s `\dt+` style overview).

## Invocation from a session

```bash
gh workflow run db-query.yml \
  -f sql_file=gcp/queries/sample_table_sizes.sql \
  -f issue_number=<TRACKING_ISSUE>
```

See `CLAUDE.md` `## Database access` for the full usage guide.
