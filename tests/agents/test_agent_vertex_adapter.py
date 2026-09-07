"""Unit tests for lib.agents.vertex_adapter.

Mocks the google-genai client so tests run offline. Verifies:
- Pydantic response_model parsing round-trip
- System-message hoisting to system_instruction
- Token usage extraction + cache subtraction
- asyncio wrapper around sync SDK call
- count_tokens heuristic
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict

# Importing the adapter module is safe without google-genai installed —
# the `from google.genai import types` lives inside complete() (line 113),
# not at module load. We don't use importorskip because importorskip
# eagerly imports google.genai, and google.genai's __init__ binds the
# `types` submodule as an attribute on the package object. Once that
# attribute is bound, patch.dict(sys.modules, {"google.genai.types":
# mock}) no longer affects `from google.genai import types` — the
# resolution goes via the package attribute, not sys.modules. The
# per-test patch_dict below patches the PARENT module so it works
# whether or not google-genai is installed.

from lib.agents.llm_client import Message
from lib.agents.schema import AnalystOutput, EntryZone, TraderOutput
from lib.agents.vertex_adapter import VertexGeminiAdapter


# ---------------------------------------------------------------------------
# Fake google-genai response shapes
# ---------------------------------------------------------------------------


@dataclass
class _FakeUsageMetadata:
    prompt_token_count: int = 0
    candidates_token_count: int = 0
    cached_content_token_count: int = 0


@dataclass
class _FakeResponse:
    text: str
    usage_metadata: Optional[_FakeUsageMetadata] = None
    finish_reason: str = "STOP"


class _FakeModels:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_call_args: dict = {}

    def generate_content(self, *, model, contents, config):
        self.last_call_args = dict(model=model, contents=contents, config=config)
        return self._response


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self.models = _FakeModels(response)


def _install_fake_client(response: _FakeResponse):
    fake = _FakeClient(response)
    # Reset singleton then patch
    VertexGeminiAdapter._client = fake
    return fake


def _reset_singleton():
    VertexGeminiAdapter._client = None


@pytest.fixture(autouse=True)
def _fresh_singleton():
    _reset_singleton()
    yield
    _reset_singleton()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_complete_parses_analyst_output():
    json_body = (
        '{"section":"market","summary":"Strong bullish structure.",'
        '"bullets":["above 200SMA","rising volume"],"bias":"bullish",'
        '"confidence":0.78}'
    )
    fake = _install_fake_client(
        _FakeResponse(
            text=json_body,
            usage_metadata=_FakeUsageMetadata(
                prompt_token_count=1200, candidates_token_count=300
            ),
        )
    )

    # Stub google.genai.types.Content / Part / GenerateContentConfig
    import sys
    types_mod = MagicMock()
    types_mod.Content = lambda role, parts: {"role": role, "parts": parts}
    types_mod.Part = lambda text: {"text": text}
    types_mod.GenerateContentConfig = lambda **kw: kw
    genai_pkg = MagicMock()
    genai_pkg.types = types_mod
    with patch.dict(sys.modules, {
            "google.genai": genai_pkg,
            "google.genai.types": types_mod,
    }):
        adapter = VertexGeminiAdapter()
        result = asyncio.run(
            adapter.complete(
                model="gemini-2.0-flash",
                system="You are a market analyst.",
                messages=[Message(role="user", content="Assess SPY for today.")],
                response_model=AnalystOutput,
                temperature=0.2,
                max_output_tokens=1024,
            )
        )

    assert isinstance(result.parsed, AnalystOutput)
    assert result.parsed.section == "market"
    assert result.parsed.bias == "bullish"
    assert result.usage.input_tokens == 1200
    assert result.usage.output_tokens == 300
    assert result.usage.cost_usd() > 0


def test_complete_hoists_system_message_into_instruction():
    json_body = (
        '{"direction":"long","entry_zone":{"low":500.0,"high":502.0},'
        '"stop":498.0,"targets":[504.0,508.0],"time_horizon":"swing",'
        '"invalidation":"close below 498","confidence":0.7}'
    )
    fake = _install_fake_client(_FakeResponse(text=json_body))

    import sys
    types_mod = MagicMock()
    types_mod.Content = lambda role, parts: {"role": role, "parts": parts}
    types_mod.Part = lambda text: {"text": text}
    captured = {}

    def capture_config(**kw):
        captured.update(kw)
        return kw

    types_mod.GenerateContentConfig = capture_config

    genai_pkg = MagicMock()
    genai_pkg.types = types_mod
    with patch.dict(sys.modules, {
            "google.genai": genai_pkg,
            "google.genai.types": types_mod,
    }):
        adapter = VertexGeminiAdapter()
        asyncio.run(
            adapter.complete(
                model="gemini-2.0-flash",
                system="Base system prompt.",
                messages=[
                    Message(role="system", content="Additional system rule."),
                    Message(role="user", content="Plan this trade."),
                ],
                response_model=TraderOutput,
            )
        )

    # System message was merged into system_instruction
    assert "Base system prompt." in captured["system_instruction"]
    assert "Additional system rule." in captured["system_instruction"]
    # Only the user message reached contents
    contents = fake.models.last_call_args["contents"]
    assert len(contents) == 1
    assert contents[0]["role"] == "user"


def test_usage_subtracts_cache_reads_from_input():
    """Gemini reports cached tokens as a subset of prompt_token_count.
    The adapter must subtract to avoid double-counting."""
    json_body = (
        '{"section":"strat","summary":"2U candle above trigger.",'
        '"bullets":[],"bias":"bullish","confidence":0.6}'
    )
    fake = _install_fake_client(
        _FakeResponse(
            text=json_body,
            usage_metadata=_FakeUsageMetadata(
                prompt_token_count=10_000,
                candidates_token_count=500,
                cached_content_token_count=8_000,
            ),
        )
    )

    import sys
    types_mod = MagicMock()
    types_mod.Content = lambda role, parts: {"role": role, "parts": parts}
    types_mod.Part = lambda text: {"text": text}
    types_mod.GenerateContentConfig = lambda **kw: kw
    genai_pkg = MagicMock()
    genai_pkg.types = types_mod
    with patch.dict(sys.modules, {
            "google.genai": genai_pkg,
            "google.genai.types": types_mod,
    }):
        adapter = VertexGeminiAdapter()
        result = asyncio.run(
            adapter.complete(
                model="gemini-2.0-flash",
                system="sys",
                messages=[Message(role="user", content="x")],
                response_model=AnalystOutput,
            )
        )

    # Uncached input = 10,000 - 8,000 = 2,000
    assert result.usage.input_tokens == 2_000
    assert result.usage.cache_read_tokens == 8_000
    assert result.usage.output_tokens == 500


def test_complete_raises_on_empty_response():
    fake = _install_fake_client(_FakeResponse(text=""))

    import sys
    types_mod = MagicMock()
    types_mod.Content = lambda role, parts: {"role": role, "parts": parts}
    types_mod.Part = lambda text: {"text": text}
    types_mod.GenerateContentConfig = lambda **kw: kw
    genai_pkg = MagicMock()
    genai_pkg.types = types_mod
    with patch.dict(sys.modules, {
            "google.genai": genai_pkg,
            "google.genai.types": types_mod,
    }):
        adapter = VertexGeminiAdapter()
        with pytest.raises(RuntimeError, match="empty response"):
            asyncio.run(
                adapter.complete(
                    model="gemini-2.0-flash",
                    system="s",
                    messages=[Message(role="user", content="q")],
                    response_model=AnalystOutput,
                )
            )


def test_count_tokens_heuristic():
    adapter = VertexGeminiAdapter()
    n = asyncio.run(adapter.count_tokens(model="gemini-2.0-flash", text="a" * 400))
    assert n == 100  # 400 // 4


def test_adapter_registered():
    from lib.agents.llm_client import _REGISTRY, get_adapter

    # Registration happens on import of vertex_adapter
    assert "vertex" in _REGISTRY
    inst = get_adapter("vertex")
    assert isinstance(inst, VertexGeminiAdapter)
