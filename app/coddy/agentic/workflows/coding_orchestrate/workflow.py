"""Workflow Engine: coding_orchestrate (coding-orchestrate).

Implemented as a google-adk Graph Workflow.
Handles user prompts and orchestrates worker agents.
All generated artifacts are strictly stored under ~/.coddy/<session_id>/artifacts/.
"""

import re
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from google.adk import Workflow
from google.adk.agents import BaseAgent, InvocationContext
from google.adk.agents._streaming_mode import StreamingMode
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context import Context
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.adk.workflow import START
from google.genai import types
from pydantic import BaseModel, PrivateAttr, ValidationError

from app.coddy.agentic.agents.coding_ambiguity_clarifier.agent import CodingAmbiguityClarifierAgent
from app.coddy.agentic.agents.coding_research_clarifier.agent import CodingResearchClarifierAgent
from app.coddy.agentic.agents.coding_research_planner.agent import CodingResearchPlannerAgent
from app.coddy.agentic.agents.coding_research_reporter.agent import CodingResearchReporterAgent
from app.coddy.agentic.agents.coding_researcher.agent import CodingResearcherAgent
from app.coddy.agentic.agents.coding_sanitizer.agent import CodingSanitizerAgent
from app.coddy.agentic.mappers.enhanced_user_request_mapper import EnhancedUserRequestMapper
from app.coddy.agentic.mappers.research_mapper import (
    EpisodeResearchMapper,
    ResearchReportMapper,
)
from app.coddy.agentic.mappers.research_plan_mapper import ResearchPlanMapper
from app.coddy.agentic.mappers.sanitize_mapper import SanitizeMapper
from app.coddy.agentic.schemas.enhanced_user_request import EnhancedUserRequest
from app.coddy.agentic.schemas.research import (
    EpisodeResearchResult,
    ResearchClarificationResult,
    ResearchReport,
)
from app.coddy.agentic.schemas.research_plan import ResearchPlan
from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest
from app.coddy.agentic.services.artifact_service import ArtifactService
from app.coddy.agentic.services.metrics_service import (
    MetricsPlugin,
    MetricsService,
)
from app.coddy.agentic.services.pricing_service import get_pricing_service
from app.coddy.agentic.services.session_service import SessionService
from app.coddy.agentic.workflows.coding_orchestrate.step_1_nodes import (
    load_project_context,
    step_1_node,
)
from app.coddy.agentic.workflows.coding_orchestrate.step_2_nodes import step_2_node
from app.coddy.agentic.workflows.coding_orchestrate.step_3_nodes import (
    check_clarifier_outcome,
    finalize_research_step,
    init_research_queue,
    load_research_material,
    prepare_clarifier_input,
    prepare_reporter_input,
    setup_episodic_research_context,
    step_3_node,
    verify_remaining_research,
)
from app.coddy.agentic.workflows.coding_orchestrate.step_4_nodes import step_4_node
from app.coddy.agentic.workflows.coding_orchestrate.step_5_nodes import step_5_node
from app.coddy.agentic.workflows.coding_orchestrate.step_6_nodes import (
    _finalize_output,
    finalize_node,
    step_6_node,
)
from app.coddy.helpers.env_helpers import load_environment
from app.coddy.helpers.logging_helpers import configure_logging
from app.coddy.utils.services import get_ui_service
from app.coddy.utils.services.user_service import get_user_service

load_environment()
configure_logging()


def extract_structured_output[T: BaseModel](
    context: CallbackContext,
    schema: type[T],
    llm_response: Any = None,
) -> T | None:
    """Extracts and parses structured output from llm_response or session event log."""
    # Priority 1: Direct extraction from llm_response if provided
    if llm_response is not None:
        if getattr(llm_response, "content", None):
            for part in getattr(llm_response.content, "parts", []):
                if getattr(part, "text", None):
                    try:
                        return schema.model_validate_json(part.text)
                    except (ValidationError, ValueError):
                        pass
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", "") == "set_model_response":
                    try:
                        return schema.model_validate(dict(fc.args))
                    except (ValidationError, ValueError):
                        pass
        return None

    # Priority 2: Search backwards for the most recent event produced by this agent in the current turn
    agent_name = context.agent_name
    events = getattr(context.session, "events", [])
    start_idx = 0
    if hasattr(context, "state") and isinstance(getattr(context, "state", None), dict):
        raw_idx = context.state.get(f"_event_idx_before_{agent_name}", 0)
        if isinstance(raw_idx, int):
            start_idx = max(0, raw_idx)

    for i in range(len(events) - 1, start_idx - 1, -1):
        event = events[i]
        if getattr(event, "author", "") == agent_name and event.content:
            for part in event.content.parts:
                # Case 1: Standard structured JSON output in part.text
                if getattr(part, "text", None):
                    try:
                        return schema.model_validate_json(part.text)
                    except (ValidationError, ValueError):
                        pass

                # Case 2: Agent has tools + output_schema (via set_model_response)
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", "") == "set_model_response":
                    try:
                        return schema.model_validate(dict(fc.args))
                    except (ValidationError, ValueError):
                        pass

    return None


__all__ = [
    "CodingOrchestratorWorkflow",
    "_finalize_output",
    "extract_structured_output",
    "finalize_node",
    "load_project_context",
    "load_research_material",
    "step_1_node",
    "step_2_node",
    "step_3_node",
    "step_4_node",
    "step_5_node",
    "step_6_node",
]


class CodingOrchestratorWorkflow(BaseAgent):
    """Workflow Engine: coding_orchestrate (coding-orchestrate)."""

    _workflow: Workflow = PrivateAttr()
    _coding_sanitize_agent: CodingSanitizerAgent = PrivateAttr()
    _coding_ambiguity_clarifier_agent: CodingAmbiguityClarifierAgent = PrivateAttr()
    _coding_research_plan_agent: CodingResearchPlannerAgent = PrivateAttr()
    _coding_researcher_agent: CodingResearcherAgent = PrivateAttr()
    _coding_research_clarifier_agent: CodingResearchClarifierAgent = PrivateAttr()
    _coding_research_reporter_agent: CodingResearchReporterAgent = PrivateAttr()
    _session_service: BaseSessionService = PrivateAttr()
    _metrics_service: MetricsService = PrivateAttr()
    _metrics_plugin: MetricsPlugin = PrivateAttr()

    def __init__(
        self,
        /,
        session_service: BaseSessionService | None = None,
        db_url: str | None = None,
        metrics_service: MetricsService | None = None,
    ) -> None:
        super().__init__(
            name="coding_orchestrator_workflow",
            description="Coding Orchestrator Workflow",
        )
        if session_service is not None:
            self._session_service = session_service
        else:
            self._session_service = SessionService(db_url=db_url)

        if metrics_service is not None:
            self._metrics_service = metrics_service
        else:
            self._metrics_service = MetricsService()
        self._metrics_plugin = MetricsPlugin(metrics_service=self._metrics_service)

        self._coding_sanitize_agent = CodingSanitizerAgent(
            before_agent_callback=CodingOrchestratorWorkflow.on_before_agent,
            after_agent_callback=CodingOrchestratorWorkflow.on_after_coding_sanitize_agent,
            after_model_callback=CodingOrchestratorWorkflow.on_after_model_coding_sanitize_agent,
        )
        self._coding_ambiguity_clarifier_agent = CodingAmbiguityClarifierAgent(
            before_agent_callback=CodingOrchestratorWorkflow.on_before_agent,
            after_agent_callback=CodingOrchestratorWorkflow.on_after_coding_ambiguity_clarifier_agent,
            after_model_callback=CodingOrchestratorWorkflow.on_after_model_coding_ambiguity_clarifier_agent,
        )
        self._coding_research_plan_agent = CodingResearchPlannerAgent(
            before_agent_callback=CodingOrchestratorWorkflow.on_before_agent,
            after_agent_callback=CodingOrchestratorWorkflow.on_after_coding_research_plan_agent,
            after_model_callback=CodingOrchestratorWorkflow.on_after_model_coding_research_plan_agent,
        )
        self._coding_researcher_agent = CodingResearcherAgent(
            before_agent_callback=CodingOrchestratorWorkflow.on_before_agent,
            after_agent_callback=CodingOrchestratorWorkflow.on_after_coding_researcher_agent,
            after_model_callback=CodingOrchestratorWorkflow.on_after_model_coding_researcher_agent,
        )
        self._coding_research_clarifier_agent = CodingResearchClarifierAgent(
            before_agent_callback=CodingOrchestratorWorkflow.on_before_agent,
            after_agent_callback=CodingOrchestratorWorkflow.on_after_coding_research_clarifier_agent,
            after_model_callback=CodingOrchestratorWorkflow.on_after_model_coding_research_clarifier_agent,
        )
        self._coding_research_reporter_agent = CodingResearchReporterAgent(
            before_agent_callback=CodingOrchestratorWorkflow.on_before_agent,
            after_agent_callback=CodingOrchestratorWorkflow.on_after_coding_research_reporter_agent,
            after_model_callback=CodingOrchestratorWorkflow.on_after_model_coding_research_reporter_agent,
        )
        self._workflow = Workflow(
            name="coding_orchestrate_workflow",
            description="Coding Orchestrate Workflow",
            edges=[
                # Main workflow through research plan, episodic research loop and routing
                (
                    START,
                    step_1_node,
                    load_project_context,
                    self._coding_sanitize_agent,
                    step_2_node,
                    self._coding_ambiguity_clarifier_agent,
                    step_3_node,
                    load_research_material,
                    self._coding_research_plan_agent,
                    init_research_queue,
                    setup_episodic_research_context,
                    self._coding_researcher_agent,
                    verify_remaining_research,
                    {
                        "loop_research": setup_episodic_research_context,
                        "clarify_issues": prepare_clarifier_input,
                        "assemble_report": prepare_reporter_input,
                    },
                ),
                # Clarifier branch and routing
                (
                    prepare_clarifier_input,
                    self._coding_research_clarifier_agent,
                    check_clarifier_outcome,
                    {
                        "new_research": setup_episodic_research_context,
                        "assemble_report": prepare_reporter_input,
                    },
                ),
                # Reporter branch through final steps
                (
                    prepare_reporter_input,
                    self._coding_research_reporter_agent,
                    finalize_research_step,
                    step_4_node,
                    step_5_node,
                    _finalize_output,
                ),
            ],
        )

    @property
    def session_service(self) -> BaseSessionService:
        """Returns the active ADK session service."""
        return self._session_service

    @property
    def metrics_service(self) -> MetricsService:
        """Returns the active metrics service."""
        return self._metrics_service

    @staticmethod
    def on_before_agent(context: CallbackContext):
        events = getattr(context.session, "events", [])
        if hasattr(context, "state") and context.state is not None:
            context.state[f"_event_idx_before_{context.agent_name}"] = len(events)
        ui = get_ui_service()
        ui.start_agent_view(agent_name=context.agent_name)
        return None

    @staticmethod
    def on_after_agent(context: CallbackContext):
        ui = get_ui_service()

        agent_name = context.agent_name
        events = getattr(context.session, "events", [])

        prompt_tokens = 0
        completion_tokens = 0
        reasoning_tokens = 0
        cached_tokens = 0
        turns = 0
        cost_eur = 0.0

        pricing_service = get_pricing_service()

        for event in events:
            if getattr(event, "author", "") == agent_name:
                usage = getattr(event, "usage_metadata", None)
                if usage:
                    p_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
                    c_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
                    cached_tok = int(getattr(usage, "cached_content_token_count", 0) or 0)
                    r_tok = int(getattr(usage, "thoughts_token_count", 0) or 0)

                    prompt_tokens += p_tok
                    completion_tokens += c_tok
                    cached_tokens += cached_tok
                    reasoning_tokens += r_tok
                    turns += 1

                    model_name = getattr(event, "model_version", None) or getattr(event, "model", None) or ""
                    breakdown = pricing_service.calculate_step_cost(
                        model_name=model_name,
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        cached_tokens=cached_tok,
                    )
                    cost_eur += breakdown.total_cost_eur

        active_view = ui.active_agent_view
        duration_sec = 0.0
        if active_view is not None:
            duration_sec = max(0.0, time.perf_counter() - active_view.start_time)

        metrics = {
            "turns": turns,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cached_tokens": cached_tokens,
            "duration_sec": duration_sec,
            "cost_eur": cost_eur,
        }
        ui.finish_agent_view(agent_name=agent_name, metrics=metrics)
        return None

    @staticmethod
    def on_before_coding_sanitize_agent(context: CallbackContext):
        ui = get_ui_service()
        ui.start_progress("Sanitizing user request...")
        return None

    @staticmethod
    def _persist_sanitizer_output(
        context: CallbackContext,
        sanitized_user_request: SanitizedUserRequest,
        show_boxes: bool = False,
    ) -> None:
        """Persists sanitized user request artifacts into state and disk."""
        context.state["sanitized_user_request"] = sanitized_user_request.model_dump()
        session_id = getattr(context.session, "id", None)
        if not session_id:
            return

        artifact_service = ArtifactService(session_id=session_id)
        user_req_md = SanitizeMapper.format_user_request(sanitized_user_request)
        local_inst_md = SanitizeMapper.format_local_project_instructions(sanitized_user_request)
        description_md = SanitizeMapper.format_local_project_description(sanitized_user_request)

        paths = artifact_service.save_sanitizer_artifacts(
            sanitized_request=sanitized_user_request,
            user_request_md=user_req_md,
            local_instruction_md=local_inst_md,
            local_description_md=description_md,
        )

        context.state["sanitized_user_request_path"] = str(paths["json"])
        context.state["sanitized_user_request_md_path"] = str(paths["user_request_md"])
        if "local_instruction_md" in paths:
            context.state["sanitized_local_instruction_path"] = str(paths["local_instruction_md"])
        if "local_description_md" in paths:
            context.state["sanitized_local_description_path"] = str(paths["local_description_md"])

        ui = get_ui_service()
        ui.record_artifact(
            agent_name="coding-sanitizer",
            name=paths["user_request_md"].name,
            path=str(paths["user_request_md"]),
        )
        ui.record_artifact(
            agent_name="coding-sanitizer",
            name=paths["json"].name,
            path=str(paths["json"]),
        )
        if "local_instruction_md" in paths:
            ui.record_artifact(
                agent_name="coding-sanitizer",
                name=paths["local_instruction_md"].name,
                path=str(paths["local_instruction_md"]),
            )
        if "local_description_md" in paths:
            ui.record_artifact(
                agent_name="coding-sanitizer",
                name=paths["local_description_md"].name,
                path=str(paths["local_description_md"]),
            )

        if show_boxes:
            ui.show_markdown_box(
                content=user_req_md,
                title="SANITIZED_USER_REQUEST.md",
                border_style="cyan",
            )
            if local_inst_md:
                ui.show_markdown_box(
                    content=local_inst_md,
                    title="SANITIZED_LOCAL_PROJECT_INSTRUCTIONS.md",
                    border_style="cyan",
                )
            if description_md:
                ui.show_markdown_box(
                    content=description_md,
                    title="SANITIZED_LOCAL_PROJECT_DESCRIPTION.md",
                    border_style="cyan",
                )

    @staticmethod
    def on_after_model_coding_sanitize_agent(
        callback_context: CallbackContext,
        llm_response: Any = None,
    ) -> Any:
        if llm_response is not None and getattr(llm_response, "partial", False) is True:
            return None

        ui = get_ui_service()
        ui.stop_progress()

        try:
            sanitized_user_request = extract_structured_output(
                context=callback_context,
                schema=SanitizedUserRequest,
                llm_response=llm_response,
            )
            if sanitized_user_request:
                CodingOrchestratorWorkflow._persist_sanitizer_output(
                    context=callback_context,
                    sanitized_user_request=sanitized_user_request,
                    show_boxes=True,
                )
        except Exception as exc:
            ui.error(f"Failed to gather artifacts from coding-sanitizer: {exc}", exc=exc, show_trace=True)

        return None

    @staticmethod
    def on_after_coding_sanitize_agent(context: CallbackContext):
        # Fallback in case after_model_callback did not run or state is missing
        if "sanitized_user_request" not in context.state:
            sanitized_user_request = extract_structured_output(context=context, schema=SanitizedUserRequest)
            if sanitized_user_request:
                CodingOrchestratorWorkflow._persist_sanitizer_output(
                    context=context,
                    sanitized_user_request=sanitized_user_request,
                    show_boxes=False,
                )

        CodingOrchestratorWorkflow.on_after_agent(context)
        return None

    @staticmethod
    def _persist_clarifier_output(
        context: CallbackContext,
        enhanced_user_request: EnhancedUserRequest,
        show_boxes: bool = False,
    ) -> None:
        """Persists enhanced user request artifacts into state and disk."""
        context.state["enhanced_user_request"] = enhanced_user_request.model_dump()
        session_id = getattr(context.session, "id", None)
        if not session_id:
            return

        artifact_service = ArtifactService(session_id=session_id)
        user_req_md = EnhancedUserRequestMapper.to_markdown(enhanced_user_request)

        paths = artifact_service.save_enhanced_user_request_artifacts(
            enhanced_request=enhanced_user_request,
            user_request_md=user_req_md,
        )

        context.state["enhanced_user_request_path"] = str(paths["json"])
        context.state["enhanced_user_request_md_path"] = str(paths["user_request_md"])

        ui = get_ui_service()
        ui.record_artifact(
            agent_name="coding-ambiguity-clarifier",
            name=paths["user_request_md"].name,
            path=str(paths["user_request_md"]),
        )
        ui.record_artifact(
            agent_name="coding-ambiguity-clarifier",
            name=paths["json"].name,
            path=str(paths["json"]),
        )

        if show_boxes:
            ui.show_markdown_box(
                content=user_req_md,
                title="ENHANCED_USER_REQUEST.md",
                border_style="cyan",
            )

    @staticmethod
    def on_after_model_coding_ambiguity_clarifier_agent(
        callback_context: CallbackContext,
        llm_response: Any = None,
    ) -> Any:
        if llm_response is not None and getattr(llm_response, "partial", False) is True:
            return None

        ui = get_ui_service()
        ui.stop_progress()

        try:
            enhanced_user_request = extract_structured_output(
                context=callback_context,
                schema=EnhancedUserRequest,
                llm_response=llm_response,
            )
            if enhanced_user_request:
                CodingOrchestratorWorkflow._persist_clarifier_output(
                    context=callback_context,
                    enhanced_user_request=enhanced_user_request,
                    show_boxes=True,
                )
        except Exception as exc:
            ui.error(f"Failed to gather artifacts from coding-ambiguity-clarifier: {exc}", exc=exc, show_trace=True)

        return None

    @staticmethod
    def on_after_coding_ambiguity_clarifier_agent(context: CallbackContext):
        # Fallback in case after_model_callback did not run or state is missing
        if "enhanced_user_request" not in context.state:
            enhanced_user_request = extract_structured_output(context=context, schema=EnhancedUserRequest)
            if enhanced_user_request:
                CodingOrchestratorWorkflow._persist_clarifier_output(
                    context=context,
                    enhanced_user_request=enhanced_user_request,
                    show_boxes=False,
                )

        CodingOrchestratorWorkflow.on_after_agent(context)
        return None

    @staticmethod
    def _persist_research_plan_output(
        context: CallbackContext,
        research_plan: ResearchPlan,
        show_boxes: bool = False,
    ) -> None:
        """Persists research plan artifacts into state and disk."""
        context.state["research_plan"] = research_plan.model_dump()
        context.state["research_materials_context"] = [item.model_dump() for item in research_plan.research_materials]
        session_id = getattr(context.session, "id", None)
        if not session_id:
            return

        artifact_service = ArtifactService(session_id=session_id)
        plan_md = ResearchPlanMapper.to_markdown(research_plan)

        json_path, md_path = artifact_service.save_research_plan_artifacts(
            plan=research_plan,
            plan_md=plan_md,
        )
        artifact_service.save_research_plan(
            project_name="coddy_project",
            plan=research_plan.model_dump(),
            plan_md=plan_md,
        )

        context.state["research_plan_json_path"] = str(json_path)
        context.state["research_plan_md_path"] = str(md_path)

        ui = get_ui_service()
        ui.record_artifact(
            agent_name="coding-research-planner",
            name=md_path.name,
            path=str(md_path),
        )
        ui.record_artifact(
            agent_name="coding-research-planner",
            name=json_path.name,
            path=str(json_path),
        )

        if show_boxes:
            ui.show_markdown_box(
                content=plan_md,
                title="Research Plan",
                border_style="green",
            )

    @staticmethod
    def on_after_model_coding_research_plan_agent(
        callback_context: CallbackContext,
        llm_response: Any = None,
    ) -> Any:
        if llm_response is not None and getattr(llm_response, "partial", False) is True:
            return None

        ui = get_ui_service()
        ui.stop_progress()

        try:
            research_plan = extract_structured_output(
                context=callback_context,
                schema=ResearchPlan,
                llm_response=llm_response,
            )
            if research_plan:
                CodingOrchestratorWorkflow._persist_research_plan_output(
                    context=callback_context,
                    research_plan=research_plan,
                    show_boxes=True,
                )
        except Exception as exc:
            ui.error(f"Failed to gather artifacts from coding-research-planner: {exc}", exc=exc, show_trace=True)

        return None

    @staticmethod
    def on_after_coding_research_plan_agent(context: CallbackContext):
        # Fallback in case after_model_callback did not run or state is missing
        if "research_plan" not in context.state:
            research_plan = extract_structured_output(context=context, schema=ResearchPlan)
            if research_plan:
                CodingOrchestratorWorkflow._persist_research_plan_output(
                    context=context,
                    research_plan=research_plan,
                    show_boxes=False,
                )

        CodingOrchestratorWorkflow.on_after_agent(context)
        return None

    @staticmethod
    def _persist_researcher_output(
        context: CallbackContext,
        result: EpisodeResearchResult,
        show_boxes: bool = False,
    ) -> None:
        """Persists episodic research result artifacts into state and disk."""
        if "completed_researches" not in context.state:
            context.state["completed_researches"] = []
        if "open_issues_raised" not in context.state:
            context.state["open_issues_raised"] = []

        active_idx = context.state.get("active_episode_index", context.state.get("current_episode_index", 0))
        if context.state.get("_last_persisted_episode_index") == active_idx:
            return

        completed: list[dict[str, Any]] = list(context.state["completed_researches"])
        completed.append(result.model_dump())
        context.state["completed_researches"] = completed
        context.state["_last_persisted_episode_index"] = active_idx
        context.state["current_episode_index"] = active_idx + 1

        if result.open_issues:
            open_issues: list[str] = list(context.state["open_issues_raised"])
            for issue in result.open_issues:
                if issue not in open_issues:
                    open_issues.append(issue)
            context.state["open_issues_raised"] = open_issues

        session_id = getattr(context.session, "id", None)
        if not session_id:
            return

        artifact_service = ArtifactService(session_id=session_id)
        result_md = EpisodeResearchMapper.to_markdown(result)
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", result.subject_title.lower()).strip("_") or "subject"
        json_path, md_path = artifact_service.save_episode_research(
            episode_index=active_idx + 1,
            subject_slug=slug,
            result=result,
            result_md=result_md,
        )

        ui = get_ui_service()
        ui.record_artifact(
            agent_name="coding-researcher",
            name=md_path.name,
            path=str(md_path),
        )
        ui.record_artifact(
            agent_name="coding-researcher",
            name=json_path.name,
            path=str(json_path),
        )

        if show_boxes:
            ui.show_markdown_box(
                content=result_md,
                title=f"Research Episode {active_idx + 1}: {result.subject_title}",
                border_style="cyan",
            )

    @staticmethod
    def on_after_model_coding_researcher_agent(
        callback_context: CallbackContext,
        llm_response: Any = None,
    ) -> Any:
        if llm_response is not None and getattr(llm_response, "partial", False) is True:
            return None

        ui = get_ui_service()
        ui.stop_progress()

        try:
            result = extract_structured_output(
                context=callback_context,
                schema=EpisodeResearchResult,
                llm_response=llm_response,
            )
            if result:
                CodingOrchestratorWorkflow._persist_researcher_output(
                    context=callback_context,
                    result=result,
                    show_boxes=True,
                )
        except Exception as exc:
            ui.error(f"Failed to gather artifacts from coding-researcher: {exc}", exc=exc, show_trace=True)

        return None

    @staticmethod
    def on_after_coding_researcher_agent(context: CallbackContext):
        # Fallback in case after_model_callback did not persist
        active_idx = context.state.get("active_episode_index", context.state.get("current_episode_index", 0))
        if context.state.get("_last_persisted_episode_index") != active_idx:
            result = extract_structured_output(context=context, schema=EpisodeResearchResult)
            if result:
                CodingOrchestratorWorkflow._persist_researcher_output(
                    context=context,
                    result=result,
                    show_boxes=True,
                )

        CodingOrchestratorWorkflow.on_after_agent(context)
        return None

    @staticmethod
    def _persist_research_clarifier_output(
        context: CallbackContext,
        clarification_result: ResearchClarificationResult,
        show_boxes: bool = False,
    ) -> None:
        """Persists research clarification results into state."""
        context.state["clarification_result"] = clarification_result.model_dump()
        ui = get_ui_service()
        if show_boxes and clarification_result.resolved_issues:
            box_lines = ["# Resolved Open Issues", ""]
            for r in clarification_result.resolved_issues:
                box_lines.append(f"- **{r.issue}** ({r.source}): {r.resolution}")
            ui.show_markdown_box(
                content="\n".join(box_lines),
                title="Research Clarifications",
                border_style="cyan",
            )

    @staticmethod
    def on_after_model_coding_research_clarifier_agent(
        callback_context: CallbackContext,
        llm_response: Any = None,
    ) -> Any:
        if llm_response is not None and getattr(llm_response, "partial", False) is True:
            return None

        ui = get_ui_service()
        ui.stop_progress()

        try:
            clarification_result = extract_structured_output(
                context=callback_context,
                schema=ResearchClarificationResult,
                llm_response=llm_response,
            )
            if clarification_result:
                CodingOrchestratorWorkflow._persist_research_clarifier_output(
                    context=callback_context,
                    clarification_result=clarification_result,
                    show_boxes=True,
                )
        except Exception as exc:
            ui.error(f"Failed to gather artifacts from coding-research-clarifier: {exc}", exc=exc, show_trace=True)

        return None

    @staticmethod
    def on_after_coding_research_clarifier_agent(context: CallbackContext):
        # Fallback in case after_model_callback did not run
        if "clarification_result" not in context.state:
            clarification_result = extract_structured_output(context=context, schema=ResearchClarificationResult)
            if clarification_result:
                CodingOrchestratorWorkflow._persist_research_clarifier_output(
                    context=context,
                    clarification_result=clarification_result,
                    show_boxes=False,
                )

        CodingOrchestratorWorkflow.on_after_agent(context)
        return None

    @staticmethod
    def _persist_research_reporter_output(
        context: CallbackContext,
        report: ResearchReport,
        show_boxes: bool = False,
    ) -> None:
        """Persists research report JSON and Markdown artifacts into state and disk."""
        context.state["research_report"] = report.model_dump()
        session_id = getattr(context.session, "id", None)
        if not session_id:
            return

        artifact_service = ArtifactService(session_id=session_id)
        report_md = ResearchReportMapper.to_markdown(report)
        json_path, md_path = artifact_service.save_research_report(
            report=report,
            report_md=report_md,
        )

        context.state["research_report_json_path"] = str(json_path)
        context.state["research_report_md_path"] = str(md_path)

        ui = get_ui_service()
        ui.record_artifact(
            agent_name="coding-research-reporter",
            name=md_path.name,
            path=str(md_path),
        )
        ui.record_artifact(
            agent_name="coding-research-reporter",
            name=json_path.name,
            path=str(json_path),
        )

        if show_boxes:
            ui.show_markdown_box(
                content=report_md,
                title="RESEARCH_REPORT.md",
                border_style="green",
            )

    @staticmethod
    def on_after_model_coding_research_reporter_agent(
        callback_context: CallbackContext,
        llm_response: Any = None,
    ) -> Any:
        if llm_response is not None and getattr(llm_response, "partial", False) is True:
            return None

        ui = get_ui_service()
        ui.stop_progress()

        try:
            report = extract_structured_output(
                context=callback_context,
                schema=ResearchReport,
                llm_response=llm_response,
            )
            if report:
                CodingOrchestratorWorkflow._persist_research_reporter_output(
                    context=callback_context,
                    report=report,
                    show_boxes=True,
                )
        except Exception as exc:
            ui.error(f"Failed to gather artifacts from coding-research-reporter: {exc}", exc=exc, show_trace=True)

        return None

    @staticmethod
    def on_after_coding_research_reporter_agent(context: CallbackContext):
        # Fallback in case after_model_callback did not run
        if "research_report" not in context.state:
            report = extract_structured_output(context=context, schema=ResearchReport)
            if report:
                CodingOrchestratorWorkflow._persist_research_reporter_output(
                    context=context,
                    report=report,
                    show_boxes=False,
                )

        CodingOrchestratorWorkflow.on_after_agent(context)
        return None

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        wf_ctx = Context(invocation_context=ctx, node=self._workflow)
        async for event in self._workflow.run(ctx=wf_ctx, node_input=ctx.user_content):
            yield event

    async def start(
        self,
        user_request: str,
        session_id: str | None = None,
        user_id: str | None = None,
        research_material_paths: list[Any] | None = None,
    ) -> str:
        """Starts workflow execution using the configured session service and SQLite working memory.

        Args:
            user_request: Raw user prompt string.
            session_id: Optional session ID string. If not provided, generates a fresh UUID4.
            user_id: Optional user identifier; defaults via get_current_user_id().
            research_material_paths: Optional list of file paths to research materials.

        Returns:
            The active session ID.
        """
        resolved_user_id = user_id or get_user_service().get_current_user_id()
        resolved_session_id = session_id or str(uuid4())

        initial_state: dict[str, Any] = {}
        if research_material_paths:
            initial_state["research_material_paths"] = [str(p) for p in research_material_paths]

        if isinstance(self._session_service, SessionService):
            session = await self._session_service.create_or_get_session(
                session_id=resolved_session_id,
                user_id=resolved_user_id,
                app_name="coddy",
                initial_state=initial_state,
            )
        else:
            session = await SessionService.create_or_get(
                session_service=self._session_service,
                session_id=resolved_session_id,
                user_id=resolved_user_id,
                app_name="coddy",
                initial_state=initial_state,
            )

        if initial_state and hasattr(session, "state"):
            for k, v in initial_state.items():
                session.state[k] = v

        runner = Runner(
            agent=self._workflow,
            session_service=self._session_service,
            app_name="coddy",
            plugins=[self._metrics_plugin],
        )

        async for _ in runner.run_async(
            user_id=resolved_user_id,
            session_id=resolved_session_id,
            new_message=types.Content(parts=[types.Part(text=user_request)]),
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            pass

        try:
            self._metrics_service.display_session_summary(
                resolved_session_id,
                console=get_ui_service().console,
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Failed to display session summary: %s", exc)

        return resolved_session_id
