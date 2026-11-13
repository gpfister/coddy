"""Configuration subsystem for Coddy.

Provides structured, type-safe settings for Coddy worker agents and runtime.
Enforces Pydantic v2 strict models (extra="forbid").
"""

import os

from pydantic import BaseModel, ConfigDict, Field

from app.coddy.helpers.env_helpers import load_environment

# Load environment variables from .env files and normalize credentials
load_environment()

DEFAULT_API_KEY: str = os.getenv("OPENAI_API_KEY", "dummy")


class CodingSanitizeConfig(BaseModel):
    """Configuration for coding-sanitize worker agent (STEP 1: coding-sanitize).

    Configurable settings:
    - model: LLM model identifier.
    - reasoning_effort: Reasoning effort level ('none', 'low', 'medium', 'high').
    - timeout: Inference timeout in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default_factory=lambda: os.getenv("CODING_SANITIZE_MODEL", "google/gemma-4-12b"),
        description="Local LLM model identifier for coding-sanitize worker agent.",
    )
    reasoning_effort: str | None = Field(
        default_factory=lambda: os.getenv("CODING_SANITIZE_REASONING_EFFORT", "none"),
        description="Reasoning effort setting ('none', 'low', 'medium', 'high').",
    )
    timeout: float = Field(
        default_factory=lambda: float(os.getenv("CODING_SANITIZE_TIMEOUT", "120.0")),
        description="Inference timeout in seconds for coding-sanitize worker agent.",
    )


class CodingResearchPlanConfig(BaseModel):
    """Configuration for coding-research-plan worker agent (STEP 2: coding-research-plan).

    Configurable settings:
    - model: LLM model identifier (default: google/gemma-4-26b-a4b-qat).
    - reasoning_effort: Reasoning effort level ('none', 'low', 'medium', 'high').
    - timeout: Inference timeout in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default_factory=lambda: os.getenv("CODING_RESEARCH_PLAN_MODEL", "google/gemma-4-26b-a4b-qat"),
        description="Local LLM model identifier for coding-research-plan worker agent.",
    )
    reasoning_effort: str | None = Field(
        default_factory=lambda: os.getenv("CODING_RESEARCH_PLAN_REASONING_EFFORT", "high"),
        description="Reasoning effort setting ('none', 'low', 'medium', 'high').",
    )
    thinking_budget: int = Field(
        default_factory=lambda: int(os.getenv("CODING_RESEARCH_PLAN_THINKING_BUDGET", "2048")),
        description="Thinking budget in tokens for heavy reasoning.",
    )
    timeout: float = Field(
        default_factory=lambda: float(os.getenv("CODING_RESEARCH_PLAN_TIMEOUT", "180.0")),
        description="Inference timeout in seconds for coding-research-plan worker agent.",
    )


class CoddyConfig(BaseModel):
    """Global configuration model for Coddy."""

    model_config = ConfigDict(extra="forbid")

    coding_sanitize: CodingSanitizeConfig = Field(
        default_factory=CodingSanitizeConfig,
        description="Configuration for coding-sanitize agent.",
    )
    coding_research_plan: CodingResearchPlanConfig = Field(
        default_factory=CodingResearchPlanConfig,
        description="Configuration for coding-research-plan agent.",
    )


# Active module-level configuration instances
coding_sanitize_config = CodingSanitizeConfig()
coding_research_plan_config = CodingResearchPlanConfig()
config = CoddyConfig(
    coding_sanitize=coding_sanitize_config,
    coding_research_plan=coding_research_plan_config,
)


def get_sanitize_config() -> CodingSanitizeConfig:
    """Returns the active coding-sanitize configuration."""
    return coding_sanitize_config


def get_research_plan_config() -> CodingResearchPlanConfig:
    """Returns the active coding-research-plan configuration."""
    return coding_research_plan_config
