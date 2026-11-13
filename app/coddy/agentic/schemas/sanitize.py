"""Strict Pydantic v2 schemas for coding-sanitize structured output and input."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AmbiguousTerm(BaseModel):
    """An ambiguous or polysemic term identified in the user request or scoped project documentation."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(description="The ambiguous or polysemic term identified in the request or documentation.")
    meanings: list[str] = Field(description="Possible interpretations or meanings of the term in this context.")
    source: str | None = Field(
        default=None,
        description="Optional origin of the ambiguity ('user_request', 'README.md', or 'AGENTS.md').",
    )


class SanitizedUserRequest(BaseModel):
    """Sanitized user request, identified ambiguous terms, optional local project instructions, and optional local project description."""

    model_config = ConfigDict(extra="forbid")

    user_request: str = Field(
        description="Sanitized user request with adjusted markdown title level, stripped of conversational pleasantries."
    )
    ambiguous_terms: list[AmbiguousTerm] = Field(
        default_factory=list,
        description="List of ambiguous terms identified in the request and their possible meanings.",
    )
    local_project_instructions: str | None = Field(
        default=None,
        description="Sanitized local project instructions from AGENTS.md, stripped strictly of persona instructions and preserving technical architecture in full detail without summarization.",
    )
    local_project_description: str | None = Field(
        default=None,
        description="Sanitized local project description from README.md, stripped strictly of persona instructions and preserving technical and project documentation in full detail without summarization.",
    )


class SanitizeInput(BaseModel):
    """Input payload for coding-sanitize agent containing raw user request, optional local project instructions, and optional local project description."""

    model_config = ConfigDict(extra="forbid")

    raw_user_request: str = Field(
        default="",
        description="Raw user requirements or input text to sanitize.",
    )
    local_project_instructions: str | None = Field(
        default=None,
        description="Optional content of the local project instructions (AGENTS.md).",
    )
    local_project_description: str | None = Field(
        default=None,
        description="Optional content of the local project description (README.md).",
    )


def normalize_sanitized_user_request_data(data: Any) -> dict[str, Any]:
    """Normalizes raw dictionary from LLM into a structure conforming to SanitizedUserRequest.

    Gracefully handles string lists, alternative key names ('name', 'word'), single-key maps,
    and optional local_project_instructions / local_project_description field mapping.
    """
    if not isinstance(data, dict):
        return {
            "user_request": str(data) if data is not None else "",
            "ambiguous_terms": [],
            "local_project_instructions": None,
            "local_project_description": None,
        }

    user_request = (
        data.get("user_request")
        or data.get("sanitized_user_request")
        or data.get("sanitized_brief")
        or data.get("sanitized_text")
        or data.get("raw_user_request")
        or data.get("request")
        or ""
    )

    local_project_instructions = (
        data.get("local_project_instructions")
        or data.get("sanitized_local_project_instructions")
    )
    if local_project_instructions is not None:
        local_project_instructions = str(local_project_instructions).strip()
        if not local_project_instructions:
            local_project_instructions = None

    local_project_description = (
        data.get("local_project_description")
        or data.get("sanitized_local_project_description")
    )
    if local_project_description is not None:
        local_project_description = str(local_project_description).strip()
        if not local_project_description:
            local_project_description = None

    raw_terms = data.get("ambiguous_terms") or data.get("terms") or []
    normalized_terms: list[dict[str, Any]] = []

    if isinstance(raw_terms, list):
        for item in raw_terms:
            if isinstance(item, str):
                item_str = item.strip()
                if item_str:
                    normalized_terms.append(
                        {
                            "term": item_str,
                            "meanings": [f"Interpretation of {item_str}"],
                        }
                    )
            elif isinstance(item, dict):
                term_val = (
                    item.get("term") or item.get("name") or item.get("word") or item.get("key") or item.get("phrase")
                )
                meanings_val = (
                    item.get("meanings")
                    or item.get("definitions")
                    or item.get("interpretations")
                    or item.get("options")
                )
                if not term_val and len(item) == 1:
                    first_key = list(item.keys())[0]
                    term_val = first_key
                    if meanings_val is None:
                        meanings_val = item[first_key]

                if not term_val:
                    continue

                if isinstance(meanings_val, list):
                    meanings_list = [str(m).strip() for m in meanings_val if str(m).strip()]
                elif isinstance(meanings_val, str):
                    meanings_list = [meanings_val.strip()] if meanings_val.strip() else []
                else:
                    meanings_list = []

                if not meanings_list:
                    meanings_list = [f"Interpretation of {term_val}"]

                normalized_terms.append(
                    {
                        "term": str(term_val).strip(),
                        "meanings": meanings_list,
                    }
                )

    return {
        "user_request": str(user_request).strip(),
        "ambiguous_terms": normalized_terms,
        "local_project_instructions": local_project_instructions,
        "local_project_description": local_project_description,
    }


__all__ = [
    "AmbiguousTerm",
    "SanitizeInput",
    "SanitizedUserRequest",
    "normalize_sanitized_user_request_data",
]
