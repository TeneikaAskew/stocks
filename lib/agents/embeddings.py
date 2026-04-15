"""
Vertex text-embedding-005 wrapper for journal reflection memory.

768-dim embeddings on the same .gcp-key.json service account that
powers the Gemini adapter — no new secrets.
"""

from __future__ import annotations

import asyncio
import os
from typing import Iterable

from .vertex_adapter import _get_genai_client

EMBEDDING_MODEL = "text-embedding-005"
EMBEDDING_DIM = 768


def _embed_sync(texts: list[str]) -> list[list[float]]:
    """Blocking embed call. `texts` is a list so batch requests work."""
    client = _get_genai_client()
    from google.genai import types

    # google-genai exposes embed_content on models
    out: list[list[float]] = []
    for text in texts:
        resp = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
        # resp.embeddings is a list[ContentEmbedding]; we sent one text
        # at a time so take the first.
        if not resp.embeddings:
            raise RuntimeError(f"Empty embedding for text: {text[:80]!r}")
        values = list(resp.embeddings[0].values)
        if len(values) != EMBEDDING_DIM:
            raise RuntimeError(
                f"Expected {EMBEDDING_DIM}-dim embedding, got {len(values)}"
            )
        out.append(values)
    return out


async def embed_text(text: str) -> list[float]:
    """Embed a single string. Awaitable for use inside the async
    orchestrator. Blocks on Vertex I/O in a thread."""
    results = await asyncio.to_thread(_embed_sync, [text])
    return results[0]


async def embed_batch(texts: Iterable[str]) -> list[list[float]]:
    """Embed many strings at once. Used by the one-shot
    scripts/backfill_journal_embeddings.py."""
    as_list = list(texts)
    if not as_list:
        return []
    return await asyncio.to_thread(_embed_sync, as_list)


def format_vector_literal(vec: list[float]) -> str:
    """pgvector text literal for raw-SQL inserts. psycopg2 has no
    type adapter for vector by default, so we serialize as the
    string form pgvector accepts."""
    return "[" + ",".join(f"{v:.7f}" for v in vec) + "]"
