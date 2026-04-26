"""Unit tests for `lib.agents.anthropic_adapter`.

The Anthropic adapter is one of two LLM backends powering the orchestrator
(Vertex Gemini being the other). Tests mirror the Vertex test shape so the
two adapters get equivalent coverage. Verifies:
    - Forced-tool-use round-trip → Pydantic parsing
    - System-message hoisting from messages list into top-level system
    - Usage extraction including cache_read subtraction from input_tokens
    - asyncio.to_thread wrapper around sync SDK call
    - RuntimeError when the model fails to emit the structured tool block
    - count_tokens heuristic
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

import pytest
from pydantic import BaseModel

from lib.agents.anthropic_adapter import AnthropicAdapter
from lib.agents.llm_client import Message
from lib.agents.schema import AnalystOutput


# ──────────────────────────────────────────────────────────────────────
# Fake anthropic SDK response shapes
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _FakeBlock:
    type: str
    name: Optional[str] = None
    input: Optional[dict] = None


@dataclass
class _FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _FakeResponse:
    content: list
    usage: _FakeUsage
    stop_reason: str = "tool_use"


class _FakeMessages:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_call_kwargs: dict = {}

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self.messages = _FakeMessages(response)


def _install_fake_client(response: _FakeResponse) -> _FakeClient:
    fake = _FakeClient(response)
    AnthropicAdapter._client = fake
    return fake


@pytest.fixture(autouse=True)
def _fresh_singleton():
    """Reset the class-level client singleton between tests so each test
    installs its own fake response."""
    AnthropicAdapter._client = None
    yield
    AnthropicAdapter._client = None


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────


def test_complete_round_trips_pydantic_via_tool_use():
    """Happy path: model returns a single tool_use block with input
    matching the AnalystOutput schema → adapter parses it back."""
    payload = {
        "section": "market",
        "summary": "Strong bullish structure.",
        "bullets": ["above 200SMA", "rising volume"],
        "bias": "bullish",
        "confidence": 0.78,
    }
    fake = _install_fake_client(_FakeResponse(
        content=[_FakeBlock(type="tool_use", name="structured_output", input=payload)],
        usage=_FakeUsage(input_tokens=120, output_tokens=85),
    ))

    adapter = AnthropicAdapter()
    result = asyncio.run(adapter.complete(
        model="claude-haiku-4-5",
        system="You are a market analyst.",
        messages=[Message(role="user", content="Analyze SPY.")],
        response_model=AnalystOutput,
    ))

    assert isinstance(result.parsed, AnalystOutput)
    assert result.parsed.bias == "bullish"
    assert result.parsed.confidence == 0.78
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 85
    # raw_text is the JSON-serialized tool input
    assert json.loads(result.raw_text) == payload


def test_complete_hoists_system_message_into_top_level_system():
    """Anthropic's API requires `system` as a top-level field, not
    a message role. The adapter must concat any role='system'
    messages into the top-level system string."""
    payload = {
        "section": "strat", "summary": "ok", "bullets": ["a"],
        "bias": "neutral", "confidence": 0.5,
    }
    fake = _install_fake_client(_FakeResponse(
        content=[_FakeBlock(type="tool_use", name="structured_output", input=payload)],
        usage=_FakeUsage(input_tokens=10, output_tokens=10),
    ))

    adapter = AnthropicAdapter()
    asyncio.run(adapter.complete(
        model="claude-haiku-4-5",
        system="Base system",
        messages=[
            Message(role="system", content="Extra rule"),
            Message(role="user", content="hi"),
        ],
        response_model=AnalystOutput,
    ))

    call_kwargs = fake.messages.last_call_kwargs
    # System-role message gets concatenated to top-level system
    assert "Base system" in call_kwargs["system"]
    assert "Extra rule" in call_kwargs["system"]
    # Only the user message survives in the messages list
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_complete_subtracts_cache_reads_from_input_tokens():
    """Cache-read tokens are billed separately, so they must be
    subtracted from the input_tokens count to avoid double-billing."""
    payload = {
        "section": "options", "summary": "ok", "bullets": ["a"],
        "bias": "neutral", "confidence": 0.5,
    }
    _install_fake_client(_FakeResponse(
        content=[_FakeBlock(type="tool_use", name="structured_output", input=payload)],
        usage=_FakeUsage(input_tokens=200, output_tokens=50,
                         cache_read_input_tokens=80),
    ))
    adapter = AnthropicAdapter()
    result = asyncio.run(adapter.complete(
        model="claude-haiku-4-5",
        system="x",
        messages=[Message(role="user", content="x")],
        response_model=AnalystOutput,
    ))
    # 200 input - 80 cache_read = 120 net
    assert result.usage.input_tokens == 120
    assert result.usage.cache_read_tokens == 80


def test_complete_does_not_subtract_when_cache_read_exceeds_input():
    """Defensive: never let `input_tokens` go negative if the SDK
    reports a weird cache_read_input_tokens > input_tokens."""
    payload = {
        "section": "catalyst", "summary": "x", "bullets": ["a"],
        "bias": "neutral", "confidence": 0.5,
    }
    _install_fake_client(_FakeResponse(
        content=[_FakeBlock(type="tool_use", name="structured_output", input=payload)],
        usage=_FakeUsage(input_tokens=50, output_tokens=20,
                         cache_read_input_tokens=999),
    ))
    adapter = AnthropicAdapter()
    result = asyncio.run(adapter.complete(
        model="claude-haiku-4-5", system="x",
        messages=[Message(role="user", content="x")],
        response_model=AnalystOutput,
    ))
    # No subtraction → 50 stays at 50
    assert result.usage.input_tokens == 50


def test_complete_raises_when_no_tool_use_block():
    """If the model returns a text block instead of the forced tool
    call (e.g. content-policy refusal), the adapter must raise rather
    than silently return an empty parsed object."""
    _install_fake_client(_FakeResponse(
        content=[_FakeBlock(type="text", input=None)],
        usage=_FakeUsage(input_tokens=10, output_tokens=5),
        stop_reason="end_turn",
    ))
    adapter = AnthropicAdapter()
    with pytest.raises(RuntimeError, match="did not return a tool_use block"):
        asyncio.run(adapter.complete(
            model="claude-haiku-4-5", system="x",
            messages=[Message(role="user", content="x")],
            response_model=AnalystOutput,
        ))


def test_complete_passes_tool_choice_forced():
    """The adapter must force the tool call (not leave it to the
    model's discretion) — that's how structured output is
    guaranteed."""
    payload = {
        "section": "market", "summary": "x", "bullets": ["a"],
        "bias": "neutral", "confidence": 0.5,
    }
    fake = _install_fake_client(_FakeResponse(
        content=[_FakeBlock(type="tool_use", name="structured_output", input=payload)],
        usage=_FakeUsage(input_tokens=10, output_tokens=5),
    ))
    adapter = AnthropicAdapter()
    asyncio.run(adapter.complete(
        model="claude-haiku-4-5", system="x",
        messages=[Message(role="user", content="x")],
        response_model=AnalystOutput,
    ))
    kwargs = fake.messages.last_call_kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "structured_output"}
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0]["name"] == "structured_output"


def test_count_tokens_returns_at_least_one():
    """Heuristic: ~3.5 chars/token. Empty string still returns ≥1 so
    the orchestrator never divides by zero on cost math."""
    adapter = AnthropicAdapter()
    assert asyncio.run(adapter.count_tokens(model="claude-haiku-4-5", text="")) == 1
    # 35 chars / 3.5 = 10
    n = asyncio.run(adapter.count_tokens(
        model="claude-haiku-4-5", text="a" * 35
    ))
    assert n == 10
