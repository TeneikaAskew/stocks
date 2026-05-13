"""Unit tests for lib.agents.pricing cost accounting."""

from __future__ import annotations

import pytest

from lib.agents.pricing import PRICE_TABLE, ModelRates, Usage, list_priced_models


def test_price_table_keys_use_known_providers():
    for provider, _ in PRICE_TABLE:
        assert provider in ("vertex", "anthropic", "openai")


def test_price_table_has_vertex_gemini_flash_day_one_default():
    assert ("vertex", "gemini-2.0-flash") in PRICE_TABLE


def test_usage_cost_basic_input_output():
    u = Usage(
        provider="vertex",
        model="gemini-2.0-flash",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )
    # 1M input @ $0.15 + 0.5M output @ $0.60 = $0.15 + $0.30 = $0.45
    assert u.cost_usd() == pytest.approx(0.45, rel=1e-6)


def test_usage_cost_with_cache_read_discount():
    u = Usage(
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=1_000,       # uncached
        output_tokens=500,
        cache_read_tokens=10_000, # 10x the uncached, at discount rate
    )
    # 1k input @ $3/M = $0.003
    # 500 output @ $15/M = $0.0075
    # 10k cache-read @ $0.30/M = $0.003
    # Total ~= $0.0135
    assert u.cost_usd() == pytest.approx(0.0135, rel=1e-4)


def test_usage_cost_cache_write_fallback_to_input_rate():
    """If a model lacks an explicit cache_write rate the computation
    must fall back to the input rate (not silently ignore)."""
    # Patch a fake model without cache_write rate
    PRICE_TABLE[("vertex", "gemini-fake")] = ModelRates(
        input_usd_per_mtok=1.0,
        output_usd_per_mtok=2.0,
        cache_read_usd_per_mtok=0.25,
        cache_write_usd_per_mtok=None,
    )
    try:
        u = Usage(
            provider="vertex",
            model="gemini-fake",
            input_tokens=0,
            output_tokens=0,
            cache_write_tokens=1_000_000,
        )
        # Falls back to $1/M = $1.00
        assert u.cost_usd() == pytest.approx(1.0, rel=1e-6)
    finally:
        del PRICE_TABLE[("vertex", "gemini-fake")]


def test_usage_cost_unknown_model_raises():
    u = Usage(
        provider="anthropic",
        model="claude-nonexistent-99",
        input_tokens=100,
        output_tokens=100,
    )
    with pytest.raises(KeyError):
        u.cost_usd()


def test_list_priced_models_is_sorted_and_nonempty():
    models = list_priced_models()
    assert len(models) > 0
    assert models == sorted(models)
