"""Google ADK SQLite session and state management service."""

import logging
from pathlib import Path
from typing import Any

from google.adk.errors.session_not_found_error import SessionNotFoundError
from google.adk.sessions import BaseSessionService, DatabaseSessionService, Session
from sqlalchemy.ext.asyncio import AsyncEngine

from app.coddy.utils.services import SqliteService, get_user_service

logger = logging.getLogger(__name__)

DEFAULT_APP_NAME = "coddy"


class SessionService(DatabaseSessionService):
    """Google ADK SQLite session and state management service.

    Inherits from DatabaseSessionService (which subclasses BaseSessionService),
    providing automated SQLite path/URL resolution via SqliteService,
    session lifecycle helpers, and state persistence.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        db_url: str | None = None,
        db_engine: AsyncEngine | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes SessionService with an optional path, URL, or engine.

        If db_engine is provided, it is forwarded directly to DatabaseSessionService.
        If db_url is provided, it is forwarded directly to DatabaseSessionService.
        Otherwise, db_path is resolved via SqliteService (defaulting to ~/.coddy/data.db).

        Args:
            db_path: Optional Path, path string, ':memory:', or sqlite URL.
            db_url: Optional database URL string for creating a new engine.
            db_engine: Optional existing SQLAlchemy AsyncEngine instance.
            **kwargs: Additional keyword arguments passed to create_async_engine.
        """
        if db_engine is not None:
            super().__init__(db_engine=db_engine)
        elif db_url is not None:
            super().__init__(db_url=db_url, **kwargs)
        else:
            resolved_url = SqliteService(db_path=db_path).get_db_url()
            logger.debug("Initializing SessionService with URL: %s", resolved_url)
            super().__init__(db_url=resolved_url, **kwargs)

    async def create_or_get_session(
        self,
        session_id: str,
        user_id: str | None = None,
        app_name: str = DEFAULT_APP_NAME,
        initial_state: dict[str, Any] | None = None,
    ) -> Session:
        """Retrieves an existing session from this service or creates a new one.

        Args:
            session_id: Target session identifier (UUID4 string).
            user_id: Optional user identifier; defaults to current OS user via UserService.
            app_name: ADK application name string (defaults to 'coddy').
            initial_state: Optional dictionary of initial state values.

        Returns:
            The active ADK Session instance.
        """
        return await self.create_or_get(
            session_service=self,
            session_id=session_id,
            user_id=user_id,
            app_name=app_name,
            initial_state=initial_state,
        )

    @classmethod
    async def create_or_get(
        cls,
        session_service: BaseSessionService,
        session_id: str,
        user_id: str | None = None,
        app_name: str = DEFAULT_APP_NAME,
        initial_state: dict[str, Any] | None = None,
    ) -> Session:
        """Retrieves an existing session from an arbitrary BaseSessionService or creates a new one.

        Args:
            session_service: Any ADK BaseSessionService (e.g. SessionService, InMemorySessionService).
            session_id: Target session identifier (UUID4 string).
            user_id: Optional user identifier; defaults to current OS user.
            app_name: ADK application name string (defaults to 'coddy').
            initial_state: Optional dictionary of initial state values.

        Returns:
            The active ADK Session instance.
        """
        resolved_user_id = user_id or get_user_service().get_current_user_id()

        try:
            session = await session_service.get_session(
                app_name=app_name,
                user_id=resolved_user_id,
                session_id=session_id,
            )
            if session is not None:
                return session
        except SessionNotFoundError:
            pass
        except Exception as e:
            logger.debug("get_session raised exception for session %s, creating new: %s", session_id, e)

        return await session_service.create_session(
            app_name=app_name,
            user_id=resolved_user_id,
            session_id=session_id,
            state=initial_state or {},
        )
