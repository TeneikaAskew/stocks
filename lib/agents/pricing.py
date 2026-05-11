"""
LLM pricing table and cost calculation.

Centralizes per-(provider, model) USD-per-million-token rates so every
adapter's Usage object can be normalized to the same `cost_usd` field.
Rates are hand-maintained from public pricing pages; update when
providers change their tiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Provider = Literal["vertex", "anthropic", "openai"]


@dataclass(frozen=True)
class ModelRates:
    """Per-million-token USD rates for a single model."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    # Cached input rates (usually cheaper). Fallback to input rate if
    # the provider doesn't distinguish cache reads.
    cache_read_usd_per_mtok: Optional[float] = None
    cache_write_usd_per_mtok: Optional[float] = None


# ---------------------------------------------------------------------------
# Price table. Keyed by (provider, model). Any model not listed here
# raises in `cost_for()` so we fail loud on unknown models rather than
# silently reporting zero cost.
# ---------------------------------------------------------------------------

PRICE_TABLE: dict[tuple[Provider, str], ModelRates] = {
    # Vertex Gemini — https://cloud.google.com/vertex-ai/generative-ai/pricing
    # Rates verified against the official pricing page 2026-05-11. Cache-read
    # rate is the steady-state context-cache hit rate; non-global pricing
    # variants (effective 2026-07-01) are not modeled — we use the global
    # rate as the canonical value.
    ("vertex", "gemini-3.1-flash-lite"): ModelRates(
        input_usd_per_mtok=0.25,
        output_usd_per_mtok=1.50,
        cache_read_usd_per_mtok=0.025,
    ),
    ("vertex", "gemini-3-flash"): ModelRates(
        input_usd_per_mtok=0.50,
        output_usd_per_mtok=3.00,
        cache_read_usd_per_mtok=0.05,
    ),
    ("vertex", "gemini-2.5-flash"): ModelRates(
        input_usd_per_mtok=0.30,
        output_usd_per_mtok=2.50,
        cache_read_usd_per_mtok=0.03,
    ),
    ("vertex", "gemini-2.5-flash-lite"): ModelRates(
        input_usd_per_mtok=0.10,
        output_usd_per_mtok=0.40,
        cache_read_usd_per_mtok=0.01,
    ),
    # gemini-2.5-pro has tiered pricing (≤200K vs >200K input). The repo
    # uses the ≤200K rate — every analyst/risk prompt in this pipeline is
    # well under 200K tokens, so the cheaper tier always applies.
    ("vertex", "gemini-2.5-pro"): ModelRates(
        input_usd_per_mtok=1.25,
        output_usd_per_mtok=10.00,
        cache_read_usd_per_mtok=0.13,
    ),
    ("vertex", "gemini-2.0-flash"): ModelRates(
        input_usd_per_mtok=0.15,
        output_usd_per_mtok=0.60,
        cache_read_usd_per_mtok=0.025,
    ),
    ("vertex", "gemini-2.0-flash-lite"): ModelRates(
        input_usd_per_mtok=0.075,
        output_usd_per_mtok=0.30,
    ),
    # Anthropic — https://www.anthropic.com/pricing
    ("anthropic", "claude-opus-4-6"): ModelRates(
        input_usd_per_mtok=15.00,
        output_usd_per_mtok=75.00,
        cache_read_usd_per_mtok=1.50,
        cache_write_usd_per_mtok=18.75,
    ),
    ("anthropic", "claude-sonnet-4-6"): ModelRates(
        input_usd_per_mtok=3.00,
        output_usd_per_mtok=15.00,
        cache_read_usd_per_mtok=0.30,
        cache_write_usd_per_mtok=3.75,
    ),
    ("anthropic", "claude-haiku-4-5-20251001"): ModelRates(
        input_usd_per_mtok=1.00,
        output_usd_per_mtok=5.00,
        cache_read_usd_per_mtok=0.10,
        cache_write_usd_per_mtok=1.25,
    ),
    # OpenAI — https://openai.com/api/pricing/
    ("openai", "gpt-5"): ModelRates(
        input_usd_per_mtok=5.00,
        output_usd_per_mtok=15.00,
        cache_read_usd_per_mtok=1.25,
    ),
    ("openai", "gpt-5-mini"): ModelRates(
        input_usd_per_mtok=0.15,
        output_usd_per_mtok=0.60,
        cache_read_usd_per_mtok=0.075,
    ),
}


@dataclass(frozen=True)
class Usage:
    """Provider-normalized token usage for a single LLM call."""

    provider: Provider
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def cost_usd(self) -> float:
        """Compute USD cost using the PRICE_TABLE. Raises KeyError if
        the (provider, model) is not listed — we prefer loud failure
        over silent zero-cost reporting."""
        rates = PRICE_TABLE[(self.provider, self.model)]

        # Uncached input tokens = total input minus whatever was read
        # from cache. Some providers (Anthropic) report these as
        # separate fields; others (OpenAI, Vertex) already subtract.
        # We assume input_tokens is the uncached portion and
        # cache_read_tokens is in addition. Adapters must follow this
        # convention.
        cost = (
            self.input_tokens / 1_000_000 * rates.input_usd_per_mtok
            + self.output_tokens / 1_000_000 * rates.output_usd_per_mtok
        )
        if self.cache_read_tokens:
            cache_rate = (
                rates.cache_read_usd_per_mtok
                if rates.cache_read_usd_per_mtok is not None
                else rates.input_usd_per_mtok
            )
            cost += self.cache_read_tokens / 1_000_000 * cache_rate
        if self.cache_write_tokens:
            write_rate = (
                rates.cache_write_usd_per_mtok
                if rates.cache_write_usd_per_mtok is not None
                else rates.input_usd_per_mtok
            )
            cost += self.cache_write_tokens / 1_000_000 * write_rate
        return cost


def list_priced_models() -> list[tuple[Provider, str]]:
    """All (provider, model) pairs with a known price. Used by the
    admin dashboard to render the dropdown options."""
    return sorted(PRICE_TABLE.keys())
