#!/usr/bin/env python3
"""
Google Cloud Storage utility helpers shared across gcp/ modules.
"""

import io
import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


def upload_dataframe_as_parquet(df: pd.DataFrame, bucket: str, blob_path: str) -> str:
    """Serialize a DataFrame to Parquet and upload to GCS.

    Returns the gs:// URI on success, empty string on failure.
    """
    if not bucket or df.empty:
        return ''
    try:
        from google.cloud import storage as gcs
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine='pyarrow')
        buf.seek(0)

        client = gcs.Client()
        blob = client.bucket(bucket).blob(blob_path)
        blob.upload_from_file(buf, content_type='application/octet-stream')
        uri = f"gs://{bucket}/{blob_path}"
        log.debug("  ↑ GCS %s", uri)
        return uri
    except Exception as e:
        log.warning("  GCS upload failed (%s): %s", blob_path, e)
        return ''


def parquet_exists_in_gcs(bucket: str, blob_path: str) -> bool:
    """Return True if the blob already exists in GCS."""
    try:
        from google.cloud import storage as gcs
        return gcs.Client().bucket(bucket).blob(blob_path).exists()
    except Exception:
        return False


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


def download_parquet_from_gcs(bucket: str, blob_path: str) -> pd.DataFrame:
    """Download a Parquet blob from GCS and return as a DataFrame.

    Returns empty DataFrame on error (consistent with data-function convention).
    """
    try:
        from google.cloud import storage as gcs
        buf = io.BytesIO()
        gcs.Client().bucket(bucket).blob(blob_path).download_to_file(buf)
        buf.seek(0)
        return pd.read_parquet(buf)
    except Exception as e:
        log.warning("  GCS Parquet download failed (%s): %s", blob_path, e)
        return pd.DataFrame()


def list_blobs(bucket: str, prefix: str) -> list:
    """Return a list of blob names under a GCS prefix."""
    try:
        from google.cloud import storage as gcs
        blobs = gcs.Client().list_blobs(bucket, prefix=prefix)
        return [b.name for b in blobs]
    except Exception as e:
        log.warning("  GCS list failed (%s): %s", prefix, e)
        return []
