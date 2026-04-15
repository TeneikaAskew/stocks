#!/usr/bin/env python3
"""
One-shot backfill: compute Vertex text-embedding-005 vectors for every
journal_entries row whose `embedding` column is NULL.

Run once after applying the schema migration, then again whenever a
bulk import adds rows without embeddings. The agent pipeline's
reflection memory depends on this — entries without embeddings never
surface in retrieve_similar_journal.

Usage:
    set -a && source .env && set +a
    python scripts/backfill_journal_embeddings.py --dry-run
    python scripts/backfill_journal_embeddings.py

Env:
    CLOUD_SQL_URL or DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
    GOOGLE_APPLICATION_CREDENTIALS (for Vertex embeddings)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path so `lib.*` imports work when this is run
# directly from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.agents.embeddings import embed_batch, format_vector_literal  # noqa: E402
from lib.agents.model_routing import _connect  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("backfill-journal-embeddings")


def _fetch_pending(conn, limit: int) -> list[tuple[str, str]]:
    """Return up to `limit` (id, text) rows where embedding IS NULL.

    `text` is a concatenation of ticker, direction, and notes so the
    embedding captures the trade's qualitative character."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id::text,
                   ticker || ' ' || direction ||
                   CASE WHEN notes IS NOT NULL AND notes <> ''
                        THEN ' - ' || notes
                        ELSE ''
                   END AS text
            FROM journal_entries
            WHERE embedding IS NULL
            ORDER BY entry_ts DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        cur.close()


def _write_embeddings(conn, pairs: list[tuple[str, list[float]]]) -> int:
    """Update a batch of rows with their new embeddings."""
    if not pairs:
        return 0
    cur = conn.cursor()
    try:
        for row_id, vec in pairs:
            cur.execute(
                "UPDATE journal_entries "
                "SET embedding = %s::vector, updated_at = NOW() "
                "WHERE id = %s",
                (format_vector_literal(vec), row_id),
            )
    finally:
        cur.close()
    conn.commit()
    return len(pairs)


async def _backfill(batch_size: int, dry_run: bool) -> int:
    conn = _connect()
    total = 0
    try:
        while True:
            pending = _fetch_pending(conn, batch_size)
            if not pending:
                break
            ids = [p[0] for p in pending]
            texts = [p[1] for p in pending]
            logger.info("embedding batch of %d rows (dry_run=%s)", len(ids), dry_run)
            if dry_run:
                # Still call the embedder to exercise credentials, but
                # don't write anything.
                _ = await embed_batch(texts)
                total += len(ids)
                break  # only one batch in dry-run
            vecs = await embed_batch(texts)
            pairs = list(zip(ids, vecs))
            written = _write_embeddings(conn, pairs)
            total += written
            logger.info("wrote %d embeddings (running total %d)", written, total)
    finally:
        conn.close()
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Rows per Vertex embedding request (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Embed one batch but do not write to the database",
    )
    args = parser.parse_args()

    try:
        total = asyncio.run(_backfill(args.batch_size, args.dry_run))
    except Exception:
        logger.exception("backfill failed")
        return 1

    logger.info("done — %d rows processed", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
