"""Tests for workflows and modular services in app/coddy/agentic/workflows/coding_orchestrate/."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest
from app.coddy.agentic.services.artifact_service import ArtifactService
from app.coddy.agentic.services.paths import (
    get_artifacts_dir,
    get_coddy_home_dir,
    get_data_db_path,
    get_memory_db_path,
    get_metrics_db_path,
)
from app.coddy.agentic.workflows.coding_orchestrate.workflow import (
    CodingOrchestratorWorkflow,
    extract_structured_output,
    step_1_node,
    step_2_node,
    step_3_node,
    step_4_node,
    step_5_node,
    step_6_node,
)


def test_paths_helpers(monkeypatch, tmp_path: Path):
    """Verify paths resolution for ~/.coddy directory structure."""
    monkeypatch.setenv("CODDY_HOME", str(tmp_path / ".coddy"))
    home = get_coddy_home_dir()
    assert home == tmp_path / ".coddy"
    assert home.exists()

    data_db = get_data_db_path()
    assert data_db == home / "data.db"

    memory_db = get_memory_db_path()
    assert memory_db == home / "memory.db"

    metrics_db = get_metrics_db_path()
    assert metrics_db == home / "metrics.db"

    artifacts_dir = get_artifacts_dir("test_session_123")
    assert artifacts_dir == home / "test_session_123" / "artifacts"
    assert artifacts_dir.exists()


def test_artifact_service_storage(tmp_path: Path):
    """Verify ArtifactService stores all artifacts inside the artifacts directory."""
    artifacts_dir = tmp_path / "artifacts"
    artifact_service = ArtifactService(artifacts_dir=artifacts_dir)

    # 1. Sanitizer artifacts
    paths = artifact_service.save_sanitizer_artifacts(
        sanitized_request={"user_request": "auth requirements"},
        user_request_md="# User request\n\nauth requirements",
    )
    assert paths["json"] == artifacts_dir / "sanitized_user_request.json"
    assert paths["user_request_md"] == artifacts_dir / "SANITIZED_USER_REQUEST.md"
    assert paths["json"].exists()
    assert paths["user_request_md"].exists()

    # 2. Specification
    spec_json, spec_md = artifact_service.save_specification(
        project_name="auth",
        spec={"version": "1.0", "executive_brief": "Auth brief"},
        spec_md="# Specification\n\nAuth spec markdown",
    )
    assert spec_json == artifacts_dir / "specifications" / "auth_spec.json"
    assert spec_md == artifacts_dir / "specifications" / "auth_spec.md"
    assert spec_json.exists()
    assert spec_md.exists()

    # 3. Plan
    plan_json, plan_md = artifact_service.save_plan(
        project_name="auth",
        plan={"version": "1.0", "title": "Auth plan"},
        plan_md="# Execution Plan\n\nAuth plan markdown",
    )
    assert plan_json == artifacts_dir / "plans" / "auth_plan.json"
    assert plan_md == artifacts_dir / "plans" / "auth_plan.md"
    assert plan_json.exists()
    assert plan_md.exists()

    # 4. Research Plan
    res_json, res_md = artifact_service.save_research_plan(
        project_name="auth",
        plan={"rationale": "OAuth research plan"},
        plan_md="# Research Plan\n\nOAuth details",
    )
    assert res_json == artifacts_dir / "research_plans" / "auth_research_plan.json"
    assert res_md == artifacts_dir / "research_plans" / "auth_research_plan.md"
    assert res_json.exists()
    assert res_md.exists()

    # 5. List artifacts
    artifacts = artifact_service.list_artifacts()
    assert "Sanitized User Request (Markdown)" in artifacts
    assert len(artifacts) >= 4


def test_coding_orchestrator_workflow_structure():
    """Verify CodingOrchestratorWorkflow initializes native ADK nodes and workflow edges."""
    wf = CodingOrchestratorWorkflow(db_url="sqlite+aiosqlite:///:memory:")
    assert wf.name == "coding_orchestrator_workflow"
    assert wf._workflow is not None
    assert wf._workflow.name == "coding_orchestrate_workflow"
    assert len(wf._workflow.edges) >= 1

    # Check agents
    assert wf._coding_sanitize_agent is not None
    assert wf._coding_sanitize_agent.name == "coding_sanitizer"
    assert wf._coding_ambiguity_clarifier_agent is not None
    assert wf._coding_ambiguity_clarifier_agent.name == "coding_ambiguity_clarifier"
    assert wf._coding_research_plan_agent is not None
    assert wf._coding_research_plan_agent.name == "coding_research_planner"
    assert wf._coding_researcher_agent is not None
    assert wf._coding_researcher_agent.name == "coding_researcher"
    assert wf._coding_research_clarifier_agent is not None
    assert wf._coding_research_clarifier_agent.name == "coding_research_clarifier"
    assert wf._coding_research_reporter_agent is not None
    assert wf._coding_research_reporter_agent.name == "coding_research_reporter"
    assert wf.session_service is not None

    # Check step nodes and agents in workflow edges
    all_nodes: list[str] = []
    for edge in wf._workflow.edges:
        if isinstance(edge, tuple):
            for n in edge:
                if hasattr(n, "name"):
                    all_nodes.append(n.name)
        elif hasattr(edge, "from_node"):
            if hasattr(edge.from_node, "name"):
                all_nodes.append(edge.from_node.name)
            if hasattr(edge.to_node, "name"):
                all_nodes.append(edge.to_node.name)

    assert "step_1_node" in all_nodes
    assert "step_2_node" in all_nodes
    assert "step_3_node" in all_nodes
    assert "step_4_node" in all_nodes
    assert "step_5_node" in all_nodes
    assert "coding_researcher" in all_nodes
    assert "coding_research_clarifier" in all_nodes
    assert "coding_research_reporter" in all_nodes
    assert "verify_remaining_research" in all_nodes
    assert "check_clarifier_outcome" in all_nodes


def test_step_nodes_passthrough_and_metadata():
    """Verify all 6 step nodes have proper names and pass through node_input."""
    import asyncio

    step_nodes = [step_1_node, step_2_node, step_3_node, step_4_node, step_5_node, step_6_node]
    for idx, node_obj in enumerate(step_nodes, 1):
        assert node_obj.name == f"step_{idx}_node"
        # Test input passthrough
        test_payload = {"prompt": f"test_input_{idx}"}
        result = asyncio.run(node_obj._func(test_payload))
        assert result == test_payload


def test_coding_orchestrator_workflow_dependency_injection():
    """Verify CodingOrchestratorWorkflow accepts custom session_service."""
    from google.adk.sessions import InMemorySessionService

    in_memory_service = InMemorySessionService()
    wf = CodingOrchestratorWorkflow(session_service=in_memory_service)
    assert wf.session_service is in_memory_service


def test_workflow_callbacks_state_and_artifact_coordination(tmp_path: Path, monkeypatch):
    """Verify callbacks update context.state and save disk artifacts via ArtifactService."""
    monkeypatch.setenv("CODDY_HOME", str(tmp_path / ".coddy"))
    session_id = "test_coord_session"

    # 1. Test on_after_coding_sanitize_agent
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.agent_name = "coding_sanitizer"

    mock_session = MagicMock()
    mock_session.id = session_id
    mock_event = MagicMock()
    mock_event.author = "coding_sanitizer"
    mock_event.content = types.Content(
        parts=[types.Part(text='{"user_request": "# Sanitized Auth Request", "ambiguous_terms": []}')]
    )
    mock_session.events = [mock_event]
    mock_context.session = mock_session
    mock_context.state = {}

    CodingOrchestratorWorkflow.on_after_coding_sanitize_agent(mock_context)

    assert "sanitized_user_request" in mock_context.state
    assert mock_context.state["sanitized_user_request"]["user_request"] == "# Sanitized Auth Request"
    assert "sanitized_user_request_path" in mock_context.state
    assert Path(mock_context.state["sanitized_user_request_path"]).exists()
    assert "sanitized_user_request_md_path" in mock_context.state
    assert Path(mock_context.state["sanitized_user_request_md_path"]).exists()

    # 2. Test on_after_coding_research_plan_agent
    mock_context2 = MagicMock(spec=CallbackContext)
    mock_context2.agent_name = "coding_research_planner"
    mock_session2 = MagicMock()
    mock_session2.id = session_id
    mock_event2 = MagicMock()
    mock_event2.author = "coding_research_planner"
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        ResearchPlanSubject,
        ResearchPlanTopic,
    )

    valid_plan = ResearchPlan(
        rationale="Decompose into OAuth2 and tokens",
        topics=[
            ResearchPlanTopic(
                topic="OAuth2 Architecture",
                description="Core authentication protocol evaluation",
                subjects=[
                    ResearchPlanSubject(
                        title="PKCE Flow",
                        description="Investigate PKCE support for CLI clients",
                    )
                ],
            )
        ],
    )
    mock_event2.content = types.Content(parts=[types.Part(text=valid_plan.model_dump_json())])
    mock_session2.events = [mock_event2]
    mock_context2.session = mock_session2
    mock_context2.state = {}

    CodingOrchestratorWorkflow.on_after_coding_research_plan_agent(mock_context2)

    assert "research_plan" in mock_context2.state
    assert mock_context2.state["research_plan"]["rationale"] == "Decompose into OAuth2 and tokens"
    assert "research_plan_json_path" in mock_context2.state
    assert Path(mock_context2.state["research_plan_json_path"]).exists()
    assert "research_plan_md_path" in mock_context2.state
    assert Path(mock_context2.state["research_plan_md_path"]).exists()


def test_extract_structured_output():
    """Verify extraction of Pydantic models from session event log."""
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.agent_name = "coding_sanitizer"

    # Simulate an ADK event with structured output in part.text
    payload = '{"user_request": "Clean input", "ambiguous_terms": []}'
    mock_event = MagicMock()
    mock_event.author = "coding_sanitizer"
    mock_event.content = types.Content(parts=[types.Part(text=payload)])

    mock_session = MagicMock()
    mock_session.events = [mock_event]
    mock_context.session = mock_session

    extracted = extract_structured_output(mock_context, SanitizedUserRequest)
    assert extracted is not None
    assert extracted.user_request == "Clean input"
    assert extracted.ambiguous_terms == []


def test_artifact_service_direct_artifacts(tmp_path: Path):
    """Verify ArtifactService stores specific named artifacts for sanitizer and research planner."""
    artifacts_dir = tmp_path / "artifacts"
    artifact_service = ArtifactService(artifacts_dir=artifacts_dir)

    # Sanitizer artifacts
    model_data = SanitizedUserRequest(
        user_request="Refactored request",
        local_project_instructions="# Instructions\n\nPreserve architecture",
        local_project_description="# Readme\n\nCoddy tools",
    )
    paths = artifact_service.save_sanitizer_artifacts(
        sanitized_request=model_data,
        user_request_md="# User request\n\nRefactored request",
        local_instruction_md="# Sanitized instructions\n\nPreserve architecture",
        local_description_md="# Sanitized readme\n\nCoddy tools",
    )
    assert paths["json"] == artifacts_dir / "sanitized_user_request.json"
    assert paths["user_request_md"] == artifacts_dir / "SANITIZED_USER_REQUEST.md"
    assert paths["local_instruction_md"] == artifacts_dir / "SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md"
    assert paths["local_description_md"] == artifacts_dir / "SANITIZED_LOCAL_PROJECT_DESCRIPTION.md"
    assert paths["json"].exists()
    assert paths["user_request_md"].exists()
    assert paths["local_instruction_md"].exists()
    assert paths["local_description_md"].exists()

    # Research plan artifacts
    from app.coddy.agentic.schemas.research_plan import ResearchPlan, ResearchPlanTopic

    plan_model = ResearchPlan(
        rationale="Top level rationale",
        topics=[ResearchPlanTopic(topic="T1", description="D1", subjects=[])],
    )
    json_path, md_path = artifact_service.save_research_plan_artifacts(
        plan=plan_model,
        plan_md="# Research Plan\n\nRationale and topics",
    )
    assert json_path == artifacts_dir / "research_plan.json"
    assert md_path == artifacts_dir / "RESEARCH_PLAN.md"
    assert json_path.exists()
    assert md_path.exists()

    listed = artifact_service.list_artifacts()
    assert "Sanitized User Request (Markdown)" in listed
    assert "Research Plan (JSON)" in listed
    assert "Research Plan (Markdown)" in listed


def test_after_model_callbacks_and_ui_output(monkeypatch, tmp_path: Path):
    """Verify after_model_callback gathers artifacts and renders UI output for both agents."""
    monkeypatch.setenv("CODDY_HOME", str(tmp_path / ".coddy"))
    session_id = "test_after_model_session"
    artifacts_dir = get_artifacts_dir(session_id)

    from io import StringIO

    from rich.console import Console

    from app.coddy.utils.services import get_ui_service

    out = StringIO()
    ui = get_ui_service()
    ui._console = Console(file=out, force_terminal=False, width=80)
    ui.display_markdown = True

    # 1. coding_sanitizer after_model_callback
    mock_context_san = MagicMock(spec=CallbackContext)
    mock_context_san.agent_name = "coding_sanitizer"
    mock_session_san = MagicMock()
    mock_session_san.id = session_id
    mock_context_san.session = mock_session_san
    mock_context_san.state = {}

    san_model = SanitizedUserRequest(
        user_request="Build authentication service",
        ambiguous_terms=[],
        local_project_instructions="Agent guidelines",
        local_project_description="Project overview",
    )
    mock_llm_response_san = MagicMock()
    mock_llm_response_san.content = types.Content(parts=[types.Part(text=san_model.model_dump_json())])

    CodingOrchestratorWorkflow.on_after_model_coding_sanitize_agent(
        callback_context=mock_context_san,
        llm_response=mock_llm_response_san,
    )

    assert "sanitized_user_request" in mock_context_san.state
    assert (artifacts_dir / "sanitized_user_request.json").exists()
    assert (artifacts_dir / "SANITIZED_USER_REQUEST.md").exists()
    assert (artifacts_dir / "SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md").exists()
    assert (artifacts_dir / "SANITIZED_LOCAL_PROJECT_DESCRIPTION.md").exists()

    rendered = out.getvalue()
    assert "SANITIZED_USER_REQUEST.md" in rendered
    assert "SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md" in rendered
    assert "SANITIZED_LOCAL_PROJECT_DESCRIPTION.md" in rendered

    # 2. coding_research_planner after_model_callback
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        ResearchPlanSubject,
        ResearchPlanTopic,
    )

    plan_model = ResearchPlan(
        rationale="Decompose auth into OAuth2 and tokens",
        topics=[
            ResearchPlanTopic(
                topic="OAuth2 Flow",
                description="Token exchange architecture",
                subjects=[
                    ResearchPlanSubject(
                        title="PKCE Evaluation",
                        description="Evaluate PKCE for desktop and CLI",
                    )
                ],
            )
        ],
    )

    mock_context_plan = MagicMock(spec=CallbackContext)
    mock_context_plan.agent_name = "coding_research_planner"
    mock_session_plan = MagicMock()
    mock_session_plan.id = session_id
    mock_context_plan.session = mock_session_plan
    mock_context_plan.state = {}

    mock_llm_response_plan = MagicMock()
    mock_llm_response_plan.content = types.Content(parts=[types.Part(text=plan_model.model_dump_json())])

    CodingOrchestratorWorkflow.on_after_model_coding_research_plan_agent(
        callback_context=mock_context_plan,
        llm_response=mock_llm_response_plan,
    )

    assert "research_plan" in mock_context_plan.state
    assert (artifacts_dir / "research_plan.json").exists()
    assert (artifacts_dir / "RESEARCH_PLAN.md").exists()
    assert "Research Plan" in out.getvalue()


@pytest.mark.anyio
async def test_load_project_context_both_files_exist(tmp_path: Path, monkeypatch):
    """Verify load_project_context reads ./README.md and ./AGENTS.md and sets state."""
    from app.coddy.agentic.workflows.coding_orchestrate.workflow import load_project_context

    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# Test Readme\nProject docs", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Test Agents\nAgent docs", encoding="utf-8")

    mock_ctx = MagicMock()
    mock_ctx.state = {}

    res = await load_project_context._func(ctx=mock_ctx, node_input="initial_input")

    assert res == "initial_input"
    assert mock_ctx.state["local_project_description"] == "# Test Readme\nProject docs"
    assert mock_ctx.state["local_project_instructions"] == "# Test Agents\nAgent docs"


@pytest.mark.anyio
async def test_load_project_context_files_missing(tmp_path: Path, monkeypatch):
    """Verify load_project_context handles missing files gracefully with None in state."""
    from app.coddy.agentic.workflows.coding_orchestrate.workflow import load_project_context

    monkeypatch.chdir(tmp_path)

    mock_ctx = MagicMock()
    mock_ctx.state = {}

    res = await load_project_context._func(ctx=mock_ctx, node_input="test_input")

    assert res == "test_input"
    assert mock_ctx.state["local_project_description"] is None
    assert mock_ctx.state["local_project_instructions"] is None


@pytest.mark.anyio
async def test_step_nodes_direct_modules():
    """Verify nodes can be imported directly from their respective step_<n>_nodes modules."""
    from app.coddy.agentic.workflows.coding_orchestrate.step_1_nodes import (
        load_project_context as s1_load,
    )
    from app.coddy.agentic.workflows.coding_orchestrate.step_1_nodes import (
        step_1_node as s1,
    )
    from app.coddy.agentic.workflows.coding_orchestrate.step_2_nodes import step_2_node as s2
    from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
        load_research_material as s3_load,
    )
    from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
        step_3_node as s3,
    )
    from app.coddy.agentic.workflows.coding_orchestrate.step_4_nodes import step_4_node as s4
    from app.coddy.agentic.workflows.coding_orchestrate.step_5_nodes import step_5_node as s5
    from app.coddy.agentic.workflows.coding_orchestrate.step_6_nodes import (
        _finalize_output as s6_fin_alias,
    )
    from app.coddy.agentic.workflows.coding_orchestrate.step_6_nodes import (
        finalize_node as s6_fin,
    )
    from app.coddy.agentic.workflows.coding_orchestrate.step_6_nodes import (
        step_6_node as s6,
    )

    assert s1.name == "step_1_node"
    assert s1_load.name == "load_project_context"
    assert s2.name == "step_2_node"
    assert s3.name == "step_3_node"
    assert s3_load.name == "load_research_material"
    assert s4.name == "step_4_node"
    assert s5.name == "step_5_node"
    assert s6.name == "step_6_node"
    assert s6_fin.name == "finalize_node"
    assert s6_fin_alias is s6_fin

    fin_res = await s6_fin._func("payload")
    assert fin_res == {"final_result": "payload"}


@pytest.mark.anyio
async def test_step_3_research_loop_nodes_routing():
    """Verify research loop nodes: queue init, episodic prompt, verify routing, clarifier and reporter inputs."""
    from google.genai import types

    from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
        check_clarifier_outcome,
        init_research_queue,
        prepare_clarifier_input,
        prepare_reporter_input,
        setup_episodic_research_context,
        verify_remaining_research,
    )

    mock_ctx = MagicMock()
    mock_ctx.state = {
        "research_plan": {
            "rationale": "Test decomposition",
            "user_request_summary": "Build high performance queue",
            "user_request_bullets": ["Throughput > 10k", "Sub-millisecond latency"],
            "project_context_summary": "Coddy event system",
            "project_context_bullets": ["Strict Pydantic", "Async execution"],
            "topics": [
                {
                    "topic": "Queue Engines",
                    "description": "Evaluate Redis vs SQLite queue",
                    "subjects": [
                        {
                            "title": "Redis Streams",
                            "description": "Assess Redis Stream persistence",
                            "target_sources": ["code", "web"],
                            "directions": ["Diagram stream pub-sub flow", "Evaluate latency"],
                            "approaches": [{"name": "RedisStreams", "description": "XADD/XREAD"}],
                            "open_issues": ["Cluster failover behavior"],
                        },
                        {
                            "title": "SQLite WAL Queue",
                            "description": "Assess SQLite table as a queue",
                            "target_sources": ["code"],
                            "directions": ["Evaluate write lock contention"],
                            "approaches": [],
                            "open_issues": [],
                        },
                    ],
                }
            ],
        }
    }

    # 1. init_research_queue
    await init_research_queue._func(ctx=mock_ctx, node_input=None)
    assert len(mock_ctx.state["research_queue"]) == 2
    assert mock_ctx.state["current_episode_index"] == 0
    assert mock_ctx.state["completed_researches"] == []
    assert mock_ctx.state["open_issues_raised"] == []

    # 2. setup_episodic_research_context (First episode)
    first_prompt_content = await setup_episodic_research_context._func(ctx=mock_ctx, node_input=None)
    assert isinstance(first_prompt_content, types.Content)
    prompt_text = first_prompt_content.parts[0].text
    assert "## Context" in prompt_text
    assert "### User request" in prompt_text
    assert "Build high performance queue" in prompt_text
    assert "### Project context" in prompt_text
    assert "Coddy event system" in prompt_text
    assert "## Previous episode" in prompt_text
    assert "*(None - this is the initial research episode)*" in prompt_text
    assert "## Current episode" in prompt_text
    assert "### Topic: Queue Engines" in prompt_text
    assert "### Subject: Redis Streams" in prompt_text
    assert "**Directions & Expected Deliverables:**" in prompt_text
    assert "- Diagram stream pub-sub flow" in prompt_text
    assert "- Cluster failover behavior" in prompt_text

    # 3. verify_remaining_research when index < len(queue)
    ev_loop = await verify_remaining_research._func(ctx=mock_ctx, node_input=None)
    assert ev_loop.actions.route == "loop_research"

    # Advance index past queue with open issues
    mock_ctx.state["current_episode_index"] = 2
    mock_ctx.state["open_issues_raised"] = ["Cluster failover behavior"]
    mock_ctx.state["completed_researches"] = [
        {
            "subject_title": "Redis Streams",
            "summary_paragraph": "Redis Streams provide ultra-low latency.",
            "summary_bullets": ["Benchmark 1", "Benchmark 2"],
        }
    ]

    # verify_remaining_research with open issues -> clarify_issues
    ev_clarify = await verify_remaining_research._func(ctx=mock_ctx, node_input=None)
    assert ev_clarify.actions.route == "clarify_issues"

    # verify_remaining_research with NO open issues -> assemble_report
    mock_ctx.state["open_issues_raised"] = []
    ev_report = await verify_remaining_research._func(ctx=mock_ctx, node_input=None)
    assert ev_report.actions.route == "assemble_report"

    # 4. prepare_clarifier_input
    mock_ctx.state["open_issues_raised"] = ["Cluster failover behavior"]
    clar_input = await prepare_clarifier_input._func(ctx=mock_ctx, node_input=None)
    assert isinstance(clar_input, types.Content)
    assert "Cluster failover behavior" in clar_input.parts[0].text
    assert "Redis Streams provide ultra-low latency." in clar_input.parts[0].text

    # 5. check_clarifier_outcome with new research topics
    mock_ctx.state["clarification_result"] = {
        "resolved_issues": [{"issue": "Cluster failover behavior", "resolution": "Use Sentinel", "source": "user"}],
        "new_research_topics": [
            {
                "topic": "Redis Sentinel",
                "description": "High availability configuration",
                "subjects": [{"title": "Sentinel Quorum", "description": "Investigate quorum config"}],
            }
        ],
    }
    ev_new = await check_clarifier_outcome._func(ctx=mock_ctx, node_input=None)
    assert ev_new.actions.route == "new_research"
    assert len(mock_ctx.state["research_queue"]) == 3  # New subject added

    # check_clarifier_outcome without new research topics
    mock_ctx.state["clarification_result"] = {"resolved_issues": [], "new_research_topics": []}
    ev_no_new = await check_clarifier_outcome._func(ctx=mock_ctx, node_input=None)
    assert ev_no_new.actions.route == "assemble_report"

    # 6. prepare_reporter_input
    rep_input = await prepare_reporter_input._func(ctx=mock_ctx, node_input=None)
    assert isinstance(rep_input, types.Content)
    assert "# Research Report Synthesis Request" in rep_input.parts[0].text


def test_research_callbacks_and_artifacts_coordination(tmp_path: Path, monkeypatch):
    """Verify research agent callbacks persist artifacts to disk and update state."""
    from app.coddy.agentic.schemas.research import (
        EpisodeResearchResult,
        ResearchClarificationResult,
        ResearchReport,
        ResolvedIssue,
    )

    monkeypatch.setenv("CODDY_HOME", str(tmp_path / ".coddy"))
    session_id = "test_research_artifacts_session"

    # 1. coding_researcher callback
    mock_context_res = MagicMock(spec=CallbackContext)
    mock_context_res.agent_name = "coding_researcher"
    mock_session_res = MagicMock()
    mock_session_res.id = session_id
    mock_context_res.session = mock_session_res
    mock_context_res.state = {
        "current_episode_index": 0,
        "completed_researches": [],
        "open_issues_raised": [],
    }

    ep_result = EpisodeResearchResult(
        subject_title="Authentication Architecture",
        summary_paragraph="Investigation of current auth flow and OAuth2 token refresh.",
        summary_bullets=["Point 1", "Point 2", "Point 3", "Point 4", "Point 5"],
        open_issues=["Token revoke latency"],
    )
    mock_llm_res = MagicMock()
    mock_llm_res.content = types.Content(parts=[types.Part(text=ep_result.model_dump_json())])

    CodingOrchestratorWorkflow.on_after_model_coding_researcher_agent(
        callback_context=mock_context_res,
        llm_response=mock_llm_res,
    )

    assert mock_context_res.state["current_episode_index"] == 1
    assert len(mock_context_res.state["completed_researches"]) == 1
    assert "Token revoke latency" in mock_context_res.state["open_issues_raised"]

    artifacts_dir = tmp_path / ".coddy" / session_id / "artifacts"
    ep_dir = artifacts_dir / "research_episodes"
    assert (ep_dir / "episode_1_authentication_architecture.json").exists()
    assert (ep_dir / "episode_1_authentication_architecture.md").exists()

    # 2. coding_research_clarifier callback
    mock_context_clar = MagicMock(spec=CallbackContext)
    mock_context_clar.agent_name = "coding_research_clarifier"
    mock_session_clar = MagicMock()
    mock_session_clar.id = session_id
    mock_context_clar.session = mock_session_clar
    mock_context_clar.state = {}

    clar_result = ResearchClarificationResult(
        resolved_issues=[
            ResolvedIssue(issue="Token revoke latency", resolution="Use Redis blacklist", source="user_clarification")
        ],
        new_research_topics=[],
    )
    mock_llm_clar = MagicMock()
    mock_llm_clar.content = types.Content(parts=[types.Part(text=clar_result.model_dump_json())])

    CodingOrchestratorWorkflow.on_after_model_coding_research_clarifier_agent(
        callback_context=mock_context_clar,
        llm_response=mock_llm_clar,
    )

    assert "clarification_result" in mock_context_clar.state
    assert len(mock_context_clar.state["clarification_result"]["resolved_issues"]) == 1

    # 3. coding_research_reporter callback
    mock_context_rep = MagicMock(spec=CallbackContext)
    mock_context_rep.agent_name = "coding_research_reporter"
    mock_session_rep = MagicMock()
    mock_session_rep.id = session_id
    mock_context_rep.session = mock_session_rep
    mock_context_rep.state = {}

    rep_model = ResearchReport(
        executive_summary="Executive report on auth and persistence.",
    )
    mock_llm_rep = MagicMock()
    mock_llm_rep.content = types.Content(parts=[types.Part(text=rep_model.model_dump_json())])

    CodingOrchestratorWorkflow.on_after_model_coding_research_reporter_agent(
        callback_context=mock_context_rep,
        llm_response=mock_llm_rep,
    )

    assert "research_report" in mock_context_rep.state
    assert (artifacts_dir / "research_report.json").exists()
    assert (artifacts_dir / "RESEARCH_REPORT.md").exists()


@pytest.mark.anyio
async def test_step_3_nodes_ui_execution():
    """Verify Step 3 nodes execute cleanly with UI service logging."""
    from google.adk.agents.context import Context

    from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
        check_clarifier_outcome,
        finalize_research_step,
        init_research_queue,
        prepare_clarifier_input,
        prepare_reporter_input,
        setup_episodic_research_context,
        verify_remaining_research,
    )

    mock_session = MagicMock()
    mock_session.id = "test_ui_session"
    ctx = MagicMock(spec=Context)
    ctx.session = mock_session
    ctx.state = {
        "research_plan": {
            "topics": [
                {
                    "topic": "Architecture",
                    "subjects": [
                        {
                            "title": "Auth Subject",
                            "description": "Evaluate auth mechanism",
                            "directions": ["Flowchart"],
                        }
                    ],
                }
            ],
            "rationale": "High-level rationale",
        }
    }

    # 1. init_research_queue
    await init_research_queue._func(ctx)
    assert len(ctx.state["research_queue"]) == 1
    assert ctx.state["current_episode_index"] == 0

    # 2. setup_episodic_research_context
    content = await setup_episodic_research_context._func(ctx)
    assert isinstance(content, types.Content)
    assert "Auth Subject" in content.parts[0].text

    # 3. verify_remaining_research
    event = await verify_remaining_research._func(ctx)
    assert event.actions.route == "loop_research"

    # Advance index to end with open issues
    ctx.state["current_episode_index"] = 1
    ctx.state["open_issues_raised"] = ["Sample Issue 1"]
    ctx.state["completed_researches"] = [
        {"subject_title": "Auth Subject", "summary_paragraph": "Done", "summary_bullets": ["Point"]}
    ]

    event_clarify = await verify_remaining_research._func(ctx)
    assert event_clarify.actions.route == "clarify_issues"

    # 4. prepare_clarifier_input
    clar_content = await prepare_clarifier_input._func(ctx)
    assert "Sample Issue 1" in clar_content.parts[0].text

    # 5. check_clarifier_outcome without new research
    ctx.state["clarification_result"] = {
        "resolved_issues": [{"issue": "Sample Issue 1", "resolution": "Fixed", "source": "user_clarification"}],
        "new_research_topics": [],
    }
    event_report = await check_clarifier_outcome._func(ctx)
    assert event_report.actions.route == "assemble_report"

    # 6. prepare_reporter_input
    rep_content = await prepare_reporter_input._func(ctx)
    assert "Auth Subject" in rep_content.parts[0].text

    # 7. finalize_research_step
    final_res = await finalize_research_step._func(ctx)
    assert final_res is None


def test_extract_structured_output_tool_call_does_not_fall_back():
    """Verify extract_structured_output does NOT fall back to old session events when llm_response is a tool call."""
    from app.coddy.agentic.schemas.research import EpisodeResearchResult

    mock_context = MagicMock(spec=CallbackContext)
    mock_context.agent_name = "coding_researcher"
    mock_context.state = {}

    # Old event in session history from previous episode
    old_ep = EpisodeResearchResult(
        subject_title="Previous Subject",
        summary_paragraph="Previous summary paragraph.",
        summary_bullets=["P1", "P2", "P3", "P4", "P5"],
    )
    old_event = MagicMock()
    old_event.author = "coding_researcher"
    old_event.content = types.Content(parts=[types.Part(text=old_ep.model_dump_json())])

    mock_session = MagicMock()
    mock_session.events = [old_event]
    mock_context.session = mock_session

    # Intermediate tool call response from current episode
    mock_tool_llm_response = MagicMock()
    mock_tool_llm_response.content = types.Content(
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="search_documents",
                    args={"query": "app/main.py"},
                )
            )
        ]
    )

    # Calling with tool call response must return None, NOT the old episode from history!
    extracted = extract_structured_output(
        mock_context,
        EpisodeResearchResult,
        llm_response=mock_tool_llm_response,
    )
    assert extracted is None


def test_extract_structured_output_scoped_to_current_turn():
    """Verify session event search does not scan events prior to _event_idx_before_{agent_name}."""
    from app.coddy.agentic.schemas.research import EpisodeResearchResult

    mock_context = MagicMock(spec=CallbackContext)
    mock_context.agent_name = "coding_researcher"

    # Old event in session history from episode 1
    old_ep = EpisodeResearchResult(
        subject_title="Episode 1 Subject",
        summary_paragraph="Summary 1.",
        summary_bullets=["P1", "P2", "P3", "P4", "P5"],
    )
    old_event = MagicMock()
    old_event.author = "coding_researcher"
    old_event.content = types.Content(parts=[types.Part(text=old_ep.model_dump_json())])

    # Intermediate event in episode 2 (tool call)
    tool_event = MagicMock()
    tool_event.author = "coding_researcher"
    tool_event.content = types.Content(
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="search_documents",
                    args={"query": "app/main.py"},
                )
            )
        ]
    )

    mock_session = MagicMock()
    mock_session.events = [old_event, tool_event]
    mock_context.session = mock_session

    # Agent start offset was recorded AFTER old_event (at index 1)
    mock_context.state = {"_event_idx_before_coding_researcher": 1}

    # Since tool_event has no valid model response, and old_event is before index 1, result is None
    extracted = extract_structured_output(
        mock_context,
        EpisodeResearchResult,
        llm_response=None,
    )
    assert extracted is None


@pytest.mark.anyio
async def test_multi_episode_sequential_loop_coordination(tmp_path: Path, monkeypatch):
    """Verify multiple episodes are processed sequentially without duplicate increments or skipping."""
    from google.adk.agents.context import Context

    from app.coddy.agentic.schemas.research import EpisodeResearchResult
    from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
        init_research_queue,
        setup_episodic_research_context,
        verify_remaining_research,
    )

    monkeypatch.setenv("CODDY_HOME", str(tmp_path / ".coddy"))
    session_id = "test_multi_ep_session"

    mock_session = MagicMock()
    mock_session.id = session_id
    mock_session.events = []

    ctx = MagicMock(spec=Context)
    ctx.session = mock_session
    ctx.state = {
        "research_plan": {
            "topics": [
                {
                    "topic": "Core Architecture",
                    "subjects": [
                        {"title": "Subject 1: CLI Entry", "description": "CLI flow"},
                        {"title": "Subject 2: Workflow Engine", "description": "ADK Graph"},
                    ],
                }
            ]
        }
    }

    # 1. Initialize queue with 2 subjects
    await init_research_queue._func(ctx)
    assert len(ctx.state["research_queue"]) == 2
    assert ctx.state["current_episode_index"] == 0

    # 2. Episode 1: Setup context
    content_ep1 = await setup_episodic_research_context._func(ctx)
    assert "Subject 1: CLI Entry" in content_ep1.parts[0].text
    assert ctx.state["active_episode_index"] == 0

    # Simulate researcher agent run for Episode 1 (with intermediate tool calls)
    cb_ctx = MagicMock(spec=CallbackContext)
    cb_ctx.agent_name = "coding_researcher"
    cb_ctx.session = mock_session
    cb_ctx.state = ctx.state

    # Tool call turn: must not persist
    tool_resp = MagicMock()
    tool_resp.content = types.Content(
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="search_documents",
                    args={"query": "app/main.py"},
                )
            )
        ]
    )
    CodingOrchestratorWorkflow.on_after_model_coding_researcher_agent(cb_ctx, llm_response=tool_resp)
    assert len(ctx.state["completed_researches"]) == 0

    # Final turn for Episode 1: set_model_response
    ep1_result = EpisodeResearchResult(
        subject_title="Subject 1: CLI Entry",
        summary_paragraph="CLI entry point investigated.",
        summary_bullets=["CLI 1", "CLI 2", "CLI 3", "CLI 4", "CLI 5"],
    )
    ep1_resp = MagicMock()
    ep1_resp.content = types.Content(parts=[types.Part(text=ep1_result.model_dump_json())])
    CodingOrchestratorWorkflow.on_after_model_coding_researcher_agent(cb_ctx, llm_response=ep1_resp)

    # After-agent callback for Episode 1: must not double persist
    CodingOrchestratorWorkflow.on_after_coding_researcher_agent(cb_ctx)
    assert len(ctx.state["completed_researches"]) == 1
    assert ctx.state["current_episode_index"] == 1
    assert ctx.state["_last_persisted_episode_index"] == 0

    # Verify remaining research routes to loop_research
    route_ep1 = await verify_remaining_research._func(ctx)
    assert route_ep1.actions.route == "loop_research"

    # 3. Episode 2: Setup context
    content_ep2 = await setup_episodic_research_context._func(ctx)
    assert "Subject 2: Workflow Engine" in content_ep2.parts[0].text
    assert ctx.state["active_episode_index"] == 1

    # Simulate Episode 2 tool call turn: must not pick up Episode 1
    CodingOrchestratorWorkflow.on_after_model_coding_researcher_agent(cb_ctx, llm_response=tool_resp)
    assert len(ctx.state["completed_researches"]) == 1
    assert ctx.state["current_episode_index"] == 1

    # Final turn for Episode 2
    ep2_result = EpisodeResearchResult(
        subject_title="Subject 2: Workflow Engine",
        summary_paragraph="Workflow engine investigated.",
        summary_bullets=["WF 1", "WF 2", "WF 3", "WF 4", "WF 5"],
    )
    ep2_resp = MagicMock()
    ep2_resp.content = types.Content(parts=[types.Part(text=ep2_result.model_dump_json())])
    CodingOrchestratorWorkflow.on_after_model_coding_researcher_agent(cb_ctx, llm_response=ep2_resp)
    CodingOrchestratorWorkflow.on_after_coding_researcher_agent(cb_ctx)

    assert len(ctx.state["completed_researches"]) == 2
    assert ctx.state["current_episode_index"] == 2
    assert ctx.state["_last_persisted_episode_index"] == 1

    # Verify remaining research routes to assemble_report (since no open issues)
    route_ep2 = await verify_remaining_research._func(ctx)
    assert route_ep2.actions.route == "assemble_report"

    # Verify artifacts exist for both episodes
    ep_dir = tmp_path / ".coddy" / session_id / "artifacts" / "research_episodes"
    assert (ep_dir / "episode_1_subject_1_cli_entry.json").exists()
    assert (ep_dir / "episode_2_subject_2_workflow_engine.json").exists()


@pytest.mark.anyio
async def test_setup_episodic_research_context_injects_research_materials() -> None:
    """Verifies that research_materials in research_plan are injected into episodic prompt."""
    from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
        init_research_queue,
        setup_episodic_research_context,
    )

    mock_ctx = MagicMock()
    mock_ctx.state = {
        "research_plan": {
            "rationale": "Decomposition with material",
            "user_request_summary": "Implement feature X",
            "user_request_bullets": ["Requirement 1"],
            "project_context_summary": "Coddy architecture",
            "project_context_bullets": ["Invariant 1"],
            "research_materials": [
                {
                    "file_path": "docs/specs/feature_x.pdf",
                    "served_information": "Contains protocol buffer definitions and API schema.",
                    "investigation_targets": "Verify backward compatibility with v1 endpoints.",
                }
            ],
            "topics": [
                {
                    "topic": "API Specification",
                    "description": "Analyze protocol buffers",
                    "subjects": [
                        {
                            "title": "Protobuf Schema",
                            "description": "Examine v2 proto schemas",
                            "target_sources": ["code", "document"],
                            "directions": ["Review message field tags"],
                            "approaches": [],
                            "open_issues": [],
                        }
                    ],
                }
            ],
        }
    }

    await init_research_queue._func(mock_ctx)
    prompt_content = await setup_episodic_research_context._func(mock_ctx)

    assert isinstance(prompt_content, types.Content)
    prompt_text = prompt_content.parts[0].text
    assert "### Research materials" in prompt_text
    assert "docs/specs/feature_x.pdf" in prompt_text
    assert "*Served Information*: Contains protocol buffer definitions and API schema." in prompt_text
    assert "*Investigation Targets*: Verify backward compatibility with v1 endpoints." in prompt_text
