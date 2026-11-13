"""Step 1 Nodes for coding-orchestrate workflow: Sanitization and Context Loading."""

from pathlib import Path
from typing import Any

from google.adk.agents.context import Context
from google.adk.workflow import node

from app.coddy.utils.services import get_ui_service


@node(name="step_1_node")
async def step_1_node(node_input: Any = None) -> Any:
    """Step 1: Sanitization (runs coding-sanitizer agent)."""
    get_ui_service().show_step(
        step_number=1,
        total_steps=5,
        title="Sanitization",
        description="Normalizes prompt and analyzes ambiguities",
        is_empty=False,
    )
    return node_input


@node(name="load_project_context")
async def load_project_context(ctx: Context, node_input: Any = None) -> Any:
    """Step 1 Pre-node: Reads ./README.md (local project description) and ./AGENTS.md (local project instructions) and adds them to context."""
    ui = get_ui_service()
    ui.start_node_view(node_name="load_project_context")

    try:
        # 1. README.md (local project description)
        ui.record_node_reading_file("./README.md")
        readme_path = Path("./README.md").resolve()
        if readme_path.is_file():
            readme_text = readme_path.read_text(encoding="utf-8")
            ctx.state["local_project_description"] = readme_text
            ui.record_node_file_result(display_name="./README.md", found=True, abs_path=str(readme_path))
        else:
            ctx.state["local_project_description"] = None
            ui.record_node_file_result(display_name="./README.md", found=False)

        # 2. AGENTS.md (local project instructions)
        ui.record_node_reading_file("./AGENTS.md")
        agents_path = Path("./AGENTS.md").resolve()
        if agents_path.is_file():
            agents_text = agents_path.read_text(encoding="utf-8")
            ctx.state["local_project_instructions"] = agents_text
            ui.record_node_file_result(display_name="./AGENTS.md", found=True, abs_path=str(agents_path))
        else:
            ctx.state["local_project_instructions"] = None
            ui.record_node_file_result(display_name="./AGENTS.md", found=False)

        ui.finish_node_view()
    except Exception as exc:
        ui.fail_node_view(error_message=str(exc))
        raise exc

    return node_input
