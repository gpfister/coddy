"""Hermetic unit tests for DuckDbService, MetricsService, MetricsPlugin, and CLI commands."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from rich.console import Console
from typer.testing import CliRunner

from app.coddy.agentic.services.metrics_service import (
    DEFAULT_CHAR_LIMIT,
    MetricsService,
    _serialize_and_truncate,
    get_metrics_plugin,
    get_metrics_service,
)
from app.coddy.app import app
from app.coddy.utils.services.duckdb_service import DuckDbService, get_duckdb_service

cli_runner = CliRunner()


@pytest.fixture
def mem_duckdb() -> DuckDbService:
    """Fixture providing an in-memory DuckDbService."""
    service = get_duckdb_service(":memory:")
    yield service
    service.close()


@pytest.fixture
def metrics_service(mem_duckdb: DuckDbService) -> MetricsService:
    """Fixture providing a MetricsService backed by in-memory DuckDB."""
    return get_metrics_service(db_path=":memory:")


def test_duckdb_service_in_memory(mem_duckdb: DuckDbService):
    """Verify DuckDbService initializes in-memory database and schema DDL."""
    assert mem_duckdb.is_memory is True
    assert mem_duckdb.db_path is None

    tables = [row[0] for row in mem_duckdb.fetchall("SHOW TABLES;")]
    assert "session_metrics" in tables
    assert "step_metrics" in tables
    assert "tool_metrics" in tables
    assert "v_session_summary" in tables
    assert "v_model_performance" in tables
    assert "v_agent_performance" in tables
    assert "v_tool_usage" in tables


def test_duckdb_service_context_manager():
    """Verify DuckDbService context manager lifecycle."""
    with get_duckdb_service(":memory:") as db:
        res = db.fetchone("SELECT 42 AS val;")
        assert res is not None
        assert res[0] == 42


def test_duckdb_service_file_path(tmp_path):
    """Verify DuckDbService file path resolution and directory creation."""
    target_path = tmp_path / "subdir" / "metrics.db"
    db = DuckDbService(db_path=target_path)
    assert db.is_memory is False
    assert db.db_path == target_path

    # Directory created on connect
    _ = db.get_connection()
    assert target_path.parent.exists()
    assert target_path.exists()
    db.close()


def test_serialize_and_truncate():
    """Verify serialization and character truncation logic."""
    short_data = {"key": "value"}
    val, truncated = _serialize_and_truncate(short_data, limit=50)
    assert not truncated
    assert "key" in val

    long_str = "x" * 200
    val_long, truncated_long = _serialize_and_truncate(long_str, limit=50)
    assert truncated_long is True
    assert len(val_long) == 50 + len("... [TRUNCATED]")
    assert val_long.endswith("... [TRUNCATED]")


def test_metrics_service_session_lifecycle(metrics_service: MetricsService):
    """Verify session recording, step recording, and aggregated finalization."""
    session_id = "test_session_123"
    t0 = datetime.datetime(2026, 11, 11, 10, 0, 0)
    t1 = datetime.datetime(2026, 11, 11, 10, 0, 2)
    t2 = datetime.datetime(2026, 11, 11, 10, 0, 5)

    # Start session
    metrics_service.record_session_start(session_id=session_id, user_id="tester", app_name="coddy", start_time=t0)

    # Record step 1
    metrics_service.record_step(
        session_id=session_id,
        step_name="sanitize",
        agent_name="coding_sanitizer",
        model_name="gemini-3.5-flash-lite",
        start_time=t0,
        end_time=t1,
        duration_ms=2000.0,
        ttft_ms=500.0,
        tokens_per_sec=50.0,
        prompt_tokens=400,
        completion_tokens=100,
        reasoning_tokens=20,
        cached_tokens=10,
        thinking_level="LOW",
        thinking_budget=1024,
        temperature=0.2,
        status="SUCCESS",
    )

    # Record tool call
    metrics_service.record_tool_call(
        session_id=session_id,
        agent_name="coding_sanitizer",
        tool_name="read_file",
        tool_args={"path": "test.txt"},
        tool_result={"content": "file content"},
        start_time=t1,
        end_time=t2,
        duration_ms=50.0,
        status="SUCCESS",
    )

    # Finalize session
    metrics_service.record_session_end(session_id=session_id, status="COMPLETED", end_time=t2)

    # Query summary
    summaries = metrics_service.get_session_summary(session_id=session_id)
    assert len(summaries) == 1
    s = summaries[0]
    assert s["session_id"] == session_id
    assert s["user_id"] == "tester"
    assert s["prompt_tokens"] == 400
    assert s["completion_tokens"] == 100
    assert s["reasoning_tokens"] == 20
    assert s["total_tokens"] == 500
    assert s["total_tool_calls"] == 1
    assert s["step_count"] == 1
    assert s["status"] == "COMPLETED"
    assert s["total_cost_eur"] > 0.0

    # Query model performance view
    models = metrics_service.get_model_performance()
    assert len(models) == 1
    m = models[0]
    assert m["model_name"] == "gemini-3.5-flash-lite"
    assert m["total_calls"] == 1
    assert m["avg_ttft_ms"] == 500.0
    assert m["avg_tokens_per_sec"] == 50.0
    assert m["total_cost_eur"] > 0.0

    # Query agent performance view
    agents = metrics_service.get_agent_performance()
    assert len(agents) == 1
    assert agents[0]["agent_name"] == "coding_sanitizer"
    assert agents[0]["total_steps"] == 1

    # Query tool usage view
    tools = metrics_service.get_tool_usage()
    assert len(tools) == 1
    assert tools[0]["tool_name"] == "read_file"
    assert tools[0]["total_invocations"] == 1

    # Query steps detail
    steps = metrics_service.get_session_steps(session_id=session_id)
    assert len(steps) == 1
    assert steps[0]["cost_eur"] > 0.0
    assert "input_rate_per_m" in steps[0]["cost_details"]

    # Verify display output does not raise
    test_console = Console(record=True, width=160)
    metrics_service.display_session_summary(session_id=session_id, console=test_console)
    output = test_console.export_text()
    assert "Session Execution Metrics" in output
    assert "coding_sanitizer" in output
    assert "gemini-3.5-flash-lite" in output
    assert "Cost (EUR)" in output
    assert "Session Cost Estimation" in output
    assert "€0.001" in output


def test_tool_truncation_in_metrics_service(metrics_service: MetricsService):
    """Verify tool arguments and results exceeding limit are truncated."""
    session_id = "sess_trunc"
    huge_result = "z" * (DEFAULT_CHAR_LIMIT + 500)
    t = datetime.datetime.now()

    metrics_service.record_tool_call(
        session_id=session_id,
        agent_name="agent",
        tool_name="read_file",
        tool_args={"arg": "ok"},
        tool_result=huge_result,
        start_time=t,
        end_time=t,
        duration_ms=10.0,
    )

    tools = metrics_service.get_session_tools(session_id)
    assert len(tools) == 1
    assert tools[0]["is_truncated"] is True
    assert tools[0]["tool_result"].endswith("... [TRUNCATED]")


@pytest.mark.anyio
async def test_metrics_plugin_lifecycle():
    """Verify MetricsPlugin intercepts execution callbacks and populates DuckDB."""
    ms = get_metrics_service(":memory:")
    plugin = get_metrics_plugin(metrics_service=ms)

    session_mock = MagicMock()
    session_mock.id = "mock_session_1"

    inv_ctx = MagicMock(spec=InvocationContext)
    inv_ctx.session = session_mock
    inv_ctx.user_id = "test_user"
    inv_ctx.app_name = "coddy"

    # 1. Run start
    await plugin.before_run_callback(invocation_context=inv_ctx)

    # 2. Agent start
    agent_mock = MagicMock(spec=BaseAgent)
    agent_mock.name = "coding_sanitizer"
    cb_ctx = MagicMock(spec=CallbackContext)
    cb_ctx.session = session_mock
    cb_ctx.agent_name = "coding_sanitizer"
    cb_ctx.node_path = "coding_sanitizer_node"
    await plugin.before_agent_callback(agent=agent_mock, callback_context=cb_ctx)

    # 3. Model call start
    llm_req = MagicMock(spec=LlmRequest)
    llm_req.model = "gemini-3.5-flash-lite"
    config = MagicMock()
    config.temperature = 0.2
    thinking = MagicMock()
    thinking.thinking_level = types.ThinkingLevel.LOW
    thinking.thinking_budget = 512
    config.thinking_config = thinking
    llm_req.config = config

    await plugin.before_model_callback(callback_context=cb_ctx, llm_request=llm_req)

    # 4. Stream event (TTFT detection)
    event_mock = MagicMock(spec=Event)
    event_mock.content = MagicMock()
    event_mock.content.parts = [MagicMock(text="first chunk")]
    event_mock.partial = True
    await plugin.on_event_callback(invocation_context=inv_ctx, event=event_mock)

    # 5. Model call end
    llm_resp = MagicMock(spec=LlmResponse)
    usage = MagicMock()
    usage.prompt_token_count = 250
    usage.candidates_token_count = 75
    usage.thoughts_token_count = 15
    usage.cached_content_token_count = 0
    llm_resp.usage_metadata = usage

    await plugin.after_model_callback(callback_context=cb_ctx, llm_response=llm_resp)

    # 6. Tool call
    tool_mock = MagicMock(spec=BaseTool)
    tool_mock.name = "read_file"
    tool_ctx = MagicMock(spec=ToolContext)
    tool_ctx.session = session_mock
    tool_ctx.agent_name = "coding_sanitizer"

    await plugin.before_tool_callback(tool=tool_mock, tool_args={"path": "a.txt"}, tool_context=tool_ctx)
    await plugin.after_tool_callback(
        tool=tool_mock, tool_args={"path": "a.txt"}, tool_context=tool_ctx, result={"ok": True}
    )

    # 7. Agent end & Run end
    await plugin.after_agent_callback(agent=agent_mock, callback_context=cb_ctx)
    await plugin.after_run_callback(invocation_context=inv_ctx)

    # Validate database state
    summaries = ms.get_session_summary("mock_session_1")
    assert len(summaries) == 1
    assert summaries[0]["status"] == "COMPLETED"
    assert summaries[0]["prompt_tokens"] == 250
    assert summaries[0]["completion_tokens"] == 75
    assert summaries[0]["reasoning_tokens"] == 15
    assert summaries[0]["total_tool_calls"] == 1

    steps = ms.get_session_steps("mock_session_1")
    assert len(steps) == 1
    assert steps[0]["model_name"] == "gemini-3.5-flash-lite"
    assert steps[0]["ttft_ms"] is not None
    assert steps[0]["ttft_ms"] >= 0.0


def test_cli_metrics_empty(monkeypatch):
    """Verify CLI metrics commands with empty database."""
    mem_ms = get_metrics_service(":memory:")
    monkeypatch.setattr("app.coddy.cli.metrics.get_metrics_service", lambda: mem_ms)

    result_summary = cli_runner.invoke(app, ["metrics", "summary"])
    assert result_summary.exit_code == 0
    assert "No metrics recorded yet" in result_summary.stdout

    result_sessions = cli_runner.invoke(app, ["metrics", "sessions"])
    assert result_sessions.exit_code == 0
    assert "No session metrics recorded yet" in result_sessions.stdout

    result_tools = cli_runner.invoke(app, ["metrics", "tools"])
    assert result_tools.exit_code == 0
    assert "No tool metrics recorded yet" in result_tools.stdout


def test_cli_metrics_with_data(monkeypatch):
    """Verify CLI metrics commands display populated tables."""
    mem_ms = get_metrics_service(":memory:")
    monkeypatch.setattr("app.coddy.cli.metrics.get_metrics_service", lambda: mem_ms)

    sid = "cli_test_session"
    t = datetime.datetime.now()
    mem_ms.record_session_start(sid, user_id="bob", app_name="coddy", start_time=t)
    mem_ms.record_step(
        session_id=sid,
        step_name="planner",
        agent_name="coding_research_planner",
        model_name="gemini-3.8-flash",
        start_time=t,
        end_time=t,
        duration_ms=1500.0,
        ttft_ms=400.0,
        tokens_per_sec=35.0,
        prompt_tokens=600,
        completion_tokens=200,
        status="SUCCESS",
    )
    mem_ms.record_tool_call(
        session_id=sid,
        agent_name="coding_research_planner",
        tool_name="graphrag_search",
        tool_args={"q": "test"},
        tool_result={"matches": 3},
        start_time=t,
        end_time=t,
        duration_ms=30.0,
    )
    mem_ms.record_session_end(sid, status="COMPLETED")

    # Test summary command
    res_sum = cli_runner.invoke(app, ["metrics", "summary"], env={"COLUMNS": "160"})
    assert res_sum.exit_code == 0
    assert "Model Performance Overview" in res_sum.stdout
    assert "gemini-3.8-flash" in res_sum.stdout
    assert "Cost (EUR)" in res_sum.stdout

    # Test sessions command
    res_sess = cli_runner.invoke(app, ["metrics", "sessions"], env={"COLUMNS": "160"})
    assert res_sess.exit_code == 0
    assert "Session Records" in res_sess.stdout
    assert sid in res_sess.stdout

    # Test tools command
    res_tools = cli_runner.invoke(app, ["metrics", "tools"], env={"COLUMNS": "160"})
    assert res_tools.exit_code == 0
    assert "Aggregate Tool Usage Overview" in res_tools.stdout
    assert "graphrag_search" in res_tools.stdout

    # Test filter by session ID
    res_sess_filter = cli_runner.invoke(app, ["metrics", "summary", "--session-id", sid], env={"COLUMNS": "160"})
    assert res_sess_filter.exit_code == 0
    assert "Session Execution Metrics" in res_sess_filter.stdout
