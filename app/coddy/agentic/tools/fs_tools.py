"""Runtime tools for Coddy worker agents."""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from app.coddy.agentic.schemas.read_file import ReadFileToolResult


def read_file(file_path: str) -> dict[str, Any]:
    """Reads the content of a local file.

    Args:
        file_path: Path to the file to read (relative to current working directory or absolute).

    Returns:
        A dictionary containing the read result adhering to ReadFileToolResult:
        - Successful: {"result": "SUCCESS", "content": <content_or_base64>, "mime_type": <mime_type>}
        - Failure: {"result": "ERROR", "message": <error_message>}
    """
    try:
        path = Path(file_path).resolve()
        if not path.exists():
            model = ReadFileToolResult(result="ERROR", message=f"File not found: '{file_path}'")
            return model.model_dump(exclude_none=True)
        if path.is_dir():
            model = ReadFileToolResult(result="ERROR", message=f"Path is a directory, not a file: '{file_path}'")
            return model.model_dump(exclude_none=True)

        guessed_mime, _ = mimetypes.guess_type(path)
        raw_bytes = path.read_bytes()

        try:
            content = raw_bytes.decode("utf-8")
            mime_type = guessed_mime or "text/plain"
        except UnicodeDecodeError:
            content = base64.b64encode(raw_bytes).decode("ascii")
            mime_type = guessed_mime or "application/octet-stream"

        model = ReadFileToolResult(
            result="SUCCESS",
            content=content,
            mime_type=mime_type,
        )
        return model.model_dump(exclude_none=True)
    except Exception as exc:
        model = ReadFileToolResult(result="ERROR", message=f"Failed to read file '{file_path}': {exc}")
        return model.model_dump(exclude_none=True)
