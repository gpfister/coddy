"""Pydantic v2 strict models for LLM pricing catalogs and step cost breakdowns."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PricingTier(BaseModel):
    """Pricing rates for a specific token prompt volume tier."""

    model_config = ConfigDict(extra="forbid")

    min_prompt_tokens: int = Field(default=0, description="Minimum prompt tokens for tier qualification.")
    max_prompt_tokens: int | None = Field(default=None, description="Maximum prompt tokens or null if unbounded.")
    input_eur: float = Field(description="Cost in EUR per pricing unit for non-cached input tokens.")
    input_audio_eur: float = Field(default=0.0, description="Cost in EUR per pricing unit for audio input tokens.")
    output_eur: float = Field(description="Cost in EUR per pricing unit for completion and reasoning output tokens.")
    context_cache_read_eur: float = Field(
        default=0.0, description="Cost in EUR per pricing unit for cached prompt tokens read."
    )
    context_cache_storage_eur_per_hour: float = Field(
        default=0.0, description="Cost in EUR per hour for context cache storage."
    )


class ModelPricing(BaseModel):
    """Pricing configuration and tier specifications for a model."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(description="Unique model identifier (e.g. gemini-3.5-flash-lite).")
    display_name: str = Field(description="Human-readable model name.")
    context_window_tokens: int = Field(description="Total supported context window in tokens.")
    max_output_tokens: int = Field(description="Maximum output generation limit in tokens.")
    tiers: list[PricingTier] = Field(description="Ordered list of token pricing tiers.")


class PricingCatalog(BaseModel):
    """Authoritative pricing catalog containing model tiers and currency metadata."""

    model_config = ConfigDict(extra="forbid")

    currency: str = Field(default="EUR", description="ISO currency code (e.g. EUR).")
    in_effect_date: str = Field(description="ISO date string when pricing went into effect.")
    pricing_unit_tokens: int = Field(default=1000000, description="Token unit for rates (typically 1,000,000).")
    cache_storage_unit_hours: int = Field(default=1, description="Hour unit for cache storage pricing.")
    usd_to_eur_benchmark_rate: float = Field(description="Benchmark USD to EUR conversion rate.")
    regional_location_premium_factor: float = Field(description="Location factor applied to base rates.")
    models: list[ModelPricing] = Field(description="Registered models with pricing tiers.")


class CostBreakdown(BaseModel):
    """Detailed cost breakdown for a single model invocation step."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(description="Resolved model identifier.")
    currency: str = Field(default="EUR", description="ISO currency code.")
    prompt_tokens: int = Field(default=0, description="Total prompt tokens.")
    cached_tokens: int = Field(default=0, description="Cached prompt tokens read.")
    non_cached_input_tokens: int = Field(default=0, description="Non-cached input tokens charged at full rate.")
    completion_tokens: int = Field(default=0, description="Output/completion tokens charged at output rate.")
    input_rate_per_m: float = Field(default=0.0, description="EUR rate per 1M non-cached input tokens.")
    cache_read_rate_per_m: float = Field(default=0.0, description="EUR rate per 1M cached read tokens.")
    output_rate_per_m: float = Field(default=0.0, description="EUR rate per 1M output tokens.")
    input_cost_eur: float = Field(default=0.0, description="Computed cost for non-cached input tokens in EUR.")
    cache_read_cost_eur: float = Field(default=0.0, description="Computed cost for cached prompt tokens in EUR.")
    output_cost_eur: float = Field(default=0.0, description="Computed cost for output tokens in EUR.")
    total_cost_eur: float = Field(default=0.0, description="Total computed step cost in EUR.")
