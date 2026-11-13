"""Tests for Coddy agents and workflow execution.

Verifies:
- CodingOrchestratorWorkflow is a google-adk BaseAgent wrapping an ADK Workflow.
- CodingSanitizerAgent is a google-adk LlmAgent with SanitizedUserRequest schema.
- CodingResearchPlannerAgent is a google-adk LlmAgent with ResearchPlan schema.
- Workflow callbacks correctly populate context state.
"""

from unittest.mock import MagicMock

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from app.coddy.agentic.agents.coding_ambiguity_clarifier.agent import CodingAmbiguityClarifierAgent
from app.coddy.agentic.agents.coding_research_planner.agent import CodingResearchPlannerAgent
from app.coddy.agentic.agents.coding_sanitizer.agent import CodingSanitizerAgent
from app.coddy.agentic.schemas.enhanced_user_request import EnhancedUserRequest
from app.coddy.agentic.schemas.research_plan import ResearchPlan
from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest
from app.coddy.agentic.workflows.coding_orchestrate.workflow import CodingOrchestratorWorkflow


def test_coding_orchestrator_workflow_inheritance():
    """Verify coding orchestrator is an ADK BaseAgent wrapping a Workflow."""
    workflow_agent = CodingOrchestratorWorkflow()
    assert isinstance(workflow_agent, BaseAgent)
    assert workflow_agent.name == "coding_orchestrator_workflow"
    assert workflow_agent.description == "Coding Orchestrator Workflow"


def test_coding_sanitizer_agent_configuration():
    """Verify CodingSanitizerAgent is an ADK LlmAgent configured with schema and tools."""

    def dummy_cb(ctx):
        return None

    agent = CodingSanitizerAgent(
        before_agent_callback=dummy_cb,
        after_agent_callback=dummy_cb,
    )
    assert isinstance(agent, LlmAgent)
    assert agent.name == "coding_sanitizer"
    assert agent.model == "gemini-3.5-flash-lite"
    assert agent.output_schema == SanitizedUserRequest
    assert agent.output_key == "sanitized_user_request"
    assert len(agent.tools) == 0


def test_coding_research_planner_agent_configuration():
    """Verify CodingResearchPlannerAgent is an ADK LlmAgent configured with schema."""

    def dummy_cb(ctx):
        return None

    agent = CodingResearchPlannerAgent(
        before_agent_callback=dummy_cb,
        after_agent_callback=dummy_cb,
    )
    assert isinstance(agent, LlmAgent)
    assert agent.name == "coding_research_planner"
    assert agent.model == "gemini-3.8-flash"
    assert agent.output_schema == ResearchPlan
    assert agent.output_key == "research_plan"


def test_callback_after_coding_sanitize_agent():
    """Verify on_after_coding_sanitize_agent extracts structured output and updates state."""
    mock_ctx = MagicMock(spec=CallbackContext)
    mock_ctx.agent_name = "coding_sanitizer"
    mock_ctx.state = {}

    payload = '{"user_request": "Cleaned request", "ambiguous_terms": [{"term": "foo", "meanings": ["bar"]}]}'
    mock_event = MagicMock()
    mock_event.author = "coding_sanitizer"
    mock_event.content = types.Content(parts=[types.Part(text=payload)])
    mock_event.usage_metadata = None

    mock_session = MagicMock()
    mock_session.events = [mock_event]
    mock_ctx.session = mock_session

    CodingOrchestratorWorkflow.on_after_coding_sanitize_agent(mock_ctx)
    assert "sanitized_user_request" in mock_ctx.state
    assert mock_ctx.state["sanitized_user_request"]["user_request"] == "Cleaned request"
    assert mock_ctx.state["sanitized_user_request"]["ambiguous_terms"] == [
        {"term": "foo", "meanings": ["bar"], "source": None}
    ]


def test_callback_after_coding_research_plan_agent():
    """Verify on_after_coding_research_plan_agent extracts structured output and updates state."""
    mock_ctx = MagicMock(spec=CallbackContext)
    mock_ctx.agent_name = "coding_research_planner"
    mock_ctx.state = {}

    payload = '{"rationale": "Research rationale", "topics": []}'
    mock_event = MagicMock()
    mock_event.author = "coding_research_planner"
    mock_event.content = types.Content(parts=[types.Part(text=payload)])
    mock_event.usage_metadata = None

    mock_session = MagicMock()
    mock_session.events = [mock_event]
    mock_ctx.session = mock_session

    CodingOrchestratorWorkflow.on_after_coding_research_plan_agent(mock_ctx)
    assert "research_plan" in mock_ctx.state
    assert mock_ctx.state["research_plan"]["rationale"] == "Research rationale"
    assert mock_ctx.state["research_plan"]["topics"] == []


def test_coding_ambiguity_clarifier_agent_configuration():
    """Verify CodingAmbiguityClarifierAgent is an ADK LlmAgent configured with schema and tool."""

    def dummy_cb(ctx):
        return None

    agent = CodingAmbiguityClarifierAgent(
        before_agent_callback=dummy_cb,
        after_agent_callback=dummy_cb,
    )
    assert isinstance(agent, LlmAgent)
    assert agent.name == "coding_ambiguity_clarifier"
    assert agent.model == "gemini-3.5-flash-lite"
    assert agent.output_schema == EnhancedUserRequest
    assert agent.output_key == "enhanced_user_request"
    assert len(agent.tools) == 1
    assert agent.tools[0].__name__ == "ask_question"


def test_callback_after_coding_ambiguity_clarifier_agent():
    """Verify on_after_coding_ambiguity_clarifier_agent extracts structured output and updates state."""
    mock_ctx = MagicMock(spec=CallbackContext)
    mock_ctx.agent_name = "coding_ambiguity_clarifier"
    mock_ctx.state = {}

    payload = (
        '{"user_request": "Fully clarified request", "clarifications": '
        '[{"ambiguity_term": "store", "question": "What store?", "answer": "SQLite", "rationale": "Chosen SQLite"}], '
        '"local_project_instructions": null, "local_project_description": null}'
    )
    mock_event = MagicMock()
    mock_event.author = "coding_ambiguity_clarifier"
    mock_event.content = types.Content(parts=[types.Part(text=payload)])
    mock_event.usage_metadata = None

    mock_session = MagicMock()
    mock_session.events = [mock_event]
    mock_ctx.session = mock_session

    CodingOrchestratorWorkflow.on_after_coding_ambiguity_clarifier_agent(mock_ctx)
    assert "enhanced_user_request" in mock_ctx.state
    assert mock_ctx.state["enhanced_user_request"]["user_request"] == "Fully clarified request"
    assert len(mock_ctx.state["enhanced_user_request"]["clarifications"]) == 1
    assert mock_ctx.state["enhanced_user_request"]["clarifications"][0]["ambiguity_term"] == "store"
    assert mock_ctx.state["enhanced_user_request"]["clarifications"][0]["answer"] == "SQLite"


def test_coding_researcher_agent_configuration():
    """Verify CodingResearcherAgent is an ADK LlmAgent configured with schema and tools."""
    from app.coddy.agentic.agents.coding_researcher.agent import CodingResearcherAgent
    from app.coddy.agentic.schemas.research import EpisodeResearchResult

    def dummy_cb(ctx):
        return None

    agent = CodingResearcherAgent(
        before_agent_callback=dummy_cb,
        after_agent_callback=dummy_cb,
    )
    assert isinstance(agent, LlmAgent)
    assert agent.name == "coding_researcher"
    assert agent.model == "gemini-3.8-flash"
    assert agent.output_schema == EpisodeResearchResult
    assert agent.output_key == "episode_research_result"
    tool_names = [t.__name__ for t in agent.tools]
    assert "web_search" in tool_names
    assert "search_facts" in tool_names
    assert "search_documents" in tool_names
    assert "execute_cypher" in tool_names
    assert "get_code_entity" in tool_names
    assert "get_call_hierarchy" in tool_names
    assert "read_file_snippet" not in tool_names
    assert "read_file" not in tool_names
    assert "list_files" not in tool_names


def test_coding_research_clarifier_agent_configuration():
    """Verify CodingResearchClarifierAgent is an ADK LlmAgent configured with schema and tools."""
    from app.coddy.agentic.agents.coding_research_clarifier.agent import CodingResearchClarifierAgent
    from app.coddy.agentic.schemas.research import ResearchClarificationResult

    def dummy_cb(ctx):
        return None

    agent = CodingResearchClarifierAgent(
        before_agent_callback=dummy_cb,
        after_agent_callback=dummy_cb,
    )
    assert isinstance(agent, LlmAgent)
    assert agent.name == "coding_research_clarifier"
    assert agent.model == "gemini-3.5-flash-lite"
    assert agent.output_schema == ResearchClarificationResult
    assert agent.output_key == "research_clarification_result"
    assert len(agent.tools) == 1
    assert agent.tools[0].__name__ == "ask_question"


def test_coding_research_reporter_agent_configuration():
    """Verify CodingResearchReporterAgent is an ADK LlmAgent configured with schema."""
    from app.coddy.agentic.agents.coding_research_reporter.agent import CodingResearchReporterAgent
    from app.coddy.agentic.schemas.research import ResearchReport

    def dummy_cb(ctx):
        return None

    agent = CodingResearchReporterAgent(
        before_agent_callback=dummy_cb,
        after_agent_callback=dummy_cb,
    )
    assert isinstance(agent, LlmAgent)
    assert agent.name == "coding_research_reporter"
    assert agent.model == "gemini-3.8-flash"
    assert agent.output_schema == ResearchReport
    assert agent.output_key == "research_report"
    assert len(agent.tools) == 0
