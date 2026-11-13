"""Low-level SQLite connection, path, and URL resolution service."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_default_data_db_path() -> Path:
    """Resolves the default SQLite database path (~/.coddy/data.db or $CODDY_HOME/data.db)."""
    env_dir = os.getenv("CODDY_HOME")
    home_path = Path(env_dir) if env_dir else Path.home() / ".coddy"
    home_path.mkdir(parents=True, exist_ok=True)
    return home_path / "data.db"


class SqliteService:
    """Manages SQLite path resolution, directory initialization, and async connection URLs."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initializes SqliteService with a filesystem path, in-memory indicator, or connection URL.

        Args:
            db_path: Path instance, path string, ':memory:', or full sqlite URL. Defaults to get_default_data_db_path().
        """
        if db_path is None:
            self._path: Path | None = get_default_data_db_path()
            self._is_memory = False
            self._custom_url: str | None = None
        elif isinstance(db_path, Path):
            self._path = db_path
            self._is_memory = False
            self._custom_url = None
        else:
            raw = str(db_path).strip()
            if raw == ":memory:" or raw == "sqlite:///:memory:" or raw == "sqlite+aiosqlite:///:memory:":
                self._path = None
                self._is_memory = True
                self._custom_url = "sqlite+aiosqlite:///:memory:"
            elif raw.startswith("sqlite+aiosqlite://") or raw.startswith("sqlite://"):
                self._path = None
                self._is_memory = False
                # Normalize sqlite:// to sqlite+aiosqlite://
                if raw.startswith("sqlite://") and not raw.startswith("sqlite+aiosqlite://"):
                    self._custom_url = raw.replace("sqlite://", "sqlite+aiosqlite://", 1)
                else:
                    self._custom_url = raw
            else:
                self._path = Path(raw)
                self._is_memory = False
                self._custom_url = None

    @property
    def is_memory(self) -> bool:
        """Indicates whether this service points to an in-memory SQLite database."""
        return self._is_memory

    @property
    def db_path(self) -> Path | None:
        """Returns the filesystem Path for the database, or None if in-memory or custom URL."""
        return self._path

    def ensure_database_dir(self) -> Path | None:
        """Ensures the parent directory for the SQLite database file exists.

        Returns:
            The Path of the parent directory, or None if using an in-memory database or remote URL.
        """
        if self._path is not None:
            parent_dir = self._path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            return parent_dir
        return None

    def get_db_url(self) -> str:
        """Returns the async driver database URL string (sqlite+aiosqlite:///...).

        Returns:
            Formatted database URL ready for SQLAlchemy / DatabaseSessionService.
        """
        if self._custom_url is not None:
            return self._custom_url
        if self._is_memory:
            return "sqlite+aiosqlite:///:memory:"
        if self._path is not None:
            self.ensure_database_dir()
            abs_path = self._path.resolve()
            return f"sqlite+aiosqlite:///{abs_path}"
        raise ValueError("Cannot resolve SQLite URL: neither path, memory, nor custom URL is set.")


def get_sqlite_service(db_path: Path | str | None = None) -> SqliteService:
    """Factory helper creating a SqliteService instance."""
    return SqliteService(db_path=db_path)
