"""Hermetic unit tests for PricingService, pricing schemas, and currency ceiling rounding."""

from __future__ import annotations

import json
from pathlib import Path

from app.coddy.agentic.schemas.pricing import PricingCatalog
from app.coddy.agentic.services.pricing_service import (
    PricingService,
    format_cost_eur,
    get_pricing_service,
    round_high_cent,
)


def test_pricing_catalog_loading_and_schema():
    """Verify loading default pricing catalog and strict schema validation."""
    service = get_pricing_service()
    catalog = service.catalog
    assert isinstance(catalog, PricingCatalog)
    assert catalog.currency == "EUR"
    assert catalog.in_effect_date == "2026-11-11"
    assert catalog.pricing_unit_tokens == 1_000_000
    assert len(catalog.models) == 4

    model_ids = {m.model_id for m in catalog.models}
    assert "gemini-4-carbon" in model_ids
    assert "gemini-4-argon" in model_ids
    assert "gemini-3.8-flash" in model_ids
    assert "gemini-3.5-flash-lite" in model_ids


def test_calculate_step_cost_gemini_35_flash_lite():
    """Verify step cost calculation for Gemini 3.5 Flash-Lite."""
    service = get_pricing_service()

    # 1,000,000 prompt tokens, 500,000 completion tokens, no cache
    cost = service.calculate_step_cost(
        model_name="gemini-3.5-flash-lite",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
        cached_tokens=0,
    )
    assert cost.currency == "EUR"
    assert cost.input_rate_per_m == 0.3036
    assert cost.output_rate_per_m == 2.53
    assert cost.input_cost_eur == 0.3036
    assert cost.output_cost_eur == 1.265
    assert cost.cache_read_cost_eur == 0.0
    assert round(cost.total_cost_eur, 6) == round(0.3036 + 1.265, 6)


def test_calculate_step_cost_with_cached_tokens():
    """Verify cache read discount calculation."""
    service = get_pricing_service()

    # 1,000,000 prompt tokens with 400,000 cached tokens -> 600,000 non-cached
    cost = service.calculate_step_cost(
        model_name="gemini-3.8-flash",
        prompt_tokens=1_000_000,
        completion_tokens=200_000,
        cached_tokens=400_000,
    )
    # Gemini 3.8 Flash rates: input=0.759/1M, cache_read=0.0759/1M, output=3.795/1M
    expected_input = 0.6 * 0.759
    expected_cache = 0.4 * 0.0759
    expected_output = 0.2 * 3.795
    expected_total = expected_input + expected_cache + expected_output

    assert cost.prompt_tokens == 1_000_000
    assert cost.cached_tokens == 400_000
    assert cost.non_cached_input_tokens == 600_000
    assert round(cost.input_cost_eur, 6) == round(expected_input, 6)
    assert round(cost.cache_read_cost_eur, 6) == round(expected_cache, 6)
    assert round(cost.output_cost_eur, 6) == round(expected_output, 6)
    assert round(cost.total_cost_eur, 6) == round(expected_total, 6)


def test_model_normalization_and_prefixes():
    """Verify model name normalization with prefixes like google/ or models/."""
    service = get_pricing_service()

    cost_1 = service.calculate_step_cost(
        model_name="google/gemini-4-carbon",
        prompt_tokens=10_000,
        completion_tokens=5_000,
    )
    cost_2 = service.calculate_step_cost(
        model_name="models/gemini-4-carbon",
        prompt_tokens=10_000,
        completion_tokens=5_000,
    )
    assert cost_1.total_cost_eur > 0.0
    assert cost_1.total_cost_eur == cost_2.total_cost_eur
    assert cost_1.model_id == "gemini-4-carbon"


def test_unlisted_or_local_models_return_zero_cost():
    """Verify local Gemma or unlisted models evaluate to zero cost."""
    service = get_pricing_service()

    cost_local = service.calculate_step_cost(
        model_name="google/gemma-4-12b",
        prompt_tokens=50_000,
        completion_tokens=10_000,
    )
    assert cost_local.total_cost_eur == 0.0
    assert cost_local.input_cost_eur == 0.0
    assert cost_local.output_cost_eur == 0.0

    cost_unknown = service.calculate_step_cost(
        model_name="unknown-custom-model",
        prompt_tokens=10_000,
        completion_tokens=2_000,
    )
    assert cost_unknown.total_cost_eur == 0.0


def test_currency_high_thousandth_rounding():
    """Verify display rounding up to the nearest 1/1000th (ceiling rounding)."""
    # Fractional thousandths round up to next thousandth
    assert round_high_cent(0.0012) == 0.002
    assert format_cost_eur(0.0012) == "€0.002"

    assert round_high_cent(0.0001) == 0.001
    assert format_cost_eur(0.0001) == "€0.001"

    assert round_high_cent(0.0101) == 0.011
    assert format_cost_eur(0.0101) == "€0.011"

    assert round_high_cent(0.0100) == 0.010
    assert format_cost_eur(0.0100) == "€0.010"

    # Zero rounds to €0.000
    assert round_high_cent(0.0) == 0.0
    assert format_cost_eur(0.0) == "€0.000"

    # Negative guards round to 0.0
    assert round_high_cent(-0.5) == 0.0
    assert format_cost_eur(-0.5) == "€0.000"


def test_custom_pricing_catalog_path(tmp_path: Path):
    """Verify PricingService can load a custom catalog file."""
    custom_catalog = {
        "currency": "EUR",
        "in_effect_date": "2026-11-11",
        "pricing_unit_tokens": 1000000,
        "cache_storage_unit_hours": 1,
        "usd_to_eur_benchmark_rate": 0.92,
        "regional_location_premium_factor": 1.10,
        "models": [
            {
                "model_id": "test-model",
                "display_name": "Test Model",
                "context_window_tokens": 100000,
                "max_output_tokens": 10000,
                "tiers": [
                    {
                        "min_prompt_tokens": 0,
                        "max_prompt_tokens": None,
                        "input_eur": 1.0,
                        "input_audio_eur": 1.0,
                        "output_eur": 2.0,
                        "context_cache_read_eur": 0.5,
                        "context_cache_storage_eur_per_hour": 0.1,
                    }
                ],
            }
        ],
    }
    file_path = tmp_path / "custom_pricing.json"
    file_path.write_text(json.dumps(custom_catalog), encoding="utf-8")

    custom_service = PricingService(catalog_path=file_path)
    breakdown = custom_service.calculate_step_cost(
        model_name="test-model",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
    )
    assert breakdown.input_cost_eur == 1.0
    assert breakdown.output_cost_eur == 1.0
    assert breakdown.total_cost_eur == 2.0
