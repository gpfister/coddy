"""Schema sanitization helpers for Google GenAI / Gemini API compatibility."""

from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from pydantic import BaseModel


def sanitize_gemini_schema(schema: Any) -> Any:
    """Recursively removes additionalProperties and additional_properties from schemas.

    Google AI Studio (Gemini Developer API) does not support additionalProperties in its
    Schema protobuf definition and rejects payloads containing it with a 400 Bad Request error.
    This helper strips those fields while preserving all other properties and typing rules.
    """
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return sanitize_gemini_schema(schema.model_json_schema())
    if isinstance(schema, types.Schema):
        schema_dict = schema.model_dump(by_alias=True, exclude_none=True)
        return sanitize_gemini_schema(schema_dict)
    if isinstance(schema, dict):
        clean: dict[str, Any] = {}
        for k, v in schema.items():
            if k in ("additionalProperties", "additional_properties"):
                continue
            clean[k] = sanitize_gemini_schema(v)
        return clean
    if isinstance(schema, list):
        return [sanitize_gemini_schema(item) for item in schema]
    return schema


def gemini_schema_before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Pre-model callback ensuring response_schema is compatible with Google AI Studio / Gemini API."""
    if llm_request is not None and getattr(llm_request, "config", None) is not None:
        resp_schema = getattr(llm_request.config, "response_schema", None)
        if resp_schema is not None:
            llm_request.config.response_schema = sanitize_gemini_schema(resp_schema)
