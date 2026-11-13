"""Hermetic unit tests for AgentExecutionView and format_duration."""

from io import StringIO

from rich.console import Console

from app.coddy.utils.ui.agent_view import (
    AgentExecutionView,
    AgentMetrics,
)
from app.coddy.utils.ui.duration_formatter import format_duration
from app.coddy.utils.ui.node_view import NodeExecutionView


def test_format_duration_edge_cases():
    """Verify format_duration conforms strictly to '<h> hour(s) <m> min <s> sec'."""
    # Zero and negative
    assert format_duration(0) == "0 sec"
    assert format_duration(0.0) == "0 sec"
    assert format_duration(-5) == "0 sec"

    # Sub-second non-zero (minimum 1 sec per agreed rule)
    assert format_duration(0.1) == "1 sec"
    assert format_duration(0.4) == "1 sec"
    assert format_duration(0.8) == "1 sec"

    # Seconds only
    assert format_duration(1.0) == "1 sec"
    assert format_duration(1.4) == "1 sec"
    assert format_duration(45) == "45 sec"

    # Minutes only (seconds is null/zero)
    assert format_duration(60) == "1 min"
    assert format_duration(120) == "2 min"

    # Minutes and seconds
    assert format_duration(65) == "1 min 5 sec"
    assert format_duration(125) == "2 min 5 sec"

    # Hours only (minutes and seconds are null/zero)
    assert format_duration(3600) == "1 hour(s)"
    assert format_duration(7200) == "2 hour(s)"

    # Hours and seconds (minutes is null/zero)
    assert format_duration(3605) == "1 hour(s) 5 sec"

    # Hours and minutes (seconds is null/zero)
    assert format_duration(3660) == "1 hour(s) 1 min"

    # Hours, minutes, and seconds
    assert format_duration(3665) == "1 hour(s) 1 min 5 sec"
    assert format_duration(7325) == "2 hour(s) 2 min 5 sec"


def test_agent_execution_view_running_state():
    """Verify AgentExecutionView renders running state with active spinner and operations."""
    view = AgentExecutionView(agent_name="coding-sanitizer")
    view.set_active_operation("thinking")

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=100)
    console.print(view)

    rendered = out.getvalue()
    assert "coding-sanitizer is running" in rendered
    assert "Thinking..." in rendered

    # Switch to tool call
    view.set_active_operation("tool:read_file")
    out2 = StringIO()
    console2 = Console(file=out2, force_terminal=True, width=100)
    console2.print(view)
    rendered2 = out2.getvalue()
    assert "Calling tool read_file..." in rendered2


def test_agent_execution_view_completed_timeline():
    """Verify AgentExecutionView renders completed timeline with all sub-steps and metrics table."""
    view = AgentExecutionView(agent_name="coding-sanitizer")

    # Add thinking turn (with reasoning tokens)
    view.add_thinking(duration_sec=3.2, reasoning_tokens=100)

    # Add prompt processing turn
    view.add_prompt_processing(duration_sec=1.5)

    # Add output generation turn
    view.add_output_generation(duration_sec=2.4, completion_tokens=150, tokens_per_sec=62.5)

    # Add tool calls (one success, one failure)
    view.add_tool_call(tool_name="read_file", status="SUCCESS", duration_sec=0.25)
    view.add_tool_call(tool_name="failing_tool", status="FAILED", duration_sec=1.1, error_message="File not found")

    # Add user question with selection
    view.add_user_question(
        question="Which database backend?",
        options=["PostgreSQL (Recommended)", "SQLite", "DuckDB"],
        selected_idx=2,
    )

    # Add intermediate text (suppressed in output per design)
    view.add_intermediate_text("Analyzing repository structure and requirements...")

    # Add artifact
    view.add_artifact(name="SANITIZED_USER_REQUEST.md", path="/path/to/SANITIZED_USER_REQUEST.md")

    # Complete with metrics
    metrics = AgentMetrics(
        turns=1,
        prompt_tokens=1500,
        completion_tokens=350,
        reasoning_tokens=120,
        cached_tokens=0,
        duration_sec=4.55,
        cost_eur=0.0034,
    )
    view.complete(metrics=metrics)

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=120)
    console.print(view)
    rendered = out.getvalue()

    # Check header (yellow bullet)
    assert "● coding-sanitizer has run" in rendered

    # Check thinking vs processing vs output generation
    assert "✔ Thought for 3 sec" in rendered
    assert "✔ Processed prompt for 2 sec" in rendered
    assert "✔ Output generated for 2 sec" in rendered

    # Check tool calls
    assert "✔ Successfully called tool read_file (duration 1 sec)" in rendered
    assert "✖ Failed calling tool failing_tool (duration 1 sec)" in rendered

    # Check question block
    assert "✔ Asked question to user" in rendered
    assert "| Question: Which database backend?" in rendered
    assert "|       1. PostgreSQL (Recommended)" in rendered
    assert "|   --> 2. SQLite" in rendered
    assert "|       3. DuckDB" in rendered
    assert "|       4. Custom response" in rendered

    # Intermediate thought process is suppressed per requirement
    assert "Analyzing repository structure" not in rendered

    # Check artifact link (clean clickable label, not raw markdown)
    assert "✔ Generated artifact SANITIZED_USER_REQUEST.md" in rendered

    # Check metrics table
    assert "Turns" in rendered
    assert "Prompt" in rendered
    assert "Cost" in rendered
    assert "(EUR)" in rendered
    assert "€0.004" in rendered
    assert "1,500" in rendered
    assert "350" in rendered
    assert "120" in rendered
    assert "5 sec" in rendered


def test_agent_execution_view_custom_answer():
    """Verify question with custom user answer renders selection indicator properly."""
    view = AgentExecutionView(agent_name="coding-orchestrate")
    view.add_user_question(
        question="What is your desired target?",
        options=["Option A", "Option B"],
        selected_idx=3,
        custom_answer="My custom desired target",
    )
    view.complete()

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=100)
    console.print(view)
    rendered = out.getvalue()

    assert "|   --> 3. Custom response: My custom desired target" in rendered


def test_agent_execution_view_failed():
    """Verify failed status rendering."""
    view = AgentExecutionView(agent_name="failing-agent")
    view.fail(error_message="Fatal crash")

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=100)
    console.print(view)
    rendered = out.getvalue()

    assert "● failing-agent failed" in rendered


def test_node_execution_view_running_and_completed():
    """Verify NodeExecutionView rendering in running and completed states."""
    view = NodeExecutionView(node_name="load_project")
    view.add_file_activity(display_name="./README.md", found=True, abs_path="/path/to/README.md")
    view.set_reading_file("./AGENTS.md")

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=100)
    console.print(view)
    rendered = out.getvalue()

    assert "○ Node load_project is running" in rendered
    assert "✔ Read ./README.md file" in rendered
    assert "○ Reading ./AGENTS.md file" in rendered

    # Now complete the node
    view.add_file_activity(display_name="./AGENTS.md", found=False)
    view.complete()

    out2 = StringIO()
    console2 = Console(file=out2, force_terminal=True, width=100)
    console2.print(view)
    rendered2 = out2.getvalue()

    assert "○ Node load_project has run" in rendered2
    assert "✔ Read ./README.md file" in rendered2
    assert "✖ No ./AGENTS.md file" in rendered2


def test_node_execution_view_failed():
    """Verify NodeExecutionView rendering when failed."""
    view = NodeExecutionView(node_name="load_project")
    view.fail("Unexpected error")

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=100)
    console.print(view)
    rendered = out.getvalue()

    assert "○ Node load_project failed" in rendered


def test_node_execution_view_info_activity():
    """Verify NodeExecutionView rendering with informational activities."""
    view = NodeExecutionView(node_name="init_research_queue")
    view.add_info_activity("Initialized research queue with 3 subjects across 2 topics")
    view.set_active_operation("Preparing episode 1/3")

    out = StringIO()
    console = Console(file=out, force_terminal=True, width=100)
    console.print(view)
    rendered = out.getvalue()

    assert "○ Node init_research_queue is running" in rendered
    assert "✔ Initialized research queue with 3 subjects across 2 topics" in rendered
    assert "○ Preparing episode 1/3" in rendered

    view.complete()
    out2 = StringIO()
    console2 = Console(file=out2, force_terminal=True, width=100)
    console2.print(view)
    rendered2 = out2.getvalue()

    assert "○ Node init_research_queue has run" in rendered2
    assert "✔ Initialized research queue with 3 subjects across 2 topics" in rendered2
