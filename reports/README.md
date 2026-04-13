# Reports Directory

**This directory is gitignored.** All phase reports (`phase*.md`) and transition/setup CSVs are stored in Google Cloud Storage and streamed by the platform API on demand.

## Source of truth

```
gs://adept-mountain-474619-d4-trading-data/raw/reports/
```

## How the app reads reports

The platform API router at [platform/api/routers/playbook.py](../platform/api/routers/playbook.py) downloads reports directly from GCS via the shared helper at [platform/api/gcs_reader.py](../platform/api/gcs_reader.py). Responses are cached in memory with a 24-hour TTL because markdown content changes rarely.

There is **no local pre-pull** and **no local filesystem fallback**. If GCS is unreachable, the endpoint returns 502 with a clear error.

## How to update a report

1. Write or regenerate the markdown/CSV locally (e.g., via `scripts/run_pipeline.py`)
2. Upload the new version to GCS:
   ```bash
   gsutil cp reports/phase6_playbook_iwm.md gs://adept-mountain-474619-d4-trading-data/raw/reports/
   ```
3. Wait up to 24 hours for the in-memory cache to expire, or restart the API process to force an immediate refresh

## Authentication

The API uses `.gcp-key.json` or `GOOGLE_APPLICATION_CREDENTIALS` from `.env` to authenticate to GCS. No extra setup required.
