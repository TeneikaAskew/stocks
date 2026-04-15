"""
Vertex AI Gemini adapter for LLMClient.

Uses the google-genai SDK in Vertex mode with the same credential path
as platform.api.routers.insights (`.gcp-key.json` via
GOOGLE_APPLICATION_CREDENTIALS). Structured output is enforced by
passing the Pydantic model's `response_schema`; Gemini returns JSON
that we parse back into the model.

Sync SDK calls are wrapped in `asyncio.to_thread` so the orchestrator's
`asyncio.gather` over parallel analysts gives real concurrency.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from .llm_client import CompletionResult, LLMClient, Message, register_adapter
from .pricing import Usage

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GCP_PROJECT = "adept-mountain-474619-d4"
DEFAULT_GCP_LOCATION = "us-east1"
DEFAULT_GCP_KEY_FILE = str(PROJECT_ROOT / ".gcp-key.json")


def _get_genai_client():
    """Lazy-initialize the google-genai Vertex client. Reused between
    calls in the same process."""
    from google.oauth2 import service_account
    from google import genai

    project = os.environ.get("GCP_PROJECT_ID", DEFAULT_GCP_PROJECT)
    location = os.environ.get("GCP_REGION", DEFAULT_GCP_LOCATION)
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_GCP_KEY_FILE)

    credentials = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        credentials=credentials,
    )


class VertexGeminiAdapter(LLMClient):
    """Vertex AI Gemini implementation of LLMClient."""

    provider = "vertex"

    _client = None  # lazy singleton across instances

    @classmethod
    def _client_singleton(cls):
        if cls._client is None:
            cls._client = _get_genai_client()
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
        from google.genai import types

        client = self._client_singleton()

        # Vertex Gemini "contents" expects alternating user/model turns.
        # System goes in `system_instruction`, not contents.
        contents: list[types.Content] = []
        for m in messages:
            if m.role == "system":
                # System messages are hoisted to system_instruction; extra
                # system turns are merged into it.
                system = system + "\n\n" + m.content if system else m.content
                continue
            role = "user" if m.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))

        # Structured output via response_schema. Pydantic v2's
        # model_json_schema() produces a draft-2020 JSON schema; Gemini
        # accepts an OpenAPI-subset schema, and google-genai accepts a
        # Pydantic class directly for convenience.
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_schema=response_model,
        )

        def _call():
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        response = await asyncio.to_thread(_call)

        raw_text = response.text or ""
        if not raw_text:
            raise RuntimeError(
                f"Gemini returned empty response for model={model} "
                f"(finish_reason={getattr(response, 'finish_reason', None)})"
            )

        parsed = response_model.model_validate_json(raw_text)

        # Usage extraction. google-genai puts it on response.usage_metadata.
        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta is not None:
            input_tokens = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
            output_tokens = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
            cache_read_tokens = int(
                getattr(usage_meta, "cached_content_token_count", 0) or 0
            )
            # Subtract cache reads from input so the pricing math works.
            if cache_read_tokens and cache_read_tokens <= input_tokens:
                input_tokens = input_tokens - cache_read_tokens
        else:
            input_tokens = output_tokens = cache_read_tokens = 0

        usage = Usage(
            provider="vertex",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )
        return CompletionResult(parsed=parsed, usage=usage, raw_text=raw_text)

    async def count_tokens(self, *, model: str, text: str) -> int:
        """Approximate token count. Gemini offers count_tokens but it's
        an RPC; we use a cheap heuristic for pre-flight estimates."""
        # ~4 chars per token is within 15% for English + JSON.
        return max(1, len(text) // 4)


def register() -> None:
    """Idempotent registration. Called by lib.agents.__init__ or
    explicitly in tests."""
    register_adapter("vertex", VertexGeminiAdapter)


# Register on import so `get_adapter('vertex')` works immediately.
register()
