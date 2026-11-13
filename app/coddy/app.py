"""Command-line interface and application entrypoint for Coddy."""

import json

import typer
from rich.console import Console

from app.coddy.cli.code import code_cmd
from app.coddy.cli.graphrag import graphrag_app
from app.coddy.cli.metrics import metrics_app
from app.coddy.helpers.env_helpers import load_environment
from app.coddy.helpers.logging_helpers import configure_logging

# Load environment variables from .env files and normalize credentials
load_environment()

configure_logging()

app = typer.Typer(
    name="coddy",
    help="Coddy: Professional Recursive Task Decomposition (RTD) CLI",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()
console_err = Console(stderr=True)

# Register sub-commands and sub-apps
app.command(name="code")(code_cmd)
app.add_typer(graphrag_app, name="graphrag")
app.add_typer(metrics_app, name="metrics")


@app.callback(invoke_without_command=True)
def main_entry(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show Coddy version"),
):
    """Coddy: Professional Recursive Task Decomposition (RTD) CLI."""
    if version:
        console.print("[bold green]Coddy[/bold green] version [bold cyan]0.1.0[/bold cyan] (RTD Engine)")
        raise typer.Exit()

    if ctx.invoked_subcommand is not None:
        return

    console.print(ctx.get_help())
    raise typer.Exit()


@app.command("schemas")
def dump_schemas():
    """Print the JSON schemas for Specification, Plan, Sanitization, and Research Plan."""
    from app.coddy.agentic.schemas.enhanced_user_request import EnhancedUserRequest
    from app.coddy.agentic.schemas.plan import Plan
    from app.coddy.agentic.schemas.research_plan import ResearchPlan
    from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest
    from app.coddy.agentic.schemas.specification import Specification

    console.print("[bold cyan]=== SPECIFICATION SCHEMA ===[/bold cyan]")
    print(json.dumps(Specification.model_json_schema(), indent=2))
    console.print("\n[bold cyan]=== PLAN SCHEMA ===[/bold cyan]")
    print(json.dumps(Plan.model_json_schema(), indent=2))
    console.print("\n[bold cyan]=== SANITIZATION SCHEMA ===[/bold cyan]")
    print(json.dumps(SanitizedUserRequest.model_json_schema(), indent=2))
    console.print("\n[bold cyan]=== ENHANCED USER REQUEST SCHEMA ===[/bold cyan]")
    print(json.dumps(EnhancedUserRequest.model_json_schema(), indent=2))
    console.print("\n[bold cyan]=== RESEARCH PLAN SCHEMA ===[/bold cyan]")
    print(json.dumps(ResearchPlan.model_json_schema(), indent=2))


def main():
    """CLI script entrypoint for pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
