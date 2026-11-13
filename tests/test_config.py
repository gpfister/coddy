"""Unit tests for Coddy configuration subsystem."""

import pytest
from pydantic import ValidationError

from app.coddy.config import (
    CoddyConfig,
    CodingResearchPlanConfig,
    CodingSanitizeConfig,
    get_research_plan_config,
    get_sanitize_config,
)


def test_coding_sanitize_config_defaults(monkeypatch):
    """Verify default values for CodingSanitizeConfig when no env vars are set."""
    monkeypatch.delenv("CODING_SANITIZE_MODEL", raising=False)
    monkeypatch.delenv("CODING_SANITIZE_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CODING_SANITIZE_TIMEOUT", raising=False)

    cfg = CodingSanitizeConfig()
    assert cfg.model == "google/gemma-4-12b"
    assert cfg.reasoning_effort == "none"
    assert cfg.timeout == 120.0


def test_coding_sanitize_config_env_overrides(monkeypatch):
    """Verify env vars override defaults for CodingSanitizeConfig."""
    monkeypatch.setenv("CODING_SANITIZE_MODEL", "custom/model-id")
    monkeypatch.setenv("CODING_SANITIZE_REASONING_EFFORT", "low")
    monkeypatch.setenv("CODING_SANITIZE_TIMEOUT", "120.5")

    cfg = CodingSanitizeConfig()
    assert cfg.model == "custom/model-id"
    assert cfg.reasoning_effort == "low"
    assert cfg.timeout == 120.5


def test_coding_sanitize_config_extra_forbid():
    """Verify Rule R1: strict schema with extra='forbid'."""
    with pytest.raises(ValidationError):
        CodingSanitizeConfig(extra_field="disallowed")


def test_coddy_config_container():
    """Verify CoddyConfig global container and get_sanitize_config helper."""
    global_cfg = CoddyConfig()
    assert global_cfg.coding_sanitize is not None
    assert global_cfg.coding_sanitize.model == "google/gemma-4-12b"

    helper_cfg = get_sanitize_config()
    assert helper_cfg.model == global_cfg.coding_sanitize.model


def test_coding_research_plan_config_defaults(monkeypatch):
    """Verify default values for CodingResearchPlanConfig."""
    monkeypatch.delenv("CODING_RESEARCH_PLAN_MODEL", raising=False)
    monkeypatch.delenv("CODING_RESEARCH_PLAN_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CODING_RESEARCH_PLAN_THINKING_BUDGET", raising=False)
    monkeypatch.delenv("CODING_RESEARCH_PLAN_TIMEOUT", raising=False)

    cfg = CodingResearchPlanConfig()
    assert cfg.model == "google/gemma-4-26b-a4b-qat"
    assert cfg.reasoning_effort == "high"
    assert cfg.thinking_budget == 2048
    assert cfg.timeout == 180.0

    helper_cfg = get_research_plan_config()
    assert helper_cfg.model == cfg.model


def test_coding_research_plan_config_extra_forbid():
    """Verify Rule R1: strict schema with extra='forbid' for research plan config."""
    with pytest.raises(ValidationError):
        CodingResearchPlanConfig(unknown_field="error")
