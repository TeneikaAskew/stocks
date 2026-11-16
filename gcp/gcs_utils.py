#!/usr/bin/env python3
"""
Google Cloud Storage utility helpers shared across gcp/ modules.

The parquet upload/download/exists helpers were removed in 2026-05 along
with the fetcher GCS-backup writes. Cloud SQL PITR + the weekly pg_dump
job replaced them. Re-introduce only with a clear consumer requirement.
"""

import io
import logging

import pandas as pd

log = logging.getLogger(__name__)


def download_csv_from_gcs(bucket: str, blob_path: str) -> pd.DataFrame:
    """Download a CSV blob from GCS and return as a DataFrame.

    Returns empty DataFrame on error (consistent with data-function convention).
    """
    try:
        from google.cloud import storage as gcs
        buf = io.BytesIO()
        gcs.Client().bucket(bucket).blob(blob_path).download_to_file(buf)
        buf.seek(0)
        return pd.read_csv(buf)
    except Exception as e:
        log.warning("  GCS CSV download failed (%s): %s", blob_path, e)
        return pd.DataFrame()


def download_text_from_gcs(bucket: str, blob_path: str) -> str:
    """Download a text blob (e.g. Markdown, JSON, plain text) from GCS.

    Returns empty string on error (consistent with the other download helpers).
    """
    try:
        from google.cloud import storage as gcs
        return gcs.Client().bucket(bucket).blob(blob_path).download_as_text()
    except Exception as e:
        log.warning("  GCS text download failed (%s): %s", blob_path, e)
        return ''


def list_blobs(bucket: str, prefix: str) -> list:
    """Return a list of blob names under a GCS prefix."""
    try:
        from google.cloud import storage as gcs
        blobs = gcs.Client().list_blobs(bucket, prefix=prefix)
        return [b.name for b in blobs]
    except Exception as e:
        log.warning("  GCS list failed (%s): %s", prefix, e)
        return []


def _storage_client():
    """A Cloud Storage client. Imported here so the module imports without
    the library and a test can replace the client."""
    from google.cloud import storage as gcs
    return gcs.Client()


def upload_text_to_gcs(bucket: str, blob_path: str, text: str, content_type: str) -> str:
    """Upload *text* as one object and return its ``gs://`` URL.

    Unlike the download helpers above, this raises on failure: its caller
    writes to the database only after the upload is known to have worked, so
    a swallowed error here would be a report that was never saved.
    """
    _storage_client().bucket(bucket).blob(blob_path).upload_from_string(
        text, content_type=content_type)
    return f"gs://{bucket}/{blob_path}"
