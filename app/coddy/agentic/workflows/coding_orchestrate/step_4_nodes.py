"""Step 4 Nodes for coding-orchestrate workflow: Specification."""

from typing import Any

from google.adk.workflow import node

from app.coddy.utils.services import get_ui_service


@node(name="step_4_node")
async def step_4_node(node_input: Any = None) -> Any:
    """Step 4: Specification (empty step for now)."""
    get_ui_service().show_step(
        step_number=4,
        total_steps=5,
        title="Specification",
        description="Generates technical specification",
        is_empty=True,
    )
    return node_input


__all__ = ["step_4_node"]
