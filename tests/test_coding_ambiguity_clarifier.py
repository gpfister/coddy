"""Hermetic unit tests for coding-ambiguity-clarifier agent and workflow integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context import Context
from google.genai import types

from app.coddy.agentic.agents.coding_ambiguity_clarifier.agent import CodingAmbiguityClarifierAgent
from app.coddy.agentic.mappers.enhanced_user_request_mapper import EnhancedUserRequestMapper
from app.coddy.agentic.schemas.enhanced_user_request import (
    ClarificationRecord,
    EnhancedUserRequest,
    normalize_enhanced_user_request_data,
)
from app.coddy.agentic.services.artifact_service import ArtifactService
from app.coddy.agentic.tools.clarification_tools import ask_question
from app.coddy.agentic.workflows.coding_orchestrate.step_2_nodes import step_2_node
from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import step_3_node
from app.coddy.agentic.workflows.coding_orchestrate.workflow import CodingOrchestratorWorkflow
from app.coddy.utils.services import get_ui_service


def test_coding_ambiguity_clarifier_agent_initialization():
    """Verify CodingAmbiguityClarifierAgent attributes and configuration."""
    agent = CodingAmbiguityClarifierAgent()
    assert agent.name == "coding_ambiguity_clarifier"
    assert agent.model == "gemini-3.5-flash-lite"
    assert agent.output_schema == EnhancedUserRequest
    assert ask_question in agent.tools


def test_clarifier_schema_validation():
    """Verify ClarificationRecord and EnhancedUserRequest strict validation."""
    record = ClarificationRecord(
        ambiguity_term="auth",
        question="Which auth scheme?",
        answer="JWT Bearer",
        rationale="Standard stateless token",
    )
    req = EnhancedUserRequest(
        user_request="Build an API with JWT Bearer authentication.",
        clarifications=[record],
        local_project_instructions="Strict typing",
        local_project_description="# Project",
    )
    assert req.user_request == "Build an API with JWT Bearer authentication."
    assert len(req.clarifications) == 1
    assert req.clarifications[0].answer == "JWT Bearer"

    norm = normalize_enhanced_user_request_data(
        {
            "enhanced_user_request": "Normalized text",
            "clarifications": [{"question": "Q?", "answer": "A"}],
        }
    )
    req2 = EnhancedUserRequest.model_validate(norm)
    assert req2.user_request == "Normalized text"
    assert len(req2.clarifications) == 1


def test_enhanced_user_request_mapper():
    """Verify EnhancedUserRequestMapper produces structured Markdown."""
    req = EnhancedUserRequest(
        user_request="Clean request text",
        clarifications=[
            ClarificationRecord(
                ambiguity_term="queue",
                question="Which queue engine?",
                answer="RabbitMQ",
                rationale="Enterprise message broker",
            )
        ],
        local_project_instructions="No persona",
        local_project_description="# Readme",
    )
    md = EnhancedUserRequestMapper.to_markdown(req)
    assert "## Enhanced User Request" in md
    assert "Clean request text" in md
    assert "## Clarifications & Resolved Ambiguities" in md
    assert "`queue`" in md
    assert "RabbitMQ" in md

    inst_md = EnhancedUserRequestMapper.format_local_project_instructions(req)
    assert "No persona" in inst_md

    readme_md = EnhancedUserRequestMapper.format_local_project_description(req)
    assert "# Readme" in readme_md


def test_artifact_service_enhanced_artifacts(tmp_path: Path):
    """Verify ArtifactService correctly saves enhanced_user_request.json and ENHANCED_USER_REQUEST.md."""
    artifacts_dir = tmp_path / "artifacts"
    artifact_service = ArtifactService(artifacts_dir=artifacts_dir)

    req = EnhancedUserRequest(
        user_request="Enhanced prompt",
        clarifications=[],
    )
    paths = artifact_service.save_enhanced_user_request_artifacts(
        enhanced_request=req,
        user_request_md="## Enhanced User Request\n\nEnhanced prompt",
    )
    assert paths["json"] == artifacts_dir / "enhanced_user_request.json"
    assert paths["user_request_md"] == artifacts_dir / "ENHANCED_USER_REQUEST.md"
    assert paths["json"].exists()
    assert paths["user_request_md"].exists()
    assert "Enhanced prompt" in paths["user_request_md"].read_text(encoding="utf-8")


def test_ask_question_tool_interactive():
    """Verify ask_question prompts the user when auto_approve is false."""
    ui = get_ui_service()
    ui.auto_approve = False

    with patch.object(ui, "ask_user", return_value="Selected Choice") as mock_ask:
        result = ask_question("Select one", ["Choice A", "Choice B"])
        assert result["result"] == "SUCCESS"
        assert result["answer"] == "Selected Choice"
        mock_ask.assert_called_once_with(question="Select one", options=["Choice A", "Choice B"])


def test_ask_question_tool_auto_approve():
    """Verify ask_question automatically chooses option 1 when auto_approve is true."""
    ui = get_ui_service()
    ui.auto_approve = True
    try:
        result = ask_question("Select one", ["Choice A", "Choice B"])
        assert result["result"] == "SUCCESS"
        assert result["answer"] == "Choice A"
    finally:
        ui.auto_approve = False


@pytest.mark.anyio
async def test_step_2_node_assembly():
    """Verify step_2_node formats input content using state from step 1."""
    mock_ctx = MagicMock(spec=Context)
    mock_ctx.state = {
        "sanitized_user_request": {
            "user_request": "Build messaging system",
            "ambiguous_terms": [{"term": "messaging", "meanings": ["SMS", "WebSockets"], "source": "user_request"}],
            "local_project_instructions": "Follow Rule R1",
            "local_project_description": "# Coddy",
        }
    }

    content = await step_2_node._func(mock_ctx)
    assert isinstance(content, types.Content)
    text = content.parts[0].text
    assert "## Sanitized User Request" in text
    assert "Build messaging system" in text
    assert "Term: 'messaging' (Source: user_request)" in text
    assert "SMS" in text
    assert "WebSockets" in text
    assert "Follow Rule R1" in text
    assert "# Coddy" in text


@pytest.mark.anyio
async def test_step_3_node_forwarding():
    """Verify step_3_node forwards enhanced user request text to step 3 planner."""
    mock_ctx = MagicMock(spec=Context)
    mock_ctx.state = {
        "enhanced_user_request": {
            "user_request": "Build messaging system using WebSockets",
            "clarifications": [],
        }
    }

    content = await step_3_node._func(mock_ctx)
    assert isinstance(content, types.Content)
    assert content.parts[0].text == "Build messaging system using WebSockets"


def test_workflow_callbacks_clarifier():
    """Verify CodingOrchestratorWorkflow callbacks extract and persist EnhancedUserRequest."""
    mock_ctx = MagicMock(spec=CallbackContext)
    mock_ctx.agent_name = "coding_ambiguity_clarifier"
    mock_ctx.state = {}

    payload = (
        '{"user_request": "Clarified request", "clarifications": [], '
        '"local_project_instructions": null, "local_project_description": null}'
    )
    mock_event = MagicMock()
    mock_event.author = "coding_ambiguity_clarifier"
    mock_event.content = types.Content(parts=[types.Part(text=payload)])
    mock_event.usage_metadata = None

    mock_session = MagicMock()
    mock_session.events = [mock_event]
    mock_session.id = "session_test_abc"
    mock_ctx.session = mock_session

    CodingOrchestratorWorkflow.on_after_coding_ambiguity_clarifier_agent(mock_ctx)
    assert "enhanced_user_request" in mock_ctx.state
    assert mock_ctx.state["enhanced_user_request"]["user_request"] == "Clarified request"
