"""Filesystem path and environment resolution helpers for Coddy services.

Coddy directory structure:
  ~/.coddy/
    data.db                     # SQLite for ADK Sessions and State (working memory)
    memory.db                   # LadybugDB for long-term memory / knowledge graph
    metrics.db                  # DuckDB for execution and token metrics
    <session_id>/
      artifacts/                # Workflow artifacts (.md, .json)
"""

import os
import uuid
from datetime import datetime
from pathlib import Path


def get_coddy_home_dir() -> Path:
    """Resolves the Coddy home directory (~/.coddy by default)."""
    env_dir = os.getenv("CODDY_HOME")
    if env_dir:
        home_path = Path(env_dir)
    else:
        home_path = Path.home() / ".coddy"
    home_path.mkdir(parents=True, exist_ok=True)
    return home_path


def resolve_session_id(session_id: str | None = None) -> str:
    """Resolves the active session or conversation identifier."""
    if session_id:
        return session_id
    env_id = os.getenv("CODDY_SESSION_ID") or os.getenv("SESSION_ID")
    if env_id:
        return env_id
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def get_session_dir(session_id: str | None = None) -> Path:
    """Resolves the directory for a specific session: ~/.coddy/<session_id>/."""
    sid = resolve_session_id(session_id)
    session_dir = get_coddy_home_dir() / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_artifacts_dir(session_id: str | None = None) -> Path:
    """Resolves the artifacts directory: ~/.coddy/<session_id>/artifacts/."""
    artifacts_dir = get_session_dir(session_id) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def get_data_db_path() -> Path:
    """Path to the SQLite database for ADK sessions and state: ~/.coddy/data.db."""
    return get_coddy_home_dir() / "data.db"


def get_memory_db_path() -> Path:
    """Path to the LadybugDB database for long-term memory: ~/.coddy/memory.db."""
    return get_coddy_home_dir() / "memory.db"


def get_metrics_db_path() -> Path:
    """Path to the DuckDB database for execution metrics: ~/.coddy/metrics.db."""
    return get_coddy_home_dir() / "metrics.db"
