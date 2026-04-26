"""
Shared GCS reader for platform API routers.

All data beyond Cloud SQL tables lives in GCS. Routers download on demand,
cache in memory with a TTL, and serve subsequent requests from cache.
No local filesystem reads, no pre-pull scripts.

Design:
    * Single module-level GCS client (created lazily on first call).
    * Short-lived TTLCache on blob listings so router caches don't thrash
      the GCS LIST API on every request.
    * Per-blob downloads are not cached here — routers cache the parsed
      DataFrame/text keyed on whatever request inputs make sense for them.
    * Filenames in this project are timestamped (e.g. backtest_IWM_20260221_161724.csv),
      so "most recent" = lexically greatest. No need for blob metadata fetches.

Usage:
    from api.gcs_reader import list_matching_blobs, download_csv, download_text

    # Find and load the newest IWM backtest
    blobs = list_matching_blobs("data/backtest_results/", r"^backtest_IWM_.*\\.csv$")
    if not blobs:
        raise HTTPException(404, "No backtest results in GCS")
    df = download_csv(blobs[0])
"""
import io
import logging
import re
from typing import Optional

import pandas as pd
from cachetools import TTLCache

log = logging.getLogger(__name__)

BUCKET = "adept-mountain-474619-d4-trading-data"
BASE_PREFIX = "raw/"  # All app data lives under gs://BUCKET/raw/*

# Module-level singleton GCS client (created on first use)
_client = None


def _get_client():
    global _client
    if _client is None:
        from google.cloud import storage as gcs
        _client = gcs.Client()
    return _client


# ── Blob listing ────────────────────────────────────────────────────────────
# Cache blob listings for 10 minutes so router-level result caches don't
# hammer the GCS LIST API. New backtest runs etc. become visible within 10m.
_LIST_CACHE: TTLCache = TTLCache(maxsize=64, ttl=600)


def list_matching_blobs(prefix: str, pattern: str) -> list[str]:
    """Return blob names under BASE_PREFIX+prefix whose **basename** matches the
    regex, sorted descending (newest first by lexical filename sort).

    Lexical sort is safe because our filenames are timestamped:
        backtest_IWM_YYYYMMDD_HHMMSS.csv
        historical_iwm_YYYYMMDD_YYYYMMDD_signals.parquet
        phase6_playbook_iwm.md
    """
    cache_key = (prefix, pattern)
    if cache_key in _LIST_CACHE:
        return _LIST_CACHE[cache_key]

    full_prefix = BASE_PREFIX + prefix
    try:
        blobs = _get_client().list_blobs(BUCKET, prefix=full_prefix)
        names = [b.name for b in blobs]
    except Exception as e:
        log.warning("GCS list failed (%s): %s", full_prefix, e)
        return []

    regex = re.compile(pattern)
    matching = sorted(
        [n for n in names if regex.search(n.rsplit("/", 1)[-1])],
        reverse=True,
    )
    _LIST_CACHE[cache_key] = matching
    return matching


def blob_exists(blob_path: str) -> bool:
    """Return True if a blob exists in GCS under BASE_PREFIX+blob_path."""
    full_path = BASE_PREFIX + blob_path
    try:
        return _get_client().bucket(BUCKET).blob(full_path).exists()
    except Exception as e:
        log.warning("GCS exists check failed (%s): %s", full_path, e)
        return False


# ── Blob downloads ──────────────────────────────────────────────────────────
# These raise on failure. Routers are responsible for translating to HTTP errors
# and for caching the parsed result keyed on their own request inputs.


def _download_bytes(blob_name: str) -> bytes:
    """Low-level: download raw bytes for a blob. blob_name includes BASE_PREFIX."""
    buf = io.BytesIO()
    _get_client().bucket(BUCKET).blob(blob_name).download_to_file(buf)
    buf.seek(0)
    return buf.read()


def download_csv(blob_name: str) -> pd.DataFrame:
    """Download a CSV blob from GCS as a DataFrame. Raises on failure.

    `blob_name` should already include BASE_PREFIX (as returned by list_matching_blobs).
    """
    data = _download_bytes(blob_name)
    return pd.read_csv(io.BytesIO(data))


def download_parquet(blob_name: str, columns: Optional[list[str]] = None) -> pd.DataFrame:
    """Download a Parquet blob from GCS as a DataFrame. Raises on failure.

    Pass `columns=[...]` to project — pyarrow only deserializes those columns,
    cutting CPU/memory on large parquets (e.g. signals files have ~30 cols of
    which the API uses ~10).
    """
    data = _download_bytes(blob_name)
    return pd.read_parquet(io.BytesIO(data), columns=columns)


def download_text(blob_path: str) -> str:
    """Download a text blob (Markdown, JSON, plain text) from GCS as a string.

    `blob_path` is relative to BASE_PREFIX, e.g. "reports/phase6_playbook_iwm.md".
    Raises on failure.
    """
    full_path = BASE_PREFIX + blob_path
    return _get_client().bucket(BUCKET).blob(full_path).download_as_text()


# ── Convenience: latest blob matching pattern ──────────────────────────────


def get_latest_csv(prefix: str, pattern: str) -> Optional[tuple[str, pd.DataFrame]]:
    """Find newest blob matching pattern under prefix, download as DataFrame.

    Returns (blob_name, dataframe) or None if no match.
    """
    blobs = list_matching_blobs(prefix, pattern)
    if not blobs:
        return None
    return blobs[0], download_csv(blobs[0])


def get_latest_parquet(prefix: str, pattern: str) -> Optional[tuple[str, pd.DataFrame]]:
    blobs = list_matching_blobs(prefix, pattern)
    if not blobs:
        return None
    return blobs[0], download_parquet(blobs[0])
