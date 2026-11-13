"""CLI code command implementation and terminal interactive interview/approval gates."""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from app.coddy.agentic import CodingOrchestratorWorkflow
from app.coddy.helpers.env_helpers import load_environment
from app.coddy.helpers.logging_helpers import configure_logging
from app.coddy.utils.services import get_ui_service

load_environment()
configure_logging()

console = Console()
console_err = Console(stderr=True)


def terminal_ask_user(question: str, options: list[str] | None = None) -> str:
    """Prompts the user interactively in the terminal for clarification with multiple choice options."""
    return get_ui_service().ask_user(question=question, options=options)


def terminal_approval_gate(gate_name: str, markdown_content: str) -> tuple[bool, str, str | None]:
    """Interactive human approval gate (Rule R4)."""
    console.print()
    console.print(Panel(f"[bold cyan]{gate_name}[/bold cyan]", title_align="left", border_style="cyan"))
    console.print(Markdown(markdown_content))
    console.print()

    console.print("[bold yellow]Human Gate - Select Decision:[/bold yellow]")
    console.print("  [1] Approve and proceed (Recommended)")
    console.print("  [2] Reject with Minor Tweak (Loop back to current phase)")
    console.print("  [3] Reject with Scope Change (Loop back to clarify phase)")
    console.print("  [4] Abort workflow")

    choice = Prompt.ask("Decision", choices=["1", "2", "3", "4"], default="1")

    if choice == "1":
        return True, "approve", None
    elif choice == "2":
        feedback = Prompt.ask("[bold yellow]Enter minor tweak feedback[/bold yellow]")
        return False, "minor_tweak", feedback
    elif choice == "3":
        feedback = Prompt.ask("[bold yellow]Enter scope change feedback[/bold yellow]")
        return False, "scope_change", feedback
    else:
        console.print("[red]Workflow aborted by user.[/red]")
        sys.exit(0)


def code_cmd(
    prompt: str = typer.Argument(
        ...,
        help="Prompt description or '-' to read from standard input.",
    ),
    auto_approve: bool = typer.Option(False, "--yes", "-y", help="Automatically approve human review gates."),
    display_markdown: bool = typer.Option(
        False,
        "--display-markdown/--no-display-markdown",
        help="Display markdown boxes on the console.",
    ),
    research_material_file: list[Path] | None = typer.Option(
        None,
        "--research-material-file",
        "-r",
        help="Path to research material file(s) (text, Markdown, PDF, Office docs, images). May be specified multiple times.",
    ),
) -> None:
    """Run the coding-orchestrate workflow on a user prompt or piped input."""
    raw_input = prompt
    if prompt == "-" or not sys.stdin.isatty() and not prompt.strip():
        raw_input = sys.stdin.read().strip()

    if not raw_input.strip():
        console_err.print("[bold red]Error:[/bold red] No prompt provided.")
        raise typer.Exit(code=1)

    if research_material_file:
        for p in research_material_file:
            resolved_p = p.resolve()
            if not resolved_p.is_file():
                console_err.print(f"[bold red]Error:[/bold red] Research material file not found: {p}")
                raise typer.Exit(code=1)

    if auto_approve:
        console.print("[bold yellow]Info:[/bold yellow] Auto-approve mode enabled.")

    ui = get_ui_service()
    ui.display_markdown = display_markdown
    ui.auto_approve = auto_approve

    start_kwargs = {}
    if research_material_file:
        start_kwargs["research_material_paths"] = research_material_file

    coding_orchestrate_workflow = CodingOrchestratorWorkflow()
    asyncio.run(coding_orchestrate_workflow.start(raw_input, **start_kwargs))
