"""Console UI service providing styled Rich console output, progress indicators, and panels."""

import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status
from rich.text import Text
from rich.traceback import Traceback

from app.coddy.utils.ui.agent_view import AgentExecutionView, AgentMetrics
from app.coddy.utils.ui.node_view import NodeExecutionView

logger = logging.getLogger(__name__)


class UIService:
    """Manages terminal UI output including disappearing progress indicators, markdown panels, and diagnostics."""

    def __init__(
        self,
        console: Console | None = None,
        console_err: Console | None = None,
        display_markdown: bool = False,
        auto_approve: bool = False,
    ) -> None:
        self._console = console or Console()
        self._console_err = console_err or Console(stderr=True)
        self._active_status: Status | None = None
        self._display_markdown: bool = display_markdown
        self._auto_approve: bool = auto_approve
        self._active_agent_view: AgentExecutionView | None = None
        self._active_node_view: NodeExecutionView | None = None
        self._active_live: Live | None = None
        self._pending_markdown_boxes: list[dict[str, Any]] = []

    @property
    def auto_approve(self) -> bool:
        """Whether to automatically approve human review gates and choices."""
        return self._auto_approve

    @auto_approve.setter
    def auto_approve(self, value: bool) -> None:
        """Sets whether to automatically approve human review gates and choices."""
        self._auto_approve = bool(value)

    @property
    def display_markdown(self) -> bool:
        """Whether to display markdown boxes on the console."""
        return self._display_markdown

    @display_markdown.setter
    def display_markdown(self, value: bool) -> None:
        """Sets whether to display markdown boxes on the console."""
        self._display_markdown = bool(value)

    @property
    def console(self) -> Console:
        """Returns the active standard output Rich console."""
        return self._console

    @property
    def console_err(self) -> Console:
        """Returns the active standard error Rich console."""
        return self._console_err

    @contextmanager
    def progress(self, description: str = "Processing...", spinner: str = "dots") -> Generator[Status, None, None]:
        """Context manager displaying a transient progress spinner that disappears when terminated."""
        status = self._console.status(description, spinner=spinner)
        try:
            status.start()
            yield status
        finally:
            status.stop()

    def start_progress(self, description: str = "Processing...", spinner: str = "dots") -> Status:
        """Starts a transient progress indicator that can be stopped via stop_progress()."""
        if self._active_status is not None:
            self.stop_progress()
        self._active_status = self._console.status(description, spinner=spinner)
        self._active_status.start()
        return self._active_status

    def stop_progress(self) -> None:
        """Stops and clears the currently active progress indicator."""
        if self._active_status is not None:
            try:
                self._active_status.stop()
            except Exception as e:
                logger.debug("Error while stopping status spinner: %s", e)
            finally:
                self._active_status = None

    @property
    def active_agent_view(self) -> AgentExecutionView | None:
        """Returns the currently active AgentExecutionView, if any."""
        return self._active_agent_view

    @property
    def active_node_view(self) -> NodeExecutionView | None:
        """Returns the currently active NodeExecutionView, if any."""
        return self._active_node_view

    def start_agent_view(self, agent_name: str) -> AgentExecutionView:
        """Initializes and starts a live AgentExecutionView display."""
        if self._active_node_view is not None:
            self.finish_node_view()
        if self._active_agent_view is not None:
            self.finish_agent_view()

        # Ensure any leftover progress status is stopped
        self.stop_progress()
        self._pending_markdown_boxes.clear()

        view = AgentExecutionView(agent_name=agent_name)
        self._active_agent_view = view

        if self._console.is_terminal:
            self._active_live = Live(
                view,
                console=self._console,
                refresh_per_second=10,
                transient=False,
            )
            self._active_live.start()

        return view

    def _refresh_live(self) -> None:
        """Refreshes the live display if active."""
        if self._active_live is not None:
            target = self._active_agent_view or self._active_node_view
            if target is not None:
                try:
                    self._active_live.update(target)
                except Exception as e:
                    logger.debug("Failed refreshing live display: %s", e)

    def record_prompt_processing_start(self, agent_name: str | None = None) -> None:
        """Records the start of LLM prompt processing."""
        if self._active_agent_view is not None:
            self._active_agent_view.set_active_operation("processing")
            self._refresh_live()

    def record_prompt_processing_end(
        self,
        agent_name: str | None = None,
        duration_sec: float = 0.0,
    ) -> None:
        """Records the completion of LLM prompt processing (TTFT)."""
        if self._active_agent_view is not None:
            self._active_agent_view.add_prompt_processing(duration_sec=duration_sec)
            self._active_agent_view.set_active_operation(None)
            self._refresh_live()

    def record_thinking_start(self, agent_name: str | None = None, operation: str = "thinking") -> None:
        """Records the start of an LLM turn ('thinking' or 'processing')."""
        if self._active_agent_view is not None:
            self._active_agent_view.set_active_operation(operation)
            self._refresh_live()

    def record_thinking_end(
        self,
        agent_name: str | None = None,
        duration_sec: float = 0.0,
        reasoning_tokens: int = 0,
    ) -> None:
        """Records the completion of an LLM turn."""
        if self._active_agent_view is not None:
            self._active_agent_view.add_thinking(duration_sec=duration_sec, reasoning_tokens=reasoning_tokens)
            self._active_agent_view.set_active_operation(None)
            self._refresh_live()

    def record_generation_start(self, agent_name: str | None = None) -> None:
        """Records the start of LLM output generation."""
        if self._active_agent_view is not None:
            self._active_agent_view.set_active_operation("generating")
            self._refresh_live()

    def record_generation_end(
        self,
        agent_name: str | None = None,
        duration_sec: float = 0.0,
        completion_tokens: int = 0,
        tokens_per_sec: float | None = None,
    ) -> None:
        """Records the completion of LLM output generation."""
        if self._active_agent_view is not None:
            self._active_agent_view.add_output_generation(
                duration_sec=duration_sec,
                completion_tokens=completion_tokens,
                tokens_per_sec=tokens_per_sec,
            )
            self._active_agent_view.set_active_operation(None)
            self._refresh_live()

    def record_tool_start(self, agent_name: str | None = None, tool_name: str = "") -> None:
        """Records the start of a tool call."""
        if self._active_agent_view is not None:
            self._active_agent_view.set_active_operation(f"tool:{tool_name}")
            self._refresh_live()

    def record_tool_end(
        self,
        agent_name: str | None = None,
        tool_name: str = "",
        status: str = "SUCCESS",
        duration_sec: float = 0.0,
        error_message: str | None = None,
    ) -> None:
        """Records the completion or failure of a tool call."""
        if self._active_agent_view is not None:
            self._active_agent_view.add_tool_call(
                tool_name=tool_name,
                status=status,
                duration_sec=duration_sec,
                error_message=error_message,
            )
            self._active_agent_view.set_active_operation(None)
            self._refresh_live()

    def record_intermediate_text(self, agent_name: str | None = None, text: str = "") -> None:
        """Records intermediate explanatory text generated by the agent."""
        if self._active_agent_view is not None and text.strip():
            self._active_agent_view.add_intermediate_text(text=text.strip())
            self._refresh_live()

    def record_artifact(self, agent_name: str | None = None, name: str = "", path: str = "") -> None:
        """Records an artifact produced by the agent."""
        if self._active_agent_view is not None:
            self._active_agent_view.add_artifact(name=name, path=path)
            self._refresh_live()

    def finish_agent_view(
        self,
        agent_name: str | None = None,
        metrics: AgentMetrics | dict[str, Any] | None = None,
    ) -> None:
        """Finalizes the active agent view, displays the metrics table, and stops live rendering."""
        if self._active_agent_view is not None:
            self._active_agent_view.complete(metrics=metrics)
            if self._active_live is not None:
                try:
                    self._active_live.update(self._active_agent_view)
                    self._active_live.stop()
                except Exception as e:
                    logger.debug("Failed stopping live display: %s", e)
                finally:
                    self._active_live = None
            else:
                self._console.print(self._active_agent_view)

            self._console.print()
            self._active_agent_view = None

            # Render markdown boxes queued during this agent's run directly below the agent view
            if self._pending_markdown_boxes:
                boxes = list(self._pending_markdown_boxes)
                self._pending_markdown_boxes.clear()
                for box in boxes:
                    self._render_markdown_box(
                        content=box["content"],
                        title=box["title"],
                        border_style=box["border_style"],
                        **box.get("panel_kwargs", {}),
                    )

    def fail_agent_view(self, agent_name: str | None = None, error_message: str | None = None) -> None:
        """Marks the active agent view as failed and stops live rendering."""
        if self._active_agent_view is not None:
            self._active_agent_view.fail(error_message=error_message)
            if self._active_live is not None:
                try:
                    self._active_live.update(self._active_agent_view)
                    self._active_live.stop()
                except Exception as e:
                    logger.debug("Failed stopping live display: %s", e)
                finally:
                    self._active_live = None
            else:
                self._console.print(self._active_agent_view)

            self._console.print()
            self._active_agent_view = None
            self._pending_markdown_boxes.clear()

    def start_node_view(self, node_name: str) -> NodeExecutionView:
        """Initializes and starts a live NodeExecutionView display."""
        if self._active_agent_view is not None:
            self.finish_agent_view()
        if self._active_node_view is not None:
            self.finish_node_view()

        self.stop_progress()

        view = NodeExecutionView(node_name=node_name)
        self._active_node_view = view

        if self._console.is_terminal:
            self._active_live = Live(
                view,
                console=self._console,
                refresh_per_second=10,
                transient=False,
            )
            self._active_live.start()

        return view

    def record_node_reading_file(self, display_name: str) -> None:
        """Sets the active node operation to reading a specific file."""
        if self._active_node_view is not None:
            self._active_node_view.set_reading_file(display_name)
            self._refresh_live()

    def record_node_file_result(self, display_name: str, found: bool, abs_path: str | None = None) -> None:
        """Records a file read/check result in the active node view."""
        if self._active_node_view is not None:
            self._active_node_view.add_file_activity(display_name=display_name, found=found, abs_path=abs_path)
            self._active_node_view.set_active_operation(None)
            self._refresh_live()

    def record_node_converting_file(self, display_name: str, target_name: str = "") -> None:
        """Sets the active node operation to converting a specific file."""
        if self._active_node_view is not None:
            self._active_node_view.set_converting_file(display_name, target_name)
            self._refresh_live()

    def record_node_conversion_result(
        self,
        display_name: str,
        target_name: str,
        abs_path: str | None = None,
        target_path: str | None = None,
    ) -> None:
        """Records a file conversion result in the active node view."""
        if self._active_node_view is not None:
            self._active_node_view.add_conversion_activity(
                display_name=display_name,
                target_name=target_name,
                abs_path=abs_path,
                target_path=target_path,
            )
            self._active_node_view.set_active_operation(None)
            self._refresh_live()

    def record_node_activity(self, message: str) -> None:
        """Records an informational activity message in the active node view."""
        if self._active_node_view is not None:
            self._active_node_view.add_info_activity(message)
            self._active_node_view.set_active_operation(None)
            self._refresh_live()

    def record_node_active_operation(self, operation: str | None) -> None:
        """Sets the currently active in-progress operation for the active node view."""
        if self._active_node_view is not None:
            self._active_node_view.set_active_operation(operation)
            self._refresh_live()

    def finish_node_view(self, node_name: str | None = None) -> None:
        """Finalizes the active node view and stops live rendering."""
        if self._active_node_view is not None:
            self._active_node_view.complete()
            if self._active_live is not None:
                try:
                    self._active_live.update(self._active_node_view)
                    self._active_live.stop()
                except Exception as e:
                    logger.debug("Failed stopping live display: %s", e)
                finally:
                    self._active_live = None
            else:
                self._console.print(self._active_node_view)

            self._console.print()
            self._active_node_view = None

    def fail_node_view(self, node_name: str | None = None, error_message: str | None = None) -> None:
        """Marks the active node view as failed and stops live rendering."""
        if self._active_node_view is not None:
            self._active_node_view.fail(error_message=error_message)
            if self._active_live is not None:
                try:
                    self._active_live.update(self._active_node_view)
                    self._active_live.stop()
                except Exception as e:
                    logger.debug("Failed stopping live display: %s", e)
                finally:
                    self._active_live = None
            else:
                self._console.print(self._active_node_view)

            self._console.print()
            self._active_node_view = None

    def ask_user(self, question: str, options: list[str] | None = None) -> str:
        """Prompts the user interactively in the terminal with optional choices, pausing Live display if active."""
        if self._auto_approve:
            selected_answer = options[0] if options else "approved"
            if self._active_agent_view is not None:
                self._active_agent_view.add_user_question(
                    question=question,
                    options=options or [],
                    selected_idx=1,
                    custom_answer=None,
                )
                self._refresh_live()
            else:
                self._console.print(
                    Panel(
                        f"[bold yellow]Clarification Interview (Auto-approved):[/bold yellow]\n{question}\n\n"
                        f"[bold green]Selected default:[/bold green] {selected_answer}",
                        title_align="left",
                        border_style="yellow",
                    )
                )
            return selected_answer

        was_live = False
        if self._active_live is not None:
            try:
                self._active_live.transient = True
                self._active_live.stop()
                was_live = True
            except Exception as e:
                logger.debug("Failed pausing live display: %s", e)

        try:
            dialog_items: list[Any] = [
                Panel(
                    f"[bold yellow]Clarification Interview:[/bold yellow]\n{question}",
                    title_align="left",
                    border_style="yellow",
                )
            ]

            selected_answer: str = ""
            selected_idx = 1
            custom_answer: str | None = None
            prompt_lines = 0

            if options:
                opts_renderables: list[Any] = [Text.from_markup("[bold cyan]Options:[/bold cyan]")]
                for idx, opt in enumerate(options, 1):
                    opts_renderables.append(Text(f"  [{idx}] {opt}"))
                custom_idx = len(options) + 1
                opts_renderables.append(Text(f"  [{custom_idx}] Other (custom response)"))
                dialog_items.extend(opts_renderables)

                dialog_group = Group(*dialog_items)
                dialog_lines = len(self._console.render_lines(dialog_group, self._console.options))
                self._console.print(dialog_group)

                choice = Prompt.ask(
                    "[bold green]Select option or enter number[/bold green]",
                    default="1",
                    console=self._console,
                )
                prompt_lines += 1

                if choice.isdigit() and 1 <= int(choice) <= len(options):
                    selected_idx = int(choice)
                    selected_answer = options[selected_idx - 1]
                elif (choice.isdigit() and int(choice) == custom_idx) or choice.lower() in ("o", "other"):
                    selected_idx = custom_idx
                    custom_answer = Prompt.ask("[bold green]Your custom answer[/bold green]", console=self._console)
                    prompt_lines += 1
                    selected_answer = custom_answer
                else:
                    selected_answer = choice
                    selected_idx = custom_idx
                    custom_answer = choice
            else:
                dialog_group = Group(*dialog_items)
                dialog_lines = len(self._console.render_lines(dialog_group, self._console.options))
                self._console.print(dialog_group)

                selected_answer = Prompt.ask("[bold green]Your answer[/bold green]", console=self._console)
                prompt_lines += 1
                selected_idx = 1

            if self._console.is_terminal:
                total_lines = dialog_lines + prompt_lines
                clear_seq = ("\033[A\033[2K" * total_lines) + "\r"
                self._console.file.write(clear_seq)
                self._console.file.flush()

            if self._active_agent_view is not None:
                self._active_agent_view.add_user_question(
                    question=question,
                    options=options or [],
                    selected_idx=selected_idx,
                    custom_answer=custom_answer,
                )

            return selected_answer
        finally:
            if was_live and self._active_agent_view is not None:
                try:
                    self._active_live = Live(
                        self._active_agent_view,
                        console=self._console,
                        refresh_per_second=10,
                        transient=False,
                    )
                    self._active_live.start()
                except Exception as e:
                    logger.debug("Failed resuming live display: %s", e)

    def show_markdown_box(
        self,
        content: str,
        title: str | None = None,
        border_style: str = "cyan",
        force: bool = False,
        **panel_kwargs: Any,
    ) -> None:
        """Displays a formatted Markdown block inside an optional titled Rich panel.

        If display_markdown is False and force is False, the box is not displayed.
        When an agent view is active, markdown boxes are queued and displayed directly
        below the agent view upon completion.

        Args:
            content: Raw Markdown content string to display.
            title: Optional title displayed on the panel border.
            border_style: Color/style for the panel border (default: cyan).
            force: Force display regardless of display_markdown flag.
            **panel_kwargs: Additional keyword arguments passed to Rich Panel.
        """
        if not self._display_markdown and not force:
            return

        if self._active_agent_view is not None:
            self._pending_markdown_boxes.append(
                {
                    "content": content,
                    "title": title,
                    "border_style": border_style,
                    "panel_kwargs": panel_kwargs,
                }
            )
            return

        self._render_markdown_box(
            content=content,
            title=title,
            border_style=border_style,
            **panel_kwargs,
        )

    def _render_markdown_box(
        self,
        content: str,
        title: str | None = None,
        border_style: str = "cyan",
        **panel_kwargs: Any,
    ) -> None:
        """Renders a single markdown box panel directly to the console."""
        markdown_renderable = Markdown(content.strip())
        panel = Panel(
            markdown_renderable,
            title=title,
            border_style=border_style,
            padding=panel_kwargs.pop("padding", (1, 2)),
            **panel_kwargs,
        )
        self._console.print(panel)

    def show_step(
        self,
        step_number: int,
        total_steps: int,
        title: str,
        description: str | None = None,
        is_empty: bool = False,
    ) -> None:
        """Displays a formatted step announcement rule on standard output.

        Args:
            step_number: Current step number (1-indexed).
            total_steps: Total number of steps in the workflow.
            title: Title / name of the step.
            description: Optional description explaining what this step does.
            is_empty: Whether this step is currently empty / not yet implemented.
        """
        rule_style = "dim cyan" if is_empty else "bold cyan"
        line_style = "dim" if is_empty else "cyan"
        self._console.print()
        self._console.rule(
            f"[{rule_style}]Step {step_number}/{total_steps}: {title}[/{rule_style}]",
            style=line_style,
            align="left",
        )
        if description:
            self._console.print(f"  [dim]{description}[/dim]")
        self._console.print()

    def warning(self, message: str, title: str = "Warning") -> None:
        """Displays a formatted warning box on standard output."""
        panel = Panel(
            f"[bold yellow]{message}[/bold yellow]",
            title=f"[yellow]{title}[/yellow]" if title else None,
            border_style="yellow",
            padding=(0, 1),
        )
        self._console.print(panel)

    def error(
        self,
        message: str,
        exc: BaseException | None = None,
        show_trace: bool = False,
        title: str = "Error",
    ) -> None:
        """Displays a formatted error box and optionally prints a syntax-highlighted traceback.

        Args:
            message: Error description string.
            exc: Optional exception object to extract traceback from.
            show_trace: Whether to render the full traceback.
            title: Title for the error panel (default: Error).
        """
        panel = Panel(
            f"[bold red]{message}[/bold red]",
            title=f"[red]{title}[/red]" if title else None,
            border_style="red",
            padding=(0, 1),
        )
        self._console_err.print(panel)

        if show_trace:
            if exc is not None:
                tb = Traceback.from_exception(
                    type(exc),
                    exc,
                    exc.__traceback__,
                    show_locals=True,
                )
                self._console_err.print(tb)
            elif sys.exc_info()[0] is not None:
                self._console_err.print_exception(show_locals=True)


ui_service = UIService()


def get_ui_service() -> UIService:
    """Returns the global UIService singleton."""
    return ui_service
