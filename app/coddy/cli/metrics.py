"""CLI commands for inspecting DuckDB execution and token metrics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import duckdb
import typer
from rich.box import ROUNDED
from rich.console import Console
from rich.table import Table

from app.coddy.agentic.services.metrics_service import get_metrics_service
from app.coddy.agentic.services.pricing_service import format_cost_eur

metrics_app = typer.Typer(
    name="metrics",
    help="Inspect execution metrics, token usage, and performance stats in DuckDB (~/.coddy/metrics.db).",
    add_completion=False,
)
console = Console()


@contextmanager
def safe_metrics_access() -> Iterator[None]:
    """Catches DuckDB IO and lock errors to provide diagnostic output instead of stack traces."""
    try:
        yield
    except duckdb.IOException as exc:
        console.print(
            f"[bold red]Metrics Database Error:[/bold red] ~/.coddy/metrics.db could not be accessed.\n[yellow]{exc}[/yellow]"
        )
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Metrics Error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@metrics_app.command(name="summary")
def metrics_summary_cmd(
    session_id: str | None = typer.Option(None, "--session-id", "-s", help="Filter summary to specific session ID"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum rows to display"),
) -> None:
    """Displays high-level performance metrics for models, agents, and overall sessions."""
    with safe_metrics_access():
        ms = get_metrics_service()

        if session_id:
            ms.display_session_summary(session_id, console=console)
            return

        # Model Performance Table
        model_rows = ms.get_model_performance()
    if model_rows:
        model_table = Table(title="Model Performance Overview", box=ROUNDED, header_style="bold magenta")
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Calls", justify="right")
        model_table.add_column("Avg Latency", justify="right")
        model_table.add_column("Avg TTFT", justify="right")
        model_table.add_column("Avg Tok/Sec", justify="right")
        model_table.add_column("Prompt Tokens", justify="right")
        model_table.add_column("Completion", justify="right")
        model_table.add_column("Reasoning", justify="right")
        model_table.add_column("Total Tokens", justify="right", style="bold")
        model_table.add_column("Cost (EUR)", justify="right", style="bold yellow")

        for m in model_rows:
            dur_str = f"{m['avg_duration_ms'] / 1000.0:.2f}s" if m.get("avg_duration_ms") else "-"
            ttft_str = f"{m['avg_ttft_ms'] / 1000.0:.2f}s" if m.get("avg_ttft_ms") else "-"
            tps_str = f"{m['avg_tokens_per_sec']:.1f}" if m.get("avg_tokens_per_sec") else "-"
            cost_str = format_cost_eur(m.get("total_cost_eur") or 0.0)
            model_table.add_row(
                m.get("model_name") or "-",
                str(m.get("total_calls", 0)),
                dur_str,
                ttft_str,
                tps_str,
                str(m.get("total_prompt_tokens", 0)),
                str(m.get("total_completion_tokens", 0)),
                str(m.get("total_reasoning_tokens", 0)),
                str(m.get("grand_total_tokens", 0)),
                cost_str,
            )
        console.print(model_table)
        console.print()

    # Agent Performance Table
    agent_rows = ms.get_agent_performance()
    if agent_rows:
        agent_table = Table(title="Agent Performance Overview", box=ROUNDED, header_style="bold green")
        agent_table.add_column("Agent", style="green")
        agent_table.add_column("Steps", justify="right")
        agent_table.add_column("Avg Latency", justify="right")
        agent_table.add_column("Prompt Tokens", justify="right")
        agent_table.add_column("Completion", justify="right")
        agent_table.add_column("Reasoning", justify="right")
        agent_table.add_column("Total Tokens", justify="right", style="bold")

        for a in agent_rows:
            dur_str = f"{a['avg_duration_ms'] / 1000.0:.2f}s" if a.get("avg_duration_ms") else "-"
            agent_table.add_row(
                a.get("agent_name") or "-",
                str(a.get("total_steps", 0)),
                dur_str,
                str(a.get("total_prompt_tokens", 0)),
                str(a.get("total_completion_tokens", 0)),
                str(a.get("total_reasoning_tokens", 0)),
                str(a.get("grand_total_tokens", 0)),
            )
        console.print(agent_table)
        console.print()

    # Recent Sessions Table
    sessions = ms.get_session_summary(limit=limit)
    if sessions:
        sess_table = Table(title="Recent Sessions Summary", box=ROUNDED, header_style="bold blue")
        sess_table.add_column("Session ID", style="cyan")
        sess_table.add_column("Duration", justify="right")
        sess_table.add_column("Steps", justify="right")
        sess_table.add_column("Tools", justify="right")
        sess_table.add_column("Tokens (P / C / R)", justify="right")
        sess_table.add_column("Total Tokens", justify="right", style="bold")
        sess_table.add_column("Cost (EUR)", justify="right", style="bold yellow")
        sess_table.add_column("Status", justify="center")

        for s in sessions:
            dur_str = f"{s.get('duration_ms', 0) / 1000.0:.2f}s" if s.get("duration_ms") else "-"
            tok_split = (
                f"{s.get('prompt_tokens', 0)} / {s.get('completion_tokens', 0)} / {s.get('reasoning_tokens', 0)}"
            )
            status_style = (
                "[green]COMPLETED[/green]" if s.get("status") == "COMPLETED" else f"[yellow]{s.get('status')}[/yellow]"
            )
            cost_str = format_cost_eur(s.get("total_cost_eur") or 0.0)
            sess_table.add_row(
                s.get("session_id") or "-",
                dur_str,
                str(s.get("step_count", 0)),
                str(s.get("total_tool_calls", 0)),
                tok_split,
                str(s.get("total_tokens", 0)),
                cost_str,
                status_style,
            )
        console.print(sess_table)
    elif not model_rows and not agent_rows:
        console.print("[dim]No metrics recorded yet in ~/.coddy/metrics.db[/dim]")


@metrics_app.command(name="sessions")
def metrics_sessions_cmd(
    session_id: str | None = typer.Option(None, "--session-id", "-s", help="Inspect specific session details"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum sessions to list"),
) -> None:
    """Lists detailed session execution records or inspects a specific session."""
    with safe_metrics_access():
        ms = get_metrics_service()

        if session_id:
            ms.display_session_summary(session_id, console=console)
            return

        sessions = ms.get_session_summary(limit=limit)
        if not sessions:
            console.print("[dim]No session metrics recorded yet.[/dim]")
            return

        table = Table(title="Session Records", box=ROUNDED, header_style="bold cyan")
        table.add_column("Session ID", style="cyan")
        table.add_column("Started", style="dim")
        table.add_column("Duration", justify="right")
        table.add_column("Steps", justify="right")
        table.add_column("Tools", justify="right")
        table.add_column("Total Tokens", justify="right", style="bold")
        table.add_column("Status", justify="center")

        for s in sessions:
            dur_str = f"{s.get('duration_ms', 0) / 1000.0:.2f}s" if s.get("duration_ms") else "-"
            st_val = s.get("start_time")
            st_str = st_val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(st_val, "strftime") else str(st_val or "-")
            status_style = (
                "[green]COMPLETED[/green]" if s.get("status") == "COMPLETED" else f"[yellow]{s.get('status')}[/yellow]"
            )

            table.add_row(
                s.get("session_id") or "-",
                st_str,
                dur_str,
                str(s.get("step_count", 0)),
                str(s.get("total_tool_calls", 0)),
                str(s.get("total_tokens", 0)),
                status_style,
            )

        console.print(table)


@metrics_app.command(name="tools")
def metrics_tools_cmd(
    session_id: str | None = typer.Option(None, "--session-id", "-s", help="Filter tool calls to specific session"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum tool rows to list"),
) -> None:
    """Inspects tool invocations and performance metrics."""
    with safe_metrics_access():
        ms = get_metrics_service()

        if session_id:
            tools = ms.get_session_tools(session_id)
            if not tools:
                console.print(f"[dim]No tool invocations recorded for session: {session_id}[/dim]")
                return

            table = Table(title=f"Tool Invocations for Session: {session_id}", box=ROUNDED, header_style="bold yellow")
            table.add_column("Agent", style="cyan")
            table.add_column("Tool", style="yellow")
            table.add_column("Duration", justify="right")
            table.add_column("Truncated", justify="center")
            table.add_column("Status", justify="center")
            table.add_column("Args Summary", style="dim")

            for t in tools[:limit]:
                dur_str = f"{t.get('duration_ms', 0) / 1000.0:.2f}s" if t.get("duration_ms") else "-"
                status_style = "[green]OK[/green]" if t.get("status") == "SUCCESS" else "[red]FAIL[/red]"
                trunc_style = "[yellow]YES[/yellow]" if t.get("is_truncated") else "NO"
                args_snip = (t.get("tool_args") or "")[:60].replace("\n", " ")

                table.add_row(
                    t.get("agent_name") or "-",
                    t.get("tool_name") or "-",
                    dur_str,
                    trunc_style,
                    status_style,
                    args_snip,
                )
            console.print(table)
            return

        # Aggregate tool usage overview
        usage = ms.get_tool_usage(limit=limit)
        if not usage:
            console.print("[dim]No tool metrics recorded yet.[/dim]")
            return

        table = Table(title="Aggregate Tool Usage Overview", box=ROUNDED, header_style="bold yellow")
        table.add_column("Tool Name", style="yellow")
        table.add_column("Invocations", justify="right")
        table.add_column("Avg Latency", justify="right")
        table.add_column("Failures", justify="right")
        table.add_column("Truncated Calls", justify="right")

        for u in usage:
            dur_str = f"{u.get('avg_duration_ms', 0) / 1000.0:.2f}s" if u.get("avg_duration_ms") else "-"
            table.add_row(
                u.get("tool_name") or "-",
                str(u.get("total_invocations", 0)),
                dur_str,
                str(u.get("failed_invocations", 0)),
                str(u.get("truncated_invocations", 0)),
            )

        console.print(table)
