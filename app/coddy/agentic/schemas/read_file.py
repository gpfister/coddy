"""Strict Pydantic v2 schemas for read_file tool results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReadFileToolResult(BaseModel):
    """Result model for the read_file agent tool."""

    model_config = ConfigDict(extra="forbid")

    result: Literal["SUCCESS", "ERROR"] = Field(description="Execution status of the tool call ('SUCCESS' or 'ERROR').")
    content: str | None = Field(
        default=None,
        description="The content of the file. Text files are encoded as UTF-8 string; binary files are base64-encoded string.",
    )
    mime_type: str | None = Field(
        default=None,
        description="MIME type of the file (e.g., 'text/plain', 'text/markdown', 'application/octet-stream').",
    )
    message: str | None = Field(
        default=None,
        description="Error message if the file read operation failed.",
    )
