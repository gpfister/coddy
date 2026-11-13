"""Unit tests for schema sanitization and Gemini API compatibility."""

from google.adk.models.llm_request import LlmRequest
from google.genai import _transformers

from app.coddy.agentic.schemas.enhanced_user_request import EnhancedUserRequest
from app.coddy.agentic.schemas.research import EpisodeResearchResult, ResearchReport
from app.coddy.agentic.schemas.research_plan import ResearchPlan
from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest
from app.coddy.helpers.schema_helpers import (
    gemini_schema_before_model_callback,
    sanitize_gemini_schema,
)


def _has_additional_properties(d) -> bool:
    """Recursively checks if a dict or list contains additionalProperties or additional_properties."""
    if isinstance(d, dict):
        if "additionalProperties" in d or "additional_properties" in d:
            return True
        return any(_has_additional_properties(v) for v in d.values())
    if isinstance(d, list):
        return any(_has_additional_properties(item) for item in d)
    return False


def test_sanitize_gemini_schema_pydantic_models():
    """Verify that additionalProperties is stripped from all Coddy Pydantic schemas."""
    schemas = [
        SanitizedUserRequest,
        EnhancedUserRequest,
        ResearchPlan,
        EpisodeResearchResult,
        ResearchReport,
    ]
    for model in schemas:
        raw_schema = model.model_json_schema()
        assert _has_additional_properties(raw_schema), (
            f"{model.__name__} should have extra='forbid' additionalProperties"
        )

        cleaned = sanitize_gemini_schema(model)
        assert isinstance(cleaned, dict)
        assert not _has_additional_properties(cleaned), f"additionalProperties must be stripped from {model.__name__}"


def test_sanitize_gemini_schema_types_schema():
    """Verify that types.Schema instances are sanitized."""
    raw_schema = _transformers.t_schema(None, SanitizedUserRequest)
    assert raw_schema.additional_properties is False

    cleaned = sanitize_gemini_schema(raw_schema)
    assert not _has_additional_properties(cleaned)

    re_validated = _transformers.t_schema(None, cleaned)
    assert re_validated.additional_properties is None
    dumped = re_validated.to_json_dict()
    assert "additional_properties" not in dumped


def test_sanitize_gemini_schema_nested_dict():
    """Verify recursive cleaning of nested dictionaries and lists."""
    dirty = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additional_properties": False,
                    "properties": {"name": {"type": "string"}},
                },
            }
        },
    }
    cleaned = sanitize_gemini_schema(dirty)
    assert not _has_additional_properties(cleaned)
    assert "properties" in cleaned
    assert "name" in cleaned["properties"]["items"]["items"]["properties"]


def test_gemini_schema_before_model_callback():
    """Verify that before_model_callback sanitizes llm_request.config.response_schema."""
    req = LlmRequest()
    req.set_output_schema(SanitizedUserRequest)

    assert req.config.response_schema == SanitizedUserRequest

    gemini_schema_before_model_callback(None, req)
    assert isinstance(req.config.response_schema, dict)
    assert not _has_additional_properties(req.config.response_schema)


def test_gemini_schema_before_model_callback_graceful():
    """Verify that callback handles None requests and empty configs without error."""
    gemini_schema_before_model_callback(None, None)

    req = LlmRequest()
    req.config = None
    gemini_schema_before_model_callback(None, req)
