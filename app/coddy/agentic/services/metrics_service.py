"""DuckDB-backed metrics collection, performance profiling, and ADK telemetry plugin."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from rich.box import ROUNDED
from rich.console import Console
from rich.table import Table

from app.coddy.agentic.services.pricing_service import format_cost_eur, get_pricing_service
from app.coddy.utils.services import DuckDbService, get_duckdb_service, get_ui_service

logger = logging.getLogger(__name__)

DEFAULT_CHAR_LIMIT = 10000


def _serialize_and_truncate(obj: Any, limit: int = DEFAULT_CHAR_LIMIT) -> tuple[str, bool]:
    """Serializes arbitrary object to string and truncates if exceeding character limit."""
    try:
        if isinstance(obj, str):
            raw = obj
        elif isinstance(obj, (dict, list, tuple)):
            raw = json.dumps(obj, default=str)
        else:
            raw = str(obj)
    except Exception:
        raw = str(obj)

    if len(raw) > limit:
        return raw[:limit] + "... [TRUNCATED]", True
    return raw, False


class MetricsService:
    """Manages recording and analytical querying of execution metrics in DuckDB."""

    def __init__(self, duckdb_service: DuckDbService | None = None, db_path: Path | str | None = None) -> None:
        """Initializes MetricsService with DuckDbService or database path.

        Args:
            duckdb_service: Existing DuckDbService instance.
            db_path: Optional path for DuckDbService if duckdb_service is None.
        """
        if duckdb_service is not None:
            self._duckdb = duckdb_service
        else:
            self._duckdb = get_duckdb_service(db_path=db_path)

    @property
    def duckdb_service(self) -> DuckDbService:
        """Returns the underlying DuckDbService."""
        return self._duckdb

    def record_session_start(
        self,
        session_id: str,
        user_id: str = "",
        app_name: str = "coddy",
        start_time: datetime | None = None,
    ) -> None:
        """Records initial session metadata in session_metrics."""
        st = start_time or datetime.now(UTC)
        query = """
        INSERT INTO session_metrics (
            session_id, user_id, app_name, start_time, status
        ) VALUES (?, ?, ?, ?, 'RUNNING')
        ON CONFLICT (session_id) DO UPDATE SET
            user_id = excluded.user_id,
            app_name = excluded.app_name,
            start_time = COALESCE(session_metrics.start_time, excluded.start_time),
            status = 'RUNNING';
        """
        self._duckdb.execute(query, [session_id, user_id, app_name, st])

    def record_session_end(
        self,
        session_id: str,
        status: str = "COMPLETED",
        error_message: str | None = None,
        end_time: datetime | None = None,
    ) -> None:
        """Finalizes session record with aggregated token counts, duration, and status."""
        et = end_time or datetime.now(UTC)

        # Aggregate tokens and cost from step_metrics
        token_agg_query = """
        SELECT
            COALESCE(SUM(prompt_tokens), 0),
            COALESCE(SUM(completion_tokens), 0),
            COALESCE(SUM(reasoning_tokens), 0),
            COALESCE(SUM(cached_tokens), 0),
            COALESCE(SUM(total_tokens), 0),
            COALESCE(SUM(cost_eur), 0.0)
        FROM step_metrics
        WHERE session_id = ?;
        """
        token_rows = self._duckdb.fetchall(token_agg_query, [session_id])
        if token_rows and token_rows[0]:
            p_tok, c_tok, r_tok, ca_tok, tot_tok, tot_cost = token_rows[0]
        else:
            p_tok = c_tok = r_tok = ca_tok = tot_tok = 0
            tot_cost = 0.0

        # Count total tools from tool_metrics
        tool_count_query = "SELECT COUNT(*) FROM tool_metrics WHERE session_id = ?;"
        tool_rows = self._duckdb.fetchall(tool_count_query, [session_id])
        tool_count = tool_rows[0][0] if tool_rows and tool_rows[0] else 0

        # Calculate session duration
        start_time_row = self._duckdb.fetchone(
            "SELECT start_time FROM session_metrics WHERE session_id = ?;", [session_id]
        )
        duration_ms: float = 0.0
        if start_time_row and start_time_row[0]:
            st = start_time_row[0]
            if isinstance(st, datetime):
                # Ensure UTC awareness for comparison
                st_utc = st if st.tzinfo is not None else st.replace(tzinfo=UTC)
                et_utc = et if et.tzinfo is not None else et.replace(tzinfo=UTC)
                duration_ms = max(0.0, (et_utc - st_utc).total_seconds() * 1000.0)

        if duration_ms <= 0.0:
            step_sum_row = self._duckdb.fetchone(
                "SELECT COALESCE(SUM(duration_ms), 0) FROM step_metrics WHERE session_id = ?;", [session_id]
            )
            if step_sum_row and step_sum_row[0]:
                duration_ms = float(step_sum_row[0])

        update_query = """
        UPDATE session_metrics
        SET
            end_time = ?,
            duration_ms = ?,
            prompt_tokens = ?,
            completion_tokens = ?,
            reasoning_tokens = ?,
            cached_tokens = ?,
            total_tokens = ?,
            total_tool_calls = ?,
            status = ?,
            error_message = ?,
            total_cost_eur = ?
        WHERE session_id = ?;
        """
        self._duckdb.execute(
            update_query,
            [
                et,
                duration_ms,
                p_tok,
                c_tok,
                r_tok,
                ca_tok,
                tot_tok,
                tool_count,
                status,
                error_message,
                tot_cost,
                session_id,
            ],
        )

    def record_step(
        self,
        session_id: str,
        step_name: str,
        agent_name: str,
        model_name: str,
        start_time: datetime,
        end_time: datetime,
        duration_ms: float,
        ttft_ms: float | None = None,
        tokens_per_sec: float | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_tokens: int = 0,
        thinking_level: str | None = None,
        thinking_budget: int | None = None,
        temperature: float | None = None,
        status: str = "SUCCESS",
        error_message: str | None = None,
        step_id: str | None = None,
        cost_eur: float | None = None,
        input_cost_eur: float | None = None,
        output_cost_eur: float | None = None,
        cache_read_cost_eur: float | None = None,
        cost_details: dict[str, Any] | str | None = None,
    ) -> str:
        """Inserts a detailed step and model performance record into step_metrics."""
        sid = step_id or f"step_{uuid.uuid4().hex[:12]}"
        total_tokens = prompt_tokens + completion_tokens

        if cost_eur is None:
            pricing_service = get_pricing_service()
            breakdown = pricing_service.calculate_step_cost(
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
            final_cost = breakdown.total_cost_eur
            final_input_cost = breakdown.input_cost_eur
            final_output_cost = breakdown.output_cost_eur
            final_cache_read_cost = breakdown.cache_read_cost_eur
            final_cost_details = json.dumps(breakdown.model_dump())
        else:
            final_cost = cost_eur
            final_input_cost = input_cost_eur if input_cost_eur is not None else 0.0
            final_output_cost = output_cost_eur if output_cost_eur is not None else 0.0
            final_cache_read_cost = cache_read_cost_eur if cache_read_cost_eur is not None else 0.0
            if isinstance(cost_details, dict):
                final_cost_details = json.dumps(cost_details)
            elif isinstance(cost_details, str):
                final_cost_details = cost_details
            else:
                final_cost_details = "{}"

        query = """
        INSERT INTO step_metrics (
            id, session_id, step_name, agent_name, model_name,
            thinking_level, thinking_budget, temperature,
            start_time, end_time, duration_ms, ttft_ms, tokens_per_sec,
            prompt_tokens, completion_tokens, reasoning_tokens, cached_tokens, total_tokens,
            status, error_message,
            cost_eur, input_cost_eur, output_cost_eur, cache_read_cost_eur, cost_details
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?, ?
        );
        """
        self._duckdb.execute(
            query,
            [
                sid,
                session_id,
                step_name,
                agent_name,
                model_name,
                thinking_level,
                thinking_budget,
                temperature,
                start_time,
                end_time,
                duration_ms,
                ttft_ms,
                tokens_per_sec,
                prompt_tokens,
                completion_tokens,
                reasoning_tokens,
                cached_tokens,
                total_tokens,
                status,
                error_message,
                final_cost,
                final_input_cost,
                final_output_cost,
                final_cache_read_cost,
                final_cost_details,
            ],
        )
        return sid

    def record_tool_call(
        self,
        session_id: str,
        agent_name: str,
        tool_name: str,
        tool_args: Any,
        tool_result: Any,
        start_time: datetime,
        end_time: datetime,
        duration_ms: float,
        step_name: str = "",
        status: str = "SUCCESS",
        error_message: str | None = None,
        max_char_limit: int = DEFAULT_CHAR_LIMIT,
        tool_call_id: str | None = None,
    ) -> str:
        """Inserts a tool invocation record into tool_metrics with payload truncation."""
        tid = tool_call_id or f"tool_{uuid.uuid4().hex[:12]}"
        args_str, truncated_args = _serialize_and_truncate(tool_args, limit=max_char_limit)
        res_str, truncated_res = _serialize_and_truncate(tool_result, limit=max_char_limit)
        is_truncated = truncated_args or truncated_res

        query = """
        INSERT INTO tool_metrics (
            id, session_id, step_name, agent_name, tool_name,
            tool_args, tool_result, is_truncated,
            start_time, end_time, duration_ms, status, error_message
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?
        );
        """
        self._duckdb.execute(
            query,
            [
                tid,
                session_id,
                step_name,
                agent_name,
                tool_name,
                args_str,
                res_str,
                is_truncated,
                start_time,
                end_time,
                duration_ms,
                status,
                error_message,
            ],
        )
        return tid

    def get_session_summary(self, session_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Queries v_session_summary view."""
        if session_id:
            query = "SELECT * FROM v_session_summary WHERE session_id = ?;"
            rows = self._duckdb.fetchall(query, [session_id])
        else:
            query = "SELECT * FROM v_session_summary ORDER BY start_time DESC LIMIT ?;"
            rows = self._duckdb.fetchall(query, [limit])

        columns = [
            "session_id",
            "user_id",
            "app_name",
            "start_time",
            "end_time",
            "duration_ms",
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "cached_tokens",
            "total_tokens",
            "total_tool_calls",
            "status",
            "step_count",
            "total_cost_eur",
        ]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_model_performance(self) -> list[dict[str, Any]]:
        """Queries v_model_performance view."""
        rows = self._duckdb.fetchall("SELECT * FROM v_model_performance;")
        columns = [
            "model_name",
            "total_calls",
            "avg_duration_ms",
            "avg_ttft_ms",
            "avg_tokens_per_sec",
            "total_prompt_tokens",
            "total_completion_tokens",
            "total_reasoning_tokens",
            "total_cached_tokens",
            "grand_total_tokens",
            "total_cost_eur",
        ]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_agent_performance(self) -> list[dict[str, Any]]:
        """Queries v_agent_performance view."""
        rows = self._duckdb.fetchall("SELECT * FROM v_agent_performance;")
        columns = [
            "agent_name",
            "total_steps",
            "avg_duration_ms",
            "total_prompt_tokens",
            "total_completion_tokens",
            "total_reasoning_tokens",
            "grand_total_tokens",
        ]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_tool_usage(self, limit: int = 50) -> list[dict[str, Any]]:
        """Queries v_tool_usage view."""
        rows = self._duckdb.fetchall("SELECT * FROM v_tool_usage ORDER BY total_invocations DESC LIMIT ?;", [limit])
        columns = [
            "tool_name",
            "total_invocations",
            "avg_duration_ms",
            "failed_invocations",
            "truncated_invocations",
        ]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_session_steps(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieves all steps recorded for a session."""
        query = "SELECT * FROM step_metrics WHERE session_id = ? ORDER BY start_time ASC;"
        rows = self._duckdb.fetchall(query, [session_id])
        columns = [
            "id",
            "session_id",
            "step_name",
            "agent_name",
            "model_name",
            "thinking_level",
            "thinking_budget",
            "temperature",
            "start_time",
            "end_time",
            "duration_ms",
            "ttft_ms",
            "tokens_per_sec",
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "cached_tokens",
            "total_tokens",
            "status",
            "error_message",
            "cost_eur",
            "input_cost_eur",
            "output_cost_eur",
            "cache_read_cost_eur",
            "cost_details",
        ]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_session_tools(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieves all tool calls recorded for a session."""
        query = "SELECT * FROM tool_metrics WHERE session_id = ? ORDER BY start_time ASC;"
        rows = self._duckdb.fetchall(query, [session_id])
        columns = [
            "id",
            "session_id",
            "step_name",
            "agent_name",
            "tool_name",
            "tool_args",
            "tool_result",
            "is_truncated",
            "start_time",
            "end_time",
            "duration_ms",
            "status",
            "error_message",
        ]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def display_session_summary(self, session_id: str, console: Console | None = None) -> None:
        """Renders an elegant Rich summary table of metrics for a session."""
        cons = console or Console()
        summaries = self.get_session_summary(session_id=session_id)
        steps = self.get_session_steps(session_id=session_id)
        if not summaries and not steps:
            return

        summary = summaries[0] if summaries else {}

        table = Table(
            title=f"Session Execution Metrics: [bold cyan]{session_id}[/bold cyan]",
            box=ROUNDED,
            header_style="bold magenta",
        )
        table.add_column("Agent / Step", style="cyan")
        table.add_column("Model", style="blue")
        table.add_column("Turns", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("TTFT (avg)", justify="right")
        table.add_column("Tok/Sec (avg)", justify="right")
        table.add_column("Tokens (P / C / R)", justify="right")
        table.add_column("Cost (EUR)", justify="right")
        table.add_column("Status", justify="center")

        # Group steps by (agent_name or step_name, model_name)
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for step in steps:
            key = (step.get("agent_name") or step.get("step_name") or "-", step.get("model_name") or "-")
            groups.setdefault(key, []).append(step)

        for (agent_label, model_label), group_steps in groups.items():
            turns_count = len(group_steps)
            sum_duration_ms = sum(s.get("duration_ms") or 0.0 for s in group_steps)
            sum_prompt = sum(s.get("prompt_tokens") or 0 for s in group_steps)
            sum_completion = sum(s.get("completion_tokens") or 0 for s in group_steps)
            sum_reasoning = sum(s.get("reasoning_tokens") or 0 for s in group_steps)
            sum_cost = sum(s.get("cost_eur") or 0.0 for s in group_steps)

            valid_ttft = [s["ttft_ms"] for s in group_steps if s.get("ttft_ms") is not None]
            avg_ttft_ms = (sum(valid_ttft) / len(valid_ttft)) if valid_ttft else None

            valid_tps = [
                s["tokens_per_sec"]
                for s in group_steps
                if s.get("tokens_per_sec") is not None and s.get("tokens_per_sec") > 0
            ]
            avg_tps = (sum(valid_tps) / len(valid_tps)) if valid_tps else None

            dur_str = f"{sum_duration_ms / 1000.0:.2f}s" if sum_duration_ms else "-"
            ttft_str = f"{avg_ttft_ms / 1000.0:.2f}s" if avg_ttft_ms else "-"
            tps_str = f"{avg_tps:.1f}" if avg_tps else "-"
            tok_str = f"{sum_prompt:,} / {sum_completion:,} / {sum_reasoning:,}"
            cost_str = format_cost_eur(sum_cost)

            all_ok = all(s.get("status") == "SUCCESS" for s in group_steps)
            status_style = "[green]OK[/green]" if all_ok else "[red]FAIL[/red]"

            table.add_row(
                agent_label,
                model_label,
                str(turns_count),
                dur_str,
                ttft_str,
                tps_str,
                tok_str,
                cost_str,
                status_style,
            )

        # Add total footer
        tot_dur_ms = summary.get("duration_ms") or sum(s.get("duration_ms") or 0.0 for s in steps)
        tot_dur = f"{tot_dur_ms / 1000.0:.2f}s" if tot_dur_ms else "-"

        all_ttft = [s["ttft_ms"] for s in steps if s.get("ttft_ms") is not None]
        tot_avg_ttft = f"{(sum(all_ttft) / len(all_ttft)) / 1000.0:.2f}s" if all_ttft else "-"

        all_tps = [
            s["tokens_per_sec"] for s in steps if s.get("tokens_per_sec") is not None and s.get("tokens_per_sec") > 0
        ]
        tot_avg_tps = f"{(sum(all_tps) / len(all_tps)):.1f}" if all_tps else "-"

        tot_tok = (
            f"{summary.get('prompt_tokens', 0):,} / "
            f"{summary.get('completion_tokens', 0):,} / "
            f"{summary.get('reasoning_tokens', 0):,}"
        )
        tot_cost = (
            summary.get("total_cost_eur")
            if summary.get("total_cost_eur") is not None
            else sum(s.get("cost_eur") or 0.0 for s in steps)
        )
        tot_cost_str = f"[bold]{format_cost_eur(tot_cost)}[/bold]"

        table.add_section()
        table.add_row(
            "[bold]Total Session[/bold]",
            f"Tools: {summary.get('total_tool_calls', 0)}",
            f"{len(steps)} turns",
            f"[bold]{tot_dur}[/bold]",
            tot_avg_ttft,
            tot_avg_tps,
            f"[bold]{tot_tok}[/bold]",
            tot_cost_str,
            f"[bold]{summary.get('status')}[/bold]",
        )

        cons.print(table)

        # Display dedicated Model Cost Breakdown table at the end of the session
        models_cost: dict[str, dict[str, Any]] = {}
        for step in steps:
            m_name = step.get("model_name") or "unknown"
            if m_name not in models_cost:
                models_cost[m_name] = {
                    "turns": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "cost_eur": 0.0,
                }
            entry = models_cost[m_name]
            entry["turns"] += 1
            entry["prompt_tokens"] += step.get("prompt_tokens") or 0
            entry["completion_tokens"] += step.get("completion_tokens") or 0
            entry["cached_tokens"] += step.get("cached_tokens") or 0
            entry["cost_eur"] += step.get("cost_eur") or 0.0

        if models_cost:
            cost_table = Table(
                title="Session Cost Estimation (EUR)",
                box=ROUNDED,
                header_style="bold green",
            )
            cost_table.add_column("Model", style="cyan")
            cost_table.add_column("Turns", justify="right")
            cost_table.add_column("Prompt Tokens", justify="right")
            cost_table.add_column("Completion", justify="right")
            cost_table.add_column("Cached Read", justify="right")
            cost_table.add_column("Cost (EUR)", justify="right", style="bold yellow")

            for m_name, m_data in models_cost.items():
                cost_table.add_row(
                    m_name,
                    str(m_data["turns"]),
                    f"{m_data['prompt_tokens']:,}",
                    f"{m_data['completion_tokens']:,}",
                    f"{m_data['cached_tokens']:,}",
                    format_cost_eur(m_data["cost_eur"]),
                )

            cost_table.add_section()
            cost_table.add_row(
                "[bold]Grand Total[/bold]",
                f"{len(steps)} turns",
                f"{summary.get('prompt_tokens', 0):,}",
                f"{summary.get('completion_tokens', 0):,}",
                f"{summary.get('cached_tokens', 0):,}",
                f"[bold yellow]{format_cost_eur(tot_cost)}[/bold yellow]",
            )
            cons.print(cost_table)


class MetricsPlugin(BasePlugin):
    """Google ADK BasePlugin that intercepts execution hooks and records metrics into DuckDB."""

    def __init__(self, metrics_service: MetricsService | None = None, name: str = "metrics_plugin") -> None:
        super().__init__(name=name)
        self._metrics_service = metrics_service or MetricsService()

        # In-flight timing and telemetry state tracking
        self._session_start_times: dict[str, datetime] = {}
        self._current_agent_name: str = ""
        self._current_step_name: str = ""

        self._model_start_time: float | None = None
        self._model_start_dt: datetime | None = None
        self._first_token_time: float | None = None
        self._thinking_start_time: float | None = None
        self._thinking_duration_sec: float = 0.0
        self._generation_start_time: float | None = None
        self._current_phase: str | None = None
        self._current_model_name: str = ""
        self._current_thinking_level: str | None = None
        self._current_thinking_budget: int | None = None
        self._current_temperature: float | None = None

        self._tool_start_times: dict[str, tuple[float, datetime]] = {}

    @property
    def metrics_service(self) -> MetricsService:
        """Returns the associated MetricsService."""
        return self._metrics_service

    async def before_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """Captures session run start."""
        session_id = getattr(getattr(invocation_context, "session", None), "id", None) or "default_session"
        user_id = getattr(invocation_context, "user_id", "")
        app_name = getattr(invocation_context, "app_name", "coddy")
        now = datetime.now(UTC)
        self._session_start_times[session_id] = now
        try:
            self._metrics_service.record_session_start(
                session_id=session_id,
                user_id=user_id,
                app_name=app_name,
                start_time=now,
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in before_run_callback: %s", exc)

    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        """Captures successful session run completion."""
        session_id = getattr(getattr(invocation_context, "session", None), "id", None) or "default_session"
        now = datetime.now(UTC)
        try:
            self._metrics_service.record_session_end(
                session_id=session_id,
                status="COMPLETED",
                end_time=now,
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in after_run_callback: %s", exc)

    async def on_run_error_callback(self, *, invocation_context: InvocationContext, error: Exception) -> None:
        """Captures failed session run."""
        session_id = getattr(getattr(invocation_context, "session", None), "id", None) or "default_session"
        now = datetime.now(UTC)
        try:
            self._metrics_service.record_session_end(
                session_id=session_id,
                status="FAILED",
                error_message=str(error),
                end_time=now,
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in on_run_error_callback: %s", exc)

    async def before_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> None:
        """Tracks active agent name."""
        self._current_agent_name = getattr(agent, "name", "")
        self._current_step_name = getattr(callback_context, "node_path", "") or self._current_agent_name

    async def after_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> None:
        """Resets active agent tracking."""
        self._current_agent_name = ""

    async def on_agent_error_callback(
        self, *, agent: BaseAgent, callback_context: CallbackContext, error: Exception
    ) -> None:
        """Handles agent error."""
        logger.debug("Agent %s failed with error: %s", getattr(agent, "name", ""), error)

    async def before_model_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        """Records model invocation start time and parameters."""
        self._model_start_time = time.perf_counter()
        self._model_start_dt = datetime.now(UTC)
        self._first_token_time = None
        self._thinking_start_time = None
        self._thinking_duration_sec = 0.0
        self._generation_start_time = None
        self._current_phase = "processing"

        self._current_model_name = getattr(llm_request, "model", "") or ""
        config = getattr(llm_request, "config", None)
        if config is not None:
            # Strip additionalProperties from response_schema for Google AI Studio / Gemini compatibility
            resp_schema = getattr(config, "response_schema", None)
            if resp_schema is not None:
                from app.coddy.helpers.schema_helpers import sanitize_gemini_schema

                config.response_schema = sanitize_gemini_schema(resp_schema)

            self._current_temperature = getattr(config, "temperature", None)
            thinking_config = getattr(config, "thinking_config", None)
            if thinking_config is not None:
                level = getattr(thinking_config, "thinking_level", None)
                self._current_thinking_level = str(level.value if hasattr(level, "value") else level) if level else None
                self._current_thinking_budget = getattr(thinking_config, "thinking_budget", None)
            else:
                self._current_thinking_level = None
                self._current_thinking_budget = None
        else:
            self._current_temperature = None
            self._current_thinking_level = None
            self._current_thinking_budget = None

        try:
            ui = get_ui_service()
            agent_name = self._current_agent_name or getattr(callback_context, "agent_name", "")
            ui.record_prompt_processing_start(agent_name=agent_name)
        except Exception as exc:
            logger.debug("MetricsPlugin error updating UI in before_model_callback: %s", exc)

    async def on_event_callback(self, *, invocation_context: InvocationContext, event: Event) -> None:
        """Detects first streaming token for TTFT computation."""
        if self._model_start_time is not None and self._first_token_time is None:
            content = getattr(event, "content", None)
            has_parts = content and getattr(content, "parts", None)
            if has_parts or getattr(event, "partial", False):
                self._first_token_time = time.perf_counter()

    async def after_model_callback(self, *, callback_context: CallbackContext, llm_response: LlmResponse) -> None:
        """Records model performance, tokens, latencies, and token rates."""
        is_partial = getattr(llm_response, "partial", False) is True
        agent_name = self._current_agent_name or getattr(callback_context, "agent_name", "")
        ui = get_ui_service()

        if is_partial:
            now_perf = time.perf_counter()
            if self._first_token_time is None:
                self._first_token_time = now_perf
                start_perf = self._model_start_time or now_perf
                prompt_processing_sec = max(0.0, now_perf - start_perf)
                try:
                    ui.record_prompt_processing_end(agent_name=agent_name, duration_sec=prompt_processing_sec)
                except Exception as exc:
                    logger.debug("MetricsPlugin error recording prompt processing in after_model_callback: %s", exc)

            content = getattr(llm_response, "content", None)
            parts = getattr(content, "parts", []) or []
            has_thought = any(getattr(p, "thought", False) is True for p in parts)
            has_output = any(
                (not getattr(p, "thought", False))
                and (bool(getattr(p, "text", None)) or bool(getattr(p, "function_call", None)))
                for p in parts
            )

            if has_thought and not has_output:
                if self._current_phase != "thinking":
                    self._current_phase = "thinking"
                    self._thinking_start_time = now_perf
                    try:
                        ui.record_thinking_start(agent_name=agent_name, operation="thinking")
                    except Exception as exc:
                        logger.debug("MetricsPlugin error recording thinking start: %s", exc)
            elif has_output or (not has_thought and parts):
                if self._current_phase == "thinking":
                    self._thinking_duration_sec = max(
                        0.0, now_perf - (self._thinking_start_time or self._first_token_time)
                    )
                    try:
                        ui.record_thinking_end(agent_name=agent_name, duration_sec=self._thinking_duration_sec)
                    except Exception as exc:
                        logger.debug("MetricsPlugin error recording thinking end: %s", exc)
                    self._current_phase = "generating"
                    self._generation_start_time = now_perf
                    try:
                        ui.record_generation_start(agent_name=agent_name)
                    except Exception as exc:
                        logger.debug("MetricsPlugin error recording generation start: %s", exc)
                elif self._current_phase != "generating":
                    self._current_phase = "generating"
                    self._generation_start_time = now_perf
                    try:
                        ui.record_generation_start(agent_name=agent_name)
                    except Exception as exc:
                        logger.debug("MetricsPlugin error recording generation start: %s", exc)

            return None

        # Final response / non-partial turn
        now_dt = datetime.now(UTC)
        end_perf = time.perf_counter()

        start_perf = self._model_start_time or end_perf
        start_dt = self._model_start_dt or now_dt
        duration_ms = max(0.0, (end_perf - start_perf) * 1000.0)

        # Usage metadata
        usage = getattr(llm_response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
        reasoning_tokens = getattr(usage, "thoughts_token_count", 0) or 0
        cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0

        # Timing breakdown
        if self._first_token_time is not None:
            # Streaming session
            ttft_ms = max(0.0, (self._first_token_time - start_perf) * 1000.0)
            if self._current_phase == "thinking":
                thinking_sec = max(0.0, end_perf - (self._thinking_start_time or self._first_token_time))
                self._thinking_duration_sec += thinking_sec
                try:
                    ui.record_thinking_end(
                        agent_name=agent_name,
                        duration_sec=self._thinking_duration_sec,
                        reasoning_tokens=reasoning_tokens,
                    )
                except Exception as exc:
                    logger.debug("MetricsPlugin error recording thinking end: %s", exc)
                gen_duration_sec = 0.0
            else:
                gen_start = self._generation_start_time or self._first_token_time
                gen_duration_sec = max(0.001, end_perf - gen_start)
                try:
                    ui.record_generation_end(
                        agent_name=agent_name,
                        duration_sec=gen_duration_sec,
                        completion_tokens=completion_tokens,
                    )
                except Exception as exc:
                    logger.debug("MetricsPlugin error recording generation end: %s", exc)
        else:
            # Non-streaming fallback
            estimated_prefill_ms = min(duration_ms * 0.45, 180.0 + (prompt_tokens / 1000.0) * 15.0)
            if completion_tokens > 0 or reasoning_tokens > 0:
                ttft_ms = round(max(30.0, min(estimated_prefill_ms, duration_ms * 0.8)), 1)
            else:
                ttft_ms = round(duration_ms, 1)

            prompt_processing_sec = ttft_ms / 1000.0
            try:
                ui.record_prompt_processing_end(agent_name=agent_name, duration_sec=prompt_processing_sec)
            except Exception as exc:
                logger.debug("MetricsPlugin error recording prompt processing: %s", exc)

            remaining_sec = max(0.0, (duration_ms - ttft_ms) / 1000.0)
            if reasoning_tokens > 0:
                total_out = reasoning_tokens + completion_tokens
                thinking_sec = remaining_sec * (reasoning_tokens / total_out) if total_out > 0 else 0.0
                gen_duration_sec = max(0.001, remaining_sec - thinking_sec)
                try:
                    ui.record_thinking_end(
                        agent_name=agent_name,
                        duration_sec=thinking_sec,
                        reasoning_tokens=reasoning_tokens,
                    )
                    ui.record_generation_end(
                        agent_name=agent_name,
                        duration_sec=gen_duration_sec,
                        completion_tokens=completion_tokens,
                    )
                except Exception as exc:
                    logger.debug("MetricsPlugin error updating UI in non-streaming after_model_callback: %s", exc)
            else:
                gen_duration_sec = max(0.001, remaining_sec)
                try:
                    ui.record_generation_end(
                        agent_name=agent_name,
                        duration_sec=gen_duration_sec,
                        completion_tokens=completion_tokens,
                    )
                except Exception as exc:
                    logger.debug("MetricsPlugin error updating UI in non-streaming after_model_callback: %s", exc)

        # Tok/sec calculation based strictly on actual time outputting tokens
        tokens_per_sec: float | None = None
        if gen_duration_sec > 0 and completion_tokens > 0:
            tokens_per_sec = round(completion_tokens / gen_duration_sec, 1)

        session_id = getattr(getattr(callback_context, "session", None), "id", "")

        try:
            self._metrics_service.record_step(
                session_id=session_id,
                step_name=self._current_step_name or agent_name,
                agent_name=agent_name,
                model_name=self._current_model_name,
                start_time=start_dt,
                end_time=now_dt,
                duration_ms=duration_ms,
                ttft_ms=ttft_ms,
                tokens_per_sec=tokens_per_sec,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                cached_tokens=cached_tokens,
                thinking_level=self._current_thinking_level,
                thinking_budget=self._current_thinking_budget,
                temperature=self._current_temperature,
                status="SUCCESS",
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in after_model_callback: %s", exc)

        # Reset model call state
        self._model_start_time = None
        self._model_start_dt = None
        self._first_token_time = None
        self._thinking_start_time = None
        self._thinking_duration_sec = 0.0
        self._generation_start_time = None
        self._current_phase = None

    async def on_model_error_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest, error: Exception
    ) -> None:
        """Records failed model call."""
        now_dt = datetime.now(UTC)
        end_perf = time.perf_counter()
        start_perf = self._model_start_time or end_perf
        start_dt = self._model_start_dt or now_dt
        duration_ms = max(0.0, (end_perf - start_perf) * 1000.0)

        session_id = getattr(getattr(callback_context, "session", None), "id", "")
        agent_name = self._current_agent_name or getattr(callback_context, "agent_name", "")

        try:
            self._metrics_service.record_step(
                session_id=session_id,
                step_name=self._current_step_name or agent_name,
                agent_name=agent_name,
                model_name=self._current_model_name,
                start_time=start_dt,
                end_time=now_dt,
                duration_ms=duration_ms,
                status="FAILED",
                error_message=str(error),
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in on_model_error_callback: %s", exc)

        self._model_start_time = None
        self._model_start_dt = None
        self._first_token_time = None
        self._thinking_start_time = None
        self._thinking_duration_sec = 0.0
        self._generation_start_time = None
        self._current_phase = None

    async def before_tool_callback(
        self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext
    ) -> None:
        """Records start of tool execution."""
        tool_name = getattr(tool, "name", str(tool))
        self._tool_start_times[tool_name] = (time.perf_counter(), datetime.now(UTC))

        try:
            ui = get_ui_service()
            agent_name = getattr(tool_context, "agent_name", "") or self._current_agent_name
            ui.record_tool_start(agent_name=agent_name, tool_name=tool_name)
        except Exception as exc:
            logger.debug("MetricsPlugin error updating UI in before_tool_callback: %s", exc)

    async def after_tool_callback(
        self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, result: dict[str, Any]
    ) -> None:
        """Records completed tool execution."""
        tool_name = getattr(tool, "name", str(tool))
        end_perf = time.perf_counter()
        end_dt = datetime.now(UTC)

        start_tuple = self._tool_start_times.pop(tool_name, (end_perf, end_dt))
        start_perf, start_dt = start_tuple
        duration_ms = max(0.0, (end_perf - start_perf) * 1000.0)

        session_id = getattr(getattr(tool_context, "session", None), "id", "")
        agent_name = getattr(tool_context, "agent_name", "") or self._current_agent_name

        try:
            self._metrics_service.record_tool_call(
                session_id=session_id,
                step_name=self._current_step_name or agent_name,
                agent_name=agent_name,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=result,
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=duration_ms,
                status="SUCCESS",
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in after_tool_callback: %s", exc)

        try:
            ui = get_ui_service()
            ui.record_tool_end(
                agent_name=agent_name,
                tool_name=tool_name,
                status="SUCCESS",
                duration_sec=duration_ms / 1000.0,
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error updating UI in after_tool_callback: %s", exc)

    async def on_tool_error_callback(
        self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, error: Exception
    ) -> None:
        """Records failed tool execution."""
        tool_name = getattr(tool, "name", str(tool))
        end_perf = time.perf_counter()
        end_dt = datetime.now(UTC)

        start_tuple = self._tool_start_times.pop(tool_name, (end_perf, end_dt))
        start_perf, start_dt = start_tuple
        duration_ms = max(0.0, (end_perf - start_perf) * 1000.0)

        session_id = getattr(getattr(tool_context, "session", None), "id", "")
        agent_name = getattr(tool_context, "agent_name", "") or self._current_agent_name

        try:
            self._metrics_service.record_tool_call(
                session_id=session_id,
                step_name=self._current_step_name or agent_name,
                agent_name=agent_name,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result={"error": str(error)},
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=duration_ms,
                status="FAILED",
                error_message=str(error),
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error in on_tool_error_callback: %s", exc)

        try:
            ui = get_ui_service()
            ui.record_tool_end(
                agent_name=agent_name,
                tool_name=tool_name,
                status="FAILED",
                duration_sec=duration_ms / 1000.0,
                error_message=str(error),
            )
        except Exception as exc:
            logger.debug("MetricsPlugin error updating UI in on_tool_error_callback: %s", exc)


def get_metrics_service(db_path: Path | str | None = None) -> MetricsService:
    """Factory helper creating a MetricsService instance."""
    return MetricsService(db_path=db_path)


def get_metrics_plugin(metrics_service: MetricsService | None = None) -> MetricsPlugin:
    """Factory helper creating a MetricsPlugin instance."""
    return MetricsPlugin(metrics_service=metrics_service)
