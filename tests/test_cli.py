"""Tests for Coddy CLI commands and inputs."""

from unittest.mock import AsyncMock

from typer.testing import CliRunner

from app.coddy.agentic.workflows.coding_orchestrate.workflow import CodingOrchestratorWorkflow
from app.coddy.app import app

runner = CliRunner()


def test_cli_version():
    """Verify --version option outputs Coddy version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Coddy version 0.1.0" in result.stdout


def test_cli_schemas():
    """Verify schemas command outputs JSON schemas."""
    result = runner.invoke(app, ["schemas"])
    assert result.exit_code == 0
    assert "SPECIFICATION SCHEMA" in result.stdout
    assert "PLAN SCHEMA" in result.stdout
    assert "SANITIZATION SCHEMA" in result.stdout
    assert "RESEARCH PLAN SCHEMA" in result.stdout


def test_cli_code_auto_approve(monkeypatch):
    """Verify code command runs workflow with auto-approve flag."""
    mock_start = AsyncMock()
    monkeypatch.setattr(CodingOrchestratorWorkflow, "start", mock_start)

    result = runner.invoke(app, ["code", "Build rate limiter", "--yes"])
    assert result.exit_code == 0
    assert "Auto-approve mode enabled" in result.stdout
    mock_start.assert_awaited_once_with("Build rate limiter")


def test_cli_code_display_markdown_flag(monkeypatch):
    """Verify code command sets display_markdown on UIService."""
    from app.coddy.utils.services import get_ui_service

    mock_start = AsyncMock()
    monkeypatch.setattr(CodingOrchestratorWorkflow, "start", mock_start)

    ui = get_ui_service()

    # Default is False
    result = runner.invoke(app, ["code", "Build rate limiter"])
    assert result.exit_code == 0
    assert ui.display_markdown is False

    # Explicit flag sets to True
    result = runner.invoke(app, ["code", "Build rate limiter", "--display-markdown"])
    assert result.exit_code == 0
    assert ui.display_markdown is True


def test_cli_code_stdin(monkeypatch):
    """Verify code command reads prompt from stdin."""
    mock_start = AsyncMock()
    monkeypatch.setattr(CodingOrchestratorWorkflow, "start", mock_start)

    result = runner.invoke(app, ["code", "-"], input="Build real-time notification engine\n")
    assert result.exit_code == 0
    mock_start.assert_awaited_once_with("Build real-time notification engine")


def test_cli_code_empty_prompt():
    """Verify code command rejects empty prompt with exit code 1."""
    result = runner.invoke(app, ["code", "   "])
    assert result.exit_code == 1
    assert "Error: No prompt provided." in (result.stderr + result.stdout)
