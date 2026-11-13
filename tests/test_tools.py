"""Hermetic unit tests for agent tools in app/coddy/agentic/tools/."""

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.coddy.agentic.schemas.read_file import ReadFileToolResult
from app.coddy.agentic.tools.fs_tools import read_file


def test_read_file_tool_result_schema_valid():
    """Verify ReadFileToolResult accepts valid success and error payloads."""
    success_model = ReadFileToolResult(
        result="SUCCESS",
        content="file contents",
        mime_type="text/plain",
    )
    dumped = success_model.model_dump(exclude_none=True)
    assert dumped == {
        "result": "SUCCESS",
        "content": "file contents",
        "mime_type": "text/plain",
    }

    error_model = ReadFileToolResult(
        result="ERROR",
        message="Something went wrong",
    )
    dumped_err = error_model.model_dump(exclude_none=True)
    assert dumped_err == {
        "result": "ERROR",
        "message": "Something went wrong",
    }


def test_read_file_tool_result_schema_extra_forbidden():
    """Verify ReadFileToolResult forbids extra fields."""
    with pytest.raises(ValidationError):
        ReadFileToolResult(result="SUCCESS", extra_field="bad")  # type: ignore[call-arg]


def test_read_file_success_text(tmp_path: Path):
    """Verify read_file successfully reads UTF-8 text file."""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello Coddy!", encoding="utf-8")

    res = read_file(str(test_file))
    assert res["result"] == "SUCCESS"
    assert res["content"] == "Hello Coddy!"
    assert "text" in res["mime_type"]


def test_read_file_success_binary(tmp_path: Path):
    """Verify read_file reads non-UTF-8 binary files and base64 encodes them."""
    test_file = tmp_path / "image.png"
    binary_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe"
    test_file.write_bytes(binary_data)

    res = read_file(str(test_file))
    assert res["result"] == "SUCCESS"
    expected_b64 = base64.b64encode(binary_data).decode("ascii")
    assert res["content"] == expected_b64
    assert res["mime_type"] == "image/png"


def test_read_file_not_found(tmp_path: Path):
    """Verify read_file returns ERROR result for nonexistent files."""
    missing = tmp_path / "does_not_exist.md"
    res = read_file(str(missing))
    assert res["result"] == "ERROR"
    assert "File not found" in res["message"]


def test_read_file_is_directory(tmp_path: Path):
    """Verify read_file returns ERROR result when target is a directory."""
    res = read_file(str(tmp_path))
    assert res["result"] == "ERROR"
    assert "directory" in res["message"].lower()


def test_ask_question_tool():
    """Verify ask_question tool prompts UIService or auto-approves."""
    from unittest.mock import patch

    from app.coddy.agentic.tools.clarification_tools import ask_question
    from app.coddy.utils.services import get_ui_service

    ui = get_ui_service()

    # Case 1: auto_approve is True
    ui.auto_approve = True
    try:
        res = ask_question("Which option?", options=["Option A", "Option B"])
        assert res["result"] == "SUCCESS"
        assert res["answer"] == "Option A"
    finally:
        ui.auto_approve = False

    # Case 2: Interactive mock
    with patch.object(ui, "ask_user", return_value="Option B") as mock_ask:
        res = ask_question("Which option?", options=["Option A", "Option B"])
        assert res["result"] == "SUCCESS"
        assert res["answer"] == "Option B"
        mock_ask.assert_called_once_with(question="Which option?", options=["Option A", "Option B"])
