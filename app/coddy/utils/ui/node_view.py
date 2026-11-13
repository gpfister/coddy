"""Rich UI elements and renderables for workflow node execution views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.console import Group, RenderableType
from rich.markup import escape
from rich.text import Text


@dataclass
class NodeFileActivity:
    """Represents a file check/read or conversion result within a workflow node."""

    display_name: str  # e.g. "./README.md"
    found: bool  # True if read successfully, False if absent
    abs_path: str | None = None  # Absolute path for link if found
    action: Literal["read", "converted", "info"] = "read"
    target_name: str | None = None  # e.g. "GraphRAG.md" for conversion
    target_path: str | None = None  # Absolute path for target link if converted


class NodeExecutionView:
    """Rich renderable managing live and completed views of workflow node execution."""

    def __init__(self, node_name: str) -> None:
        self.node_name = node_name
        self.status: Literal["running", "completed", "failed"] = "running"
        self.activities: list[NodeFileActivity] = []
        self.active_operation: str | None = None

    def add_file_activity(self, display_name: str, found: bool, abs_path: str | None = None) -> None:
        """Records a file reading result."""
        self.activities.append(
            NodeFileActivity(display_name=display_name, found=found, abs_path=abs_path, action="read")
        )

    def add_conversion_activity(
        self,
        display_name: str,
        target_name: str,
        abs_path: str | None = None,
        target_path: str | None = None,
    ) -> None:
        """Records a file conversion result."""
        self.activities.append(
            NodeFileActivity(
                display_name=display_name,
                found=True,
                abs_path=abs_path,
                action="converted",
                target_name=target_name,
                target_path=target_path,
            )
        )

    def add_info_activity(self, message: str) -> None:
        """Records an informational activity message in the node view."""
        self.activities.append(
            NodeFileActivity(
                display_name=message,
                found=True,
                action="info",
            )
        )

    def set_active_operation(self, op: str | None) -> None:
        """Sets the currently active operation (e.g. 'Reading ./AGENTS.md file')."""
        self.active_operation = op

    def set_reading_file(self, display_name: str) -> None:
        """Sets active operation to reading a specific file."""
        self.active_operation = f"Reading [bold]{escape(display_name)}[/bold] file"

    def set_converting_file(self, display_name: str, target_name: str = "") -> None:
        """Sets active operation to converting a specific file."""
        if target_name:
            self.active_operation = (
                f"Converting [bold]{escape(display_name)}[/bold] -> [bold]{escape(target_name)}[/bold]"
            )
        else:
            self.active_operation = f"Converting [bold]{escape(display_name)}[/bold]"

    def complete(self) -> None:
        """Marks the node view as completed."""
        self.status = "completed"
        self.active_operation = None

    def fail(self, error_message: str | None = None) -> None:
        """Marks the node view as failed."""
        self.status = "failed"
        self.active_operation = None

    def __rich__(self) -> RenderableType:
        renderables: list[RenderableType] = []

        # 1. Header
        if self.status == "running":
            renderables.append(
                Text.from_markup(f"[bold yellow]○[/bold yellow] Node [bold]{escape(self.node_name)}[/bold] is running")
            )
        elif self.status == "completed":
            renderables.append(
                Text.from_markup(f"[bold yellow]○[/bold yellow] Node [bold]{escape(self.node_name)}[/bold] has run")
            )
        else:
            renderables.append(
                Text.from_markup(f"[bold red]○[/bold red] Node [bold]{escape(self.node_name)}[/bold] failed")
            )

        # 2. File and Node Activity Items
        for item in self.activities:
            if item.action == "info":
                try:
                    renderables.append(Text.from_markup(f"  [bold green]✔[/bold green] {item.display_name}"))
                except Exception:
                    renderables.append(Text.from_markup(f"  [bold green]✔[/bold green] {escape(item.display_name)}"))
            elif item.action == "converted":
                if item.abs_path:
                    orig_link = f"[bold cyan underline link=file://{escape(item.abs_path)}]{escape(item.display_name)}[/bold cyan underline link]"
                else:
                    orig_link = f"[bold]{escape(item.display_name)}[/bold]"

                target_name = item.target_name or ""
                if item.target_path:
                    target_link = f"[bold cyan underline link=file://{escape(item.target_path)}]{escape(target_name)}[/bold cyan underline link]"
                else:
                    target_link = f"[bold]{escape(target_name)}[/bold]"

                renderables.append(
                    Text.from_markup(f"  [bold green]✔[/bold green] Converted {orig_link} -> {target_link}")
                )
            elif item.found:
                if item.abs_path:
                    link_markup = f"[bold cyan underline link=file://{escape(item.abs_path)}]{escape(item.display_name)}[/bold cyan underline link]"
                else:
                    link_markup = f"[bold]{escape(item.display_name)}[/bold]"
                renderables.append(Text.from_markup(f"  [bold green]✔[/bold green] Read {link_markup} file"))
            else:
                renderables.append(
                    Text.from_markup(f"  [bold red]✖[/bold red] No [bold]{escape(item.display_name)}[/bold] file")
                )

        # 3. Active in-progress operation
        if self.status == "running" and self.active_operation:
            renderables.append(Text.from_markup(f"  [bold yellow]○[/bold yellow] {self.active_operation}"))

        return Group(*renderables)
