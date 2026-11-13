"""Pricing service and cost calculation engine for token consumption."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.coddy.agentic.schemas.pricing import CostBreakdown, ModelPricing, PricingCatalog, PricingTier
from app.coddy.utils.ui.cost_formatter import (
    format_cost_eur,
    round_high_cent,
    round_high_thousandth,
)

__all__ = [
    "PricingService",
    "format_cost_eur",
    "get_pricing_service",
    "round_high_cent",
    "round_high_thousandth",
]

logger = logging.getLogger(__name__)

DEFAULT_PRICING_FILE = Path(__file__).parent.parent.parent / "data" / "pricing.json"


class PricingService:
    """Calculates model invocation costs against an authoritative pricing catalog."""

    def __init__(self, catalog_path: Path | str | None = None) -> None:
        """Initializes PricingService with optional path to pricing catalog JSON."""
        if catalog_path is not None:
            self._catalog_path = Path(catalog_path)
        else:
            env_path = os.getenv("CODDY_PRICING_PATH")
            self._catalog_path = Path(env_path) if env_path else DEFAULT_PRICING_FILE

        self._catalog: PricingCatalog | None = None
        self._models_by_id: dict[str, ModelPricing] = {}
        self._load_catalog()

    @property
    def catalog(self) -> PricingCatalog:
        """Returns the loaded PricingCatalog."""
        if self._catalog is None:
            self._load_catalog()
        assert self._catalog is not None
        return self._catalog

    def _load_catalog(self) -> None:
        """Loads and parses the pricing catalog JSON using strict Pydantic schema."""
        if not self._catalog_path.exists():
            logger.warning("Pricing catalog file not found at %s. Initializing empty catalog.", self._catalog_path)
            self._catalog = PricingCatalog(
                currency="EUR",
                in_effect_date="2026-11-11",
                pricing_unit_tokens=1000000,
                cache_storage_unit_hours=1,
                usd_to_eur_benchmark_rate=0.92,
                regional_location_premium_factor=1.10,
                models=[],
            )
            self._models_by_id = {}
            return

        with open(self._catalog_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        self._catalog = PricingCatalog.model_validate(raw_data)
        self._models_by_id = {model.model_id.lower(): model for model in self._catalog.models}

    @staticmethod
    def normalize_model_id(model_name: str) -> str:
        """Normalizes an arbitrary model string to canonical model ID.

        Strips provider prefixes (e.g. 'google/', 'models/') and standardizes casing.
        """
        cleaned = model_name.strip().lower()
        if cleaned.startswith("google/"):
            cleaned = cleaned[len("google/") :]
        if cleaned.startswith("models/"):
            cleaned = cleaned[len("models/") :]
        return cleaned

    def get_model_pricing(self, model_name: str) -> ModelPricing | None:
        """Looks up ModelPricing definition for a given model identifier."""
        canonical_id = self.normalize_model_id(model_name)
        if canonical_id in self._models_by_id:
            return self._models_by_id[canonical_id]

        # Secondary fuzzy prefix/suffix match if exact normalized match fails
        for registered_id, model_def in self._models_by_id.items():
            if registered_id == canonical_id or canonical_id.endswith(registered_id):
                return model_def
        return None

    def find_matching_tier(self, model: ModelPricing, prompt_tokens: int) -> PricingTier:
        """Finds matching pricing tier based on prompt tokens volume."""
        for tier in model.tiers:
            if tier.min_prompt_tokens <= prompt_tokens:
                if tier.max_prompt_tokens is None or prompt_tokens <= tier.max_prompt_tokens:
                    return tier

        # Fallback to the first tier if none explicitly matches bounds
        return model.tiers[0]

    def calculate_step_cost(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
    ) -> CostBreakdown:
        """Calculates precise monetary cost breakdown for a step model invocation.

        Args:
            model_name: Model identifier used in invocation.
            prompt_tokens: Total prompt tokens sent to model.
            completion_tokens: Candidates/output tokens generated.
            cached_tokens: Cached prompt tokens read from context cache.

        Returns:
            CostBreakdown with token counts, unit rates, and costs in EUR.
        """
        model = self.get_model_pricing(model_name)
        if model is None or not model.tiers:
            # Unlisted, custom, or local models (e.g. local Gemma) evaluate to €0.00
            return CostBreakdown(
                model_id=model_name,
                currency=self.catalog.currency,
                prompt_tokens=prompt_tokens,
                cached_tokens=cached_tokens,
                non_cached_input_tokens=max(0, prompt_tokens - cached_tokens),
                completion_tokens=completion_tokens,
                input_rate_per_m=0.0,
                cache_read_rate_per_m=0.0,
                output_rate_per_m=0.0,
                input_cost_eur=0.0,
                cache_read_cost_eur=0.0,
                output_cost_eur=0.0,
                total_cost_eur=0.0,
            )

        tier = self.find_matching_tier(model, prompt_tokens)
        unit = float(self.catalog.pricing_unit_tokens)

        effective_cached = max(0, min(cached_tokens, prompt_tokens))
        effective_non_cached = max(0, prompt_tokens - effective_cached)

        input_cost = (effective_non_cached / unit) * tier.input_eur
        cache_read_cost = (effective_cached / unit) * tier.context_cache_read_eur
        output_cost = (completion_tokens / unit) * tier.output_eur
        total_cost = input_cost + cache_read_cost + output_cost

        return CostBreakdown(
            model_id=model.model_id,
            currency=self.catalog.currency,
            prompt_tokens=prompt_tokens,
            cached_tokens=effective_cached,
            non_cached_input_tokens=effective_non_cached,
            completion_tokens=completion_tokens,
            input_rate_per_m=tier.input_eur,
            cache_read_rate_per_m=tier.context_cache_read_eur,
            output_rate_per_m=tier.output_eur,
            input_cost_eur=input_cost,
            cache_read_cost_eur=cache_read_cost,
            output_cost_eur=output_cost,
            total_cost_eur=total_cost,
        )


_pricing_service_instance: PricingService | None = None


def get_pricing_service(catalog_path: Path | str | None = None) -> PricingService:
    """Returns singleton PricingService instance."""
    global _pricing_service_instance
    if _pricing_service_instance is None or catalog_path is not None:
        _pricing_service_instance = PricingService(catalog_path=catalog_path)
    return _pricing_service_instance
