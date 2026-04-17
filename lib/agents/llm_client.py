"""
Provider-agnostic LLM client interface.

The pipeline calls `client.complete(...)` without knowing which
provider serves the underlying model; the adapter for the current
role is resolved from the model_routing snapshot captured at pipeline
start (see lib.agents.orchestrator).

Each concrete adapter lives in a separate module and registers itself
via `register_adapter`. Adapters are async and must wrap sync provider
SDK calls in `asyncio.to_thread` so `asyncio.gather` over the parallel
analyst tier gives real concurrency.

A single rule every adapter must obey: the returned Usage reports
`input_tokens` as the *uncached* input portion; cache reads live in
`cache_read_tokens`. This keeps `Usage.cost_usd()` arithmetic simple.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from pydantic import BaseModel

from .pricing import Provider, Usage
from .schema import AgentRole


@dataclass
class Message:
    """Single chat-style message."""

    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class CompletionResult:
    """What `LLMClient.complete` returns. `parsed` is an instance of
    the response_model the caller passed in, guaranteed non-None on
    success. `usage` is normalized across providers."""

    parsed: BaseModel
    usage: Usage
    raw_text: Optional[str] = None


class LLMClient(abc.ABC):
    """Adapter base class. One subclass per provider."""

    provider: Provider

    @abc.abstractmethod
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
        """Run a structured completion.

        Every provider path must:
          - Force the model to emit JSON validating against
            `response_model` (Vertex: response_schema from
            `model_json_schema()`; Anthropic: tool-use forced choice;
            OpenAI: response_format json_schema strict).
          - Parse the JSON into `response_model` before returning.
          - Return uncached input tokens in `Usage.input_tokens` and
            cache reads in `Usage.cache_read_tokens`.
          - Wrap sync SDK calls in `asyncio.to_thread`.
        """

    @abc.abstractmethod
    async def count_tokens(self, *, model: str, text: str) -> int:
        """Approximate token count for pre-flight cost estimates used
        by the /admin Test button. Adapters may use the provider's
        tokenizer or a local approximation."""


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[Provider, Type[LLMClient]] = {}


def register_adapter(provider: Provider, cls: Type[LLMClient]) -> None:
    _REGISTRY[provider] = cls


def get_adapter(provider: Provider) -> LLMClient:
    """Return an instance of the adapter for the given provider.
    Adapters are expected to be cheap to instantiate (they hold a
    lazy-init SDK client). Raises KeyError if the provider isn't
    registered — e.g. ANTHROPIC_API_KEY missing at import time."""
    try:
        cls = _REGISTRY[provider]
    except KeyError as exc:
        raise KeyError(
            f"No LLM adapter registered for provider {provider!r}. "
            "Is the relevant SDK installed and credentials configured?"
        ) from exc
    return cls()


def available_providers() -> list[Provider]:
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Route snapshot — the orchestrator freezes per-role routes at pipeline
# start so mid-run admin flips can't produce inconsistent model_versions
# in a single report.
# ---------------------------------------------------------------------------


@dataclass
class RouteSnapshot:
    """Immutable per-role routing captured at pipeline start."""

    routes: dict[AgentRole, tuple[Provider, str]] = field(default_factory=dict)

    def get(self, role: AgentRole) -> tuple[Provider, str]:
        return self.routes[role]

    def model_versions(self) -> dict[str, str]:
        """Flatten to the JSONB-friendly shape used in InsightReport."""
        return {role: f"{prov}:{model}" for role, (prov, model) in self.routes.items()}
