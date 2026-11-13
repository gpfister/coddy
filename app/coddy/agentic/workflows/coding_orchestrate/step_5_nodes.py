"""Step 5 Nodes for coding-orchestrate workflow: Implementation Planning & Finalization."""

from typing import Any

from google.adk.workflow import node

from app.coddy.utils.services import get_ui_service


@node(name="step_5_node")
async def step_5_node(node_input: Any = None) -> Any:
    """Step 5: Implementation planning (empty step for now)."""
    get_ui_service().show_step(
        step_number=5,
        total_steps=5,
        title="Implementation Planning",
        description="Generates task decomposition and execution plan",
        is_empty=True,
    )
    return node_input


@node(name="finalize_node")
async def finalize_node(node_input: Any) -> dict[str, Any]:
    """Terminal node wrapping the final outcome."""
    return {"final_result": node_input}


_finalize_output = finalize_node

__all__ = ["_finalize_output", "finalize_node", "step_5_node"]
