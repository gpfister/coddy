"""Step 6 Nodes (Backwards compatibility alias for step 5)."""

from typing import Any

from google.adk.workflow import node

from app.coddy.agentic.workflows.coding_orchestrate.step_5_nodes import (
    _finalize_output,
    finalize_node,
)


@node(name="step_6_node")
async def step_6_node(node_input: Any = None) -> Any:
    """Backwards compatibility alias node for step 6."""
    return node_input


__all__ = ["_finalize_output", "finalize_node", "step_6_node"]
