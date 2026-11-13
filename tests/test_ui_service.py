"""Hermetic unit tests for UIService in app/coddy/utils/services/ui_service.py."""

from io import StringIO

from rich.console import Console

from app.coddy.utils.services.ui_service import UIService, get_ui_service, ui_service


def test_ui_service_singleton():
    """Verify UIService singleton and factory function."""
    assert get_ui_service() is ui_service
    assert isinstance(ui_service, UIService)


def test_ui_service_progress_context():
    """Verify progress indicator context manager starts and stops without error."""
    out = StringIO()
    console = Console(file=out, force_terminal=True, width=80)
    service = UIService(console=console)

    with service.progress("Testing progress spinner..."):
        pass

    # Status indicator is transient and stops cleanly
    assert service._active_status is None


def test_ui_service_start_and_stop_progress():
    """Verify start_progress and stop_progress manage active status cleanly."""
    out = StringIO()
    console = Console(file=out, force_terminal=True, width=80)
    service = UIService(console=console)

    status = service.start_progress("Long running task...")
    assert service._active_status is status

    service.stop_progress()
    assert service._active_status is None

    # Safe to call multiple times
    service.stop_progress()
    assert service._active_status is None


def test_ui_service_show_markdown_box():
    """Verify show_markdown_box renders markdown inside a titled box when enabled."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=80)
    service = UIService(console=console, display_markdown=True)

    service.show_markdown_box(
        content="## Subheading\n\nThis is a **markdown** message.",
        title="Sanitized User Request",
        border_style="cyan",
    )

    rendered = out.getvalue()
    assert "Sanitized User Request" in rendered
    assert "Subheading" in rendered
    assert "This is a markdown message" in rendered


def test_ui_service_show_markdown_box_without_title():
    """Verify show_markdown_box renders markdown with no title when enabled."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=80)
    service = UIService(console=console, display_markdown=True)

    service.show_markdown_box(
        content="Simple content without title",
    )

    rendered = out.getvalue()
    assert "Simple content without title" in rendered


def test_ui_service_display_markdown_flag():
    """Verify show_markdown_box suppresses output when display_markdown is False."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=80)
    service = UIService(console=console, display_markdown=False)

    service.show_markdown_box(content="Hidden markdown", title="Hidden Title")
    assert out.getvalue() == ""

    # Force allows rendering even if display_markdown is False
    service.show_markdown_box(content="Forced markdown", title="Forced Title", force=True)
    assert "Forced Title" in out.getvalue()

    # Changing flag dynamically
    service.display_markdown = True
    service.show_markdown_box(content="Now visible", title="Visible Title")
    assert "Visible Title" in out.getvalue()


def test_ui_service_warning():
    """Verify warning renders formatted warning panel."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=80)
    service = UIService(console=console)

    service.warning("Configuration file missing, using defaults", title="Config Warning")

    rendered = out.getvalue()
    assert "Config Warning" in rendered
    assert "Configuration file missing, using defaults" in rendered


def test_ui_service_error_without_trace():
    """Verify error renders red error message to console_err without traceback when show_trace=False."""
    err_out = StringIO()
    console_err = Console(file=err_out, force_terminal=False, width=80)
    service = UIService(console_err=console_err)

    service.error("Invalid database connection string", show_trace=False)

    rendered = err_out.getvalue()
    assert "Error" in rendered
    assert "Invalid database connection string" in rendered
    assert "Traceback" not in rendered


def test_ui_service_error_with_trace():
    """Verify error renders traceback when show_trace=True with an explicit exception."""
    err_out = StringIO()
    console_err = Console(file=err_out, force_terminal=False, width=80)
    service = UIService(console_err=console_err)

    try:
        raise ValueError("Simulated network failure")
    except ValueError as exc:
        service.error("Operation failed", exc=exc, show_trace=True)

    rendered = err_out.getvalue()
    assert "Operation failed" in rendered
    assert "ValueError" in rendered
    assert "Simulated network failure" in rendered


def test_ui_service_show_step_active():
    """Verify show_step renders active step panel with title and description."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=80)
    service = UIService(console=console)

    service.show_step(
        step_number=1,
        total_steps=6,
        title="Sanitization",
        description="Normalizes prompt and analyzes ambiguities",
        is_empty=False,
    )

    rendered = out.getvalue()
    assert "Step 1/6: Sanitization" in rendered
    assert "Normalizes prompt and analyzes ambiguities" in rendered
    assert "Status: Not yet implemented" not in rendered


def test_ui_service_show_step_empty():
    """Verify show_step renders empty step rule without skipped status note."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=80)
    service = UIService(console=console)

    service.show_step(
        step_number=2,
        total_steps=6,
        title="Clarification of Ambiguities",
        description="Resolves ambiguities with the user",
        is_empty=True,
    )

    rendered = out.getvalue()
    assert "Step 2/6: Clarification of Ambiguities" in rendered
    assert "Resolves ambiguities with the user" in rendered
    assert "Status: Not yet implemented" not in rendered


def test_ui_service_agent_view_lifecycle():
    """Verify UIService manages agent view start, sub-events, artifacts, and finish."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=120)
    service = UIService(console=console, display_markdown=True)

    view = service.start_agent_view(agent_name="coding-sanitizer")
    assert service.active_agent_view is view

    service.record_prompt_processing_start(agent_name="coding-sanitizer")
    assert view.active_operation == "processing"

    service.record_prompt_processing_end(agent_name="coding-sanitizer", duration_sec=1.2)
    assert view.active_operation is None
    assert len(view.activities) == 1

    service.record_thinking_start(agent_name="coding-sanitizer", operation="thinking")
    assert view.active_operation == "thinking"

    service.record_thinking_end(agent_name="coding-sanitizer", duration_sec=2.1, reasoning_tokens=50)
    assert view.active_operation is None
    assert len(view.activities) == 2

    service.record_generation_start(agent_name="coding-sanitizer")
    assert view.active_operation == "generating"

    service.record_generation_end(
        agent_name="coding-sanitizer",
        duration_sec=3.5,
        completion_tokens=200,
        tokens_per_sec=57.1,
    )
    assert view.active_operation is None
    assert len(view.activities) == 3

    service.record_tool_start(agent_name="coding-sanitizer", tool_name="read_file")
    assert view.active_operation == "tool:read_file"

    service.record_tool_end(
        agent_name="coding-sanitizer",
        tool_name="read_file",
        status="SUCCESS",
        duration_sec=0.4,
    )
    assert view.active_operation is None
    assert len(view.activities) == 4

    service.record_intermediate_text(agent_name="coding-sanitizer", text="Analyzing code...")
    assert len(view.activities) == 5

    service.record_artifact(agent_name="coding-sanitizer", name="BRIEF.md", path="/tmp/BRIEF.md")
    assert len(view.activities) == 6

    # Queue a markdown box while agent is running
    service.show_markdown_box(content="# Sanitized Request\n\nDetails here", title="SANITIZED_USER_REQUEST.md")

    metrics = {
        "turns": 1,
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "reasoning_tokens": 50,
        "cached_tokens": 0,
        "duration_sec": 3.0,
    }
    service.finish_agent_view(agent_name="coding-sanitizer", metrics=metrics)
    assert service.active_agent_view is None

    rendered = out.getvalue()
    assert "● coding-sanitizer has run" in rendered
    assert "✔ Processed prompt for 1 sec" in rendered
    assert "✔ Thought for 2 sec" in rendered
    assert "✔ Output generated for 4 sec" in rendered
    assert "✔ Successfully called tool read_file (duration 1 sec)" in rendered
    assert "Analyzing code..." not in rendered
    assert "✔ Generated artifact BRIEF.md" in rendered
    assert "1,000" in rendered
    assert "SANITIZED_USER_REQUEST.md" in rendered
    # The markdown box must appear AFTER the metrics table (below the agent step)
    assert rendered.index("1,000") < rendered.index("SANITIZED_USER_REQUEST.md")


def test_ui_service_ask_user(monkeypatch):
    """Verify UIService.ask_user pauses/resumes and records user question/answer."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=120)
    service = UIService(console=console)

    service.start_agent_view(agent_name="test-agent")

    # Simulate choosing option 2
    from rich.prompt import Prompt

    monkeypatch.setattr(Prompt, "ask", lambda *args, **kwargs: "2")

    ans = service.ask_user(
        question="Which architecture?",
        options=["Arch A", "Arch B", "Arch C"],
    )
    assert ans == "Arch B"

    view = service.active_agent_view
    assert view is not None
    assert len(view.activities) == 1

    service.finish_agent_view()
    rendered = out.getvalue()
    assert "✔ Asked question to user" in rendered
    assert "|   --> 2. Arch B" in rendered


def test_ui_service_ask_user_terminal_clearing(monkeypatch):
    """Verify UIService.ask_user in terminal mode pauses live, and clears dialog lines upon answer."""
    out = StringIO()
    console = Console(file=out, force_terminal=True, width=120)
    service = UIService(console=console)

    service.start_agent_view(agent_name="clarifier-agent")
    assert service._active_live is not None

    from rich.prompt import Prompt

    monkeypatch.setattr(Prompt, "ask", lambda *args, **kwargs: "1")

    ans = service.ask_user(
        question="Which performance aspect?",
        options=["Latency", "Throughput"],
    )
    assert ans == "Latency"

    # Terminal output should contain the ANSI cursor up and erase line sequences
    raw_output = out.getvalue()
    assert "\x1b[A\x1b[2K" in raw_output

    view = service.active_agent_view
    assert view is not None
    assert len(view.activities) == 1

    service.finish_agent_view()


def test_ui_service_node_view_lifecycle():
    """Verify UIService correctly manages node view lifecycle and outputs expected format."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=120)
    service = UIService(console=console)

    view = service.start_node_view("load_project")
    assert service.active_node_view is view

    service.record_node_reading_file("./README.md")
    service.record_node_file_result(display_name="./README.md", found=True, abs_path="/workspace/README.md")
    service.record_node_reading_file("./AGENTS.md")
    service.record_node_file_result(display_name="./AGENTS.md", found=False)

    service.finish_node_view()
    assert service.active_node_view is None

    rendered = out.getvalue()
    assert "○ Node load_project has run" in rendered
    assert "✔ Read ./README.md file" in rendered
    assert "✖ No ./AGENTS.md file" in rendered


def test_ui_service_node_view_conversion_activity():
    """Verify UIService correctly records and renders conversion activities."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=120)
    service = UIService(console=console)

    view = service.start_node_view("load_research_material")
    assert service.active_node_view is view

    service.record_node_reading_file("../researches/GraphRAG.html")
    service.record_node_file_result(
        display_name="../researches/GraphRAG.html",
        found=True,
        abs_path="/researches/GraphRAG.html",
    )
    service.record_node_converting_file("GraphRAG.html", "GraphRAG.md")
    service.record_node_conversion_result(
        display_name="GraphRAG.html",
        target_name="GraphRAG.md",
        abs_path="/artifacts/research_materials/GraphRAG.html",
        target_path="/artifacts/research_materials/GraphRAG.md",
    )

    service.finish_node_view()
    assert service.active_node_view is None

    rendered = out.getvalue()
    assert "○ Node load_research_material has run" in rendered
    assert "✔ Read ../researches/GraphRAG.html file" in rendered
    assert "✔ Converted GraphRAG.html -> GraphRAG.md" in rendered


def test_ui_service_node_view_info_activity():
    """Verify UIService correctly records and renders generic node activities."""
    out = StringIO()
    console = Console(file=out, force_terminal=False, width=120)
    service = UIService(console=console)

    view = service.start_node_view("verify_remaining_research")
    assert service.active_node_view is view

    service.record_node_active_operation("Evaluating queue status...")
    assert view.active_operation == "Evaluating queue status..."

    service.record_node_activity("2 research subject(s) remaining in queue -> routing to 'loop_research'")
    assert view.active_operation is None

    service.finish_node_view()
    assert service.active_node_view is None

    rendered = out.getvalue()
    assert "○ Node verify_remaining_research has run" in rendered
    assert "✔ 2 research subject(s) remaining in queue -> routing to 'loop_research'" in rendered
