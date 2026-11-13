"""Strict Pydantic v2 schemas for coding-ambiguity-clarifier structured output and input."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClarificationRecord(BaseModel):
    """Record of an ambiguity question asked to the user and their clarifying response."""

    model_config = ConfigDict(extra="forbid")

    ambiguity_term: str | None = Field(
        default=None,
        description="The ambiguous term or concept being resolved.",
    )
    question: str = Field(description="The clarification question presented to the user.")
    answer: str = Field(description="The answer or selection provided by the user.")
    rationale: str = Field(
        default="",
        description="Brief explanation of how this answer resolves the ambiguity or introduces adjustments.",
    )


class EnhancedUserRequest(BaseModel):
    """Fully clarified and enhanced user request accompanied by clarification history and project context."""

    model_config = ConfigDict(extra="forbid")

    user_request: str = Field(
        description="Fully enhanced, unambiguous user request incorporating all clarification answers."
    )
    clarifications: list[ClarificationRecord] = Field(
        default_factory=list,
        description="Chronological log of clarification questions and user responses.",
    )
    local_project_instructions: str | None = Field(
        default=None,
        description="Sanitized technical instructions from local project instructions (AGENTS.md) carried forward from Step 1.",
    )
    local_project_description: str | None = Field(
        default=None,
        description="Sanitized project documentation from local project description (README.md) carried forward from Step 1.",
    )


def normalize_enhanced_user_request_data(data: Any) -> dict[str, Any]:
    """Normalizes raw dictionary from LLM into a structure conforming to EnhancedUserRequest."""
    if not isinstance(data, dict):
        return {
            "user_request": str(data) if data is not None else "",
            "clarifications": [],
            "local_project_instructions": None,
            "local_project_description": None,
        }

    user_request = (
        data.get("user_request")
        or data.get("enhanced_user_request")
        or data.get("enhanced_request")
        or data.get("sanitized_user_request")
        or data.get("request")
        or ""
    )

    clarifications_raw = data.get("clarifications") or []
    clarifications: list[dict[str, Any]] = []
    if isinstance(clarifications_raw, list):
        for item in clarifications_raw:
            if isinstance(item, dict):
                clarifications.append(
                    {
                        "ambiguity_term": item.get("ambiguity_term"),
                        "question": str(item.get("question") or ""),
                        "answer": str(item.get("answer") or ""),
                        "rationale": str(item.get("rationale") or ""),
                    }
                )

    local_project_instructions = (
        data.get("local_project_instructions")
        or data.get("sanitized_local_project_instructions")
    )
    if local_project_instructions is not None:
        local_project_instructions = str(local_project_instructions).strip() or None

    local_project_description = (
        data.get("local_project_description")
        or data.get("sanitized_local_project_description")
    )
    if local_project_description is not None:
        local_project_description = str(local_project_description).strip() or None

    return {
        "user_request": str(user_request).strip(),
        "clarifications": clarifications,
        "local_project_instructions": local_project_instructions,
        "local_project_description": local_project_description,
    }
