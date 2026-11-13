"""Low-level DuckDB connection, path, and lifecycle management service."""

import logging
import os
import threading
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

DDL_TABLES = """
CREATE TABLE IF NOT EXISTS session_metrics (
    session_id VARCHAR PRIMARY KEY,
    user_id VARCHAR,
    app_name VARCHAR,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms DOUBLE,
    prompt_tokens BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    reasoning_tokens BIGINT DEFAULT 0,
    cached_tokens BIGINT DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    total_tool_calls INTEGER DEFAULT 0,
    status VARCHAR,
    error_message VARCHAR,
    total_cost_eur DOUBLE DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS step_metrics (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR,
    step_name VARCHAR,
    agent_name VARCHAR,
    model_name VARCHAR,
    thinking_level VARCHAR,
    thinking_budget INTEGER,
    temperature DOUBLE,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms DOUBLE,
    ttft_ms DOUBLE,
    tokens_per_sec DOUBLE,
    prompt_tokens BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    reasoning_tokens BIGINT DEFAULT 0,
    cached_tokens BIGINT DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    status VARCHAR,
    error_message VARCHAR,
    cost_eur DOUBLE DEFAULT 0.0,
    input_cost_eur DOUBLE DEFAULT 0.0,
    output_cost_eur DOUBLE DEFAULT 0.0,
    cache_read_cost_eur DOUBLE DEFAULT 0.0,
    cost_details VARCHAR
);

CREATE TABLE IF NOT EXISTS tool_metrics (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR,
    step_name VARCHAR,
    agent_name VARCHAR,
    tool_name VARCHAR,
    tool_args VARCHAR,
    tool_result VARCHAR,
    is_truncated BOOLEAN DEFAULT FALSE,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_ms DOUBLE,
    status VARCHAR,
    error_message VARCHAR
);
"""

DDL_VIEWS = """
CREATE OR REPLACE VIEW v_session_summary AS
SELECT
    s.session_id,
    s.user_id,
    s.app_name,
    s.start_time,
    s.end_time,
    s.duration_ms,
    s.prompt_tokens,
    s.completion_tokens,
    s.reasoning_tokens,
    s.cached_tokens,
    s.total_tokens,
    s.total_tool_calls,
    s.status,
    COUNT(DISTINCT st.id) AS step_count,
    COALESCE(s.total_cost_eur, 0.0) AS total_cost_eur
FROM session_metrics s
LEFT JOIN step_metrics st ON s.session_id = st.session_id
GROUP BY ALL;

CREATE OR REPLACE VIEW v_model_performance AS
SELECT
    model_name,
    COUNT(*) AS total_calls,
    ROUND(AVG(duration_ms), 2) AS avg_duration_ms,
    ROUND(AVG(ttft_ms), 2) AS avg_ttft_ms,
    ROUND(AVG(tokens_per_sec), 2) AS avg_tokens_per_sec,
    SUM(prompt_tokens) AS total_prompt_tokens,
    SUM(completion_tokens) AS total_completion_tokens,
    SUM(reasoning_tokens) AS total_reasoning_tokens,
    SUM(cached_tokens) AS total_cached_tokens,
    SUM(total_tokens) AS grand_total_tokens,
    ROUND(SUM(cost_eur), 6) AS total_cost_eur
FROM step_metrics
WHERE status = 'SUCCESS'
GROUP BY model_name;

CREATE OR REPLACE VIEW v_agent_performance AS
SELECT
    agent_name,
    COUNT(*) AS total_steps,
    ROUND(AVG(duration_ms), 2) AS avg_duration_ms,
    SUM(prompt_tokens) AS total_prompt_tokens,
    SUM(completion_tokens) AS total_completion_tokens,
    SUM(reasoning_tokens) AS total_reasoning_tokens,
    SUM(total_tokens) AS grand_total_tokens
FROM step_metrics
GROUP BY agent_name;

CREATE OR REPLACE VIEW v_tool_usage AS
SELECT
    tool_name,
    COUNT(*) AS total_invocations,
    ROUND(AVG(duration_ms), 2) AS avg_duration_ms,
    COUNT(CASE WHEN status = 'FAILED' THEN 1 END) AS failed_invocations,
    COUNT(CASE WHEN is_truncated THEN 1 END) AS truncated_invocations
FROM tool_metrics
GROUP BY tool_name;
"""

DDL_SCHEMA = DDL_TABLES + DDL_VIEWS


def get_default_metrics_db_path() -> Path:
    """Resolves the default DuckDB metrics database path (~/.coddy/metrics.db or $CODDY_HOME/metrics.db)."""
    env_dir = os.getenv("CODDY_HOME")
    home_path = Path(env_dir) if env_dir else Path.home() / ".coddy"
    home_path.mkdir(parents=True, exist_ok=True)
    return home_path / "metrics.db"


class DuckDbService:
    """Thread-safe DuckDB lifecycle, execution, and schema management service."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initializes DuckDbService with a filesystem path or ':memory:'.

        Args:
            db_path: Path instance, path string, or ':memory:'. Defaults to get_default_metrics_db_path().
        """
        self._lock = threading.RLock()
        self._conn: duckdb.DuckDBPyConnection | None = None

        if db_path is None:
            self._path: Path | None = get_default_metrics_db_path()
            self._is_memory = False
        elif isinstance(db_path, Path):
            self._path = db_path
            self._is_memory = False
        else:
            raw = str(db_path).strip()
            if raw == ":memory:":
                self._path = None
                self._is_memory = True
            else:
                self._path = Path(raw)
                self._is_memory = False

    @property
    def is_memory(self) -> bool:
        """Indicates whether this service points to an in-memory DuckDB database."""
        return self._is_memory

    @property
    def db_path(self) -> Path | None:
        """Returns the filesystem Path for the database, or None if in-memory."""
        return self._path

    def ensure_database_dir(self) -> Path | None:
        """Ensures the parent directory for the DuckDB file exists.

        Returns:
            The Path of the parent directory, or None if using an in-memory database.
        """
        if self._path is not None:
            parent_dir = self._path.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            return parent_dir
        return None

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Retrieves or creates the open DuckDB connection and initializes the schema.

        Returns:
            Open DuckDB connection instance.
        """
        with self._lock:
            if self._conn is None:
                if self._is_memory:
                    self._conn = duckdb.connect(":memory:")
                else:
                    self.ensure_database_dir()
                    assert self._path is not None
                    self._conn = duckdb.connect(str(self._path.resolve()))
                self._init_schema(self._conn)
            return self._conn

    def _init_schema(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Executes the DDL statements for tables, migrations, and views."""
        try:
            conn.execute(DDL_TABLES)
            migrations = [
                "ALTER TABLE step_metrics ADD COLUMN IF NOT EXISTS cost_eur DOUBLE DEFAULT 0.0;",
                "ALTER TABLE step_metrics ADD COLUMN IF NOT EXISTS input_cost_eur DOUBLE DEFAULT 0.0;",
                "ALTER TABLE step_metrics ADD COLUMN IF NOT EXISTS output_cost_eur DOUBLE DEFAULT 0.0;",
                "ALTER TABLE step_metrics ADD COLUMN IF NOT EXISTS cache_read_cost_eur DOUBLE DEFAULT 0.0;",
                "ALTER TABLE step_metrics ADD COLUMN IF NOT EXISTS cost_details VARCHAR;",
                "ALTER TABLE session_metrics ADD COLUMN IF NOT EXISTS total_cost_eur DOUBLE DEFAULT 0.0;",
            ]
            for mig in migrations:
                conn.execute(mig)
            conn.execute(DDL_VIEWS)
        except Exception as exc:
            logger.error("Failed to initialize DuckDB schema: %s", exc)
            raise

    def execute(self, query: str, parameters: list[Any] | tuple[Any, ...] | None = None) -> duckdb.DuckDBPyConnection:
        """Executes a SQL query within the thread-safe connection lock.

        Args:
            query: SQL query string.
            parameters: Optional query parameters.

        Returns:
            The connection after execution.
        """
        with self._lock:
            conn = self.get_connection()
            if parameters:
                return conn.execute(query, parameters)
            return conn.execute(query)

    def fetchall(self, query: str, parameters: list[Any] | tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """Executes a query and fetches all rows.

        Args:
            query: SQL query string.
            parameters: Optional query parameters.

        Returns:
            List of row tuples.
        """
        with self._lock:
            conn = self.get_connection()
            if parameters:
                cursor = conn.execute(query, parameters)
            else:
                cursor = conn.execute(query)
            return cursor.fetchall()

    def fetchone(self, query: str, parameters: list[Any] | tuple[Any, ...] | None = None) -> tuple[Any, ...] | None:
        """Executes a query and fetches a single row.

        Args:
            query: SQL query string.
            parameters: Optional query parameters.

        Returns:
            Single row tuple or None.
        """
        with self._lock:
            conn = self.get_connection()
            if parameters:
                cursor = conn.execute(query, parameters)
            else:
                cursor = conn.execute(query)
            return cursor.fetchone()

    def close(self) -> None:
        """Closes the DuckDB connection if currently open."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception as exc:
                    logger.debug("Exception closing DuckDB connection: %s", exc)
                finally:
                    self._conn = None

    def __enter__(self) -> "DuckDbService":
        self.get_connection()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def get_duckdb_service(db_path: Path | str | None = None) -> DuckDbService:
    """Factory helper creating a DuckDbService instance."""
    return DuckDbService(db_path=db_path)
