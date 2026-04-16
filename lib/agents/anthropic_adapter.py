"""
Anthropic Claude adapter for LLMClient.

Uses the anthropic Python SDK with structured output via forced
tool-use (wraps the Pydantic schema as a single tool input_schema
and forces the model to call it). Async via asyncio.to_thread so
the orchestrator's asyncio.gather gives real concurrency.

The adapter self-registers on import ONLY when ANTHROPIC_API_KEY is
set. When the key is absent, get_adapter("anthropic") raises KeyError
— which is the expected behavior (the admin UI shows has_credentials=False).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Type

from pydantic import BaseModel

from .llm_client import CompletionResult, LLMClient, Message, register_adapter
from .pricing import Usage

logger = logging.getLogger(__name__)


def _get_anthropic_client():
    """Lazy-initialize the Anthropic client."""
    import anthropic

    return anthropic.Anthropic()


class AnthropicAdapter(LLMClient):
    """Anthropic Claude implementation of LLMClient."""

    provider = "anthropic"

    _client = None  # lazy singleton across instances

    @classmethod
    def _client_singleton(cls):
        if cls._client is None:
            cls._client = _get_anthropic_client()
        return cls._client

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        response_model: Type[BaseModel],
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
        enable_cache: bool = False,
    ) -> CompletionResult:
        client = self._client_singleton()

        # Build message list (Anthropic expects user/assistant alternation)
        api_messages = []
        for m in messages:
            if m.role == "system":
                system = system + "\n\n" + m.content if system else m.content
                continue
            api_messages.append({"role": m.role, "content": m.content})

        # Structured output via forced tool-use. Define a single tool
        # whose input_schema matches the Pydantic model, then force the
        # model to call it.
        schema = response_model.model_json_schema()
        tool_name = "structured_output"
        tools = [
            {
                "name": tool_name,
                "description": f"Return the structured {response_model.__name__} response.",
                "input_schema": schema,
            }
        ]

        def _call():
            return client.messages.create(
                model=model,
                system=system or "",
                messages=api_messages,
                tools=tools,
                tool_choice={"type": "tool", "name": tool_name},
                temperature=temperature,
                max_tokens=max_output_tokens,
            )

        response = await asyncio.to_thread(_call)

        # Extract the tool use block
        tool_input = None
        raw_text = ""
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                tool_input = block.input
                raw_text = json.dumps(tool_input)
                break

        if tool_input is None:
            raise RuntimeError(
                f"Anthropic {model} did not return a tool_use block "
                f"(stop_reason={response.stop_reason})"
            )

        parsed = response_model.model_validate(tool_input)

        # Usage extraction
        usage_obj = response.usage
        input_tokens = getattr(usage_obj, "input_tokens", 0) or 0
        output_tokens = getattr(usage_obj, "output_tokens", 0) or 0
        cache_read_tokens = getattr(usage_obj, "cache_read_input_tokens", 0) or 0

        # Subtract cache reads from input for pricing consistency
        if cache_read_tokens and cache_read_tokens <= input_tokens:
            input_tokens = input_tokens - cache_read_tokens

        usage = Usage(
            provider="anthropic",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )
        return CompletionResult(parsed=parsed, usage=usage, raw_text=raw_text)

    async def count_tokens(self, *, model: str, text: str) -> int:
        """Approximate token count. Claude tokenizer is ~3.5 chars/token
        for English + JSON."""
        return max(1, int(len(text) / 3.5))


def register() -> None:
    """Idempotent registration. Only registers when ANTHROPIC_API_KEY is set."""
    register_adapter("anthropic", AnthropicAdapter)


# Conditionally register on import — only when the API key is available.
if os.environ.get("ANTHROPIC_API_KEY"):
    register()
else:
    logger.debug(
        "ANTHROPIC_API_KEY not set — Anthropic adapter not registered. "
        "Models will appear grayed out in the admin UI."
    )
