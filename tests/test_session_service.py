"""Hermetic tests for UserService, SqliteService, and ADK SessionService."""

from pathlib import Path

import pytest
from google.adk.events import Event
from google.adk.sessions import BaseSessionService, DatabaseSessionService, InMemorySessionService
from google.genai import types

from app.coddy.agentic.services.session_service import SessionService
from app.coddy.utils.services.sqlite_service import SqliteService, get_sqlite_service
from app.coddy.utils.services.user_service import UserService, get_user_service


def test_user_service_fallback():
    """Verify UserService resolves user identifier."""
    user_id = get_user_service().get_current_user_id()
    assert user_id == "coddy_user"
    assert UserService().get_current_user_id() == "coddy_user"


def test_sqlite_service_paths_and_urls(tmp_path: Path):
    """Verify SqliteService resolves paths, memory modes, and sqlite+aiosqlite URLs."""
    # 1. Custom filesystem path
    db_file = tmp_path / "subdir" / "test.db"
    svc = get_sqlite_service(db_file)
    assert not svc.is_memory
    assert svc.db_path == db_file
    url = svc.get_db_url()
    assert url == f"sqlite+aiosqlite:///{db_file.resolve()}"
    assert db_file.parent.exists()

    # 2. In-memory mode
    mem_svc = get_sqlite_service(":memory:")
    assert mem_svc.is_memory
    assert mem_svc.db_path is None
    assert mem_svc.get_db_url() == "sqlite+aiosqlite:///:memory:"

    # 3. Explicit URL prefix normalization
    norm_svc = SqliteService("sqlite:///custom.db")
    assert norm_svc.get_db_url() == "sqlite+aiosqlite:///custom.db"


@pytest.mark.anyio
async def test_session_service_inheritance_and_memory():
    """Verify SessionService inherits from BaseSessionService and supports in-memory execution."""
    session_service = SessionService(db_path=":memory:")
    assert isinstance(session_service, BaseSessionService)
    assert isinstance(session_service, DatabaseSessionService)
    assert isinstance(session_service, SessionService)

    session_id = "test_sess_001"
    user_id = "test_user"

    session = await session_service.create_or_get_session(
        session_id=session_id,
        user_id=user_id,
        app_name="coddy",
        initial_state={"phase": "sanitize", "counter": 1},
    )

    assert session.id == session_id
    assert session.state.get("phase") == "sanitize"
    assert session.state.get("counter") == 1

    # Idempotent retrieval
    retrieved = await session_service.create_or_get_session(
        session_id=session_id,
        user_id=user_id,
        app_name="coddy",
    )
    assert retrieved.id == session_id
    assert retrieved.state.get("phase") == "sanitize"


@pytest.mark.anyio
async def test_session_service_create_or_get_classmethod():
    """Verify SessionService.create_or_get works with arbitrary BaseSessionService."""
    in_memory = InMemorySessionService()
    session_id = "test_in_mem_999"
    user_id = "test_user"

    created = await SessionService.create_or_get(
        session_service=in_memory,
        session_id=session_id,
        user_id=user_id,
        initial_state={"source": "classmethod_test"},
    )
    assert created.id == session_id
    assert created.state.get("source") == "classmethod_test"

    retrieved = await SessionService.create_or_get(
        session_service=in_memory,
        session_id=session_id,
        user_id=user_id,
    )
    assert retrieved.id == session_id
    assert retrieved.state.get("source") == "classmethod_test"


@pytest.mark.anyio
async def test_session_service_disk_persistence(tmp_path: Path):
    """Verify SessionService persists sessions and state across service instances on disk."""
    db_path = tmp_path / "data.db"

    service1 = SessionService(db_path=db_path)
    session_id = "persistent_sess_123"
    user_id = "dev_user"

    created = await service1.create_session(
        app_name="coddy",
        user_id=user_id,
        session_id=session_id,
        state={"task": "deconstruct_auth"},
    )
    assert created.id == session_id

    # Append an event
    event = Event(
        author="coding-sanitize",
        content=types.Content(parts=[types.Part(text='{"status": "ok"}')]),
    )
    await service1.append_event(session=created, event=event)

    # Re-open with a new SessionService instance reading the same SQLite file
    service2 = SessionService(db_path=db_path)
    reloaded = await service2.get_session(
        app_name="coddy",
        user_id=user_id,
        session_id=session_id,
    )
    assert reloaded is not None
    assert reloaded.id == session_id
    assert reloaded.state.get("task") == "deconstruct_auth"
    assert len(reloaded.events) >= 1
    assert reloaded.events[0].author == "coding-sanitize"
