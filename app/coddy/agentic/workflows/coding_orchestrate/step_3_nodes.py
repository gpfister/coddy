"""Step 3 Nodes for coding-orchestrate workflow: Research Planning, Execution & Reporting."""

from pathlib import Path
from typing import Any

from google.adk.agents.context import Context
from google.adk.events import Event, EventActions
from google.adk.workflow import node
from google.genai import types
from rich.markup import escape

from app.coddy.agentic.services.artifact_service import ArtifactService
from app.coddy.agentic.services.research_material_service import ResearchMaterialService
from app.coddy.utils.services import get_ui_service


@node(name="step_3_node")
async def step_3_node(ctx: Context | Any = None, node_input: Any = None) -> Any:
    """Step 3: Research & Investigation (announcement and input preparation)."""
    ui = get_ui_service()
    ui.show_step(
        step_number=3,
        total_steps=5,
        title="Research & Investigation",
        description="Generates deep research plan, executes episodic investigations, clarifies open issues, and synthesizes technical report",
        is_empty=False,
    )

    state = getattr(ctx, "state", None)
    if state is None or not hasattr(state, "get"):
        return node_input if node_input is not None else ctx

    enhanced_req = state.get("enhanced_user_request")
    if enhanced_req:
        if isinstance(enhanced_req, dict):
            req_text = enhanced_req.get("user_request", "")
            state["local_project_instructions"] = enhanced_req.get("local_project_instructions")
            state["local_project_description"] = enhanced_req.get("local_project_description")
        else:
            req_text = getattr(enhanced_req, "user_request", "")
            state["local_project_instructions"] = getattr(enhanced_req, "local_project_instructions", None)
            state["local_project_description"] = getattr(enhanced_req, "local_project_description", None)
        if req_text.strip():
            return types.Content(parts=[types.Part(text=req_text.strip())])

    return node_input


@node(name="load_research_material")
async def load_research_material(ctx: Context, node_input: Any = None) -> Any:
    """Step 3 Pre-node: Ingests research material files and adds them to context."""
    state = getattr(ctx, "state", None)
    if state is None or not hasattr(state, "get"):
        return node_input

    raw_material_paths = state.get("research_material_paths")
    if not raw_material_paths or not isinstance(raw_material_paths, list):
        return node_input

    ui = get_ui_service()
    ui.start_node_view(node_name="load_research_material")

    try:
        material_service = ResearchMaterialService()
        ingested_materials: list[dict[str, Any]] = []

        for p in raw_material_paths:
            ui.record_node_reading_file(str(p))
            ingested = material_service.ingest_file(p)
            ingested_materials.append(ingested)
            ui.record_node_file_result(display_name=str(p), found=True, abs_path=str(Path(p).resolve()))

        session = getattr(ctx, "session", None)
        session_id = getattr(session, "id", None) or "default_session"
        artifact_service = ArtifactService(session_id=session_id)
        saved_records = artifact_service.save_research_materials(ingested_materials)

        for rec in saved_records:
            ui.record_node_conversion_result(
                display_name=rec["original_file_name"],
                target_name=rec["converted_file_name"],
                abs_path=rec["original_artifact_path"],
                target_path=rec["artifact_path"],
            )
            ui.record_artifact(
                agent_name="coding-research-planner",
                name=rec["converted_file_name"],
                path=rec["artifact_path"],
            )

        formatted_materials = ResearchMaterialService.format_materials_for_context(ingested_materials)
        state["research_materials"] = formatted_materials
        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return node_input


@node(name="init_research_queue")
async def init_research_queue(ctx: Context, node_input: Any = None) -> Any:
    """Initializes the episodic research queue from the finalized ResearchPlan."""
    ui = get_ui_service()
    ui.start_node_view(node_name="init_research_queue")
    try:
        state = getattr(ctx, "state", None)
        if state is None or not hasattr(state, "get"):
            ui.record_node_activity("No workflow state found; research queue empty")
            ui.finish_node_view()
            return node_input

        plan_data = state.get("research_plan") or {}
        topics = plan_data.get("topics") or []

        queue: list[dict[str, Any]] = []
        for topic in topics:
            topic_name = topic.get("topic", "")
            for subject in topic.get("subjects", []):
                queue.append(
                    {
                        "topic": topic_name,
                        "subject": subject,
                    }
                )

        state["research_queue"] = queue
        state["current_episode_index"] = 0
        state["completed_researches"] = []
        state["open_issues_raised"] = []

        ui.record_node_activity(f"Initialized research queue with {len(queue)} subjects across {len(topics)} topics")
        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return node_input


@node(name="setup_episodic_research_context")
async def setup_episodic_research_context(ctx: Context, node_input: Any = None) -> Any:
    """Prepares the episodic prompt for the next research subject."""
    ui = get_ui_service()
    ui.start_node_view(node_name="setup_episodic_research_context")
    try:
        state = getattr(ctx, "state", None)
        if state is None or not hasattr(state, "get"):
            ui.record_node_activity("No workflow state found; returning default input")
            ui.finish_node_view()
            return node_input

        queue = state.get("research_queue") or []
        idx = state.get("current_episode_index", 0)

        if idx >= len(queue):
            ui.record_node_activity(f"All {len(queue)} episodes prepared; queue exhausted")
            ui.finish_node_view()
            return node_input

        state["active_episode_index"] = idx

        item = queue[idx]
        topic_name = item.get("topic", "")
        subject = item.get("subject", {})
        subject_title = subject.get("title", "")

        ui.record_node_active_operation(f"Preparing episode {idx + 1}/{len(queue)}: {subject_title}")

        plan_data = state.get("research_plan") or {}
        u_summary = plan_data.get("user_request_summary") or "Overall user request and architecture requirements."
        u_bullets = plan_data.get("user_request_bullets") or []
        p_summary = plan_data.get("project_context_summary") or "Coddy project codebase architecture."
        p_bullets = plan_data.get("project_context_bullets") or []

        # Format Context section
        context_lines = [
            "## Context",
            "",
            "### User request",
            "",
            u_summary,
            "",
        ]
        if u_bullets:
            for b in u_bullets:
                context_lines.append(f"- {b}")
            context_lines.append("")

        context_lines.extend(
            [
                "### Project context",
                "",
                p_summary,
                "",
            ]
        )
        if p_bullets:
            for b in p_bullets:
                context_lines.append(f"- {b}")
            context_lines.append("")

        res_materials = plan_data.get("research_materials") or []
        if res_materials:
            context_lines.extend(
                [
                    "### Research materials",
                    "",
                ]
            )
            for mat in res_materials:
                f_path = mat.get("file_path", "")
                s_info = mat.get("served_information", "")
                i_targets = mat.get("investigation_targets", "")
                context_lines.append(f"- **{f_path}**:")
                if s_info:
                    context_lines.append(f"  - *Served Information*: {s_info}")
                if i_targets:
                    context_lines.append(f"  - *Investigation Targets*: {i_targets}")
            context_lines.append("")

        # Format Previous episode section
        completed = state.get("completed_researches") or []
        prev_lines = ["## Previous episode", ""]
        if completed:
            prev = completed[-1]
            prev_title = prev.get("subject_title", "Previous Subject")
            prev_p = prev.get("summary_paragraph", "")
            prev_b = prev.get("summary_bullets", [])
            prev_lines.append(f"**Previous Subject Researched**: {prev_title}\n")
            if prev_p:
                prev_lines.append(f"{prev_p}\n")
            if prev_b:
                for b in prev_b:
                    prev_lines.append(f"- {b}")
                prev_lines.append("")
        else:
            prev_lines.append("*(None - this is the initial research episode)*\n")

        # Format Current episode section
        curr_lines = [
            "## Current episode",
            "",
            f"### Topic: {topic_name}",
            f"### Subject: {subject.get('title', '')}",
            "",
            f"**Description**: {subject.get('description', '')}\n",
        ]

        sources = subject.get("target_sources") or ["code", "document"]
        curr_lines.append(f"**Target Sources**: {', '.join(sources)}\n")

        directions = subject.get("directions") or []
        if directions:
            curr_lines.append("**Directions & Expected Deliverables:**")
            for d in directions:
                curr_lines.append(f"- {d}")
            curr_lines.append("")

        approaches = subject.get("approaches") or []
        if approaches:
            curr_lines.append("**Candidate Technical Approaches to Evaluate:**")
            for a in approaches:
                curr_lines.append(f"- **{a.get('name', '')}**: {a.get('description', '')}")
                if a.get("rationale"):
                    curr_lines.append(f"  *Rationale*: {a.get('rationale')}")
            curr_lines.append("")

        open_issues = subject.get("open_issues") or []
        if open_issues:
            curr_lines.append("**Open Issues Expected to Resolve:**")
            for issue in open_issues:
                curr_lines.append(f"- {issue}")
            curr_lines.append("")

        full_prompt = "\n".join(context_lines + prev_lines + curr_lines).strip()
        ui.record_node_activity(
            f"Prepared episode {idx + 1}/{len(queue)}: [bold]{escape(subject_title)}[/bold] (Topic: {escape(topic_name)})"
        )
        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return types.Content(parts=[types.Part(text=full_prompt)])


@node(name="verify_remaining_research")
async def verify_remaining_research(ctx: Context, node_input: Any = None) -> Event:
    """Verifies if more research subjects remain or routes to clarification/reporting."""
    ui = get_ui_service()
    ui.start_node_view(node_name="verify_remaining_research")
    try:
        state = getattr(ctx, "state", None) or {}
        queue = state.get("research_queue") or []
        idx = state.get("current_episode_index", 0)

        if idx < len(queue):
            remaining = len(queue) - idx
            ui.record_node_activity(f"{remaining} research subject(s) remaining in queue -> routing to 'loop_research'")
            ui.finish_node_view()
            return Event(actions=EventActions(route="loop_research"))

        open_issues = state.get("open_issues_raised") or []
        if open_issues:
            ui.record_node_activity(
                f"All episodes complete, {len(open_issues)} open issue(s) raised -> routing to 'clarify_issues'"
            )
            ui.finish_node_view()
            return Event(actions=EventActions(route="clarify_issues"))

        ui.record_node_activity("All episodes complete with no open issues -> routing to 'assemble_report'")
        ui.finish_node_view()
        return Event(actions=EventActions(route="assemble_report"))
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc


@node(name="prepare_clarifier_input")
async def prepare_clarifier_input(ctx: Context, node_input: Any = None) -> Any:
    """Prepares aggregated research findings and open issues for coding-research-clarifier."""
    ui = get_ui_service()
    ui.start_node_view(node_name="prepare_clarifier_input")
    try:
        state = getattr(ctx, "state", None) or {}
        completed = state.get("completed_researches") or []
        open_issues = state.get("open_issues_raised") or []
        plan_data = state.get("research_plan") or {}

        lines = [
            "# Research Open Issues Clarification Request",
            "",
        ]

        topics = plan_data.get("topics") or []
        if topics:
            lines.extend(
                [
                    "## Active Research Plan Overview",
                    "",
                ]
            )
            for t in topics:
                subj_names = [s.get("subject", "") for s in t.get("subjects", [])]
                lines.append(f"- **{t.get('topic', '')}**: {', '.join(subj_names)}")
            lines.append("")

        lines.extend(
            [
                "## Summary of Completed Researches",
                "",
            ]
        )

        for idx, res in enumerate(completed, start=1):
            lines.append(f"### Episode {idx}: {res.get('subject_title', '')}")
            lines.append(f"{res.get('summary_paragraph', '')}\n")
            bullets = res.get("summary_bullets") or []
            for b in bullets:
                lines.append(f"- {b}")
            lines.append("")

        lines.extend(
            [
                "## Open Issues Raised During Research",
                "",
                "Please analyze the following open issues against the completed research findings above.",
                "Resolve what you can directly from findings, and ask the user about any remaining unresolved issues.",
                "",
            ]
        )

        for issue in open_issues:
            lines.append(f"- {issue}")

        ui.record_node_activity(
            f"Prepared clarification input: {len(open_issues)} open issue(s), {len(completed)} completed episode(s)"
        )
        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return types.Content(parts=[types.Part(text="\n".join(lines).strip())])


@node(name="check_clarifier_outcome")
async def check_clarifier_outcome(ctx: Context, node_input: Any = None) -> Event:
    """Checks if the clarifier added new research topics/subjects or routes to report assembly."""
    ui = get_ui_service()
    ui.start_node_view(node_name="check_clarifier_outcome")
    try:
        state = getattr(ctx, "state", None) or {}
        clarification = state.get("clarification_result") or {}
        new_topics = clarification.get("new_research_topics") or []

        new_subjects_found = False
        new_count = 0
        if new_topics:
            queue = state.get("research_queue") or []
            for topic in new_topics:
                t_name = topic.get("topic", "")
                for subject in topic.get("subjects", []):
                    queue.append(
                        {
                            "topic": t_name,
                            "subject": subject,
                        }
                    )
                    new_subjects_found = True
                    new_count += 1
            state["research_queue"] = queue

        if new_subjects_found:
            state["open_issues_raised"] = []
            ui.record_node_activity(
                f"Clarification added {new_count} new research subject(s) -> routing to 'new_research'"
            )
            ui.finish_node_view()
            return Event(actions=EventActions(route="new_research"))

        resolved_count = len(clarification.get("resolved_issues") or [])
        ui.record_node_activity(
            f"All issues resolved ({resolved_count} issue(s) handled) -> routing to 'assemble_report'"
        )
        ui.finish_node_view()
        return Event(actions=EventActions(route="assemble_report"))
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc


@node(name="prepare_reporter_input")
async def prepare_reporter_input(ctx: Context, node_input: Any = None) -> Any:
    """Prepares consolidated research data for coding-research-reporter."""
    ui = get_ui_service()
    ui.start_node_view(node_name="prepare_reporter_input")
    try:
        state = getattr(ctx, "state", None) or {}
        plan_data = state.get("research_plan") or {}
        completed = state.get("completed_researches") or []
        materials = state.get("research_materials") or []
        clarification = state.get("clarification_result") or {}

        lines = [
            "# Research Report Synthesis Request",
            "",
            "Synthesize a comprehensive technical research report from all research episodes, ingested materials, and clarified open issues.",
            "",
            "## Research Plan Rationale",
            plan_data.get("rationale", ""),
            "",
            "## Completed Research Episodes",
            "",
        ]

        for idx, res in enumerate(completed, start=1):
            lines.append(f"### Episode {idx}: {res.get('subject_title', '')}")
            lines.append(f"{res.get('summary_paragraph', '')}\n")
            if res.get("summary_bullets"):
                for b in res["summary_bullets"]:
                    lines.append(f"- {b}")
                lines.append("")
            if res.get("impacted_code_references"):
                lines.append("**Impacted Code References:**")
                for ref in res["impacted_code_references"]:
                    lines.append(
                        f"- `{ref.get('file_path')}` ({ref.get('symbol_name', '')}): {ref.get('description', '')}"
                    )
                lines.append("")
            if res.get("logic_and_rules_description"):
                lines.append(f"**Logic and Rules**:\n{res['logic_and_rules_description']}\n")
            if res.get("diagrams"):
                lines.append("**Diagrams Provided:**")
                for d in res["diagrams"]:
                    lines.append(f"- {d.get('title')}: {d.get('description', '')}")
                lines.append("")

        if materials:
            lines.extend(["## Ingested Research Materials", ""])
            for mat in materials:
                lines.append(f"- `{mat.get('file_path', '')}`: {mat.get('served_information', '')}")
            lines.append("")

        resolved = clarification.get("resolved_issues") or []
        if resolved:
            lines.extend(["## Clarification Log", ""])
            for item in resolved:
                lines.append(
                    f"- Issue: {item.get('issue', '')} -> Resolution ({item.get('source', '')}): {item.get('resolution', '')}"
                )
            lines.append("")

        ui.record_node_activity(
            f"Aggregated {len(completed)} episode(s) and {len(materials)} material source(s) for report synthesis"
        )
        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return types.Content(parts=[types.Part(text="\n".join(lines).strip())])


@node(name="finalize_research_step")
async def finalize_research_step(ctx: Context, node_input: Any = None) -> Any:
    """Finalizes Step 3 research execution."""
    ui = get_ui_service()
    ui.start_node_view(node_name="finalize_research_step")
    try:
        state = getattr(ctx, "state", None) or {}
        report = state.get("research_report")
        if report:
            ui.record_node_activity("Step 3 research synthesis complete; artifacts persisted")
        else:
            ui.record_node_activity("Step 3 research completed")
        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return node_input


__all__ = [
    "check_clarifier_outcome",
    "finalize_research_step",
    "init_research_queue",
    "load_research_material",
    "prepare_clarifier_input",
    "prepare_reporter_input",
    "setup_episodic_research_context",
    "step_3_node",
    "verify_remaining_research",
]
