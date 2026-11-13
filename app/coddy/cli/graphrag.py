"""CLI graphrag command and subcommands (ingest, status)."""

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from app.coddy.graphrag.services.cache_service import (
    get_cache_dir,
    get_git_commit_sha,
    has_cached_graphrag,
    is_git_dirty,
)
from app.coddy.graphrag.services.graphrag_service import GraphRAGService

console = Console()
console_err = Console(stderr=True)

graphrag_app = typer.Typer(
    name="graphrag",
    help="Manage GraphRAG cache, status, and ingestion.",
    add_completion=False,
)


def ensure_graphrag_initialized(
    repo_dir: Path = Path("."),
    force_reingest: bool = False,
    auto_approve: bool = False,
    quiet: bool = False,
    session_logger: Any | None = None,
) -> GraphRAGService:
    """Ensures GraphRAG service is ready: checks .cache/graphrag/<commit_sha>/, reloads or ingests."""
    service = GraphRAGService()
    commit_sha = service.cache_service.get_git_commit_sha(repo_dir)
    dirty = service.cache_service.is_git_dirty(repo_dir)
    cached = service.cache_service.has_cached_graphrag(commit_sha)

    reingest = force_reingest or not cached

    if cached and not force_reingest and dirty:
        if not auto_approve and not quiet:
            choice = Prompt.ask(
                "[bold yellow]Git working tree has uncommitted modifications. Re-run GraphRAG ingestion?[/bold yellow] [y/N]",
                default="N",
            )
            if choice.strip().lower() in ("y", "yes"):
                reingest = True

    if reingest:
        with console.status(
            f"[bold cyan]Running GraphRAG ingestion for commit {commit_sha[:8]}...[/bold cyan]",
            spinner="dots",
        ) as status:

            def on_progress(msg: str):
                status.update(f"[bold cyan]{msg}[/bold cyan]")

            stats = service.run_ingestion_pipeline(
                repo_dir=repo_dir,
                commit_sha=commit_sha,
                progress_callback=on_progress,
            )
        if not quiet:
            console.print(
                f"[green]✓[/green] GraphRAG ingested & cached for [bold cyan]{commit_sha[:8]}[/bold cyan] "
                f"({stats.nodes} nodes, {stats.edges} edges, {stats.chunks} doc chunks, {stats.facts} facts)"
            )
    else:
        with console.status(
            f"[bold cyan]Loading GraphRAG cache for commit {commit_sha[:8]}...[/bold cyan]",
            spinner="dots",
        ):
            loaded = service.load_cache(commit_sha)
            if not loaded:
                stats = service.run_ingestion_pipeline(
                    repo_dir=repo_dir,
                    commit_sha=commit_sha,
                )
                if not quiet:
                    console.print(
                        f"[green]✓[/green] GraphRAG ingested & cached for [bold cyan]{commit_sha[:8]}[/bold cyan]"
                    )
                return service

        stats = service.get_stats()
        if not quiet:
            console.print(
                f"[green]✓[/green] GraphRAG loaded from cache for [bold cyan]{commit_sha[:8]}[/bold cyan] "
                f"({stats.nodes} nodes, {stats.edges} edges, {stats.chunks} doc chunks, {stats.facts} facts)"
            )

    return service


@graphrag_app.command("ingest")
def graphrag_ingest_cmd(
    repo_dir: Path = typer.Option(Path("."), "--repo-dir", "-d", help="Target repository directory"),
) -> None:
    """Force re-ingestion of codebase AST, docs, and intents into GraphRAG cache."""
    commit_sha = get_git_commit_sha(repo_dir)
    ensure_graphrag_initialized(repo_dir=repo_dir, force_reingest=True)
    cache_dir = get_cache_dir(commit_sha)
    console.print(
        Panel(
            f"[bold green]GraphRAG Ingestion Complete[/bold green]\n\n"
            f"Commit SHA:    [bold cyan]{commit_sha}[/bold cyan]\n"
            f"Graph Cache:   [cyan]{cache_dir / 'graph.json'}[/cyan]\n"
            f"Vectors Cache: [cyan]{cache_dir / 'vectors.json'}[/cyan]",
            border_style="green",
        )
    )


@graphrag_app.command("status")
def graphrag_status_cmd(
    repo_dir: Path = typer.Option(Path("."), "--repo-dir", "-d", help="Target repository directory"),
) -> None:
    """Display current GraphRAG cache status, git commit SHA, and entity statistics."""
    commit_sha = get_git_commit_sha(repo_dir)
    dirty = is_git_dirty(repo_dir)
    cached = has_cached_graphrag(commit_sha)
    cache_dir = get_cache_dir(commit_sha)

    status_str = "[bold green]Cached[/bold green]" if cached else "[bold red]Missing (Ingestion required)[/bold red]"
    dirty_str = "[bold yellow]Yes (uncommitted modifications)[/bold yellow]" if dirty else "[green]No (clean)[/green]"

    stats_str = ""
    if cached:
        try:
            g_data = json.loads((cache_dir / "graph.json").read_text(encoding="utf-8"))
            v_data = json.loads((cache_dir / "vectors.json").read_text(encoding="utf-8"))
            n_count = len(g_data.get("nodes", []))
            e_count = len(g_data.get("edges", []))
            colls = v_data.get("collections", {})
            chunks_count = len(colls.get("DocChunk", []))
            facts_count = len(colls.get("Fact", []))
            stats_str = (
                f"\n\n[bold]In-Memory Entity Counts:[/bold]\n"
                f"  - Graph Nodes:             [cyan]{n_count}[/cyan]\n"
                f"  - Graph Edges:             [cyan]{e_count}[/cyan]\n"
                f"  - Vectorized Doc Chunks:   [cyan]{chunks_count}[/cyan]\n"
                f"  - Vectorized Facts/Intents:[cyan]{facts_count}[/cyan]"
            )
        except Exception:
            pass

    console.print(
        Panel(
            f"[bold cyan]GraphRAG Cache Status[/bold cyan]\n\n"
            f"Repository:   [cyan]{repo_dir.resolve()}[/cyan]\n"
            f"Commit SHA:   [bold cyan]{commit_sha}[/bold cyan]\n"
            f"Tree Dirty:   {dirty_str}\n"
            f"Cache Status: {status_str}\n"
            f"Cache Folder: [cyan]{cache_dir}[/cyan]"
            f"{stats_str}",
            border_style="cyan",
        )
    )
