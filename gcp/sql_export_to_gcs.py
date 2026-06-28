#!/usr/bin/env python3
"""
Weekly Cloud SQL → GCS logical backup.

Calls the Cloud SQL Admin API to export the entire `trading` database as a
gzipped SQL dump and write it to gs://<bucket>/sql-dumps/. Backs up *every*
table (~30 of them), not just the parquet-mirrored subset.

Designed as a Cloud Run Job invoked weekly by Cloud Scheduler. Uses the
trading-runner SA's Application Default Credentials. Polls the export
operation until DONE; exits non-zero on failure so failure_notifier picks
it up.

IAM prerequisites (one-time, see deploy.sh setup_pg_dump_iam):
- trading-runner SA needs roles/cloudsql.editor on the project (or the
  instance) to invoke the export.
- The Cloud SQL service identity
  (service-<PROJECT_NUMBER>@gcp-sa-cloud-sql.iam.gserviceaccount.com)
  needs roles/storage.objectAdmin on the destination bucket — the export
  is performed by Cloud SQL itself writing to GCS, NOT by the calling SA.

Usage:
    python -m gcp.sql_export_to_gcs                     # uses defaults
    python -m gcp.sql_export_to_gcs --bucket OTHER      # override bucket
    python -m gcp.sql_export_to_gcs --no-offload        # skip serverless offload
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests
from google.auth import default
from google.auth.transport.requests import Request

from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "adept-mountain-474619-d4")
INSTANCE = os.environ.get("CLOUD_SQL_INSTANCE", "trading-db")
DATABASE = os.environ.get("DB_NAME", "trading")
DEFAULT_BUCKET = os.environ.get(
    "SQL_DUMP_BUCKET", f"{PROJECT}-trading-data"
)
DEFAULT_PREFIX = os.environ.get("SQL_DUMP_PREFIX", "sql-dumps")
POLL_INTERVAL_SECS = 15
# Poll cap is set 10 min below the Cloud Run task-timeout (10800s) so the
# job exits with a clean TimeoutError before Cloud Run kills the task and
# the failure_notifier sees a bare "Terminating task" message. The 2026-06-28
# outage showed POLL_MAX_SECS == task-timeout = 3600 caused Cloud Run to
# terminate the task before the Python code could detect the timeout.
POLL_MAX_SECS = 10200  # 2h50m (task-timeout is 3h = 10800s)


def _get_token() -> str:
    """Get an OAuth token for the SA's default credentials."""
    creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def trigger_export(bucket: str, prefix: str, offload: bool) -> tuple[str, str]:
    """POST to Cloud SQL Admin API to start an export. Returns (gcs_uri, op_name)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    uri = f"gs://{bucket}/{prefix}/trading-{ts}.sql.gz"

    body = {
        "exportContext": {
            "uri": uri,
            "databases": [DATABASE],
            "fileType": "SQL",
            "offload": offload,
        }
    }

    r = requests.post(
        f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}"
        f"/instances/{INSTANCE}/export",
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(
            f"Export trigger failed: HTTP {r.status_code} {r.text}"
        )
    op = r.json()
    return uri, op["name"]


def wait_for_op(op_name: str) -> dict:
    """Poll the operation until status=DONE. Raises on failure."""
    started = time.monotonic()
    while True:
        if time.monotonic() - started > POLL_MAX_SECS:
            raise TimeoutError(f"Export timed out after {POLL_MAX_SECS}s")

        time.sleep(POLL_INTERVAL_SECS)
        r = requests.get(
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}"
            f"/operations/{op_name}",
            headers={"Authorization": f"Bearer {_get_token()}"},
            timeout=30,
        )
        if r.status_code >= 400:
            raise RuntimeError(
                f"Operation poll failed: HTTP {r.status_code} {r.text}"
            )
        st = r.json()
        status = st.get("status", "?")
        log.info("  op status: %s", status)
        if status == "DONE":
            if "error" in st:
                raise RuntimeError(f"Export failed: {st['error']}")
            return st


def main():
    parser = argparse.ArgumentParser(
        description="Weekly Cloud SQL → GCS logical backup"
    )
    parser.add_argument(
        "--bucket", default=DEFAULT_BUCKET,
        help=f"Destination GCS bucket (default: {DEFAULT_BUCKET})",
    )
    parser.add_argument(
        "--prefix", default=DEFAULT_PREFIX,
        help=f"GCS object prefix (default: {DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--no-offload", dest="offload", action="store_false", default=True,
        help="Skip serverless offload (default: enabled — runs export "
             "without using primary's CPU/IO; takes slightly longer but "
             "doesn't impact production reads/writes).",
    )
    args = parser.parse_args()

    log.info("Cloud SQL → GCS export")
    log.info("  project : %s", PROJECT)
    log.info("  instance: %s", INSTANCE)
    log.info("  database: %s", DATABASE)
    log.info("  dest    : gs://%s/%s/", args.bucket, args.prefix)
    log.info("  offload : %s", args.offload)

    uri, op_name = trigger_export(args.bucket, args.prefix, args.offload)
    log.info("  → export started, polling operation %s", op_name)
    log.info("  → output : %s", uri)

    op_result = wait_for_op(op_name)
    duration_ms = 0
    if op_result.get("startTime") and op_result.get("endTime"):
        try:
            start = datetime.fromisoformat(
                op_result["startTime"].replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                op_result["endTime"].replace("Z", "+00:00")
            )
            duration_ms = int((end - start).total_seconds() * 1000)
        except Exception:
            pass
    log.info("  ✓ export complete (%d ms)", duration_ms)
    log.info("  ✓ dump at %s", uri)


if __name__ == "__main__":
    main()
