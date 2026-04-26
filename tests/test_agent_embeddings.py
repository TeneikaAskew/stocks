"""Unit tests for `lib/agents/embeddings.py`.

Vertex text-embedding-005 wrapper used by the journal reflection
memory layer. Tests cover:
    - 768-dim guard (the embedding contract)
    - Empty-list short-circuit in embed_batch
    - format_vector_literal pgvector text format
    - Empty-embedding response → RuntimeError, not silent zero-vector
    - Single-text + batch parity

We patch `_embed_sync` rather than the underlying google-genai client so
the lazy `from google.genai import types` inside `_embed_sync` never
runs — that import otherwise leaks the real submodule into sys.modules
and breaks `test_agent_vertex_adapter.py` which mocks the same import
later in the test session.
"""

from __future__ import annotations

import asyncio

import pytest


# ──────────────────────────────────────────────────────────────────────
# format_vector_literal — pgvector text format (pure helper, no patching)
# ──────────────────────────────────────────────────────────────────────


def test_format_vector_literal_brackets_and_commas():
    from lib.agents.embeddings import format_vector_literal

    out = format_vector_literal([1.0, 2.5, -0.3])
    # pgvector's text format is `[v1,v2,...]` with no spaces
    assert out == "[1.0000000,2.5000000,-0.3000000]"


def test_format_vector_literal_truncates_to_7_decimals():
    """Storage precision matches the format (avoid weird floating-point
    text noise inflating SQL parameter size)."""
    from lib.agents.embeddings import format_vector_literal

    out = format_vector_literal([0.123456789012345])
    assert out == "[0.1234568]"


def test_format_vector_literal_empty_list():
    """Empty input → '[]', NOT '[,]' or crash."""
    from lib.agents.embeddings import format_vector_literal

    assert format_vector_literal([]) == "[]"


# ──────────────────────────────────────────────────────────────────────
# embed_text / embed_batch — the public async entry points
#
# Both call `_embed_sync(list[str]) -> list[list[float]]` under the
# hood (via `asyncio.to_thread`). Patching `_embed_sync` lets us cover
# the contract without ever loading google-genai.
# ──────────────────────────────────────────────────────────────────────


def _install_embed_sync(monkeypatch, fn):
    """Replace `embeddings._embed_sync` for the test."""
    from lib.agents import embeddings as emb_mod
    monkeypatch.setattr(emb_mod, "_embed_sync", fn)


def test_embed_text_returns_768_dim_list(monkeypatch):
    """Happy path: embed_text returns the first vector from a 1-element
    batch result. Validates the contract for downstream pgvector inserts."""
    from lib.agents.embeddings import embed_text, EMBEDDING_DIM

    captured = {"texts": None}

    def fake(texts):
        captured["texts"] = texts
        return [[0.1] * EMBEDDING_DIM]

    _install_embed_sync(monkeypatch, fake)

    result = asyncio.run(embed_text("hello world"))
    assert len(result) == EMBEDDING_DIM
    assert all(isinstance(v, float) for v in result)
    # `_embed_sync` is called with a 1-element list so batch shape is uniform
    assert captured["texts"] == ["hello world"]


def test_embed_text_propagates_runtime_error(monkeypatch):
    """If `_embed_sync` raises (empty embeddings, dim mismatch, network),
    the async wrapper does not swallow it."""
    from lib.agents.embeddings import embed_text

    def fake(texts):
        raise RuntimeError("Empty embedding for text: 'anything'")

    _install_embed_sync(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="Empty embedding"):
        asyncio.run(embed_text("anything"))


def test_embed_batch_empty_short_circuits_no_call(monkeypatch):
    """Empty input → no _embed_sync call. Backfill scripts iterate over
    pending journal entries — passing an empty list shouldn't burn a
    Vertex request on a no-op."""
    from lib.agents.embeddings import embed_batch

    def fake(texts):
        pytest.fail("_embed_sync should not be called for empty input")

    _install_embed_sync(monkeypatch, fake)
    result = asyncio.run(embed_batch([]))
    assert result == []


def test_embed_batch_passes_through_list_unmodified(monkeypatch):
    """`embed_batch` accepts any Iterable but materializes to a list
    before handing off — so the underlying call sees the same items
    even if the caller passed a generator."""
    from lib.agents.embeddings import embed_batch, EMBEDDING_DIM

    captured = {"texts": None}

    def fake(texts):
        captured["texts"] = list(texts)
        return [[0.5] * EMBEDDING_DIM for _ in texts]

    _install_embed_sync(monkeypatch, fake)

    # Generator → list-conversion happens inside embed_batch
    out = asyncio.run(embed_batch(t for t in ["a", "b", "c"]))
    assert len(out) == 3
    assert all(len(v) == EMBEDDING_DIM for v in out)
    assert captured["texts"] == ["a", "b", "c"]


def test_embed_batch_propagates_per_item_error(monkeypatch):
    """If `_embed_sync` raises mid-batch (one bad input), the whole
    call fails. Partial success would desync the row→embedding
    alignment in the DB."""
    from lib.agents.embeddings import embed_batch

    def fake(texts):
        # _embed_sync iterates internally and raises on `bad`
        if "bad" in texts:
            raise RuntimeError("Empty embedding for text: 'bad'")
        return [[0.0] * 768 for _ in texts]

    _install_embed_sync(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="Empty embedding"):
        asyncio.run(embed_batch(["good", "bad", "also good"]))


# ──────────────────────────────────────────────────────────────────────
# _embed_sync internals — guard contracts asserted via direct mock
#
# We can't run _embed_sync against the real client offline, but we
# can verify it surfaces the documented errors when the underlying
# client returns degenerate shapes.
# ──────────────────────────────────────────────────────────────────────


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

        class _Models:
            def __init__(self, parent):
                self._parent = parent

            def embed_content(self, *, model, contents):
                self._parent.calls.append({"model": model, "contents": contents})
                return self._parent._response

        self.models = _Models(self)


def _stub_genai_types(monkeypatch):
    """Pre-populate `google.genai.types` in sys.modules with a stub so
    the lazy `from google.genai import types` inside `_embed_sync`
    doesn't trigger a real google-genai package load. Required because
    `test_agent_vertex_adapter.py` later in the session relies on
    `patch.dict(sys.modules, ...)` against the same import path; once
    the real module is imported, patch.dict can no longer divert it
    via attribute access on the parent."""
    import sys
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "google", MagicMock())
    monkeypatch.setitem(sys.modules, "google.genai", MagicMock())
    monkeypatch.setitem(sys.modules, "google.genai.types", MagicMock())


def test_embed_sync_raises_on_empty_embeddings(monkeypatch):
    """Vertex sometimes returns `embeddings=[]` on rate-limit edges —
    surface as a RuntimeError so the backfill loop can retry instead
    of inserting a silent zero-vector."""
    _stub_genai_types(monkeypatch)
    from lib.agents import embeddings as emb_mod

    fake = _FakeClient(_FakeResponse(embeddings=[]))
    monkeypatch.setattr(emb_mod, "_get_genai_client", lambda: fake)

    with pytest.raises(RuntimeError, match="Empty embedding"):
        emb_mod._embed_sync(["anything"])


def test_embed_sync_raises_on_wrong_dimension(monkeypatch):
    """If Vertex changes model versions and the dim drifts, the
    `vector(768)` SQL column would reject the insert with an opaque
    error. Catch the mismatch at the source."""
    _stub_genai_types(monkeypatch)
    from lib.agents import embeddings as emb_mod

    fake = _FakeClient(_FakeResponse(
        embeddings=[_FakeEmbedding(values=[0.0] * 512)]  # wrong dim
    ))
    monkeypatch.setattr(emb_mod, "_get_genai_client", lambda: fake)

    with pytest.raises(RuntimeError, match="Expected 768-dim"):
        emb_mod._embed_sync(["anything"])
