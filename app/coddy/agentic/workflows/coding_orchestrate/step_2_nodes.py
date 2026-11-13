"""Step 2 Nodes for coding-orchestrate workflow: Clarification of Ambiguities."""

from typing import Any

from google.adk.agents.context import Context
from google.adk.workflow import node
from google.genai import types

from app.coddy.utils.services import get_ui_service


@node(name="step_2_node")
async def step_2_node(ctx: Context | Any = None, node_input: Any = None) -> Any:
    """Step 2: Clarification of ambiguities (runs coding-ambiguity-clarifier agent)."""
    get_ui_service().show_step(
        step_number=2,
        total_steps=5,
        title="Clarification of Ambiguities",
        description="Resolves identified ambiguities interactively with the user",
        is_empty=False,
    )

    state = getattr(ctx, "state", None)
    if state is None or not hasattr(state, "get"):
        return node_input if node_input is not None else ctx

    sanitized_req = state.get("sanitized_user_request") or {}
    user_request_text = sanitized_req.get("user_request", "")
    ambiguous_terms = sanitized_req.get("ambiguous_terms", [])
    local_instructions = sanitized_req.get("local_project_instructions")
    local_description = sanitized_req.get("local_project_description")

    lines: list[str] = [
        "## Sanitized User Request",
        user_request_text,
        "",
        "## Identified Ambiguous Terms to Clarify",
    ]

    if ambiguous_terms:
        for idx, term_data in enumerate(ambiguous_terms, 1):
            if isinstance(term_data, dict):
                term_name = term_data.get("term", "")
                meanings = term_data.get("meanings", [])
                source = term_data.get("source")
            else:
                term_name = getattr(term_data, "term", str(term_data))
                meanings = getattr(term_data, "meanings", [])
                source = getattr(term_data, "source", None)

            source_str = f" (Source: {source})" if source else ""
            lines.append(f"{idx}. Term: '{term_name}'{source_str}")
            for m in meanings:
                lines.append(f"   - {m}")
    else:
        lines.append("None identified.")

    if local_description:
        lines.extend(["", "## Pre-loaded Local Project Description (README.md) Context", local_description])
    if local_instructions:
        lines.extend(["", "## Pre-loaded Local Project Instructions (AGENTS.md) Context", local_instructions])

    lines.append(
        "\nInstructions: Please clarify the ambiguities identified above with the user using ask_question. "
        "Evaluate their answers for any newly introduced ambiguities and clarify those as well. "
        "Once all ambiguities are resolved, generate the finalized EnhancedUserRequest structured output."
    )

    return types.Content(parts=[types.Part(text="\n".join(lines))])
